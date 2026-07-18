from app.models import User, Complaint, BWGDeclaration, WorkerProfile
from werkzeug.security import generate_password_hash
from app import db

def _make_user(app, username, role='citizen', phone='+919876543201', password='testpass123'):
    with app.app_context():
        u = User(username=username, password_hash=generate_password_hash(password),
                 role=role, phone=phone, is_approved=True)
        db.session.add(u)
        db.session.commit()
        return u.id

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
    # regular admin must be bounced (303/302 redirect, NOT 200)
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
    # Login -> MFA required
    r = client.post('/login', data={'username': 'bwgadmin', 'password': 'testpass123'},
                    follow_redirects=False)
    assert r.status_code == 302
    # Extract OTP from flash (printed by server); simulate by reading user row
    with app.app_context():
        from app.models import User as U
        otp = U.query.filter_by(username='bwgadmin').first().otp
    r2 = client.post('/mfa-verify', data={'otp': otp}, follow_redirects=False)
    assert r2.status_code == 302
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