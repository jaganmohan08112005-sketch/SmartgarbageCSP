import sys
import json
import pytest
from app import create_app, db
from app.models import User, Complaint, BWGDeclaration, WorkerProfile, Notification, SmartBin
from werkzeug.security import generate_password_hash


@pytest.fixture
def app():
    fd, path = __import__('tempfile').mkstemp(suffix='.db')
    import os
    os.close(fd)
    a = create_app()
    a.config['TESTING'] = True
    a.config['WTF_CSRF_ENABLED'] = False
    a.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{path}'
    with a.app_context():
        db.create_all()
        yield a
        db.session.remove()


@pytest.fixture
def client(app):
    return app.test_client()


def _login(client, app, username, password='demo123', role='citizen', phone='+919876543210'):
    # ensure user exists
    with app.app_context():
        if not User.query.filter_by(username=username).first():
            u = User(username=username, password_hash=generate_password_hash(password),
                     role=role, phone=phone, is_approved=True)
            db.session.add(u)
            db.session.commit()
    r = client.post('/login', data={'username': username, 'password': password}, follow_redirects=False)
    assert r.status_code == 302, f"login {username} -> {r.status_code}"
    if role in ('admin', 'worker'):
        with app.app_context():
            otp = User.query.filter_by(username=username).first().otp
        r2 = client.post('/mfa-verify', data={'otp': otp}, follow_redirects=False)
        assert r2.status_code == 302


def test_public_home(client):
    r = client.get('/')
    assert r.status_code == 200
    assert b'SmartGarbage' in r.data or b'smartgarbage' in r.data.lower()


def test_citizen_register_login_dashboard(client, app):
    r = client.post('/register', data={
        'username': 'wt_citizen', 'password': 'demo123', 'phone': '+919876543211'}, follow_redirects=False)
    assert r.status_code in (302, 200)
    _login(client, app, 'wt_citizen')
    r = client.get('/dashboard')
    assert r.status_code == 200
    assert b'Eco-Reward' in r.data or b'Wallet' in r.data
    assert b'Cleanliness Leaderboard' in r.data


def test_citizen_declare_waste(client, app):
    _login(client, app, 'wt_citizen')
    r = client.post('/dashboard/declare-waste', data={
        'wet_kg': '2.5', 'dry_kg': '1.2', 'sanitary_kg': '0.3',
        'hazardous_kg': '0.1', 'ward': 'Ward 2 - Chintalavalasa Junction'}, follow_redirects=False)
    assert r.status_code == 302
    with app.app_context():
        assert db.session.query(db.func.count(User.query.filter_by(username='wt_citizen').exists())).scalar()


def test_anonymous_illegal_dump(client):
    r = client.get('/report-illegal')
    assert r.status_code == 200
    r = client.post('/report-illegal', data={
        'category': 'E-Waste', 'description': 'tour dump',
        'ward': 'Ward 1 - MVGR College Area', 'latitude': '18.0565', 'longitude': '83.4040'}, follow_redirects=True)
    assert r.status_code in (200, 302)


def test_worker_flow(client, app):
    _login(client, app, 'wt_worker', role='worker', phone='+919876543212')
    r = client.get('/worker')
    assert r.status_code == 200
    assert b'Offload' in r.data or b'Geo' in r.data


def test_admin_console(client, app):
    _login(client, app, 'wt_admin', role='admin', phone='+919876543213')
    r = client.get('/admin')
    assert r.status_code == 200
    for label in [b'Live', b'Fleet', b'Audit', b'Firmware']:
        assert label in r.data, f"admin missing {label}"


def test_route_optimize(client, app):
    _login(client, app, 'wt_admin2', role='admin', phone='+919876543214')
    r = client.get('/api/route-optimize')
    assert r.status_code == 200
    d = json.loads(r.data)
    assert 'total_distance' in d


def test_audit_trail_requires_superadmin(client, app):
    # regular admin cannot reach audit
    _login(client, app, 'wt_admin3', role='admin', phone='+919876543215')
    r = client.get('/admin/audit', follow_redirects=False)
    assert r.status_code in (302, 303, 403)


def test_ota_firmware_push(client, app):
    _login(client, app, 'wt_admin4', role='admin', phone='+919876543216')
    r = client.post('/admin/firmware/upload', data={
        'version': '3.0.1', 'description': 'tour', 'target_bins': 'ALL'}, follow_redirects=False)
    assert r.status_code in (302, 200)


def test_analytics_and_csrd(client, app):
    _login(client, app, 'wt_admin5', role='admin', phone='+919876543217')
    r = client.get('/analytics')
    assert r.status_code == 200
    r = client.get('/analytics/csrd-export')
    assert r.status_code == 200
    assert 'waste_declarations' in json.loads(r.data)


def test_iot_telemetry_ingestion(client, app):
    with app.app_context():
        if not SmartBin.query.filter_by(hardware_id='BIN-402').first():
            db.session.add(SmartBin(hardware_id='BIN-402', latitude=18.05, longitude=83.40,
                                 level=96, temperature=71.0, methane=640.0, ward='Ward 1 - MVGR College Area'))
            db.session.commit()
    r = client.post('/api/bin-telemetry', json={
        'hardware_id': 'BIN-402', 'level': 96, 'temperature': 71.0,
        'methane': 640.0, 'battery_level': 80})
    assert r.status_code == 200
    d = json.loads(r.data)
    assert 'level' in d and 'hardware_id' in d


def test_superadmin_panel_access(client, app):
    # superadmin user
    with app.app_context():
        if not User.query.filter_by(username='wt_super').first():
            u = User(username='wt_super', password_hash=generate_password_hash('demo123'),
                     role='admin', phone='+919876543218', is_superadmin=True, is_approved=True)
            db.session.add(u)
            db.session.commit()
    _login(client, app, 'wt_super')
    r = client.get('/admin/super')
    assert r.status_code == 200
    r = client.get('/admin/audit')
    assert r.status_code == 200
    assert b'Audit' in r.data


def test_state_portal_export(client, app):
    _login(client, app, 'wt_admin6', role='admin', phone='+919876543219')
    r = client.get('/analytics/state-portal-export')
    assert r.status_code == 200
    assert 'indicators' in json.loads(r.data)


def test_transparency_view_public(client):
    r = client.get('/transparency')
    assert r.status_code == 200
    r = client.get('/ward/Ward%201%20-%20MVGR%20College%20Area')
    assert r.status_code == 200


def test_full_resolution_notification(client, app):
    # citizen reports, admin resolves, citizen gets notification
    _login(client, app, 'wt_cit2')
    client.post('/report', data={
        'name': 'wt_cit2', 'phone': '+919876543220', 'ward': 'Ward 1 - MVGR College Area',
        'address': 'Gate', 'description': 'overflow', 'latitude': '18.05', 'longitude': '83.40',
        'report_time': '2026-07-18T10:00'}, follow_redirects=True)
    client.get('/logout', follow_redirects=True)
    _login(client, app, 'wt_admin7', role='admin', phone='+919876543221')
    with app.app_context():
        cid = Complaint.query.filter_by(name='wt_cit2').first().id
    r = client.get(f'/resolve/{cid}', follow_redirects=False)
    assert r.status_code == 302
    with app.app_context():
        from app.models import User as U
        uid = U.query.filter_by(username='wt_cit2').first().id
        assert Notification.query.filter_by(user_id=uid).count() == 1
