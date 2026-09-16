"""Persistent local preview server: bundled Postgres + seeded roles.

Runs the real app (CSRF enabled, TESTING=False) on 127.0.0.1:5001 so the
preview tab can exercise every role: citizen / worker / admin / anonymous.

Local loopback requests get the dev OTP flashed on screen (see
_is_local_request), so admin MFA login is walkthrough-able in the preview.
"""
import os
import sys
import time
import tempfile
import threading

# Must run before ANY other import: the app's blocking I/O (psycopg2, SSE
# streams, requests) must become gevent-cooperative, otherwise the admin
# dashboard's SocketIO/SSE connections freeze the gevent hub and the whole
# server stops answering (observed live on the /admin page).
from gevent import monkey
monkey.patch_all()

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pgserver

PGDATA = os.path.join(tempfile.gettempdir(), 'sg_pgdata_preview')
os.makedirs(PGDATA, exist_ok=True)
db_server = pgserver.get_server(pgdata=PGDATA)
db_server.ensure_postgres_running()
os.environ['TEST_DATABASE_URL'] = db_server.get_uri()
os.environ.setdefault('DATABASE_URL', db_server.get_uri())  # satisfy eager checks
print(f"[preview] PostgreSQL up at {db_server.get_uri()}", flush=True)

from werkzeug.security import generate_password_hash
from app import db, create_app, socketio
from app.models import User, WorkerProfile

app = create_app(test_config={
    "TESTING": False,
    "WTF_CSRF_ENABLED": True,       # exercise the real CSRF path
    "SQLALCHEMY_DATABASE_URI": db_server.get_uri(),
    "MAIL_BACKEND": "locmem",       # no SMTP locally; outbox captures mail
})


def _seed():
    with app.app_context():
        db.create_all()
        if User.query.filter_by(username="qa_citizen").first():
            print("[preview] already seeded", flush=True)
            return
        citizen = User(username="qa_citizen", email="citizen@example.com",
                       password_hash=generate_password_hash("testpass123"),
                       role="citizen", phone="+919876543210",
                       is_approved=True, email_verified=True, green_points=120)
        admin = User(username="qa_admin", email="admin@example.com",
                     password_hash=generate_password_hash("testpass123"),
                     role="admin", phone="+919876543211",
                     is_approved=True, is_superadmin=True)
        worker = User(username="qa_worker", email="worker@example.com",
                      password_hash=generate_password_hash("testpass123"),
                      role="worker", phone="+919876543212",
                      is_approved=True)
        db.session.add_all([citizen, admin, worker])
        db.session.commit()
        db.session.add(WorkerProfile(user_id=worker.id, vehicle_id="CV-01",
                                     status="Active", performance_rating=5.0,
                                     is_informal_picker=False))
        db.session.commit()
        print("[preview] seeded qa_citizen / qa_worker / qa_admin (testpass123)", flush=True)


def _serve():
    socketio.run(app, host="127.0.0.1", port=5001, debug=False, allow_unsafe_werkzeug=True)


if __name__ == "__main__":
    _seed()
    threading.Thread(target=_serve, daemon=True).start()
    print("[preview] serving http://127.0.0.1:5001", flush=True)
    while True:
        time.sleep(60)
