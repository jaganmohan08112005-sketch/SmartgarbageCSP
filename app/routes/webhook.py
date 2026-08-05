import os
import requests

from flask import (jsonify, request)

from ..models import (AuditLog, IllegalDumpReport, PAYTInvoice, utcnow)

from .. import csrf, db, limiter

from . import (_download_illegal_media, _verify_razorpay_webhook_signature,
               _verify_telegram_secret, _verify_twilio_signature, logger, main, write_audit)


# Inbound WhatsApp/Telegram webhooks. With no real Twilio/Telegram credentials
# configured (dev sandbox), signature checks are skipped so the bots keep working.
@main.route('/webhook/whatsapp', methods=['POST'])
@limiter.limit("60/minute")
@csrf.exempt
def webhook_whatsapp():
    """Twilio WhatsApp inbound webhook. A citizen photos a trash pile; we extract
    GPS from the image (or supplied lat/lon), log an anonymous IllegalDumpReport,
    and reply with a TwiML acknowledgement."""
    from flask import Response
    if not _verify_twilio_signature():
        logger.warning("whatsapp_signature_invalid", ip=request.remote_addr)
        return Response('Signature validation failed.', mimetype='text/plain', status=403)
    form = request.form
    sender = form.get('From', '')
    body = form.get('Body', '')
    num_media = int(form.get('NumMedia', 0) or 0)
    lat = form.get('Latitude')
    lon = form.get('Longitude')
    photo, gps = None, None
    if num_media > 0:
        media_url = form.get('MediaUrl0')
        sid = os.environ.get('TWILIO_ACCOUNT_SID')
        token = os.environ.get('TWILIO_AUTH_TOKEN')
        auth = (sid, token) if sid and token else None
        photo, gps = _download_illegal_media(media_url, auth)
        if gps:
            lat, lon = gps
    report = IllegalDumpReport(
        latitude=float(lat) if lat else None,
        longitude=float(lon) if lon else None,
        category='WhatsApp Report',
        description=body or 'Illegal dump reported via WhatsApp bot.',
        scrubbed_photo=photo, ward='', status='Pending'
    )
    db.session.add(report)
    db.session.commit()
    write_audit("ILLEGAL_REPORT_WHATSAPP", detail=f"From {sender}, media={num_media}")
    twiml = ('<?xml version="1.0" encoding="UTF-8"?>'
             '<Response><Message>✅ Report received! Ticket #'
             f'{report.id} logged. Our team will inspect the location.</Message></Response>')
    return Response(twiml, mimetype='application/xml')


@main.route('/webhook/telegram', methods=['POST'])
@limiter.limit("60/minute")
@csrf.exempt
def webhook_telegram():
    """Telegram Bot API webhook. Accepts a photo (+ optional location/caption),
    resolves the file via Telegram API, extracts GPS, logs an IllegalDumpReport."""
    if not _verify_telegram_secret():
        logger.warning("telegram_secret_invalid", ip=request.remote_addr)
        return jsonify({"ok": False, "error": "Forbidden"}), 403
    data = request.get_json(silent=True) or {}
    message = data.get('message', {})
    chat_id = message.get('chat', {}).get('id')
    caption = message.get('caption', '')
    location = message.get('location')
    lat = location.get('latitude') if location else None
    lon = location.get('longitude') if location else None
    photo, gps = None, None
    photos = message.get('photo')
    if photos:
        file_id = photos[-1]['file_id']  # largest resolution
        token = os.environ.get('TELEGRAM_BOT_TOKEN')
        if token:
            try:
                fresp = requests.get(
                    f"https://api.telegram.org/bot{token}/getFile?file_id={file_id}",
                    timeout=10).json()
                if fresp.get('ok'):
                    file_path = fresp['result']['file_path']
                    media_url = f"https://api.telegram.org/file/bot{token}/{file_path}"
                    photo, gps = _download_illegal_media(media_url)
            except Exception as e:
                logger.error("telegram_file_error", error=str(e))
    if gps:
        lat, lon = gps
    report = IllegalDumpReport(
        latitude=float(lat) if lat else None,
        longitude=float(lon) if lon else None,
        category='Telegram Report',
        description=caption or 'Illegal dump reported via Telegram bot.',
        scrubbed_photo=photo, ward='', status='Pending'
    )
    db.session.add(report)
    db.session.commit()
    write_audit("ILLEGAL_REPORT_TELEGRAM", detail=f"chat_id {chat_id}")
    # Telegram expects a 200 OK acknowledgement
    return jsonify({"ok": True, "ticket_id": report.id})


@main.route('/webhook/razorpay', methods=['POST'])
@limiter.limit("60/minute")
@csrf.exempt
def webhook_razorpay():
    """Razorpay payment-capture webhook.

    Trust boundary: the X-Razorpay-Signature header (HMAC-SHA256 over the raw
    body, keyed by RAZORPAY_WEBHOOK_SECRET) proves Razorpay — not a citizen —
    sent the event, so the invoice is only ever marked Paid server-side.
    Idempotent: re-delivered captures are no-ops. Unknown orders are logged
    and acknowledged (Razorpay expects a 2xx either way).
    """
    if not _verify_razorpay_webhook_signature():
        logger.warning("razorpay_webhook_signature_invalid", ip=request.remote_addr)
        return jsonify({"ok": False, "error": "Invalid signature"}), 403
    data = request.get_json(silent=True) or {}
    event = data.get('event', '')
    payment = (data.get('payload') or {}).get('payment') or {}
    entity = payment.get('entity') or {}
    if event == 'payment.captured' and entity.get('order_id'):
        invoice = PAYTInvoice.query.filter_by(
            razorpay_order_id=entity['order_id']).first()
        if invoice is None:
            logger.warning("razorpay_webhook_unknown_order", order_id=entity['order_id'])
            return jsonify({"ok": True, "ignored": "unknown_order"})
        if invoice.status != 'Paid':
            # A refunded/waived invoice is TERMINAL — a re-delivered or late
            # capture must never resurrect it (money was reversed/forgiven).
            if invoice.refund_id or invoice.status in ('Refunded', 'Waived'):
                logger.info("payt_webhook_capture_ignored_terminal",
                            invoice_id=invoice.id, status=invoice.status)
                return jsonify({"ok": True, "handled": True, "ignored": "terminal_state"})
            invoice.status = 'Paid'
            invoice.paid_at = utcnow()
            invoice.transaction_ref = (entity.get('id') or invoice.transaction_ref or '')[:120]
            invoice.payment_method = 'Razorpay'
            # The attempt finally succeeded — the retry counter is stale now.
            invoice.failed_attempts = 0
            invoice.last_failed_at = None
            invoice.last_failed_reason = None
            db.session.commit()
            write_audit('PAYT_PAID', target=f'Invoice #{invoice.id}',
                        detail=f'Razorpay webhook capture {entity.get("id")}, Rs {invoice.amount_rs:.2f}')
            logger.info("payt_webhook_captured", invoice_id=invoice.id,
                        payment_id=entity.get('id'))
            # Generate + email the citizen's downloadable PDF receipt off the
            # webhook request path (reportlab + SMTP must never delay the 2xx).
            from ..jobs import enqueue, payt_receipt_job
            enqueue(payt_receipt_job, invoice.id)
        return jsonify({"ok": True, "handled": True})
    if event == 'payment.failed' and entity.get('order_id'):
        # Failure events are INFORMATIONAL ONLY: they bump a per-invoice retry
        # counter and audit the attempt, but invoice.status stays capture-driven
        # (only payment.captured / a signature-verified verify flips it). A
        # failed attempt must never be able to downgrade a Paid invoice.
        invoice = PAYTInvoice.query.filter_by(
            razorpay_order_id=entity['order_id']).first()
        if invoice is None:
            logger.warning("razorpay_webhook_unknown_order", order_id=entity['order_id'])
            return jsonify({"ok": True, "ignored": "unknown_order"})
        if invoice.status != 'Paid':  # late failure after capture: ignore
            # Razorpay delivers webhooks at-least-once, so dedupe re-deliveries
            # of the SAME payment failure via the immutable audit ledger (the
            # same idempotency discipline payment.captured already follows).
            payment_id = entity.get('id') or ''
            if payment_id:
                # Prefix match on the immutable audit detail (filter_by would be
                # an exact match, but the detail carries the attempt text after
                # the payment_id marker). ilike keeps it collation-proof.
                dup = AuditLog.query.filter(
                    AuditLog.action == 'PAYT_PAYMENT_FAILED',
                    AuditLog.target == f'Invoice #{invoice.id}',
                    AuditLog.detail.like(f'payment_id={payment_id}|%')).first()
                if dup is not None:
                    logger.info("payt_webhook_payment_failed_dedup",
                                invoice_id=invoice.id, payment_id=payment_id)
                    return jsonify({"ok": True, "handled": True, "deduped": True})
            invoice.failed_attempts = (invoice.failed_attempts or 0) + 1
            invoice.last_failed_at = utcnow()
            invoice.last_failed_reason = (entity.get('error_description')
                                          or entity.get('error_code') or '')[:200]
            db.session.commit()
            write_audit('PAYT_PAYMENT_FAILED', target=f'Invoice #{invoice.id}',
                        detail=(f'payment_id={payment_id}|'
                                f"Attempt {invoice.failed_attempts} failed for order "
                                f"{entity['order_id']}: {invoice.last_failed_reason or 'no reason'}"))
            logger.info("payt_webhook_payment_failed", invoice_id=invoice.id,
                        payment_id=payment_id,
                        attempts=invoice.failed_attempts,
                        reason=invoice.last_failed_reason)
        return jsonify({"ok": True, "handled": True})
    # Any other event (order.paid, payment.authorized, …) is acknowledged.
    return jsonify({"ok": True, "ignored": event or "unknown_event"})
