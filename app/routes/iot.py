import hashlib
import hmac
import os
import time
from datetime import timedelta as _TD

from flask import (current_app, jsonify, request)

from ..models import (BinTelemetryLog, Device, DispatchAssignment, IncidentLog, SensorHealth, SmartBin, utcnow)

from ..ml_model import predict_overflow_eta_hours

from .. import csrf, db, limiter, socketio

from ..auth import admin_required

from . import (FORECAST_ALERT_HOURS, _recompute_bin_status, activate_compactor,
               evaluate_emergency_metrics, fit_length, haversine_m, logger, main,
               write_audit)

import app.routes as _routes  # call-time: honors test monkeypatches


def _hash_device_key(api_key: str) -> str:
    """One-way hash for device API keys at rest."""
    return hashlib.sha256(api_key.encode('utf-8')).hexdigest()


def _is_deployed():
    """True when running on a production platform (Render or Fly.io).

    The OLD check only enforced the HMAC secret on Render — a Fly.io
    deployment without IOT_TELEMETRY_SECRET silently accepted unsigned
    telemetry from the public internet. Both platforms are production.
    """
    return bool(os.environ.get('RENDER') or os.environ.get('FLY_APP_NAME'))


def _authenticate_device(hardware_id: str):
    """Validate per-device API key. Returns Device or None."""
    device = Device.query.filter_by(hardware_id=hardware_id, is_active=True).first()
    if not device:
        return None
    provided = request.headers.get('X-Device-Key', '')
    if not provided:
        return None
    expected = hmac.new(
        device.api_key_hash.encode(), hardware_id.encode(), hashlib.sha256
    ).hexdigest()
    if hmac.compare_digest(expected, provided):
        return device
    return None


@main.route('/api/devices/register', methods=['POST'])
@admin_required
def register_device():
    """Provision a new IoT device. Returns the plaintext API key once."""
    data = request.get_json(silent=True) or {}
    hardware_id = data.get('hardware_id', '').strip()
    name = data.get('name', '').strip()
    if not hardware_id:
        return jsonify({"success": False, "message": "hardware_id required."}), 400
    existing = Device.query.filter_by(hardware_id=hardware_id).first()
    if existing:
        return jsonify({"success": False, "message": "Device already registered."}), 409
    api_key = os.urandom(16).hex()
    device = Device(
        hardware_id=hardware_id,
        api_key_hash=_hash_device_key(api_key),
        name=fit_length(name, 100) if 'fit_length' in globals() else name[:100],
    )
    db.session.add(device)
    db.session.commit()
    write_audit("DEVICE_REGISTER", target=hardware_id, detail=f"Provisioned IoT device: {name or hardware_id}")
    return jsonify({"success": True, "hardware_id": hardware_id, "api_key": api_key})


@main.route('/api/bin-telemetry', methods=['POST'])
@limiter.limit("100/minute")
@csrf.exempt  # HMAC-signed IoT device POSTs; see IOT_TELEMETRY_SECRET
def bin_telemetry():
    """ESP32/Arduino smart-bin ingestion endpoint. Receives live sensor
    readings, updates the bin record in the database, clears stale sensor
    faults, and runs the emergency evaluation pipeline (fire / methane
    hazard detection + webhook dispatch) via evaluate_emergency_metrics()."""
    # ── IoT auth: require a valid HMAC-SHA256 signature when a telemetry
    # secret is configured (production). Skipped in dev when no secret set. ──
    secret = current_app.config.get('IOT_TELEMETRY_SECRET')
    # On ANY production platform (Render OR Fly.io) the HMAC secret is
    # mandatory — never accept unsigned telemetry from a public endpoint.
    if not secret and _is_deployed():
        logger.error("iot_telemetry_secret_missing", ip=request.remote_addr)
        return jsonify({"success": False,
                        "message": "IOT_TELEMETRY_SECRET not configured."}), 503
    if secret:
        raw = request.get_data(cache=True)
        provided = request.headers.get('X-Signature', '')
        expected = hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(provided, expected):
            return jsonify({"success": False, "message": "Invalid signature."}), 403

    data = request.get_json(silent=True) or request.form
    hw_id = data.get('hardware_id') or data.get('id')
    if not hw_id:
        return jsonify({"success": False, "message": "hardware_id is required."}), 400

    # Per-device API key auth (preferred): validate X-Device-Key against the
    # Device table. Falls back to the global IOT_TELEMETRY_SECRET HMAC only
    # when no Device row exists yet (backward compat during migration).
    device = _authenticate_device(hw_id)
    if device:
        device.last_seen = utcnow()
    else:
        secret = current_app.config.get('IOT_TELEMETRY_SECRET')
        if not secret and _is_deployed():
            logger.error("iot_telemetry_secret_missing", ip=request.remote_addr)
            return jsonify({"success": False,
                            "message": "IOT_TELEMETRY_SECRET not configured."}), 503
        if secret:
            raw = request.get_data(cache=True)
            provided = request.headers.get('X-Signature', '')
            expected = hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
            if not hmac.compare_digest(provided, expected):
                return jsonify({"success": False, "message": "Invalid signature."}), 403

    smart_bin = SmartBin.query.filter_by(hardware_id=hw_id).first()
    if not smart_bin:
        return jsonify({"success": False, "message": f"Bin {hw_id} not found."}), 404

    # Snapshot pre-ping state so we only audit meaningful *changes* — a per-ping
    # audit row for every sensor heartbeat would balloon the AuditLog table to
    # the largest table in the DB within weeks.
    prev_state = (smart_bin.level, smart_bin.status, smart_bin.sensor_fault,
                  round(smart_bin.temperature, 1), round(smart_bin.methane, 1))

    try:
        if data.get('level') is not None:
            smart_bin.level = int(float(data.get('level')))
        if data.get('temperature') is not None:
            smart_bin.temperature = float(data.get('temperature'))
        if data.get('methane') is not None:
            smart_bin.methane = float(data.get('methane'))
        if data.get('battery_level') is not None:
            smart_bin.battery_level = int(float(data.get('battery_level')))
    except (ValueError, TypeError):
        return jsonify({"success": False, "message": "Invalid numeric telemetry value."}), 400

    # ── Replay protection: optional device clock (unix seconds). When a frame
    # carries `ts`, reject anything older than 5 minutes — an intercepted HMAC
    # frame replayed later must not re-trigger state changes. Devices without
    # a clock omit it (HMAC + per-device key still gate entry). ──
    ts = data.get('ts')
    if ts is not None:
        try:
            if abs(int(time.time()) - int(ts)) > 300:
                return jsonify({"success": False, "message": "Stale frame."}), 403
        except (ValueError, TypeError):
            return jsonify({"success": False, "message": "Invalid ts."}), 400

    # ── GPS-drift guard: a stationary bin can't jump. Coordinates more than
    # 2 km from the last known position are rejected (audited, so a stolen or
    # relocated bin surfaces) instead of silently mis-rendering on the map. ──
    if (data.get('latitude') is not None and data.get('longitude') is not None
            and smart_bin.latitude is not None and smart_bin.longitude is not None):
        try:
            new_lat, new_lon = float(data['latitude']), float(data['longitude'])
            if haversine_m(smart_bin.latitude, smart_bin.longitude,
                           new_lat, new_lon) > 2000:
                write_audit("BIN_GPS_ANOMALY", target=hw_id,
                            detail=f"Rejected {new_lat},{new_lon} (>2 km from last known position)")
            else:
                smart_bin.latitude, smart_bin.longitude = new_lat, new_lon
        except (ValueError, TypeError):
            pass  # malformed coords: keep the last known position

    # ── Lid-state ingest: an open lid is a service event, not an emergency. ──
    if data.get('lid_open') is not None:
        new_lid = bool(data.get('lid_open'))
        if new_lid != bool(smart_bin.lid_open):
            write_audit("BIN_LID_STATE", target=hw_id,
                        detail="Lid open" if new_lid else "Lid closed")
        smart_bin.lid_open = new_lid

    smart_bin.status = _recompute_bin_status(smart_bin.level)
    smart_bin.last_updated = utcnow()

    # ── Live telemetry history: append a per-ping level snapshot so the
    # fill-rate estimator can learn this bin's ACTUAL fill velocity over time
    # (least-squares slope over real (time, level) points) instead of inferring
    # it from a single anchor timestamp. Retention: prune this bin's rows older
    # than 14 days on the same commit — history needs to be deep enough to
    # learn velocity, but not so deep it balloons into the largest table. ──
    _prune_cutoff = utcnow() - _TD(days=14)
    BinTelemetryLog.query.filter(
        BinTelemetryLog.bin_id == smart_bin.id,
        BinTelemetryLog.timestamp < _prune_cutoff).delete(synchronize_session=False)
    db.session.add(BinTelemetryLog(
        bin_id=smart_bin.id,
        level=smart_bin.level,
        temperature=smart_bin.temperature,
        methane=smart_bin.methane,
        battery_level=smart_bin.battery_level,
        status=smart_bin.status,
        timestamp=utcnow()
    ))

    # ── ML overflow forecast: hours-to-overflow from fill-rate model. ──
    # Persist into the (previously unused) overflow_eta_hours column so the
    # route optimizer + forecast API read a stored value instead of recomputing.
    # NOTE: computed BEFORE the pre-compaction step below — if the solar
    # compactor fires this ping, the stored eta reflects pre-compaction fill
    # until the next ping recomputes it (the 0.25h anchor guard in
    # _estimate_fill_rate_hour_pct prevents spurious alerts right after).
    now = utcnow()
    prev_eta = smart_bin.overflow_eta_hours
    # ── ETA recompute throttle ──
    # The fill-rate estimator queries telemetry history + runs the sklearn
    # regressor on EVERY ping (28,800/day at 5-min cadence). Only recompute
    # when the level changed by >5% OR 15 minutes have elapsed since the last
    # computation — the forecast is an advisory, not a per-ping necessity.
    _last_eta = smart_bin.last_eta_computed_at
    _level_delta = abs((smart_bin.level or 0) - (prev_state[0] or 0))
    _eta_stale = (_last_eta is None or
                  (now - _last_eta).total_seconds() >= 900)  # 15 min
    if _eta_stale or _level_delta > 5:
        smart_bin.overflow_eta_hours = predict_overflow_eta_hours(smart_bin, now)
        smart_bin.last_eta_computed_at = now
    # else: keep the stored forecast (no recompute this ping)

    # ── Stagnant Rot & Decomposition Timer (Max 48h above 10% fill) ──
    if smart_bin.level > 10:
        if smart_bin.decomposition_started_at is None:
            smart_bin.decomposition_started_at = now
    else:
        # Bin was cleared/emptied below threshold → reset the timer
        smart_bin.decomposition_started_at = None

    # ── Solar-Powered Mechanical Pre-Compaction (triggers at 70% fill) ──
    if smart_bin.precompaction_enabled and smart_bin.level >= 70:
        if (smart_bin.last_compacted_at is None or
                (now - smart_bin.last_compacted_at).total_seconds() > 3600):
            activate_compactor(smart_bin)

    # ── Stuck-sensor classifier (environmental noise). A constant >=95% level
    # across the last 5 pings is far more likely a blocked ultrasonic sensor
    # (cardboard, rain, debris) than genuine overflow — flag it as a sensor
    # fault (which suppresses the auto-dispatch below) instead of dispatching
    # a truck. The NEXT ping with a changed reading self-heals via the clear
    # branch. ──
    _history = (BinTelemetryLog.query
                .filter_by(bin_id=smart_bin.id)
                .order_by(BinTelemetryLog.timestamp.desc())
                .limit(5).all())
    _was_faulted = smart_bin.sensor_fault
    _stuck = (len(_history) >= 5 and (smart_bin.level or 0) >= 95
              and len({h.level for h in _history}) == 1)
    if _stuck:
        smart_bin.sensor_fault = True
        _sh = SensorHealth.query.filter_by(bin_id=smart_bin.id).first()
        if _sh:
            _sh.fault_flag = True
            _sh.fault_reason = "Stuck sensor: constant level across 5 pings (possible blockage)"
        if not _was_faulted:
            write_audit("SENSOR_SUSPICIOUS", target=hw_id,
                        detail=f"Constant {smart_bin.level}% across 5 pings — possible blockage, dispatch suppressed")
    elif smart_bin.sensor_fault:
        # A live ping with a changed reading clears the previous fault so the
        # bin returns to healthy state.
        smart_bin.sensor_fault = False
        sh = SensorHealth.query.filter_by(bin_id=smart_bin.id).first()
        if sh:
            sh.fault_flag = False
            sh.maintenance_scheduled = False
        # Also resolve any open Sensor Fault incidents
        open_faults = IncidentLog.query.filter_by(
            bin_id=smart_bin.id, incident_type="Sensor Fault", status="Active").all()
        for inc in open_faults:
            inc.status = "Resolved"

    # Single commit for the whole request: telemetry fields, sensor-fault
    # resolution, decomposition timer and any queued IncidentLog rows are all
    # persisted together (previously each helper self-committed, multiplying
    # DB round-trips under IoT load).
    # Proactive-dispatch alert: fire exactly ONCE when the forecast crosses
    # the urgent threshold (not on every ping while it stays urgent). Detect
    # the crossing BEFORE the commit so the auto-queued Pending dispatch
    # assignment persists in the same single transaction as the telemetry.
    eta = smart_bin.overflow_eta_hours
    crossed_alert = (not smart_bin.sensor_fault and eta is not None
                     and eta <= FORECAST_ALERT_HOURS
                     and (prev_eta is None or prev_eta > FORECAST_ALERT_HOURS))
    if crossed_alert:
        existing_dispatch = DispatchAssignment.query.filter_by(bin_id=smart_bin.id).filter(
            DispatchAssignment.status.in_(['Pending', 'Assigned'])).first()
        if existing_dispatch is None:
            db.session.add(DispatchAssignment(bin_id=smart_bin.id, eta_hours=eta, status='Pending'))

    hazard = evaluate_emergency_metrics(smart_bin)
    db.session.commit()

    # Webhooks fire AFTER the commit so receivers see the persisted incident.
    if hazard:
        itype, severity, details = hazard
        _routes._dispatch_webhooks("SMART_BIN_EMERGENCY", {
            "bin_id": smart_bin.hardware_id,
            "incident_type": itype, "severity": severity,
            "description": details,
        })

    if crossed_alert:
        logger.info("overflow_forecast_alert", bin=smart_bin.hardware_id, eta_hours=eta)
        _routes._dispatch_webhooks("SMART_BIN_OVERFLOW_ALERT", {
            "bin_id": smart_bin.hardware_id,
            "ward": smart_bin.ward,
            "level": smart_bin.level,
            "overflow_eta_hours": eta,
        })
        # Real-time nudge: every open worker/admin dashboard hears the new
        # urgent bin and re-renders its proactive-dispatch queue.
        socketio.emit('dispatch_nudge', {
            'hardware_id': smart_bin.hardware_id,
            'bin_id': smart_bin.id,
            'ward': smart_bin.ward,
            'level': smart_bin.level,
            'overflow_eta_hours': eta,
        })

    # Push the fresh bin state to the live admin control room.
    socketio.emit('bin_update', {
        'hardware_id': hw_id,
        'level': smart_bin.level,
        'status': smart_bin.status,
        'latitude': smart_bin.latitude,
        'longitude': smart_bin.longitude,
        'battery_level': smart_bin.battery_level,
        'temperature': smart_bin.temperature,
        'methane': smart_bin.methane,
        'sensor_fault': smart_bin.sensor_fault,
        'overflow_eta_hours': smart_bin.overflow_eta_hours,
    })

    cur_state = (smart_bin.level, smart_bin.status, smart_bin.sensor_fault,
                 round(smart_bin.temperature, 1), round(smart_bin.methane, 1))
    if cur_state != prev_state:
        write_audit("BIN_TELEMETRY", target=hw_id,
                    detail=f"Level {smart_bin.level}% | {smart_bin.temperature}°C | CH4 {smart_bin.methane}ppm")
    return jsonify({
        "success": True,
        "hardware_id": hw_id,
        "level": smart_bin.level,
        "status": smart_bin.status,
        "temperature": smart_bin.temperature,
        "methane": smart_bin.methane,
        "battery_level": smart_bin.battery_level,
        "overflow_eta_hours": smart_bin.overflow_eta_hours
    })
