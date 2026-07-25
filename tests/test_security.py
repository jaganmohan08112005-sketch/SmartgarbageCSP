"""Regression tests for the security hardening pass (see PR #1)."""
import io

from werkzeug.security import generate_password_hash


def _make_user(app, username, role='citizen', phone=None):
    from app import db
    from app.models import User
    with app.app_context():
        user = User(username=username, role=role, phone=phone,
                    password_hash=generate_password_hash(username), is_approved=True)
        db.session.add(user)
        db.session.commit()
        return user.id


def _login(client, username):
    return client.post('/login', data={'username': username, 'password': username},
                       follow_redirects=True)


def test_payt_invoice_is_not_readable_by_another_citizen(client, app):
    from app import db
    from app.models import PAYTInvoice
    owner_id = _make_user(app, 'owner_citizen', phone='+919876500101')
    _make_user(app, 'other_citizen', phone='+919876500102')
    with app.app_context():
        invoice = PAYTInvoice(user_id=owner_id, period='2026-07', amount_rs=1234.5,
                              status='Pending')
        db.session.add(invoice)
        db.session.commit()
        inv_id = invoice.id

    _login(client, 'other_citizen')
    resp = client.get(f'/payt/pay/{inv_id}')
    assert resp.status_code == 403
    assert b'1234.5' not in resp.data


def test_payt_invoice_is_readable_by_its_owner(client, app):
    from app import db
    from app.models import PAYTInvoice
    owner_id = _make_user(app, 'owner_citizen2', phone='+919876500103')
    with app.app_context():
        invoice = PAYTInvoice(user_id=owner_id, period='2026-07', amount_rs=99.0,
                              status='Pending')
        db.session.add(invoice)
        db.session.commit()
        inv_id = invoice.id

    _login(client, 'owner_citizen2')
    assert client.get(f'/payt/pay/{inv_id}').status_code == 200


def test_login_rotates_the_session(client, app):
    _make_user(app, 'fixation_citizen', phone='+919876500104')
    with client.session_transaction() as sess:
        sess['planted'] = 'attacker-value'
    _login(client, 'fixation_citizen')
    with client.session_transaction() as sess:
        assert 'planted' not in sess
        assert sess['username'] == 'fixation_citizen'


def test_language_choice_survives_login(client, app):
    _make_user(app, 'lang_citizen', phone='+919876500105')
    client.get('/set-lang/te')
    _login(client, 'lang_citizen')
    with client.session_transaction() as sess:
        assert sess.get('lang') == 'te'


def test_set_lang_next_rejects_protocol_relative_url(client):
    resp = client.get('/set-lang/en?next=//evil.example.com')
    assert not resp.headers['Location'].startswith('//evil.example.com')


def test_machine_endpoints_are_csrf_exempt(app):
    csrf_exempt_paths = {'/api/bin-telemetry', '/webhook/whatsapp', '/webhook/telegram'}
    app.config['WTF_CSRF_ENABLED'] = True
    client = app.test_client()
    for path in csrf_exempt_paths:
        resp = client.post(path, data={'hardware_id': 'NOPE'})
        assert resp.status_code != 400 or b'CSRF' not in resp.data, path


def test_webhook_media_url_allowlist_blocks_ssrf():
    from app.routes import _is_allowed_media_url
    assert _is_allowed_media_url('https://api.twilio.com/Media/abc')
    assert not _is_allowed_media_url('http://169.254.169.254/latest/meta-data/')
    assert not _is_allowed_media_url('https://api.twilio.com.evil.example/x')
    assert not _is_allowed_media_url('http://localhost:5000/admin')


def test_non_image_upload_is_rejected(app):
    from werkzeug.datastructures import FileStorage
    from app.routes import save_compressed_photo
    payload = FileStorage(stream=io.BytesIO(b'<script>alert(1)</script>'),
                          filename='payload.html', content_type='text/html')
    with app.test_request_context():
        assert save_compressed_photo(payload, 'complaint') is None


def test_mfa_otp_is_burned_after_repeated_wrong_codes(client, app):
    from app.models import User
    _make_user(app, 'otp_worker', role='worker', phone='+919876500106')
    _login(client, 'otp_worker')
    for _ in range(4):
        resp = client.post('/mfa-verify', data={'otp': '000000'}, follow_redirects=True)
        assert b'Invalid or expired OTP' in resp.data
    resp = client.post('/mfa-verify', data={'otp': '000000'}, follow_redirects=True)
    with app.app_context():
        assert User.query.filter_by(username='otp_worker').first().otp is None
    with client.session_transaction() as sess:
        assert 'user_id' not in sess


def test_security_headers_present(client):
    resp = client.get('/login')
    assert resp.headers['X-Content-Type-Options'] == 'nosniff'
    assert resp.headers['Referrer-Policy'] == 'strict-origin-when-cross-origin'
    assert 'Permissions-Policy' in resp.headers
