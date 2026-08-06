from datetime import datetime, timezone, timedelta
from collections import defaultdict

from flask import (abort, jsonify, render_template, request)

from ..models import (AuditLog, SmartBin, WasteDeclaration, utcnow)

from .. import db

from ..auth import admin_required

from . import (WARD_COORDINATES, _compute_analytics, _csrd_payload, _performance_pdf_bytes, _state_portal_indicators, main)


@main.route('/analytics')
@admin_required
def analytics():
    d = _compute_analytics()
    # circular_economy / carbon_data are still passed for the static text displays
    return render_template('analytics.html',
                           circular_economy=d['circular'],
                           carbon_data=d['carbon'])


@main.route('/api/analytics-data')
@admin_required
def analytics_data():
    return jsonify(_compute_analytics())


@main.route('/analytics/state-portal-export')
@admin_required
def state_portal_export():
    indicators = _state_portal_indicators()
    fmt = request.args.get('format', 'json')
    if fmt == 'csv':
        import csv, io
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["indicator", "value"])
        for k, v in indicators.items():
            w.writerow([k, v])
        buf.seek(0)
        return buf.getvalue(), 200, {
            'Content-Type': 'text/csv',
            'Content-Disposition': 'attachment; filename=state_portal_compliance.csv'
        }
    return jsonify({
        "report_title": "State Portal SWM Compliance Return",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "indicators": indicators
    })


@main.route('/api/analytics/sensor-faults')
@admin_required
def sensor_fault_analytics():
    """Stuck-sensor incident analytics over a rolling window.

    The immutable AuditLog is the source of truth: the fault lifecycle is
    reconstructed per bin by pairing detection events (SENSOR_SUSPICIOUS from
    the stuck-sensor classifier, SENSOR_FAULT_FLAGGED from the stale-sensor
    sweep) with resolution events (SENSOR_SELF_HEALED / BIN_FAULT_CLEARED /
    MAINTENANCE_COMPLETED). All aggregation happens in Python over one
    filtered query, keeping the SQL portable (SQLite + Postgres).

    Pairing semantics: each detection opens a pending slot that the NEXT
    resolution closes — consecutive detections for one outage (e.g. stale +
    stuck both firing) collapse, so time-to-clear measures from the FIRST
    detection of the outage, while the fault-rate counts every detection
    event. Resolutions whose detection predates the window still count toward
    the self-heal/manual split (recent resolution activity) but contribute no
    time-to-clear. At equal timestamps detections sort before resolutions.
    """
    try:
        days = int(request.args.get('days', 90))
    except (TypeError, ValueError):
        days = 90
    days = max(7, min(days, 365))
    cutoff = utcnow() - timedelta(days=days)

    DETECTIONS = ('SENSOR_SUSPICIOUS', 'SENSOR_FAULT_FLAGGED')
    SELF_HEAL = 'SENSOR_SELF_HEALED'
    MANUAL = ('BIN_FAULT_CLEARED', 'MAINTENANCE_COMPLETED')

    rows = (db.session.query(AuditLog.action, AuditLog.target, AuditLog.timestamp)
            .filter(AuditLog.timestamp >= cutoff,
                    AuditLog.action.in_(list(DETECTIONS) + [SELF_HEAL] + list(MANUAL)))
            .all())

    # One pass builds both the bin->ward map and the per-ward bin census.
    ward_of = {}
    bins_per_ward = defaultdict(int)
    for b in SmartBin.query.all():
        ward_of[b.hardware_id] = b.ward
        bins_per_ward[b.ward] += 1

    by_bin = defaultdict(list)
    for action, target, ts in rows:
        if target:
            by_bin[target].append((ts, action))

    ward_stats = defaultdict(lambda: {'detections': 0, 'self_heal': 0,
                                      'manual': 0, 'ttc_hours': []})
    bin_detections = {}          # hardware_id -> count (repeat offenders)
    weekly = defaultdict(lambda: [0, 0])  # 'YYYY-Www' -> [detections, resolutions]
    detections_total = self_heal_total = manual_total = 0
    ttc_hours = []

    for hw, evs in by_bin.items():
        # Stable pairing: detections sort before resolutions at equal
        # timestamps so a same-second detection+resolution never mispairs.
        evs.sort(key=lambda e: (e[0], 0 if e[1] in DETECTIONS else 1))
        pending_detection = None
        det_count = 0
        for ts, action in evs:
            week = f"{ts.isocalendar()[0]}-W{ts.isocalendar()[1]:02d}" if ts else None
            if action in DETECTIONS:
                detections_total += 1
                det_count += 1
                if pending_detection is None:
                    pending_detection = ts
                if week:
                    weekly[week][0] += 1
                ward_stats[ward_of.get(hw)]['detections'] += 1
            else:
                if action == SELF_HEAL:
                    self_heal_total += 1
                    ward_stats[ward_of.get(hw)]['self_heal'] += 1
                else:
                    manual_total += 1
                    ward_stats[ward_of.get(hw)]['manual'] += 1
                if week:
                    weekly[week][1] += 1
                if pending_detection is not None:
                    delta_h = (ts - pending_detection).total_seconds() / 3600.0
                    if delta_h >= 0:
                        ttc_hours.append(delta_h)
                        ward_stats[ward_of.get(hw)]['ttc_hours'].append(delta_h)
                    pending_detection = None
        if det_count:
            bin_detections[hw] = det_count

    ward_rows = []
    for w, s in sorted(ward_stats.items(), key=lambda kv: -kv[1]['detections']):
        bins = bins_per_ward.get(w, 0)
        ttc = sum(s['ttc_hours']) / len(s['ttc_hours']) if s['ttc_hours'] else None
        resolved = s['self_heal'] + s['manual']
        ward_rows.append({
            'ward': w,
            'bins': bins,
            'detections': s['detections'],
            'fault_rate': round(s['detections'] / bins, 2) if bins else None,
            'avg_ttc_hours': round(ttc, 1) if ttc is not None else None,
            'self_heal': s['self_heal'],
            'manual': s['manual'],
            'self_heal_pct': round(s['self_heal'] / resolved * 100, 1) if resolved else 0.0,
        })

    avg_ttc = sum(ttc_hours) / len(ttc_hours) if ttc_hours else None
    resolved_total = self_heal_total + manual_total

    # Contiguous weekly axis from the window start to now — sparse buckets are
    # zero-filled so the trend chart shows quiet weeks as zeros, not gaps. The
    # 7-day date loop can stop just short of the current (partial) week, so
    # the current week's key is appended explicitly — otherwise events in that
    # final week would be bucketed but never rendered.
    weeks = []
    seen = set()
    cur = cutoff
    while cur <= utcnow():
        iso = cur.isocalendar()
        key = f"{iso[0]}-W{iso[1]:02d}"
        if key not in seen:
            seen.add(key)
            weeks.append(key)
        cur += timedelta(days=7)
    now_iso = utcnow().isocalendar()
    now_key = f"{now_iso[0]}-W{now_iso[1]:02d}"
    if now_key not in seen:
        weeks.append(now_key)

    return jsonify({
        'days': days,
        'kpis': {
            'detections': detections_total,
            'resolved': resolved_total,
            'self_heal': self_heal_total,
            'manual': manual_total,
            'self_heal_pct': round(self_heal_total / resolved_total * 100, 1) if resolved_total else 0.0,
            'avg_ttc_hours': round(avg_ttc, 1) if avg_ttc is not None else None,
            'currently_faulted': SmartBin.query.filter_by(sensor_fault=True).count(),
        },
        'series': {
            'labels': weeks,
            'detections': [weekly[w][0] for w in weeks],
            'resolutions': [weekly[w][1] for w in weeks],
        },
        'wards': ward_rows,
        'top_bins': [{'hardware_id': hw, 'detections': n, 'ward': ward_of.get(hw)}
                     for hw, n in sorted(bin_detections.items(),
                                         key=lambda kv: -kv[1])[:5]],
    })


@main.route('/api/trend/segregation')
@admin_required
def trend_segregation():
    """Monthly segregation % per ward — aggregated in SQL.

    Previously pulled EVERY WasteDeclaration row into Python (a full-table
    scan that would OOM the 1 GB Fly VM once declarations grow). Now the
    database does the bucketing: group by (month, ward) with per-group sums,
    using the month expression that matches each dialect (strftime on SQLite,
    to_char on Postgres — same parity discipline as the dunning ilike guard).
    The new ix_waste_declaration_ward_timestamp index serves the filter+group.
    """
    from sqlalchemy import func
    from collections import defaultdict

    if db.engine.dialect.name == 'postgresql':
        month_expr = func.to_char(WasteDeclaration.timestamp, 'YYYY-MM')
    else:
        month_expr = func.strftime('%Y-%m', WasteDeclaration.timestamp)

    rows = (db.session.query(
        month_expr.label('month'),
        WasteDeclaration.ward,
        func.sum(WasteDeclaration.wet_kg + WasteDeclaration.dry_kg).label('seg'),
        func.sum(WasteDeclaration.wet_kg + WasteDeclaration.dry_kg +
                 WasteDeclaration.sanitary_kg + WasteDeclaration.hazardous_kg).label('tot'),
    ).filter(WasteDeclaration.timestamp.isnot(None))
     .group_by(month_expr, WasteDeclaration.ward)
     .all())

    # [segregated, total] per (month, ward)
    buckets = defaultdict(lambda: defaultdict(lambda: [0.0, 0.0]))
    for month, ward, seg, tot in rows:
        buckets[month][ward][0] += seg or 0.0
        buckets[month][ward][1] += tot or 0.0
    months = sorted(buckets.keys())
    series = {}
    for wd in WARD_COORDINATES:
        series[wd] = [
            round((buckets[m][wd][0] / buckets[m][wd][1]) * 100, 1)
            if buckets[m].get(wd, [0, 0])[1] else 0.0
            for m in months
        ]
    return jsonify({"months": months, "series": series})


@main.route('/analytics/csrd-export')
@admin_required
def csrd_export():
    return jsonify(_csrd_payload())


@main.route('/analytics/performance-pdf')
@admin_required
def performance_pdf():
    content, filename = _performance_pdf_bytes()
    return content, 200, {
        'Content-Type': 'application/pdf',
        'Content-Disposition': f'attachment; filename={filename}'
    }


@main.route('/analytics/export/request')
@admin_required
def export_request():
    kind = request.args.get('kind', 'state-portal')
    fmt = request.args.get('format', 'json')
    if kind not in ('state-portal', 'csrd', 'performance-pdf'):
        abort(400)
    import uuid
    from ..jobs import enqueue, generate_export_job
    job_id = uuid.uuid4().hex
    enqueue(generate_export_job, job_id, kind, fmt)
    return jsonify({"job_id": job_id, "kind": kind, "status": "queued"})


@main.route('/analytics/export/status/<job_id>')
@admin_required
def export_status(job_id):
    from ..jobs import fetch_artifact
    return jsonify({"job_id": job_id, "status": "ready" if fetch_artifact(job_id) else "processing"})


@main.route('/analytics/export/result/<job_id>')
@admin_required
def export_result(job_id):
    from ..jobs import fetch_artifact
    artifact = fetch_artifact(job_id)
    if artifact is None:
        return jsonify({"error": "Artifact not ready yet."}), 202
    content, content_type, filename = artifact
    return content, 200, {
        'Content-Type': content_type,
        'Content-Disposition': f'attachment; filename={filename}'
    }
