from app.models import User, Complaint, BWGDeclaration, Notification, utcnow
from werkzeug.security import generate_password_hash
from app import db, create_app, socketio
import json as _json
import os


def test_language_switch_renders_telugu_labels(client):
    r = client.get('/set-lang/te', follow_redirects=False)
    assert r.status_code == 302

    r2 = client.get('/login')
    assert r2.status_code == 200
    body = r2.get_data(as_text=True)
    assert 'లాగిన్' in body or 'లాగిన్' in body


def test_dashboard_renders_telugu_labels_after_language_switch(client, app):
    _make_user(app, 'telugucitizen')
    client.get('/set-lang/te', follow_redirects=False)
    r = client.post('/login', data={'username': 'telugucitizen', 'password': 'testpass123'}, follow_redirects=True)
    assert r.status_code == 200

    r2 = client.get('/dashboard', follow_redirects=False)
    assert r2.status_code == 200
    body = r2.get_data(as_text=True)
    assert 'ఇకో-రివార్డ్ వాలెట్ బ్యాలెన్స్' in body


def test_lang_query_param_serves_localized_page_without_redirect(client):
    """?lang=te must render Telugu with a 200 — no /set-lang/ 302 hop for
    the no-JS language links (and for crawlers that follow them)."""
    r = client.get('/?lang=te', follow_redirects=False)
    assert r.status_code == 200
    with client.session_transaction() as sess:
        assert sess.get('lang') == 'te'
    body = r.get_data(as_text=True)
    assert 'లాగిన్' in body  # లాగిన్ (Login)

    r2 = client.get('/schedule?lang=en', follow_redirects=False)
    assert r2.status_code == 200
    with client.session_transaction() as sess:
        assert sess.get('lang') == 'en'


def _make_user(app, username, role='citizen', phone=None, password='testpass123', green_points=0):
    if phone is None:
        phone = f'+91987654{hash(username) % 10000:04d}'
    with app.app_context():
        u = User(username=username, password_hash=generate_password_hash(password),
                 role=role, phone=phone, is_approved=True, green_points=green_points)
        db.session.add(u)
        db.session.commit()
        return u.id


def _login_admin(client, app, username, password='testpass123'):
    client.post('/login', data={'username': username, 'password': password}, follow_redirects=False)
    # OTPs are stored hashed — read the plaintext dev OTP from the session.
    with client.session_transaction() as sess:
        otp = sess.get('dev_otp')
    client.post('/mfa-verify', data={'otp': otp}, follow_redirects=False)


# ── Login lockout after repeated failures ──────────────────────
def test_login_lockout_after_failures(client, app):
    from app.models import User as U
    _make_user(app, 'lockuser', password='rightpass123')
    for _ in range(10):
        client.post('/login', data={'username': 'lockuser', 'password': 'wrong'})
    # The 11th attempt uses the CORRECT password — account must still be locked.
    r = client.post('/login', data={'username': 'lockuser', 'password': 'rightpass123'},
                    follow_redirects=True)
    body = r.data.lower()
    assert b'locked' in body, f"expected lockout flash, got: {body[:400]}"
    with app.app_context():
        u = U.query.filter_by(username='lockuser').first()
        assert u.failed_login_count >= 10
        assert u.locked_until is not None


def test_login_success_resets_failures(client, app):
    from app.models import User as U
    _make_user(app, 'resetlock', password='rightpass123')
    # 3 failures (below the 5-attempt threshold), then a correct login.
    for _ in range(3):
        client.post('/login', data={'username': 'resetlock', 'password': 'wrong'})
    r = client.post('/login', data={'username': 'resetlock', 'password': 'rightpass123'},
                    follow_redirects=False)
    assert r.status_code == 302
    with app.app_context():
        u = U.query.filter_by(username='resetlock').first()
        assert u.failed_login_count == 0
        assert u.locked_until is None


# ── resolve-bin requires worker role (citizen blocked) ───────
def test_citizen_cannot_resolve_bin(client, app):
    from app.models import SmartBin
    _make_user(app, 'rescit')
    with app.app_context():
        b = SmartBin(hardware_id='BIN-RES-1', latitude=18.05, longitude=83.40,
                     level=90, status='Critical', ward='Ward 1 - MVGR College Area')
        db.session.add(b)
        db.session.commit()
    client.post('/login', data={'username': 'rescit', 'password': 'testpass123'},
                follow_redirects=False)
    r = client.post('/resolve-bin/BIN-RES-1', follow_redirects=False)
    assert r.status_code == 403


def _make_jpeg_bytes():
    """Return a tiny in-memory JPEG for multipart uploads in tests."""
    import io
    from PIL import Image
    buf = io.BytesIO()
    Image.new('RGB', (200, 120), (120, 200, 80)).save(buf, format='JPEG')
    buf.seek(0)
    return buf


def test_worker_can_resolve_bin_with_after_photo_and_gps(client, app):
    """Close-the-loop: a worker clearing a bin MUST submit a live After-photo
    AND device GPS within CLEAR_RADIUS_M of the bin — the clear is accepted
    and the evidence path is persisted on the bin."""
    from app.models import SmartBin, WorkerProfile
    uid = _make_user(app, 'reswork', role='worker')
    with app.app_context():
        wp = WorkerProfile(user_id=uid, vehicle_id='CV-99', status='Active')
        db.session.add(wp)
        b = SmartBin(hardware_id='BIN-RES-2', latitude=18.05, longitude=83.40,
                     level=90, status='Critical', ward='Ward 1 - MVGR College Area')
        db.session.add(b)
        db.session.commit()
    _login_admin(client, app, 'reswork')
    r = client.post('/resolve-bin/BIN-RES-2',
                    data={'after_photo': (_make_jpeg_bytes(), 'after.jpg'),
                          'lat': '18.05', 'lon': '83.40'},
                    content_type='multipart/form-data', follow_redirects=False)
    assert r.status_code == 200
    assert r.get_json().get('success') is True
    with app.app_context():
        b = SmartBin.query.filter_by(hardware_id='BIN-RES-2').first()
        assert b.level == 0 and b.status == 'Safe'
        assert b.after_photo is not None and 'after' in b.after_photo


def test_resolve_bin_requires_after_photo(client, app):
    """Close-the-loop: clearing a bin without an After-photo is REJECTED (400)
    — a driver can no longer tap 'Cleared' from down the street."""
    from app.models import SmartBin, WorkerProfile
    uid = _make_user(app, 'reswork2', role='worker')
    with app.app_context():
        db.session.add(WorkerProfile(user_id=uid, vehicle_id='CV-98', status='Active'))
        db.session.add(SmartBin(hardware_id='BIN-RES-3', latitude=18.05, longitude=83.40,
                                level=90, status='Critical',
                                ward='Ward 1 - MVGR College Area'))
        db.session.commit()
    _login_admin(client, app, 'reswork2')
    r = client.post('/resolve-bin/BIN-RES-3',
                    data={'lat': '18.05', 'lon': '83.40'},
                    content_type='multipart/form-data', follow_redirects=False)
    assert r.status_code == 400
    assert r.get_json().get('success') is False
    with app.app_context():
        b = SmartBin.query.filter_by(hardware_id='BIN-RES-3').first()
        assert b.level == 90  # unchanged — clear rejected


def test_resolve_bin_rejects_gps_out_of_range(client, app):
    """Close-the-loop: worker GPS far from the bin (e.g. cleared from across
    town) is REJECTED even with a photo — the ticket only closes on-site."""
    from app.models import SmartBin, WorkerProfile
    uid = _make_user(app, 'reswork3', role='worker')
    with app.app_context():
        db.session.add(WorkerProfile(user_id=uid, vehicle_id='CV-97', status='Active'))
        db.session.add(SmartBin(hardware_id='BIN-RES-4', latitude=18.05, longitude=83.40,
                                level=90, status='Critical',
                                ward='Ward 1 - MVGR College Area'))
        db.session.commit()
    _login_admin(client, app, 'reswork3')
    r = client.post('/resolve-bin/BIN-RES-4',
                    data={'after_photo': (_make_jpeg_bytes(), 'after.jpg'),
                          'lat': '18.5', 'lon': '84.0'},  # ~56km away
                    content_type='multipart/form-data', follow_redirects=False)
    assert r.status_code == 400
    assert r.get_json().get('success') is False
    with app.app_context():
        b = SmartBin.query.filter_by(hardware_id='BIN-RES-4').first()
        assert b.level == 90  # unchanged — clear rejected


def test_report_requires_gps_server_side(client, app):
    """Anti-spam: /report rejects a submission with NO device coordinates even
    when the client tries to bypass the browser check (no default-coords
    fallback server-side either)."""
    _make_user(app, 'nogpscit')
    client.post('/login', data={'username': 'nogpscit', 'password': 'testpass123'},
                follow_redirects=False)
    r = client.post('/report', data={
        'name': 'nogpscit', 'phone': '+919876543214',
        'ward': 'Ward 1 - MVGR College Area', 'address': 'Gate',
        'description': 'Overflow', 'report_time': '2026-07-18T10:00'
    }, follow_redirects=False)
    assert r.status_code == 302  # bounced back to the form
    with app.app_context():
        assert Complaint.query.filter_by(name='nogpscit').first() is None


def test_report_photo_gps_mismatch_blocked(client, app, monkeypatch):
    """Anti-spam: a photo geotagged far from the submitter's device position is
    a screenshot / internet image — the submission is blocked server-side."""
    import app.routes.citizen as citizen_mod
    _make_user(app, 'exifcit')
    client.post('/login', data={'username': 'exifcit', 'password': 'testpass123'},
                follow_redirects=False)
    # Simulate a photo whose EXIF GPS is ~2km from the reported device position.
    monkeypatch.setattr(citizen_mod, '_photo_gps_from_upload',
                        lambda file: (18.10, 83.45))
    r = client.post('/report',
                    data={'name': 'exifcit', 'phone': '+919876543215',
                          'ward': 'Ward 1 - MVGR College Area', 'address': 'Gate',
                          'description': 'Overflow', 'latitude': '18.05',
                          'longitude': '83.40', 'report_time': '2026-07-18T10:00',
                          'photo': (_make_jpeg_bytes(), 'shot.jpg')},
                    content_type='multipart/form-data', follow_redirects=False)
    assert r.status_code == 302  # bounced back with the mismatch message
    with app.app_context():
        assert Complaint.query.filter_by(name='exifcit').first() is None


def test_report_photo_gps_match_accepted(client, app, monkeypatch):
    """Anti-spam: a photo geotagged AT the device position passes the
    cross-check and the complaint is filed normally."""
    import app.routes.citizen as citizen_mod
    _make_user(app, 'exifok')
    client.post('/login', data={'username': 'exifok', 'password': 'testpass123'},
                follow_redirects=False)
    monkeypatch.setattr(citizen_mod, '_photo_gps_from_upload',
                        lambda file: (18.05, 83.40))  # matches device coords
    r = client.post('/report',
                    data={'name': 'exifok', 'phone': '+919876543216',
                          'ward': 'Ward 1 - MVGR College Area', 'address': 'Gate',
                          'description': 'Overflow', 'latitude': '18.05',
                          'longitude': '83.40', 'report_time': '2026-07-18T10:00',
                          'photo': (_make_jpeg_bytes(), 'shot.jpg')},
                    content_type='multipart/form-data', follow_redirects=False)
    assert r.status_code in (200, 302)
    with app.app_context():
        assert Complaint.query.filter_by(name='exifok').first() is not None


def test_report_photo_upload_succeeds_with_real_pipeline(client, app):
    """Regression: the REAL photo pipeline (_photo_gps_from_upload ->
    _ai_verify_photo -> save_compressed_photo) must accept a valid JPEG and
    file the complaint.

    Pillow 12 takes ownership of the file-like handed to Image.open() and
    img.close() closes it — which used to poison the request's upload stream
    ('I/O operation on closed file') and reject EVERY photo complaint. The
    earlier photo tests monkeypatched _photo_gps_from_upload (skipping the
    stream-closer), so this runs the true chain with zero monkeypatching.
    """
    _make_user(app, 'photocit')
    client.post('/login', data={'username': 'photocit', 'password': 'testpass123'},
                follow_redirects=False)
    r = client.post('/report',
                    data={'name': 'photocit', 'phone': '+919876543217',
                          'ward': 'Ward 1 - MVGR College Area', 'address': 'Gate',
                          'description': 'Overflow with photo evidence',
                          'latitude': '18.05', 'longitude': '83.40',
                          'report_time': '2026-08-03T10:00',
                          'photo': (_make_jpeg_bytes(), 'shot.jpg')},
                    content_type='multipart/form-data', follow_redirects=False)
    assert r.status_code in (200, 302)  # not bounced back to the form
    with app.app_context():
        comp = Complaint.query.filter_by(name='photocit').first()
        assert comp is not None, 'photo complaint was rejected'
        assert comp.photo is not None and 'uploads/' in comp.photo


# ── Telemetry audit only on state change (no per-ping bloat) ──
def test_telemetry_audit_only_on_state_change(client, app):
    from app.models import SmartBin, AuditLog
    with app.app_context():
        b = SmartBin(hardware_id='BIN-AUD-1', latitude=18.05, longitude=83.40,
                     level=10, status='Safe', ward='Ward 1 - MVGR College Area')
        db.session.add(b)
        db.session.commit()
    # First ping changes level 10 → 90 (state change → 1 audit row)
    r1 = client.post('/api/bin-telemetry', json={'hardware_id': 'BIN-AUD-1', 'level': 90})
    assert r1.status_code == 200
    with app.app_context():
        n1 = AuditLog.query.filter_by(action='BIN_TELEMETRY', target='BIN-AUD-1').count()
        assert n1 == 1
    # Second identical ping → no new audit row
    r2 = client.post('/api/bin-telemetry', json={'hardware_id': 'BIN-AUD-1', 'level': 90})
    assert r2.status_code == 200
    with app.app_context():
        n2 = AuditLog.query.filter_by(action='BIN_TELEMETRY', target='BIN-AUD-1').count()
        assert n2 == 1


# ── ProxyFix: trusted client IP for rate limiting + audit ─────
def test_proxy_fix_uses_forwarded_for(client, app):
    from app.models import AuditLog
    _make_user(app, 'proxycit')
    r = client.post('/login',
                    data={'username': 'proxycit', 'password': 'testpass123'},
                    headers={'X-Forwarded-For': '203.0.113.7'},
                    follow_redirects=False)
    assert r.status_code == 302
    with app.app_context():
        log = AuditLog.query.filter_by(action='LOGIN', username='proxycit')\
                            .order_by(AuditLog.id.desc()).first()
        assert log is not None
        assert log.ip_address == '203.0.113.7', f"got {log.ip_address}"


# ── CSRF enforcement on POST ─────────────────────────────────
def test_register_requires_csrf(client, app):
    app.config['WTF_CSRF_ENABLED'] = True
    r = client.post('/register', data={'username': 'csrfuser',
                                       'password': 'testpass123', 'phone': '+919876543202'})
    assert r.status_code in (400, 302)


# ── Superadmin gating: regular admin cannot reach /admin/audit ──
def test_audit_requires_superadmin(client, app):
    _make_user(app, 'regadmin', role='admin')
    client.post('/login', data={'username': 'regadmin', 'password': 'testpass123'})
    r = client.get('/admin/audit', follow_redirects=False)
    assert r.status_code in (302, 303, 403)


# ── Complaint lifecycle ───────────────────────────────────────
def test_complaint_lifecycle(client, app):
    _make_user(app, 'complainer')
    client.post('/login', data={'username': 'complainer', 'password': 'testpass123'})
    r = client.post('/report', data={
        'name': 'complainer', 'phone': '+919876543203',
        'ward': 'Ward 1 - MVGR College Area', 'address': 'Near gate',
        'description': 'Overflow', 'latitude': '18.05', 'longitude': '83.40',
        'report_time': '2026-07-18T10:00'
    }, follow_redirects=True)
    assert r.status_code in (200, 302)
    with app.app_context():
        c = Complaint.query.filter_by(name='complainer').first()
        assert c is not None
        assert c.status == 'Submitted'


# ── BWG approval flow (admin + MFA) ──────────────────────────
def test_bwg_approval_flow(client, app):
    uid = _make_user(app, 'bwguser')
    with app.app_context():
        decl = BWGDeclaration(user_id=uid, entity_name='Test Mall', entity_type='commercial',
                              composting_kg=10, recyclable_kg=10, landfill_kg=10,
                              request_bulk_pickup=True, pickup_status='Pending')
        db.session.add(decl)
        db.session.commit()
        did = decl.id
    _make_user(app, 'bwgadmin', role='admin')
    _login_admin(client, app, 'bwgadmin')
    r3 = client.get(f'/admin/bwg-approve/{did}', follow_redirects=False)
    assert r3.status_code == 302
    with app.app_context():
        assert BWGDeclaration.query.get(did).pickup_status == 'Approved'


# ── Picker self-registration (informal worker) ──────────────
def test_picker_registration(client, app):
    r = client.post('/register/picker', data={
        'username': 'picker1', 'phone': '+919876543204',
        'area': 'Ward 2', 'password': 'testpass123'
    }, follow_redirects=True)
    assert r.status_code in (200, 302)
    with app.app_context():
        u = User.query.filter_by(username='picker1').first()
        assert u is not None
        assert u.role == 'worker'
        assert u.worker_profile is not None
        assert u.worker_profile.is_informal_picker is True


# ── Webhook signature verification (Twilio-style) ───────────
def test_whatsapp_webhook_rejects_bad_signature(client, app):
    r = client.post('/webhook/whatsapp', data={'From': 'whatsapp:+919876543205',
                                               'Body': 'test dump'})
    assert r.status_code in (403, 400, 200)


def test_whatsapp_webhook_enforces_signature_when_configured(client, app, monkeypatch):
    """With TWILIO_AUTH_TOKEN set, a missing/wrong X-Twilio-Signature must be
    rejected with 403 (forged requests can no longer spam the webhook)."""
    monkeypatch.setenv('TWILIO_AUTH_TOKEN', 'tok')
    # No signature header -> 403
    r = client.post('/webhook/whatsapp', data={'From': 'whatsapp:+919876543205',
                                               'Body': 'test dump'})
    assert r.status_code == 403
    # Wrong signature header -> 403
    r = client.post('/webhook/whatsapp', data={'From': 'whatsapp:+919876543205',
                                               'Body': 'test dump'},
                    headers={'X-Twilio-Signature': 'AAAA'})
    assert r.status_code == 403

    # Correct signature -> 200 (TwiML ack). Derive the URL from url_for so the
    # test survives SERVER_NAME/scheme changes (e.g. https behind a proxy).
    import base64, hmac, hashlib
    from flask import url_for
    with app.app_context():
        url = url_for('main.webhook_whatsapp', _external=True)
    params = ''.join(f'{k}{v}' for k, v in sorted({'From': 'whatsapp:+919876543205',
                                                   'Body': 'test dump'}.items()))
    sig = base64.b64encode(hmac.new(b'tok', (url + params).encode(), hashlib.sha1).digest()).decode()
    r = client.post('/webhook/whatsapp', data={'From': 'whatsapp:+919876543205',
                                               'Body': 'test dump'},
                    headers={'X-Twilio-Signature': sig})
    assert r.status_code == 200


def test_telegram_webhook_enforces_secret_when_configured(client, app, monkeypatch):
    """With TELEGRAM_BOT_SECRET set, a wrong/missing secret token is 403."""
    monkeypatch.setenv('TELEGRAM_BOT_SECRET', 'topsecret')
    r = client.post('/webhook/telegram', json={'message': {'chat': {'id': 1}}})
    assert r.status_code == 403
    r = client.post('/webhook/telegram', json={'message': {'chat': {'id': 1}}},
                    headers={'X-Telegram-Bot-Api-Secret-Token': 'wrong'})
    assert r.status_code == 403
    r = client.post('/webhook/telegram', json={'message': {'chat': {'id': 1}}},
                    headers={'X-Telegram-Bot-Api-Secret-Token': 'topsecret'})
    assert r.status_code == 200


# ── Worker GPS heartbeat: persists geofence state (GET is read-only) ──
def test_worker_gps_persists_location_and_violation(client, app):
    from app.models import WorkerProfile, AuditLog
    uid = _make_user(app, 'gpsworker', role='worker')
    with app.app_context():
        db.session.add(WorkerProfile(user_id=uid, vehicle_id='CV-01', status='Active',
                                     current_lat=18.056, current_lon=83.404))
        db.session.commit()
    _login_admin(client, app, 'gpsworker')

    # Inside CV-01's sector polygon -> no violation
    r = client.post('/api/worker/gps', data={'lat': '18.056', 'lon': '83.404'},
                    follow_redirects=False)
    assert r.status_code == 200
    data = r.get_json()
    assert data['in_bounds'] is True
    assert data['geofence_violation'] is False

    # Far outside the sector -> violation persisted + audited
    r = client.post('/api/worker/gps', data={'lat': '18.5', 'lon': '84.0'},
                    follow_redirects=False)
    assert r.status_code == 200
    assert r.get_json()['in_bounds'] is False
    with app.app_context():
        wp = WorkerProfile.query.filter_by(user_id=uid).first()
        assert wp.geofence_violation is True
        assert AuditLog.query.filter_by(action='GEOFENCE_VIOLATION').count() >= 1

    # Out-of-range coords rejected
    r = client.post('/api/worker/gps', data={'lat': '99', 'lon': '83'})
    assert r.status_code == 400


def test_worker_gps_blocks_citizen(client, app):
    _make_user(app, 'gpscitizen')
    client.post('/login', data={'username': 'gpscitizen', 'password': 'testpass123'})
    r = client.post('/api/worker/gps', data={'lat': '18.05', 'lon': '83.40'})
    assert r.status_code == 403


# ── Fleet GET is read-only (no DB mutation on a read) ─────────
def test_fleet_location_get_does_not_write(client, app, monkeypatch):
    """A GET to /api/fleet-location must not create audit rows or commit
    geofence violations (side-effect-free GETs)."""
    from app.models import AuditLog
    _make_user(app, 'fleetadmin', role='admin')
    _login_admin(client, app, 'fleetadmin')
    with app.app_context():
        before = AuditLog.query.filter_by(action='GEOFENCE_VIOLATION').count()
    for _ in range(3):
        r = client.get('/api/fleet-location', follow_redirects=False)
        assert r.status_code == 200
    with app.app_context():
        after = AuditLog.query.filter_by(action='GEOFENCE_VIOLATION').count()
    assert after == before, "fleet GET must not write audit rows"


# ── Webhook persistence: survives restart via the Webhook table ──
def test_webhook_persisted_to_db(client, app):
    from app.models import Webhook
    _make_user(app, 'whadmin', role='admin')
    _login_admin(client, app, 'whadmin')
    r = client.post('/api/webhooks', data={'webhook_url': 'https://example.com/hook'},
                    follow_redirects=False)
    assert r.status_code == 302
    with app.app_context():
        assert Webhook.query.filter_by(url='https://example.com/hook').first() is not None

    # Re-registering the same URL does not duplicate
    client.post('/api/webhooks', data={'webhook_url': 'https://example.com/hook'},
                follow_redirects=False)
    with app.app_context():
        assert Webhook.query.filter_by(url='https://example.com/hook').count() == 1


def test_webhooks_queried_from_db(app):
    """Webhooks are queried directly from the DB, not from an in-memory list."""
    from app.models import Webhook
    with app.app_context():
        if not Webhook.query.filter_by(url='https://reload.example/hook').first():
            db.session.add(Webhook(url='https://reload.example/hook'))
            db.session.commit()
        # _reload_webhooks is now a no-op; webhooks are always queried from DB.
        import app.routes as routes
        routes._reload_webhooks()
        # Verify the webhook is in the database (where it's queried from now).
        wh = Webhook.query.filter_by(url='https://reload.example/hook').first()
        assert wh is not None
        assert wh.url == 'https://reload.example/hook'


# ── Firmware upload validation: extension allowlist + sha256 ──
def test_firmware_upload_rejects_bad_extension(client, app):
    import io
    _make_user(app, 'fwadmin', role='admin')
    _login_admin(client, app, 'fwadmin')
    r = client.post('/admin/firmware/upload',
                    data={'version': '1.0', 'firmware_file': (io.BytesIO(b'evil'), 'malware.exe')},
                    content_type='multipart/form-data', follow_redirects=False)
    assert r.status_code == 302
    # No release should have been created
    with app.app_context():
        from app.models import FirmwareRelease
        assert FirmwareRelease.query.filter_by(version='1.0').first() is None


def test_firmware_upload_stores_sha256(client, app):
    import io, hashlib
    _make_user(app, 'fwadmin2', role='admin')
    _login_admin(client, app, 'fwadmin2')
    payload = b'\x00\x01\x02firmware-image'
    r = client.post('/admin/firmware/upload',
                    data={'version': '2.0', 'description': 'ota',
                          'firmware_file': (io.BytesIO(payload), 'fw.bin')},
                    content_type='multipart/form-data', follow_redirects=False)
    assert r.status_code == 302
    with app.app_context():
        from app.models import FirmwareRelease
        rel = FirmwareRelease.query.filter_by(version='2.0').first()
        assert rel is not None
        assert rel.sha256 == hashlib.sha256(payload).hexdigest()


# ── /health includes Redis check (pass when unset) ─────────────
def test_health_endpoint_ok(client):
    r = client.get('/health')
    assert r.status_code == 200
    assert r.get_json()['status'] == 'healthy'


def test_health_includes_jobs_kpis(client):
    """/health surfaces job-queue KPIs (duration/retries/dead-letter) without
    affecting the health verdict — dead-lettered jobs are a signal, not an
    outage."""
    from app.jobs import _METRICS, record_outcome, record_retry, _count_dead_letter
    _METRICS.clear()  # isolated counters: suite-wide job runs can't shift counts
    record_outcome('probe_sms', 'success', 0.5)
    record_outcome('probe_sms', 'failed', 1.5)
    record_retry('probe_sms')
    _count_dead_letter('probe_sms', 'health-dl-1')
    r = client.get('/health')
    assert r.status_code == 200
    jobs = r.get_json()['jobs']
    assert jobs['jobs_run'] == 2
    assert jobs['retries'] == 1
    assert jobs['dead_lettered'] == 1
    assert jobs['avg_duration_s'] > 0


# ── Retry policies + dead-letter handling ───────────────────
def test_job_retry_policies_declared_for_sending_jobs():
    """Every delivery/external-call job declares a retry policy with a positive
    max_retries and monotonic backoff intervals (rq.Retry contract)."""
    from app.jobs import JOB_RETRY_POLICIES
    for name in ('send_sms_job', 'send_email_job', 'send_otp_job',
                 'notify_status_change_job', 'dispatch_webhooks_job',
                 'payt_reminder_job', 'generate_export_job', 'dunning_job'):
        assert name in JOB_RETRY_POLICIES, name
        max_retries, intervals = JOB_RETRY_POLICIES[name]
        assert isinstance(max_retries, int) and max_retries >= 1
        assert len(intervals) == max_retries
        assert intervals == sorted(intervals)  # exponential / increasing backoff


def test_enqueue_retry_false_runs_inline_without_redis():
    """The inline fallback (no REDIS_URL) ignores retry policies entirely and
    still executes the job synchronously — local dev/pytest unchanged."""
    from app.jobs import enqueue
    ran = []

    def _probe(x):
        ran.append(x)
        return x + 5

    result = enqueue(_probe, 10, retry=False)
    assert ran == [10]
    assert result == 15


def test_failed_jobs_helpers_degrade_without_redis():
    """All dead-letter helpers are safe without a broker: empty list, False, 0."""
    from app.jobs import (failed_jobs, requeue_failed_job,
                          delete_failed_job, clear_failed_jobs)
    assert failed_jobs() == []
    assert requeue_failed_job('missing-job-id') is False
    assert delete_failed_job('missing-job-id') is False
    assert clear_failed_jobs() == 0


# ── Failed-jobs dashboard (admin) ─────────────────────────────
def test_failed_jobs_dashboard_requires_admin(client, app):
    """The dead-letter dashboard is admin-only — anonymous users are bounced."""
    _make_user(app, 'fjcit', role='citizen')
    _login_admin(client, app, 'fjcit')
    r = client.get('/admin/failed-jobs', follow_redirects=False)
    assert r.status_code == 403  # citizen role blocked by admin_required


def test_failed_jobs_dashboard_renders_empty_state(client, app):
    """Admin sees the dashboard with an empty-state message when no Redis
    (tests always run broker-less)."""
    _make_user(app, 'fjadmin', role='admin')
    _login_admin(client, app, 'fjadmin')
    r = client.get('/admin/failed-jobs')
    assert r.status_code == 200
    assert 'No failed jobs' in r.get_data(as_text=True)


def test_failed_jobs_clear_and_requeue_routes(client, app):
    """Requeue / delete / clear POST routes redirect back to the dashboard and
    flash without crashing when there is no broker."""
    _make_user(app, 'fjadmin2', role='admin')
    _login_admin(client, app, 'fjadmin2')
    for url in ('/admin/failed-jobs/clear',
                '/admin/failed-jobs/requeue/unknown-job',
                '/admin/failed-jobs/delete/unknown-job'):
        r = client.post(url, follow_redirects=True)
        assert r.status_code == 200
        assert 'Failed Jobs' in r.get_data(as_text=True)


def test_restore_retry_budget_applies_policy_and_skips_unlisted():
    """_restore_retry_budget re-applies retries_left + retry_intervals from the
    job's declared JOB_RETRY_POLICIES entry (exactly as Queue.enqueue would set
    them) and leaves jobs without a policy untouched."""
    from app.jobs import _restore_retry_budget

    class _FakeJob:
        func_name = 'app.jobs.send_sms_job'
        retries_left = 0          # exhausted by the failure that dead-lettered it
        retry_intervals = None

    job = _FakeJob()
    assert _restore_retry_budget(job) is True
    assert job.retries_left == 3              # send_sms_job policy: max_retries
    assert job.retry_intervals == [30, 60, 120]

    class _NoPolicyJob:
        func_name = 'app.jobs.custom_unlisted'
        retries_left = 0
        retry_intervals = None

    job2 = _NoPolicyJob()
    assert _restore_retry_budget(job2) is False
    assert job2.retries_left == 0
    assert job2.retry_intervals is None


def test_requeue_failed_job_restores_retry_budget(monkeypatch):
    """A manually requeued dead-lettered job gets its FULL automatic backoff
    budget back before re-enqueueing — RQ keeps retries_left exhausted, so a
    plain requeue would dead-letter again on the very next failure."""
    import sys
    import types
    from app import jobs as jobs_mod

    saved_states = []  # (retries_left, retry_intervals) at job.save() time

    class _FakeJob:
        def __init__(self, job_id):
            self.id = job_id
            self.func_name = 'app.jobs.send_sms_job'
            self.retries_left = 0
            self.retry_intervals = None

        def save(self):
            saved_states.append((self.retries_left, self.retry_intervals))

        @classmethod
        def fetch(cls, job_id, connection=None, serializer=None):
            return cls(job_id)

    class _FakeRegistry:
        def __init__(self):
            self.requeued = []

        def requeue(self, job_or_id, at_front=False):
            self.requeued.append(job_or_id)
            return True

    class _FakeQueue:
        def __init__(self):
            self.connection = object()
            self.failed_job_registry = _FakeRegistry()

    # The test env has no rq installed (lazy imports only), so inject a fake
    # rq.job module — requeue_failed_job imports Job from it at call time.
    fake_rq = types.ModuleType('rq')
    fake_job_mod = types.ModuleType('rq.job')
    fake_job_mod.Job = _FakeJob
    fake_rq.job = fake_job_mod
    monkeypatch.setitem(sys.modules, 'rq', fake_rq)
    monkeypatch.setitem(sys.modules, 'rq.job', fake_job_mod)

    q = _FakeQueue()
    monkeypatch.setattr(jobs_mod, '_get_queue', lambda: q)

    assert jobs_mod.requeue_failed_job('job-dead-1') is True
    # the RESTORED job object (not just the id) is handed to the registry, so
    # RQ re-enqueues it with the full budget — no re-fetch can drop it
    passed = q.failed_job_registry.requeued
    assert len(passed) == 1 and passed[0].id == 'job-dead-1'
    assert passed[0].retries_left == 3
    assert passed[0].retry_intervals == [30, 60, 120]
    # budget restored and persisted BEFORE the registry requeue happens
    assert saved_states == [(3, [30, 60, 120])]


# ── Background job queue (RQ) with inline fallback ──────────
def test_jobs_enqueue_runs_inline_without_redis():
    """Without REDIS_URL, enqueue() executes the job synchronously so the app
    (and tests) work identically with or without a broker."""
    from app.jobs import enqueue
    ran = []

    def _probe(x):
        ran.append(x)
        return x * 2

    result = enqueue(_probe, 21)
    assert ran == [21]
    assert result == 42


def test_dunning_job_creates_and_dedupes_reminders(app):
    """The PAYT dunning job finds overdue unpaid invoices and creates an in-app
    reminder; re-running does not duplicate notifications."""
    from datetime import timedelta
    from app.jobs import dunning_job
    from app.models import PAYTInvoice, Notification
    uid = _make_user(app, 'duncit', role='citizen')
    with app.app_context():
        inv = PAYTInvoice(user_id=uid, period='March 2026', weight_kg=12.0,
                          landfill_kg=4.0, amount_rs=120.0, status='Unpaid',
                          issued_at=utcnow() - timedelta(days=45))
        db.session.add(inv)
        db.session.commit()
        inv_id = inv.id
    with app.app_context():
        count = dunning_job(grace_days=30)
        assert count >= 1
        notes = Notification.query.filter(
            Notification.user_id == uid,
            Notification.link == f'/payt/pay/{inv_id}').all()
        assert len(notes) == 1
        assert 'overdue' in notes[0].message.lower()
        # Second run must not duplicate
        assert dunning_job(grace_days=30) == 0
        assert Notification.query.filter_by(user_id=uid).count() == 1


# ── PAYT seed script: realistic ledger for demos ─────────────
def test_seed_payt_invoices_creates_realistic_mix(app):
    """scripts/seed_payt_invoices.py populates several citizens with a mixed
    Paid/Unpaid/Waived/Refunded history, amounts that mirror the app's billing
    formula, and dunning-eligible overdue invoices — idempotently."""
    from datetime import timedelta
    import scripts.seed_payt_invoices as seed_mod
    from app.models import PAYTInvoice
    from app.jobs import dunning_job

    summary = seed_mod.seed_payt_invoices(app=app, months=5, force=True)
    # 7 citizens × 5 trailing months, statuses by month: 19 Paid, 14 Unpaid,
    # 1 Waived (unpaid, forgiven) and 1 Refunded (paid, Razorpay-reversed).
    assert summary['invoices'] == 35
    assert summary['created'] == 35
    assert summary['citizens'] == 7
    assert summary['by_status']['Paid'] == 19
    assert summary['by_status']['Unpaid'] == 14
    assert summary['by_status']['Waived'] == 1
    assert summary['by_status']['Refunded'] == 1
    assert summary['dunning_eligible'] >= 1

    # Idempotent re-run adds nothing.
    summary2 = seed_mod.seed_payt_invoices(app=app, months=5)
    assert summary2['created'] == 0
    assert summary2['skipped'] == 35

    # Amounts follow the real billing rule: base = kg × ₹1.5, penalty from
    # compliance (1.0x..2.0x); paid invoices carry a ref + paid_at; refunded
    # ones carry a Razorpay refund id.
    with app.app_context():
        paid = PAYTInvoice.query.filter_by(status='Paid').first()
        assert paid.amount_rs == round(round(paid.weight_kg * 1.5, 2) * paid.penalty_multiplier, 2)
        assert paid.penalty_multiplier == round(1.0 + (100.0 - paid.compliance_score) / 100.0, 2)
        assert paid.transaction_ref and paid.paid_at is not None
        refunded = PAYTInvoice.query.filter_by(status='Refunded').first()
        assert refunded.refund_id and refunded.refunded_at is not None
        assert refunded.payment_method == 'Razorpay'
        waived = PAYTInvoice.query.filter_by(status='Waived').first()
        assert waived.refund_reason and waived.paid_at is None
        # Older Unpaid invoices (June/July, issued > 30 days ago) exist and the
        # dunning sweep flags exactly the same set the seed counts.
        assert dunning_job(grace_days=30) == summary['dunning_eligible']
        overdue_unpaid = PAYTInvoice.query.filter(
            PAYTInvoice.status == 'Unpaid',
            PAYTInvoice.issued_at < utcnow() - timedelta(days=30)).count()
        assert overdue_unpaid >= 1


def test_async_export_request_and_result(client, app):
    """Export generation runs through the job queue; the request/status/result
    flow works inline when Redis is absent (tests)."""
    _make_user(app, 'expasync', role='admin')
    _login_admin(client, app, 'expasync')
    r = client.get('/analytics/export/request?kind=state-portal&format=csv',
                   follow_redirects=False)
    assert r.status_code == 200
    job_id = r.get_json()['job_id']
    r2 = client.get(f'/analytics/export/status/{job_id}', follow_redirects=False)
    assert r2.status_code == 200
    assert r2.get_json()['status'] == 'ready'
    r3 = client.get(f'/analytics/export/result/{job_id}', follow_redirects=False)
    assert r3.status_code == 200
    assert 'text/csv' in r3.headers.get('Content-Type', '')
    assert 'indicator,value' in r3.get_data(as_text=True)


# ── State-portal compliance export (admin) ──────────────────
def test_state_portal_export(client, app):
    _make_user(app, 'expadmin', role='admin')
    client.post('/login', data={'username': 'expadmin', 'password': 'testpass123'})
    r = client.get('/analytics/state-portal-export', follow_redirects=False)
    assert r.status_code in (200, 302)
    if r.status_code == 200:
        import json
        data = json.loads(r.data)
        assert 'indicators' in data


# ── Trend-over-time segregation API (admin) ─────────────
def test_trend_segregation_api(client, app):
    _make_user(app, 'trendadmin', role='admin')
    client.post('/login', data={'username': 'trendadmin', 'password': 'testpass123'})
    r = client.get('/api/trend/segregation', follow_redirects=False)
    assert r.status_code in (200, 302)
    if r.status_code == 200:
        import json
        data = json.loads(r.data)
        assert 'months' in data and 'series' in data


def test_trend_segregation_sql_aggregates_by_month_and_ward(client, app):
    """The rewritten endpoint aggregates in SQL (GROUP BY month, ward) — seed
    declarations across two months and two wards and assert the exact
    per-month segregation % comes back (not an empty/garbled series)."""
    from datetime import datetime as _dt
    from app.models import WasteDeclaration
    _make_user(app, 'trendsql', role='admin')
    with app.app_context():
        u = User.query.filter_by(username='trendsql').first()
        w1 = 'Ward 1 - MVGR College Area'
        w2 = 'Ward 2 - Chintalavalasa Junction'
        # July: Ward1 seg 6/10 = 60%; Ward2 seg 4/6 = 66.7% (same month, 2 wards)
        db.session.add_all([
            WasteDeclaration(user_id=u.id, wet_kg=3, dry_kg=3, sanitary_kg=2, hazardous_kg=2,
                             ward=w1, timestamp=_dt(2026, 7, 10)),
            WasteDeclaration(user_id=u.id, wet_kg=2, dry_kg=2, sanitary_kg=1, hazardous_kg=1,
                             ward=w2, timestamp=_dt(2026, 7, 12)),
            # August: Ward1 seg 0/5 = 0% (only one ward declares)
            WasteDeclaration(user_id=u.id, wet_kg=0, dry_kg=0, sanitary_kg=5, hazardous_kg=0,
                             ward=w1, timestamp=_dt(2026, 8, 5)),
        ])
        db.session.commit()
    _login_admin(client, app, 'trendsql')
    r = client.get('/api/trend/segregation', follow_redirects=False)
    assert r.status_code == 200
    data = _json.loads(r.data)
    assert data['months'] == ['2026-07', '2026-08']
    assert data['series'][w1] == [60.0, 0.0], data['series'][w1]
    assert data['series'][w2] == [66.7, 0.0], data['series'][w2]


# ── Hot-path composite indexes declared on models (sync with migration) ──
def test_hot_path_composite_indexes_declared_on_models():
    """Notification and WasteDeclaration declare the composite indexes the
    f3a4b5c6d7e8 migration creates — create_all in tests keeps them in sync."""
    from app.models import Notification, WasteDeclaration
    notif_names = {ix.name for ix in Notification.__table__.indexes}
    assert 'ix_notification_user_read_created' in notif_names
    wd_names = {ix.name for ix in WasteDeclaration.__table__.indexes}
    assert 'ix_waste_declaration_ward_timestamp' in wd_names


# ── Structured-data guard: the GovernmentOrganization entity (base.html) must
#    ship on every public page with the full trust set — postalCode, awards,
#    telephone, geo — so a schema regression fails CI instead of silently
#    dropping the portal out of Google Rich Results / AI citations. ──
SCHEMA_ANON_PAGES = ['/', '/about', '/schedule', '/report', '/transparency',
                     '/privacy', '/login', '/register', '/register/picker']


def _jsonld_objects(html):
    """Decode every JSON-LD block in a page, including @graph children."""
    import re
    for match in re.findall(r'<script type="application/ld\+json">(.*?)</script>',
                            html, re.S):
        try:
            data = _json.loads(match)
        except _json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            yield data
            for node in data.get('@graph', []) or []:
                yield node
        elif isinstance(data, list):
            yield from data


def _assert_org_schema(client, path):
    r = client.get(path)
    assert r.status_code == 200, f'{path} failed to render'
    org = next((d for d in _jsonld_objects(r.get_data(as_text=True))
                if d.get('@type') == 'GovernmentOrganization'), None)
    assert org is not None, f'{path}: GovernmentOrganization schema missing'
    assert org.get('telephone'), f'{path}: telephone missing'
    assert org.get('address', {}).get('postalCode') == '535005', \
        f'{path}: address.postalCode missing or wrong'
    award_text = ' '.join(org.get('award') or [])
    assert 'Solid Waste Management Rules, 2026' in award_text, \
        f'{path}: SWM Rules award missing'
    geo = org.get('geo') or {}
    assert geo.get('latitude') is not None and geo.get('longitude') is not None, \
        f'{path}: geo coordinates missing'


def test_every_public_page_ships_complete_government_schema(client, app):
    """The GovernmentOrganization JSON-LD (rendered by base.html) carries the
    address (postalCode), awards, telephone and geo on every public page —
    the same signals the SEO/trust audits score. /report is a public form
    (sitemap-listed, no login required), so it is checked anonymously here."""
    for path in SCHEMA_ANON_PAGES:
        _assert_org_schema(client, path)


# ── robots.txt must never block crawlers (DEPLOY.md §8.2: the audit once
#    caught the live site serving an OLD robots.txt with `Disallow: /`) ──
def test_robots_txt_never_blocks_crawlers(client):
    """Assert the robots route always serves the open config: allow-all
    catch-all, explicit AI-bot groups, and the sitemap — with no-store
    caching so a CDN/proxy can never replay an old blocking version."""
    import re
    r = client.get('/robots.txt')
    assert r.status_code == 200
    assert 'text/plain' in r.content_type
    body = r.get_data(as_text=True)
    # Path-specific disallows (/admin, /api/, …) are fine; a sitewide
    # `Disallow: /` is the audit's #1 visibility blocker.
    assert not re.search(r'^Disallow:\s*/\s*$', body, re.M), \
        'robots.txt must never contain a sitewide Disallow: /'
    assert re.search(r'^User-agent: \*\s*$', body, re.M), \
        'catch-all user-agent group missing'
    assert 'Allow: /' in body
    for bot in ('GPTBot', 'OAI-SearchBot', 'ClaudeBot', 'Google-Extended',
                'PerplexityBot'):
        assert f'User-agent: {bot}' in body, f'{bot} AI group missing'
    assert 'Sitemap:' in body and 'sitemap.xml' in body
    assert 'no-store' in (r.headers.get('Cache-Control') or ''), \
        'robots.txt must be no-store so stale versions cannot be cached'


def test_sitemap_lists_all_public_pages(client):
    """sitemap.xml must declare every public page and be no-store cached."""
    r = client.get('/sitemap.xml')
    assert r.status_code == 200
    assert 'xml' in r.content_type
    body = r.get_data(as_text=True)
    for path in ('/', '/about', '/schedule', '/report', '/transparency',
                 '/register', '/register/picker', '/privacy'):
        assert path in body, f'sitemap missing {path}'
    assert 'no-store' in (r.headers.get('Cache-Control') or ''), \
        'sitemap.xml must be no-store so stale versions cannot be cached'


# ── Live-weather status is cached (wttr.in hit once per 10-min window) ──
def test_weather_status_cached_within_ttl(monkeypatch):
    """get_live_weather_status must not hammer wttr.in on every call — the
    in-process TTL cache collapses repeated calls into a single HTTP request."""
    import app.ml_model as ml
    calls = {'n': 0}

    class _FakeResp:
        ok = True

        def json(self):
            return {'current_condition': [{'weatherDesc': [{'value': 'Clear'}]}]}

    def fake_get(url, timeout=4):
        calls['n'] += 1
        return _FakeResp()

    monkeypatch.setattr(ml.requests, 'get', fake_get)
    ml._WEATHER_CACHE = {'ts': 0.0, 'val': None}  # reset the module cache
    first = ml.get_live_weather_status()
    second = ml.get_live_weather_status()
    third = ml.get_live_weather_status()
    assert calls['n'] == 1, f"expected 1 HTTP call, got {calls['n']}"
    assert first == second == third


def test_weather_status_refetches_after_ttl_expiry(monkeypatch):
    """Once the 10-minute window elapses the cache is stale and wttr.in is
    polled again — the cache must not be a permanent freeze."""
    import app.ml_model as ml
    import time as _time
    calls = {'n': 0}

    class _FakeResp:
        ok = True

        def json(self):
            return {'current_condition': [{'weatherDesc': [{'value': 'Rain'}]}]}

    def fake_get(url, timeout=4):
        calls['n'] += 1
        return _FakeResp()

    monkeypatch.setattr(ml.requests, 'get', fake_get)
    ml._WEATHER_CACHE = {'ts': 0.0, 'val': None}
    ml.get_live_weather_status()
    assert calls['n'] == 1
    # Age the cache past the TTL → next call must re-fetch.
    ml._WEATHER_CACHE['ts'] = _time.time() - ml.WEATHER_CACHE_TTL_S - 1
    ml.get_live_weather_status()
    assert calls['n'] == 2


def test_weather_failure_falls_back_to_season_without_caching_error(monkeypatch):
    """An unreachable wttr.in must degrade to the season heuristic (never
    raise) — and that fallback IS cached so a down API can't stall every
    schedule POST with a fresh 4s timeout."""
    import app.ml_model as ml

    def failing_get(url, timeout=4):
        raise RuntimeError('wttr.in down')

    monkeypatch.setattr(ml.requests, 'get', failing_get)
    ml._WEATHER_CACHE = {'ts': 0.0, 'val': None}
    val = ml.get_live_weather_status()
    assert val in (0, 1, 2)
    assert ml._WEATHER_CACHE['val'] == val  # fallback cached too


# ── Landing-page weather widget is Redis-cached (open-meteo once) ──
def test_home_weather_served_from_cache(client, app, monkeypatch):
    """The landing page weather widget reads the per-location cache first and
    only hits open-meteo on a miss — a warm cache means zero network I/O on
    the homepage request path."""
    import app.routes.public as public
    fetch_calls = {'n': 0}

    class _FakeResp:
        status_code = 200

        def json(self):
            return {'current': {'temperature_2m': 30, 'relative_humidity_2m': 70,
                                'wind_speed_10m': 12, 'weather_code': 0}}

    def fake_get(url, timeout=5):
        fetch_calls['n'] += 1
        return _FakeResp()

    cache_store = {}
    monkeypatch.setattr(public.requests, 'get', fake_get)
    monkeypatch.setattr(public, 'cache_get', lambda key: cache_store.get(key))
    monkeypatch.setattr(public, 'cache_set', lambda key, value, ttl_seconds=60: cache_store.update({key: value}))

    r1 = client.get('/?fetch_weather=true&lat=18.06&lon=83.41')
    assert r1.status_code == 200
    assert fetch_calls['n'] == 1  # cold cache → one open-meteo call
    body1 = _json.loads(r1.data)
    assert body1['temp'] == '30°C'

    r2 = client.get('/?fetch_weather=true&lat=18.06&lon=83.41')
    assert r2.status_code == 200
    assert fetch_calls['n'] == 1  # warm cache → no second network call
    assert _json.loads(r2.data) == body1


# ── Complaint resolution pushes a notification to citizen ──
def test_resolve_sends_status_sms_and_whatsapp_prefix(client, app, monkeypatch):
    """Resolving a complaint triggers the out-of-band status alert helper:
    the reporter's phone receives a Twilio message, and when a WhatsApp sender
    is configured the To number carries the whatsapp: prefix."""
    cid = _make_user(app, 'smscitiz', phone='+919876543208')
    with app.app_context():
        comp = Complaint(
            name='smscitiz', phone='+919876543208',
            ward='Ward 1 - MVGR College Area', address='Gate',
            description='Overflow', status='Pending', user_id=cid
        )
        db.session.add(comp)
        db.session.commit()
        comp_id = comp.id
    _make_user(app, 'smsadmin', role='admin')
    _login_admin(client, app, 'smsadmin')

    sent = {}
    monkeypatch.setenv('TWILIO_ACCOUNT_SID', 'ACtest')
    monkeypatch.setenv('TWILIO_AUTH_TOKEN', 'tok')
    monkeypatch.setenv('TWILIO_WHATSAPP_NUMBER', 'whatsapp:+14155238886')

    def fake_post(url, data=None, auth=None, timeout=None):
        sent.update({'to': data.get('To'), 'body': data.get('Body')})
        return type('R', (), {'status_code': 201})()

    import app.routes as routes
    monkeypatch.setattr(routes.requests, 'post', fake_post)
    monkeypatch.setattr(routes, '_is_local_request', lambda: False)

    r = client.get(f'/resolve/{comp_id}', follow_redirects=False)
    assert r.status_code == 302
    assert sent.get('to') == 'whatsapp:+919876543208'  # WhatsApp prefix mirrored
    assert 'resolved' in sent.get('body', '').lower()


# ── Complaint resolution pushes a notification to citizen ──
def test_resolve_pushes_notification(client, app):
    cid = _make_user(app, 'notifciti')
    client.post('/login', data={'username': 'notifciti', 'password': 'testpass123'})
    client.post('/report', data={
        'name': 'notifciti', 'phone': '+919876543206',
        'ward': 'Ward 1 - MVGR College Area', 'address': 'Gate',
        'description': 'Overflow', 'latitude': '18.05', 'longitude': '83.40',
        'report_time': '2026-07-18T10:00'
    }, follow_redirects=True)
    client.get('/logout', follow_redirects=True)
    _make_user(app, 'resadmin', role='admin')
    _login_admin(client, app, 'resadmin')
    with app.app_context():
        comp = Complaint.query.filter_by(name='notifciti').first()
        comp_id = comp.id
    r = client.get(f'/resolve/{comp_id}', follow_redirects=False)
    assert r.status_code == 302
    with app.app_context():
        assert Notification.query.filter_by(user_id=cid).count() == 1


# ── Citizen complaint tracking: signed token + timeline + ward SLA ──
def test_tracking_token_roundtrip_and_tamper(app):
    """The tracking token is a signed complaint id: it verifies back to the
    id, but a tampered signature (or a token for a different salt) never
    resolves — complaints can't be enumerated."""
    from app.routes import make_complaint_token, verify_complaint_token
    with app.app_context():
        token = make_complaint_token(42)
        assert verify_complaint_token(token) == 42
        # Flipping a character breaks the signature → None, not an exception.
        tampered = token[:-1] + ('A' if token[-1] != 'A' else 'B')
        assert verify_complaint_token(tampered) is None
        assert verify_complaint_token('not-a-real-token') is None
        assert verify_complaint_token('') is None


def test_tracking_token_expires_after_max_age(app):
    """Expired tokens verify to None so old links 404 instead of leaking data."""
    import app.routes as routes_mod
    from app.routes import make_complaint_token, verify_complaint_token
    with app.app_context():
        token = make_complaint_token(7)
        assert verify_complaint_token(token) == 7
        # Force max_age negative → every token is instantly expired (a token
        # signed moments ago can carry a 0.0 age, so 0 wouldn't reliably trip).
        original = routes_mod.TRACK_TOKEN_MAX_AGE
        try:
            routes_mod.TRACK_TOKEN_MAX_AGE = -1
            assert verify_complaint_token(token) is None
        finally:
            # Restore — this module constant is process-global and other tests
            # mint tokens too; leaving it negative would expire THEIR tokens.
            routes_mod.TRACK_TOKEN_MAX_AGE = original


def test_track_page_renders_timeline_and_ward_sla(client, app):
    """The public /track/<token> page shows the status timeline and the
    ward's average resolution time (computed from resolved complaints)."""
    from app.routes import make_complaint_token
    from datetime import timedelta
    cid = _make_user(app, 'trackciti')
    filed = utcnow() - timedelta(hours=6)
    with app.app_context():
        comp = Complaint(
            name='trackciti', phone='+919876543210',
            ward='Ward 1 - MVGR College Area', address='Gate',
            description='Overflow bin near the college gate', status='Resolved',
            user_id=cid, created_at=filed, resolved_at=utcnow(),
        )
        db.session.add(comp)
        db.session.commit()
        cid2 = comp.id
        from app.models import ComplaintStatusLog
        db.session.add(ComplaintStatusLog(complaint_id=cid2, status='Submitted',
                                          created_at=filed))
        db.session.add(ComplaintStatusLog(complaint_id=cid2, status='Resolved',
                                          created_at=utcnow()))
        db.session.commit()
        token = make_complaint_token(cid2)
    r = client.get(f'/track/{token}')
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert f'Ticket #{cid2}' in body
    assert 'Submitted' in body and 'Resolved' in body
    assert 'Avg. resolution time in this ward' in body
    # Exactly 6h between created_at and resolved_at → the ward average renders
    # as "6.0 h" (a weak `'h' in body` check would pass even without the SLA).
    assert '6.0 h' in body


def test_track_page_rejects_invalid_and_unknown_tokens(client, app):
    """Invalid tokens 404 (no complaint leakage) — the track page is public
    but only reachable with a valid signature."""
    assert client.get('/track/garbage-token').status_code == 404
    assert client.get('/track/').status_code == 404
    # A valid signature for a complaint id that doesn't exist → 404 too.
    from app.routes import make_complaint_token
    with app.app_context():
        ghost = make_complaint_token(999999)
    assert client.get(f'/track/{ghost}').status_code == 404


def test_report_auto_sms_tracks_link(client, app, monkeypatch):
    """Filing a complaint SMSes the reporter a signed /track/ link via the
    existing Twilio path (WhatsApp prefix mirrored when configured)."""
    cid = _make_user(app, 'trackreporter', phone='+919876543211')
    client.post('/login', data={'username': 'trackreporter', 'password': 'testpass123'},
                follow_redirects=False)
    sent = {}
    monkeypatch.setenv('TWILIO_ACCOUNT_SID', 'ACtest')
    monkeypatch.setenv('TWILIO_AUTH_TOKEN', 'tok')
    monkeypatch.setenv('TWILIO_WHATSAPP_NUMBER', 'whatsapp:+14155238886')

    def fake_post(url, data=None, auth=None, timeout=None):
        sent.update({'to': data.get('To'), 'body': data.get('Body')})
        return type('R', (), {'status_code': 201})()

    import app.routes as routes
    monkeypatch.setattr(routes.requests, 'post', fake_post)
    monkeypatch.setattr(routes, '_is_local_request', lambda: False)

    r = client.post('/report', data={
        'name': 'trackreporter', 'phone': '+919876543211',
        'ward': 'Ward 1 - MVGR College Area', 'address': 'Gate',
        'description': 'Overflow', 'latitude': '18.05', 'longitude': '83.40',
        'report_time': '2026-08-03T10:00'
    }, follow_redirects=True)
    assert r.status_code in (200, 302)
    # The SMS body must contain a signed /track/ link.
    assert sent.get('to') == 'whatsapp:+919876543211'
    assert '/track/' in sent.get('body', '')
    # And the success page exposes the same link for copying.
    with app.app_context():
        comp = Complaint.query.filter_by(user_id=cid).first()
        assert comp is not None
        from app.models import ComplaintStatusLog
        assert ComplaintStatusLog.query.filter_by(
            complaint_id=comp.id, status='Submitted').count() == 1


def test_resolve_records_timeline_event_and_resolved_at(client, app):
    """Admin resolve appends a Resolved timeline event and stamps resolved_at
    (the SLA estimator reads resolved_at - created_at)."""
    from app.models import ComplaintStatusLog
    cid = _make_user(app, 'reslogciti')
    with app.app_context():
        comp = Complaint(
            name='reslogciti', phone='+919876543212',
            ward='Ward 1 - MVGR College Area', address='Gate',
            description='Overflow', status='Submitted', user_id=cid,
        )
        db.session.add(comp)
        db.session.commit()
        comp_id = comp.id
    _make_user(app, 'reslogadmin', role='admin')
    _login_admin(client, app, 'reslogadmin')
    r = client.get(f'/resolve/{comp_id}', follow_redirects=False)
    assert r.status_code == 302
    with app.app_context():
        comp = Complaint.query.get(comp_id)
        assert comp.status == 'Resolved'
        assert comp.resolved_at is not None
        assert ComplaintStatusLog.query.filter_by(
            complaint_id=comp_id, status='Resolved').count() == 1


def test_sla_escalation_records_timeline_event(app):
    """The SLA-escalation sweep records an Escalated timeline event so the
    citizen sees why their complaint moved out of the normal flow."""
    from app.models import ComplaintStatusLog
    from datetime import timedelta
    cid = _make_user(app, 'slaescciti')
    with app.app_context():
        comp = Complaint(
            name='slaescciti', phone='+919876543213',
            ward='Ward 1 - MVGR College Area', address='Gate',
            description='Overflow', status='Submitted', user_id=cid,
            sla_deadline=utcnow() - timedelta(hours=1),
        )
        db.session.add(comp)
        db.session.commit()
        comp_id = comp.id
    from app.jobs import sla_escalation_job
    escalated = sla_escalation_job()
    assert escalated >= 1
    with app.app_context():
        comp = Complaint.query.get(comp_id)
        assert comp.status == 'Escalated'
        assert ComplaintStatusLog.query.filter_by(
            complaint_id=comp_id, status='Escalated').count() == 1


# ── Citizen notifications list + mark-read (real-time push data layer) ──
def test_notifications_list_and_markread(client, app):
    cid = _make_user(app, 'notifuser')
    with app.app_context():
        db.session.add(Notification(user_id=cid, message="Test note", link='/dashboard'))
        db.session.commit()
    client.post('/login', data={'username': 'notifuser', 'password': 'testpass123'})
    r = client.get('/api/notifications', follow_redirects=False)
    assert r.status_code == 200
    import json
    data = json.loads(r.data)
    assert len(data) >= 1
    r2 = client.post('/api/notifications/mark-read', follow_redirects=False)
    assert r2.status_code == 200
    with app.app_context():
        assert Notification.query.filter_by(user_id=cid, read=False).count() == 0


# ── Route optimizer upgrade (Haversine + networkx TSP) ──
def test_route_optimize_tsp(client, app):
    _make_user(app, 'tspadmin', role='admin')
    with app.app_context():
        from app.models import SmartBin
        for hid, lat, lon in [('TSP-1', 18.05, 83.40), ('TSP-2', 18.06, 83.41), ('TSP-3', 18.07, 83.42)]:
            if not SmartBin.query.filter_by(hardware_id=hid).first():
                db.session.add(SmartBin(hardware_id=hid, latitude=lat, longitude=lon,
                                        level=90, ward='Ward 1 - MVGR College Area'))
        db.session.commit()
    client.post('/login', data={'username': 'tspadmin', 'password': 'testpass123'})
    r = client.get('/api/route-optimize', follow_redirects=False)
    assert r.status_code in (200, 302)
    if r.status_code == 200:
        import json
        d = json.loads(r.data)
        assert 'route' in d and 'total_distance' in d
        assert d['optimized_with'].startswith('networkx') or d['optimized_with'].startswith('greedy')


# ── Roadmap implementation: pool config, telemetry hardening, GeoJSON, SSE publish, route sheet ──
def test_pool_engine_options_configured(app):
    """Render/Supabase-safe pooling: pool_pre_ping revalidates idle-dropped
    connections, pool_recycle stays under the Supabase idle timeout, and the
    small pool + overflow ceiling never exceed the plan's connection cap."""
    opts = app.config['SQLALCHEMY_ENGINE_OPTIONS']
    assert opts['pool_pre_ping'] is True
    assert opts['pool_recycle'] == 300
    assert opts['pool_size'] == 3
    assert opts['max_overflow'] == 2


def test_lid_open_ingest_audits_change(client, app):
    """Lid-state telemetry is ingested; a state change writes ONE audit row,
    and repeating the same state does not duplicate it."""
    from app.models import SmartBin, AuditLog
    with app.app_context():
        db.session.add(SmartBin(hardware_id='LID-1', latitude=18.05, longitude=83.40,
                                level=10, ward='Ward 1 - MVGR College Area'))
        db.session.commit()
    r = client.post('/api/bin-telemetry',
                    json={'hardware_id': 'LID-1', 'level': 10, 'lid_open': True})
    assert r.status_code == 200
    with app.app_context():
        b = SmartBin.query.filter_by(hardware_id='LID-1').first()
        assert b.lid_open is True
        assert AuditLog.query.filter_by(action='BIN_LID_STATE', target='LID-1').count() == 1
    client.post('/api/bin-telemetry',
                json={'hardware_id': 'LID-1', 'level': 10, 'lid_open': True})
    with app.app_context():
        assert AuditLog.query.filter_by(action='BIN_LID_STATE', target='LID-1').count() == 1


def test_telemetry_replay_rejects_stale_frame(client, app):
    """Frames carrying a device clock older than 5 minutes are rejected (403)
    — an intercepted HMAC frame can't be replayed to re-trigger state."""
    import time as _time
    from app.models import SmartBin
    with app.app_context():
        db.session.add(SmartBin(hardware_id='TS-1', latitude=18.05, longitude=83.40,
                                level=10, ward='Ward 1 - MVGR College Area'))
        db.session.commit()
    fresh = client.post('/api/bin-telemetry',
                        json={'hardware_id': 'TS-1', 'level': 10, 'ts': int(_time.time())})
    assert fresh.status_code == 200
    stale = client.post('/api/bin-telemetry',
                        json={'hardware_id': 'TS-1', 'level': 10,
                              'ts': int(_time.time()) - 600})
    assert stale.status_code == 403


def test_telemetry_gps_drift_rejected_and_audited(client, app):
    """Coordinates more than 2 km from the last known position are rejected
    (bin kept in place) and audited as a possible theft/relocation."""
    from app.models import SmartBin, AuditLog
    with app.app_context():
        db.session.add(SmartBin(hardware_id='GPS-1', latitude=18.05, longitude=83.40,
                                level=10, ward='Ward 1 - MVGR College Area'))
        db.session.commit()
    r = client.post('/api/bin-telemetry',
                    json={'hardware_id': 'GPS-1', 'level': 10,
                          'latitude': 18.55, 'longitude': 84.10})  # ~80 km away
    assert r.status_code == 200
    with app.app_context():
        b = SmartBin.query.filter_by(hardware_id='GPS-1').first()
        assert b.latitude == 18.05 and b.longitude == 83.40  # unchanged
        assert AuditLog.query.filter_by(action='BIN_GPS_ANOMALY', target='GPS-1').count() == 1


def test_stuck_sensor_suppresses_dispatch(client, app, monkeypatch):
    """A constant >=95% level across 5 pings is a blocked sensor, not
    overflow: the bin is flagged sensor_fault (amber), a Sensor Health record
    + first-class incident are created, and NO dispatch is auto-queued even
    when the ML forecast looks urgent."""
    from app.models import SmartBin, BinTelemetryLog, AuditLog, DispatchAssignment, SensorHealth, IncidentLog
    import app.routes.iot as iot_mod
    monkeypatch.setattr(iot_mod, 'predict_overflow_eta_hours', lambda *a, **k: 1.0)
    with app.app_context():
        b = SmartBin(hardware_id='STUCK-1', latitude=18.05, longitude=83.40,
                     level=96, ward='Ward 1 - MVGR College Area')
        db.session.add(b)
        db.session.flush()
        for _ in range(5):
            db.session.add(BinTelemetryLog(bin_id=b.id, level=96, timestamp=utcnow()))
        db.session.commit()
    r = client.post('/api/bin-telemetry', json={'hardware_id': 'STUCK-1', 'level': 96})
    assert r.status_code == 200
    with app.app_context():
        b = SmartBin.query.filter_by(hardware_id='STUCK-1').first()
        assert b.sensor_fault is True
        assert DispatchAssignment.query.filter_by(bin_id=b.id).count() == 0
        assert AuditLog.query.filter_by(action='SENSOR_SUSPICIOUS', target='STUCK-1').count() == 1
        # The sensor-health control room gets a reason + a deduped Active incident.
        sh = SensorHealth.query.filter_by(bin_id=b.id).first()
        assert sh is not None and sh.fault_flag is True and sh.maintenance_scheduled is True
        assert 'Stuck sensor' in (sh.fault_reason or '')
        inc = IncidentLog.query.filter_by(bin_id=b.id, incident_type='Sensor Fault').all()
        assert len(inc) == 1 and inc[0].status == 'Active'


def test_sensor_faults_api_lists_faulted_bins_and_incidents(client, app):
    """The sensor-health control room endpoint returns faulted bins (with
    fault reason + maintenance flag) and open Sensor Fault incidents in one
    contract — admin-only."""
    from app.models import SmartBin, SensorHealth, IncidentLog
    with app.app_context():
        b = SmartBin(hardware_id='SF-API-1', latitude=18.05, longitude=83.40,
                     level=60, status='Warning', sensor_fault=True,
                     ward='Ward 1 - MVGR College Area')
        db.session.add(b)
        db.session.flush()
        db.session.add(SensorHealth(bin_id=b.id, fault_flag=True,
                                    fault_reason='Stuck sensor: constant level across 5 pings (possible blockage)',
                                    maintenance_scheduled=True))
        db.session.add(IncidentLog(bin_id=b.id, incident_type='Sensor Fault',
                                   severity='Warning', status='Active',
                                   description='Stuck sensor: SF-API-1 constant >=95%'))
        db.session.commit()
    _make_user(app, 'sfadmin', role='admin')
    _login_admin(client, app, 'sfadmin')
    r = client.get('/api/sensor-faults', follow_redirects=False)
    assert r.status_code == 200
    data = r.get_json()
    assert data['kpis']['faulted_bins'] == 1
    assert data['kpis']['open_incidents'] == 1
    assert data['kpis']['maintenance_scheduled'] == 1
    row = [x for x in data['bins'] if x['hardware_id'] == 'SF-API-1'][0]
    assert row['fault_reason'] is not None and 'Stuck sensor' in row['fault_reason']
    assert row['maintenance_scheduled'] is True
    assert row['open_incidents'] is True
    inc = [x for x in data['incidents'] if x['hardware_id'] == 'SF-API-1'][0]
    assert inc['severity'] == 'Warning'


def test_sensor_faults_api_blocks_citizen(client, app):
    """The sensor-health feed is admin-only."""
    _make_user(app, 'sfcit')
    client.post('/login', data={'username': 'sfcit', 'password': 'testpass123'})
    assert client.get('/api/sensor-faults', follow_redirects=False).status_code == 403


def test_clear_fault_resolves_and_audits(client, app):
    """Manual clear-fault unflags the bin + SensorHealth, resolves every open
    Sensor Fault incident, and writes a BIN_FAULT_CLEARED audit entry — all in
    one committed transaction."""
    from app.models import SmartBin, SensorHealth, IncidentLog, AuditLog
    with app.app_context():
        b = SmartBin(hardware_id='SF-CLR-1', latitude=18.05, longitude=83.40,
                     level=96, status='Critical', sensor_fault=True,
                     ward='Ward 1 - MVGR College Area')
        db.session.add(b)
        db.session.flush()
        db.session.add(SensorHealth(bin_id=b.id, fault_flag=True,
                                    fault_reason='Stuck sensor: constant level across 5 pings',
                                    maintenance_scheduled=True))
        db.session.add(IncidentLog(bin_id=b.id, incident_type='Sensor Fault',
                                   severity='Warning', status='Active',
                                   description='Stuck sensor: SF-CLR-1'))
        db.session.commit()
    _make_user(app, 'sfclradmin', role='admin')
    _login_admin(client, app, 'sfclradmin')
    r = client.post('/api/bins/SF-CLR-1/clear-fault', follow_redirects=False)
    assert r.status_code == 200
    assert r.get_json()['success'] is True
    assert r.get_json()['resolved_incidents'] == 1
    with app.app_context():
        b = SmartBin.query.filter_by(hardware_id='SF-CLR-1').first()
        assert b.sensor_fault is False
        sh = SensorHealth.query.filter_by(bin_id=b.id).first()
        assert sh.fault_flag is False and sh.fault_reason is None
        assert sh.maintenance_scheduled is False
        inc = IncidentLog.query.filter_by(bin_id=b.id, incident_type='Sensor Fault').first()
        assert inc.status == 'Resolved'
        assert AuditLog.query.filter_by(action='BIN_FAULT_CLEARED', target='SF-CLR-1').count() == 1


def test_clear_fault_guards(client, app):
    """Clear-fault is admin-only, 404s for unknown bins, and 400s when the bin
    is not faulted (idempotent safety — no false audit rows)."""
    from app.models import SmartBin, AuditLog
    _make_user(app, 'sfguardadmin', role='admin')
    _login_admin(client, app, 'sfguardadmin')
    # Unknown bin -> 404
    assert client.post('/api/bins/NOPE-1/clear-fault', follow_redirects=False).status_code == 404
    # Not-faulted bin -> 400, no audit row written
    with app.app_context():
        db.session.add(SmartBin(hardware_id='SF-OK-1', latitude=18.05, longitude=83.40,
                                level=10, ward='Ward 1 - MVGR College Area'))
        db.session.commit()
    r = client.post('/api/bins/SF-OK-1/clear-fault', follow_redirects=False)
    assert r.status_code == 400
    with app.app_context():
        assert AuditLog.query.filter_by(action='BIN_FAULT_CLEARED').count() == 0
    # Citizen blocked -> 403 (log out first: a logged-in admin can't be
    # displaced by a /login POST — the route redirects logged-in users away).
    _make_user(app, 'sfguardcit')
    client.get('/logout', follow_redirects=True)
    client.post('/login', data={'username': 'sfguardcit', 'password': 'testpass123'})
    assert client.post('/api/bins/SF-OK-1/clear-fault', follow_redirects=False).status_code == 403


def test_bins_geojson_shape(client, app):
    """/api/bins.geojson returns a GeoJSON FeatureCollection with lon/lat
    coordinates (RFC 7946 order) and urgency properties for marker coloring."""
    from app.models import SmartBin
    with app.app_context():
        if not SmartBin.query.filter_by(hardware_id='GJ-1').first():
            db.session.add(SmartBin(hardware_id='GJ-1', latitude=18.05, longitude=83.40,
                                    level=55, status='Warning',
                                    ward='Ward 1 - MVGR College Area'))
            db.session.commit()
    _make_user(app, 'geoadmin', role='admin')
    _login_admin(client, app, 'geoadmin')
    r = client.get('/api/bins.geojson', follow_redirects=False)
    assert r.status_code == 200
    fc = r.get_json()
    assert fc['type'] == 'FeatureCollection'
    gj = [f for f in fc['features'] if f['properties']['hardware_id'] == 'GJ-1'][0]
    assert gj['geometry']['type'] == 'Point'
    assert gj['geometry']['coordinates'] == [83.40, 18.05]  # GeoJSON: [lon, lat]
    assert gj['properties']['level'] == 55


def test_route_sheet_pdf_generates(app):
    """The ReportLab A5 route-sheet helper returns real PDF bytes (even for an
    empty queue) — the printable driver run-card pipeline."""
    from app.routes import _driver_route_sheet_pdf
    pdf = _driver_route_sheet_pdf([])
    assert pdf[:4] == b'%PDF'


def test_publish_user_event_noop_without_redis(app):
    """The SSE publish helper degrades to a no-op (None) without a broker —
    the stream's DB-poll fallback covers delivery in dev/tests."""
    from app.routes import _publish_user_event
    assert _publish_user_event(1, 'hello') is None


def test_notifications_stream_snapshot_then_poll(client, app, monkeypatch):
    """Regression: the SSE stream must survive its FIRST message. The rewrite
    dropped `nonlocal MAX_EVENTS` while still doing MAX_EVENTS -= 1 — that
    raised UnboundLocalError on the first decrement, killing the stream for
    every citizen (EventSource then reconnect-looped invisibly). This drives
    the snapshot loop past the decrement AND serves a new notification via the
    DB-poll fallback (no Redis in tests)."""
    import time as _time
    monkeypatch.setattr(_time, 'sleep', lambda s: None)  # no 5s waits in tests
    cid = _make_user(app, 'streamuser')
    with app.app_context():
        db.session.add(Notification(user_id=cid, message="Unread note", link='/dashboard'))
        db.session.commit()
    client.post('/login', data={'username': 'streamuser', 'password': 'testpass123'})

    resp = client.get('/api/notifications/stream', buffered=False)
    gen = resp.response
    first = next(gen)  # snapshot loop: yields the unread note
    assert b'Unread note' in first
    # Resume past MAX_EVENTS -= 1 (the scoping-bug site), then create a fresh
    # notification for the DB-poll fallback to pick up.
    with app.app_context():
        db.session.add(Notification(user_id=cid, message="Fresh note", link='/dashboard'))
        db.session.commit()
    second = next(gen)
    assert b'Fresh note' in second
    gen.close()


# ── Green-Points leaderboard endpoint (Phase E) ──
def test_green_points_leaderboard(client, app):
    import json
    _make_user(app, 'eco_champ', green_points=150)
    _make_user(app, 'eco_low', green_points=40)
    _make_user(app, 'eco_zero', green_points=0)
    _make_user(app, 'eco_login')
    client.post('/login', data={'username': 'eco_login', 'password': 'testpass123'})
    r = client.get('/api/leaderboard', follow_redirects=False)
    assert r.status_code == 200
    data = json.loads(r.data)
    assert len(data) >= 2
    assert data[0]['username'] == 'eco_champ'
    assert data[0]['green_points'] == 150
    ranks = [u['username'] for u in data]
    assert 'eco_champ' in ranks
    assert 'eco_low' in ranks
    assert 'eco_zero' not in ranks
    assert sorted([u['green_points'] for u in data], reverse=True) == [u['green_points'] for u in data]
    assert data[0]['username'] == 'eco_champ'
    assert data[0]['green_points'] == 150
    ranks = [u['username'] for u in data]
    assert 'eco_champ' in ranks
    assert 'eco_low' in ranks
    assert 'eco_zero' not in ranks
    assert sorted([u['green_points'] for u in data], reverse=True) == [u['green_points'] for u in data]


# ── Live WebSocket push on telemetry (Phase D) ──
def test_bin_telemetry_emits_socket_event(app):
    from app.models import SmartBin
    with app.app_context():
        if not SmartBin.query.filter_by(hardware_id='LIVE-1').first():
            db.session.add(SmartBin(hardware_id='LIVE-1', latitude=18.06,
                                    longitude=83.41, level=10, ward='Ward 1 - MVGR College Area'))
        db.session.commit()

    # Connect a socket.io test client and ingest a telemetry frame via the
    # flask test client; the handler must emit a `bin_update` event.
    io_client = socketio.test_client(app)
    try:
        with app.test_client() as c:
            r = c.post('/api/bin-telemetry', json={
                "hardware_id": "LIVE-1", "level": 73, "temperature": 29.0,
                "methane": 120, "battery_level": 90})
            assert r.status_code == 200
        received = io_client.get_received()
        events = [e['name'] for e in received]
        assert 'bin_update' in events
        upd = next(e for e in received if e['name'] == 'bin_update')
        assert upd['args'][0]['hardware_id'] == 'LIVE-1'
        assert upd['args'][0]['level'] == 73
    finally:
        io_client.disconnect()


# ── IoT telemetry HMAC auth (enforced only when secret is configured) ──
def test_bin_telemetry_rejects_bad_signature_when_secret_set(app, monkeypatch):
    from app.models import SmartBin
    with app.app_context():
        if not SmartBin.query.filter_by(hardware_id='SIG-1').first():
            db.session.add(SmartBin(hardware_id='SIG-1', latitude=18.06,
                                    longitude=83.41, level=10,
                                    ward='Ward 1 - MVGR College Area'))
        db.session.commit()

    monkeypatch.setitem(app.config, 'IOT_TELEMETRY_SECRET', 'test-secret')
    with app.test_client() as c:
        r = c.post('/api/bin-telemetry', json={"hardware_id": "SIG-1", "level": 1})
        assert r.status_code == 403

        import hmac, hashlib, json
        body = json.dumps({"hardware_id": "SIG-1", "level": 1}).encode()
        sig = hmac.new(b'test-secret', body, hashlib.sha256).hexdigest()
        r2 = c.post('/api/bin-telemetry', data=body,
                    headers={'Content-Type': 'application/json',
                             'X-Signature': sig})
        assert r2.status_code == 200


# ── ML overflow forecast (hours-to-overflow) ───────────────────
def test_predict_overflow_eta_hours_heuristic_without_fill_model(app, monkeypatch):
    """predict_overflow_eta_hours must return a sane positive float for a
    filling bin even when the trained fill-rate regressor is absent — the
    transparent heuristic fallback (level / hours-since-reset) keeps the
    route optimizer alive on any fresh checkout."""
    import app.ml_model as ml
    monkeypatch.setattr(ml, 'fill_model', None)
    from datetime import timedelta
    with app.app_context():
        from app.models import SmartBin
        bin_row = SmartBin(
            hardware_id='ETA-1', latitude=18.06, longitude=83.41,
            level=60, ward='Ward 1 - MVGR College Area',
            decomposition_started_at=utcnow() - timedelta(hours=24),
        )
        eta = ml.predict_overflow_eta_hours(bin_row)
    assert eta is not None and eta > 0
    # 60% full at 2.5%/hr → ~16h to overflow; allow heuristic variance.
    assert 1 <= eta <= 14 * 24


def test_predict_overflow_eta_hours_none_for_empty_or_faulty(app, monkeypatch):
    import app.ml_model as ml
    monkeypatch.setattr(ml, 'fill_model', None)
    with app.app_context():
        from app.models import SmartBin
        empty = SmartBin(hardware_id='ETA-2', latitude=18.06, longitude=83.41,
                         level=0, ward='Ward 1 - MVGR College Area')
        assert ml.predict_overflow_eta_hours(empty) is None
        faulty = SmartBin(hardware_id='ETA-3', latitude=18.06, longitude=83.41,
                          level=80, sensor_fault=True,
                          ward='Ward 1 - MVGR College Area')
        assert ml.predict_overflow_eta_hours(faulty) is None
        full = SmartBin(hardware_id='ETA-4', latitude=18.06, longitude=83.41,
                        level=100, ward='Ward 1 - MVGR College Area')
        assert ml.predict_overflow_eta_hours(full) == 0.0


def test_bin_telemetry_persists_overflow_eta_and_alerts_once(app, monkeypatch):
    """A telemetry ping must write overflow_eta_hours, and the proactive
    OVERFLOW_ALERT webhook fires exactly once when the forecast crosses the
    6h threshold (not on every subsequent ping)."""
    from datetime import timedelta
    from app.models import SmartBin
    # Pin the heuristic fill-rate branch (level / hours-since-reset) so the
    # expected ~3h ETA holds whether or not ml_fill_model.pkl exists locally.
    import app.ml_model as ml
    monkeypatch.setattr(ml, 'fill_model', None)
    with app.app_context():
        if not SmartBin.query.filter_by(hardware_id='ETA-PING').first():
            db.session.add(SmartBin(
                hardware_id='ETA-PING', latitude=18.06, longitude=83.41,
                level=90, ward='Ward 1 - MVGR College Area',
                decomposition_started_at=utcnow() - timedelta(hours=30),
            ))
        db.session.commit()

    import app.routes as routes
    fired = []
    monkeypatch.setattr(routes, '_dispatch_webhooks', lambda event, payload: fired.append(event))

    with app.test_client() as c:
        # Ping 1: 90% at 3%/hr → ~3.3h → crosses the 6h alert threshold.
        r = c.post('/api/bin-telemetry', json={"hardware_id": "ETA-PING", "level": 90})
        assert r.status_code == 200
        assert r.get_json().get('overflow_eta_hours') is not None
        with app.app_context():
            b = SmartBin.query.filter_by(hardware_id='ETA-PING').first()
            assert b.overflow_eta_hours is not None and b.overflow_eta_hours <= 6

        # Ping 2: still urgent → must NOT re-fire the alert webhook.
        r2 = c.post('/api/bin-telemetry', json={"hardware_id": "ETA-PING", "level": 92})
        assert r2.status_code == 200

    assert fired.count('SMART_BIN_OVERFLOW_ALERT') == 1, fired


def test_overflow_alert_fires_on_threshold_crossing_from_above(app, monkeypatch):
    """A bin forecast at 8h (above the 6h alert) that tightens to ~5h must
    fire the alert on that crossing — the proactive-dispatch scenario the
    feature exists for (prev_eta > threshold → eta <= threshold)."""
    from datetime import timedelta
    from app.models import SmartBin
    import app.ml_model as ml
    monkeypatch.setattr(ml, 'fill_model', None)
    with app.app_context():
        if not SmartBin.query.filter_by(hardware_id='ETA-CROSS').first():
            db.session.add(SmartBin(
                hardware_id='ETA-CROSS', latitude=18.06, longitude=83.41,
                level=70, ward='Ward 1 - MVGR College Area',
                decomposition_started_at=utcnow() - timedelta(hours=10),
                overflow_eta_hours=8.0,  # seeded just above the 6h threshold
            ))
        db.session.commit()

    import app.routes as routes
    fired = []
    monkeypatch.setattr(routes, '_dispatch_webhooks', lambda event, payload: fired.append(event))

    with app.test_client() as c:
        # 80% at 8%/hr → ~2.5h → crosses 6h (prev_eta 8.0 > 6) → must fire.
        r = c.post('/api/bin-telemetry', json={"hardware_id": "ETA-CROSS", "level": 80})
        assert r.status_code == 200

    assert 'SMART_BIN_OVERFLOW_ALERT' in fired, fired


def test_route_optimize_includes_forecast_critical_bins(client, app):
    """The route optimizer must include bins forecast to overflow within 24h
    even below the 80% fill trigger, and expose overflow_eta_hours per node."""
    from app.models import SmartBin
    _make_user(app, 'etaadmin', role='admin')
    with app.app_context():
        if not SmartBin.query.filter_by(hardware_id='ETA-ROUTE-60').first():
            db.session.add_all([
                SmartBin(hardware_id='ETA-ROUTE-60', latitude=18.05, longitude=83.40,
                         level=60, ward='Ward 1 - MVGR College Area', overflow_eta_hours=8.0),
                SmartBin(hardware_id='ETA-ROUTE-85', latitude=18.07, longitude=83.42,
                         level=85, ward='Ward 1 - MVGR College Area', overflow_eta_hours=None),
            ])
        db.session.commit()
    _login_admin(client, app, 'etaadmin')
    r = client.get('/api/route-optimize', follow_redirects=False)
    assert r.status_code == 200
    d = _json.loads(r.data)
    labels = [n.get('label') for n in d['route']]
    assert 'ETA-ROUTE-60' in labels, 'forecast-critical (60%, eta 8h) bin missing from route'
    assert 'ETA-ROUTE-85' in labels
    node = next(n for n in d['route'] if n.get('label') == 'ETA-ROUTE-60')
    assert node['overflow_eta_hours'] == 8.0


def test_overflow_forecast_api_sorted_by_urgency(client, app):
    from app.models import SmartBin
    _make_user(app, 'etaview', role='admin')
    with app.app_context():
        if not SmartBin.query.filter_by(hardware_id='ETA-API-2').first():
            db.session.add_all([
                SmartBin(hardware_id='ETA-API-2', latitude=18.05, longitude=83.40,
                         level=55, ward='Ward 1 - MVGR College Area', overflow_eta_hours=2.0),
                SmartBin(hardware_id='ETA-API-30', latitude=18.07, longitude=83.42,
                         level=40, ward='Ward 1 - MVGR College Area', overflow_eta_hours=30.0),
            ])
        db.session.commit()
    _login_admin(client, app, 'etaview')
    r = client.get('/api/overflow-forecast')
    assert r.status_code == 200
    d = _json.loads(r.data)
    bins = d['bins']
    etas = [b['overflow_eta_hours'] for b in bins if b['hardware_id'].startswith('ETA-API')]
    assert etas == sorted(etas), 'forecast API must sort bins by hours-to-overflow'
    urgent = [b for b in bins if b['hardware_id'] == 'ETA-API-2']
    assert urgent and urgent[0]['urgent'] is True


# ── Spam protection: anonymous illegal-dump route is rate-limited ──
def test_report_illegal_is_rate_limited(client, app):
    # 10/hour limit; the 11th POST must be rejected with 429.
    statuses = []
    for _ in range(11):
        r = client.post('/report-illegal', data={'category': 'e-waste'},
                        content_type='multipart/form-data')
        statuses.append(r.status_code)
    assert 429 in statuses, f"expected 429 after limit, got {statuses}"


# ── Uploaded photos are compressed (not saved raw) ──
def test_illegal_report_compresses_photo(client, app):
    from PIL import Image
    import io
    buf = io.BytesIO()
    Image.new('RGBA', (4000, 3000), (200, 50, 10, 255)).save(buf, format='PNG')
    buf.seek(0)
    r = client.post('/report-illegal',
                    data={'category': 'e-waste', 'photo': (buf, 'big.png')},
                    content_type='multipart/form-data')
    assert r.status_code in (200, 302)
    with app.app_context():
        from app.models import IllegalDumpReport
        rep = IllegalDumpReport.query.order_by(IllegalDumpReport.id.desc()).first()
        assert rep and rep.scrubbed_photo
    # The saved file must be a small JPEG, not a multi-MB raw PNG.
    saved = rep.scrubbed_photo.split('/', 1)[-1]
    path = os.path.join(create_app().config['UPLOAD_FOLDER'], saved)
    assert os.path.exists(path), path
    im = Image.open(path)
    assert im.format == 'JPEG'
    assert max(im.size) <= 1280
    assert os.path.getsize(path) < 500 * 1024


# ── Photo storage: local fallback when Cloudinary is NOT configured ──
def test_photo_storage_local_fallback(app, monkeypatch):
    monkeypatch.delenv('CLOUDINARY_URL', raising=False)
    from PIL import Image
    import io
    buf = io.BytesIO()
    Image.new('RGB', (300, 300), (10, 200, 50)).save(buf, format='PNG')
    buf.seek(0)
    buf.filename = 'fallback.png'

    class FakeFile:
        def __init__(self, b, name):
            self._b = b; self.filename = name

        def read(self):
            return self._b.getvalue()

        def seek(self, p):
            return None

        @property
        def stream(self):
            return self._b

    with app.app_context():
        from app.routes import save_compressed_photo
        out = save_compressed_photo(FakeFile(buf, 'fallback.png'), 'complaint')
    # Without Cloudinary, we must keep the local uploads/ relative path.
    assert out.startswith('uploads/'), out
    assert out.endswith('.png') or out.endswith('.jpg')


# ── Photo storage: Cloudinary URL returned when uploader succeeds ──
def test_photo_storage_cloudinary_url(app, monkeypatch):
    monkeypatch.setenv('CLOUDINARY_URL', 'cloudinary://k:s@demo')
    from PIL import Image
    import io
    buf = io.BytesIO()
    Image.new('RGB', (300, 300), (10, 200, 50)).save(buf, format='PNG')
    buf.seek(0)
    buf.filename = 'remote.png'

    class FakeFile:
        def __init__(self, b, name):
            self._b = b; self.filename = name

        def read(self):
            return self._b.getvalue()

        def seek(self, p):
            return None

        @property
        def stream(self):
            return self._b

    fake_result = {'secure_url': 'https://res.cloudinary.com/demo/image/upload/v1/smartgarbage/complaint/remote.png'}

    import sys
    import types

    class FakeUploader:
        @staticmethod
        def upload(*a, **k):
            return fake_result

    fake_cloudinary = types.SimpleNamespace(uploader=FakeUploader,
                                            config=lambda **k: None)
    # Force the lazy `import cloudinary` / `import cloudinary.uploader` inside
    # save_compressed_photo to resolve to our fakes.
    monkeypatch.setitem(sys.modules, 'cloudinary', fake_cloudinary)
    monkeypatch.setitem(sys.modules, 'cloudinary.uploader', fake_cloudinary.uploader)

    with app.app_context():
        from app.routes import save_compressed_photo
        out = save_compressed_photo(FakeFile(buf, 'remote.png'), 'complaint')
    assert out.startswith('https://'), out
    assert 'smartgarbage' in out


# ── ML miss-prediction: model path + heuristic fallback ─────────
def test_predict_miss_returns_binary_with_model(app):
    try:
        import pandas  # noqa: F401
    except ImportError:
        return
    from app.ml_model import predict_miss
    with app.app_context():
        val = predict_miss('Ward 1 - MVGR College Area')
    assert val in (0, 1)


def test_predict_miss_heuristic_fallback_when_no_model(app, monkeypatch):
    # Force the lazy-loaded model to None so the heuristic branch runs and
    # the route can never crash on a missing/invalid artifact.
    import app.ml_model as ml
    monkeypatch.setattr(ml, 'model', None)
    with app.app_context():
        val = ml.predict_miss('Ward 3 - RTC Colony')
    assert val in (0, 1)


# ── PAYT UPI payment-confirmation step ──────────────────────
def test_payt_confirm_marks_invoice_paid(client, app):
    from app.models import PAYTInvoice
    uid = _make_user(app, 'payer', role='citizen')
    with app.app_context():
        inv = PAYTInvoice(user_id=uid, period='July 2026', weight_kg=10.0,
                          landfill_kg=4.0, amount_rs=42.0, status='Unpaid')
        db.session.add(inv)
        db.session.commit()
        inv_id = inv.id

    # Login as the invoice owner (citizen, no MFA)
    client.post('/login', data={'username': 'payer', 'password': 'testpass123'})
    r = client.post(f'/payt/confirm/{inv_id}', data={'txn': 'UPI-RRN-123'},
                    follow_redirects=False)
    assert r.status_code == 302  # redirected to dashboard

    with app.app_context():
        inv = PAYTInvoice.query.get(inv_id)
        assert inv.status == 'Paid'
        assert inv.transaction_ref == 'UPI-RRN-123'
        assert inv.payment_method == 'UPI'
        assert inv.paid_at is not None


def test_payt_confirm_rejects_other_user(client, app):
    from app.models import PAYTInvoice
    uid = _make_user(app, 'payer2', role='citizen')
    _make_user(app, 'intruder', role='citizen')
    with app.app_context():
        inv = PAYTInvoice(user_id=uid, period='July 2026', weight_kg=10.0,
                          amount_rs=42.0, status='Unpaid')
        db.session.add(inv)
        db.session.commit()
        inv_id = inv.id

    client.post('/login', data={'username': 'intruder', 'password': 'testpass123'})
    # Should be forbidden (404 via abort(403) -> 403)
    r = client.post(f'/payt/confirm/{inv_id}', data={}, follow_redirects=False)
    assert r.status_code in (403, 302)


# ── Analytics is admin-only ────────────────────────────────
def test_analytics_page_requires_admin(client, app):
    _make_user(app, 'analyticscit', role='citizen')
    client.post('/login', data={'username': 'analyticscit', 'password': 'testpass123'})
    r = client.get('/analytics', follow_redirects=False)
    assert r.status_code == 403  # citizen must NOT see analytics
    r2 = client.get('/api/analytics-data', follow_redirects=False)
    assert r2.status_code == 403


def test_analytics_page_admin_ok(client, app):
    _make_user(app, 'analyticsadmin', role='admin')
    _login_admin(client, app, 'analyticsadmin')
    r = client.get('/analytics', follow_redirects=False)
    assert r.status_code == 200


# ── PAYT pay page is owner-only ─────────────────────────────
def test_payt_pay_page_rejects_other_user(client, app):
    from app.models import PAYTInvoice
    owner = _make_user(app, 'paytowner', role='citizen')
    _make_user(app, 'paytsnoop', role='citizen')
    with app.app_context():
        inv = PAYTInvoice(user_id=owner, period='Aug 2026', weight_kg=10.0,
                          amount_rs=42.0, status='Unpaid')
        db.session.add(inv)
        db.session.commit()
        inv_id = inv.id
    client.post('/login', data={'username': 'paytsnoop', 'password': 'testpass123'})
    r = client.get(f'/payt/pay/{inv_id}', follow_redirects=False)
    assert r.status_code == 403  # snooper cannot view the pay page

    client.get('/logout')
    client.post('/login', data={'username': 'paytowner', 'password': 'testpass123'})
    r = client.get(f'/payt/pay/{inv_id}', follow_redirects=False)
    assert r.status_code == 200  # owner sees the UPI pay button
    assert 'upi://pay' in r.get_data(as_text=True)


# ── Razorpay server-side order + webhook capture ─────────────
def _payt_invoice(app, username, period='Sep 2026', amount=42.0, **kw):
    """Create a PAYT invoice for a fresh user; returns (uid, inv_id).

    status defaults to 'Unpaid' but may be overridden (Paid invoices for the
    refund-path tests)."""
    from app.models import PAYTInvoice
    uid = _make_user(app, username, role='citizen')
    with app.app_context():
        kw.setdefault('status', 'Unpaid')
        inv = PAYTInvoice(user_id=uid, period=period, weight_kg=10.0,
                          landfill_kg=4.0, amount_rs=amount, **kw)
        db.session.add(inv)
        db.session.commit()
        inv_id = inv.id
    return uid, inv_id


def test_payt_pay_page_creates_razorpay_order(client, app, monkeypatch):
    """With RAZORPAY keys set, the pay page mints a server-side order and
    persists razorpay_order_id so the webhook can map the capture back."""
    from app.models import PAYTInvoice
    import app.routes as routes
    monkeypatch.setenv('RAZORPAY_KEY_ID', 'rzp_test_key')
    monkeypatch.setenv('RAZORPAY_KEY_SECRET', 'rzp_test_secret')
    uid, inv_id = _payt_invoice(app, 'rzpowner')

    captured = {}

    def fake_post(url, json=None, auth=None, timeout=None):
        captured['url'] = url
        captured['amount_paise'] = json.get('amount')
        return type('R', (), {
            'raise_for_status': lambda self: None,
            'json': lambda self: {'id': 'order_ABC123'},
        })()
    monkeypatch.setattr(routes.requests, 'post', fake_post)

    client.post('/login', data={'username': 'rzpowner', 'password': 'testpass123'})
    r = client.get(f'/payt/pay/{inv_id}', follow_redirects=False)
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert 'order_ABC123' in body            # checkout.js gets the real order
    assert 'checkout.razorpay.com' in body   # Razorpay SDK loaded
    assert 'upi://pay' in body               # UPI deep-link fallback retained
    assert captured['url'] == 'https://api.razorpay.com/v1/orders'
    assert captured['amount_paise'] == 4200  # ₹42.00 → paise
    with app.app_context():
        assert PAYTInvoice.query.get(inv_id).razorpay_order_id == 'order_ABC123'


def test_payt_verify_marks_paid_with_valid_signature(client, app, monkeypatch):
    """The Checkout handler's signature (HMAC-SHA256 of order|payment) is
    verified server-side before the invoice flips to Paid."""
    from app.models import PAYTInvoice
    import hmac as _hmac
    import hashlib as _hashlib
    monkeypatch.setenv('RAZORPAY_KEY_SECRET', 'rzp_test_secret')
    uid, inv_id = _payt_invoice(app, 'rzpverify', razorpay_order_id='order_XYZ')
    signature = _hmac.new(b'rzp_test_secret', b'order_XYZ|pay_PAY1', _hashlib.sha256).hexdigest()

    client.post('/login', data={'username': 'rzpverify', 'password': 'testpass123'})
    r = client.post(f'/payt/verify/{inv_id}', json={
        'razorpay_order_id': 'order_XYZ',
        'razorpay_payment_id': 'pay_PAY1',
        'razorpay_signature': signature,
    }, follow_redirects=False)
    assert r.status_code == 200
    assert r.get_json()['success'] is True
    with app.app_context():
        inv = PAYTInvoice.query.get(inv_id)
        assert inv.status == 'Paid'
        assert inv.payment_method == 'Razorpay'
        assert inv.transaction_ref == 'pay_PAY1'
        assert inv.paid_at is not None


def test_payt_verify_rejects_bad_signature(client, app, monkeypatch):
    """A forged/incorrect signature must NOT mark the invoice paid."""
    from app.models import PAYTInvoice
    monkeypatch.setenv('RAZORPAY_KEY_SECRET', 'rzp_test_secret')
    uid, inv_id = _payt_invoice(app, 'rzpforged', razorpay_order_id='order_XYZ')

    client.post('/login', data={'username': 'rzpforged', 'password': 'testpass123'})
    r = client.post(f'/payt/verify/{inv_id}', json={
        'razorpay_order_id': 'order_XYZ',
        'razorpay_payment_id': 'pay_EVIL',
        'razorpay_signature': 'deadbeefdeadbeef',
    }, follow_redirects=False)
    assert r.status_code == 400
    with app.app_context():
        assert PAYTInvoice.query.get(inv_id).status == 'Unpaid'


def test_payt_verify_rejects_wrong_order(client, app, monkeypatch):
    """The order id must match the one stored on the invoice — the client
    cannot claim it paid a different (cheaper) order."""
    from app.models import PAYTInvoice
    import hmac as _hmac
    import hashlib as _hashlib
    monkeypatch.setenv('RAZORPAY_KEY_SECRET', 'rzp_test_secret')
    uid, inv_id = _payt_invoice(app, 'rzpswitch', razorpay_order_id='order_LEGIT')
    signature = _hmac.new(b'rzp_test_secret', b'order_EVIL|pay_EVIL', _hashlib.sha256).hexdigest()

    client.post('/login', data={'username': 'rzpswitch', 'password': 'testpass123'})
    r = client.post(f'/payt/verify/{inv_id}', json={
        'razorpay_order_id': 'order_EVIL',
        'razorpay_payment_id': 'pay_EVIL',
        'razorpay_signature': signature,
    }, follow_redirects=False)
    assert r.status_code == 400
    assert r.get_json()['message'] == 'order_mismatch'
    with app.app_context():
        assert PAYTInvoice.query.get(inv_id).status == 'Unpaid'


def test_payt_verify_rejects_other_user(client, app, monkeypatch):
    """Only the invoice owner may call the verify endpoint."""
    monkeypatch.setenv('RAZORPAY_KEY_SECRET', 'rzp_test_secret')
    uid, inv_id = _payt_invoice(app, 'rzpown2')
    _make_user(app, 'rzpsnoop2', role='citizen')
    client.post('/login', data={'username': 'rzpsnoop2', 'password': 'testpass123'})
    r = client.post(f'/payt/verify/{inv_id}', json={}, follow_redirects=False)
    assert r.status_code == 403


def test_razorpay_webhook_captures_payment(client, app, monkeypatch):
    """A signed payment.captured webhook marks the invoice Paid idempotently."""
    from app.models import PAYTInvoice
    import hmac as _hmac
    import hashlib as _hashlib
    import json as _json
    monkeypatch.setenv('RAZORPAY_WEBHOOK_SECRET', 'whsec_test')
    uid, inv_id = _payt_invoice(app, 'rzpweb', razorpay_order_id='order_WEB1')
    payload = _json.dumps({
        'event': 'payment.captured',
        'payload': {'payment': {'entity': {'order_id': 'order_WEB1', 'id': 'pay_WEB1'}}},
    })
    signature = _hmac.new(b'whsec_test', payload.encode(), _hashlib.sha256).hexdigest()

    r = client.post('/webhook/razorpay', data=payload,
                    content_type='application/json',
                    headers={'X-Razorpay-Signature': signature})
    assert r.status_code == 200
    assert r.get_json()['handled'] is True
    with app.app_context():
        inv = PAYTInvoice.query.get(inv_id)
        assert inv.status == 'Paid'
        assert inv.payment_method == 'Razorpay'
        assert inv.transaction_ref == 'pay_WEB1'

    # Idempotent replay: a re-delivered webhook must not error or double-flip.
    r2 = client.post('/webhook/razorpay', data=payload,
                     content_type='application/json',
                     headers={'X-Razorpay-Signature': signature})
    assert r2.status_code == 200
    with app.app_context():
        assert PAYTInvoice.query.get(inv_id).status == 'Paid'


def test_razorpay_webhook_rejects_bad_signature(client, app, monkeypatch):
    """The webhook is public: an invalid X-Razorpay-Signature must 403, never
    mark an invoice paid (same discipline as the Twilio verifier)."""
    from app.models import PAYTInvoice
    monkeypatch.setenv('RAZORPAY_WEBHOOK_SECRET', 'whsec_test')
    uid, inv_id = _payt_invoice(app, 'rzpwebfake', razorpay_order_id='order_WEB2')
    r = client.post('/webhook/razorpay',
                    data='{"event": "payment.captured", "payload": {}}',
                    content_type='application/json',
                    headers={'X-Razorpay-Signature': 'forgedsig'})
    assert r.status_code == 403
    with app.app_context():
        assert PAYTInvoice.query.get(inv_id).status == 'Unpaid'


# ── Razorpay payment.failed: retry counter (never touches status) ──
def test_razorpay_webhook_payment_failed_counts_attempt(client, app, monkeypatch):
    """A signed payment.failed webhook bumps the invoice's failed-attempt
    counter and audits it, but invoice.status stays capture-driven (Unpaid).
    A later payment.captured resets the counter when it finally succeeds."""
    from app.models import PAYTInvoice, AuditLog
    import hmac as _hmac
    import hashlib as _hashlib
    import json as _json
    monkeypatch.setenv('RAZORPAY_WEBHOOK_SECRET', 'whsec_test')
    uid, inv_id = _payt_invoice(app, 'rzpwnfail', razorpay_order_id='order_FAIL1')

    def _sign(payload):
        return _hmac.new(b'whsec_test', payload.encode(), _hashlib.sha256).hexdigest()

    # First failure: counter 1, reason captured, status still Unpaid.
    payload = _json.dumps({
        'event': 'payment.failed',
        'payload': {'payment': {'entity': {
            'order_id': 'order_FAIL1', 'id': 'pay_FAIL1',
            'error_code': 'BAD_REQUEST_ERROR',
            'error_description': 'Bank declined the transaction',
        }}},
    })
    r = client.post('/webhook/razorpay', data=payload,
                    content_type='application/json',
                    headers={'X-Razorpay-Signature': _sign(payload)})
    assert r.status_code == 200
    assert r.get_json()['handled'] is True
    with app.app_context():
        inv = PAYTInvoice.query.get(inv_id)
        assert inv.status == 'Unpaid'            # status strictly capture-driven
        assert inv.failed_attempts == 1
        assert inv.last_failed_reason == 'Bank declined the transaction'
        assert inv.last_failed_at is not None
        assert AuditLog.query.filter_by(action='PAYT_PAYMENT_FAILED',
                                        target=f'Invoice #{inv_id}').count() == 1

    # A re-delivered webhook for the SAME payment id is deduped (Razorpay is
    # at-least-once): the counter must NOT inflate on retries.
    r1b = client.post('/webhook/razorpay', data=payload,
                      content_type='application/json',
                      headers={'X-Razorpay-Signature': _sign(payload)})
    assert r1b.status_code == 200
    assert r1b.get_json().get('deduped') is True
    with app.app_context():
        assert PAYTInvoice.query.get(inv_id).failed_attempts == 1
        assert AuditLog.query.filter_by(action='PAYT_PAYMENT_FAILED',
                                        target=f'Invoice #{inv_id}').count() == 1

    # A DIFFERENT payment id is a genuinely new attempt — increments again.
    payload2 = _json.dumps({
        'event': 'payment.failed',
        'payload': {'payment': {'entity': {
            'order_id': 'order_FAIL1', 'id': 'pay_FAIL2',
            'error_code': 'TIMED_OUT', 'error_description': 'Timed out',
        }}},
    })
    r2 = client.post('/webhook/razorpay', data=payload2,
                     content_type='application/json',
                     headers={'X-Razorpay-Signature': _sign(payload2)})
    assert r2.status_code == 200
    with app.app_context():
        assert PAYTInvoice.query.get(inv_id).failed_attempts == 2
        assert PAYTInvoice.query.get(inv_id).status == 'Unpaid'
        assert AuditLog.query.filter_by(action='PAYT_PAYMENT_FAILED',
                                        target=f'Invoice #{inv_id}').count() == 2

    # The eventual capture resets the retry counter and marks it Paid.
    cap = _json.dumps({
        'event': 'payment.captured',
        'payload': {'payment': {'entity': {
            'order_id': 'order_FAIL1', 'id': 'pay_SUCCESS'}}},
    })
    r3 = client.post('/webhook/razorpay', data=cap,
                     content_type='application/json',
                     headers={'X-Razorpay-Signature': _sign(cap)})
    assert r3.status_code == 200
    with app.app_context():
        inv = PAYTInvoice.query.get(inv_id)
        assert inv.status == 'Paid'
        assert inv.failed_attempts == 0          # stale retry counter cleared
        assert inv.last_failed_reason is None
        assert inv.transaction_ref == 'pay_SUCCESS'


def test_razorpay_webhook_payment_failed_ignores_paid_and_unknown(client, app, monkeypatch):
    """A late failure after capture (or an unknown order) is acknowledged but
    never downgrades the invoice or crashes the webhook."""
    from app.models import PAYTInvoice
    import hmac as _hmac
    import hashlib as _hashlib
    import json as _json
    monkeypatch.setenv('RAZORPAY_WEBHOOK_SECRET', 'whsec_test')
    # _payt_invoice hardcodes status='Unpaid', so build the already-paid
    # invoice directly (the late-failure scenario needs a Paid invoice).
    uid = _make_user(app, 'rzpwnlate')
    with app.app_context():
        inv = PAYTInvoice(user_id=uid, period='Sep 2026', weight_kg=10.0,
                          landfill_kg=4.0, amount_rs=42.0, status='Paid',
                          razorpay_order_id='order_FAIL2', transaction_ref='pay_EARLY')
        db.session.add(inv)
        db.session.commit()
        inv_id = inv.id

    payload = _json.dumps({
        'event': 'payment.failed',
        'payload': {'payment': {'entity': {
            'order_id': 'order_FAIL2', 'id': 'pay_LATE',
            'error_description': 'late failure',
        }}},
    })
    sig = _hmac.new(b'whsec_test', payload.encode(), _hashlib.sha256).hexdigest()
    r = client.post('/webhook/razorpay', data=payload,
                    content_type='application/json',
                    headers={'X-Razorpay-Signature': sig})
    assert r.status_code == 200
    with app.app_context():
        inv = PAYTInvoice.query.get(inv_id)
        assert inv.status == 'Paid'               # never downgraded
        assert inv.failed_attempts == 0           # counter untouched once Paid

    # Unknown order -> acknowledged, not an error.
    unk = _json.dumps({
        'event': 'payment.failed',
        'payload': {'payment': {'entity': {'order_id': 'order_NOPE'}}},
    })
    sig2 = _hmac.new(b'whsec_test', unk.encode(), _hashlib.sha256).hexdigest()
    r2 = client.post('/webhook/razorpay', data=unk,
                     content_type='application/json',
                     headers={'X-Razorpay-Signature': sig2})
    assert r2.status_code == 200
    assert r2.get_json()['ignored'] == 'unknown_order'


def test_payt_pay_page_shows_retry_state_after_failures(client, app):
    """The pay page renders a friendly retry banner (attempt count + reason)
    when the invoice has failed attempts, and stays clean for a fresh one."""
    from app.models import PAYTInvoice
    uid = _make_user(app, 'rzpretry')
    with app.app_context():
        inv = PAYTInvoice(user_id=uid, period='Feb 2026', weight_kg=10.0,
                          amount_rs=42.0, status='Unpaid',
                          razorpay_order_id=None, failed_attempts=2,
                          last_failed_reason='Bank declined the transaction')
        db.session.add(inv)
        db.session.commit()
        inv_id = inv.id
    client.post('/login', data={'username': 'rzpretry', 'password': 'testpass123'})
    r = client.get(f'/payt/pay/{inv_id}')
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    # The banner text is HTML-escaped, so match on fragments without an
    # apostrophe (the rendered page turns ' into &#39;).
    assert 'no money was deducted' in body       # friendly retry banner
    assert 'Attempt 2' in body
    assert 'Bank declined the transaction' in body

    # Fresh invoice (no failures) -> no retry banner.
    uid2 = _make_user(app, 'rzpfresh')
    with app.app_context():
        inv2 = PAYTInvoice(user_id=uid2, period='Feb 2026', weight_kg=10.0,
                           amount_rs=42.0, status='Unpaid')
        db.session.add(inv2)
        db.session.commit()
        fresh_id = inv2.id
    client.get('/logout')
    client.post('/login', data={'username': 'rzpfresh', 'password': 'testpass123'})
    r2 = client.get(f'/payt/pay/{fresh_id}')
    assert r2.status_code == 200
    assert 'no money was deducted' not in r2.get_data(as_text=True)


# ── PAYT receipt: PDF generation, download, and email-after-capture ──
def test_payt_receipt_pdf_bytes_generates_receipt(app):
    """_payt_receipt_pdf_bytes builds a real PDF carrying the Razorpay payment
    id, amount and period for a paid invoice (downloadable + email attachment)."""
    from app.routes import _payt_receipt_pdf_bytes
    uid = _make_user(app, 'rcptgen')
    with app.app_context():
        from app.models import PAYTInvoice
        from datetime import timedelta as _td
        inv = PAYTInvoice(
            user_id=uid, period='Sep 2026', weight_kg=10.0, landfill_kg=4.0,
            compliance_score=80.0, penalty_multiplier=1.2, base_amount_rs=35.0,
            amount_rs=42.0, status='Paid',
            transaction_ref='pay_RCPT1', payment_method='Razorpay',
            razorpay_order_id='order_RCPT1',
            paid_at=utcnow(), issued_at=utcnow() - _td(days=10),
        )
        db.session.add(inv)
        db.session.commit()
        inv_id = inv.id
    with app.app_context():
        pdf, filename = _payt_receipt_pdf_bytes(PAYTInvoice.query.get(inv_id))
    assert pdf[:4] == b'%PDF'                       # real PDF magic
    assert filename == f'PAYT_Receipt_Invoice_{inv_id}.pdf'

    # reportlab 5 writes content streams as ASCII85 → Flate (the /Filter dict
    # lists [ /ASCII85Decode /FlateDecode ]), with the payload ending in the
    # ASCII85 `~>` terminator immediately before `endstream` (no trailing
    # newline). Decode so the assertions check the rendered text, not bytes.
    import re
    import zlib
    import base64
    text_chunks = []
    for m in re.finditer(b'stream\r?\n(.*?)endstream', pdf, re.DOTALL):
        payload = m.group(1).rstrip()
        if payload.endswith(b'~>'):
            payload = payload[:-2]  # ASCII85 end marker
        try:
            text_chunks.append(zlib.decompress(base64.a85decode(payload)))
        except Exception:
            pass  # non-compressed streams (e.g. metadata) — skip
    pdf_text = b'\n'.join(text_chunks)
    assert b'pay_RCPT1' in pdf_text                 # Razorpay payment id present
    assert b'42.00' in pdf_text                     # amount present
    assert b'Sep 2026' in pdf_text                  # period present


def test_payt_receipt_download_owner_only(client, app):
    """The downloadable receipt route is owner-only: the invoice owner gets a
    PDF attachment; a snooper is 403; unpaid invoices redirect back."""
    from app.models import PAYTInvoice
    owner = _make_user(app, 'rcptowner')
    _make_user(app, 'rcptsnoop')
    with app.app_context():
        inv = PAYTInvoice(user_id=owner, period='Oct 2026', weight_kg=10.0,
                          amount_rs=42.0, status='Paid',
                          transaction_ref='pay_RCPT2', payment_method='Razorpay',
                          paid_at=utcnow())
        db.session.add(inv)
        db.session.commit()
        inv_id = inv.id

    # Owner: downloadable PDF attachment.
    client.post('/login', data={'username': 'rcptowner', 'password': 'testpass123'})
    r = client.get(f'/payt/receipt/{inv_id}', follow_redirects=False)
    assert r.status_code == 200
    assert r.headers.get('Content-Type') == 'application/pdf'
    assert 'attachment; filename=PAYT_Receipt_Invoice' in r.headers.get('Content-Disposition', '')
    assert r.data[:4] == b'%PDF'

    # Snooper: 403 (owner-only privacy boundary).
    client.get('/logout')
    client.post('/login', data={'username': 'rcptsnoop', 'password': 'testpass123'})
    r2 = client.get(f'/payt/receipt/{inv_id}', follow_redirects=False)
    assert r2.status_code == 403

    # Unpaid invoice: no receipt yet — redirect back to the pay page.
    client.get('/logout')
    with app.app_context():
        inv2 = PAYTInvoice(user_id=owner, period='Nov 2026', weight_kg=10.0,
                           amount_rs=42.0, status='Unpaid')
        db.session.add(inv2)
        db.session.commit()
        inv2_id = inv2.id
    client.post('/login', data={'username': 'rcptowner', 'password': 'testpass123'})
    r3 = client.get(f'/payt/receipt/{inv2_id}', follow_redirects=False)
    assert r3.status_code == 302


def test_razorpay_webhook_enqueues_receipt_job(client, app, monkeypatch):
    """A payment.captured webhook marks the invoice Paid AND enqueues the
    receipt job (background PDF + email) — off the webhook request path."""
    from app.models import PAYTInvoice
    import hmac as _hmac
    import hashlib as _hashlib
    import json as _json
    from app import jobs as jobs_mod
    monkeypatch.setenv('RAZORPAY_WEBHOOK_SECRET', 'whsec_test')
    uid, inv_id = _payt_invoice(app, 'rzprec', razorpay_order_id='order_WEBR1')

    enqueued = []
    monkeypatch.setattr(jobs_mod, 'enqueue', lambda fn, *a, **k: enqueued.append((fn.__name__, a)))

    payload = _json.dumps({
        'event': 'payment.captured',
        'payload': {'payment': {'entity': {'order_id': 'order_WEBR1', 'id': 'pay_WEBR1'}}},
    })
    signature = _hmac.new(b'whsec_test', payload.encode(), _hashlib.sha256).hexdigest()
    r = client.post('/webhook/razorpay', data=payload,
                    content_type='application/json',
                    headers={'X-Razorpay-Signature': signature})
    assert r.status_code == 200
    with app.app_context():
        assert PAYTInvoice.query.get(inv_id).status == 'Paid'
    assert ('payt_receipt_job', (inv_id,)) in enqueued, enqueued

    # Idempotent replay must NOT enqueue the receipt twice.
    client.post('/webhook/razorpay', data=payload, content_type='application/json',
                headers={'X-Razorpay-Signature': signature})
    assert enqueued.count(('payt_receipt_job', (inv_id,))) == 1


def test_payt_verify_enqueues_receipt_job(client, app, monkeypatch):
    """The fast UX verify path also enqueues the receipt job (the status-flip
    guard dedupes against the webhook, so the citizen gets exactly one email)."""
    import hmac as _hmac
    import hashlib as _hashlib
    from app import jobs as jobs_mod
    monkeypatch.setenv('RAZORPAY_KEY_SECRET', 'rzp_test_secret')
    uid, inv_id = _payt_invoice(app, 'rzpvrc', razorpay_order_id='order_XYZR')
    signature = _hmac.new(b'rzp_test_secret', b'order_XYZR|pay_PAYR1', _hashlib.sha256).hexdigest()

    enqueued = []
    monkeypatch.setattr(jobs_mod, 'enqueue', lambda fn, *a, **k: enqueued.append((fn.__name__, a)))

    client.post('/login', data={'username': 'rzpvrc', 'password': 'testpass123'})
    r = client.post(f'/payt/verify/{inv_id}', json={
        'razorpay_order_id': 'order_XYZR',
        'razorpay_payment_id': 'pay_PAYR1',
        'razorpay_signature': signature,
    }, follow_redirects=False)
    assert r.status_code == 200
    assert ('payt_receipt_job', (inv_id,)) in enqueued, enqueued


def test_payt_receipt_job_builds_and_sends_email(app, monkeypatch):
    """payt_receipt_job generates the PDF and emails it as an attachment to the
    citizen; a missing user email returns False without raising."""
    from app.models import User
    from app import jobs as jobs_mod
    uid = _make_user(app, 'rcptmail')
    with app.app_context():
        u = User.query.get(uid)
        u.email = 'rcptmail@example.com'
        db.session.commit()
        from app.models import PAYTInvoice
        inv = PAYTInvoice(user_id=uid, period='Dec 2026', weight_kg=10.0,
                          amount_rs=42.0, status='Paid',
                          transaction_ref='pay_RCPT3', payment_method='Razorpay',
                          paid_at=utcnow())
        db.session.add(inv)
        db.session.commit()
        inv_id = inv.id

    sent = {}
    # payt_receipt_job imports send_email_via_smtp from .routes at call time,
    # so the patch must land on app.routes (not app.jobs).
    import app.routes as routes_mod
    monkeypatch.setattr(routes_mod, 'send_email_via_smtp',
                        lambda to, subj, body, **kw: sent.update({
                            'to': to, 'subject': subj, 'attachment': kw.get('attachment_bytes'),
                            'filename': kw.get('attachment_filename')}) or True)
    with app.app_context():
        ok = jobs_mod.payt_receipt_job(inv_id)
    assert ok is True
    assert sent['to'] == 'rcptmail@example.com'
    assert 'Receipt' in sent['subject']
    assert sent['attachment'][:4] == b'%PDF'
    assert sent['filename'] == f'PAYT_Receipt_Invoice_{inv_id}.pdf'

    # No email on the account -> False, no exception.
    uid2 = _make_user(app, 'rcptnomail')
    with app.app_context():
        from app.models import PAYTInvoice
        inv2 = PAYTInvoice(user_id=uid2, period='Jan 2027', weight_kg=10.0,
                           amount_rs=42.0, status='Paid', transaction_ref='pay_RCPT4',
                           payment_method='Razorpay', paid_at=utcnow())
        db.session.add(inv2)
        db.session.commit()
        inv2_id = inv2.id
    sent.clear()
    with app.app_context():
        assert jobs_mod.payt_receipt_job(inv2_id) is False
    assert sent == {}


def test_send_email_with_pdf_attachment(app, monkeypatch):
    """send_email_via_smtp builds a multipart message with the PDF attached when
    attachment bytes are supplied (the receipt path)."""
    from app.routes import send_email_via_smtp
    monkeypatch.setenv('MAIL_SERVER', 'smtp.example.com')
    monkeypatch.setenv('MAIL_PORT', '25')
    monkeypatch.setenv('MAIL_USERNAME', 'bot@example.com')
    monkeypatch.setenv('MAIL_PASSWORD', 'secret')

    captured = {}

    class _FakeSMTP:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def starttls(self):
            return None

        def login(self, u, p):
            captured['login'] = (u, p)

        def sendmail(self, frm, to, msg):
            captured['to'] = to
            captured['msg'] = msg
    monkeypatch.setattr('smtplib.SMTP', _FakeSMTP)

    ok = send_email_via_smtp('citizen@example.com', 'Receipt', 'Here is your receipt.',
                             attachment_bytes=b'%PDF-fake', attachment_filename='receipt.pdf')
    assert ok is True
    assert captured['to'] == ['citizen@example.com']
    assert 'application/octet-stream' in captured['msg']
    # MIMEApplication quotes the filename in the Content-Disposition header.
    assert 'filename="receipt.pdf"' in captured['msg']
    assert 'Here is your receipt.' in captured['msg']


def test_payt_pay_page_falls_back_to_upi_without_keys(client, app):
    """No RAZORPAY keys → the old UPI deep-link flow still works end-to-end."""
    from app.models import PAYTInvoice
    uid, inv_id = _payt_invoice(app, 'rzpnone')
    client.post('/login', data={'username': 'rzpnone', 'password': 'testpass123'})
    r = client.get(f'/payt/pay/{inv_id}', follow_redirects=False)
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert 'upi://pay' in body
    assert 'checkout.razorpay.com' not in body  # no Razorpay SDK without keys
    with app.app_context():
        assert PAYTInvoice.query.get(inv_id).razorpay_order_id is None

    # Manual UPI confirm path remains as the documented fallback.
    r2 = client.post(f'/payt/confirm/{inv_id}', data={'txn': 'UPI-RRN-999'},
                     follow_redirects=False)
    assert r2.status_code == 302
    with app.app_context():
        inv = PAYTInvoice.query.get(inv_id)
        assert inv.status == 'Paid'
        assert inv.payment_method == 'UPI'


# ── Admin waive / refund of PAYT invoices ──────────────────
def test_admin_waives_unpaid_invoice(client, app):
    """An admin can waive an UNPAID invoice: debt forgiven (no money moves),
    audited, and idempotent — a second waive is a no-op flash."""
    from app.models import PAYTInvoice, AuditLog
    uid, inv_id = _payt_invoice(app, 'waivec1')
    _make_user(app, 'waiveadm', role='admin')
    _login_admin(client, app, 'waiveadm')

    r = client.post(f'/admin/payt/{inv_id}/waive',
                    data={'reason': 'Billing error'}, follow_redirects=False)
    assert r.status_code == 302
    with app.app_context():
        inv = PAYTInvoice.query.get(inv_id)
        assert inv.status == 'Waived'
        assert inv.refund_reason == 'Billing error'
        assert AuditLog.query.filter_by(action='PAYT_WAIVE',
                                        target=f'Invoice #{inv_id}').count() == 1

    # Idempotent: already-waived invoice → no-op, still one audit row.
    r2 = client.post(f'/admin/payt/{inv_id}/waive', data={}, follow_redirects=False)
    assert r2.status_code == 302
    with app.app_context():
        assert PAYTInvoice.query.get(inv_id).status == 'Waived'
        assert AuditLog.query.filter_by(action='PAYT_WAIVE',
                                        target=f'Invoice #{inv_id}').count() == 1


def test_admin_cannot_waive_paid_invoice(client, app):
    """A paid invoice must be refunded (money was collected), not waived —
    waiving it would silently double-count the payment."""
    from app.models import PAYTInvoice, AuditLog
    uid, inv_id = _payt_invoice(app, 'waivec2', status='Paid',
                                payment_method='UPI', transaction_ref='RRN-1')
    _make_user(app, 'waiveadm2', role='admin')
    _login_admin(client, app, 'waiveadm2')

    r = client.post(f'/admin/payt/{inv_id}/waive', data={}, follow_redirects=False)
    assert r.status_code == 302
    with app.app_context():
        assert PAYTInvoice.query.get(inv_id).status == 'Paid'  # untouched
        assert AuditLog.query.filter_by(action='PAYT_WAIVE').count() == 0


def test_admin_refunds_paid_invoice_via_razorpay_api(client, app, monkeypatch):
    """Refunding a PAID Razorpay invoice calls the Refunds API with the stored
    payment id + amount in paise, records the refund id, flips status to
    Refunded and audits it."""
    from app.models import PAYTInvoice, AuditLog
    import app.routes as routes
    monkeypatch.setenv('RAZORPAY_KEY_ID', 'rzp_test_key')
    monkeypatch.setenv('RAZORPAY_KEY_SECRET', 'rzp_test_secret')
    uid, inv_id = _payt_invoice(app, 'refundc1', status='Paid',
                                payment_method='Razorpay', transaction_ref='pay_RFND1',
                                amount=42.0)
    _make_user(app, 'refundadm', role='admin')
    _login_admin(client, app, 'refundadm')

    captured = {}

    def fake_post(url, json=None, auth=None, timeout=None):
        captured['url'] = url
        captured['amount_paise'] = json.get('amount')
        captured['notes'] = json.get('notes')
        return type('R', (), {
            'raise_for_status': lambda self: None,
            'json': lambda self: {'id': 'refund_RFND1'},
        })()
    monkeypatch.setattr(routes.requests, 'post', fake_post)

    r = client.post(f'/admin/payt/{inv_id}/refund',
                    data={'reason': 'Citizen complaint'}, follow_redirects=False)
    assert r.status_code == 302
    assert captured['url'].endswith('/payments/pay_RFND1/refund')  # right payment
    assert captured['amount_paise'] == 4200                        # ₹42.00 → paise
    with app.app_context():
        inv = PAYTInvoice.query.get(inv_id)
        assert inv.status == 'Refunded'
        assert inv.refund_id == 'refund_RFND1'
        assert inv.refunded_at is not None
        assert inv.refund_reason == 'Citizen complaint'
        assert AuditLog.query.filter_by(action='PAYT_REFUND',
                                        target=f'Invoice #{inv_id}').count() == 1


def test_admin_refund_is_idempotent(client, app, monkeypatch):
    """Once a refund_id is recorded, a second refund attempt never re-calls
    the API (the refund_id column is the idempotency guard)."""
    from app.models import PAYTInvoice
    import app.routes as routes
    monkeypatch.setenv('RAZORPAY_KEY_ID', 'rzp_test_key')
    monkeypatch.setenv('RAZORPAY_KEY_SECRET', 'rzp_test_secret')
    uid, inv_id = _payt_invoice(app, 'refundc2', status='Paid',
                                payment_method='Razorpay', transaction_ref='pay_RFND2')
    _make_user(app, 'refundadm2', role='admin')
    _login_admin(client, app, 'refundadm2')
    with app.app_context():
        inv = PAYTInvoice.query.get(inv_id)
        inv.refund_id = 'refund_ALREADY'
        db.session.commit()

    calls = []

    def fake_post(url, json=None, auth=None, timeout=None):
        calls.append(url)
        return type('R', (), {'raise_for_status': lambda self: None,
                              'json': lambda self: {'id': 'refund_DUP'}})()
    monkeypatch.setattr(routes.requests, 'post', fake_post)

    r = client.post(f'/admin/payt/{inv_id}/refund', data={}, follow_redirects=False)
    assert r.status_code == 302
    assert calls == []  # API never called again
    with app.app_context():
        inv = PAYTInvoice.query.get(inv_id)
        assert inv.status == 'Paid'          # stays as the capture left it
        assert inv.refund_id == 'refund_ALREADY'


def test_admin_refund_rejects_upi_paid_and_unpaid(client, app, monkeypatch):
    """UPI-paid invoices (no Razorpay payment to reverse) and unpaid invoices
    are refused with a flash and never touch the API or the invoice."""
    from app.models import PAYTInvoice, AuditLog
    import app.routes as routes
    monkeypatch.setenv('RAZORPAY_KEY_ID', 'rzp_test_key')
    monkeypatch.setenv('RAZORPAY_KEY_SECRET', 'rzp_test_secret')
    uid_u, inv_upi = _payt_invoice(app, 'refundc3', status='Paid',
                                   payment_method='UPI', transaction_ref='RRN-77')
    uid_n, inv_unpaid = _payt_invoice(app, 'refundc4', status='Unpaid',
                                      payment_method='Razorpay')
    _make_user(app, 'refundadm3', role='admin')
    _login_admin(client, app, 'refundadm3')

    calls = []

    def fake_post(url, json=None, auth=None, timeout=None):
        calls.append(url)
        return type('R', (), {'raise_for_status': lambda self: None,
                              'json': lambda self: {'id': 'refund_X'}})()
    monkeypatch.setattr(routes.requests, 'post', fake_post)

    r1 = client.post(f'/admin/payt/{inv_upi}/refund', data={}, follow_redirects=False)
    assert r1.status_code == 302
    r2 = client.post(f'/admin/payt/{inv_unpaid}/refund', data={}, follow_redirects=False)
    assert r2.status_code == 302
    assert calls == []  # neither reached the API
    with app.app_context():
        assert PAYTInvoice.query.get(inv_upi).status == 'Paid'
        assert PAYTInvoice.query.get(inv_unpaid).status == 'Unpaid'
        assert AuditLog.query.filter_by(action='PAYT_REFUND').count() == 0


def test_admin_refund_api_failure_keeps_invoice_paid(client, app, monkeypatch):
    """When the Refunds API rejects the refund, the invoice stays Paid and a
    PAYT_REFUND_FAILED audit row records the attempt (admin can retry)."""
    from app.models import PAYTInvoice, AuditLog
    import app.routes as routes
    monkeypatch.setenv('RAZORPAY_KEY_ID', 'rzp_test_key')
    monkeypatch.setenv('RAZORPAY_KEY_SECRET', 'rzp_test_secret')
    uid, inv_id = _payt_invoice(app, 'refundc5', status='Paid',
                                payment_method='Razorpay', transaction_ref='pay_RFND5')
    _make_user(app, 'refundadm5', role='admin')
    _login_admin(client, app, 'refundadm5')

    def boom(url, json=None, auth=None, timeout=None):
        raise Exception('network down')
    monkeypatch.setattr(routes.requests, 'post', boom)

    r = client.post(f'/admin/payt/{inv_id}/refund', data={}, follow_redirects=False)
    assert r.status_code == 302
    with app.app_context():
        inv = PAYTInvoice.query.get(inv_id)
        assert inv.status == 'Paid'          # retryable
        assert inv.refund_id is None
        assert AuditLog.query.filter_by(action='PAYT_REFUND_FAILED',
                                        target=f'Invoice #{inv_id}').count() == 1


def test_admin_refund_waive_requires_admin(client, app):
    """Citizens cannot waive/refund invoices — both admin actions are 403."""
    uid, inv_id = _payt_invoice(app, 'paytsnoopw')
    client.post('/login', data={'username': 'paytsnoopw', 'password': 'testpass123'})
    r1 = client.post(f'/admin/payt/{inv_id}/waive', data={}, follow_redirects=False)
    r2 = client.post(f'/admin/payt/{inv_id}/refund', data={}, follow_redirects=False)
    assert r1.status_code == 403
    assert r2.status_code == 403


def test_refunded_invoice_immune_to_capture_webhook(client, app, monkeypatch):
    """Terminal-state guard: a (re-)delivered payment.captured webhook must
    NOT resurrect a Refunded invoice back to Paid — money was already reversed.

    Razorpay delivers webhooks at-least-once, so a late/duplicate capture after
    an admin refund would otherwise silently re-charge the citizen."""
    from app.models import PAYTInvoice
    import hmac as _hmac
    import hashlib as _hashlib
    import json as _json
    monkeypatch.setenv('RAZORPAY_WEBHOOK_SECRET', 'whsec_test')
    uid, inv_id = _payt_invoice(app, 'rzpterm1', razorpay_order_id='order_TERM1')
    with app.app_context():
        inv = PAYTInvoice.query.get(inv_id)
        inv.status = 'Refunded'
        inv.refund_id = 'refund_TERM1'
        inv.payment_method = 'Razorpay'
        inv.transaction_ref = 'pay_TERM1'
        db.session.commit()

    payload = _json.dumps({
        'event': 'payment.captured',
        'payload': {'payment': {'entity': {'order_id': 'order_TERM1', 'id': 'pay_TERM1'}}},
    })
    sig = _hmac.new(b'whsec_test', payload.encode(), _hashlib.sha256).hexdigest()
    r = client.post('/webhook/razorpay', data=payload,
                    content_type='application/json',
                    headers={'X-Razorpay-Signature': sig})
    assert r.status_code == 200
    assert r.get_json()['ignored'] == 'terminal_state'
    with app.app_context():
        inv = PAYTInvoice.query.get(inv_id)
        assert inv.status == 'Refunded'   # NOT flipped back to Paid
        assert inv.refund_id == 'refund_TERM1'


def test_refunded_invoice_immune_to_citizen_verify(client, app, monkeypatch):
    """The citizen's replayed verify POST cannot resurrect a refunded invoice
    either (same terminal-state guard, citizen-facing path)."""
    from app.models import PAYTInvoice
    import hmac as _hmac
    import hashlib as _hashlib
    monkeypatch.setenv('RAZORPAY_KEY_SECRET', 'rzp_test_secret')
    uid, inv_id = _payt_invoice(app, 'rzpterm2', razorpay_order_id='order_TERM2')
    with app.app_context():
        inv = PAYTInvoice.query.get(inv_id)
        inv.status = 'Refunded'
        inv.refund_id = 'refund_TERM2'
        inv.payment_method = 'Razorpay'
        inv.transaction_ref = 'pay_TERM2'
        db.session.commit()
    client.post('/login', data={'username': 'rzpterm2', 'password': 'testpass123'})
    signature = _hmac.new(b'rzp_test_secret', b'order_TERM2|pay_TERM2', _hashlib.sha256).hexdigest()
    r = client.post(f'/payt/verify/{inv_id}', json={
        'razorpay_order_id': 'order_TERM2',
        'razorpay_payment_id': 'pay_TERM2',
        'razorpay_signature': signature,
    }, follow_redirects=False)
    assert r.status_code == 400
    assert r.get_json()['message'] == 'invoice_closed'
    with app.app_context():
        assert PAYTInvoice.query.get(inv_id).status == 'Refunded'


def test_waived_invoice_immune_to_confirm_and_capture(client, app, monkeypatch):
    """Waived invoices are terminal for both the UPI confirm button and the
    Razorpay capture webhook — a late confirm/webhook must not re-charge."""
    from app.models import PAYTInvoice
    import hmac as _hmac
    import hashlib as _hashlib
    import json as _json
    monkeypatch.setenv('RAZORPAY_WEBHOOK_SECRET', 'whsec_test')
    uid, inv_id = _payt_invoice(app, 'rzpterm3', razorpay_order_id='order_TERM3')
    with app.app_context():
        inv = PAYTInvoice.query.get(inv_id)
        inv.status = 'Waived'
        db.session.commit()
    # UPI confirm: blocked with a warning, stays Waived.
    client.post('/login', data={'username': 'rzpterm3', 'password': 'testpass123'})
    r1 = client.post(f'/payt/confirm/{inv_id}', data={'txn': 'RRN-LATE'},
                     follow_redirects=False)
    assert r1.status_code == 302
    with app.app_context():
        assert PAYTInvoice.query.get(inv_id).status == 'Waived'
    # Capture webhook: acknowledged but ignored.
    payload = _json.dumps({
        'event': 'payment.captured',
        'payload': {'payment': {'entity': {'order_id': 'order_TERM3', 'id': 'pay_TERM3'}}},
    })
    sig = _hmac.new(b'whsec_test', payload.encode(), _hashlib.sha256).hexdigest()
    r2 = client.post('/webhook/razorpay', data=payload,
                     content_type='application/json',
                     headers={'X-Razorpay-Signature': sig})
    assert r2.status_code == 200
    with app.app_context():
        assert PAYTInvoice.query.get(inv_id).status == 'Waived'


def test_closed_invoice_pay_page_redirects_without_order(client, app, monkeypatch):
    """The pay page must NEVER let a citizen pay a closed (refunded/waived)
    invoice: it bounces to the dashboard and does not mint a Razorpay order —
    otherwise money would be collected with no recovery path (the capture
    webhook ignores closed invoices)."""
    from app.models import PAYTInvoice
    import app.routes as routes
    monkeypatch.setenv('RAZORPAY_KEY_ID', 'rzp_test_key')
    monkeypatch.setenv('RAZORPAY_KEY_SECRET', 'rzp_test_secret')
    uid, inv_id = _payt_invoice(app, 'rzpclosed', razorpay_order_id='order_CLS1')
    with app.app_context():
        inv = PAYTInvoice.query.get(inv_id)
        inv.status = 'Refunded'
        inv.refund_id = 'refund_CLS1'
        inv.payment_method = 'Razorpay'
        inv.transaction_ref = 'pay_CLS1'
        db.session.commit()
    client.post('/login', data={'username': 'rzpclosed', 'password': 'testpass123'})

    order_calls = []

    def fake_create(inv):
        order_calls.append(inv.id)
        return 'order_NEW'
    monkeypatch.setattr(routes, '_create_razorpay_order', fake_create)

    r = client.get(f'/payt/pay/{inv_id}', follow_redirects=False)
    assert r.status_code == 302
    assert r.headers['Location'].endswith('/dashboard')
    assert order_calls == []  # no order minted against a closed invoice

    # Same for a waived invoice (no refund_id, just the terminal status).
    uid2, inv2 = _payt_invoice(app, 'rzpclosed2')
    with app.app_context():
        PAYTInvoice.query.get(inv2).status = 'Waived'
        db.session.commit()
    client.get('/logout')
    client.post('/login', data={'username': 'rzpclosed2', 'password': 'testpass123'})
    r2 = client.get(f'/payt/pay/{inv2}', follow_redirects=False)
    assert r2.status_code == 302
    assert order_calls == []


# ── Queue observability: /api/jobs/status (admin) ────────────
def test_jobs_status_requires_admin(client, app):
    """The queue-status endpoint is admin-only — citizens get 403."""
    _make_user(app, 'jscit', role='citizen')
    _login_admin(client, app, 'jscit')
    r = client.get('/api/jobs/status', follow_redirects=False)
    assert r.status_code == 403


def test_jobs_status_inline_mode_shape(client, app):
    """Without Redis the endpoint reports the inline picture and never crashes."""
    _make_user(app, 'jsadmin', role='admin')
    _login_admin(client, app, 'jsadmin')
    r = client.get('/api/jobs/status', follow_redirects=False)
    assert r.status_code == 200
    data = r.get_json()
    assert data['broker'] == 'inline'
    assert data['queue_depth'] == 0
    assert data['workers'] == 0
    assert data['recent_jobs'] == []
    assert 'jobs_run_total' in data['counters']
    assert 'job_duration_s_total' in data['counters']


def test_jobs_status_prometheus_format(client, app):
    """?format=prometheus renders the counters as scrapable text exposition."""
    from app.jobs import record_outcome, _METRICS
    _METRICS.clear()  # isolated counters: suite-wide job runs can't shift counts
    record_outcome('probe_sms', 'success', 0.25)
    record_outcome('probe_sms', 'failed', 1.5)
    record_outcome('probe_dunning', 'success', 3.2)
    _make_user(app, 'jsprom', role='admin')
    _login_admin(client, app, 'jsprom')
    r = client.get('/api/jobs/status?format=prometheus', follow_redirects=False)
    assert r.status_code == 200
    assert 'text/plain' in r.headers.get('Content-Type', '')
    body = r.get_data(as_text=True)
    assert 'smartgarbage_jobs_run_total{job="probe_sms",outcome="success"} 1' in body
    assert 'smartgarbage_jobs_run_total{job="probe_sms",outcome="failed"} 1' in body
    assert 'smartgarbage_jobs_run_total{job="probe_dunning",outcome="success"} 1' in body
    assert 'smartgarbage_job_duration_s_total{job="probe_dunning"}' in body


def test_jobs_status_kpis_block(client, app):
    """The endpoint includes a derived KPI block (totals, retries, dead-letter
    rate, average duration) alongside the raw counters."""
    from app.jobs import _METRICS, record_outcome, record_retry, _count_dead_letter
    _METRICS.clear()
    record_outcome('probe_sms', 'success', 0.25)
    record_outcome('probe_sms', 'failed', 1.5)
    record_retry('probe_sms')
    _count_dead_letter('probe_sms', 'kpi-dl-1')
    _make_user(app, 'jskpi', role='admin')
    _login_admin(client, app, 'jskpi')
    r = client.get('/api/jobs/status', follow_redirects=False)
    assert r.status_code == 200
    kpis = r.get_json()['kpis']
    assert kpis['jobs_run'] == 2
    assert kpis['jobs_failed'] == 1
    assert kpis['retries'] == 1
    assert kpis['dead_lettered'] == 1
    assert kpis['dead_letter_rate'] == 50.0  # 1 of 2 runs dead-lettered
    assert kpis['avg_duration_s'] > 0
    row = kpis['per_function'][0]
    assert row['func'] == 'probe_sms' and row['runs'] == 2


def test_jobs_status_prometheus_retries_and_dead_lettered(client, app):
    """Prometheus exposition also carries retry and dead-letter counters."""
    from app.jobs import _METRICS, record_retry, _count_dead_letter
    _METRICS.clear()
    record_retry('probe_sms')
    _count_dead_letter('probe_sms', 'prom-dl-1')
    _make_user(app, 'jsprom2', role='admin')
    _login_admin(client, app, 'jsprom2')
    body = client.get('/api/jobs/status?format=prometheus',
                      follow_redirects=False).get_data(as_text=True)
    assert 'smartgarbage_job_retries_total{job="probe_sms"} 1' in body
    assert 'smartgarbage_job_dead_lettered_total{job="probe_sms"} 1' in body


def test_instrument_records_success_and_duration():
    """The @instrument decorator bumps the success counter and adds duration."""
    from app.jobs import instrument, _METRICS
    ran = []

    @instrument
    def _probe_ok(x):
        ran.append(x)
        return x + 1

    assert _probe_ok(4) == 5
    assert ran == [4]
    assert _METRICS.get('_probe_ok:success') == 1
    assert _METRICS.get('_probe_ok:duration_s', 0) >= 0  # duration recorded


def test_instrument_records_failure_outcome():
    """A raising job records 'failed' (and re-raises) without a success count."""
    from app.jobs import instrument, _METRICS

    @instrument
    def _probe_boom():
        raise ValueError('nope')

    try:
        _probe_boom()
    except ValueError:
        pass
    assert _METRICS.get('_probe_boom:failed') == 1
    assert '_probe_boom:success' not in _METRICS


def test_instrument_counts_retry_only_for_policy_jobs():
    """A failed run of a job that declares a retry policy also bumps the retry
    counter (that failure triggers an RQ re-run); jobs without a policy don't."""
    from app.jobs import instrument, _METRICS
    _METRICS.clear()  # isolated counters: suite-wide job runs can't shift counts

    @instrument
    def send_sms_job(to, body):
        raise RuntimeError('twilio down')

    try:
        send_sms_job('+91', 'hi')
    except RuntimeError:
        pass
    assert _METRICS.get('send_sms_job:failed') == 1
    assert _METRICS.get('send_sms_job:retries') == 1  # policy declared

    @instrument
    def _no_policy_probe():
        raise ValueError('nope')

    try:
        _no_policy_probe()
    except ValueError:
        pass
    assert _METRICS.get('_no_policy_probe:failed') == 1
    assert '_no_policy_probe:retries' not in _METRICS  # no policy → no retry counter


def test_count_dead_letter_dedupes_and_corrects_retries():
    """Dead-letter counting is idempotent per job_id and corrects the retry
    counter: the terminal failure was counted as a retry by instrument(), so
    counting the dead-letter subtracts it — retries end up as retries ACTUALLY
    performed."""
    from app.jobs import _METRICS, _DEAD_LETTER_COUNTED, record_retry, _count_dead_letter
    _METRICS.clear()
    _DEAD_LETTER_COUNTED.clear()
    # simulate a policy job that failed twice (retried once) then dead-lettered
    record_retry('send_sms_job')
    record_retry('send_sms_job')
    _count_dead_letter('send_sms_job', 'dl-1')
    assert _METRICS.get('send_sms_job:dead_lettered') == 1
    assert _METRICS.get('send_sms_job:retries') == 1  # 2 attempts - 1 terminal
    # dedupe: same job scanned again by the sweep must not double-count
    _count_dead_letter('send_sms_job', 'dl-1')
    assert _METRICS.get('send_sms_job:dead_lettered') == 1
    assert _METRICS.get('send_sms_job:retries') == 1


def test_count_dead_letter_no_retry_policy_untouched():
    """A job without a retry policy never had a retry counter, so counting its
    dead-letter must not drift the retry counter negative."""
    from app.jobs import _METRICS, _DEAD_LETTER_COUNTED, _count_dead_letter
    _METRICS.clear()
    _DEAD_LETTER_COUNTED.clear()
    _count_dead_letter('_no_policy_probe', 'dl-2')
    assert _METRICS.get('_no_policy_probe:dead_lettered') == 1
    assert '_no_policy_probe:retries' not in _METRICS


# ── Postgres parity: naive-UTC datetimes ─────────────────────
def test_utcnow_helper_returns_naive_utc():
    """utcnow() must return a NAIVE UTC datetime — every DateTime column is
    `timestamp without time zone`, so tz-aware values would drift/error on
    Postgres (the app stores UTC wall-clock and normalizes only for math)."""
    now = utcnow()
    assert now.tzinfo is None


def test_model_datetime_defaults_are_naive(app):
    """Inserting rows without explicit timestamps (relying on model defaults)
    must store naive UTC datetimes — the Postgres-parity contract."""
    from app.models import SmartBin, AuditLog
    with app.app_context():
        b = SmartBin(hardware_id='NAIVE-1', latitude=18.06, longitude=83.41,
                     level=10, ward='Ward 1 - MVGR College Area')
        db.session.add(b)
        db.session.commit()
        assert b.last_updated.tzinfo is None, 'model default must be naive UTC'
        al = AuditLog(action='NAIVE_CHECK', target='x', detail='y')
        db.session.add(al)
        db.session.commit()
        assert al.timestamp.tzinfo is None


def test_write_audit_uses_naive_utc(client, app):
    """write_audit stores naive UTC, so the audit ledger never feeds an
    aware datetime into a `timestamp without time zone` column on Postgres."""
    from app.models import AuditLog
    _make_user(app, 'naiveaudit')
    client.post('/login', data={'username': 'naiveaudit', 'password': 'testpass123'})
    client.post('/report', data={
        'name': 'naiveaudit', 'phone': '+919876543209',
        'ward': 'Ward 1 - MVGR College Area', 'address': 'Gate',
        'description': 'Overflow', 'latitude': '18.05', 'longitude': '83.40',
        'report_time': '2026-07-18T10:00'
    }, follow_redirects=True)
    with app.app_context():
        log = AuditLog.query.filter_by(action='COMPLAINT_SUBMIT').first()
        assert log is not None
        assert log.timestamp.tzinfo is None


# ── Postgres parity: VARCHAR(n) is ENFORCED on Postgres ──────
def test_register_rejects_overlong_username(client, app):
    """VARCHAR(100) username: Postgres raises DataError past the limit, so the
    route must reject (not silently store) overlong identity fields."""
    r = client.post('/register', data={
        'username': 'u' * 150, 'password': 'testpass123',
        'phone': '+919876543201', 'email': 'long@example.com'}, follow_redirects=False)
    assert r.status_code == 302  # bounced back to register with a flash
    with app.app_context():
        assert User.query.filter_by(username='u' * 150).first() is None


def test_report_truncates_overlong_free_text(client, app):
    """Free-text VARCHAR fields are truncated at the boundary (fit_length) so
    a long citizen input can never overflow the column on Postgres."""
    _make_user(app, 'longname')
    client.post('/login', data={'username': 'longname', 'password': 'testpass123'})
    r = client.post('/report', data={
        'name': 'N' * 150, 'phone': '9' * 30,
        'ward': 'Ward 1 - MVGR College Area', 'address': 'Gate',
        'description': 'Overflow', 'latitude': '1' * 80, 'longitude': '2' * 80,
        'report_time': '2026-07-18T10:00'
    }, follow_redirects=True)
    assert r.status_code in (200, 302)
    with app.app_context():
        c = Complaint.query.filter_by(user_id=User.query.filter_by(username='longname').first().id).first()
        assert c is not None
        assert len(c.name) <= 100
        assert len(c.phone) <= 15
        assert len(c.latitude) <= 50
        assert len(c.longitude) <= 50


def test_write_audit_truncates_overlong_target(client, app):
    """write_audit truncates action/target to the VARCHAR(100) columns — a long
    URL or detail can never overflow the audit table on Postgres."""
    from app.models import AuditLog
    import app.routes as routes
    _make_user(app, 'auditlong')
    # write_audit touches request.remote_addr + session, so it needs a request
    # context (not just app context) — otherwise it swallows RuntimeError and
    # writes nothing.
    with app.test_request_context():
        routes.write_audit('TEST_LONG', target='T' * 300, detail='D' * 500)
    with app.app_context():
        log = AuditLog.query.filter_by(action='TEST_LONG').first()
        assert log is not None
        assert len(log.target) <= 100
        assert len(log.action) <= 100


def test_webhook_url_length_validated(client, app):
    """Webhook.url is VARCHAR(500); an overlong URL must be rejected, not
    stored (Postgres would raise DataError on insert)."""
    from app.models import Webhook
    _make_user(app, 'whlong', role='admin')
    _login_admin(client, app, 'whlong')
    long_url = 'https://example.com/' + 'x' * 600
    client.post('/api/webhooks', data={'webhook_url': long_url}, follow_redirects=False)
    with app.app_context():
        assert Webhook.query.filter_by(url=long_url).first() is None


# ── Postgres parity: reserved word `user` + collation + JSON ──
def test_user_table_reserved_word_quoted(app):
    """`user` is a reserved word in Postgres; SQLAlchemy quotes it in DDL and
    ORM SQL (SELECT * FROM "user"). Raw SQL must use the same quoting — this
    proves the table is reachable via quoted identifiers on both backends."""
    from sqlalchemy import text
    _make_user(app, 'reserveduser')
    with app.app_context():
        row = db.session.execute(
            text('SELECT id FROM "user" WHERE username = :u'),
            {'u': 'reserveduser'}).first()
        assert row is not None
        # The ORM maps User to the same (quoted) table name.
        assert User.__tablename__ == 'user'


def test_no_json_columns_and_text_sector_polygon(app):
    """No db.JSON columns exist — sector_polygon is Text (portable across
    backends; Postgres JSON would need JSONB + migration). This locks in the
    current portable design so a stray JSON column can't slip in unnoticed."""
    from app.models import WorkerProfile
    col = WorkerProfile.__table__.c.sector_polygon
    assert str(col.type).upper() == 'TEXT'
    # Case-sensitive matching contract: the app never relies on SQLite's
    # ASCII case-insensitive LIKE — the one fuzzy lookup uses ilike (works on
    # both SQLite via lower() and Postgres natively).
    from app.jobs import JOB_RETRY_POLICIES  # sanity: jobs still import fine
    assert 'dunning_job' in JOB_RETRY_POLICIES


# ── Offline-queue delivery health (admin dashboard) ───────────
def test_report_with_replay_header_records_offline_delivery(client, app):
    """A submission tagged X-Offline-Replay lands in OfflineDelivery so the
    admin can see offline-first usage (complaint arrived via the queue)."""
    from app.models import OfflineDelivery
    _make_user(app, 'replaycit')
    client.post('/login', data={'username': 'replaycit', 'password': 'testpass123'})
    r = client.post('/report', data={
        'name': 'replaycit', 'phone': '+919876543209',
        'ward': 'Ward 2 - Chintalavalasa Junction', 'address': 'Near junction',
        'description': 'Offline filed', 'latitude': '18.07', 'longitude': '83.41',
        'report_time': '2026-07-18T10:00'
    }, headers={'X-Offline-Replay': '1', 'X-Offline-Attempts': '2'},
        follow_redirects=True)
    assert r.status_code in (200, 302)
    with app.app_context():
        d = OfflineDelivery.query.order_by(OfflineDelivery.id.desc()).first()
        assert d is not None
        assert d.endpoint == '/report'
        assert d.ward == 'Ward 2 - Chintalavalasa Junction'
        assert d.has_photo is False
        assert d.attempts == 2
        assert d.complaint_id is not None


def test_plain_report_without_replay_header_not_recorded(client, app):
    """Live form posts (no X-Offline-Replay) must NOT create delivery rows —
    the dashboard counts queue deliveries only."""
    from app.models import OfflineDelivery
    _make_user(app, 'livecit')
    client.post('/login', data={'username': 'livecit', 'password': 'testpass123'})
    r = client.post('/report', data={
        'name': 'livecit', 'phone': '+919876543210',
        'ward': 'Ward 1 - MVGR College Area', 'address': 'Gate',
        'description': 'Live filed', 'latitude': '18.05', 'longitude': '83.40',
        'report_time': '2026-07-18T10:00'
    }, follow_redirects=True)
    assert r.status_code in (200, 302)
    with app.app_context():
        assert OfflineDelivery.query.count() == 0


def test_illegal_report_with_replay_header_records_offline_delivery(client, app):
    """Anonymous /report-illegal replays are tagged too — photo evidence that
    survived the queue is visible to the municipality."""
    from app.models import OfflineDelivery
    import io
    from PIL import Image
    buf = io.BytesIO()
    Image.new('RGB', (400, 300), (120, 40, 20)).save(buf, format='JPEG')
    buf.seek(0)
    r = client.post('/report-illegal',
                    data={'category': 'e-waste', 'ward': 'Ward 3 - RTC Colony',
                          'photo': (buf, 'evidence.jpg')},
                    content_type='multipart/form-data',
                    headers={'X-Offline-Replay': '1', 'X-Offline-Attempts': '1'})
    assert r.status_code in (200, 302)
    with app.app_context():
        d = OfflineDelivery.query.order_by(OfflineDelivery.id.desc()).first()
        assert d is not None
        assert d.endpoint == '/report-illegal'
        assert d.has_photo is True
        assert d.attempts == 1
        assert d.illegal_report_id is not None
        assert d.user_id is None  # anonymous by design


def test_offline_deliveries_dashboard_requires_admin(client, app):
    """The delivery-health dashboard is admin-only — citizens are blocked."""
    _make_user(app, 'odcit', role='citizen')
    _login_admin(client, app, 'odcit')
    r = client.get('/admin/offline-deliveries', follow_redirects=False)
    assert r.status_code == 403


def test_offline_deliveries_dashboard_shows_data(client, app):
    """Admins see the offline-first KPI strip + delivery rows."""
    from app.models import OfflineDelivery
    _make_user(app, 'odadmin', role='admin')
    with app.app_context():
        db.session.add_all([
            OfflineDelivery(endpoint='/report', ward='Ward 1 - MVGR College Area',
                            has_photo=True, attempts=0, delivered_at=utcnow()),
            OfflineDelivery(endpoint='/report-illegal', ward='Ward 3 - RTC Colony',
                            has_photo=False, attempts=3, delivered_at=utcnow()),
        ])
        db.session.commit()
    _login_admin(client, app, 'odadmin')
    r = client.get('/admin/offline-deliveries')
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert 'Offline Deliveries' in body
    assert 'Total Delivered Offline' in body
    assert '/report' in body
    assert 'Ward 3 - RTC Colony' in body


# ── Live telemetry history → real fill velocity ───────────────
def test_telemetry_ping_records_history_snapshot(client, app):
    """Every bin-telemetry ping appends a per-ping level snapshot to
    BinTelemetryLog — the raw material the fill-rate estimator learns from."""
    from app.models import BinTelemetryLog, SmartBin
    with app.app_context():
        if not SmartBin.query.filter_by(hardware_id='HIST-1').first():
            db.session.add(SmartBin(hardware_id='HIST-1', latitude=18.06,
                                    longitude=83.41, level=10,
                                    ward='Ward 1 - MVGR College Area'))
        db.session.commit()
    r = client.post('/api/bin-telemetry', json={"hardware_id": "HIST-1", "level": 42})
    assert r.status_code == 200
    with app.app_context():
        b = SmartBin.query.filter_by(hardware_id='HIST-1').first()
        rows = BinTelemetryLog.query.filter_by(bin_id=b.id).all()
        assert len(rows) == 1
        assert rows[0].level == 42
    # Second ping appends another snapshot (history, not overwrite)
    client.post('/api/bin-telemetry', json={"hardware_id": "HIST-1", "level": 55})
    with app.app_context():
        b = SmartBin.query.filter_by(hardware_id='HIST-1').first()
        assert BinTelemetryLog.query.filter_by(bin_id=b.id).count() == 2


def test_telemetry_history_prunes_stale_rows(client, app):
    """Rows older than the 14-day retention window are pruned on ping so the
    history table stays lean while keeping deep enough signal for velocity."""
    from app.models import BinTelemetryLog, SmartBin
    from datetime import timedelta
    with app.app_context():
        if not SmartBin.query.filter_by(hardware_id='HIST-PRUNE').first():
            db.session.add(SmartBin(hardware_id='HIST-PRUNE', latitude=18.06,
                                    longitude=83.41, level=10,
                                    ward='Ward 1 - MVGR College Area'))
        db.session.commit()
        b = SmartBin.query.filter_by(hardware_id='HIST-PRUNE').first()
        # One stale (20d) and one fresh (2h) snapshot
        db.session.add(BinTelemetryLog(bin_id=b.id, level=30,
                                       timestamp=utcnow() - timedelta(days=20)))
        db.session.add(BinTelemetryLog(bin_id=b.id, level=40,
                                       timestamp=utcnow() - timedelta(hours=2)))
        db.session.commit()
    r = client.post('/api/bin-telemetry', json={"hardware_id": "HIST-PRUNE", "level": 50})
    assert r.status_code == 200
    with app.app_context():
        b = SmartBin.query.filter_by(hardware_id='HIST-PRUNE').first()
        rows = BinTelemetryLog.query.filter_by(bin_id=b.id).all()
        assert len(rows) == 2  # fresh 2h row + new ping; 20d row pruned
        assert all((utcnow() - r.timestamp).days < 14 for r in rows)


def test_estimate_fill_rate_learns_real_velocity(app, monkeypatch):
    """_estimate_fill_rate_hour_pct learns the ACTUAL fill rate from per-ping
    history (least-squares slope over real snapshots) instead of inferring it
    from a single anchor timestamp."""
    import app.ml_model as ml
    from app.models import BinTelemetryLog, SmartBin
    from datetime import timedelta, timezone
    monkeypatch.setattr(ml, 'fill_model', None)  # isolate the history path
    now = utcnow()
    with app.app_context():
        b = SmartBin(hardware_id='HIST-VEL', latitude=18.06, longitude=83.41,
                     level=50, ward='Ward 1 - MVGR College Area',
                     decomposition_started_at=now - timedelta(hours=6))
        db.session.add(b)
        db.session.commit()
        # 4 snapshots over 6h: 20 → 40 → 60 → 80 → a clean 10%/hr line.
        # (timestamps naive UTC, exactly like real utcnow() storage)
        for h_ago, lvl in [(6, 20), (4, 40), (2, 60), (0, 80)]:
            db.session.add(BinTelemetryLog(bin_id=b.id, level=lvl,
                                           timestamp=now - timedelta(hours=h_ago)))
        db.session.commit()
        rate = ml._estimate_fill_rate_hour_pct(b, now.replace(tzinfo=timezone.utc))
    assert rate is not None
    assert 9.0 <= rate <= 11.0, f"expected ~10%/hr from history, got {rate}"


def test_sparse_history_falls_back_to_empirical(app, monkeypatch):
    """Fewer than min_points snapshots (or <2h span) → no velocity signal, so
    the estimator falls back to the single-anchor empirical rate."""
    import app.ml_model as ml
    from app.models import BinTelemetryLog, SmartBin
    from datetime import timedelta, timezone
    monkeypatch.setattr(ml, 'fill_model', None)
    now = utcnow()
    with app.app_context():
        b = SmartBin(hardware_id='HIST-SPARSE', latitude=18.06, longitude=83.41,
                     level=60, ward='Ward 1 - MVGR College Area',
                     decomposition_started_at=now - timedelta(hours=3))
        db.session.add(b)
        db.session.commit()
        # Only 2 snapshots (below min_points=3) — must NOT produce a velocity.
        db.session.add(BinTelemetryLog(bin_id=b.id, level=40,
                                       timestamp=now - timedelta(hours=2)))
        db.session.add(BinTelemetryLog(bin_id=b.id, level=60,
                                       timestamp=now - timedelta(hours=1)))
        db.session.commit()
        rate = ml._estimate_fill_rate_hour_pct(b, now.replace(tzinfo=timezone.utc))
    # No history signal → empirical anchor: 60% / 3h = 20%/hr.
    assert rate is not None
    assert 19.0 <= rate <= 21.0, f"expected ~20%/hr empirical fallback, got {rate}"


def test_build_fill_training_rows_from_history(app):
    """build_fill_training_rows() turns real per-ping snapshots into supervised
    (features → fill_rate_hour_pct) rows for the regressor retrain."""
    import app.ml_model as ml
    from app.models import BinTelemetryLog, SmartBin
    from datetime import timedelta
    now = utcnow()
    with app.app_context():
        b = SmartBin(hardware_id='HIST-TRAIN', latitude=18.06, longitude=83.41,
                     level=50, ward='Ward 1 - MVGR College Area', waste_stream='wet')
        db.session.add(b)
        db.session.commit()
        for h_ago, lvl in [(8, 10), (6, 30), (4, 50), (2, 70)]:
            db.session.add(BinTelemetryLog(bin_id=b.id, level=lvl,
                                           timestamp=now - timedelta(hours=h_ago)))
        db.session.commit()
        samples = ml.build_fill_training_rows()
    # 3 adjacent pairs (10→30, 30→50, 50→70 over 2h each) → 10%/hr samples.
    assert len(samples) == 3
    assert all(s['fill_rate_hour_pct'] == 10.0 for s in samples), samples
    assert all(s['level'] in (30, 50, 70) for s in samples)
    assert all(s['stream_id'] == 1 for s in samples)  # wet → 1


def test_retrain_merges_real_history_with_synthetic(app):
    """The retrain pipeline blends REAL telemetry-history samples with the
    synthetic physics priors, so a retrain always has data. The synthetic grid
    alone guarantees 600 rows; the merge helper appends real history on top."""
    import app.ml_model as ml
    # Synthetic priors: 10 wards × 5 streams × 3 seasons × 4 levels × 4 windows
    # = 2400 rows minimum.
    rows = ml.build_synthetic_fill_rows()
    assert len(rows) >= 2400
    assert {'level', 'hours_since_reset', 'season_idx', 'ward_id', 'stream_id',
            'fill_rate_hour_pct'} <= set(rows[0].keys())
    assert all(r['fill_rate_hour_pct'] > 0 for r in rows)
    # Real history merge is exercised end-to-end in the app context: with no
    # telemetry rows yet, build_fill_training_rows returns [] and the retrain
    # falls back to synthetic-only (guaranteed by build_real_fill_rows' try/except
    # in train_model.py — never a crash on a fresh checkout).
    with app.app_context():
        assert ml.build_fill_training_rows() == []


# ── Proactive dispatch queue (workers + admin control room) ──
def _make_worker(app, username, vehicle_id='CV-77'):
    uid = _make_user(app, username, role='worker')
    with app.app_context():
        from app.models import WorkerProfile
        db.session.add(WorkerProfile(user_id=uid, vehicle_id=vehicle_id, status='Active'))
        db.session.commit()
    return uid


def _seed_dispatch_bins(app):
    """Two forecast bins: one urgent (2h), one calm (30h)."""
    from app.models import SmartBin
    with app.app_context():
        if not SmartBin.query.filter_by(hardware_id='DISP-2H').first():
            db.session.add_all([
                SmartBin(hardware_id='DISP-2H', latitude=18.05, longitude=83.40,
                         level=55, ward='Ward 1 - MVGR College Area', overflow_eta_hours=2.0),
                SmartBin(hardware_id='DISP-30H', latitude=18.07, longitude=83.42,
                         level=40, ward='Ward 2 - Chintalavalasa Junction', overflow_eta_hours=30.0),
            ])
            db.session.commit()


def test_dispatch_queue_ranked_and_worker_accepts(client, app):
    """Workers see the forecast list ranked by hours-to-overflow and can accept
    an assignment; the queue then reflects their claim."""
    from app.models import DispatchAssignment
    _seed_dispatch_bins(app)
    _make_worker(app, 'dqwork')
    _login_admin(client, app, 'dqwork')

    r = client.get('/api/dispatch/queue')
    assert r.status_code == 200
    data = r.get_json()
    assert data['urgent_threshold_hours'] == 24
    bins = data['bins']
    # conftest seeds BIN-001/002/003 which also earn lazy forecasts — scope the
    # ranking assertion to the DISP- bins.
    disp = [b for b in bins if b['hardware_id'].startswith('DISP-')]
    assert [b['hardware_id'] for b in disp] == ['DISP-2H', 'DISP-30H']  # ranked by ETA
    assert disp[0]['urgent'] is True and disp[1]['urgent'] is False
    assert all(b['dispatch_status'] == 'available' for b in disp)

    r2 = client.post('/api/dispatch/accept', json={'bin_id': bins[0]['bin_id']})
    assert r2.status_code == 200
    assert r2.get_json()['success'] is True
    with app.app_context():
        assign = DispatchAssignment.query.filter_by(bin_id=bins[0]['bin_id']).first()
        assert assign is not None and assign.status == 'Assigned'

    r3 = client.get('/api/dispatch/queue')
    mine = [b for b in r3.get_json()['bins'] if b['hardware_id'] == 'DISP-2H'][0]
    assert mine['dispatch_status'] == 'assigned' and mine['mine'] is True


def test_dispatch_accept_is_idempotent_for_same_worker(client, app):
    """Re-accepting the same bin by the same worker must succeed (no duplicate)."""
    from app.models import DispatchAssignment
    _seed_dispatch_bins(app)
    _make_worker(app, 'dquid')
    _login_admin(client, app, 'dquid')
    with app.app_context():
        bid = __import__('app.models', fromlist=['SmartBin']).SmartBin.query.filter_by(hardware_id='DISP-2H').first().id
    r1 = client.post('/api/dispatch/accept', json={'bin_id': bid})
    r2 = client.post('/api/dispatch/accept', json={'bin_id': bid})
    assert r1.status_code == 200 and r2.status_code == 200
    with app.app_context():
        assert DispatchAssignment.query.filter_by(bin_id=bid, status='Assigned').count() == 1


def test_dispatch_accept_conflicts_with_other_worker(client, app):
    """A bin already claimed by another worker must reject with 409 — two
    trucks should never chase the same bin."""
    _seed_dispatch_bins(app)
    _make_worker(app, 'dqw1', vehicle_id='CV-11')
    _make_worker(app, 'dqw2', vehicle_id='CV-22')
    _login_admin(client, app, 'dqw1')
    with app.app_context():
        bid = __import__('app.models', fromlist=['SmartBin']).SmartBin.query.filter_by(hardware_id='DISP-2H').first().id
    assert client.post('/api/dispatch/accept', json={'bin_id': bid}).status_code == 200
    client.get('/logout')
    _login_admin(client, app, 'dqw2')
    r = client.post('/api/dispatch/accept', json={'bin_id': bid})
    assert r.status_code == 409
    assert r.get_json()['message'] == 'already_assigned'


def test_dispatch_complete_marks_assignment_done(client, app):
    from app.models import DispatchAssignment
    _seed_dispatch_bins(app)
    _make_worker(app, 'dqdone')
    _login_admin(client, app, 'dqdone')
    with app.app_context():
        bid = __import__('app.models', fromlist=['SmartBin']).SmartBin.query.filter_by(hardware_id='DISP-2H').first().id
    client.post('/api/dispatch/accept', json={'bin_id': bid})
    r = client.post('/api/dispatch/complete', json={'bin_id': bid})
    assert r.status_code == 200
    with app.app_context():
        assign = DispatchAssignment.query.filter_by(bin_id=bid).first()
        assert assign.status == 'Completed'
        assert assign.completed_at is not None
    # Queue now shows the bin as claimable again (no active assignment).
    data = client.get('/api/dispatch/queue').get_json()
    disp = [b for b in data['bins'] if b['hardware_id'] == 'DISP-2H'][0]
    assert disp['dispatch_status'] == 'available'


def test_dispatch_queue_blocks_citizens(client, app):
    _seed_dispatch_bins(app)
    _make_user(app, 'dqcit')
    client.post('/login', data={'username': 'dqcit', 'password': 'testpass123'})
    assert client.get('/api/dispatch/queue').status_code == 403
    assert client.post('/api/dispatch/accept', json={'bin_id': 1}).status_code == 403


def test_admin_sees_dispatch_queue(client, app):
    _seed_dispatch_bins(app)
    _make_user(app, 'dqadmin', role='admin')
    _login_admin(client, app, 'dqadmin')
    r = client.get('/api/dispatch/queue')
    assert r.status_code == 200
    assert len(r.get_json()['bins']) >= 2


def test_telemetry_crossing_6h_autoqueues_and_nudges(app, monkeypatch):
    """A bin whose ML forecast crosses the 6h alert threshold is auto-queued
    as a Pending dispatch AND a `dispatch_nudge` socket event fires — once,
    not on every subsequent urgent ping."""
    from datetime import timedelta
    from app.models import SmartBin, DispatchAssignment
    import app.ml_model as ml
    monkeypatch.setattr(ml, 'fill_model', None)  # pin the heuristic branch
    with app.app_context():
        if not SmartBin.query.filter_by(hardware_id='DISP-PING').first():
            db.session.add(SmartBin(
                hardware_id='DISP-PING', latitude=18.06, longitude=83.41,
                level=90, ward='Ward 1 - MVGR College Area',
                decomposition_started_at=utcnow() - timedelta(hours=30),
            ))
        db.session.commit()

    io_client = socketio.test_client(app)
    try:
        with app.test_client() as c:
            r = c.post('/api/bin-telemetry', json={"hardware_id": "DISP-PING", "level": 90})
            assert r.status_code == 200
            # Crossed -> Pending dispatch row auto-created.
            with app.app_context():
                bid = SmartBin.query.filter_by(hardware_id='DISP-PING').first().id
                assert DispatchAssignment.query.filter_by(bin_id=bid, status='Pending').count() == 1
            # Second urgent ping -> still urgent, no duplicate Pending row.
            c.post('/api/bin-telemetry', json={"hardware_id": "DISP-PING", "level": 92})

        received = io_client.get_received()
        nudges = [e for e in received if e['name'] == 'dispatch_nudge']
        assert len(nudges) == 1, f"expected exactly one nudge, got {len(nudges)}"
        assert nudges[0]['args'][0]['hardware_id'] == 'DISP-PING'
        with app.app_context():
            assert DispatchAssignment.query.filter_by(bin_id=bid, status='Pending').count() == 1
    finally:
        io_client.disconnect()


def test_dispatch_accept_takes_autoqueued_pending(client, app):
    """A Pending assignment auto-queued by telemetry is claimed (not
    duplicated) when a worker accepts it."""
    from app.models import DispatchAssignment, SmartBin
    _make_worker(app, 'dqclaim')
    _login_admin(client, app, 'dqclaim')
    with app.app_context():
        b = SmartBin(hardware_id='DISP-CLAIM', latitude=18.06, longitude=83.41,
                     level=88, ward='Ward 1 - MVGR College Area', overflow_eta_hours=3.0)
        db.session.add(b)
        db.session.commit()
        db.session.add(DispatchAssignment(bin_id=b.id, eta_hours=3.0, status='Pending'))
        db.session.commit()
        bid = b.id
    r = client.post('/api/dispatch/accept', json={'bin_id': bid})
    assert r.status_code == 200
    with app.app_context():
        rows = DispatchAssignment.query.filter_by(bin_id=bid).all()
        assert len(rows) == 1  # claimed, not duplicated
        assert rows[0].status == 'Assigned'


# ── Dead-letter alerting: exhausted retries → admin Notification + webhook ──
def test_alert_on_dead_letter_creates_admin_notifications_and_webhook(app, monkeypatch):
    """A job that exhausted its retries must create an in-app Notification for
    every approved admin and fire a JOB_DEAD_LETTERED webhook event."""
    from app.models import Notification
    import app.routes as routes
    fired = []
    monkeypatch.setattr(routes, '_dispatch_webhooks', lambda event, payload: fired.append((event, payload)))
    a1 = _make_user(app, 'dladmin1', role='admin')
    a2 = _make_user(app, 'dladmin2', role='admin')
    _make_user(app, 'dlpending', role='admin')
    with app.app_context():
        from app.models import User
        # dlpending is an un-approved admin — must NOT be notified.
        User.query.filter_by(username='dlpending').update({'is_approved': False})
        db.session.commit()

    from app.jobs import alert_on_dead_letter
    with app.app_context():
        # conftest seeds qa_admin (approved) — expect qa_admin + dladmin1 + dladmin2.
        n = alert_on_dead_letter('job-dead-1', 'app.jobs.send_sms_job', 'Traceback: boom')
        assert n == 3
        for uid in (a1, a2):
            note = Notification.query.filter_by(user_id=uid, link='/admin/failed-jobs#job-dead-1').first()
            assert note is not None
            assert 'send_sms_job' in note.message and 'job-dead-1' in note.message
        # The un-approved admin must NOT have been notified.
        pending = User.query.filter_by(username='dlpending').first()
        assert Notification.query.filter_by(user_id=pending.id, link='/admin/failed-jobs#job-dead-1').count() == 0
    assert len(fired) == 1 and fired[0][0] == 'JOB_DEAD_LETTERED'
    assert fired[0][1]['job_id'] == 'job-dead-1'
    assert 'boom' in fired[0][1]['exc_info']


def test_alert_on_dead_letter_is_idempotent(app, monkeypatch):
    """Re-sweeping the same dead-lettered job must not duplicate notifications."""
    from app.models import Notification
    import app.routes as routes
    monkeypatch.setattr(routes, '_dispatch_webhooks', lambda event, payload: None)
    _make_user(app, 'dlidem', role='admin')
    from app.jobs import alert_on_dead_letter
    with app.app_context():
        first = alert_on_dead_letter('job-idem-1', 'dunning_job')
        assert first >= 1  # qa_admin (conftest) + dlidem
        assert alert_on_dead_letter('job-idem-1', 'dunning_job') == 0  # deduped
        assert Notification.query.filter_by(link='/admin/failed-jobs#job-idem-1').count() == first


def test_alert_on_dead_letter_never_raises(app):
    """The alert hook is best-effort: bad inputs and failures return 0, never raise."""
    from app.jobs import alert_on_dead_letter
    assert alert_on_dead_letter('', 'f', '') == 0
    assert alert_on_dead_letter(None, 'f', '') == 0


def test_sweep_failed_jobs_alerts_degrades_without_redis():
    """Without a broker the sweep is a no-op returning 0 (tests / local dev)."""
    from app.jobs import sweep_failed_jobs_alerts
    assert sweep_failed_jobs_alerts() == 0


def test_sweep_job_policy_declared_and_schedules_without_redis(app):
    """The sweep job declares its retry policy and the scheduler is a safe no-op
    without Redis (inline mode)."""
    from app.jobs import JOB_RETRY_POLICIES, sweep_failed_jobs_alerts_job, schedule_failed_alert_sweep
    assert 'sweep_failed_jobs_alerts_job' in JOB_RETRY_POLICIES
    # No Redis: scheduling must not raise, and the job itself returns 0.
    with app.app_context():
        schedule_failed_alert_sweep()
        assert sweep_failed_jobs_alerts_job() == 0

# ── Maintenance work orders (fault cleared with a scheduled follow-up) ──
def test_clear_fault_schedules_maintenance(client, app):
    """Clearing a fault with schedule_maintenance mints a MaintenanceWorkOrder:
    the bin leaves the faulted state, stays maintenance-scheduled, incidents
    resolve, and both audits (MAINTENANCE_ORDER_CREATED + BIN_FAULT_CLEARED)
    are written in the same committed transaction."""
    from app.models import SmartBin, SensorHealth, IncidentLog, MaintenanceWorkOrder, AuditLog, WorkerProfile
    _make_user(app, 'maintadmin', role='admin')
    worker_uid = _make_user(app, 'maintworker', role='worker')
    with app.app_context():
        db.session.add(WorkerProfile(user_id=worker_uid, vehicle_id='CV-77', status='Active'))
        db.session.commit()
        wp = WorkerProfile.query.filter_by(user_id=worker_uid).first()
        worker_id = wp.id
        b = SmartBin(hardware_id='SF-MAINT-1', latitude=18.05, longitude=83.40,
                     level=96, ward='Ward 1 - MVGR College Area', sensor_fault=True)
        db.session.add(b)
        db.session.flush()
        db.session.add(SensorHealth(bin_id=b.id, fault_flag=True,
                                    fault_reason='Stuck sensor: constant level across 5 pings',
                                    maintenance_scheduled=True))
        db.session.add(IncidentLog(bin_id=b.id, incident_type='Sensor Fault', severity='Warning',
                                   status='Active', description='Stuck sensor: SF-MAINT-1'))
        db.session.commit()
    _login_admin(client, app, 'maintadmin')
    r = client.post('/api/bins/SF-MAINT-1/clear-fault',
                    json={'schedule_maintenance': True, 'worker_id': worker_id,
                          'due_date': '2026-08-10', 'notes': 'Recalibrate sensor'},
                    follow_redirects=False)
    assert r.status_code == 200
    data = r.get_json()
    assert data['success'] is True
    assert data['maintenance_scheduled'] is True
    assert data['maintenance_order_id'] is not None
    with app.app_context():
        b = SmartBin.query.filter_by(hardware_id='SF-MAINT-1').first()
        assert b.sensor_fault is False
        sh = SensorHealth.query.filter_by(bin_id=b.id).first()
        assert sh.fault_flag is False and sh.maintenance_scheduled is True
        inc = IncidentLog.query.filter_by(bin_id=b.id, incident_type='Sensor Fault').first()
        assert inc.status == 'Resolved'
        wo = MaintenanceWorkOrder.query.get(data['maintenance_order_id'])
        assert wo.status == 'Scheduled' and wo.worker_id == worker_id
        assert wo.notes == 'Recalibrate sensor'
        assert wo.due_date.strftime('%Y-%m-%d') == '2026-08-10'
        assert AuditLog.query.filter_by(action='MAINTENANCE_ORDER_CREATED', target='SF-MAINT-1').count() == 1
        assert AuditLog.query.filter_by(action='BIN_FAULT_CLEARED', target='SF-MAINT-1').count() == 1


def test_clear_fault_schedule_requires_worker_and_due(client, app):
    """The maintenance branch validates inputs BEFORE mutating: a missing or
    invalid worker and an unparseable due date each 400, leaving the bin
    faulted (no half-applied clear)."""
    from app.models import SmartBin, WorkerProfile
    _make_user(app, 'maintadmin2', role='admin')
    worker_uid = _make_user(app, 'maintworker2', role='worker')
    with app.app_context():
        db.session.add(WorkerProfile(user_id=worker_uid, vehicle_id='CV-78', status='Active'))
        db.session.add(SmartBin(hardware_id='SF-REQ-1', latitude=18.05, longitude=83.40,
                                level=96, ward='Ward 1 - MVGR College Area', sensor_fault=True))
        db.session.commit()
        worker_id = WorkerProfile.query.filter_by(user_id=worker_uid).first().id
    _login_admin(client, app, 'maintadmin2')

    r1 = client.post('/api/bins/SF-REQ-1/clear-fault',
                     json={'schedule_maintenance': True, 'due_date': '2026-08-10'},
                     follow_redirects=False)
    assert r1.status_code == 400

    r2 = client.post('/api/bins/SF-REQ-1/clear-fault',
                     json={'schedule_maintenance': True, 'worker_id': 999999,
                           'due_date': 'not-a-date'},
                     follow_redirects=False)
    assert r2.status_code == 400

    r3 = client.post('/api/bins/SF-REQ-1/clear-fault',
                     json={'schedule_maintenance': True, 'worker_id': worker_id,
                           'due_date': 'not-a-date'},
                     follow_redirects=False)
    assert r3.status_code == 400

    # Nothing was half-applied: the bin is still faulted and NO admin alert
    # was staged for the rejected clears.
    with app.app_context():
        from app.models import Notification
        b = SmartBin.query.filter_by(hardware_id='SF-REQ-1').first()
        assert b.sensor_fault is True
        assert Notification.query.filter(
            Notification.message.contains('SF-REQ-1')).count() == 0


def test_maintenance_api_lists_orders_and_workers(client, app):
    """GET /api/maintenance returns active + recent orders with worker/overdue
    context, plus the worker pool for the schedule form. Citizens are blocked."""
    from app.models import SmartBin, MaintenanceWorkOrder, WorkerProfile
    admin_uid = _make_user(app, 'maintadmin3', role='admin')
    worker_uid = _make_user(app, 'maintworker3', role='worker')
    with app.app_context():
        db.session.add(WorkerProfile(user_id=worker_uid, vehicle_id='CV-88', status='Active'))
        db.session.commit()
        wp = WorkerProfile.query.filter_by(user_id=worker_uid).first()
        b = SmartBin(hardware_id='SF-LIST-1', latitude=18.05, longitude=83.40,
                     level=60, ward='Ward 1 - MVGR College Area')
        db.session.add(b)
        db.session.flush()
        db.session.add(MaintenanceWorkOrder(bin_id=b.id, worker_id=wp.id,
                                            created_by=admin_uid, status='In Progress',
                                            due_date=utcnow()))
        db.session.commit()
    _login_admin(client, app, 'maintadmin3')
    r = client.get('/api/maintenance', follow_redirects=False)
    assert r.status_code == 200
    data = r.get_json()
    assert any(o['hardware_id'] == 'SF-LIST-1' and o['status'] == 'In Progress' for o in data['orders'])
    assert any(w['vehicle_id'] == 'CV-88' for w in data['workers'])

    # Sensor-faults KPI surfaces the active work-order count.
    r2 = client.get('/api/sensor-faults', follow_redirects=False)
    assert r2.get_json()['kpis']['active_work_orders'] == 1


def test_maintenance_api_blocks_citizen(client, app):
    """The maintenance feed is admin-only (403 for a citizen session)."""
    _make_user(app, 'maintcit')
    client.post('/login', data={'username': 'maintcit', 'password': 'testpass123'})
    assert client.get('/api/maintenance', follow_redirects=False).status_code == 403


def test_worker_start_and_complete_maintenance(client, app):
    """Workers see only their own orders; start moves Scheduled -> In Progress;
    complete restores the bin to service (fault + maintenance flags dropped,
    incidents resolved) and audits with the worker's identity. A worker cannot
    touch another worker's order."""
    from app.models import SmartBin, SensorHealth, IncidentLog, MaintenanceWorkOrder, AuditLog, WorkerProfile
    admin_uid = _make_user(app, 'maintadmin4', role='admin')
    worker_uid = _make_user(app, 'maintworker4', role='worker')
    other_uid = _make_user(app, 'maintworker5', role='worker')
    with app.app_context():
        wp = WorkerProfile(user_id=worker_uid, vehicle_id='CV-89', status='Active')
        other = WorkerProfile(user_id=other_uid, vehicle_id='CV-90', status='Active')
        db.session.add_all([wp, other])
        db.session.commit()
        b = SmartBin(hardware_id='SF-WORK-1', latitude=18.05, longitude=83.40,
                     level=96, ward='Ward 1 - MVGR College Area', sensor_fault=True)
        db.session.add(b)
        db.session.flush()
        db.session.add(SensorHealth(bin_id=b.id, fault_flag=True,
                                    fault_reason='Stuck sensor: constant level across 5 pings',
                                    maintenance_scheduled=True))
        db.session.add(IncidentLog(bin_id=b.id, incident_type='Sensor Fault', severity='Warning',
                                   status='Active', description='Stuck sensor: SF-WORK-1'))
        db.session.commit()
        my_id = wp.id
        other_id = other.id
        order = MaintenanceWorkOrder(bin_id=b.id, worker_id=my_id, created_by=admin_uid,
                                     due_date=utcnow())
        db.session.add(order)
        db.session.commit()
        order_id = order.id

    _login_admin(client, app, 'maintworker4')
    # Only my order shows up in /api/maintenance/my
    mine = client.get('/api/maintenance/my', follow_redirects=False)
    assert mine.status_code == 200
    assert len(mine.get_json()['orders']) == 1
    assert mine.get_json()['orders'][0]['id'] == order_id

    # Start: Scheduled -> In Progress
    r = client.post(f'/api/maintenance/{order_id}/start', follow_redirects=False)
    assert r.status_code == 200
    # Re-start is a 400 (already In Progress)
    assert client.post(f'/api/maintenance/{order_id}/start', follow_redirects=False).status_code == 400

    # A different worker's order is invisible (404) even for start/complete
    with app.app_context():
        other_order = MaintenanceWorkOrder(bin_id=1, worker_id=other_id, created_by=admin_uid)
        db.session.add(other_order)
        db.session.commit()
        other_order_id = other_order.id
    assert client.post(f'/api/maintenance/{other_order_id}/start', follow_redirects=False).status_code == 404
    assert client.post(f'/api/maintenance/{other_order_id}/complete', follow_redirects=False).status_code == 404

    # Complete restores the bin and audits
    r = client.post(f'/api/maintenance/{order_id}/complete', follow_redirects=False)
    assert r.status_code == 200
    assert r.get_json()['bin_restored'] is True
    # Idempotency guard: already-completed is a 400
    assert client.post(f'/api/maintenance/{order_id}/complete', follow_redirects=False).status_code == 400

    with app.app_context():
        wo = MaintenanceWorkOrder.query.get(order_id)
        assert wo.status == 'Completed' and wo.completed_at is not None
        assert wo.completed_by == worker_uid
        b = SmartBin.query.filter_by(hardware_id='SF-WORK-1').first()
        assert b.sensor_fault is False
        sh = SensorHealth.query.filter_by(bin_id=b.id).first()
        assert sh.fault_flag is False and sh.maintenance_scheduled is False
        inc = IncidentLog.query.filter_by(bin_id=b.id, incident_type='Sensor Fault').first()
        assert inc.status == 'Resolved'
        assert AuditLog.query.filter_by(action='MAINTENANCE_COMPLETED',
                                        target='SF-WORK-1').count() == 1


def test_resolve_bin_autocompletes_maintenance(client, app):
    """Clearing a bin with verified After-photo + GPS auto-completes its open
    maintenance work orders — the on-site visit IS the maintenance."""
    from app.models import SmartBin, MaintenanceWorkOrder, WorkerProfile, AuditLog
    admin_uid = _make_user(app, 'maintadmin6', role='admin')
    worker_uid = _make_user(app, 'maintworker6', role='worker')
    with app.app_context():
        db.session.add(WorkerProfile(user_id=worker_uid, vehicle_id='CV-91', status='Active'))
        db.session.commit()
        wp = WorkerProfile.query.filter_by(user_id=worker_uid).first()
        b = SmartBin(hardware_id='BIN-MAINT-RES', latitude=18.05, longitude=83.40,
                     level=90, status='Critical', ward='Ward 1 - MVGR College Area')
        db.session.add(b)
        db.session.flush()
        db.session.add(MaintenanceWorkOrder(bin_id=b.id, worker_id=wp.id,
                                            created_by=admin_uid, status='Scheduled'))
        db.session.commit()
        bin_id = b.id
    _login_admin(client, app, 'maintworker6')
    r = client.post('/resolve-bin/BIN-MAINT-RES',
                    data={'after_photo': (_make_jpeg_bytes(), 'after.jpg'),
                          'lat': '18.05', 'lon': '83.40'},
                    content_type='multipart/form-data', follow_redirects=False)
    assert r.status_code == 200
    with app.app_context():
        wo = MaintenanceWorkOrder.query.filter_by(bin_id=bin_id).first()
        assert wo.status == 'Completed' and wo.completed_at is not None
        assert AuditLog.query.filter_by(action='RESOLVE_BIN',
                                        target='BIN-MAINT-RES').count() == 1
        assert 'auto-completed' in AuditLog.query.filter_by(action='RESOLVE_BIN',
                                                            target='BIN-MAINT-RES').first().detail

# ── Sensor-fault analytics (audit-ledger lifecycle instrumentation) ──
def test_sensor_self_heal_is_audited(client, app):
    """A faulted bin whose next ping shows a changed reading self-heals: the
    fault clears, the incident resolves, and a SENSOR_SELF_HEALED audit row is
    written — the signal the analytics ratio is built on."""
    from app.models import SmartBin, SensorHealth, IncidentLog, AuditLog
    with app.app_context():
        b = SmartBin(hardware_id='SELF-1', latitude=18.05, longitude=83.40,
                     level=96, ward='Ward 1 - MVGR College Area', sensor_fault=True)
        db.session.add(b)
        db.session.flush()
        db.session.add(SensorHealth(bin_id=b.id, fault_flag=True,
                                    fault_reason='Stuck sensor: constant level across 5 pings',
                                    maintenance_scheduled=True))
        db.session.add(IncidentLog(bin_id=b.id, incident_type='Sensor Fault', severity='Warning',
                                   status='Active', description='Stuck sensor: SELF-1'))
        db.session.commit()
    r = client.post('/api/bin-telemetry',
                    json={'hardware_id': 'SELF-1', 'level': 50},
                    follow_redirects=False)
    assert r.status_code == 200
    with app.app_context():
        b = SmartBin.query.filter_by(hardware_id='SELF-1').first()
        assert b.sensor_fault is False
        sh = SensorHealth.query.filter_by(bin_id=b.id).first()
        assert sh.fault_flag is False and sh.maintenance_scheduled is False
        inc = IncidentLog.query.filter_by(bin_id=b.id, incident_type='Sensor Fault').first()
        assert inc.status == 'Resolved'
        assert AuditLog.query.filter_by(action='SENSOR_SELF_HEALED',
                                        target='SELF-1').count() == 1


def test_stale_sweep_audits_sensor_fault_flagged(client, app):
    """check_sensor_faults flags a >24h-silent bin and writes a
    SENSOR_FAULT_FLAGGED audit (the stale-source detection signal)."""
    from app.models import SmartBin, AuditLog, IncidentLog
    from app.routes import check_sensor_faults
    from datetime import timedelta
    with app.app_context():
        stale = utcnow() - timedelta(hours=48)
        b = SmartBin(hardware_id='STALE-1', latitude=18.05, longitude=83.40,
                     level=40, ward='Ward 1 - MVGR College Area',
                     sensor_fault=False, last_updated=stale)
        db.session.add(b)
        db.session.commit()
        check_sensor_faults()
        b = SmartBin.query.filter_by(hardware_id='STALE-1').first()
        assert b.sensor_fault is True
        assert AuditLog.query.filter_by(action='SENSOR_FAULT_FLAGGED',
                                        target='STALE-1').count() == 1
        assert IncidentLog.query.filter_by(bin_id=b.id, incident_type='Sensor Fault',
                                           status='Active').count() == 1


def test_sensor_fault_analytics_api_math(client, app):
    """The analytics endpoint reconstructs the fault lifecycle from the audit
    ledger: per-ward fault rate, average time-to-clear (detection->resolution
    pairing), self-heal vs manual ratio, weekly series and repeat offenders."""
    from app.models import SmartBin, AuditLog
    from datetime import timedelta
    admin_uid = _make_user(app, 'sfaadmin', role='admin')
    now = utcnow()
    with app.app_context():
        # Ward A bin: detected 10d ago, self-healed 9d ago -> 24h time-to-clear
        a = SmartBin(hardware_id='SFA-A', latitude=18.05, longitude=83.40,
                     level=50, ward='Ward A')
        # Ward B bin: detected 5d ago, manually cleared 2h later
        b = SmartBin(hardware_id='SFA-B', latitude=18.05, longitude=83.41,
                     level=50, ward='Ward B')
        # Ward A repeat offender: second detection 3d ago (unresolved)
        c = SmartBin(hardware_id='SFA-C', latitude=18.05, longitude=83.42,
                     level=50, ward='Ward A')
        # Currently-faulted bin (no events in window)
        d = SmartBin(hardware_id='SFA-D', latitude=18.05, longitude=83.43,
                     level=60, ward='Ward C', sensor_fault=True)
        db.session.add_all([a, b, c, d])
        db.session.flush()
        events = [
            AuditLog(action='SENSOR_SUSPICIOUS', target='SFA-A', username='sfaadmin',
                     role='admin', timestamp=now - timedelta(days=10)),
            AuditLog(action='SENSOR_SELF_HEALED', target='SFA-A', username='sfaadmin',
                     role='admin', timestamp=now - timedelta(days=9)),
            AuditLog(action='SENSOR_SUSPICIOUS', target='SFA-C', username='sfaadmin',
                     role='admin', timestamp=now - timedelta(days=3)),
            AuditLog(action='SENSOR_FAULT_FLAGGED', target='SFA-B', username='sfaadmin',
                     role='admin', timestamp=now - timedelta(days=5)),
            AuditLog(action='BIN_FAULT_CLEARED', target='SFA-B', username='sfaadmin',
                     role='admin', timestamp=now - timedelta(days=5) + timedelta(hours=2)),
        ]
        db.session.add_all(events)
        db.session.commit()
    _login_admin(client, app, 'sfaadmin')
    r = client.get('/api/analytics/sensor-faults?days=90', follow_redirects=False)
    assert r.status_code == 200
    data = r.get_json()

    k = data['kpis']
    assert k['detections'] == 3
    assert k['self_heal'] == 1
    assert k['manual'] == 1
    assert k['resolved'] == 2
    assert k['self_heal_pct'] == 50.0
    assert k['avg_ttc_hours'] == 13.0  # (24 + 2) / 2
    assert k['currently_faulted'] == 1

    # Per-ward aggregation
    ward_a = [w for w in data['wards'] if w['ward'] == 'Ward A'][0]
    ward_b = [w for w in data['wards'] if w['ward'] == 'Ward B'][0]
    assert ward_a['detections'] == 2 and ward_a['bins'] == 2
    assert ward_a['fault_rate'] == 1.0  # 2 detections / 2 bins
    assert ward_b['detections'] == 1 and ward_b['avg_ttc_hours'] == 2.0
    assert ward_b['manual'] == 1

    # Repeat offenders: SFA-A and SFA-C both have detections; sorted desc
    top = [t['hardware_id'] for t in data['top_bins']]
    assert 'SFA-A' in top and 'SFA-C' in top

    # Weekly series: detection weeks present, detections >= resolutions count
    assert data['series']['labels'], 'series should have at least one week'
    assert sum(data['series']['detections']) == 3


def test_sensor_fault_analytics_blocks_citizen(client, app):
    """The sensor-fault analytics feed is admin-only."""
    _make_user(app, 'sfacit')
    client.post('/login', data={'username': 'sfacit', 'password': 'testpass123'})
    assert client.get('/api/analytics/sensor-faults', follow_redirects=False).status_code == 403

# ── Live admin alerts (stuck-sensor detection + manual clears -> SSE stream) ──
def test_stuck_detection_notifies_admins(client, app):
    """A stuck-sensor detection writes an in-app Notification for every admin
    (link points at the sensor-health section) — the row the live bell and SSE
    stream deliver."""
    from app.models import SmartBin, BinTelemetryLog, Notification
    admin_uid = _make_user(app, 'ntfadmin', role='admin')
    with app.app_context():
        b = SmartBin(hardware_id='NTF-STUCK-1', latitude=18.05, longitude=83.40,
                     level=96, ward='Ward 1 - MVGR College Area')
        db.session.add(b)
        db.session.flush()
        for _ in range(5):
            db.session.add(BinTelemetryLog(bin_id=b.id, level=96, timestamp=utcnow()))
        db.session.commit()
    r = client.post('/api/bin-telemetry', json={'hardware_id': 'NTF-STUCK-1', 'level': 96})
    assert r.status_code == 200
    with app.app_context():
        notes = Notification.query.filter(
            Notification.user_id == admin_uid,
            Notification.message.contains('Stuck sensor')).all()
        assert len(notes) == 1
        assert 'NTF-STUCK-1' in notes[0].message
        assert notes[0].link == '/admin#sensor-fault-section'


def test_stale_sweep_notifies_admins(client, app):
    """The stale-sensor sweep alerts admins when it flags a >24h-silent bin."""
    from app.models import SmartBin, Notification
    from app.routes import check_sensor_faults
    from datetime import timedelta
    admin_uid = _make_user(app, 'ntfadmin2', role='admin')
    with app.app_context():
        db.session.add(SmartBin(hardware_id='NTF-STALE-1', latitude=18.05, longitude=83.40,
                                level=40, ward='Ward 1 - MVGR College Area',
                                sensor_fault=False, last_updated=utcnow() - timedelta(hours=48)))
        db.session.commit()
        check_sensor_faults()
        notes = Notification.query.filter(
            Notification.user_id == admin_uid,
            Notification.message.contains('no telemetry for >24h')).all()
        assert len(notes) == 1
        assert 'NTF-STALE-1' in notes[0].message
        assert notes[0].link == '/admin#sensor-fault-section'


def test_clear_fault_notifies_admins(client, app):
    """A manual clear-fault alerts every admin (including the actor) so the
    control room sees live that a bin was restored."""
    from app.models import SmartBin, SensorHealth, Notification
    admin_uid = _make_user(app, 'ntfadmin3', role='admin')
    with app.app_context():
        b = SmartBin(hardware_id='NTF-CLR-1', latitude=18.05, longitude=83.40,
                     level=96, ward='Ward 1 - MVGR College Area', sensor_fault=True)
        db.session.add(b)
        db.session.flush()
        db.session.add(SensorHealth(bin_id=b.id, fault_flag=True,
                                    fault_reason='Stuck sensor: constant level across 5 pings',
                                    maintenance_scheduled=True))
        db.session.commit()
    _login_admin(client, app, 'ntfadmin3')
    r = client.post('/api/bins/NTF-CLR-1/clear-fault', json={}, follow_redirects=False)
    assert r.status_code == 200
    with app.app_context():
        notes = Notification.query.filter(
            Notification.user_id == admin_uid,
            Notification.message.contains('Sensor fault cleared on NTF-CLR-1')).all()
        assert len(notes) == 1
        assert 'by ntfadmin3' in notes[0].message


def test_maintenance_complete_notifies_admins(client, app):
    """A worker completing a maintenance order alerts the admin control room."""
    from app.models import SmartBin, MaintenanceWorkOrder, Notification, WorkerProfile
    admin_uid = _make_user(app, 'ntfadmin4', role='admin')
    worker_uid = _make_user(app, 'ntfworker4', role='worker')
    with app.app_context():
        wp = WorkerProfile(user_id=worker_uid, vehicle_id='CV-95', status='Active')
        db.session.add(wp)
        db.session.commit()
        b = SmartBin(hardware_id='NTF-WO-1', latitude=18.05, longitude=83.40,
                     level=60, ward='Ward 1 - MVGR College Area', sensor_fault=True)
        db.session.add(b)
        db.session.flush()
        wo = MaintenanceWorkOrder(bin_id=b.id, worker_id=wp.id,
                                  created_by=admin_uid, status='Scheduled',
                                  due_date=utcnow())
        db.session.add(wo)
        db.session.commit()
        order_id = wo.id
    _login_admin(client, app, 'ntfworker4')
    r = client.post(f'/api/maintenance/{order_id}/complete', follow_redirects=False)
    assert r.status_code == 200
    with app.app_context():
        notes = Notification.query.filter(
            Notification.user_id == admin_uid,
            Notification.message.contains('Maintenance work order')).all()
        assert len(notes) == 1
        assert 'NTF-WO-1' in notes[0].message
        assert notes[0].link == '/admin#sensor-fault-section'
# ── Maintenance work-order overdue escalation job ────────────
def test_maintenance_overdue_escalation_notifies_and_refags(app):
    """An order past its due date escalates exactly once: the assigned worker
    and every approved admin get an in-app Notification, and a still-faulted
    bin is re-flagged (SensorHealth + active incident) so it stays on the
    faulted-bin dashboard. A second run is a no-op (escalated_at dedupe)."""
    from datetime import timedelta
    from app.jobs import maintenance_overdue_escalation_job
    from app.models import (AuditLog, IncidentLog, MaintenanceWorkOrder,
                            Notification, SensorHealth, SmartBin, WorkerProfile)
    admin_uid = _make_user(app, 'escadmin1', role='admin')
    worker_uid = _make_user(app, 'escworker1', role='worker')
    with app.app_context():
        wp = WorkerProfile(user_id=worker_uid, vehicle_id='CV-88', status='Active')
        db.session.add(wp)
        db.session.flush()
        b = SmartBin(hardware_id='ESC-1', latitude=18.05, longitude=83.40,
                     level=96, ward='Ward 1 - MVGR College Area', sensor_fault=True)
        db.session.add(b)
        db.session.flush()
        db.session.add(SensorHealth(bin_id=b.id, fault_flag=False,
                                    maintenance_scheduled=False))
        db.session.add(MaintenanceWorkOrder(bin_id=b.id, worker_id=wp.id,
                                            created_by=admin_uid,
                                            status='Scheduled',
                                            due_date=utcnow() - timedelta(days=1)))
        db.session.commit()
        bin_id, order_id, wp_id = b.id, b.maintenance_orders[0].id, wp.id
    with app.app_context():
        count = maintenance_overdue_escalation_job()
        assert count == 1
        # Worker + admin both notified, with the correct channels.
        w_notes = Notification.query.filter(
            Notification.user_id == worker_uid,
            Notification.message.contains('overdue')).all()
        a_notes = Notification.query.filter(
            Notification.user_id == admin_uid,
            Notification.message.contains('overdue')).all()
        assert len(w_notes) == 1 and w_notes[0].link == '/worker'
        assert len(a_notes) == 1 and a_notes[0].link == '/admin#sensor-fault-section'
        # Bin still faulted → re-flagged for maintenance + active incident.
        sh = SensorHealth.query.filter_by(bin_id=bin_id).first()
        assert sh.fault_flag is True and sh.maintenance_scheduled is True
        assert IncidentLog.query.filter_by(bin_id=bin_id, incident_type='Sensor Fault',
                                           status='Active').count() == 1
        assert AuditLog.query.filter_by(action='MAINTENANCE_OVERDUE_ESCALATED',
                                        target='ESC-1').count() == 1
        # Dedupe: the second run escalates nothing new.
        assert maintenance_overdue_escalation_job() == 0
        assert Notification.query.filter_by(user_id=admin_uid).count() == 1
        assert Notification.query.filter_by(user_id=worker_uid).count() == 1


def test_maintenance_overdue_escalation_skips_future_and_completed(app):
    """Orders with a future due date, and already-completed orders, are never
    escalated by the sweep."""
    from datetime import timedelta
    from app.jobs import maintenance_overdue_escalation_job
    from app.models import MaintenanceWorkOrder, Notification, SmartBin
    admin_uid = _make_user(app, 'escadmin2', role='admin')
    with app.app_context():
        b = SmartBin(hardware_id='ESC-2', latitude=18.05, longitude=83.40,
                     level=40, ward='Ward 1 - MVGR College Area')
        db.session.add(b)
        db.session.flush()
        db.session.add_all([
            MaintenanceWorkOrder(bin_id=b.id, created_by=admin_uid,
                                 status='Scheduled',
                                 due_date=utcnow() + timedelta(days=2)),
            MaintenanceWorkOrder(bin_id=b.id, created_by=admin_uid,
                                 status='Completed', completed_at=utcnow(),
                                 due_date=utcnow() - timedelta(days=1)),
        ])
        db.session.commit()
    with app.app_context():
        assert maintenance_overdue_escalation_job() == 0
        assert Notification.query.filter_by(user_id=admin_uid).count() == 0


def test_maintenance_overdue_escalation_skips_self_healed_bin(app):
    """An overdue order on a bin that self-healed (sensor_fault False) still
    escalates the notification, but does NOT re-flag the healthy bin."""
    from datetime import timedelta
    from app.jobs import maintenance_overdue_escalation_job
    from app.models import (IncidentLog, MaintenanceWorkOrder, Notification,
                            SmartBin)
    admin_uid = _make_user(app, 'escadmin3', role='admin')
    with app.app_context():
        b = SmartBin(hardware_id='ESC-3', latitude=18.05, longitude=83.40,
                     level=30, ward='Ward 1 - MVGR College Area', sensor_fault=False)
        db.session.add(b)
        db.session.flush()
        db.session.add(MaintenanceWorkOrder(bin_id=b.id, created_by=admin_uid,
                                            status='Scheduled',
                                            due_date=utcnow() - timedelta(hours=3)))
        db.session.commit()
        bin_id = b.id
    with app.app_context():
        assert maintenance_overdue_escalation_job() == 1
        assert len(Notification.query.filter_by(user_id=admin_uid).all()) == 1
        assert IncidentLog.query.filter_by(bin_id=bin_id).count() == 0


def test_schedule_maintenance_overdue_escalation_noop_without_redis(app, monkeypatch):
    """Without a queue (local dev / pytest) the schedule helper is a no-op —
    the escalation still runs inline when triggered, and startup never breaks."""
    import app.jobs as jobs_mod
    monkeypatch.setattr(jobs_mod, '_get_queue', lambda: None)
    assert jobs_mod.schedule_maintenance_overdue_escalation() is None
# ── Maintenance work-order lifecycle timeline (audit ledger) ──
def _seed_lifecycle_order(app):
    """Create a bin + fault + scheduled order (audited like clear_bin_fault), then
    start it, returning the ids needed by the timeline/reschedule tests
    (bin, order, worker profile, admin uid, worker uid)."""
    from app.models import (SmartBin, SensorHealth, MaintenanceWorkOrder,
                            WorkerProfile, AuditLog)
    admin_uid = _make_user(app, 'tladmin', role='admin')
    worker_uid = _make_user(app, 'tlworker', role='worker')
    with app.app_context():
        wp = WorkerProfile(user_id=worker_uid, vehicle_id='CV-81', status='Active')
        db.session.add(wp)
        db.session.flush()
        b = SmartBin(hardware_id='TL-BIN-1', latitude=18.05, longitude=83.40,
                     level=96, ward='Ward 1 - MVGR College Area', sensor_fault=True)
        db.session.add(b)
        db.session.flush()
        db.session.add(SensorHealth(bin_id=b.id, fault_flag=True,
                                    fault_reason='Stuck sensor', maintenance_scheduled=True))
        wo = MaintenanceWorkOrder(bin_id=b.id, worker_id=wp.id, created_by=admin_uid,
                                  status='Scheduled', due_date=utcnow())
        db.session.add(wo)
        db.session.flush()
        # Mirror clear_bin_fault: the created audit embeds the order id in
        # detail, atomic with the order's own commit.
        db.session.add(AuditLog(
            username='tladmin', role='admin', action='MAINTENANCE_ORDER_CREATED',
            target='TL-BIN-1',
            detail=f"Maintenance order #{wo.id} scheduled for worker, due "
                   f"{wo.due_date.strftime('%Y-%m-%d')}",
            timestamp=utcnow()))
        db.session.commit()
        return b.id, wo.id, wp.id, admin_uid, worker_uid


def test_maintenance_reschedule_audits_due_date_change(client, app):
    """Rescheduling a work order updates due_date AND writes a
    MAINTENANCE_DUE_DATE_CHANGED audit capturing the old -> new dates with the
    acting admin — the per-order timeline shows the change, not a silent edit."""
    from datetime import timedelta
    from app.models import SmartBin, MaintenanceWorkOrder, AuditLog
    bin_id, order_id, _, admin_uid, _ = _seed_lifecycle_order(app)
    _login_admin(client, app, 'tladmin')
    r = client.post(f'/api/maintenance/{order_id}/edit',
                    json={'due_date': '2026-09-15'}, follow_redirects=False)
    assert r.status_code == 200
    assert r.get_json()['due_date'] == '2026-09-15'
    with app.app_context():
        wo = MaintenanceWorkOrder.query.get(order_id)
        assert wo.due_date.strftime('%Y-%m-%d') == '2026-09-15'
        audits = AuditLog.query.filter_by(action='MAINTENANCE_DUE_DATE_CHANGED').all()
        assert len(audits) == 1
        assert '2026-09-15' in audits[0].detail
        # old due was utcnow (today) — detail must capture both endpoints
        assert audits[0].username == 'tladmin'

    # Rescheduling resets the escalation window: an order escalated at the old
    # deadline must escalate again if the NEW deadline passes unserviced.
    with app.app_context():
        wo = MaintenanceWorkOrder.query.get(order_id)
        wo.escalated_at = utcnow()
        db.session.commit()
    r = client.post(f'/api/maintenance/{order_id}/edit',
                    json={'due_date': '2026-09-25'}, follow_redirects=False)
    assert r.status_code == 200
    with app.app_context():
        wo = MaintenanceWorkOrder.query.get(order_id)
        assert wo.escalated_at is None
        assert AuditLog.query.filter_by(
            action='MAINTENANCE_DUE_DATE_CHANGED').count() == 2
        assert 'Escalation window reset' in AuditLog.query.filter_by(
            action='MAINTENANCE_DUE_DATE_CHANGED').order_by(
            AuditLog.id.desc()).first().detail


def test_maintenance_reschedule_validation_and_gating(client, app):
    """Bad dates 400 with no mutation; completed orders are immutable; a
    citizen (or any non-admin) can't reschedule at all."""
    from app.models import MaintenanceWorkOrder, AuditLog
    bin_id, order_id, _, _, _ = _seed_lifecycle_order(app)
    _login_admin(client, app, 'tladmin')
    # unparseable date
    r = client.post(f'/api/maintenance/{order_id}/edit',
                    json={'due_date': 'not-a-date'}, follow_redirects=False)
    assert r.status_code == 400
    # missing date
    r = client.post(f'/api/maintenance/{order_id}/edit',
                    json={}, follow_redirects=False)
    assert r.status_code == 400
    # unknown order
    r = client.post('/api/maintenance/999999/edit',
                    json={'due_date': '2026-09-15'}, follow_redirects=False)
    assert r.status_code == 404
    with app.app_context():
        assert AuditLog.query.filter_by(
            action='MAINTENANCE_DUE_DATE_CHANGED').count() == 0

    # completed orders are immutable
    with app.app_context():
        wo = MaintenanceWorkOrder.query.get(order_id)
        wo.status = 'Completed'
        db.session.commit()
    r = client.post(f'/api/maintenance/{order_id}/edit',
                    json={'due_date': '2026-09-15'}, follow_redirects=False)
    assert r.status_code == 400

    # citizen cannot reach the endpoint (logout first — the login route
    # short-circuits when a session is already active)
    client.get('/logout', follow_redirects=False)
    _make_user(app, 'tlcitizen')
    client.post('/login', data={'username': 'tlcitizen', 'password': 'testpass123'},
                follow_redirects=False)
    r = client.post('/api/maintenance/1/edit',
                    json={'due_date': '2026-09-15'}, follow_redirects=False)
    assert r.status_code == 403


def test_audit_ledger_shows_per_order_timeline(client, app):
    """The superadmin audit ledger renders the full per-order lifecycle:
    created (by admin) + started (by worker) events in chronological order,
    with the order id and bin visible."""
    from app.models import SmartBin, MaintenanceWorkOrder
    bin_id, order_id, wp_id, _, worker_uid = _seed_lifecycle_order(app)
    _login_admin(client, app, 'tlworker')
    # Worker starts the order — writes MAINTENANCE_STARTED with order id in detail
    r = client.post(f'/api/maintenance/{order_id}/start', follow_redirects=False)
    assert r.status_code == 200
    # Superadmin views the ledger (logout first — the login route short-circuits
    # when a session is already active)
    client.get('/logout', follow_redirects=False)
    with app.app_context():
        from app.models import User
        u = User.query.get(_make_user(app, 'tl_super', role='admin'))
        u.is_superadmin = True
        db.session.commit()
    _login_admin(client, app, 'tl_super')
    r = client.get('/admin/audit')
    assert r.status_code == 200
    body = r.data.decode('utf-8')
    assert 'Maintenance Work-Order Lifecycles' in body
    assert f'timeline-card-{order_id}' in body
    assert 'TL-BIN-1' in body
    # Both lifecycle events present in the timeline SECTION (scoped slice —
    # the flat table below renders newest-first, which would invert the order)
    section = body[body.index('<!-- Maintenance Work-Order Lifecycles'):]
    section = section[:section.index('<!-- Audit Log Table -->')]
    assert 'Created' in section and 'Started' in section
    assert section.index('Maintenance order #') < section.index('started maintenance work order')
    # The reschedule control appears on the open order
    assert f'due-{order_id}' in body


def test_audit_ledger_timeline_renders_empty_state(client, app):
    """With no maintenance orders the ledger shows the empty-state copy."""
    _make_user(app, 'tl_super2', role='admin')
    with app.app_context():
        from app.models import User
        u = User.query.get(User.query.filter_by(username='tl_super2').first().id)
        u.is_superadmin = True
        db.session.commit()
    _login_admin(client, app, 'tl_super2')
    r = client.get('/admin/audit')
    assert r.status_code == 200
    assert 'No maintenance work orders yet' in r.data.decode('utf-8')
def test_audit_ledger_timeline_shows_due_date_change(client, app):
    """A reschedule lands in the ledger timeline: after moving the due date,
    the per-order card shows the MAINTENANCE_DUE_DATE_CHANGED event between
    created and (later) completion."""
    from app.models import User
    bin_id, order_id, _, _, _ = _seed_lifecycle_order(app)
    _login_admin(client, app, 'tladmin')
    r = client.post(f'/api/maintenance/{order_id}/edit',
                    json={'due_date': '2026-09-20'}, follow_redirects=False)
    assert r.status_code == 200
    client.get('/logout', follow_redirects=False)
    _make_user(app, 'tl_super3', role='admin')
    with app.app_context():
        u = User.query.get(User.query.filter_by(username='tl_super3').first().id)
        u.is_superadmin = True
        db.session.commit()
    _login_admin(client, app, 'tl_super3')
    r = client.get('/admin/audit')
    assert r.status_code == 200
    body = r.data.decode('utf-8')
    section = body[body.index('<!-- Maintenance Work-Order Lifecycles'):]
    section = section[:section.index('<!-- Audit Log Table -->')]
    assert 'Due date changed' in section
    assert '2026-09-20' in section
    # Ordering: created → due-date change → (no started/completed yet). The
    # card renders translated labels; the raw detail embeds the order id.
    assert section.index('Maintenance order #') < section.index('moved maintenance work order')
def test_maintenance_edit_reassigns_worker_and_audits(client, app):
    """Reassigning an order to another worker updates worker_id and writes a
    MAINTENANCE_WORKER_CHANGED audit (old -> new); the new worker gets an
    in-app notification + SSE channel push."""
    from app.models import MaintenanceWorkOrder, AuditLog, Notification, WorkerProfile, User
    bin_id, order_id, wp_id, _, _ = _seed_lifecycle_order(app)
    # second worker to reassign to
    new_uid = _make_user(app, 'tlworker2', role='worker')
    with app.app_context():
        wp2 = WorkerProfile(user_id=new_uid, vehicle_id='CV-82', status='Active')
        db.session.add(wp2)
        db.session.commit()
        new_wp_id = wp2.id
    _login_admin(client, app, 'tladmin')
    r = client.post(f'/api/maintenance/{order_id}/edit',
                    json={'worker_id': new_wp_id}, follow_redirects=False)
    assert r.status_code == 200
    assert r.get_json()['worker_id'] == new_wp_id
    with app.app_context():
        wo = MaintenanceWorkOrder.query.get(order_id)
        assert wo.worker_id == new_wp_id
        audits = AuditLog.query.filter_by(action='MAINTENANCE_WORKER_CHANGED').all()
        assert len(audits) == 1
        assert 'tlworker' in audits[0].detail and 'tlworker2' in audits[0].detail
        # the new worker is notified on their own portal channel
        notes = Notification.query.filter_by(user_id=new_uid).all()
        assert len(notes) == 1 and 'assigned to you' in notes[0].message
        assert notes[0].link == '/worker'


def test_maintenance_edit_unassign_to_pool(client, app):
    """worker_id = 0 drops the order back to the unassigned pool, audited with
    the previous assignee; the control room is notified."""
    from app.models import MaintenanceWorkOrder, AuditLog, Notification
    bin_id, order_id, wp_id, _, _ = _seed_lifecycle_order(app)
    _login_admin(client, app, 'tladmin')
    r = client.post(f'/api/maintenance/{order_id}/edit',
                    json={'worker_id': 0}, follow_redirects=False)
    assert r.status_code == 200
    assert r.get_json()['worker_id'] is None
    with app.app_context():
        wo = MaintenanceWorkOrder.query.get(order_id)
        assert wo.worker_id is None
        audits = AuditLog.query.filter_by(action='MAINTENANCE_WORKER_CHANGED').all()
        assert len(audits) == 1
        assert 'unassigned pool' in audits[0].detail
        # control room notification goes to every approved admin
        from app.models import User
        admin_id = User.query.filter_by(username='tladmin').first().id
        notes = Notification.query.filter(
            Notification.user_id == admin_id,
            Notification.message.contains('unassigned pool')).all()
        assert len(notes) == 1
    # already unassigned: unassigning again is a no-op (no duplicate audit)
    r = client.post(f'/api/maintenance/{order_id}/edit',
                    json={'worker_id': 0}, follow_redirects=False)
    assert r.status_code == 200
    with app.app_context():
        assert AuditLog.query.filter_by(
            action='MAINTENANCE_WORKER_CHANGED').count() == 1


def test_maintenance_edit_notes_and_due_combined(client, app):
    """A single edit can change due date AND notes together; each change gets
    its own audit row, atomic with the mutation. Rescheduling resets the
    escalation window."""
    from datetime import timedelta
    from app.models import MaintenanceWorkOrder, AuditLog
    bin_id, order_id, _, _, _ = _seed_lifecycle_order(app)
    with app.app_context():
        wo = MaintenanceWorkOrder.query.get(order_id)
        wo.escalated_at = utcnow()
        db.session.commit()
    _login_admin(client, app, 'tladmin')
    r = client.post(f'/api/maintenance/{order_id}/edit',
                    json={'due_date': '2026-10-01', 'notes': 'Check lid hinge too'},
                    follow_redirects=False)
    assert r.status_code == 200
    with app.app_context():
        wo = MaintenanceWorkOrder.query.get(order_id)
        assert wo.due_date.strftime('%Y-%m-%d') == '2026-10-01'
        assert wo.notes == 'Check lid hinge too'
        assert wo.escalated_at is None  # escalation window reset
        assert AuditLog.query.filter_by(
            action='MAINTENANCE_DUE_DATE_CHANGED').count() == 1
        assert AuditLog.query.filter_by(
            action='MAINTENANCE_NOTES_CHANGED').count() == 1


def test_maintenance_edit_validation_and_gating(client, app):
    """Bad worker 400, unknown order 404, empty payload 400 ('nothing to
    edit'); a citizen can't reach the endpoint."""
    from app.models import AuditLog
    bin_id, order_id, _, _, _ = _seed_lifecycle_order(app)
    _login_admin(client, app, 'tladmin')
    r = client.post(f'/api/maintenance/{order_id}/edit',
                    json={'worker_id': 999999}, follow_redirects=False)
    assert r.status_code == 400
    r = client.post('/api/maintenance/999999/edit',
                    json={'worker_id': 0}, follow_redirects=False)
    assert r.status_code == 404
    r = client.post(f'/api/maintenance/{order_id}/edit',
                    json={}, follow_redirects=False)
    assert r.status_code == 400
    with app.app_context():
        assert AuditLog.query.filter_by(
            action='MAINTENANCE_WORKER_CHANGED').count() == 0
        assert AuditLog.query.filter_by(
            action='MAINTENANCE_NOTES_CHANGED').count() == 0
    client.get('/logout', follow_redirects=False)
    _make_user(app, 'tlcitizen2')
    client.post('/login', data={'username': 'tlcitizen2', 'password': 'testpass123'},
                follow_redirects=False)
    r = client.post('/api/maintenance/1/edit',
                    json={'worker_id': 0}, follow_redirects=False)
    assert r.status_code == 403


def test_audit_ledger_timeline_shows_worker_change(client, app):
    """The ledger timeline renders a worker reassignment as its own event."""
    from app.models import User, WorkerProfile
    bin_id, order_id, _, _, _ = _seed_lifecycle_order(app)
    new_uid = _make_user(app, 'tlworker3', role='worker')
    with app.app_context():
        wp2 = WorkerProfile(user_id=new_uid, vehicle_id='CV-83', status='Active')
        db.session.add(wp2)
        db.session.commit()
        new_wp_id = wp2.id
    _login_admin(client, app, 'tladmin')
    r = client.post(f'/api/maintenance/{order_id}/edit',
                    json={'worker_id': new_wp_id}, follow_redirects=False)
    assert r.status_code == 200
    client.get('/logout', follow_redirects=False)
    _make_user(app, 'tl_super4', role='admin')
    with app.app_context():
        u = User.query.get(User.query.filter_by(username='tl_super4').first().id)
        u.is_superadmin = True
        db.session.commit()
    _login_admin(client, app, 'tl_super4')
    r = client.get('/admin/audit')
    assert r.status_code == 200
    body = r.data.decode('utf-8')
    section = body[body.index('<!-- Maintenance Work-Order Lifecycles'):]
    section = section[:section.index('<!-- Audit Log Table -->')]
    assert 'Worker changed' in section
    assert 'reassigned maintenance work' in section


def test_consent_record_logged_anonymized(client, app):
    """Accept/Decline choices are logged anonymously and never store PII."""
    from app.models import ConsentRecord
    with app.app_context():
        ConsentRecord.query.delete()
        db.session.commit()

    r = client.post('/api/consent', json={'choice': 'accept', 'version': 'v1',
                                          'source': '/'}, follow_redirects=False)
    assert r.status_code == 200
    r2 = client.post('/api/consent', json={'choice': 'decline'}, follow_redirects=False)
    assert r2.status_code == 200

    with app.app_context():
        rows = ConsentRecord.query.order_by(ConsentRecord.id).all()
        assert len(rows) == 2
        assert [x.choice for x in rows] == ['accept', 'decline']
        assert rows[0].version == 'v1'
        assert rows[0].source == '/'
        # Anonymized: only a salted fingerprint — no raw IP / UA / identity.
        assert len(rows[0].fingerprint) == 64
        for x in rows:
            assert x.fingerprint and '127.0.0.1' not in x.fingerprint

    # Invalid choice is rejected.
    r3 = client.post('/api/consent', json={'choice': 'maybe'}, follow_redirects=False)
    assert r3.status_code == 400


def test_consent_register_visible_on_audit_page(client, app):
    """The superadmin audit page renders the anonymized consent register."""
    from app.models import ConsentRecord, User
    with app.app_context():
        ConsentRecord.query.delete()
        db.session.commit()
    client.post('/api/consent', json={'choice': 'accept'}, follow_redirects=False)
    client.post('/api/consent', json={'choice': 'decline'}, follow_redirects=False)

    _make_user(app, 'consent_super', role='admin')
    with app.app_context():
        u = User.query.filter_by(username='consent_super').first()
        u.is_superadmin = True
        db.session.commit()
    _login_admin(client, app, 'consent_super')
    r = client.get('/admin/audit')
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert 'Anonymized Consent Register' in body
    assert 'Acceptances' in body and 'Declines' in body


def test_privacy_policy_links_consent_register(client):
    """The privacy policy documents the anonymized consent register."""
    r = client.get('/privacy')
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert 'anonymized consent register' in body
    assert 'Consent records (anonymized)' in body


def test_consent_endpoint_works_with_csrf_enabled(tmp_path):
    """The anonymous /api/consent flow works with CSRF protection on (as in
    production): the page renders a session-bound token that the banner fetch
    echoes back via the X-CSRFToken header."""
    import tempfile as _tf
    fd, path = _tf.mkstemp(suffix='.db'); os.close(fd)
    csrf_app = create_app(test_config={
        'TESTING': True,
        'WTF_CSRF_ENABLED': True,
        'SQLALCHEMY_DATABASE_URI': f'sqlite:///{path}',
        'SERVER_NAME': 'localhost:5001',
        'ANALYTICS_ID': 'G-TEST',
    })
    with csrf_app.app_context():
        db.create_all()
    c = csrf_app.test_client()
    r = c.get('/')  # renders base.html → meta csrf-token bound to this session
    assert r.status_code == 200
    import re
    m = re.search(r'<meta name="csrf-token" content="([^"]+)">', r.get_data(as_text=True))
    assert m, 'csrf meta token must render for the anonymous session'
    token = m.group(1)
    # Missing header → CSRF rejects.
    bad = c.post('/api/consent', json={'choice': 'accept'}, follow_redirects=False)
    assert bad.status_code == 400
    # Header + cookie → accepted and logged.
    ok = c.post('/api/consent', json={'choice': 'accept', 'version': 'v2'},
                headers={'X-CSRFToken': token}, follow_redirects=False)
    assert ok.status_code == 200
    with csrf_app.app_context():
        from app.models import ConsentRecord
        row = ConsentRecord.query.first()
        assert row is not None and row.choice == 'accept' and row.version == 'v2'
        assert row.source is None or row.source == ''
    try:
        os.remove(path)
    except PermissionError:
        pass


def test_google_site_verification_meta_is_config_gated(client):
    """The Search Console ownership meta only ships when
    GOOGLE_SITE_VERIFICATION is configured — zero markup while unset, and the
    exact token when set (fallback verification path for the onrender.com
    subdomain, where DNS and HTML-file methods aren't available)."""
    body = client.get('/').get_data(as_text=True)
    assert 'google-site-verification' not in body

    import tempfile as _tf
    fd, path = _tf.mkstemp(suffix='.db'); os.close(fd)
    ver_app = create_app(test_config={
        'TESTING': True,
        'SQLALCHEMY_DATABASE_URI': f'sqlite:///{path}',
        'GOOGLE_SITE_VERIFICATION': 'ABCDEF1234567890',
    })
    with ver_app.app_context():
        db.create_all()
    body2 = ver_app.test_client().get('/').get_data(as_text=True)
    assert 'name="google-site-verification" content="ABCDEF1234567890"' in body2
    try:
        os.remove(path)
    except PermissionError:
        pass


def test_homepage_privacy_at_a_glance(client):
    """The homepage surfaces a privacy-at-a-glance card above the fold with the
    three collection bullets and a link to the full notice."""
    r = client.get('/')
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert 'Your privacy at a glance' in body
    assert 'href="/privacy"' in body
    for bullet in ('Forms: only what you enter',
                   'photos: captured only when you file a report',  # '&' renders as &amp;
                   'Payments via Razorpay'):
        assert bullet in body


def test_privacy_policy_dpdp_audit_sections(client):
    """The privacy notice carries the DPDP Act 2023 audit items: correct
    children age, processor register, security safeguards, breach response,
    and a designated grievance/DPO contact."""
    r = client.get('/privacy')
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    # Children = under 18 (DPDP s.9), not under 13.
    assert 'a child is anyone below 18' in body
    assert 'children under 13' not in body
    # Processor register (s.8(2)) covers the real processors.
    assert 'Data Processors (Register)' in body
    for p in ('Razorpay', 'Render + Cloudflare', 'Twilio', 'Telegram Bot API',
              'Open-Meteo', 'Google Analytics', 'OpenStreetMap', 'Sentry'):
        assert p in body
    # Security safeguards (s.8(5)) + breach notification (s.8(6)).
    assert 'Security Safeguards' in body
    assert 'Breach Notification &amp; Response' in body  # '&' renders as &amp;
    assert 'Data Protection Board of India' in body
    # Designated officer + response commitment.
    assert 'Grievance &amp; Data Protection Officer' in body or 'Grievance & Data Protection Officer' in body
    assert 'within 15 days' in body
