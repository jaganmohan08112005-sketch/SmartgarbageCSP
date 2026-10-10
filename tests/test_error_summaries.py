"""GOV.UK-style error-summary coverage.

The report and track forms render an `sg-error-summary` block on server-side
validation (see tests/test_features.py::test_report_requires_description...).
These tests extend that contract to the login, register, contact and schedule
forms so every form matches.
"""


def test_register_shows_error_summary(client):
    r = client.post('/register', data={'username': 'sx', 'password': 'testpass123'},
                    follow_redirects=True)
    body = r.data.decode()
    assert r.status_code == 200
    assert 'sg-error-summary' in body
    assert 'register-error-summary-title' in body
    assert 'Phone number is required' in body
    assert 'href="#reg_phone"' in body


def test_login_shows_error_summary(client):
    r = client.post('/login', data={'username': 'nobody-xyz', 'password': 'wrongpass'},
                    follow_redirects=True)
    body = r.data.decode()
    assert r.status_code == 200
    assert 'sg-error-summary' in body
    assert 'login-error-summary-title' in body
    assert 'Invalid username or password' in body
    assert 'href="#lg_username"' in body


def test_phone_login_error_activates_phone_tab(client):
    r = client.post('/auth/phone-login', data={'phone_number': ''}, follow_redirects=True)
    body = r.data.decode()
    assert r.status_code == 200
    assert 'sg-error-summary' in body
    assert 'href="#otp_phone"' in body
    # the phone pane must be the one shown when its field has an error
    assert 'show active" id="phone-login"' in body


def test_contact_shows_error_summary(client):
    r = client.post('/contact', data={'name': '', 'email': '', 'subject': '', 'message': ''},
                    follow_redirects=True)
    body = r.data.decode()
    assert r.status_code == 200
    assert 'sg-error-summary' in body
    assert 'contact-error-summary-title' in body
    assert 'href="#contactName"' in body


def test_schedule_shows_error_summary(client):
    r = client.post('/schedule', data={'ward': ''}, follow_redirects=True)
    body = r.data.decode()
    assert r.status_code == 200
    assert 'sg-error-summary' in body
    assert 'schedule-error-summary-title' in body
    assert 'href="#schedWard"' in body


def test_clean_forms_have_no_error_summary(client):
    """A plain GET must never render the summary block."""
    for path in ('/login', '/register', '/contact', '/schedule'):
        body = client.get(path).data.decode()
        assert 'sg-error-summary' not in body, path
