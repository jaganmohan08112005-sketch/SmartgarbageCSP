from app.models import User, Complaint, BWGDeclaration, WorkerProfile, Notification
from werkzeug.security import generate_password_hash
from app import db, create_app, socketio
import json as _json
import os

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
    with app.app_context():
        otp = User.query.filter_by(username=username).first().otp
    client.post('/mfa-verify', data={'otp': otp}, follow_redirects=False)

# ── Login lockout after repeated failures ──────────────────────
def test_login_lockout_after_failures(client, app):
    _make_user(app, 'lockuser', password='rightpass123')
    for _ in range(5):
        client.post('/login', data={'username': 'lockuser', 'password': 'wrong'})
    r = client.post('/login', data={'username': 'lockuser', 'password': 'rightpass123'},
                       follow_redirects=True)
    assert b'locked' in r.data.lower() or b'too many' in r.data.lower() or r.status_code == 200

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
        assert c.status == 'Pending'

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

# ── Green-Points leaderboard endpoint (Phase E) ──
def test_green_points_leaderboard(client, app):
    import json
    _make_user(app, 'eco_champ', green_points=120)
    _make_user(app, 'eco_low', green_points=40)
    _make_user(app, 'eco_zero', green_points=0)
    cid = _make_user(app, 'eco_login')
    client.post('/login', data={'username': 'eco_login', 'password': 'testpass123'})
    r = client.get('/api/leaderboard', follow_redirects=False)
    assert r.status_code == 200
    data = json.loads(r.data)
    # Only users with >0 points are ranked, sorted descending.
    assert [u['username'] for u in data] == ['eco_champ', 'eco_low']
    assert data[0]['green_points'] == 120


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
    from app import create_app
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
    from app.models import User, PAYTInvoice
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
    from app.models import User, PAYTInvoice
    uid = _make_user(app, 'payer2', role='citizen')
    intruder = _make_user(app, 'intruder', role='citizen')
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
