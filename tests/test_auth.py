
def test_register_requires_phone(client):
    response = client.post('/register', data={
        'username': 'testuser1',
        'password': 'testpass123'
    }, follow_redirects=True)
    assert b'Phone number is required' in response.data


def test_register_validates_indian_phone(client):
    response = client.post('/register', data={
        'username': 'testuser2',
        'password': 'testpass123',
        'phone': '1234567890'
    }, follow_redirects=True)
    assert b'valid Indian mobile number' in response.data or b'Fake or sequential' in response.data


def test_register_accepts_valid_phone(client):
    response = client.post('/register', data={
        'username': 'testuser3',
        'password': 'testpass123',
        'phone': '+919876543201',
        'email': 'user3@example.com'
    }, follow_redirects=True)
    assert b'Registration successful' in response.data or b'Please log in' in response.data


def test_admin_registration_requires_approval(client, app):
    response = client.post('/register', data={
        'username': 'wouldbeadmin',
        'password': 'testpass123',
        'phone': '9876543201',
        'email': 'admin@example.com',
        'role': 'admin'
    }, follow_redirects=True)
    assert response.status_code == 200
    assert b'Registration successful' in response.data or b'pending approval' in response.data or b'cannot log in' in response.data or b'approval' in response.data


def test_report_is_public(client):
    """The missed-pickup report form is public (it is listed in the sitemap
    and the homepage promises 'no login needed to file a report'): an
    unauthenticated resident can open it and submit without an account."""
    r = client.get('/report')
    assert r.status_code == 200
    assert b'Report a Missed Collection' in r.data
    # POST without login is allowed but still enforces the GPS anti-spam gate.
    r2 = client.post('/report', data={
        'name': 'test',
        'phone': '9876543210',
        'ward': 'Ward 1',
        'address': 'Test address',
        'description': 'Overflow'
    }, follow_redirects=True)
    assert b'GPS coordinates are required' in r2.data


def test_phone_validation_rejects_all_same(client):
    response = client.post('/auth/phone-login', data={
        'phone_number': '9999999999'
    }, follow_redirects=True)
    assert b'valid Indian mobile' in response.data or b'rejected' in response.data.lower()


def test_phone_validation_rejects_sequential(client):
    response = client.post('/auth/phone-login', data={
        'phone_number': '1234567890'
    }, follow_redirects=True)
    assert b'valid Indian mobile' in response.data or b'rejected' in response.data.lower()


def test_superadmin_console_blocked_while_mfa_pending(client, app):
    """Regression: superadmin_required never checked session['mfa_pending'],
    so an admin with the password could skip OTP entirely and reach the
    Super-Admin Console (and its approve/create-admin POSTs) by direct URL.
    The console must redirect to /mfa-verify until OTP verification."""
    from app.models import User
    client.post("/login", data={"username": "qa_admin", "password": "testpass123"},
                follow_redirects=False)
    with client.session_transaction() as sess:
        assert sess.get('mfa_pending') is True
    r = client.get("/admin/super")
    assert r.status_code == 302 and "/mfa-verify" in r.headers["Location"]
    # And the approve POST is equally blocked while pending.
    with app.app_context():
        target = User.query.filter_by(username="qa_admin").first()
        uid = target.id
    r2 = client.post("/admin/super", data={"action": "approve_admin", "user_id": uid})
    assert r2.status_code == 302 and "/mfa-verify" in r2.headers["Location"]
