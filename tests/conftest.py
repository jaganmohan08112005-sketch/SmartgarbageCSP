import os
import sys
import socket
import sqlite3
from contextlib import closing
from datetime import date, datetime

import pytest

# Ensure project root on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app, db
from app.models import User, SmartBin, Schedule, Complaint, WorkerProfile
from werkzeug.security import generate_password_hash


# ---------------------------------------------------------------------------
# sqlite3 datetime adapters (Python 3.12 deprecation recipe)
# ---------------------------------------------------------------------------
# Python 3.12 deprecated sqlite3's implicit datetime adapters, and the suite
# binds raw datetime/date objects to SQLite in several modules (fixture
# inserts into TIMESTAMP columns, SQLAlchemy-side window cutoffs against
# sqlite:// URLs). Bindings happen at test time, so the replacement recipe
# from the sqlite3 documentation is registered here, once, at conftest import
# — every test module inherits it without re-registering. The recipe writes
# byte-identical text to the deprecated default adapter (ISO 8601 + " ",
# verified) so any stored text or WHERE window comparison sees exactly what
# it always saw:
#   https://docs.python.org/3/library/sqlite3.html#sqlite3-adapters
#
# Regression tripwires, in order of loudness:
#   * pytest.ini filterwarnings turns any surviving default-adapter
#     DeprecationWarning into an ERROR, suite-wide.
#   * tests/test_weekly_report_script.py::test_no_sqlite_datetime_adapter_deprecations
#     pins both binding surfaces of that module-by-name via recwarn.
# No converters: no test opens a connection with detect_types, so nothing
# reads stored text back as an implicit datetime object.


def _adapt_sqlite_date(val):
    return val.isoformat()


def _adapt_sqlite_datetime(val):
    return val.isoformat(" ")


sqlite3.register_adapter(date, _adapt_sqlite_date)
sqlite3.register_adapter(datetime, _adapt_sqlite_datetime)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _free_port():
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


def _complete_mfa(client, app, username, password="testpass123"):
    """Log in a user, read the generated OTP from the session (dev_otp), and
    complete MFA. The app context must already be active (true when called
    from fixtures)."""
    client.post("/login", data={"username": username, "password": password}, follow_redirects=False)
    with client.session_transaction() as sess:
        otp = sess.get('dev_otp')
    if not otp:
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
            email_verified=True,
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
# xdist isolation: one PostgreSQL database per worker
# ---------------------------------------------------------------------------
def _give_this_worker_its_own_database():
    """Under pytest-xdist, point TEST_DATABASE_URL at this worker's own DB.

    The app fixture drops/recreates the schema per test, so two workers
    sharing one database would drop each other's tables mid-test (that is why
    the suite used to be forced sequential with -n 0). Instead each worker
    re-creates its own database ``sg_test_<worker>`` in the SAME cluster
    TEST_DATABASE_URL already points to (the URI user created it with needs
    CREATE DATABASE rights — the local pgserver cluster and the CI service
    container both connect as a superuser), then rewrites its own
    os.environ copy of the variable. Every later reader in this process —
    the app fixture here, tests/qa/conftest.py's app and session-scoped
    Playwright live-server fixtures, and the in-test guards (e.g.
    tests/test_features.py:6361) — therefore sees the worker's database
    with no further changes.

    A leftover database from a previous crashed run is dropped before
    re-creating: at worker start this process owns no connections to it, so a
    plain DROP cannot hit the 'database is being accessed' error.

    The bootstrap also has to be *idempotent within its worker process*.
    Because ``tests/`` has no ``__init__.py``, test code that says
    ``from tests.conftest import _complete_mfa`` (tests/test_features.py)
    loads this file a second time under a different sys.modules key, which
    re-runs this module-level call while the worker already holds open
    connections to its own database — a second DROP would then die with
    ObjectInUse (the "other user" being ourselves). A marker in os.environ
    survives re-import (module-level names would not: the second module
    object gets its own namespace) and skips the drop/CREATE entirely.

    Non-xdist runs (-n 0, plain single-process pytest) are untouched: no
    worker env var, no rewrite, the caller's database as-is.
    """
    wid = os.environ.get('PYTEST_XDIST_WORKER')
    if not wid:
        return
    base = os.environ.get('TEST_DATABASE_URL')
    if not base:
        return
    from urllib.parse import urlsplit, urlunsplit

    parts = urlsplit(base)
    dbname = f"sg_test_{wid}"
    if os.environ.get('_SG_TEST_WORKER_DB') == dbname:
        # Already bootstrapped by another module object of this conftest in
        # this process (see the docstring); its connections are live.
        return
    import psycopg2
    from psycopg2.extensions import quote_ident

    admin_url = urlunsplit((parts.scheme, parts.netloc, '/postgres',
                            parts.query, parts.fragment))
    conn = psycopg2.connect(admin_url, connect_timeout=10)
    conn.autocommit = True  # CREATE/DROP DATABASE cannot run in a transaction
    try:
        cur = conn.cursor()
        cur.execute('SELECT 1 FROM pg_database WHERE datname = %s', (dbname,))
        if cur.fetchone():
            cur.execute('DROP DATABASE ' + quote_ident(dbname, conn))
        cur.execute('CREATE DATABASE ' + quote_ident(dbname, conn))
        cur.close()
    finally:
        conn.close()
    os.environ['TEST_DATABASE_URL'] = urlunsplit(
        (parts.scheme, parts.netloc, '/' + dbname,
         parts.query, parts.fragment))
    os.environ['_SG_TEST_WORKER_DB'] = dbname
    print(f"[conftest] worker {wid} using its own database {dbname}")


_give_this_worker_its_own_database()


# ---------------------------------------------------------------------------
# App fixture
# ---------------------------------------------------------------------------
def _make_app(db_uri):
    return create_app(test_config={
        "TESTING": True,
        "WTF_CSRF_ENABLED": False,
        "SQLALCHEMY_DATABASE_URI": db_uri,
        "SERVER_NAME": "localhost:5001",
        # Exercise the email paths in every test run: the locmem backend
        # stores messages in `mail.outbox` instead of opening an SMTP
        # connection, so OTP/registration/status mails are actually sent
        # (and assertable) in CI rather than erroring on connect or being
        # silently skipped. flask-mailman already defaults to locmem when
        # TESTING=True, but pinning it here makes the contract explicit and
        # independent of the library's default.
        "MAIL_BACKEND": "locmem",
    })


@pytest.fixture
def app():
    test_db_url = os.environ.get('TEST_DATABASE_URL')
    if not test_db_url:
        raise RuntimeError(
            "TEST_DATABASE_URL is not set.\n"
            "Run the suite through the bundled local Postgres harness instead - it\n"
            "boots an embedded pgserver cluster and exports the URL for you, so no\n"
            "Supabase account is needed:\n"
            "    python run_pg_suite.py -q\n"
            "To use your own database, point TEST_DATABASE_URL at any PostgreSQL\n"
            "instance (Supabase pooler URL works too):\n"
            "    export TEST_DATABASE_URL='postgresql://user:pass@host:5432/test_db?sslmode=require'"
        )
    # Postgres mode: schema is drop/recreated per test for isolation. Under
    # pytest-xdist this is safe because each worker owns its own database
    # (see _give_this_worker_its_own_database above); single-process runs
    # (-n 0) keep the caller-provided TEST_DATABASE_URL as-is.
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
