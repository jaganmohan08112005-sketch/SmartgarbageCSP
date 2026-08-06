import hashlib
import math
import os
import random
import requests
from datetime import datetime

from flask import (current_app, flash, jsonify, redirect, render_template, request, session, send_file, url_for)

from werkzeug.utils import secure_filename

from werkzeug.security import generate_password_hash

from ..models import (AuditLog, BWGDeclaration, Complaint, DispatchAssignment, FirmwareRelease, IllegalDumpReport, IncidentLog, MaintenanceWorkOrder, Notification, OfflineDelivery, PAYTInvoice, SensorHealth, SmartBin, User, Webhook, WorkerProfile, utcnow)

from ..ml_model import predict_overflow_eta_hours

from ..auth import admin_required, login_required, superadmin_required

from .. import db, socketio

from . import (DEFAULT_LAT, DEFAULT_LON, DUMP_YARDS, FORECAST_URGENT_HOURS, SECTOR_POLYGONS, _create_razorpay_refund, _driver_route_sheet_pdf, _forecast_priority, _notify_admins, _notify_status_change, _publish_admin_alerts, _publish_user_event, fit_length, main, point_in_polygon, record_complaint_event, validate_indian_phone, write_audit)


@main.route('/api/illegal-reports')
@admin_required
def api_illegal_reports():
    """Recent illegal-dump reports (dev/demo helper for the sandbox UI)."""
    limit = min(int(request.args.get('limit', 10) or 10), 50)
    rows = IllegalDumpReport.query.order_by(IllegalDumpReport.timestamp.desc()).limit(limit).all()
    return jsonify([
        {
            'id': r.id,
            'category': r.category,
            'description': (r.description or '')[:120],
            'status': r.status,
            'latitude': r.latitude,
            'longitude': r.longitude,
            'scrubbed_photo': r.scrubbed_photo,
            'timestamp': r.timestamp.isoformat() if r.timestamp else None,
        }
        for r in rows
    ])


@main.route('/admin')
@admin_required
def admin():
    # NOTE: check_sensor_faults()/check_decomposition_timers() were REMOVED
    # from the per-load path — they ran 2 full-table scans + 2N queries on
    # EVERY admin page load. They now run on a 15-minute scheduled RQ job
    # (see jobs.py: maintenance_job) so the admin dashboard stays fast.
    complaints = Complaint.query.order_by(Complaint.id.desc()).all()
    bins = SmartBin.query.all()
    workers = WorkerProfile.query.all()
    incidents = IncidentLog.query.order_by(IncidentLog.id.desc()).all()
    sensor_healths = SensorHealth.query.all()
    firmware_releases = FirmwareRelease.query.order_by(FirmwareRelease.created_at.desc()).all()
    illegal_reports = IllegalDumpReport.query.order_by(IllegalDumpReport.timestamp.desc()).all()
    bwg_requests = BWGDeclaration.query.filter_by(request_bulk_pickup=True, pickup_status='Pending').all()
    # Recent PAYT invoices for the waive/refund ledger (admin billing actions).
    payt_invoices = PAYTInvoice.query.order_by(PAYTInvoice.issued_at.desc()).limit(30).all()
    kpis = {
        "total_bins": len(bins),
        "critical_bins": len([b for b in bins if b.status == "Critical"]),
        "active_trucks": len([w for w in workers if w.status == "Active"]),
        "pending_complaints": len([c for c in complaints if c.status == "Pending"]),
        "daily_waste_tons": round(sum(b.level for b in bins) * 0.045, 2),
        "sensor_faults": len([b for b in bins if b.sensor_fault]),
        "geofence_violations": len([w for w in workers if w.geofence_violation]),
        "pending_pickups": len(bwg_requests),
    }
    current_user = User.query.get(session.get('user_id'))
    webhooks = [w.url for w in Webhook.query.order_by(Webhook.id).all()]
    return render_template('admin.html', complaints=complaints, bins=bins, workers=workers,
                           incidents=incidents, kpis=kpis, webhooks=webhooks,
                           sensor_healths=sensor_healths, firmware_releases=firmware_releases,
                           illegal_reports=illegal_reports, bwg_requests=bwg_requests,
                           payt_invoices=payt_invoices,
                           dump_yards=DUMP_YARDS,
                           is_superadmin=(current_user.is_superadmin if current_user else False))


@main.route('/api/route-optimize')
@login_required
def route_optimize():
    critical_bins = SmartBin.query.filter(
        db.or_(
            SmartBin.level >= 80,
            (SmartBin.overflow_eta_hours.isnot(None))
            & (SmartBin.overflow_eta_hours <= FORECAST_URGENT_HOURS),
        )
    ).all()
    # Cap the problem size so the endpoint always answers promptly even with a
    # huge grid (nearest-neighbour + 2-opt is O(n²) per pair of bins).
    critical_bins = sorted(critical_bins, key=_forecast_priority)[:12]
    depot = {"lat": DEFAULT_LAT, "lon": DEFAULT_LON, "label": "Municipal HQ (Depot)"}
    if not critical_bins:
        return jsonify({"route": [depot], "total_distance": 0,
                        "message": "No critical bins today.", "optimized_with": "none"})

    nodes = [{"lat": b.latitude, "lon": b.longitude, "label": b.hardware_id,
              "ward": b.ward, "level": b.level,
              "overflow_eta_hours": b.overflow_eta_hours} for b in critical_bins]

    # ── Distance helpers ──────────────────────────────────────
    def haversine_km(la1, lo1, la2, lo2):
        R = 6371.0  # Earth radius km
        phi1, phi2 = math.radians(la1), math.radians(la2)
        dphi = math.radians(la2 - la1)
        dlmb = math.radians(lo2 - lo1)
        a = math.sin(dphi / 2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlmb / 2)**2
        return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    # Shared session for road-distance calls (created lazily on first use).
    _osrm_session = None

    def road_km(a, b):
        """Real road-network distance via OSRM. Falls back to Haversine on any error."""
        nonlocal _osrm_session
        try:
            if _osrm_session is None:
                _osrm_session = requests.Session()  # reuse connections (fast)
            url = (f"https://router.project-osrm.org/route/v1/driving/"
                   f"{a['lon']},{a['lat']};{b['lon']},{b['lat']}?overview=false")
            r = _osrm_session.get(url, timeout=2)
            if r.status_code == 200:
                return r.json()["routes"][0]["distance"] / 1000.0
        except Exception:
            pass
        return haversine_km(a["lat"], a["lon"], b["lat"], b["lon"])

    # ── Build distance matrix (Haversine by default; OSRM only if it answers
    # promptly — a healthy network round-trip takes well under a second, so a
    # slow/half-reachable OSRM (which would stall every pair call) is skipped).
    # Road pairs are fetched in a small thread pool so the endpoint returns in
    # ~one round trip instead of n² × timeout seconds. road_km never raises
    # (it falls back to Haversine internally), so a legit 0.0 distance only
    # happens for i == j and is excluded below. ──
    n = len(nodes)
    use_road = False
    try:
        import time as _time
        _probe = requests.Session()
        _t0 = _time.time()
        _probe.get("https://router.project-osrm.org/route/v1/driving/83.40,18.05;83.41,18.06?overview=false", timeout=2)
        use_road = (_time.time() - _t0) < 1.5
    except Exception:
        use_road = False

    dist = [[0.0] * n for _ in range(n)]
    if use_road:
        from concurrent.futures import ThreadPoolExecutor, as_completed
        with ThreadPoolExecutor(max_workers=8) as _ex:
            _futures = {
                _ex.submit(road_km, nodes[i], nodes[j]): (i, j)
                for i in range(n) for j in range(n) if i != j
            }
            for _f in as_completed(_futures):
                _i, _j = _futures[_f]
                dist[_i][_j] = _f.result()
        # Fallback for any pair the pool left at 0.0 (never for i == j).
        for i in range(n):
            for j in range(n):
                if i != j and dist[i][j] == 0.0:
                    dist[i][j] = haversine_km(nodes[i]["lat"], nodes[i]["lon"], nodes[j]["lat"], nodes[j]["lon"])
    else:
        for i in range(n):
            for j in range(n):
                if i != j:
                    dist[i][j] = haversine_km(nodes[i]["lat"], nodes[i]["lon"], nodes[j]["lat"], nodes[j]["lon"])

    # ── Solve TSP with networkx (nearest-neighbour + 2-opt refinement) ──
    try:
        import networkx as nx
        G = nx.complete_graph(n)
        for i in range(n):
            for j in range(n):
                if i != j:
                    G[i][j]["weight"] = dist[i][j]
        # initial tour via greedy nearest neighbour
        tour = [0]
        remaining = set(range(1, n))
        while remaining:
            last = tour[-1]
            nxt = min(remaining, key=lambda k: dist[last][k])
            tour.append(nxt)
            remaining.discard(nxt)
        # 2-opt improvement
        improved = True
        while improved:
            improved = False
            for a in range(len(tour) - 1):
                for b in range(a + 1, len(tour)):
                    if b - a == 1:
                        continue
                    new = tour[:a + 1] + tour[a + 1:b + 1][::-1] + tour[b + 1:]

                    def cost(t):
                        c = dist[t[-1]][t[0]]
                        for k in range(len(t) - 1):
                            c += dist[t[k]][t[k + 1]]
                        return c
                    if cost(new) < cost(tour) - 1e-9:
                        tour = new
                        improved = True
        order = tour
        method = "networkx-tsp-2opt" + ("-road" if use_road else "-haversine")
    except Exception:
        # Fallback: greedy nearest neighbour on straight-line
        order = []
        current = depot
        unvisited = list(range(n))
        while unvisited:
            cidx = min(unvisited, key=lambda k: dist[k][0] if current is depot
                       else haversine_km(current["lat"], current["lon"], nodes[k]["lat"], nodes[k]["lon"]))
            order.append(cidx)
            current = nodes[cidx]
            unvisited.remove(cidx)
        method = "greedy-haversine-fallback"

    route = [depot]
    total = 0.0
    prev = depot
    for idx in order:
        node = nodes[idx]
        if prev is depot:
            seg = dist[idx][0] if use_road else haversine_km(depot["lat"], depot["lon"], node["lat"], node["lon"])
        else:
            seg = road_km(prev, node) if use_road else haversine_km(prev["lat"], prev["lon"], node["lat"], node["lon"])
        total += seg
        route.append(node)
        prev = node
    back = road_km(prev, depot) if use_road else haversine_km(prev["lat"], prev["lon"], depot["lat"], depot["lon"])
    total += back
    route.append(depot)

    # ── Resource-savings dashboard: show exactly what dynamic routing buys ──
    # vs. the static 45 km/day baseline the municipality used to run. Fuel at
    # ₹62/km (diesel + wear, urban collection truck average) and manpower at
    # ~24 km/h effective service speed + 4 min per stop.
    traditional_km = 45.0
    saved_km = max(0.0, traditional_km - total)
    co2_saved_kg = round(saved_km * 0.21, 2)
    fuel_saved_rs = round(saved_km * 62.0, 2)
    manpower_hours = round(total / 24.0 + len(critical_bins) * (4.0 / 60.0), 2)
    traditional_hours = round(traditional_km / 24.0 + len(critical_bins) * (4.0 / 60.0), 2)
    manpower_saved_hours = round(max(0.0, traditional_hours - manpower_hours), 2)
    write_audit("ROUTE_OPTIMIZE", detail=f"Optimized route ({method}): {round(total, 2)}km, {len(critical_bins)} critical bins, ~₹{fuel_saved_rs} fuel saved.")
    return jsonify({"route": route, "total_distance": round(total, 2),
                    "critical_count": len(critical_bins), "co2_saved_kg": co2_saved_kg,
                    "fuel_saved_rs": fuel_saved_rs,
                    "manpower_hours": manpower_hours,
                    "manpower_saved_hours": manpower_saved_hours,
                    "optimized_with": method})


@main.route('/api/overflow-forecast')
@admin_required
def overflow_forecast():
    """Bins ranked by forecast hours-to-overflow for proactive dispatch.

    Returns every bin that currently has a forecast (or can be forecast from
    its telemetry), sorted by urgency, so the admin control room can dispatch
    a truck before a bin overflows rather than after. Admin-only: exposes
    per-bin coordinates + forecasts (dispatch-grade data), not citizen-facing.
    """
    rows = []
    for b in SmartBin.query.order_by(SmartBin.level.desc()).all():
        eta = b.overflow_eta_hours
        if eta is None:
            # Lazy-compute for bins seeded before the forecast pipeline existed
            # (e.g. demo data) — best-effort, never raises.
            try:
                eta = predict_overflow_eta_hours(b)
            except Exception:
                eta = None
        if eta is None:
            continue
        rows.append({
            "hardware_id": b.hardware_id,
            "ward": b.ward,
            "level": b.level,
            "status": b.status,
            "overflow_eta_hours": eta,
            "urgent": eta <= FORECAST_URGENT_HOURS,
            "critical": b.level >= 80,
            "latitude": b.latitude,
            "longitude": b.longitude,
        })
    rows.sort(key=lambda r: (r["overflow_eta_hours"], -r["level"]))
    return jsonify({"bins": rows, "urgent_threshold_hours": FORECAST_URGENT_HOURS})


@main.route('/api/fleet-location')
@admin_required
def fleet_location():
    """Fleet positions for the admin control room. READ-ONLY: previously this
    GET mutated the DB (writing geofence_violation on a read). Violations are
    now persisted only by the worker GPS heartbeat endpoint (/api/worker/gps)."""
    workers = WorkerProfile.query.filter(WorkerProfile.status == 'Active').all()
    fleet = []
    for w in workers:
        # Use the worker's last reported GPS when available, else simulate
        # slight drift from assigned position (dev-only visualisation).
        if w.current_lat is not None and w.current_lon is not None:
            lat, lon = w.current_lat, w.current_lon
        else:
            lat = w.latitude + random.uniform(-0.001, 0.001)
            lon = w.longitude + random.uniform(-0.001, 0.001)
        sector_poly = SECTOR_POLYGONS.get(w.vehicle_id, [])
        in_bounds = point_in_polygon(lat, lon, sector_poly) if sector_poly else True
        fleet.append({
            "vehicle_id": w.vehicle_id,
            "worker_username": w.user.username if w.user else "Unknown",
            "lat": lat, "lon": lon,
            "status": w.status,
            "in_bounds": in_bounds,
            "geofence_violation": w.geofence_violation
        })
    # Push the fresh fleet positions to the live admin control room.
    socketio.emit('fleet_update', {"fleet": fleet})

    return jsonify(fleet)


def _is_ssrf_blocked(hostname):
    """True when a hostname resolves to a private/loopback/link-local IP.

    SSRF guard: an admin could register `http://169.254.169.254/` (cloud
    metadata) and the dispatch_webhooks_job would POST to it, leaking cloud
    credentials. Resolve the hostname and reject any IP in the RFC1918
    private, loopback, link-local, or metadata ranges.
    """
    import ipaddress
    try:
        import socket
        infos = socket.getaddrinfo(hostname, None)
        for info in infos:
            ip = ipaddress.ip_address(info[4][0])
            if (ip.is_private or ip.is_loopback or ip.is_link_local
                    or ip.is_multicast or ip.is_reserved
                    or ip.is_unspecified):
                return True
        return False
    except Exception:
        # DNS failure — treat as blocked (fail closed).
        return True


@main.route('/api/webhooks', methods=['POST'])
@admin_required
def configure_webhooks():
    url = request.form.get('webhook_url', '').strip()
    if url:
        try:
            from urllib.parse import urlparse
            parsed_url = urlparse(url)
            if parsed_url.scheme not in ('http', 'https'):
                flash('Invalid webhook URL: must use http or https.', 'error')
                return redirect(url_for('main.admin'))
            if not parsed_url.hostname:
                flash('Invalid webhook URL: hostname is required.', 'error')
                return redirect(url_for('main.admin'))
            # SSRF guard: reject URLs that resolve to private/loopback/link-local
            # IPs (cloud metadata, internal services, localhost).
            if _is_ssrf_blocked(parsed_url.hostname):
                flash('Invalid webhook URL: private/loopback addresses are not allowed.', 'error')
                return redirect(url_for('main.admin'))
        except Exception:
            flash('Invalid webhook URL format.', 'error')
            return redirect(url_for('main.admin'))
        # VARCHAR(500) on Postgres — reject URLs that would overflow the column.
        if len(url) > 500:
            flash('Webhook URL is too long (max 500 characters).', 'error')
            return redirect(url_for('main.admin'))
        existing = Webhook.query.filter_by(url=url).first()
        if existing is None:
            # Persist so the registration survives restarts and is shared across
            # workers (the old in-memory list was silently lost on every deploy).
            db.session.add(Webhook(url=url))
            db.session.commit()
            write_audit("WEBHOOK_ADD", target=url, detail="Webhook URL registered.")
            flash(f"Webhook registered: {url}", "success")
    return redirect(url_for('main.admin'))


@main.route('/api/bins.geojson')
@admin_required
def bins_geojson():
    """GeoJSON FeatureCollection of all bins for the Leaflet control room.

    One contract feeds every map view (admin GIS tab, fleet geo-fencing);
    properties carry the status/urgency fields the markers color by.
    """
    # Bins without coordinates would emit [null, null] and break marker
    # rendering — a bin only maps once it has reported a position.
    bins = [b for b in SmartBin.query.all()
            if b.latitude is not None and b.longitude is not None]
    return jsonify({
        'type': 'FeatureCollection',
        'features': [{
            'type': 'Feature',
            'geometry': {'type': 'Point', 'coordinates': [b.longitude, b.latitude]},
            'properties': {
                'id': b.id, 'hardware_id': b.hardware_id, 'ward': b.ward,
                'level': b.level, 'status': b.status,
                'overflow_eta_hours': b.overflow_eta_hours,
                'battery_level': b.battery_level,
                'sensor_fault': b.sensor_fault,
                'lid_open': b.lid_open,
                'last_seen': b.last_updated.isoformat() if b.last_updated else None,
            },
        } for b in bins],
    })


@main.route('/admin/route-sheet.pdf')
@admin_required
def route_sheet_pdf():
    """Printable A5 dispatch route sheet for the current assignments."""
    from io import BytesIO
    assignments = (DispatchAssignment.query
                   .filter_by(status='Assigned')
                   .order_by(DispatchAssignment.eta_hours.is_(None),
                             DispatchAssignment.eta_hours.asc())
                   .all())
    pdf = _driver_route_sheet_pdf(assignments)
    return send_file(BytesIO(pdf), mimetype='application/pdf',
                     as_attachment=True, download_name='dispatch_route_sheet.pdf')


# ── Sensor-health control room: faulted bins + open Sensor Fault incidents ──
@main.route('/api/sensor-faults')
@admin_required
def sensor_faults_api():
    """Everything the sensor-health view renders in one contract.

    Faulted bins come from two sources: the stuck-sensor classifier (constant
    >=95% level across 5 pings) and the stale-sensor sweep (no telemetry for
    >24h). Open 'Sensor Fault' IncidentLog rows carry the actionable incidents
    the control room resolves — clearing a bin's fault resolves its incidents
    (see clear_bin_fault).
    """
    faulted = [b for b in SmartBin.query.all() if b.sensor_fault]
    incidents = IncidentLog.query.filter_by(
        incident_type='Sensor Fault', status='Active').all()
    incident_ids = {inc.bin_id for inc in incidents}
    active_orders = MaintenanceWorkOrder.query.filter(
        MaintenanceWorkOrder.status.in_(['Scheduled', 'In Progress'])).count()
    kpis = {
        'faulted_bins': len(faulted),
        'open_incidents': len(incidents),
        'maintenance_scheduled': sum(1 for b in faulted
                                     if b.sensor_health and b.sensor_health.maintenance_scheduled),
        'active_work_orders': active_orders,
    }
    return jsonify({
        'kpis': kpis,
        'bins': [{
            'id': b.id,
            'hardware_id': b.hardware_id,
            'ward': b.ward,
            'level': b.level,
            'status': b.status,
            'fault_reason': (b.sensor_health.fault_reason if b.sensor_health else None),
            'maintenance_scheduled': bool(b.sensor_health and b.sensor_health.maintenance_scheduled),
            'last_ping': b.last_updated.isoformat() if b.last_updated else None,
            'open_incidents': b.id in incident_ids,
        } for b in faulted],
        'incidents': [{
            'id': inc.id,
            'bin_id': inc.bin_id,
            'hardware_id': inc.bin.hardware_id if inc.bin else None,
            'severity': inc.severity,
            'description': inc.description,
            'since': inc.timestamp.isoformat() if inc.timestamp else None,
        } for inc in incidents],
    })


@main.route('/api/bins/<hw_id>/clear-fault', methods=['POST'])
@admin_required
def clear_bin_fault(hw_id):
    """Manually clear a bin's sensor fault (e.g. after on-site inspection).

    Unflags the bin + SensorHealth record, resolves every open 'Sensor Fault'
    incident for the bin, and writes a BIN_FAULT_CLEARED audit entry with the
    acting admin's identity — all in one transaction so a failure rolls back
    the whole action (no half-cleared state).

    Optional maintenance follow-up: when the request body carries
    `schedule_maintenance`, a MaintenanceWorkOrder is minted for the chosen
    worker with a due date. The bin leaves the faulted state but stays
    maintenance-scheduled until the worker completes the order (the sensor
    health view tracks it in the work-orders table).
    """
    b = SmartBin.query.filter_by(hardware_id=hw_id).first()
    if b is None:
        return jsonify({'success': False, 'message': 'Bin not found.'}), 404
    if not b.sensor_fault:
        return jsonify({'success': False, 'message': 'Bin is not currently faulted.'}), 400

    data = request.get_json(silent=True) or {}
    schedule_maintenance = bool(data.get('schedule_maintenance'))
    worker = due_date = None
    if schedule_maintenance:
        try:
            worker_id = int(data.get('worker_id'))
        except (TypeError, ValueError):
            worker_id = None
        worker = WorkerProfile.query.get(worker_id) if worker_id else None
        if worker is None:
            return jsonify({'success': False, 'message': 'A maintenance worker must be selected.'}), 400
        due_date = _parse_due_date(data.get('due_date'))
        if due_date is None:
            return jsonify({'success': False, 'message': 'A valid due date (YYYY-MM-DD) is required.'}), 400

    open_incs = IncidentLog.query.filter_by(
        bin_id=b.id, incident_type='Sensor Fault', status='Active').all()
    b.sensor_fault = False
    if b.sensor_health:
        b.sensor_health.fault_flag = False
        b.sensor_health.fault_reason = None
        b.sensor_health.maintenance_scheduled = schedule_maintenance  # stays True until the order completes
    for inc in open_incs:
        inc.status = 'Resolved'

    order = None
    if schedule_maintenance:
        order = MaintenanceWorkOrder(
            bin_id=b.id, worker_id=worker.id, created_by=session['user_id'],
            due_date=due_date, notes=fit_length(data.get('notes', ''), 300) or None)
        db.session.add(order)
        # Flush so the audit rows can reference the real order id (immutable
        # ledger — correlating the audit to the work order must be possible).
        db.session.flush()
        worker_label = worker.user.username if worker.user else f'worker #{worker.id}'
        write_audit("MAINTENANCE_ORDER_CREATED", target=hw_id,
                    detail=f"Maintenance order #{order.id} scheduled for {worker_label}, due {due_date.strftime('%Y-%m-%d')}",
                    commit=False)
        detail = (f"Manual clear by admin — maintenance work order #{order.id} scheduled "
                  f"(due {due_date.strftime('%Y-%m-%d')}), {len(open_incs)} incident(s) resolved")
    else:
        detail = f"Manual clear by admin — {len(open_incs)} open incident(s) resolved"
    write_audit("BIN_FAULT_CLEARED", target=hw_id, detail=detail, commit=False)
    msg = f"🧹 Sensor fault cleared on {hw_id} by {session.get('username', 'admin')}."
    if order:
        msg += f" Maintenance work order #{order.id} scheduled (due {due_date.strftime('%Y-%m-%d')})."
    staged = _notify_admins(msg, link="/admin#sensor-fault-section")
    db.session.commit()
    # Live alert after the commit — a toast must never announce a clear that
    # rolled back.
    _publish_admin_alerts(staged)
    return jsonify({'success': True, 'resolved_incidents': len(open_incs),
                    'maintenance_order_id': order.id if order else None,
                    'maintenance_scheduled': bool(order)})


def _parse_due_date(raw):
    """Parse 'YYYY-MM-DD' (date input) or ISO 'YYYY-MM-DDTHH:MM' into a naive
    UTC datetime; returns None for anything unparseable so callers can 400."""
    if not raw:
        return None
    raw = str(raw).strip()
    for fmt in ('%Y-%m-%d', '%Y-%m-%dT%H:%M', '%Y-%m-%d %H:%M'):
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue
    return None


@main.route('/api/maintenance')
@admin_required
def maintenance_api():
    """Maintenance work orders + the worker pool, in one control-room contract.

    Active orders (Scheduled / In Progress) come first ordered by due date
    (overdue flagged read-side), then the most recent completed orders. The
    worker list feeds the schedule-maintenance form's dropdown.
    """
    active = (MaintenanceWorkOrder.query
              .filter(MaintenanceWorkOrder.status.in_(['Scheduled', 'In Progress']))
              .order_by(MaintenanceWorkOrder.due_date.is_(None),
                        MaintenanceWorkOrder.due_date.asc())
              .all())
    completed = (MaintenanceWorkOrder.query
                 .filter_by(status='Completed')
                 .order_by(MaintenanceWorkOrder.completed_at.desc())
                 .limit(10).all())
    now = utcnow()

    def _row(o):
        return {
            'id': o.id,
            'bin_id': o.bin_id,
            'hardware_id': o.bin.hardware_id if o.bin else None,
            'ward': o.bin.ward if o.bin else None,
            'worker_id': o.worker_id,
            'worker_name': o.worker.user.username if (o.worker and o.worker.user) else None,
            'vehicle_id': o.worker.vehicle_id if o.worker else None,
            'status': o.status,
            'due_date': o.due_date.isoformat() if o.due_date else None,
            'overdue': bool(o.due_date and o.status != 'Completed' and o.due_date < now),
            'notes': o.notes,
            'created_at': o.created_at.isoformat() if o.created_at else None,
            'completed_at': o.completed_at.isoformat() if o.completed_at else None,
        }

    workers = [{
        'id': w.id,
        'name': w.user.username if w.user else f'Worker {w.id}',
        'vehicle_id': w.vehicle_id,
        'status': w.status,
    } for w in WorkerProfile.query.order_by(WorkerProfile.id.asc()).all()]
    return jsonify({'orders': [_row(o) for o in active + completed],
                    'workers': workers})


@main.route('/resolve/<int:id>')
@admin_required
def resolve_complaint(id):
    complaint = Complaint.query.get_or_404(id)
    if complaint.status != 'Resolved':
        complaint.status = 'Resolved'
        complaint.resolved_at = utcnow()
        # Push an in-app notification to the reporting citizen
        if complaint.user_id:
            note = Notification(
                user_id=complaint.user_id,
                message=f"Your complaint #{id} in {complaint.ward} has been resolved. Thank you!",
                link='/dashboard'
            )
            db.session.add(note)
            # Real-time: publish to the citizen's SSE channel (no-op without Redis)
            _publish_user_event(complaint.user_id, note.message)
        db.session.commit()
        # Citizen-tracking timeline: the resolution is a first-class event
        record_complaint_event(complaint, 'Resolved',
                               'Resolved by the sanitation control room.')
        # Out-of-band status alert (WhatsApp / SMS / email fallback)
        _notify_status_change(complaint)
        write_audit("RESOLVE_COMPLAINT", target=f"Complaint #{id}", detail=f"Ward: {complaint.ward}")
        flash(f"Complaint #{id} resolved.", "success")
    return redirect(url_for('main.admin'))


@main.route('/admin/run-dunning', methods=['POST'])
@admin_required
def run_dunning():
    from ..jobs import enqueue, dunning_job
    result = enqueue(dunning_job)
    if isinstance(result, int):
        flash(f"Dunning run complete: {result} overdue invoice reminder(s) created.", 'success')
    else:
        flash("Dunning run enqueued in the background.", 'success')
    return redirect(url_for('main.admin'))


@main.route('/admin/failed-jobs')
@admin_required
def failed_jobs_dashboard():
    from ..jobs import failed_jobs
    jobs = failed_jobs()
    return render_template('failed_jobs.html', jobs=jobs, job_count=len(jobs))


@main.route('/api/jobs/status')
@admin_required
def jobs_status():
    """Queue observability: depth, active workers, recent job outcomes with
    per-job durations, and Prometheus-style counters.

    Returns JSON by default; append ?format=prometheus for Prometheus text
    exposition (scrapable by a /metrics collector). Degrades to the inline
    (no-Redis) picture with in-process counters when no broker is configured.
    """
    from ..jobs import queue_status, prometheus_exposition
    if request.args.get('format') == 'prometheus':
        data = queue_status()
        body = prometheus_exposition(data.get('counters', {}))
        return body, 200, {'Content-Type': 'text/plain; version=0.0.4; charset=utf-8'}
    return jsonify(queue_status())


@main.route('/admin/failed-jobs/requeue/<job_id>', methods=['POST'])
@admin_required
def failed_job_requeue(job_id):
    from ..jobs import requeue_failed_job
    ok = requeue_failed_job(job_id)
    write_audit("FAILED_JOB_REQUEUE", target=f"job:{job_id}", detail="ok" if ok else "no-broker")
    flash(f"Job {job_id} requeued for another attempt." if ok
          else f"Could not requeue job {job_id} (no Redis or unknown job).",
          "success" if ok else "error")
    return redirect(url_for('main.failed_jobs_dashboard'))


@main.route('/admin/failed-jobs/delete/<job_id>', methods=['POST'])
@admin_required
def failed_job_delete(job_id):
    from ..jobs import delete_failed_job
    ok = delete_failed_job(job_id)
    write_audit("FAILED_JOB_DELETE", target=f"job:{job_id}", detail="ok" if ok else "no-broker")
    flash(f"Job {job_id} removed from the dead-letter queue." if ok
          else f"Could not delete job {job_id}.", "success" if ok else "error")
    return redirect(url_for('main.failed_jobs_dashboard'))


@main.route('/admin/failed-jobs/clear', methods=['POST'])
@admin_required
def failed_jobs_clear():
    from ..jobs import clear_failed_jobs
    n = clear_failed_jobs()
    write_audit("FAILED_JOBS_CLEAR", detail=f"{n} job(s) purged")
    flash(f"Cleared {n} failed job(s) from the dead-letter queue.", "success")
    return redirect(url_for('main.failed_jobs_dashboard'))


@main.route('/admin/bwg-approve/<int:id>')
@admin_required
def bwg_approve(id):
    decl = BWGDeclaration.query.get_or_404(id)
    decl.pickup_status = 'Approved'
    db.session.commit()
    write_audit("BWG_APPROVE", target=decl.entity_name, detail=f"{decl.recyclable_kg}kg bulk pickup approved.")
    flash(f"Bulk pickup approved for {decl.entity_name}.", "success")
    return redirect(url_for('main.admin'))


@main.route('/admin/payt/<int:inv_id>/waive', methods=['POST'])
@admin_required
def payt_waive(inv_id):
    """Admin waives an invoice — the debt is forgiven, no money moves.

    Only meaningful for invoices the citizen has NOT paid: waiving a paid
    invoice without reversing the Razorpay charge would silently double-count
    the payment, so those must go through the refund path instead. Idempotent:
    a second waive on an already-waived/refunded invoice is a no-op with a
    flash, so double-clicks can't corrupt billing state. Audited."""
    invoice = PAYTInvoice.query.get_or_404(inv_id)
    if invoice.status in ('Waived', 'Refunded'):
        flash(f"Invoice #{inv_id} is already {invoice.status}.", 'info')
        return redirect(url_for('main.admin'))
    if invoice.status == 'Paid':
        flash("Paid invoices must be refunded (money was collected), not waived.", 'error')
        return redirect(url_for('main.admin'))
    invoice.status = 'Waived'
    invoice.refund_reason = fit_length(request.form.get('reason', '').strip() or 'Waived by admin', 200)
    db.session.commit()
    write_audit("PAYT_WAIVE", target=f'Invoice #{inv_id}',
                detail=f"Waived Rs {invoice.amount_rs:.2f}: {invoice.refund_reason}")
    flash(f"Invoice #{inv_id} waived (Rs {invoice.amount_rs:.2f} forgiven).", "success")
    return redirect(url_for('main.admin'))


@main.route('/admin/payt/<int:inv_id>/refund', methods=['POST'])
@admin_required
def payt_refund(inv_id):
    """Admin refunds a PAID invoice via the Razorpay Refunds API.

    Only Razorpay-paid invoices can be auto-refunded (transaction_ref holds the
    Razorpay payment id; UPI payments have no Razorpay payment to reverse —
    those need a manual bank transfer, so we refuse with a clear message).
    Idempotent: the invoice's refund_id column is the guard — once a refund id
    is recorded, a second attempt is a no-op (Razorpay also rejects duplicate
    full refunds). The API call is best-effort and never raises; on failure
    the invoice stays Paid so the admin can retry. Audited on both paths."""
    invoice = PAYTInvoice.query.get_or_404(inv_id)
    if invoice.refund_id:
        flash(f"Invoice #{inv_id} was already refunded ({invoice.refund_id}).", 'info')
        return redirect(url_for('main.admin'))
    if invoice.status != 'Paid':
        flash(f"Invoice #{inv_id} is not paid — cannot refund a {invoice.status} invoice.", 'error')
        return redirect(url_for('main.admin'))
    if invoice.payment_method != 'Razorpay' or not (invoice.transaction_ref or '').strip():
        flash(f"Invoice #{inv_id} was paid via {invoice.payment_method or 'UPI'} — "
              "no Razorpay payment to reverse. Process the refund manually.", 'error')
        return redirect(url_for('main.admin'))
    reason = fit_length(request.form.get('reason', '').strip() or 'Refunded by admin', 200)
    refund_id = _create_razorpay_refund(invoice, reason)
    if not refund_id:
        write_audit("PAYT_REFUND_FAILED", target=f'Invoice #{inv_id}',
                    detail=f"Refund API rejected or unconfigured: {reason}")
        flash(f"Refund for invoice #{inv_id} failed (Razorpay API). Invoice stays Paid — try again.", 'error')
        return redirect(url_for('main.admin'))
    invoice.status = 'Refunded'
    invoice.refund_id = refund_id
    invoice.refunded_at = utcnow()
    invoice.refund_reason = reason
    db.session.commit()
    write_audit("PAYT_REFUND", target=f'Invoice #{inv_id}',
                detail=f"Refund {refund_id} for Rs {invoice.amount_rs:.2f}: {reason}")
    flash(f"Invoice #{inv_id} refunded (refund {refund_id}).", "success")
    return redirect(url_for('main.admin'))


@main.route('/admin/offline-deliveries')
@admin_required
def offline_deliveries():
    """Offline-first usage + delivery health: complaints/photos that arrived
    via the PWA IndexedDB queue (tagged X-Offline-Replay by offline.js).

    Gives the municipality one place to see offline-first adoption: how many
    reports were queued while out of signal and delivered on reconnect, how
    many carried photo evidence, and how many replay attempts delivery took
    (attempts > 0 means the queue retried before succeeding)."""
    from datetime import timedelta as _td
    from sqlalchemy import func
    cutoff7 = utcnow() - _td(days=7)
    cutoff30 = utcnow() - _td(days=30)
    all_rows = OfflineDelivery.query.order_by(OfflineDelivery.delivered_at.desc()).limit(500).all()
    total = OfflineDelivery.query.count()
    week = OfflineDelivery.query.filter(OfflineDelivery.delivered_at >= cutoff7).count()
    month = OfflineDelivery.query.filter(OfflineDelivery.delivered_at >= cutoff30).count()
    photos = OfflineDelivery.query.filter_by(has_photo=True).count()
    retried = OfflineDelivery.query.filter(OfflineDelivery.attempts > 0).count()
    # Exact ward distribution via SQL GROUP BY (no full-table scan in Python,
    # unlike the recent-500 window used for the row table).
    ward_counts = db.session.query(
        OfflineDelivery.ward, func.count(OfflineDelivery.id)
    ).filter(OfflineDelivery.ward.isnot(None)).group_by(OfflineDelivery.ward).all()
    top_wards = sorted(ward_counts, key=lambda kv: kv[1], reverse=True)[:5]
    return render_template('offline_deliveries.html', deliveries=all_rows, total=total,
                           week=week, month=month, photos=photos, retried=retried,
                           top_wards=top_wards)


@main.route('/admin/audit')
@superadmin_required
def audit_trail():
    # Super-admin only — the audit ledger is a privileged security view.
    # (Regular admins cannot reach this; the decorator enforces it.)
    logs = AuditLog.query.order_by(AuditLog.timestamp.desc()).limit(500).all()
    return render_template('audit_log.html', logs=logs, is_superadmin=True)


# Super-admin console: the sanctioned way to create admin accounts now that
# public self-registration is citizen/worker only. @superadmin_required gates it.
@main.route('/admin/super', methods=['GET', 'POST'])
@superadmin_required
def super_admin():
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'create_admin':
            username = request.form.get('username', '').strip()
            password = request.form.get('password', '')
            raw_phone = request.form.get('phone', '').strip()
            if not username or not password or not raw_phone:
                flash('Username, password and phone are all required.', 'error')
            elif len(username) > 100:
                flash('Username must be 100 characters or fewer.', 'error')
            elif len(password) < 6:
                flash('Admin password must be at least 6 characters.', 'error')
            elif User.query.filter_by(username=username).first():
                flash('Username already exists.', 'error')
            else:
                phone = validate_indian_phone(raw_phone)
                if not phone:
                    flash('Enter a valid Indian mobile number for the admin.', 'error')
                else:
                    new_admin = User(username=username,
                                     password_hash=generate_password_hash(password),
                                     role='admin', phone=phone, is_approved=True)
                    db.session.add(new_admin)
                    db.session.commit()
                    write_audit("SUPER_CREATE_ADMIN", target=username,
                                detail="Super-admin created new admin account.")
                    flash(f"Admin account '{username}' created.", 'success')
        elif action == 'toggle_super':
            uid = request.form.get('user_id', type=int)
            target = User.query.get(uid) if uid else None
            if target and target.id != session['user_id']:
                target.is_superadmin = not target.is_superadmin
                db.session.commit()
                write_audit("SUPER_TOGGLE", target=target.username,
                            detail=f"is_superadmin set to {target.is_superadmin}")
                flash(f"Updated super-admin flag for {target.username}.", 'success')
        elif action == 'approve_admin':
            uid = request.form.get('user_id', type=int)
            target = User.query.get(uid) if uid else None
            if target and target.role == 'admin' and not target.is_approved:
                target.is_approved = True
                db.session.commit()
                write_audit("SUPER_APPROVE_ADMIN", target=target.username,
                            detail="Super-admin approved pending admin account.")
                flash(f"Admin account '{target.username}' approved.", 'success')
        elif action == 'deny_admin':
            uid = request.form.get('user_id', type=int)
            target = User.query.get(uid) if uid else None
            if target and target.role == 'admin' and not target.is_approved:
                db.session.delete(target)
                db.session.commit()
                write_audit("SUPER_DENY_ADMIN", target=target.username,
                            detail="Super-admin denied pending admin account.")
                flash(f"Admin account '{target.username}' denied and removed.", 'success')
        return redirect(url_for('main.super_admin'))
    users = User.query.order_by(User.id).all()
    return render_template('super_admin.html', users=users, session_user_id=session.get('user_id'))


@main.route('/admin/firmware')
@admin_required
def firmware_hub():
    releases = FirmwareRelease.query.order_by(FirmwareRelease.created_at.desc()).all()
    bins = SmartBin.query.all()
    return render_template('firmware.html', releases=releases, bins=bins)


@main.route('/admin/firmware/upload', methods=['POST'])
@admin_required
def firmware_upload():
    version = fit_length(request.form.get('version', '').strip(), 20)
    description = request.form.get('description', '').strip()
    target_bins = fit_length(request.form.get('target_bins', 'ALL').strip(), 200)
    file = request.files.get('firmware_file')
    if not version or not file or file.filename == '':
        flash("Version number and firmware file are required.", "error")
        return redirect(url_for('main.firmware_hub'))
    # ── Artifact validation: only real firmware images, bounded size ──
    ALLOWED_FW_EXT = ('.bin', '.hex', '.uf2', '.elf')
    MAX_FW_BYTES = 8 * 1024 * 1024  # 8 MB
    fname = file.filename or ''
    ext = os.path.splitext(fname)[1].lower()
    if ext not in ALLOWED_FW_EXT:
        flash(f"Invalid firmware file type '{ext or 'none'}'. Allowed: .bin, .hex, .uf2, .elf.", "error")
        return redirect(url_for('main.firmware_hub'))
    raw = file.read(MAX_FW_BYTES + 1)
    if len(raw) > MAX_FW_BYTES:
        flash("Firmware file exceeds the 8 MB limit.", "error")
        return redirect(url_for('main.firmware_hub'))
    file.seek(0)  # rewind so file.save() below can write the full content
    sha256 = hashlib.sha256(raw).hexdigest()
    filename = fit_length(secure_filename(f"firmware_v{version}_{fname}"), 200)
    upload_path = os.path.join(current_app.config.get('FIRMWARE_FOLDER',
                               current_app.config['UPLOAD_FOLDER']), filename)
    file.save(upload_path)
    release = FirmwareRelease(version=version, filename=filename, description=description,
                              target_bins=target_bins, push_status='Pending',
                              uploaded_by=session['user_id'], sha256=sha256)
    db.session.add(release); db.session.commit()
    write_audit("FIRMWARE_UPLOAD", target=f"v{version}",
                detail=f"File: {filename}, SHA-256: {sha256[:12]}…, Targets: {target_bins}")
    flash(f"Firmware v{version} uploaded successfully. Ready to push.", "success")
    return redirect(url_for('main.firmware_hub'))


@main.route('/api/ota/<hw_id>', methods=['POST'])
@admin_required
def ota_push(hw_id):
    release_id = request.form.get('release_id')
    release = FirmwareRelease.query.get(release_id)
    if not release:
        return jsonify({"success": False, "message": "Firmware release not found."}), 404
    target_bin = SmartBin.query.filter_by(hardware_id=hw_id).first()
    if not target_bin:
        return jsonify({"success": False, "message": f"Bin {hw_id} not found."}), 404
    # Simulate OTA push (in production this would call MQTT or HTTP to the ESP32)
    success = random.random() > 0.1  # 90% success rate simulation
    if success:
        release.push_status = 'Pushed'
        release.pushed_at = utcnow()
        db.session.commit()
        write_audit("OTA_PUSH", target=hw_id, detail=f"Firmware v{release.version} pushed to {hw_id}.")
        return jsonify({"success": True, "message": f"OTA push to {hw_id} successful. Bin rebooting...",
                        "version": release.version})
    else:
        release.push_status = 'Failed'
        db.session.commit()
        return jsonify({"success": False, "message": f"OTA push to {hw_id} failed. Bin may be offline."}), 503


@main.route('/admin/toggle-compactor/<string:hw_id>', methods=['POST'])
@admin_required
def toggle_compactor(hw_id):
    smart_bin = SmartBin.query.filter_by(hardware_id=hw_id).first_or_404()
    smart_bin.precompaction_enabled = not smart_bin.precompaction_enabled
    db.session.commit()
    write_audit("TOGGLE_COMPACTOR", target=hw_id,
                detail=f"Solar pre-compaction {'ENABLED' if smart_bin.precompaction_enabled else 'DISABLED'}.")
    return jsonify({"success": True, "hardware_id": hw_id,
                    "precompaction_enabled": smart_bin.precompaction_enabled})


@main.route('/api/bins')
@login_required
def api_bins():
    bins = SmartBin.query.all()
    return jsonify([{
        "id": b.id,
        "hardware_id": b.hardware_id,
        "latitude": b.latitude,
        "longitude": b.longitude,
        "level": b.level,
        "battery": b.battery_level,
        "temperature": b.temperature,
        "methane": b.methane,
        "status": b.status,
        "ward": b.ward,
        "precompaction_enabled": b.precompaction_enabled,
    } for b in bins])
