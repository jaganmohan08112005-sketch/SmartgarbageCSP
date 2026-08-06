import random

from flask import (flash, jsonify, redirect, render_template, request, session, url_for)

from sqlalchemy.exc import IntegrityError

from ..models import (Complaint, DispatchAssignment, IncidentLog, MaintenanceWorkOrder, OffloadLog, SensorHealth, SmartBin, User, WorkerProfile, utcnow)

from ..auth import worker_required, roles_required

from .. import db, socketio

from ..ml_model import predict_overflow_eta_hours

from . import (DUMP_YARDS, FORECAST_URGENT_HOURS, SECTOR_POLYGONS, _notify_admins,
               _notify_status_change, _publish_admin_alerts, fit_length, haversine_m,
               main, point_in_polygon, record_complaint_event,
               save_compressed_photo, write_audit)

# Close-the-loop: a bin may ONLY be cleared when the worker uploads a live
# After-photo AND their device GPS is within this radius of the bin. A truck
# driver can no longer tap "Cleared" from down the street — the server rejects
# any clear whose photo/GPS can't be verified. 200m tolerates real-world GPS
# jitter (~10-30m) while still proving on-site presence.
CLEAR_RADIUS_M = 200


@main.route('/api/worker/gps', methods=['POST'])
@worker_required
def worker_gps():
    """Worker app GPS heartbeat. Persists the vehicle position and records a
    geo-fence violation (with audit) when the sector polygon is exited — this is
    the only place geofence state is written (the fleet GET is read-only)."""
    profile = WorkerProfile.query.filter_by(user_id=session['user_id']).first()
    if not profile:
        return jsonify({"success": False, "message": "Worker profile not found."}), 404
    try:
        lat = float(request.form.get('lat', ''))
        lon = float(request.form.get('lon', ''))
    except (TypeError, ValueError):
        return jsonify({"success": False, "message": "lat/lon are required numbers."}), 400
    if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
        return jsonify({"success": False, "message": "Coordinates out of range."}), 400

    profile.current_lat = lat
    profile.current_lon = lon
    sector_poly = SECTOR_POLYGONS.get(profile.vehicle_id, [])
    in_bounds = point_in_polygon(lat, lon, sector_poly) if sector_poly else True
    if not in_bounds and not profile.geofence_violation:
        profile.geofence_violation = True
        write_audit("GEOFENCE_VIOLATION", target=profile.vehicle_id,
                    detail=f"Vehicle {profile.vehicle_id} exited assigned sector at ({lat:.5f},{lon:.5f}).")
    elif in_bounds and profile.geofence_violation:
        profile.geofence_violation = False
        write_audit("GEOFENCE_CLEARED", target=profile.vehicle_id,
                    detail=f"Vehicle {profile.vehicle_id} returned to sector.")
    db.session.commit()
    return jsonify({"success": True, "lat": lat, "lon": lon,
                    "in_bounds": in_bounds,
                    "geofence_violation": profile.geofence_violation})


@main.route('/worker')
@worker_required
def worker():
    profile = WorkerProfile.query.filter_by(user_id=session['user_id']).first()
    work_bins = SmartBin.query.filter(SmartBin.level >= 50).all()
    offload_logs = OffloadLog.query.filter_by(worker_id=profile.id).order_by(
        OffloadLog.timestamp.desc()).limit(10).all() if profile else []
    task_bins_data = [{'hardware_id': b.hardware_id, 'latitude': b.latitude, 'longitude': b.longitude,
                       'level': b.level, 'status': b.status, 'ward': b.ward} for b in work_bins]
    dispatch_queue = _dispatch_queue_rows(profile)
    return render_template('worker.html', profile=profile, work_bins=work_bins,
                           task_bins_data=task_bins_data,
                           dispatch_queue=dispatch_queue,
                           offload_logs=offload_logs, dump_yards=DUMP_YARDS)


def _bin_from_request():
    """Resolve the target SmartBin from JSON or form data.

    request.get_json returns a plain dict (no type= kwarg on dict.get), while
    request.form is a MultiDict (which accepts it) — so coerce manually to
    keep both client payload styles working."""
    data = request.get_json(silent=True) or request.form
    raw = data.get('bin_id')
    try:
        bin_id = int(raw)
    except (TypeError, ValueError):
        return None
    return SmartBin.query.get(bin_id)


def _dispatch_queue_rows(profile=None):
    """Bins with a live overflow forecast, ranked by hours-to-overflow.

    Mirrors the admin /api/overflow-forecast ranking (smallest ETA first, then
    highest fill) but adds each bin's dispatch-assignment state so workers see
    what's claimable, what's already taken, and what's theirs. Admin control
    room renders the same list live.

    Performance: a SINGLE SQL LEFT JOIN replaces the old 3N-query pattern
    (iterate every bin + 2 DispatchAssignment queries per bin). With 500 bins
    that was 1,500 queries per dashboard render; now it's one.
    """
    # One query: every bin with a live forecast, LEFT JOINed to its most
    # recent Assigned dispatch AND a correlated EXISTS for Pending. The
    # EXISTS is a correlated subquery evaluated per-row by the DB engine —
    # not a separate Python query per bin.
    _pending_exists = db.session.query(DispatchAssignment.id).filter(
        DispatchAssignment.bin_id == SmartBin.id,
        DispatchAssignment.status == 'Pending'
    ).exists()
    _assigned = db.session.query(DispatchAssignment).filter(
        DispatchAssignment.bin_id == SmartBin.id,
        DispatchAssignment.status == 'Assigned'
    ).order_by(DispatchAssignment.id.desc()).limit(1).subquery()
    # Pull every bin that can be forecast (any fill at all, or an already
    # stored ETA). Bins whose forecast hasn't been computed yet (seeded before
    # the forecast pipeline, or a fresh checkout with no telemetry pings) get
    # one computed on the fly below — the same lazy path /api/overflow-forecast
    # uses — so the proactive queue is never silently empty on real data.
    q = (db.session.query(SmartBin, _assigned.c.worker_id, _pending_exists)
         .outerjoin(_assigned, _assigned.c.bin_id == SmartBin.id)
         .filter(db.or_(SmartBin.overflow_eta_hours.isnot(None),
                        SmartBin.level > 0))
         .all())
    rows = []
    for b, assigned_worker_id, has_pending in q:
        eta = b.overflow_eta_hours
        if eta is None:
            # No stored forecast — compute one on the fly (best-effort, never
            # raises): level <= 0 or a sensor-faulted bin yields None and is
            # skipped, mirroring predict_overflow_eta_hours' contract.
            try:
                eta = predict_overflow_eta_hours(b)
            except Exception:
                eta = None
        if eta is None:
            continue
        my_assign = assigned_worker_id is not None and profile and assigned_worker_id == profile.id
        rows.append({
            'hardware_id': b.hardware_id,
            'bin_id': b.id,
            'ward': b.ward,
            'level': b.level,
            'status': b.status,
            'overflow_eta_hours': eta,
            'urgent': eta <= FORECAST_URGENT_HOURS,
            'dispatch_status': 'assigned' if assigned_worker_id is not None else ('pending' if has_pending else 'available'),
            'assigned_worker_id': assigned_worker_id,
            'mine': bool(my_assign),
        })
    # The SQL ORDER BY can't rank bins whose ETA was just computed in Python —
    # sort here (smallest hours-to-overflow first, then highest fill) so the
    # ranking is identical for stored and lazy forecasts, on SQLite AND Postgres.
    rows.sort(key=lambda r: (r['overflow_eta_hours'], -r['level']))
    return rows


@main.route('/api/dispatch/queue')
@roles_required('worker', 'admin')
def dispatch_queue():
    """Proactive-dispatch queue for workers AND the admin control room.

    Ranked by ML overflow forecast (hours-to-overflow ascending). Each row
    carries its dispatch state so the worker UI can show Accept/Complete and
    the admin view can watch assignment progress live."""
    profile = WorkerProfile.query.filter_by(user_id=session['user_id']).first()
    return jsonify({
        'bins': _dispatch_queue_rows(profile),
        'urgent_threshold_hours': FORECAST_URGENT_HOURS,
    })


@main.route('/api/dispatch/accept', methods=['POST'])
@worker_required
def dispatch_accept():
    """Accept a dispatch assignment for a bin. Idempotent: re-accepting the
    same bin by the same worker is a no-op success; another worker's active
    assignment is rejected with 409 so two trucks don't chase one bin."""
    profile = WorkerProfile.query.filter_by(user_id=session['user_id']).first()
    if not profile:
        return jsonify({"success": False, "message": "Worker profile not found."}), 404
    smart_bin = _bin_from_request()
    if not smart_bin:
        return jsonify({"success": False, "message": "Bin not found."}), 404

    existing = (DispatchAssignment.query
                .filter_by(bin_id=smart_bin.id, status='Assigned')
                .order_by(DispatchAssignment.id.desc()).first())
    if existing:
        if existing.worker_id != profile.id:
            return jsonify({"success": False, "message": "already_assigned"}), 409
        # Already mine — idempotent re-accept.
        return jsonify({"success": True, "assignment_id": existing.id})

    # Optimistic-lock claim of the auto-queued Pending row. There is at most
    # one Pending row per bin (the telemetry auto-queue refuses to mint a
    # second one), so target its id with a status guard: `WHERE id=? AND
    # status='Pending'` is a single atomic UPDATE on both SQLite and Postgres
    # — of two workers racing to claim it, exactly one sees rowcount 1; the
    # loser sees 0 and falls through to the fresh-insert path, where the
    # partial unique index on (bin_id) WHERE status='Assigned' turns the
    # second insert into an IntegrityError -> 409. No two trucks can ever
    # hold the same bin.
    pending = (DispatchAssignment.query
               .filter_by(bin_id=smart_bin.id, status='Pending')
               .order_by(DispatchAssignment.id.asc()).first())
    claimed = False
    if pending:
        claimed = bool((db.session.query(DispatchAssignment)
                        .filter(DispatchAssignment.id == pending.id,
                                DispatchAssignment.status == 'Pending')
                        .update({'status': 'Assigned', 'worker_id': profile.id,
                                 'assigned_at': utcnow(),
                                 'eta_hours': smart_bin.overflow_eta_hours},
                                synchronize_session=False)))
    if claimed:
        assignment = (DispatchAssignment.query
                      .filter_by(bin_id=smart_bin.id, status='Assigned').first())
        db.session.commit()
    else:
        # No Pending row, or we lost the race for it — either way the partial
        # unique index makes the fresh insert atomic: a concurrent winner
        # surfaces as IntegrityError -> 409.
        assignment = DispatchAssignment(bin_id=smart_bin.id, status='Assigned',
                                        worker_id=profile.id,
                                        assigned_at=utcnow(),
                                        eta_hours=smart_bin.overflow_eta_hours)
        db.session.add(assignment)
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            return jsonify({"success": False, "message": "already_assigned"}), 409
    write_audit("DISPATCH_ACCEPT", target=smart_bin.hardware_id,
                detail=f"Worker {session.get('username')} accepted proactive dispatch.")
    socketio.emit('dispatch_update', {
        'hardware_id': smart_bin.hardware_id,
        'bin_id': smart_bin.id,
        'status': 'Assigned',
        'worker_id': profile.id,
    })
    return jsonify({"success": True, "assignment_id": assignment.id})


@main.route('/api/dispatch/complete', methods=['POST'])
@worker_required
def dispatch_complete():
    """Mark a worker's active dispatch assignment completed (bin cleared)."""
    profile = WorkerProfile.query.filter_by(user_id=session['user_id']).first()
    if not profile:
        return jsonify({"success": False, "message": "Worker profile not found."}), 404
    smart_bin = _bin_from_request()
    if not smart_bin:
        return jsonify({"success": False, "message": "Bin not found."}), 404

    assignment = (DispatchAssignment.query
                  .filter_by(bin_id=smart_bin.id, worker_id=profile.id, status='Assigned')
                  .order_by(DispatchAssignment.id.desc()).first())
    if not assignment:
        return jsonify({"success": False, "message": "No active assignment for this bin."}), 404
    assignment.status = 'Completed'
    assignment.completed_at = utcnow()
    db.session.commit()
    write_audit("DISPATCH_COMPLETE", target=smart_bin.hardware_id,
                detail=f"Worker {session.get('username')} completed proactive dispatch.")
    socketio.emit('dispatch_update', {
        'hardware_id': smart_bin.hardware_id,
        'bin_id': smart_bin.id,
        'status': 'Completed',
        'worker_id': profile.id,
    })
    return jsonify({"success": True, "assignment_id": assignment.id})


# ── Maintenance work orders (sensor-health follow-up) ──
@main.route('/api/maintenance/my')
@worker_required
def my_maintenance():
    """The logged-in worker's maintenance work orders.

    Active (Scheduled / In Progress) orders first sorted by due date — overdue
    flagged read-side so the card can highlight them — then the 5 most recent
    completed orders for the shift history.
    """
    profile = WorkerProfile.query.filter_by(user_id=session['user_id']).first()
    if not profile:
        return jsonify({'orders': []})
    active = (MaintenanceWorkOrder.query
              .filter(MaintenanceWorkOrder.worker_id == profile.id,
                      MaintenanceWorkOrder.status.in_(['Scheduled', 'In Progress']))
              .order_by(MaintenanceWorkOrder.due_date.is_(None),
                        MaintenanceWorkOrder.due_date.asc())
              .all())
    completed = (MaintenanceWorkOrder.query
                 .filter_by(worker_id=profile.id, status='Completed')
                 .order_by(MaintenanceWorkOrder.completed_at.desc()).limit(5).all())
    now = utcnow()
    return jsonify({'orders': [{
        'id': o.id,
        'bin_id': o.bin_id,
        'hardware_id': o.bin.hardware_id if o.bin else None,
        'ward': o.bin.ward if o.bin else None,
        'status': o.status,
        'due_date': o.due_date.isoformat() if o.due_date else None,
        'overdue': bool(o.due_date and o.status != 'Completed' and o.due_date < now),
        'notes': o.notes,
    } for o in active + completed]});


@main.route('/api/maintenance/<int:order_id>/start', methods=['POST'])
@worker_required
def maintenance_start(order_id):
    """Worker begins a Scheduled maintenance order (Scheduled -> In Progress)."""
    profile = WorkerProfile.query.filter_by(user_id=session['user_id']).first()
    if not profile:
        return jsonify({'success': False, 'message': 'Worker profile not found.'}), 404
    order = MaintenanceWorkOrder.query.get(order_id)
    if not order or order.worker_id != profile.id:
        return jsonify({'success': False, 'message': 'Work order not found.'}), 404
    if order.status != 'Scheduled':
        return jsonify({'success': False, 'message': f'Order is already {order.status}.'}), 400
    order.status = 'In Progress'
    db.session.commit()
    write_audit("MAINTENANCE_STARTED",
                target=order.bin.hardware_id if order.bin else f'WO #{order.id}',
                detail=f"Worker {session.get('username')} started maintenance work order #{order.id}.")
    socketio.emit('maintenance_update', {'order_id': order.id,
                                         'hardware_id': order.bin.hardware_id if order.bin else None,
                                         'status': order.status})
    return jsonify({'success': True})


@main.route('/api/maintenance/<int:order_id>/complete', methods=['POST'])
@roles_required('worker', 'admin')
def maintenance_complete(order_id):
    """Mark a maintenance work order completed — by the assigned worker or any
    admin (control-room fallback).

    Completes the order (Scheduled/In Progress -> Completed), drops the bin's
    maintenance-scheduled flag, clears any lingering sensor fault, resolves
    open Sensor Fault incidents, and audits the action with the actor's
    identity. Workers may only complete their own orders; admins any.
    """
    order = MaintenanceWorkOrder.query.get(order_id)
    if not order:
        return jsonify({'success': False, 'message': 'Work order not found.'}), 404
    profile = WorkerProfile.query.filter_by(user_id=session['user_id']).first()
    if session.get('role') == 'worker' and (not profile or order.worker_id != profile.id):
        return jsonify({'success': False, 'message': 'Work order not found.'}), 404
    if order.status == 'Completed':
        return jsonify({'success': False, 'message': 'Work order already completed.'}), 400

    order.status = 'Completed'
    order.completed_at = utcnow()
    order.completed_by = session.get('user_id')
    b = order.bin
    if b:
        # The maintenance visit restored the bin to service.
        b.sensor_fault = False
        sh = SensorHealth.query.filter_by(bin_id=b.id).first()
        if sh:
            sh.fault_flag = False
            sh.maintenance_scheduled = False
        for inc in IncidentLog.query.filter_by(
                bin_id=b.id, incident_type='Sensor Fault', status='Active').all():
            inc.status = 'Resolved'
    staged = _notify_admins(
        f"✅ Maintenance work order #{order.id} completed on "
        f"{order.bin.hardware_id if order.bin else '?'} by {session.get('username', 'worker')} — "
        f"bin restored to service.",
        link="/admin#sensor-fault-section")
    db.session.commit()
    # Live alert after the commit — a toast must never announce a completion
    # that rolled back.
    _publish_admin_alerts(staged)
    write_audit("MAINTENANCE_COMPLETED",
                target=order.bin.hardware_id if order.bin else f'WO #{order.id}',
                detail=(f"{session.get('role')} {session.get('username')} completed "
                        f"maintenance work order #{order.id}."))
    socketio.emit('maintenance_update', {'order_id': order.id,
                                         'hardware_id': order.bin.hardware_id if order.bin else None,
                                         'status': order.status})
    return jsonify({'success': True, 'bin_restored': bool(b)})


@main.route('/resolve-bin/<string:hw_id>', methods=['POST'])
@worker_required
def resolve_bin(hw_id):
    """Clear a bin — CLOSE-THE-LOOP: requires a live After-photo + on-site GPS.

    The old flow let a worker tap "Clear Bins" with no evidence, so a driver
    could mark an overflowing bin cleaned from down the street. Now the POST
    must carry:
      * after_photo  — a real-time photo of the cleared bin (multipart file)
      * lat / lon    — the worker's device GPS captured at the same moment
    The server verifies the worker's GPS is within CLEAR_RADIUS_M of the bin
    (Haversine) before the clear is accepted; a missing photo or out-of-range
    GPS is rejected with 400, so the ticket only closes with proof.
    """
    smart_bin = SmartBin.query.filter_by(hardware_id=hw_id).first_or_404()

    # ── 1. After-photo is mandatory ──
    photo_file = request.files.get('after_photo')
    if not photo_file or photo_file.filename == '':
        return jsonify({"success": False,
                        "message": "After-photo required. Upload a live photo of the cleared bin to close this ticket."}), 400

    # ── 2. Live GPS is mandatory ──
    try:
        w_lat = float(request.form.get('lat', ''))
        w_lon = float(request.form.get('lon', ''))
    except (TypeError, ValueError):
        w_lat = w_lon = None
    if w_lat is None or w_lon is None or not (-90 <= w_lat <= 90) or not (-180 <= w_lon <= 180):
        return jsonify({"success": False,
                        "message": "Your GPS must be within range of the bin. Enable location and try again."}), 400

    # ── 3. Worker GPS must match the bin's location (Haversine) ──
    dist_m = haversine_m(w_lat, w_lon, smart_bin.latitude, smart_bin.longitude)
    if dist_m > CLEAR_RADIUS_M:
        return jsonify({"success": False,
                        "message": f"Your GPS ({dist_m:.0f}m from bin) is out of range. Move to the bin and retry."}), 400

    # ── 4. Persist the evidence, then clear ──
    after_path = save_compressed_photo(photo_file, 'after')
    smart_bin.after_photo = after_path
    smart_bin.level = 0; smart_bin.status = "Safe"
    smart_bin.battery_level = min(100, smart_bin.battery_level + 10)
    smart_bin.temperature = 24.0; smart_bin.methane = 20.0
    smart_bin.sensor_fault = False
    smart_bin.last_updated = utcnow()
    unresolved = Complaint.query.filter_by(ward=smart_bin.ward, status="Pending").all()
    for comp in unresolved:
        comp.status = "Resolved"
        comp.resolved_at = utcnow()
        reporter = User.query.get(comp.user_id)
        if reporter: reporter.green_points += 10
        # Timeline event joins the single commit below (commit=False)
        record_complaint_event(comp, 'Resolved',
                               f'Bin {hw_id} cleared by sanitation worker — complaint resolved.',
                               commit=False)
        _notify_status_change(comp)
    active_incidents = IncidentLog.query.filter_by(bin_id=smart_bin.id, status="Active").all()
    for inc in active_incidents: inc.status = "Resolved"
    # Also clear sensor fault if present
    sh = SensorHealth.query.filter_by(bin_id=smart_bin.id).first()
    if sh: sh.fault_flag = False; sh.maintenance_scheduled = False
    # Auto-close any open maintenance work orders for this bin — clearing it
    # with verified evidence IS the maintenance visit.
    open_orders = (MaintenanceWorkOrder.query
                   .filter(MaintenanceWorkOrder.bin_id == smart_bin.id,
                           MaintenanceWorkOrder.status != 'Completed')
                   .all())
    staged = []
    for wo in open_orders:
        wo.status = 'Completed'
        wo.completed_at = utcnow()
        wo.completed_by = session.get('user_id')
        # Manual-resolution signal for the sensor-fault analytics (atomic with
        # the resolve_bin commit below).
        write_audit("MAINTENANCE_COMPLETED", target=hw_id,
                    detail=f"Worker {session.get('username')} completed maintenance work order #{wo.id} (auto-closed by bin clearance).",
                    commit=False)
        # Live alert to the control room (staged; pushed after the commit).
        staged.extend(_notify_admins(
            f"✅ Maintenance work order #{wo.id} auto-completed — bin {hw_id} "
            f"cleared with verified evidence.",
            link="/admin#sensor-fault-section"))
    if open_orders:
        socketio.emit('maintenance_update', {'status': 'Completed', 'bin_id': smart_bin.id})
    db.session.commit()
    _publish_admin_alerts(staged)
    write_audit("RESOLVE_BIN", target=hw_id,
                detail=(f"Bin {hw_id} cleared with verified After-photo ({after_path}), "
                        f"worker GPS {dist_m:.0f}m from bin."
                        + (f" {len(open_orders)} maintenance order(s) auto-completed." if open_orders else "")))
    return jsonify({"success": True, "message": f"Bin {hw_id} cleared and reset with verified evidence!"})


@main.route('/worker/offload', methods=['POST'])
@worker_required
def worker_offload():
    profile = WorkerProfile.query.filter_by(user_id=session['user_id']).first()
    if not profile:
        flash("Worker profile not found.", "error")
        return redirect(url_for('main.worker'))
    dump_yard_id = fit_length(request.form.get('dump_yard_id', ''), 50)
    weight_kg = float(request.form.get('weight_kg', 0))
    # AI CV Impurity Check (simulated)
    impurity_detected = False
    impurity_detail = None
    # Simulate: if methane of any assigned critical bin > 300, flag impurity
    critical_bins = SmartBin.query.filter(SmartBin.level >= 80, SmartBin.methane > 300).all()
    if critical_bins and random.random() < 0.3:
        impurity_detected = True
        impurity_detail = f"CV Scanner flagged contaminated organic waste mixed with plastic in bin {critical_bins[0].hardware_id}. Sorting violation logged."
        incident = IncidentLog(bin_id=critical_bins[0].id, incident_type="Impurity Detected",
                               severity="Warning", status="Active", description=impurity_detail)
        db.session.add(incident)
    offload = OffloadLog(worker_id=profile.id, dump_yard_id=dump_yard_id, weight_kg=weight_kg,
                         vehicle_id=profile.vehicle_id, impurity_flagged=impurity_detected,
                         impurity_detail=impurity_detail, verified=True)
    db.session.add(offload)
    # Generate PAYT-style invoice context
    profile.status = 'Idle'
    db.session.commit()
    write_audit("OFFLOAD_LOG", target=dump_yard_id,
                detail=f"Worker {session.get('username')} dumped {weight_kg}kg at {dump_yard_id}.")
    if impurity_detected:
        flash(f"⚠️ Impurity flagged! {impurity_detail} Offload recorded with violation note.", "warning")
    else:
        flash(f"✅ Offload verified: {weight_kg}kg at {dump_yard_id}. Digital manifest logged!", "success")
    return redirect(url_for('main.worker'))


@main.route('/worker/report-issue', methods=['POST'])
@worker_required
def worker_report_issue():
    bin_hw_id = fit_length(request.form.get('bin_id'), 50)
    issue_type = fit_length(request.form.get('issue_type'), 50)
    details = request.form.get('details')
    target_bin = SmartBin.query.filter_by(hardware_id=bin_hw_id).first()
    incident = IncidentLog(bin_id=target_bin.id if target_bin else None,
                           incident_type=issue_type, severity="Warning", status="Active",
                           description=f"Worker reported [{issue_type}] — {details} (Bin: {bin_hw_id})")
    db.session.add(incident)
    db.session.commit()
    write_audit("WORKER_REPORT_ISSUE", target=bin_hw_id, detail=f"{issue_type}: {details}")
    flash("Issue flagged to administrative dashboard.", "success")
    return redirect(url_for('main.worker'))
