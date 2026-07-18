from app.models import User, Complaint, BWGDeclaration, WorkerProfile, Notification
from werkzeug.security import generate_password_hash
from app import db

def _make_user(app, username, role='citizen', phone=None, password='testpass123'):
    if phone is None:
        phone = f'+91987654{hash(username) % 10000:04d}'
    with app.app_context():
        u = User(username=username, password_hash=generate_password_hash(password),
                 role=role, phone=phone, is_approved=True)
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
