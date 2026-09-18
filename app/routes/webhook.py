import os
import hashlib
import hmac
import json as _json
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


@main.route('/webhook/whatsapp-cloud', methods=['GET'])
def webhook_whatsapp_cloud_verify():
    """Meta webhook subscription handshake (WhatsApp Cloud API).

    When you click "Webhooks -> Manage -> Edit" in the Meta App Dashboard and
    point it at this URL, Meta first sends a GET with hub.mode=subscribe and a
    hub.verify_token you typed into the dashboard. Echoing hub.challenge back
    completes the subscription so Meta starts POSTing citizen "Hi" messages —
    each of which opens the sender's 24h service window that carries all OTP/
    status replies (free with no cap through Sep 30, 2026; from Oct 1, 2026
    Meta bills per delivered message but every number gets 1,000 free
    service messages per month — inbound citizen messages are always free).

    Set WHATSAPP_WEBHOOK_VERIFY_TOKEN in the environment to the exact string
    you typed into the Meta dashboard. Without it the handshake always fails
    closed (403) so a forgot-token deploy can't silently accept subscriptions.
    """
    mode = request.args.get('hub.mode')
    token = request.args.get('hub.verify_token')
    challenge = request.args.get('hub.challenge')
    expected = os.environ.get('WHATSAPP_WEBHOOK_VERIFY_TOKEN')
    if mode == 'subscribe' and expected and token == expected and challenge:
        return challenge, 200, {'Content-Type': 'text/plain; charset=utf-8'}
    logger.warning("whatsapp_cloud_verify_rejected", mode=mode,
                   token_ok=bool(expected and token == expected))
    return 'Forbidden', 403


@main.route('/webhook/whatsapp-cloud', methods=['POST'])
@limiter.limit("120/minute")
@csrf.exempt
def webhook_whatsapp_cloud():
    """Meta WhatsApp Cloud API inbound messages.

    Two jobs:
    1. Log a citizen's photo report (message with image + caption) as an
       anonymous IllegalDumpReport — the same contract as the Twilio path.
    2. Register that the sender messaged us (an audit entry), which is what
       opens their 24h customer-service window so outbound OTP/status texts
       ride the free service-reply class (uncapped through Sep 30, 2026;
       from Oct 1, 2026 the first 1,000 delivered service replies per month
       are free — inbound messages are never charged).

    Security: X-Hub-Signature-256 (HMAC-SHA256 of the raw body keyed by the
    app secret) is verified whenever WHATSAPP_APP_SECRET is configured;
    unconfigured (local dev) the signature check is skipped so the endpoint
    stays testable — matching the Twilio webhook's dev-sandbox behavior.
    Always answers 200 (Meta retries non-2xx for up to ~24h otherwise).
    """
    raw = request.get_data(cache=True) or b''
    app_secret = os.environ.get('WHATSAPP_APP_SECRET')
    if app_secret:
        provided = (request.headers.get('X-Hub-Signature-256') or '').removeprefix('sha256=')
        expected = hmac.new(app_secret.encode(), raw, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(provided, expected):
            logger.warning("whatsapp_cloud_signature_invalid", ip=request.remote_addr)
            return 'Invalid signature', 403
    payload = request.get_json(silent=True) or {}
    try:
        for entry in (payload.get('entry') or []):
            for change in (entry.get('changes') or []):
                value = change.get('value') or {}
                for msg in (value.get('messages') or []):
                    sender = msg.get('from') or ''          # E.164 digits, e.g. 919876543210
                    mtype = msg.get('type')
                    body = ''
                    lat = lon = None
                    photo = None
                    if mtype == 'text':
                        body = (msg.get('text') or {}).get('body') or ''
                    elif mtype == 'image':
                        image = msg.get('image') or {}
                        body = image.get('caption') or ''
                        media_id = image.get('id')
                        token = os.environ.get('WHATSAPP_CLOUD_TOKEN')
                        if media_id and token:
                            photo, gps = _download_whatsapp_media(media_id, token)
                            if gps:
                                lat, lon = gps
                    if mtype == 'location':
                        loc = msg.get('location') or {}
                        lat, lon = loc.get('latitude'), loc.get('longitude')
                        body = (msg.get('location') or {}).get('name') or body
                    if sender:
                        report = IllegalDumpReport(
                            latitude=float(lat) if lat is not None else None,
                            longitude=float(lon) if lon is not None else None,
                            category='WhatsApp Report',
                            description=body or f'WhatsApp {mtype or "unknown"} message received.',
                            scrubbed_photo=photo, ward='', status='Pending'
                        )
                        db.session.add(report)
                        db.session.commit()
                        write_audit("ILLEGAL_REPORT_WHATSAPP_CLOUD",
                                    detail=f"from {sender[:6]}**** type={mtype}")
    except Exception as e:
        # Never error to Meta: log and ack, else delivery retries storm.
        logger.error("whatsapp_cloud_webhook_error", error=str(e))
        db.session.rollback()
    return jsonify({'ok': True})


def _download_whatsapp_media(media_id, token):
    """Fetch a Meta media item (image) by id and return (bytes, (lat, lon)).

    Two-step Graph API flow: GET /{media-id} returns a temporary URL, then a
    authenticated GET downloads the bytes. EXIF GPS extraction is delegated to
    _download_illegal_media by handing it the URL with a Bearer header — but
    Meta's URL rejects Authorization headers, so the bytes are fetched here and
    EXIF is extracted locally via the shared helper's parser when possible.
    """
    try:
        meta = requests.get(
            f"https://graph.facebook.com/v21.0/{media_id}",
            params={'access_token': token}, timeout=8)
        if meta.status_code // 100 != 2:
            logger.warning("whatsapp_media_meta_failed", status=meta.status_code)
            return None, None
        url = (meta.json() or {}).get('url')
        if not url:
            return None, None
        dl = requests.get(url, timeout=10)
        if dl.status_code // 100 != 2 or not dl.content:
            return None, None
        blob = dl.content
        gps = None
        try:
            import io
            from PIL import Image
            from PIL.ExifTags import GPSTAGS
            img = Image.open(io.BytesIO(blob))
            exif = img._getexif() or {}
            gps_tags_raw = exif.get(34853)  # GPSInfo tag id
            if gps_tags_raw:
                # normalize tag names -> readable keys (GPSLatitude, GPSLatitudeRef, ...)
                gps_tags = {GPSTAGS.get(k, k): v for k, v in gps_tags_raw.items()}

                def _dms(v):
                    """(deg, min, sec) rationals -> float degrees."""
                    try:
                        d, m, s = v
                        return float(d) + float(m) / 60 + float(s) / 3600
                    except Exception:
                        return None

                lat = _dms(gps_tags.get('GPSLatitude'))
                lon = _dms(gps_tags.get('GPSLongitude'))
                if lat is not None and str(gps_tags.get('GPSLatitudeRef', 'N')).upper().startswith('S'):
                    lat = -lat
                if lon is not None and str(gps_tags.get('GPSLongitudeRef', 'E')).upper().startswith('W'):
                    lon = -lon
                gps = (lat, lon) if lat and lon else None
        except Exception:
            gps = None
        return blob, gps
    except Exception as e:
        logger.error("whatsapp_media_download_error", error=str(e))
        return None, None


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
