"""Web Push notification utilities.

Manages VAPID keys and sends push notifications via the Web Push API.
Uses pywebpush for encryption and delivery. All sends are best-effort
and never raise — a failed push is logged and skipped.
"""
import os
import json
import structlog

logger = structlog.get_logger(__name__)

# ── VAPID Key Management ────────────────────────────────────────
# Keys are generated once and stored in instance/vapid_private.pem
# and instance/vapid_public.pem. If they don't exist, we generate them.

_vapid_private_path = None
_vapid_public_key = None


def _get_vapid_paths():
    """Return (private_path, public_path) inside the instance folder."""
    from flask import current_app
    instance = current_app.instance_path
    return (
        os.path.join(instance, 'vapid_private.pem'),
        os.path.join(instance, 'vapid_public.pem'),
    )


def _ensure_vapid_keys():
    """Generate VAPID key pair if it doesn't exist."""
    global _vapid_private_path, _vapid_public_key
    if _vapid_public_key is not None:
        return

    priv_path, pub_path = _get_vapid_paths()

    if os.path.exists(priv_path) and os.path.exists(pub_path):
        _vapid_private_path = priv_path
        with open(pub_path, 'r') as f:
            _vapid_public_key = f.read().strip()
        return

    # Generate new key pair
    try:
        from py_vapid import Vapid
        vapid = Vapid()
        vapid.generate_keys()
        os.makedirs(os.path.dirname(priv_path), exist_ok=True)
        with open(priv_path, 'wb') as f:
            f.write(vapid.private_pem())
        with open(pub_path, 'w') as f:
            f.write(vapid.public_key)
        _vapid_private_path = priv_path
        _vapid_public_key = vapid.public_key
        logger.info("vapid_keys_generated", path=priv_path)
    except ImportError:
        logger.warning("py_vapid_not_installed_push_disabled")
        _vapid_public_key = ""


def get_vapid_private_key():
    """Return the VAPID private key PEM bytes."""
    _ensure_vapid_keys()
    if _vapid_private_path and os.path.exists(_vapid_private_path):
        with open(_vapid_private_path, 'rb') as f:
            return f.read()
    return None


def get_vapid_public_key():
    """Return the VAPID public key string."""
    _ensure_vapid_keys()
    return _vapid_public_key or ""


def get_vapid_claims():
    """Return VAPID claims (audience + contact)."""
    from flask import current_app
    contact = current_app.config.get('VAPID_CONTACT_EMAIL', 'mailto:admin@smartgarbage.onrender.com')
    return {"aud": "https://fcm.googleapis.com", "sub": contact}


# ── Send Push Notification ───────────────────────────────────────

def send_push_notification(user_id, title, body, url="/dashboard"):
    """Send a web push notification to all of a user's subscribed devices.

    Best-effort: never raises. Logs failures and removes dead subscriptions.
    Every attempt is recorded in PushNotificationLog for admin analytics.
    """
    from .models import PushSubscription, PushNotificationLog, db

    subs = PushSubscription.query.filter_by(user_id=user_id).all()
    if not subs:
        return

    private_key = get_vapid_private_key()
    if not private_key:
        logger.warning("push_send_no_vapid_key")
        return

    payload = json.dumps({
        "title": title,
        "body": body,
        "url": url,
        "icon": "/static/icon-192.png",
        "badge": "/static/icon-192.png",
        "tag": f"sg-{url}",
        "data": {"url": url},
    })

    dead_endpoints = []
    sent_count = 0
    failed_count = 0

    for sub in subs:
        try:
            from pywebpush import webpush, WebPushException
            webpush(
                subscription_info={
                    "endpoint": sub.endpoint,
                    "keys": {"p256dh": sub.p256dh, "auth": sub.auth},
                },
                data=payload,
                vapid_private_key=private_key,
                vapid_claims=get_vapid_claims(),
                ttl=86400,  # 24h
            )
            sub.last_used_at = utcnow()
            sent_count += 1
            logger.info("push_sent", user_id=user_id, endpoint=sub.endpoint[:50])
        except Exception as e:
            error_str = str(e)
            # 404 = subscription expired, 410 = subscription unsubscribed
            if '404' in error_str or '410' in error_str or 'expired' in error_str.lower():
                dead_endpoints.append(sub.endpoint)
                logger.info("push_dead_subscription", endpoint=sub.endpoint[:50])
                # Log dead subscription
                try:
                    db.session.add(PushNotificationLog(
                        user_id=user_id, title=title, body=body, url=url,
                        status='dead', error=error_str[:500],
                        endpoint=sub.endpoint[:200],
                    ))
                except Exception:
                    pass
            else:
                failed_count += 1
                logger.warning("push_send_failed", error=error_str[:200])
                # Log failed attempt
                try:
                    db.session.add(PushNotificationLog(
                        user_id=user_id, title=title, body=body, url=url,
                        status='failed', error=error_str[:500],
                        endpoint=sub.endpoint[:200],
                    ))
                except Exception:
                    pass

    # Log successful sends
    if sent_count > 0:
        try:
            db.session.add(PushNotificationLog(
                user_id=user_id, title=title, body=body, url=url,
                status='sent', endpoint=f'{sent_count} device(s)',
            ))
        except Exception:
            pass

    # Clean up dead subscriptions
    if dead_endpoints:
        for ep in dead_endpoints:
            PushSubscription.query.filter_by(endpoint=ep).delete()
        db.session.commit()
    else:
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()


def send_complaint_status_push(complaint):
    """Send push notification when a complaint status changes.

    Called from _notify_status_change() after in-app notification is created.
    """
    from flask import url_for

    if not complaint.user_id:
        return

    status_messages = {
        'Submitted': 'Your complaint has been received.',
        'Under Review': 'Your complaint is being reviewed by the ward officer.',
        'Assigned': 'A sanitation worker has been assigned to your complaint.',
        'In Progress': 'A worker is on the way to resolve your complaint.',
        'Escalated': 'Your complaint has been escalated for urgent attention.',
        'Resolved': 'Your complaint has been resolved! 🎉',
        'Closed': 'Your complaint has been closed.',
    }

    status = complaint.status
    msg = status_messages.get(status, f'Your complaint status changed to {status}.')
    title = f"🗑️ Complaint #{complaint.id}"
    body = f"{msg} Ward: {complaint.ward or 'N/A'}"

    try:
        track_url = url_for('main.track_complaint', token='', _external=True).rstrip('/')
        # Use the tracking page if available, otherwise dashboard
        url = f"/dashboard"
    except Exception:
        url = "/dashboard"

    send_push_notification(complaint.user_id, title, body, url=url)
