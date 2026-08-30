
import os
import sys
import tempfile
import threading
import time
import socket
from contextlib import closing

import pytest

# Ensure project root on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app, db
from app.models import User, SmartBin, Schedule, Complaint, WorkerProfile
from werkzeug.security import generate_password_hash


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _free_port():
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


def _complete_mfa(client, username, password="testpass123", role=None):
    """Log in a user, read the generated OTP from the session (dev_otp), and
    complete MFA. Assumes an active app context (provided by the app fixture)."""
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)
    with client.session_transaction() as sess:
        otp = sess.get('dev_otp')
    if not otp:
        return
    client.post("/mfa-verify", data={"otp": otp}, follow_redirects=False)


# ---------------------------------------------------------------------------
# App fixture
# ---------------------------------------------------------------------------
def _make_app(db_uri):
    return create_app(test_config={
        "TESTING": True,
        "WTF_CSRF_ENABLED": False,
        "SQLALCHEMY_DATABASE_URI": db_uri,
        "SERVER_NAME": "localhost:5001"
    })


@pytest.fixture
def app():
    test_db_url = os.environ.get('TEST_DATABASE_URL')
    if not test_db_url:
        raise RuntimeError(
            "TEST_DATABASE_URL must be set to a Supabase/PostgreSQL connection string.\n"
            "Example: export TEST_DATABASE_URL='postgresql://user:pass@host:5432/test_db?sslmode=require'"
        )
    # Postgres mode: the service-container database is shared across tests,
    # so drop/recreate the schema per test to keep each test isolated.
    app = _make_app(test_db_url)
    with app.app_context():
        db.drop_all()
        db.create_all()
        _seed(app)
        yield app
        db.session.remove()
        db.drop_all()
    with app.app_context():
        db.engine.dispose()
        with app.app_context():
            db.engine.dispose()
        os.remove(path)


def _seed(app):
    """Insert deterministic seed data for audit/flow tests."""
    with app.app_context():
        if User.query.filter_by(username="qa_citizen").first():
            return
        citizen = User(
            username="qa_citizen",
            email="citizen@example.com",
            password_hash=generate_password_hash("testpass123"),
            role="citizen",
            phone="+919876543210",
            is_approved=True,
            green_points=10,
        )
        admin = User(
            username="qa_admin",
            email="admin@example.com",
            password_hash=generate_password_hash("testpass123"),
            role="admin",
            phone="+919876543211",
            is_approved=True,
            is_superadmin=True,
        )
        worker = User(
            username="qa_worker",
            email="worker@example.com",
            password_hash=generate_password_hash("testpass123"),
            role="worker",
            phone="+919876543212",
            is_approved=True,
        )
        db.session.add_all([citizen, admin, worker])
        db.session.commit()

        wp = WorkerProfile(
            user_id=worker.id,
            vehicle_id="CV-01",
            status="Active",
            performance_rating=5.0,
            is_informal_picker=False,
        )
        db.session.add(wp)

        for i, (hw, lat, lon, ward) in enumerate([
            ("BIN-001", 18.0552, 83.4051, "Ward 1 - MVGR College Area"),
            ("BIN-002", 18.0675, 83.4094, "Ward 2 - Chintalavalasa Junction"),
            ("BIN-003", 18.0702, 83.4153, "Ward 3 - RTC Colony"),
        ], start=1):
            db.session.add(
                SmartBin(
                    hardware_id=hw,
                    latitude=lat,
                    longitude=lon,
                    level=20 * i,
                    ward=ward,
                    status="Safe",
                )
            )

        db.session.add_all([
            Schedule(ward="Ward 1 - MVGR College Area", day="Monday", time_slot="07:00-08:00", vehicle_id="CV-01"),
            Schedule(ward="Ward 2 - Chintalavalasa Junction", day="Tuesday", time_slot="08:00-09:00", vehicle_id="CV-02"),
        ])

        c = Complaint(
            name="qa_citizen",
            phone="+919876543210",
            ward="Ward 1 - MVGR College Area",
            address="Near gate",
            description="Overflow",
            status="Pending",
            user_id=citizen.id,
        )
        db.session.add(c)
        db.session.commit()


# ---------------------------------------------------------------------------
# Client fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def citizen_client(client):
    client.post("/login", data={"username": "qa_citizen", "password": "testpass123"}, follow_redirects=False)
    return client


@pytest.fixture
def admin_client(client):
    _complete_mfa(client, "qa_admin")
    return client


# ---------------------------------------------------------------------------
# Playwright / live-server fixtures
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session")
def live_server_url():
    port = _free_port()
    test_db_url = os.environ.get('TEST_DATABASE_URL')
    if not test_db_url:
        raise RuntimeError(
            "TEST_DATABASE_URL must be set for live server tests.\n"
            "Example: export TEST_DATABASE_URL='postgresql://user:pass@host:5432/test_db?sslmode=require'"
        )
    app = create_app(test_config={
        "TESTING": False,
        "WTF_CSRF_ENABLED": False,
        "SQLALCHEMY_DATABASE_URI": test_db_url
    })
    with app.app_context():
        db.create_all()
        _seed(app)

    def _run():
        app.run(host="127.0.0.1", port=port, use_reloader=False, threaded=True)

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    time.sleep(2)
    yield f"http://127.0.0.1:{port}"
    # Teardown omitted intentionally for temp DB; process exits with session.


@pytest.fixture(scope="session")
def browser(playwright):
    browser = playwright.chromium.launch(headless=True)
    yield browser
    browser.close()


@pytest.fixture
def page(browser, live_server_url):
    context = browser.new_context(base_url=live_server_url, viewport={"width": 1280, "height": 900})
    page = context.new_page()
    yield page
    context.close()
