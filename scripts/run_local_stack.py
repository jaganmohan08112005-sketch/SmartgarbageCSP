#!/usr/bin/env python3
"""Local full stack for recording the demo video.

All work happens in-process so that the pgserver postgres.exe stays alive
(Windows Defender kills it the moment the parent process that started it exits
or spawns a subprocess that outlives the pg_ctl invocation).

Flow: pgserver boot → schema via db.create_all() [skips Alembic entirely for
      local dev] → seed demo data → Flask on 127.0.0.1:5057
"""
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
os.chdir(ROOT)
sys.path.insert(0, ROOT)

# ── 1. Boot pgserver (persistent PGDATA — survives restarts with cached port)
PGDATA = os.path.join(tempfile.gettempdir(), "sg_pgdata_v3")
os.makedirs(PGDATA, exist_ok=True)

import pgserver  # noqa: E402

# pgserver hardcodes a 10s pg_ctl timeout; Windows Defender can cause the
# freshly-spawned postgres.exe to exceed it. Widen + retry.
import subprocess as _sp  # noqa: E402
_orig_run = _sp.run
def _patched_run(*a, **kw):
    if kw.get('timeout') == 10:
        kw['timeout'] = 120
    return _orig_run(*a, **kw)
_sp.run = _patched_run

pg = None
for attempt in (1, 2, 3):
    try:
        pg = pgserver.get_server(pgdata=PGDATA)
        pg.ensure_postgres_running()
        print(f"[stack] pgserver running on attempt {attempt}")
        break
    except Exception as exc:
        print(f"[stack] pgserver attempt {attempt} failed: {exc}")
        import shutil
        shutil.rmtree(PGDATA, ignore_errors=True)
        os.makedirs(PGDATA, exist_ok=True)
        if attempt == 3:
            raise

DB_URL = pg.get_uri()
os.environ["DATABASE_URL"] = DB_URL
os.environ["SENTRY_DSN"] = ""
print(f"[stack] Postgres: {DB_URL}")

# ── 2. Verify connectivity with a raw psycopg2 ping before going further
import time  # noqa: E402
import psycopg2  # noqa: E402
for ping_attempt in range(20):
    try:
        conn = psycopg2.connect(DB_URL, connect_timeout=5)
        conn.close()
        print("[stack] DB ping OK")
        break
    except psycopg2.OperationalError as e:
        print(f"[stack] DB ping attempt {ping_attempt + 1}/20 failed: {e}")
        time.sleep(2)
else:
    raise RuntimeError("Could not connect to pgserver after 40 seconds")

# ── 3. Create schema + run migrations in-process (single process = pgserver lives)
print("[stack] creating app and running migrations in-process...")
from app import create_app, db, socketio, limiter  # noqa: E402
from flask_migrate import upgrade as _alembic_upgrade  # noqa: E402

app = create_app()
with app.app_context():
    _alembic_upgrade()
    print("[stack] migrations done.")

    # ── 4. Seed demo data in-process
    print("[stack] seeding demo data...")
    from werkzeug.security import generate_password_hash  # noqa: E402
    from app.models import User, WorkerProfile, SmartBin  # noqa: E402

    # --- seed users (idempotent) ---
    def _get_or_create_user(username, role, phone, green_points=0,
                             is_superadmin=False, email=None):
        u = User.query.filter_by(username=username).first()
        if not u:
            u = User(
                username=username,
                password_hash=generate_password_hash(username),
                role=role, phone=phone, is_approved=True,
                green_points=green_points,
                is_superadmin=is_superadmin,
                email=email,
            )
            db.session.add(u)
            db.session.flush()
            print(f"  created user {username}")
        return u

    admin_user = _get_or_create_user(
        "24331A4441ADMIN", "admin", "+919876543210",
        is_superadmin=True, email="jaganmohan08112005@gmail.com")
    citizen_user = _get_or_create_user(
        "24331A4441CITIZEN", "citizen", "+919876543211", green_points=120)
    worker_user = _get_or_create_user(
        "24331A4441WORKER", "worker", "+919876543212",
        # uq_user_email forbids sharing the admin's address (migration
        # l1m2n3o4p5q6) — worker gets Rama's email, mirroring seed_db.py.
        email="rama18072005@gmail.com")
    db.session.commit()

    # --- worker profile for CV-01 ---
    if not WorkerProfile.query.filter_by(vehicle_id="CV-01").first():
        db.session.add(WorkerProfile(
            user_id=worker_user.id, vehicle_id="CV-01",
            latitude=18.0675, longitude=83.4094,
            status="Active", performance_rating=4.9,
            ppe_compliance=True, training_completed=True,
            insurance_enrolled=True,
        ))
        db.session.commit()
        print("  created CV-01 worker profile")

    # --- smart bins across 5 wards ---
    wards = {
        "Ward 1 - MVGR College Area":       (18.0552, 83.4051),
        "Ward 2 - Chintalavalasa Junction": (18.0675, 83.4094),
        "Ward 3 - RTC Colony":              (18.0702, 83.4153),
        "Ward 4 - Ramalayam Street":        (18.0650, 83.4005),
        "Ward 5 - Sai Nagar":              (18.0751, 83.4201),
    }
    bins_added = 0
    for w_idx, (ward, (lat, lon)) in enumerate(wards.items(), 1):
        for i in range(1, 9):
            hw = f"BIN-{w_idx}{i:02d}"
            if SmartBin.query.filter_by(hardware_id=hw).first():
                continue
            if i in (1, 2):
                level, status = 15 + i * 8, "Safe"
            elif i in (3, 4, 5):
                level, status = 55 + i * 4, "Warning"
            elif i in (6, 7):
                level, status = 82 + i * 3, "Critical"
            else:
                level, status = 95, "Pending Clearance"
            db.session.add(SmartBin(
                hardware_id=hw,
                latitude=round(lat + (i - 4.5) * 0.0009, 6),
                longitude=round(lon + (i % 3 - 1) * 0.0011, 6),
                level=level, status=status, ward=ward,
                battery_level=max(30, 100 - i * 6),
                temperature=round(26 + level * 0.25, 1),
                methane=round(40 + level * 2.2, 1),
                precompaction_enabled=(i % 3 == 0),
                sensor_fault=(i == 1),
            ))
            bins_added += 1
    if bins_added:
        db.session.commit()
        print(f"  created {bins_added} bins")

    # BIN-101 and BIN-302 featured in the demo script
    for hw, level, temp, methane, ward in [
        ("BIN-101", 88, 46.0, 236.5, "Ward 1 - MVGR College Area"),
        ("BIN-302", 90, 72.1, 850.0, "Ward 3 - RTC Colony"),
    ]:
        if not SmartBin.query.filter_by(hardware_id=hw).first():
            db.session.add(SmartBin(
                hardware_id=hw, ward=ward,
                latitude=18.0552, longitude=83.4051,
                level=level, status="Critical",
                battery_level=64, temperature=temp, methane=methane,
                precompaction_enabled=False,
            ))
    db.session.commit()
    print("[stack] seeding done.")

# ── 5. Serve Flask on 127.0.0.1:5057 (rate limiting off for the recorder)
app.config["RATELIMIT_ENABLED"] = False
try:
    limiter.enabled = False
except Exception:
    pass

print("[stack] starting Flask dev server on http://127.0.0.1:5057 ...")
print("[stack] demo credentials: 24331A4441ADMIN / 24331A4441CITIZEN / 24331A4441WORKER (password=username)")
print("[stack] OTP is shown on screen at login for dev mode.")
socketio.run(app, host="127.0.0.1", port=5057, debug=False, log_output=True,
             allow_unsafe_werkzeug=True)
