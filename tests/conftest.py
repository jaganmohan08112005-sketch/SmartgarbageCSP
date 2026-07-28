import os
import sys
import tempfile
import socket
import json
from contextlib import closing

import pytest

# Ensure project root on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app, db
from app.models import User, SmartBin, Schedule, Complaint, WorkerProfile, BWGDeclaration, PAYTInvoice, WasteDeclaration, Notification
from werkzeug.security import generate_password_hash


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _free_port():
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


def _complete_mfa(client, app, username, password="testpass123"):
    """Log in a user, read the generated OTP from DB, and complete MFA.
    The app context must already be active (true when called from fixtures)."""
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)
    u = User.query.filter_by(username=username).first()
    if u and u.otp:
        otp = u.otp
    else:
        return
    client.post("/mfa-verify", data={"otp": otp}, follow_redirects=False)


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
# App fixture
# ---------------------------------------------------------------------------
@pytest.fixture
def app():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    app = create_app(test_config={
        "TESTING": True,
        "WTF_CSRF_ENABLED": False,
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{path}",
        "SERVER_NAME": "localhost:5001"
    })
    with app.app_context():
        db.create_all()
        _seed(app)
        yield app
        db.session.remove()
    with app.app_context():
        db.engine.dispose()
    os.remove(path)


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
def admin_client(client, app):
    # Use session_transaction to bypass MFA flow
    with client.session_transaction() as sess:
        u = User.query.filter_by(username="qa_admin").first()
        sess['user_id'] = u.id
        sess['username'] = 'qa_admin'
        sess['role'] = 'admin'
        sess['mfa_pending'] = False
    return client
