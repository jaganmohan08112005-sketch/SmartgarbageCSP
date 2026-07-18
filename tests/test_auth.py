from app.models import User
from werkzeug.security import generate_password_hash

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
        'phone': '+919876543201'
    }, follow_redirects=True)
    assert b'Registration successful' in response.data or b'Please log in' in response.data

def test_admin_registration_forced_to_citizen(client, app):
    from app import db
    response = client.post('/register', data={
        'username': 'wouldbeadmin',
        'password': 'testpass123',
        'phone': '9876543201',
        'role': 'admin'
    }, follow_redirects=True)
    with app.app_context():
        u = User.query.filter_by(username='wouldbeadmin').first()
        assert u is not None
        assert u.role == 'citizen'

def test_report_requires_login(client):
    response = client.post('/report', data={
        'name': 'test',
        'phone': '9876543210',
        'ward': 'Ward 1',
        'address': 'Test address'
    }, follow_redirects=True)
    assert b'login' in response.data.lower() or response.status_code == 302

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