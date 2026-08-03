import os
import re
import sys
import hmac
import base64
import hashlib
import json
import random
import structlog
from datetime import datetime, timedelta, timezone
from itsdangerous import URLSafeTimedSerializer
from flask import (Blueprint, request, url_for, session, flash, current_app)
from werkzeug.utils import secure_filename
import requests

# ──────────────────────────────────────────────
# PHONE VALIDATION HELPER
# ──────────────────────────────────────────────
def validate_indian_phone(phone):
    """Validate an Indian mobile number.
    Accepts: +91XXXXXXXXXX or 91XXXXXXXXXX or XXXXXXXXXX (10 digits starting 6-9).
    Returns normalised +91XXXXXXXXXX on success, None on failure.
    Rejects obviously fake sequences (all-same digit, sequential runs).
    """
    if not phone:
        return None
    # Strip spaces, dashes, parentheses
    cleaned = re.sub(r'[\s\-().]+', '', phone)
    # Accept optional +91 or 91 prefix
    match = re.fullmatch(r'(?:\+91|91)?([6-9]\d{9})', cleaned)
    if not match:
        return None
    digits = match.group(1)
    # Reject all-same digit: 9999999999, 6666666666 …
    if len(set(digits)) == 1:
        return None
    # Reject simple ascending/descending sequences: 1234567890, 9876543210
    asc  = ''.join(str((int(digits[0]) + i) % 10) for i in range(10))
    desc = ''.join(str((int(digits[0]) - i) % 10) for i in range(10))
    if digits == asc or digits == desc:
        return None
    return f'+91{digits}'

# Ensure UTF-8 stdout
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

from .. import db, limiter, csrf, current_app
from ..models import (Schedule, Complaint, User, SmartBin, WorkerProfile, IncidentLog,
                     AuditLog, SensorHealth, OffloadLog, IllegalDumpReport,
                     WasteDeclaration, BWGDeclaration, PAYTInvoice, FirmwareRelease,
                     Notification, Webhook, OfflineDelivery, utcnow)
from ..ml_model import predict_miss, predict_overflow_eta_hours

logger = structlog.get_logger("smartgarbage.routes")

# ──────────────────────────────────────────────
# OTP HASHING HELPER
# ──────────────────────────────────────────────
def _hash_otp(otp_val):
    """One-way hash for OTPs at rest — never store plaintext OTPs in the DB.
    Matches the same digest used in login() / auth_phone_login() / mfa_verify()."""
    return hashlib.sha256(otp_val.encode('utf-8')).hexdigest()


# ──────────────────────────────────────────────
# ACCOUNT LOCKOUT POLICY (brute-force defense)
# The columns exist on User; these helpers enforce them so repeated failed
# logins lock the account for a cooling window instead of allowing unlimited
# guessing (the global IP rate limit alone is bypassable via proxy rotation).
# ──────────────────────────────────────────────
# 10 attempts before a 15-min cool-down: low enough to stop brute force, high
# enough that a stranger can't trivially DoS a victim's account with 5 guesses.
MAX_LOGIN_ATTEMPTS = 10
LOCKOUT_MINUTES = 15


def _locked_until_utc(user):
    """Return the lockout expiry as a timezone-aware UTC datetime.

    SQLite returns naive datetimes (it has no tz support); Postgres returns
    aware ones. Normalize so arithmetic like `until - now` never raises.
    """
    until = user.locked_until if user else None
    if until is not None and until.tzinfo is None:
        until = until.replace(tzinfo=timezone.utc)
    return until


def _is_account_locked(user):
    """True while the account is inside its lockout window."""
    until = _locked_until_utc(user)
    return until is not None and until > datetime.now(timezone.utc)


def _record_failed_login(user):
    """Increment the failed-attempt counter and lock the account at the threshold."""
    user.failed_login_count = (user.failed_login_count or 0) + 1
    if user.failed_login_count >= MAX_LOGIN_ATTEMPTS:
        user.locked_until = utcnow() + timedelta(minutes=LOCKOUT_MINUTES)
    db.session.commit()


def _clear_login_failures(user):
    """Reset the failure counter after a successful login."""
    if user.failed_login_count or user.locked_until:
        user.failed_login_count = 0
        user.locked_until = None
        db.session.commit()


# ──────────────────────────────────────────────
# SUPABASE STORAGE HELPER
# ──────────────────────────────────────────────
def _upload_to_supabase(data, filename, prefix):
    """Upload compressed bytes to Supabase Storage bucket 'uploads'.
    Returns a public URL on success, or None on failure."""
    try:
        from supabase import create_client
        url = os.environ.get('SUPABASE_URL')
        key = os.environ.get('SUPABASE_SERVICE_ROLE_KEY') or os.environ.get('SUPABASE_ANON_KEY')
        if not url or not key:
            return None
        client = create_client(url, key)
        path = f"{prefix}/{filename}"
        client.storage.from_('uploads').upload(path, data, {'content-type': 'image/jpeg', 'upsert': 'true'})
        public_url = client.storage.from_('uploads').get_public_url(path)
        return public_url
    except Exception as e:
        logger.error("supabase_upload_failed", error=str(e))
        return None


# ──────────────────────────────────────────────
# PHOTO COMPRESSION HELPER
# ──────────────────────────────────────────────
MAX_IMAGE_DIM = 1280      # longest edge, px
JPEG_QUALITY = 82         # good visual quality, ~5-10x smaller than phone photos

def save_compressed_photo(file_storage, prefix):
    """Save an uploaded photo compressed + EXIF-stripped, then persist it.

    On Render (and any host with Cloudinary configured via CLOUDINARY_URL) the
    compressed bytes are uploaded to Cloudinary object storage and a public URL is
    returned — this survives container restarts, unlike the ephemeral /tmp disk.
    When Cloudinary is not configured (local dev) the file is written to the local
    UPLOAD_FOLDER and a relative path ('uploads/foo.jpg') is returned, which the
    templates resolve against /static.

    Opens with Pillow, resizes to MAX_IMAGE_DIM on the longest edge, re-saves as
    JPEG at JPEG_QUALITY (~5-10x smaller than phone photos), strips all EXIF as a
    privacy side-effect. Falls back to the raw file on any error.
    """
    # Cap the original filename stem so the composite path/URL stays under the
    # VARCHAR(200) photo columns — Postgres enforces lengths SQLite ignores.
    _stem = secure_filename(file_storage.filename or 'photo.jpg')[:80] or 'photo.jpg'
    filename = f"{prefix}_{random.randint(10000, 99999)}_{_stem}"
    try:
        from PIL import Image
        import io
        img = Image.open(file_storage.stream if hasattr(file_storage, 'stream') else file_storage)
        img = img.convert('RGB')  # drop alpha + any exotic modes
        img.thumbnail((MAX_IMAGE_DIM, MAX_IMAGE_DIM))
        buf = io.BytesIO()
        # Save to an in-memory buffer as JPEG (no EXIF survives the RGB re-encode).
        img.save(buf, format='JPEG', quality=JPEG_QUALITY, optimize=True)
        data = buf.getvalue()
    except Exception as e:
        current_app.logger.warning("Photo compress failed for %s: %s", filename, e)
        file_storage.seek(0)
        data = file_storage.read()

    # Storage priority: Supabase > Cloudinary > local disk.
    # Supabase is preferred when SUPABASE_URL + key are set (managed, survives restarts).
    supabase_url = _upload_to_supabase(data, filename, prefix)
    if supabase_url:
        return supabase_url

    # Cloudinary is optional. If CLOUDINARY_URL is set, upload there; else local disk.
    cloudinary_url = os.getenv('CLOUDINARY_URL')
    if cloudinary_url:
        try:
            import cloudinary
            import cloudinary.uploader
            cloudinary.config(secure=True)
            result = cloudinary.uploader.upload(
                data, public_id=f"smartgarbage/{prefix}/{filename.rsplit('.', 1)[0]}",
                folder="smartgarbage", resource_type="image")
            return result.get('secure_url', '')
        except Exception as e:
            current_app.logger.error("Cloudinary upload failed for %s: %s", filename, e)
            # Fall through to local disk so we never lose the upload.

    upload_path = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
    os.makedirs(os.path.dirname(upload_path), exist_ok=True)
    with open(upload_path, 'wb') as f:
        f.write(data)
    return f"uploads/{filename}"

main = Blueprint('main', __name__)

# ──────────────────────────────────────────────
# CONSTANTS & CONFIG
# ──────────────────────────────────────────────
WARD_COORDINATES = {
    "Ward 1 - MVGR College Area":          {"lat": 18.0552, "lon": 83.4051},
    "Ward 2 - Chintalavalasa Junction":    {"lat": 18.0675, "lon": 83.4094},
    "Ward 3 - RTC Colony":                 {"lat": 18.0702, "lon": 83.4153},
    "Ward 4 - Ramalayam Street":           {"lat": 18.0650, "lon": 83.4005},
    "Ward 5 - Sai Nagar":                  {"lat": 18.0751, "lon": 83.4201},
}
DEFAULT_LAT = 18.0675
DEFAULT_LON = 83.4094

# Geo-fence sector polygons per vehicle (bounding box format: [[lat,lon], ...])
SECTOR_POLYGONS = {
    "CV-01": [[18.0530,83.4020],[18.0530,83.4080],[18.0590,83.4080],[18.0590,83.4020]],
    "CV-02": [[18.0650,83.4060],[18.0650,83.4120],[18.0710,83.4120],[18.0710,83.4060]],
    "CV-03": [[18.0680,83.4120],[18.0680,83.4190],[18.0740,83.4190],[18.0740,83.4120]],
    "CV-04": [[18.0620,83.3970],[18.0620,83.4030],[18.0680,83.4030],[18.0680,83.3970]],
    "CV-05": [[18.0720,83.4160],[18.0720,83.4240],[18.0790,83.4240],[18.0790,83.4160]],
}
DUMP_YARDS = ["YARD-A (Vizianagaram Central)", "YARD-B (East Processing Plant)", "YARD-C (North Recycling Hub)"]


# ──────────────────────────────────────────────
# UTILITIES
# ──────────────────────────────────────────────
def get_wmo_phrase(code):
    if code == 0: return "Clear Skies"
    if code in [1, 2, 3]: return "Mainly Clear / Partly Cloudy"
    if code in [45, 48]: return "Foggy Conditions"
    if code in [51, 53, 55]: return "Drizzle / Light Rain"
    if code in [61, 63, 65]: return "Rainy Weather"
    if code in [80, 81, 82]: return "Heavy Rain Showers"
    if code in [95, 96, 99]: return "Thunderstorm Alert"
    return "Normal Seasonal Conditions"

def point_in_polygon(lat, lon, polygon):
    """Ray-casting algorithm to test if point is inside polygon."""
    n = len(polygon)
    inside = False
    px, py = lat, lon
    j = n - 1
    for i in range(n):
        xi, yi = polygon[i]
        xj, yj = polygon[j]
        if ((yi > py) != (yj > py)) and (px < (xj - xi) * (py - yi) / (yj - yi) + xi):
            inside = not inside
        j = i
    return inside

def fit_length(value, max_len):
    """Truncate a string to a column's VARCHAR(n) limit (Postgres parity).

    SQLite silently ignores declared string lengths; Postgres raises a
    DataError past VARCHAR(n). Free-text form fields are truncated at the
    boundary so a long citizen input can never crash the write.
    """
    if value is None:
        return None
    return value[:max_len]


import math

def haversine_m(lat1, lon1, lat2, lon2):
    """Return distance in meters between two lat/lon points."""
    R = 6371000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def find_duplicate_complaint(ward, lat, lon, window_minutes=30, radius_m=100):
    """Check for an existing open complaint within radius_m and window_minutes.

    Returns the matching Complaint or None. Used to deduplicate rapid repeat
    reports from the same overflow event."""
    from datetime import timedelta
    from ..models import Complaint
    if lat is None or lon is None:
        return None
    try:
        lat_f, lon_f = float(lat), float(lon)
    except (TypeError, ValueError):
        return None
    cutoff = utcnow() - timedelta(minutes=window_minutes)
    candidates = Complaint.query.filter(
        Complaint.ward == ward,
        Complaint.status != 'Resolved',
        Complaint.created_at >= cutoff,
        Complaint.latitude.isnot(None),
        Complaint.longitude.isnot(None),
    ).all()
    for c in candidates:
        try:
            d = haversine_m(lat_f, lon_f, float(c.latitude), float(c.longitude))
        except (TypeError, ValueError):
            continue
        if d <= radius_m:
            return c
    return None



def write_audit(action, target=None, detail=None):
    """Write an entry to the immutable AuditLog."""
    try:
        entry = AuditLog(
            user_id=session.get('user_id'),
            username=session.get('username', 'anonymous'),
            role=session.get('role', 'unknown'),
            action=fit_length(action, 100),
            target=fit_length(target, 100),
            detail=detail,
            ip_address=fit_length(request.remote_addr, 50),
            timestamp=utcnow()
        )
        db.session.add(entry)
        db.session.commit()
    except Exception as e:
        logger.error("audit_log_write_error", error=str(e))


def _record_offline_delivery(endpoint, ward=None, has_photo=False, complaint_id=None, illegal_report_id=None):
    """Log a submission that arrived via the PWA offline queue (if tagged).

    The client sends `X-Offline-Replay: 1` (plus X-Offline-Attempts) when it
    replays a queued IndexedDB submission, so the municipality can see
    offline-first usage: which complaints/photos arrived after connectivity
    returned instead of via a live form post. Best-effort, never raises — a
    delivery log write must never break the submission it records.

    NOTE: the marker is a self-reported analytics counter, NOT a trust
    boundary — any client can forge it. That's fine here: it only feeds the
    admin delivery-health dashboard, grants no access, and the endpoints it
    guards (/report, /report-illegal) are already login/rate-limited.
    """
    if request.headers.get('X-Offline-Replay') != '1':
        return
    try:
        attempts = request.headers.get('X-Offline-Attempts')
        db.session.add(OfflineDelivery(
            endpoint=fit_length(endpoint, 100),
            complaint_id=complaint_id,
            illegal_report_id=illegal_report_id,
            ward=fit_length(ward, 100),
            has_photo=has_photo,
            attempts=int(attempts) if attempts and attempts.isdigit() else 0,
            user_id=session.get('user_id'),
            delivered_at=utcnow()
        ))
        db.session.commit()
        logger.info("offline_delivery_recorded", endpoint=endpoint, has_photo=has_photo)
    except Exception as e:
        db.session.rollback()
        logger.error("offline_delivery_record_error", error=str(e))

def evaluate_emergency_metrics(smart_bin):
    """Detect fire/methane hazards and queue the IncidentLog row.

    Does NOT commit — the caller owns the transaction so telemetry writes once
    per request instead of evaluate() self-committing. Returns the hazard tuple
    (itype, severity, details) or None so the caller can dispatch webhooks
    AFTER the commit (guaranteeing the incident is persisted first)."""
    hazard = False
    details = ""
    itype = ""
    severity = "Warning"
    if smart_bin.temperature > 65.0:
        hazard = True; itype = "Fire Hazard"; severity = "Critical"
        details = f"Extreme temperature ({smart_bin.temperature}°C) at {smart_bin.hardware_id} in {smart_bin.ward}."
    elif smart_bin.methane > 500.0:
        hazard = True; itype = "Methane Leak"; severity = "Critical"
        details = f"Hazardous methane ({smart_bin.methane} ppm) at {smart_bin.hardware_id} in {smart_bin.ward}."
    if hazard:
        incident = IncidentLog(bin_id=smart_bin.id, incident_type=itype, severity=severity,
                               status="Active", description=details, timestamp=utcnow())
        db.session.add(incident)
        return itype, severity, details
    return None


def _reload_webhooks():
    """No-op: webhooks are now queried directly from the DB on every dispatch."""
    pass


def _dispatch_webhooks(event, payload):
    """Fire an event to every registered webhook URL (best-effort, never raises).

    Runs in the RQ background queue (inline fallback when Redis is absent) so a
    slow webhook receiver can never stall the telemetry ingest path."""
    from ..jobs import enqueue, dispatch_webhooks_job
    try:
        urls = [w.url for w in Webhook.query.order_by(Webhook.id).all()]
    except Exception:
        urls = []
    enqueue(dispatch_webhooks_job, urls, event, payload)

def activate_compactor(smart_bin):
    """Trigger solar-powered mechanical compactor for bin (no commit — caller commits)."""
    smart_bin.last_compacted_at = utcnow()
    smart_bin.level = max(0, int(smart_bin.level * 0.7))
    write_audit("PRE_COMPACTION", target=smart_bin.hardware_id,
                detail=f"Compactor activated at 70%+ fill, level reduced to {smart_bin.level}%")

def check_sensor_faults():
    """Auto-flag bins that haven't pinged in 24h as Sensor Fault."""
    threshold = datetime.now(timezone.utc) - timedelta(hours=24)
    bins = SmartBin.query.all()
    for b in bins:
        last = b.last_updated
        if last is None:
            # Never reported telemetry — treat as perpetually stale (fault)
            last = datetime.min.replace(tzinfo=timezone.utc)
        elif last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        if last < threshold and not b.sensor_fault:
            b.sensor_fault = True
            # Create / update SensorHealth record
            sh = SensorHealth.query.filter_by(bin_id=b.id).first()
            if sh:
                sh.fault_flag = True
                sh.fault_reason = f"No telemetry received for >24h. Last ping: {b.last_updated}"
                sh.maintenance_scheduled = True
            else:
                sh = SensorHealth(bin_id=b.id, fault_flag=True,
                                  fault_reason=f"No telemetry for >24h. Last ping: {b.last_updated}",
                                  maintenance_scheduled=True)
                db.session.add(sh)
            # Log incident
            existing = IncidentLog.query.filter_by(bin_id=b.id, incident_type="Sensor Fault", status="Active").first()
            if not existing:
                db.session.add(IncidentLog(bin_id=b.id, incident_type="Sensor Fault", severity="Warning",
                                           status="Active",
                                           description=f"Sensor Fault: {b.hardware_id} silent >24h. Maintenance scheduled."))
    db.session.commit()

def check_decomposition_timers():
    """Override ultrasonic status → 'Pending Clearance' (🟡 Yellow) for any bin
    that has stayed above 10% fill for more than 48h without being cleared."""
    threshold = datetime.now(timezone.utc) - timedelta(hours=48)
    bins = SmartBin.query.filter(SmartBin.level > 10).all()
    for b in bins:
        if b.decomposition_started_at is None:
            # Timer hasn't started (level just crossed 10%) — seed it now
            b.decomposition_started_at = utcnow()
            continue
        started = b.decomposition_started_at
        if started.tzinfo is None:
            started = started.replace(tzinfo=timezone.utc)
        if started < threshold and b.status != "Pending Clearance":
            b.status = "Pending Clearance"
            existing = IncidentLog.query.filter_by(
                bin_id=b.id, incident_type="Decomposition Timeout", status="Active").first()
            if not existing:
                db.session.add(IncidentLog(
                    bin_id=b.id, incident_type="Decomposition Timeout", severity="Warning",
                    status="Active",
                    description=f"{b.hardware_id} stagnant >48h above 10% fill. Forced 🟡 Pending Clearance."))
    db.session.commit()

# ──────────────────────────────────────────────
# ACCESS DECORATORS  (see app/auth.py for shared impl)
# ──────────────────────────────────────────────
from ..auth import login_required, admin_required, worker_required, superadmin_required, roles_required


# ═══════════════════════════════════════════════════════════════════
# SECTION 1 — HOME / WEATHER
# ═══════════════════════════════════════════════════════════════════

# ═══════════════════════════════════════════════════════════════════
# SECTION 2 — AUTHENTICATION
# ═══════════════════════════════════════════════════════════════════








# ═══════════════════════════════════════════════════════════════════
# SECTION 2a — PASSWORD RESET
# ═══════════════════════════════════════════════════════════════════
def send_reset_email(user_email, user_id):
    """Generate a password-reset token and send it via SMTP or flask-mailman."""
    serializer = URLSafeTimedSerializer(current_app.config['SECRET_KEY'])
    token = serializer.dumps(str(user_id), salt='password-reset-salt')
    reset_url = url_for('main.reset_password', token=token, _external=True)
    subject = 'SmartGarbage — Password Reset Request'
    body = f'Click the link below to reset your password (valid for 30 minutes):\n\n{reset_url}\n\nIf you did not request this, ignore this email.'
    if send_email_via_smtp(user_email, subject, body):
        return True
    try:
        from flask_mailman import Message
        msg = Message(subject, recipients=[user_email], body=body)
        mail.send(msg)
        return True
    except Exception as e:
        logger.error("mail_send_error", error=str(e))
        return False






# ═══════════════════════════════════════════════════════════════════
# SECTION 3 — CITIZEN DASHBOARD
# ═══════════════════════════════════════════════════════════════════
def _is_local_request():
    host = request.host.split(':')[0] if ':' in request.host else request.host
    return host in ('127.0.0.1', 'localhost', '0.0.0.0')


def _send_otp_with_fallback(recipient, otp_val, subject='SmartGarbage OTP'):
    is_local = _is_local_request()
    if is_local:
        flash(f"Dev OTP (localhost): {otp_val}", "success")
        return
    # Gateway send runs in the RQ background queue (inline fallback without Redis)
    # so the login request never blocks on Twilio/SMTP.
    from ..jobs import enqueue, send_otp_job
    enqueue(send_otp_job, recipient, otp_val, subject)
    flash("MFA required. Enter the OTP sent to your registered contact.", "success")



# Citizen Green-Points leaderboard (ward-scoped, privacy-conscious:
# usernames only, never phone numbers). Powers the dashboard "Eco Champions" card.

# ══════════════════════════════════════════════════════════════════
# PAYT / Razorpay-UPI payment endpoint (client-side button triggers this)
# ════════════════════════════════════════════════




# Citizen real-time notifications (SSE push for complaint status changes)




def _notify_status_change(complaint):
    """Deliver a complaint status update out-of-band (WhatsApp/SMS, email fallback).

    In-app Notification rows are created by the caller; this only handles the
    external channel. Sends are best-effort and never raise: a missing phone or
    unconfigured gateways just logs and returns. Localhost requests skip the
    send entirely (dev shouldn't hit real numbers). The actual gateway call
    runs in the RQ background queue (inline fallback without Redis) so resolving
    a complaint never blocks on Twilio/SMTP.
    """
    if _is_local_request():
        return
    user = User.query.get(complaint.user_id) if complaint.user_id else None
    phone = (user.phone if user else None) or complaint.phone
    email = user.email if user else None
    from ..jobs import enqueue, notify_status_change_job
    enqueue(notify_status_change_job, complaint.id, phone, email,
            complaint.ward or 'your area', complaint.status)


# 4-Stream Waste Segregation Declaration

# PAYT Invoice List API

# ═══════════════════════════════════════════════════════════════════
# SECTION 4 — ANONYMOUS ILLEGAL DUMP REPORT
# ═══════════════════════════════════════════════════════════════════

# ──────────────────────────────────────────────
# OMNICHANNEL HELPERS (WhatsApp / Telegram bot)
# ──────────────────────────────────────────────
def _extract_gps_from_exif(img):
    """Return (lat, lon) decimal degrees read from a PIL image's EXIF GPS tags."""
    try:
        from PIL.ExifTags import GPSTAGS, TAGS
        exif = img._getexif()
        if not exif:
            return None
        gps = {}
        for tag, val in exif.items():
            if TAGS.get(tag) == 'GPSInfo':
                for t, v in val.items():
                    gps[GPSTAGS.get(t, t)] = v
        if 'GPSLatitude' not in gps or 'GPSLongitude' not in gps:
            return None
        def _to_deg(value):
            d, m, s = value
            return float(d) + float(m) / 60.0 + float(s) / 3600.0
        lat = _to_deg(gps['GPSLatitude'])
        lon = _to_deg(gps['GPSLongitude'])
        if gps.get('GPSLatitudeRef') == 'S':
            lat = -lat
        if gps.get('GPSLongitudeRef') == 'W':
            lon = -lon
        return lat, lon
    except Exception as e:
        logger.error("gps_exif_parse_error", error=str(e))
        return None

def _download_illegal_media(media_url, auth=None):
    """Download a remote image, extract native GPS from EXIF, strip EXIF, and
    save it. Returns (relative_upload_path_or_None, (lat,lon)_or_None)."""
    try:
        resp = requests.get(media_url, auth=auth, timeout=10)
        if resp.status_code != 200:
            return None, None
        from PIL import Image
        import io
        img = Image.open(io.BytesIO(resp.content))
        gps = _extract_gps_from_exif(img)
        clean = io.BytesIO()
        img.save(clean, format=img.format or 'JPEG')
        clean.seek(0)
        filename = f"illegal_{random.randint(10000,99999)}.jpg"
        path = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
        with open(path, 'wb') as f:
            f.write(clean.read())
        return f"uploads/{filename}", gps
    except Exception as e:
        logger.error("media_download_error", error=str(e))
        return None, None

# ──────────────────────────────────────────────
# WEBHOOK VERIFICATION (Twilio / Telegram)
# These endpoints are publicly reachable, so they must reject forged requests.
# Enforcement is strict when credentials are configured; when unset (local
# dev, no credentials) the check is skipped so the sandbox keeps working.
# ──────────────────────────────────────────────
def _verify_twilio_signature():
    """Validate X-Twilio-Signature per Twilio's spec: HMAC-SHA1 over the full
    request URL + sorted POST params, keyed by TWILIO_AUTH_TOKEN."""
    token = os.environ.get('TWILIO_AUTH_TOKEN')
    if not token:
        return True  # no credentials configured (dev sandbox) — skip
    provided = request.headers.get('X-Twilio-Signature', '')
    url = request.url
    params = ''.join(f'{k}{v}' for k, v in sorted(request.form.items()))
    expected = base64.b64encode(hmac.new(token.encode(), (url + params).encode(), hashlib.sha1).digest()).decode()
    return hmac.compare_digest(provided, expected)


def _verify_telegram_secret():
    """Validate the X-Telegram-Bot-Api-Secret-Token header (set at webhook
    registration via setWebhook?secret_token=...)."""
    secret = os.environ.get('TELEGRAM_BOT_SECRET')
    if not secret:
        return True  # not configured — skip
    provided = request.headers.get('X-Telegram-Bot-Api-Secret-Token', '')
    return hmac.compare_digest(provided, secret)


# ──────────────────────────────────────────────
# RAZORPAY PAYMENT INTEGRATION (server-side orders + webhook capture)
# The confirm button used to trust the citizen's word. Now the flow is:
#   1. Server creates an order via the Razorpay Orders API (no SDK — raw
#      requests + HMAC, matching the Twilio gateway pattern).
#   2. The Razorpay Checkout UI collects payment against that order.
#   3. The success handler posts the payment signature back; we verify it
#      here with the key secret before marking the invoice paid.
#   4. The /webhook/razorpay endpoint independently confirms the capture via
#      the webhook secret — belt and braces, idempotent on both sides.
# ──────────────────────────────────────────────
def _razorpay_enabled():
    """True when Razorpay keys are configured (production checkout available)."""
    return bool(os.environ.get('RAZORPAY_KEY_ID') and os.environ.get('RAZORPAY_KEY_SECRET'))


def _create_razorpay_order(invoice):
    """Create a server-side Razorpay order for a PAYT invoice.

    Amount is passed in paise (Razorpay's unit). Returns the order id on
    success, or None on any failure — callers fall back to the UPI deep-link.
    Never raises: a checkout outage must not block the citizen from paying.
    """
    key_id = os.environ.get('RAZORPAY_KEY_ID')
    key_secret = os.environ.get('RAZORPAY_KEY_SECRET')
    if not key_id or not key_secret:
        return None
    try:
        amount_paise = int(round(invoice.amount_rs * 100))
        resp = requests.post(
            'https://api.razorpay.com/v1/orders',
            json={
                'amount': amount_paise,
                'currency': 'INR',
                'receipt': f'PAYT-{invoice.id}',
                'notes': {'invoice_id': str(invoice.id), 'app': 'smartgarbage'},
            },
            auth=(key_id, key_secret),
            timeout=8,
        )
        resp.raise_for_status()
        return resp.json().get('id')
    except Exception as e:
        logger.error("razorpay_order_create_error", error=str(e))
        return None


def _create_razorpay_refund(invoice, reason=''):
    """Reverse a captured Razorpay payment via the Refunds API.

    POSTs to /v1/payments/{payment_id}/refund (the payment id is stored on the
    invoice as transaction_ref when the capture webhook lands). Amount is
    passed in paise, exactly like the order helper. Returns the refund id on
    success, None on any failure — never raises. Idempotency lives in the
    caller: it must not call this twice for the same invoice (refund_id
    column is the guard), and Razorpay itself rejects duplicate full refunds
    of the same payment.
    """
    key_id = os.environ.get('RAZORPAY_KEY_ID')
    key_secret = os.environ.get('RAZORPAY_KEY_SECRET')
    payment_id = (invoice.transaction_ref or '').strip()
    if not key_id or not key_secret or not payment_id:
        return None
    try:
        amount_paise = int(round(invoice.amount_rs * 100))
        resp = requests.post(
            f'https://api.razorpay.com/v1/payments/{payment_id}/refund',
            json={
                'amount': amount_paise,
                'notes': {'invoice_id': str(invoice.id),
                          'reason': (reason or '')[:200],
                          'app': 'smartgarbage'},
            },
            auth=(key_id, key_secret),
            timeout=8,
        )
        resp.raise_for_status()
        return resp.json().get('id')
    except Exception as e:
        logger.error("razorpay_refund_error", invoice_id=invoice.id, error=str(e))
        return None


def _verify_razorpay_payment_signature(order_id, payment_id, signature):
    """Verify the Checkout-handler signature: HMAC-SHA256 of 'order_id|payment_id'
    keyed by the API key secret, hex-encoded (Razorpay's documented scheme)."""
    key_secret = os.environ.get('RAZORPAY_KEY_SECRET')
    if not key_secret or not signature:
        return False
    expected = hmac.new(
        key_secret.encode(), f'{order_id}|{payment_id}'.encode(), hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


def _verify_razorpay_webhook_signature():
    """Validate X-Razorpay-Signature per Razorpay's spec: HMAC-SHA256 over the
    RAW request body, keyed by RAZORPAY_WEBHOOK_SECRET (same discipline as the
    Twilio verifier above — the header is the trust boundary for public hooks)."""
    secret = os.environ.get('RAZORPAY_WEBHOOK_SECRET')
    if not secret:
        return True  # no credentials configured (dev sandbox) — skip
    provided = request.headers.get('X-Razorpay-Signature', '')
    raw = request.get_data(cache=True)
    expected = hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    return hmac.compare_digest(provided, expected)





# ═══════════════════════════════════════════════════════════════════
# SECTION 4b — DEV SANDBOX: simulate WhatsApp / Telegram bots in-browser
# (no real Twilio/Telegram account needed — drives the public webhooks)
# ═══════════════════════════════════════════════════════════════════


# ═══════════════════════════════════════════════════════════════════
# SECTION 5 — BWG COMMERCIAL LEDGER
# ═══════════════════════════════════════════════════════════════════

# ═══════════════════════════════════════════════════════════════════
# SECTION 6 — SCHEDULE
# ═══════════════════════════════════════════════════════════════════

# ═══════════════════════════════════════════════════════════════════
# SECTION 7 — COMPLAINT REPORTING
# ═══════════════════════════════════════════════════════════════════

# ═════════════════════════════════════════════════════════════════
# SECTION 8b — WARD COMMITTEE / GRAM SABHA TRANSPARENCY VIEW
# (Read-only, no login — civic accountability per waste-governance norms)
# ═════════════════════════════════════════════════════════════════

# ═════════════════════════════════════════════════════════════════
# SECTION 8 — ADMIN CONSOLE
# ═════════════════════════════════════════════════════════════════

# ──────────────────────────────────────────────
# OVERFLOW FORECAST (ML fill-rate) — proactive dispatch
# SmartBin.overflow_eta_hours is written by predict_overflow_eta_hours() on
# every telemetry ping (see bin_telemetry) and reused here so the route
# optimizer and the forecast API never re-compute from scratch.
# ──────────────────────────────────────────────
FORECAST_URGENT_HOURS = 24   # bins forecast to overflow within a day
FORECAST_ALERT_HOURS = 6     # cross this threshold -> dispatch alert once


def _forecast_priority(b):
    """Ranking key for critical-bin selection: smallest ETA first, then
    highest current fill. Bins with no forecast fall back to their level."""
    eta = b.overflow_eta_hours
    if eta is None:
        # No forecast yet — rank by fill so they still get picked up.
        return (1e9, -float(b.level))
    return (float(eta), -float(b.level))


# Route Optimizer — nearest-neighbour seeding + 2-opt refinement (networkx)
# over a distance matrix (OSRM road distance when reachable, else Haversine).
# Criticality now combines the classic 80% fill trigger with the ML forecast:
# bins forecast to overflow within FORECAST_URGENT_HOURS are included even if
# their current level hasn't hit 80% yet (proactive dispatch).







# Webhook configuration

# Complaint resolution

# Manually trigger the PAYT dunning run (overdue-invoice reminders).
# Enqueues dunning_job into RQ (inline fallback without Redis).

# ──────────────────────────────────────────────
# FAILED-JOBS DASHBOARD (RQ dead-letter queue)
# ──────────────────────────────────────────────








# Admin approves BWG pickup request

# ═══════════════════════════════════════════════════════════════════
# SECTION 9 — AUDIT TRAIL (Super-Admin)
# ═══════════════════════════════════════════════════════════════════

# ──────────────────────────────────────────────
# SECTION 9b — SUPER-ADMIN CONSOLE
# (Only reachable via @superadmin_required — the sanctioned way to
#  create admin accounts now that public self-registration is citizen/worker only)
# ──────────────────────────────────────────────

# ═══════════════════════════════════════════════════════════════════
# SECTION 10 — OTA FIRMWARE HUB
# ═══════════════════════════════════════════════════════════════════



# ═══════════════════════════════════════════════════════════════════
# SECTION 11 — SANITATION WORKER PORTAL
# ═══════════════════════════════════════════════════════════════════

# Mark bin as cleared (worker duty — not citizen-accessible, which previously
# let any logged-in user reset bins, resolve ward complaints and farm points)

# Toggle Solar-Powered Mechanical Pre-Compaction per bin

# Smart-bin telemetry for the admin GIS map (loaded client-side via fetch so the
# template stays free of server-injected Jinja inside the <script> block)

# Digital Manifest: Offload Checkpoint

# Worker issue reporter

# ═══════════════════════════════════════════════════════════════════
# SECTION 11.5 — IoT BIN TELEMETRY INGESTION
# ═══════════════════════════════════════════════════════════════════
def _recompute_bin_status(level):
    """Derive Safe / Warning / Critical status from fill level."""
    if level >= 80:
        return "Critical"
    if level >= 50:
        return "Warning"
    return "Safe"


# ═══════════════════════════════════════════════════════════════════
# SECTION 12 — ANALYTICS & COMPLIANCE
# ═══════════════════════════════════════════════════════════════════
def _compute_analytics():
    """Aggregate all analytics metrics. Shared by the page and the JSON API so
    no server data has to be embedded inside the template's <script>.

    All aggregates run in SQL (COALESCE over SUM) instead of pulling every
    WasteDeclaration row into Python — the previous full-table scan would OOM
    the 1 GB Fly VM once declarations grow to tens of thousands of rows."""
    from sqlalchemy import func
    bins = SmartBin.query.all()
    row = db.session.query(
        func.coalesce(func.sum(WasteDeclaration.wet_kg), 0.0),
        func.coalesce(func.sum(WasteDeclaration.dry_kg), 0.0),
        func.coalesce(func.sum(WasteDeclaration.sanitary_kg), 0.0),
        func.coalesce(func.sum(WasteDeclaration.hazardous_kg), 0.0),
    ).one()
    total_wet, total_dry, total_sanitary, total_hazardous = (float(v) for v in row)
    total_declared = total_wet + total_dry + total_sanitary + total_hazardous
    recycled = total_dry + total_hazardous
    landfill = total_wet + total_sanitary
    recycling_rate = round((recycled / total_declared * 100) if total_declared > 0 else 42.0, 1)

    traditional_km_monthly = 45.0 * 22  # 22 working days
    optimized_km_monthly = traditional_km_monthly * 0.78
    co2_saved_monthly_kg = round((traditional_km_monthly - optimized_km_monthly) * 0.21, 1)
    co2_saved_tonnes = round(co2_saved_monthly_kg / 1000, 3)

    generation_trends = {
        "labels": ["06:00", "09:00", "12:00", "15:00", "18:00", "21:00"],
        "organic": [12, 25, 18, 30, 45, 22],
        "plastic": [8, 14, 25, 20, 35, 15],
        "metal": [3, 7, 10, 5, 12, 8]
    }
    circular_economy = {
        "recycled_kg": round(recycled, 1),
        "landfill_kg": round(landfill, 1),
        "recycling_rate": recycling_rate,
        "wet_kg": round(total_wet, 1),
        "dry_kg": round(total_dry, 1),
        "sanitary_kg": round(total_sanitary, 1),
        "hazardous_kg": round(total_hazardous, 1),
    }
    carbon_data = {
        "traditional_km": traditional_km_monthly,
        "optimized_km": round(optimized_km_monthly, 1),
        "co2_saved_kg": co2_saved_monthly_kg,
        "co2_saved_tonnes": co2_saved_tonnes,
        "trees_equivalent": round(co2_saved_tonnes * 45, 1),
    }
    bins_json = [{"lat": b.latitude, "lon": b.longitude, "level": b.level} for b in bins]
    return {
        "circular": circular_economy,
        "carbon": carbon_data,
        "bins": bins_json,
        "trends": generation_trends,
    }



# State-Portal Compliance Export (SWM Rules 2026 mandated indicators)
def _state_portal_indicators():
    """SWM Rules 2026 compliance indicators (SQL aggregates — no full-table loads)."""
    from datetime import timedelta as _td
    from sqlalchemy import func
    period_start = utcnow() - _td(days=30)
    totals = db.session.query(
        func.coalesce(func.sum(WasteDeclaration.wet_kg + WasteDeclaration.dry_kg +
                               WasteDeclaration.sanitary_kg + WasteDeclaration.hazardous_kg), 0.0),
        func.coalesce(func.sum(WasteDeclaration.wet_kg + WasteDeclaration.dry_kg), 0.0),
    ).filter(WasteDeclaration.timestamp >= period_start).one()
    total_w = float(totals[0]) or 1
    seg_w = float(totals[1])
    return {
        "ulb_name": "Chintalavalasa Gram Panchayat",
        "report_period": period_start.strftime("%Y-%m-%d") + " to " + datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "total_waste_kg_30d": round(total_w, 1),
        "segregated_kg_30d": round(seg_w, 1),
        "segregation_coverage_pct": round((seg_w / total_w) * 100, 1),
        "total_complaints": Complaint.query.count(),
        "resolved_complaints": Complaint.query.filter(Complaint.status == 'Resolved').count(),
        "active_smart_bins": SmartBin.query.count(),
        "bins_above_80pct": SmartBin.query.filter(SmartBin.level >= 80).count(),
        "bulk_waste_generators": BWGDeclaration.query.count(),
        "informal_waste_pickers_registered": WorkerProfile.query.filter_by(is_informal_picker=True).count(),
        "workers_with_insurance": WorkerProfile.query.filter_by(insurance_enrolled=True).count(),
    }



# Trend-over-time analytics: monthly segregation % per ward

# ESG/CSRD Compliance Export data endpoint (data for client-side jsPDF)
def _csrd_payload():
    """ESG/CSRD compliance payload (row caps keep the response bounded as the
    tables grow — old behaviour serialised every row of every table)."""
    all_declarations = WasteDeclaration.query.order_by(WasteDeclaration.id.desc()).limit(500).all()
    all_offloads = OffloadLog.query.order_by(OffloadLog.id.desc()).limit(500).all()
    all_audits = AuditLog.query.order_by(AuditLog.timestamp.desc()).limit(100).all()
    return {
        "report_title": "SmartGarbage ESG/CSRD Compliance Report",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "municipality": "Chintalavalasa, Vizianagaram",
        "waste_declarations": [{
            "id": d.id, "wet_kg": d.wet_kg, "dry_kg": d.dry_kg,
            "sanitary_kg": d.sanitary_kg, "hazardous_kg": d.hazardous_kg,
            "ward": d.ward, "timestamp": d.timestamp.isoformat()
        } for d in all_declarations],
        "offload_logs": [{
            "id": o.id, "dump_yard": o.dump_yard_id, "weight_kg": o.weight_kg,
            "verified": o.verified, "impurity_flagged": o.impurity_flagged,
            "timestamp": o.timestamp.isoformat()
        } for o in all_offloads],
        "audit_trail_sample": [{
            "username": a.username, "action": a.action, "target": a.target,
            "timestamp": a.timestamp.isoformat()
        } for a in all_audits]
    }



def _performance_pdf_bytes():
    """Build the admin performance PDF; returns (pdf_bytes, filename)."""
    from io import BytesIO
    from reportlab.lib.pagesizes import letter
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet
    d = _compute_analytics()
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter)
    story = []
    styles = getSampleStyleSheet()
    story.append(Paragraph("SmartGarbage Performance Report", styles['Title']))
    story.append(Spacer(1, 12))
    data = [
        ["Metric", "Value"],
        ["Total Bins", str(len(SmartBin.query.all()))],
        ["Recycling Rate", f"{d['circular']['recycling_rate']}%"],
        ["CO2 Saved (kg)", str(d['carbon']['co2_saved_kg'])],
        ["Optimized Distance (km)", str(d['carbon']['optimized_km'])],
        ["Traditional Distance (km)", str(d['carbon']['traditional_km'])],
    ]
    t = Table(data, hAlign='LEFT')
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.darkgreen),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 12),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
    ]))
    story.append(t)
    doc.build(story)
    buf.seek(0)
    return buf.getvalue(), 'SmartGarbage_Performance_Report.pdf'


def _payt_receipt_pdf_bytes(invoice):
    """Build a PAYT payment receipt PDF; returns (pdf_bytes, filename).

    Rendered for a citizen after their Razorpay payment is captured: shows the
    invoice period, the paid amount, the Razorpay payment id (transaction_ref)
    and the municipality's branding so the citizen has a downloadable record
    for reconciliation. Best-effort — a reportlab failure raises to the caller,
    who decides whether the payment flow should surface it."""
    from io import BytesIO
    from reportlab.lib.pagesizes import letter
    from reportlab.lib import colors
    from reportlab.platypus import (SimpleDocTemplate, Table, TableStyle,
                                    Paragraph, Spacer)
    from reportlab.lib.styles import getSampleStyleSheet

    def _fmt(dt):
        if dt is None:
            return '—'
        if dt.tzinfo is not None:
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt.strftime('%d %b %Y, %I:%M %p')

    user = invoice.user
    citizen_name = user.username if user else f"Citizen #{invoice.user_id}"
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter,
                            rightMargin=54, leftMargin=54, topMargin=54, bottomMargin=54)
    styles = getSampleStyleSheet()
    story = []
    story.append(Paragraph("SmartGarbage Municipal Services", styles['Title']))
    story.append(Paragraph(
        "Chintalavalasa Gram Panchayat · Vizianagaram · Pay-As-You-Throw",
        styles['Italic']))
    story.append(Spacer(1, 6))
    story.append(Paragraph(
        f"<b>Payment Receipt</b> — Invoice #{invoice.id}", styles['Heading2']))
    story.append(Paragraph(
        f"Issued: {_fmt(invoice.paid_at or invoice.issued_at)}", styles['Normal']))
    story.append(Spacer(1, 14))

    data = [
        ["Detail", "Value"],
        ["Citizen", citizen_name],
        ["Billing Period", invoice.period or '—'],
        ["Weight Billed", f"{invoice.weight_kg:.1f} kg"],
        ["Segregation Compliance", f"{invoice.compliance_score:.0f}%"],
        # Standard reportlab fonts encode WinAnsi only — the rupee glyph (U+20B9)
        # has no WinAnsi codepoint and would render as a black box, so amounts
        # use the 'Rs.' convention (matching the audit logs) in the PDF.
        ["Penalty Multiplier", f"{invoice.penalty_multiplier:.2f}x"],
        ["Base Amount", f"Rs.{invoice.base_amount_rs:.2f}"],
        ["Amount Paid", f"Rs.{invoice.amount_rs:.2f}"],
        ["Payment Method", (invoice.payment_method or 'Razorpay').title()],
        ["Razorpay Payment ID", invoice.transaction_ref or '—'],
        ["Paid At", _fmt(invoice.paid_at)],
    ]
    t = Table(data, colWidths=[160, 330], hAlign='LEFT')
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.darkgreen),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 11),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.beige]),
        ('GRID', (0, 0), (-1, -1), 0.6, colors.grey),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 10),
    ]))
    story.append(t)
    story.append(Spacer(1, 20))
    story.append(Paragraph(
        "Thank you for contributing to a cleaner Chintalavalasa.", styles['Normal']))
    # reportlab 5.x dropped the 'Small' sample style — clone Normal and shrink.
    _small = styles['Normal'].clone('ReceiptSmall')
    _small.fontSize = 8
    _small.textColor = colors.grey
    story.append(Paragraph(
        "This is a computer-generated receipt and does not require a signature.",
        _small))
    doc.build(story)
    buf.seek(0)
    filename = f"PAYT_Receipt_Invoice_{invoice.id}.pdf"
    return buf.getvalue(), filename




# ═══════════════════════════════════════════════════════════════════
# ASYNC EXPORT GENERATION (RQ background queue)
# The heavy PDF/CSV/JSON export builds run in the job queue so admin requests
# never block on reportlab / large-table serialisation. When REDIS_URL is
# unset (local dev / pytest) enqueue() runs the job inline, so the
# request → status → result flow works identically without a broker.
# ═══════════════════════════════════════════════════════════════════





# ═══════════════════════════════════════════════════════════════════
# SECTION 13 — PWA STATIC ROUTES
# ═══════════════════════════════════════════════════════════════════



# Offline fallback page (served by the service worker when navigation fails).


# Privacy policy (public, no login) — GDPR/SWM transparency requirement.


# Deep health check endpoint for deployment orchestrators.






# ═══════════════════════════════════════════════════════════════════
# OPTIONAL REDIS CACHE (used for KPI / leaderboard data when configured)
# Pooled client — creating a fresh redis.Redis per call (previous behaviour)
# churns TCP connections on every cache hit; build the client once lazily.
# ═══════════════════════════════════════════════════════════════════
_redis_client_instance = None


def _redis_client():
    global _redis_client_instance
    if _redis_client_instance is None:
        try:
            import redis
            url = os.environ.get('REDIS_URL')
            if not url:
                return None
            _redis_client_instance = redis.Redis.from_url(url, socket_timeout=2,
                                                          decode_responses=False)
        except Exception:
            return None
    return _redis_client_instance


def cache_get(key):
    r = _redis_client()
    if not r:
        return None
    try:
        value = r.get(key)
        if value:
            return json.loads(value)
    except Exception:
        pass
    return None


def cache_set(key, value, ttl_seconds=60):
    r = _redis_client()
    if not r:
        return
    try:
        r.set(key, json.dumps(value), ex=ttl_seconds)
    except Exception:
        pass


# ═══════════════════════════════════════════════════════════════════
# SMS / EMAIL GATEWAY INTEGRATION HELPERS
# Keep current simulated fallback when real credentials are absent.
# ═══════════════════════════════════════════════════════════════════
def send_sms_via_twilio(to_number, body):
    """Send an SMS (or WhatsApp, if TWILIO_WHATSAPP_NUMBER is set) via Twilio.

    The WhatsApp sender number is configured with a `whatsapp:` prefix (e.g.
    `whatsapp:+14155238886`); Twilio requires the recipient to carry the same
    prefix for WhatsApp conversations, so we mirror it onto the To address.
    """
    sid = os.environ.get('TWILIO_ACCOUNT_SID')
    auth = os.environ.get('TWILIO_AUTH_TOKEN')
    sender = os.environ.get('TWILIO_WHATSAPP_NUMBER') or os.environ.get('TWILIO_FROM_NUMBER')
    if not sid or not auth or not sender:
        return False
    try:
        url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json"
        if sender.startswith('whatsapp:'):
            # Twilio requires both From and To to be prefixed for WhatsApp.
            to_number = to_number if to_number.startswith('whatsapp:') else f"whatsapp:{to_number}"
        data = {
            'To': to_number,
            'From': sender,
            'Body': body,
        }
        requests.post(url, data=data, auth=(sid, auth), timeout=5)
        return True
    except Exception as e:
        logger.error("twilio_sms_error", error=str(e))
        return False


def send_email_via_smtp(to_email, subject, body, attachment_bytes=None, attachment_filename=None):
    """Send an email via SMTP, optionally with a binary attachment (e.g. PDF).

    Mirrors the plain-text path when no attachment is given; when
    attachment_bytes is provided the message becomes multipart/mixed with the
    body as text and the attachment as application/octet-stream. Returns True
    on success, False when SMTP is unconfigured or the send fails."""
    host = os.environ.get('MAIL_SERVER')
    port = int(os.environ.get('MAIL_PORT', 25))
    use_tls = os.environ.get('MAIL_USE_TLS', 'false').lower() in ('true', '1', 'yes')
    username = os.environ.get('MAIL_USERNAME')
    password = os.environ.get('MAIL_PASSWORD')
    sender = os.environ.get('MAIL_DEFAULT_SENDER')
    if not host or not username or not password:
        return False
    try:
        import smtplib
        from email.mime.multipart import MIMEMultipart
        from email.mime.text import MIMEText
        from email.mime.application import MIMEApplication
        if attachment_bytes is not None:
            msg = MIMEMultipart()
            msg.attach(MIMEText(body))
            part = MIMEApplication(attachment_bytes, _subtype='octet-stream')
            part.add_header('Content-Disposition', 'attachment',
                            filename=attachment_filename or 'attachment.bin')
            msg.attach(part)
        else:
            msg = MIMEText(body)
        msg['Subject'] = subject
        msg['From'] = sender or username
        msg['To'] = to_email
        with smtplib.SMTP(host, port, timeout=5) as server:
            if use_tls:
                server.starttls()
            server.login(username, password)
            server.sendmail(msg['From'], [msg['To']], msg.as_string())
        return True
    except Exception as e:
        logger.error("smtp_email_error", error=str(e))
        return False

# ═══════════════════════════════════════════════════════════════════
# ROUTE REGISTRATION — submodules attach their handlers to `main`.
# (imported last: they only need names defined above)
# ═══════════════════════════════════════════════════════════════════
from . import auth, citizen, admin, worker, iot, webhook, analytics, public

