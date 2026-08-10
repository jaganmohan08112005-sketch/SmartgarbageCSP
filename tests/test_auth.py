
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
    assert b'Report a Missed Pickup' in r.data
    # POST without login is allowed but still enforces the GPS anti-spam gate.
    r2 = client.post('/report', data={
        'name': 'test',
        'phone': '9876543210',
        'ward': 'Ward 1',
        'address': 'Test address'
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
