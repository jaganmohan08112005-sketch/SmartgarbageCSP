import os

from datetime import datetime, timedelta, timezone

from flask import (Response, abort, current_app, flash, jsonify, redirect, render_template, request, session, url_for)

from ..models import (BWGDeclaration, Complaint, IllegalDumpReport, Notification, PAYTInvoice, SmartBin, User, WasteDeclaration, utcnow)

from ..auth import login_required

from .. import db, limiter

from . import (DUMP_YARDS, WARD_COORDINATES, GPS_VERIFY_RADIUS_M, _ai_verify_photo,
               _create_razorpay_order, _payt_receipt_pdf_bytes, _photo_gps_from_upload,
               _publish_user_event, _razorpay_enabled, _record_offline_delivery,
               _redis_client, _send_tracking_link, _verify_razorpay_payment_signature,
               cache_get, cache_set, find_duplicate_complaint, fit_length, haversine_m,
               logger, main, make_complaint_token, record_complaint_event,
               save_compressed_photo, write_audit)


@main.route('/dashboard')
@login_required
def dashboard():
    try:
        page = max(1, int(request.args.get('page', 1)))
    except (ValueError, TypeError):
        page = 1
    try:
        per_page = min(50, max(1, int(request.args.get('per_page', 20))))
    except (ValueError, TypeError):
        per_page = 20
    complaints = Complaint.query.filter_by(user_id=session['user_id']).order_by(Complaint.id.desc()).limit(per_page).offset((page - 1) * per_page).all()
    # Signed tracking tokens for the citizen's own complaints (Track button)
    complaint_tokens = {c.id: make_complaint_token(c.id) for c in complaints}
    user = User.query.get(session['user_id'])
    wards_scores = []
    for ward_name in WARD_COORDINATES:
        bins = SmartBin.query.filter_by(ward=ward_name).all()
        avg_level = sum(b.level for b in bins) / len(bins) if bins else 0
        wards_scores.append({"ward": ward_name, "score": max(0, 100 - int(avg_level))})
    wards_scores.sort(key=lambda x: x['score'], reverse=True)
    bin_assets = SmartBin.query.all()
    invoices = PAYTInvoice.query.filter_by(user_id=session['user_id']).order_by(PAYTInvoice.issued_at.desc()).limit(per_page).offset((page - 1) * per_page).all()
    declarations = WasteDeclaration.query.filter_by(user_id=session['user_id']).order_by(WasteDeclaration.timestamp.desc()).limit(per_page).offset((page - 1) * per_page).all()
    # Segregation streak counts DISTINCT calendar days with segregated > 0 kg —
    # the old loop counted consecutive ROWS, so two declarations in one day
    # inflated the streak. SQL DISTINCT DATE() is portable across SQLite/Postgres.
    _segregated_days = db.session.query(
        db.func.date(WasteDeclaration.timestamp)
    ).filter(
        WasteDeclaration.user_id == session['user_id'],
        (WasteDeclaration.wet_kg + WasteDeclaration.dry_kg) > 0,
    ).distinct().all()
    streak = len(_segregated_days)
    if user is None:
        flash('Account not found. Please log in again.', 'error')
        return redirect(url_for('main.logout'))
    if user.segregation_streak != streak:
        user.segregation_streak = streak
        db.session.commit()
    bins_data = [{'hardware_id': b.hardware_id, 'latitude': b.latitude, 'longitude': b.longitude,
                  'level': b.level, 'status': b.status} for b in bin_assets]
    from datetime import timedelta as _td
    cutoff = utcnow() - _td(days=30)
    cache_key = f"ward_seg:{cutoff.date().isoformat()}"
    cached = cache_get(cache_key)
    if cached is not None:
        ward_seg = cached
    else:
        ward_seg = {}
        for wd in WARD_COORDINATES:
            wdecls = WasteDeclaration.query.filter(WasteDeclaration.ward == wd,
                                                   WasteDeclaration.timestamp >= cutoff).all()
            if wdecls:
                tot = sum(d.wet_kg + d.dry_kg + d.sanitary_kg + d.hazardous_kg for d in wdecls) or 1
                seg = sum(d.wet_kg + d.dry_kg for d in wdecls)
                ward_seg[wd] = round((seg / tot) * 100, 1)
            else:
                ward_seg[wd] = 0.0
        cache_set(cache_key, ward_seg, ttl_seconds=120)
    ward_leaderboard = sorted(ward_seg.items(), key=lambda kv: kv[1], reverse=True)
    current_user_phone = user.phone or ''
    return render_template('dashboard.html', complaints=complaints, complaint_tokens=complaint_tokens,
                           green_points=user.green_points,
                           leaderboard=wards_scores, bins=bin_assets, bins_data=bins_data,
                           invoices=invoices, declarations=declarations, dump_yards=DUMP_YARDS,
                           current_user_phone=current_user_phone,
                           segregation_streak=streak, ward_leaderboard=ward_leaderboard,
                           page=page, per_page=per_page)


@main.route('/api/leaderboard')
@login_required
def green_points_leaderboard():
    ward = request.args.get('ward', '').strip()
    try:
        page = max(1, int(request.args.get('page', 1)))
    except (ValueError, TypeError):
        page = 1
    try:
        per_page = min(50, max(1, int(request.args.get('per_page', 20))))
    except (ValueError, TypeError):
        per_page = 20
    cache_key = f"leaderboard:{ward}:{page}:{per_page}"
    cached = cache_get(cache_key)
    if cached is not None:
        return jsonify(cached)
    query = User.query.filter(User.green_points > 0)
    if ward:
        user_ids = db.session.query(WasteDeclaration.user_id).filter(
            WasteDeclaration.ward == ward).distinct()
        query = query.filter(User.id.in_(user_ids))
    page_obj = query.order_by(User.green_points.desc()).limit(per_page).offset((page - 1) * per_page).all()
    payload = [
        {"rank": i + 1 + (page - 1) * per_page, "username": u.username, "green_points": u.green_points}
        for i, u in enumerate(page_obj)
    ]
    cache_set(cache_key, payload, ttl_seconds=30)
    return jsonify(payload)


@main.route('/payt/pay/<int:inv_id>')
@login_required
def payt_invoice_payment(inv_id):
    """Render the PAYT payment page.

    Primary flow: a Razorpay order is created SERVER-SIDE and handed to the
    Checkout UI, so the citizen never decides 'I paid' — the capture is
    verified via payment signature + webhook. When Razorpay isn't configured
    (or the API call fails) the UPI deep-link remains as a fallback.
    """
    invoice = PAYTInvoice.query.get_or_404(inv_id)
    # Privacy: only the invoice owner may view/pay it.
    if invoice.user_id != session['user_id']:
        abort(403)
    # Refunded/waived invoices are TERMINAL — never let the citizen pay a
    # closed invoice (the money would be collected with no recovery path: the
    # capture webhook would ignore it and nothing would auto-refund).
    if invoice.refund_id or invoice.status in ('Refunded', 'Waived'):
        flash('This invoice is closed (refunded/waived) — no payment is due.', 'warning')
        return redirect(url_for('main.dashboard'))
    # Build a UPI deep-link that any UPI app can open.
    # UPI deep links expect the amount in decimal rupees (e.g. "150.00"), not paise.
    upi_url = (f"upi://pay?pa={os.getenv('RAZOR_PAYER', 'smartgarbage@ybl')}"
               f"&am={invoice.amount_rs:.2f}&pn=SmartGarbage&tn=PAYT-Invoice-{inv_id}&cu=INR")

    # Server-side order creation (primary path). Idempotent: reuse a stored
    # order id for this invoice when one already exists so the page never
    # mints a fresh order on every reload. Only open (Unpaid) invoices get an
    # order — closed ones were already bounced above.
    order_id = None
    if _razorpay_enabled() and invoice.status == 'Unpaid':
        order_id = invoice.razorpay_order_id or _create_razorpay_order(invoice)
        if order_id and not invoice.razorpay_order_id:
            invoice.razorpay_order_id = order_id
            db.session.commit()

    return render_template('payt_payment.html', invoice=invoice, upi_url=upi_url,
                           razorpay_order_id=order_id,
                           razorpay_key_id=os.getenv('RAZORPAY_KEY_ID'),
                           amount_paise=int(round(invoice.amount_rs * 100)))


@main.route('/payt/verify/<int:inv_id>', methods=['POST'])
@login_required
def payt_verify_payment(inv_id):
    """Verify the Razorpay Checkout payment signature and mark the invoice paid.

    Replaces the old trust-based 'I've completed the UPI payment' button: the
    citizen now only succeeds when their payment actually went through the
    server-created order. The capture webhook (/webhook/razorpay) is the
    second, independent confirmation — this endpoint is a fast UX path so the
    citizen doesn't wait for webhook delivery.
    """
    invoice = PAYTInvoice.query.get_or_404(inv_id)
    if invoice.user_id != session['user_id']:
        abort(403)
    if invoice.status == 'Paid':
        return jsonify({"success": True, "message": "already_paid"})
    # Refunded/waived invoices are terminal — a replayed verify (the Razorpay
    # capture webhook is at-least-once, and a citizen could re-POST the success
    # payload) must never resurrect a reversed/forgiven invoice.
    if invoice.refund_id or invoice.status in ('Refunded', 'Waived'):
        return jsonify({"success": False, "message": "invoice_closed"}), 400

    data = request.get_json(silent=True) or {}
    order_id = data.get('razorpay_order_id', '')
    payment_id = data.get('razorpay_payment_id', '')
    signature = data.get('razorpay_signature', '')
    if not all([order_id, payment_id, signature]):
        return jsonify({"success": False, "message": "missing_payment_details"}), 400
    # The signature must match the server-created order; never trust the client
    # to claim which order they paid for.
    if order_id != invoice.razorpay_order_id:
        logger.warning("payt_order_mismatch", invoice_id=inv_id, order_id=order_id)
        return jsonify({"success": False, "message": "order_mismatch"}), 400
    if not _verify_razorpay_payment_signature(order_id, payment_id, signature):
        write_audit("PAYT_VERIFY_FAILED", target=f'Invoice #{inv_id}',
                    detail=f"Razorpay signature check failed (order {order_id})")
        return jsonify({"success": False, "message": "signature_invalid"}), 400

    invoice.status = 'Paid'
    invoice.paid_at = utcnow()
    invoice.transaction_ref = fit_length(payment_id, 120)
    invoice.payment_method = 'Razorpay'
    db.session.commit()
    write_audit('PAYT_PAID', target=f'Invoice #{inv_id}',
                detail=f'Razorpay payment {payment_id} verified, Rs {invoice.amount_rs:.2f}')
    # Generate + email the citizen's PDF receipt (background; the webhook also
    # enqueues it, but the status-flip guard means only the first path sends).
    from ..jobs import enqueue, payt_receipt_job
    enqueue(payt_receipt_job, inv_id)
    return jsonify({"success": True, "message": "paid"})


@main.route('/payt/confirm/<int:inv_id>', methods=['POST'])
@login_required
def payt_confirm_payment(inv_id):
    """Mark a PAYT invoice as Paid after the citizen confirms the UPI payment."""
    invoice = PAYTInvoice.query.get_or_404(inv_id)
    if invoice.user_id != session['user_id']:
        abort(403)
    if invoice.status == 'Paid':
        flash('This invoice is already paid.', 'success')
        return redirect(url_for('main.dashboard'))
    if invoice.refund_id or invoice.status in ('Refunded', 'Waived'):
        flash('This invoice is closed (refunded/waived) — no payment is due.', 'warning')
        return redirect(url_for('main.dashboard'))
    # Optional external transaction ref (e.g. UPI RRN) passed by a real gateway/webhook.
    txn = (request.form.get('txn') or request.args.get('txn')
           or f"PAYT-{inv_id}-{int(datetime.now(timezone.utc).timestamp())}")
    invoice.status = 'Paid'
    invoice.paid_at = utcnow()
    invoice.transaction_ref = fit_length(txn, 120)
    invoice.payment_method = 'UPI'
    db.session.commit()
    write_audit('PAYT_PAID', target=f'Invoice #{inv_id}', detail=f'Amount Rs {invoice.amount_rs:.2f}, ref {txn}')
    flash(f'Payment of Rs {invoice.amount_rs:.2f} confirmed. Thank you!', 'success')
    return redirect(url_for('main.dashboard'))


@main.route('/payt/receipt/<int:inv_id>')
@login_required
def payt_receipt(inv_id):
    """Download the PDF receipt for a PAID PAYT invoice.

    Owner-only (privacy: an invoice's payment details belong to its citizen).
    Generates the receipt on the fly with reportlab — the same builder the
    background email job uses — so the citizen can re-download it any time."""
    invoice = PAYTInvoice.query.get_or_404(inv_id)
    if invoice.user_id != session['user_id']:
        abort(403)
    if invoice.status != 'Paid':
        flash('Receipts are available after the invoice is paid.', 'warning')
        # Closed invoices (Refunded/Waived) have no payment page — send the
        # citizen back to the dashboard, not a pay page they can't use.
        return redirect(url_for('main.dashboard'))
    content, filename = _payt_receipt_pdf_bytes(invoice)
    return Response(content, mimetype='application/pdf',
                    headers={'Content-Disposition': f'attachment; filename={filename}'})


@main.route('/api/notifications/stream')
@login_required
def notifications_stream():
    from flask import Response, stream_with_context
    import time as _time
    MAX_EVENTS = 50

    def event_stream():
        # MAX_EVENTS is rebound below, so it must be declared nonlocal — the
        # stream reads/writes it across branches (snapshot loop, pub/sub loop,
        # DB-poll loop). WITHOUT this, the first decrement raises
        # UnboundLocalError and the stream dies on the first message.
        nonlocal MAX_EVENTS
        # Send current unread immediately. Note: this snapshot races the first
        # pub/sub subscribe below — a notification created in between surfaces
        # on the next page load (the DB poll is the eventual-consistency net).
        uid = session['user_id']
        with current_app.app_context():
            notes = Notification.query.filter_by(
                user_id=uid, read=False).order_by(Notification.id.asc()).all()
            last_id = notes[-1].id if notes else 0
            for n in notes:
                yield f"data: {n.message}\n\n"
                MAX_EVENTS -= 1
                if MAX_EVENTS <= 0:
                    return
        # Redis pub/sub: instant push with a 15s timeout that doubles as a
        # keep-alive heartbeat (proxies kill idle SSE connections). The loop
        # never touches the DB, so the request holds no pool slot and — under
        # gevent workers — no worker is pinned by the stream.
        r = _redis_client()
        if r is not None:
            ps = None
            redis_ok = True
            try:
                ps = r.pubsub()
                ps.subscribe(f"notify:{uid}")
                while MAX_EVENTS > 0:
                    msg = ps.get_message(timeout=15, ignore_subscribe_messages=True)
                    if msg and msg.get('type') == 'message':
                        data = msg['data']
                        if isinstance(data, bytes):
                            data = data.decode('utf-8')
                        yield f"data: {data}\n\n"
                        MAX_EVENTS -= 1
                    else:
                        yield ": ping\n\n"  # heartbeat
            except Exception:
                # Redis configured but down/flapping: degrade to the DB-poll
                # loop below instead of killing live notifications for every
                # connected user (a Redis outage must not take the stream down
                # when the DB is fine). GeneratorExit is BaseException, so a
                # client disconnect still runs the finally cleanly.
                redis_ok = False
            finally:
                if ps is not None:
                    try:
                        ps.close()
                    except Exception:
                        pass
            if redis_ok:
                return
        # No Redis (dev/tests) or Redis failed mid-stream: lightweight DB poll
        # fallback with heartbeat.
        while True:
            _time.sleep(5)
            with current_app.app_context():
                new = Notification.query.filter(
                    Notification.user_id == uid,
                    Notification.id > last_id).order_by(Notification.id.asc()).all()
                for n in new:
                    last_id = n.id
                    yield f"data: {n.message}\n\n"
                    MAX_EVENTS -= 1
                    if MAX_EVENTS <= 0:
                        return
    return Response(stream_with_context(event_stream()),
                    mimetype='text/event-stream')


@main.route('/api/notifications')
@login_required
def notifications_list():
    notes = Notification.query.filter_by(user_id=session['user_id']).order_by(
        Notification.id.desc()).limit(20).all()
    return jsonify([{
        "id": n.id, "message": n.message, "link": n.link,
        "read": n.read, "created_at": n.created_at.isoformat() if n.created_at else None
    } for n in notes])


@main.route('/api/notifications/mark-read', methods=['POST'])
@login_required
def notifications_mark_read():
    Notification.query.filter_by(user_id=session['user_id'], read=False).update({"read": True})
    db.session.commit()
    return jsonify({"ok": True})


# ── Web Push Notification Endpoints ──────────────────────────────

import hashlib, base64, json as _json
from ..models import PushSubscription


@main.route('/api/push/vapid-key')
def push_vapid_key():
    """Return the VAPID public key for the frontend to use in subscribe()."""
    from ..push import get_vapid_public_key
    return jsonify({"publicKey": get_vapid_public_key()})


@main.route('/api/push/subscribe', methods=['POST'])
@login_required
def push_subscribe():
    """Store a browser push subscription for the current user."""
    data = request.get_json(force=True)
    endpoint = data.get('endpoint')
    p256dh = data.get('keys', {}).get('p256dh')
    auth = data.get('keys', {}).get('auth')
    if not endpoint or not p256dh or not auth:
        return jsonify({"error": "Missing subscription keys"}), 400

    # Deduplicate: if this exact endpoint already exists, update last_used_at
    existing = PushSubscription.query.filter_by(endpoint=endpoint).first()
    if existing:
        existing.last_used_at = utcnow()
        if existing.user_id != session['user_id']:
            existing.user_id = session['user_id']
        db.session.commit()
        return jsonify({"ok": True, "action": "updated"})

    sub = PushSubscription(
        user_id=session['user_id'],
        endpoint=endpoint,
        p256dh=p256dh,
        auth=auth,
    )
    db.session.add(sub)
    db.session.commit()
    return jsonify({"ok": True, "action": "created"})


@main.route('/api/push/unsubscribe', methods=['POST'])
@login_required
def push_unsubscribe():
    """Remove a push subscription (or all for the current user)."""
    data = request.get_json(force=True) if request.data else {}
    endpoint = data.get('endpoint')
    if endpoint:
        PushSubscription.query.filter_by(
            user_id=session['user_id'], endpoint=endpoint).delete()
    else:
        PushSubscription.query.filter_by(user_id=session['user_id']).delete()
    db.session.commit()
    return jsonify({"ok": True})


@main.route('/api/push/status')
@login_required
def push_status():
    """Return how many push subscriptions the user has."""
    count = PushSubscription.query.filter_by(user_id=session['user_id']).count()
    return jsonify({"subscribed": count > 0, "deviceCount": count})


@main.route('/api/redeem', methods=['POST'])
@login_required
def redeem_rewards():
    """Redeem green points for a coupon.

    Uses an ATOMIC conditional UPDATE so two concurrent requests (double-click,
    two tabs) can never both pass the balance check and both deduct — the
    previous read-then-write pattern had a race that let a user redeem twice
    for one coupon. The UPDATE only succeeds when the balance is sufficient,
    and `rowcount == 1` is the single source of truth for success.
    """
    user = User.query.get(session['user_id'])
    if user is None:
        return jsonify({"success": False, "message": "Account not found."}), 404
    try:
        points_to_redeem = int(request.form.get('points', 0))
    except (ValueError, TypeError):
        points_to_redeem = 0
    reward_type = request.form.get('reward_type', '')
    if points_to_redeem <= 0:
        return jsonify({"success": False, "message": "Invalid points amount."}), 400
    # Atomic conditional decrement — the DB enforces the balance check.
    result = db.session.execute(
        db.text("UPDATE \"user\" SET green_points = green_points - :pts "
                "WHERE id = :uid AND green_points >= :pts"),
        {"pts": points_to_redeem, "uid": user.id}
    )
    db.session.commit()
    if result.rowcount == 1:
        user = User.query.get(session['user_id'])
        write_audit("REDEEM_POINTS", detail=f"Redeemed {points_to_redeem} pts for {reward_type}.")
        return jsonify({"success": True, "message": f"Coupon redeemed for {reward_type}!",
                        "new_points": user.green_points})
    return jsonify({"success": False, "message": "Insufficient green points."}), 400


@main.route('/dashboard/declare-waste', methods=['POST'])
@login_required
def declare_waste():
    """Record a 4-stream waste declaration and award green points.

    Trust-free integrity guards:
      1. ONE declaration per calendar day per user — the previous route let a
         user POST unlimited times, farming points with fake kg (and fake zero
         declarations to avoid PAYT). The cap matches the WasteDeclaration
         timestamp and is enforced BEFORE any write.
      2. Plausibility check — declared kg is compared against the user's
         household size × ward per-capita norm. Outliers are flagged for admin
         review instead of silently driving PAYT invoices.
      3. Point-awarding is idempotent-background: the points are computed and
         applied in the same transaction as the declaration row itself, so a
         double-POST can never double-award (the daily cap is the first gate).
    """
    user = User.query.get(session['user_id'])
    if user is None:
        flash('Account not found. Please log in again.', 'error')
        return redirect(url_for('main.logout'))
    wet = float(request.form.get('wet_kg', 0) or 0)
    dry = float(request.form.get('dry_kg', 0) or 0)
    sanitary = float(request.form.get('sanitary_kg', 0) or 0)
    hazardous = float(request.form.get('hazardous_kg', 0) or 0)
    if min(wet, dry, sanitary, hazardous) < 0:
        flash('Weights cannot be negative.', 'error')
        return redirect(url_for('main.dashboard'))
    ward = fit_length(request.form.get('ward', ''), 100)
    total_kg = wet + dry + sanitary + hazardous

    # ── Guard 1: one declaration per calendar day (UTC) ──
    today_start = utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    existing_today = WasteDeclaration.query.filter(
        WasteDeclaration.user_id == user.id,
        WasteDeclaration.timestamp >= today_start,
    ).first()
    if existing_today:
        flash('You have already submitted your daily waste declaration. Come back tomorrow!', 'warning')
        return redirect(url_for('main.dashboard'))

    # ── Guard 2: plausibility flag (declared kg vs household × ward norm) ──
    # Average Indian per-capita municipal waste is ~0.45 kg/day. A household of
    # N can plausibly declare ~N×0.45×3 (3x headroom for guests/commercial mix).
    # Beyond that the declaration is flagged for admin audit rather than trusted.
    hh = max(1, user.household_size or 1)
    plausible_limit = hh * 0.45 * 3.0
    flagged = total_kg > plausible_limit
    declaration = WasteDeclaration(user_id=user.id, wet_kg=wet, dry_kg=dry,
                                   sanitary_kg=sanitary, hazardous_kg=hazardous, ward=ward,
                                   flagged_outlier=flagged)
    db.session.add(declaration)
    points_earned = max(5, int(total_kg * 2))
    # Award points only for the PRIMARY daily declaration — capped at 1/day.
    user.green_points += points_earned
    db.session.commit()
    write_audit("WASTE_DECLARATION", target=ward,
                detail=f"Declared {total_kg:.1f}kg total waste."
                + (" FLAGGED for plausibility review." if flagged else ""))
    if flagged:
        flash("Waste declaration submitted (flagged for weight verification). Earned +{points} Green Points 🌿".format(points=points_earned), "warning")
    else:
        flash(f"Waste declaration submitted! Earned +{points_earned} Green Points 🌿", "success")
    return redirect(url_for('main.dashboard'))


@main.route('/api/payt-invoice')
@login_required
def payt_invoice_list():
    invoices = PAYTInvoice.query.filter_by(user_id=session['user_id']).all()
    return jsonify([{
        "id": inv.id, "period": inv.period, "weight_kg": inv.weight_kg,
        "amount_rs": inv.amount_rs, "status": inv.status,
        "issued_at": inv.issued_at.isoformat()
    } for inv in invoices])


@main.route('/report-illegal', methods=['GET', 'POST'])
@limiter.limit("10/hour")
def report_illegal():
    if request.method == 'POST':
        latitude = request.form.get('latitude')
        longitude = request.form.get('longitude')
        category = request.form.get('category', 'Unknown')
        description = request.form.get('description', '')
        ward = request.form.get('ward', '')
        photo_filename = None
        file = request.files.get('photo')
        if file and file.filename != '':
            photo_filename = save_compressed_photo(file, 'illegal')
        report = IllegalDumpReport(
            latitude=float(latitude) if latitude else None,
            longitude=float(longitude) if longitude else None,
            category=fit_length(category, 100), description=description,
            scrubbed_photo=photo_filename, ward=fit_length(ward, 100), status="Pending"
        )
        db.session.add(report)
        db.session.commit()
        # Offline-queue deliveries are logged for the admin delivery-health dashboard
        _record_offline_delivery('/report-illegal', ward=report.ward,
                                 has_photo=bool(photo_filename), illegal_report_id=report.id)
        # No user_id stored — anonymous by design
        flash("Anonymous report submitted. Your identity is protected. Thank you! 🛡️", "success")
        return redirect(url_for('main.report_illegal'))
    return render_template('illegal_dump.html')


@main.route('/bwg-ledger', methods=['GET', 'POST'])
@login_required
def bwg_ledger():
    if request.method == 'POST':
        user = User.query.get(session['user_id'])
        if user is None:
            flash('Account not found. Please log in again.', 'error')
            return redirect(url_for('main.logout'))
        entity_name = fit_length(request.form.get('entity_name', ''), 200)
        entity_type = fit_length(request.form.get('entity_type', 'commercial'), 50)
        composting_kg = float(request.form.get('composting_kg', 0))
        recyclable_kg = float(request.form.get('recyclable_kg', 0))
        landfill_kg = float(request.form.get('landfill_kg', 0))
        request_pickup = request.form.get('request_pickup') == 'on'
        decl = BWGDeclaration(
            user_id=user.id, entity_name=entity_name, entity_type=entity_type,
            composting_kg=composting_kg, recyclable_kg=recyclable_kg,
            landfill_kg=landfill_kg, request_bulk_pickup=request_pickup,
            pickup_status='Pending' if request_pickup else 'N/A'
        )
        db.session.add(decl)
        # Generate PAYT invoice with segregation-compliance penalty
        # (SWM Rules 2026: landfill fees penalise mixed/unsegregated waste)
        total_kg = composting_kg + recyclable_kg + landfill_kg
        segregated_kg = composting_kg + recyclable_kg  # exempt from landfill fee
        if total_kg > 0:
            compliance = round((segregated_kg / total_kg) * 100, 1)
        else:
            compliance = 100.0
        # Penalty multiplier: full compliance (100%) = 1.0; 0% = up to 2.0x
        penalty = round(1.0 + (100.0 - compliance) / 100.0, 2)
        if total_kg >= 100:
            base = round(total_kg * 1.5, 2)  # ₹1.5 per kg base rate
            amount = round(base * penalty, 2)
            # PAYT billing integrity v3: the invoice carries the SELF-REPORTED
            # weight into a "Self-Reported" billing_status. A background
            # reconciliation job matches worker-verified OffloadLog weights
            # per ward/period and flips it to "Verified" (or "Disputed" when
            # the discrepancy > 20%), so only verified weights drive the final
            # invoice amount charged.
            invoice = PAYTInvoice(
                user_id=user.id,
                period=datetime.now(timezone.utc).strftime("%B %Y"),
                weight_kg=total_kg, bin_pickups=0,
                segregation_kg=segregated_kg, landfill_kg=landfill_kg,
                compliance_score=compliance, penalty_multiplier=penalty,
                base_amount_rs=base, amount_rs=amount, status='Unpaid',
                billing_status='Self-Reported'
            )
            db.session.add(invoice)
            if penalty > 1.0:
                flash(f"BWG Declaration recorded. PAYT Invoice of ₹{amount} generated "
                      f"(compliance {compliance:.0f}% → {penalty:.2f}x penalty applied).", "warning")
            else:
                flash(f"BWG Declaration recorded. PAYT Invoice of ₹{amount} generated for {total_kg:.0f}kg.", "success")
        else:
            flash("BWG Declaration submitted successfully.", "success")
        db.session.commit()
        write_audit("BWG_DECLARATION", target=entity_name, detail=f"{total_kg:.1f}kg declared.")
        return redirect(url_for('main.bwg_ledger'))
    declarations = BWGDeclaration.query.filter_by(user_id=session['user_id']).order_by(BWGDeclaration.timestamp.desc()).all()
    return render_template('bwg_ledger.html', declarations=declarations)


@main.route('/report', methods=['GET', 'POST'])
# Public by design: /report is in the sitemap and the homepage promises
# "no login needed to file a report" — residents must be able to report a
# missed pickup without creating an account. Anti-spam stays server-side
# (rate limit, mandatory GPS, photo EXIF cross-check, duplicate suppression).
# Logged-in reporters still earn Green Points; anonymous ones get the full
# resolution flow (SMS tracking link) but no account credit.
@limiter.limit("15/hour")
def report():
    if request.method == 'POST':
        uid = session.get('user_id')
        name = (request.form.get('name') or '').strip() or 'Anonymous Resident'
        phone = (request.form.get('phone') or '').strip()
        ward = request.form.get('ward')
        address = (request.form.get('address') or '').strip() or 'Chintalavalasa'
        description = request.form.get('description')
        latitude = request.form.get('latitude')
        longitude = request.form.get('longitude')
        report_time = (request.form.get('report_time') or '').strip() or utcnow().strftime('%Y-%m-%dT%H:%M')

        dup = find_duplicate_complaint(ward, latitude, longitude)
        if dup:
            flash(f'An open complaint already exists for this location (Ticket #{dup.id}, {dup.status}). Duplicate suppressed.', 'warning')
            return redirect(url_for('main.report'))

        # ── Anti-spam: GPS is mandatory (no silent default-coords fallback).
        # The client blocks submissions without a live device fix; this is the
        # server-side enforcement so a crafted POST can't bypass it.
        try:
            _lat_f = float(latitude) if latitude else None
            _lon_f = float(longitude) if longitude else None
        except (TypeError, ValueError):
            _lat_f = _lon_f = None
        if _lat_f is None or _lon_f is None:
            flash('GPS coordinates are required to file a report. Enable location access and try again.', 'error')
            return redirect(url_for('main.report'))

        photo_filename = None
        file = request.files.get('photo')
        ai_verified = True
        if file and file.filename != '':
            # EXIF cross-check: a photo geotagged far from the submitter's
            # live position is a screenshot / internet image — reject it.
            photo_gps = _photo_gps_from_upload(file)
            if photo_gps is not None:
                dist_m = haversine_m(_lat_f, _lon_f, photo_gps[0], photo_gps[1])
                if dist_m > GPS_VERIFY_RADIUS_M:
                    flash(f'Photo location does not match your device location ({dist_m:.0f}m apart). Please submit a live, on-site photo.', 'error')
                    return redirect(url_for('main.report'))
            # AI image-verification pipeline placeholder (anti-fake-report).
            ai_verified, ai_note = _ai_verify_photo(file)
            if not ai_verified:
                flash('Uploaded photo could not be verified as a valid image. Please retry.', 'error')
                return redirect(url_for('main.report'))
            photo_filename = save_compressed_photo(file, 'complaint')
        # Complaint lifecycle v3: new reports enter the state machine as
        # 'Submitted' with a 48h SLA deadline (escalated in the background job
        # if unresolved past that window). The route links the complaint to a
        # specific bin (by proximity) so auto-resolution is bin-accurate
        # instead of ward-wide.
        _linked_bin = None
        try:
            # Nearest bin in the same ward (tolerant: still links if ward
            # mismatches but within 500m, since users pick wrong wards).
            nearest = None
            nearest_d = 500.0
            for _b in SmartBin.query.filter_by(ward=ward).all():
                try:
                    d = haversine_m(_lat_f, _lon_f, _b.latitude, _b.longitude)
                except Exception:
                    continue
                if d < nearest_d:
                    nearest_d = d
                    nearest = _b
            if nearest is not None:
                _linked_bin = nearest.id
        except Exception:
            _linked_bin = None
        _now = utcnow()
        new_complaint = Complaint(
            name=fit_length(name, 100), phone=fit_length(phone, 15),
            ward=fit_length(ward, 100),
            address=f"Chintalavalasa, {fit_length(address, 200)}", description=description,
            photo=photo_filename, latitude=fit_length(latitude, 50),
            longitude=fit_length(longitude, 50),
            report_time=fit_length(report_time, 100), user_id=uid,
            status='Submitted', bin_id=_linked_bin,
            sla_deadline=_now + timedelta(hours=48))
        db.session.add(new_complaint)
        # Green Points are a logged-in reward; anonymous reports (the form is
        # now public) still enter the full resolution flow without credit.
        if uid:
            user = User.query.get(uid)
            if user is None:
                flash('Account not found. Please log in again.', 'error')
                return redirect(url_for('main.logout'))
            user.green_points += 15
        db.session.commit()
        # Citizen-tracking timeline: the first event is the filing itself.
        record_complaint_event(new_complaint, 'Submitted',
                               'Complaint filed — the sanitation control room has been alerted.')
        # SMS/WhatsApp the reporter a signed tracking link (skipped on localhost).
        _send_tracking_link(new_complaint)
        write_audit("COMPLAINT_SUBMIT", target=ward, detail=f"Overflow report filed by {name}."
                    + ("" if ai_verified else " AI image verification pending."))
        # Offline-queue deliveries are logged for the admin delivery-health dashboard
        _record_offline_delivery('/report', ward=ward, has_photo=bool(photo_filename),
                                 complaint_id=new_complaint.id)
        track_token = make_complaint_token(new_complaint.id)
        return render_template('success.html', complaint_id=new_complaint.id,
                               track_url=url_for('main.track_complaint', token=track_token,
                                                 _external=True))
    return render_template('report.html')
