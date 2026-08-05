"""Seed demo smart bins + fleet workers for local development.

Populates the SQLite/dev DB with:
  - Smart bins spread across the 5 wards, including some at Critical level
    (>=80% fill, plus one with high temperature/methane for the simulator),
    some Warning, some with sensor faults, and some with solar pre-compaction
    enabled so every admin map feature has data to show.
  - Active fleet worker profiles (CV-01..CV-05) positioned inside their
    assigned sector polygons, plus one intentionally out-of-bounds truck to
    demo geo-fence violation flagging.

Safe to re-run: existing hardware_ids / vehicle_ids are skipped. NEVER runs on
a deployed platform (guarded by the same RENDER/FLY_APP_NAME check used by
the app itself).
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _is_deployed():
    return bool(os.environ.get('RENDER') or os.environ.get('FLY_APP_NAME'))


def main():
    if _is_deployed():
        print("Refusing to seed demo data on a deployed platform.")
        return

    from app import create_app, db
    from app.models import SmartBin, User, WorkerProfile
    from werkzeug.security import generate_password_hash

    app = create_app()
    with app.app_context():
        # ── Wards and their centers (mirrors routes.py WARD_COORDINATES) ──
        wards = {
            "Ward 1 - MVGR College Area":       (18.0552, 83.4051),
            "Ward 2 - Chintalavalasa Junction": (18.0675, 83.4094),
            "Ward 3 - RTC Colony":              (18.0702, 83.4153),
            "Ward 4 - Ramalayam Street":        (18.0650, 83.4005),
            "Ward 5 - Sai Nagar":               (18.0751, 83.4201),
        }

        # ── Smart bins (8 per ward, staggered fill levels) ──
        bins_created = 0
        for ward, (lat, lon) in wards.items():
            for i in range(1, 9):
                hw = f"BIN-{list(wards.keys()).index(ward) + 1}{i:02d}"
                if SmartBin.query.filter_by(hardware_id=hw).first():
                    continue
                # Stagger levels: 2 safe, 3 warning, 2 critical, 1 pending-clearance
                if i in (1, 2):
                    level, status = 15 + (i * 8), "Safe"
                elif i in (3, 4, 5):
                    level, status = 55 + (i * 4), "Warning"
                elif i in (6, 7):
                    level, status = 82 + (i * 3), "Critical"
                else:
                    level, status = 95, "Pending Clearance"
                sb = SmartBin(
                    hardware_id=hw,
                    latitude=round(lat + (i - 4.5) * 0.0009, 6),
                    longitude=round(lon + (i % 3 - 1) * 0.0011, 6),
                    level=level,
                    battery_level=max(30, 100 - i * 6),
                    temperature=round(26 + (level * 0.25), 1),
                    methane=round(40 + (level * 2.2), 1),
                    status=status,
                    ward=ward,
                    precompaction_enabled=(i % 3 == 0),
                    # Flag the very first (safe, low-level) bin per ward as a
                    # stale sensor so the Sensor Faults KPI is non-zero.
                    sensor_fault=(i == 1),
                )
                db.session.add(sb)
                bins_created += 1

        # One dramatic emergency bin for the "Simulate Anomaly" button.
        # NOTE: id kept distinct from the generated BIN-3xx scheme above
        # (ward 3 would otherwise produce a colliding "BIN-302").
        if not SmartBin.query.filter_by(hardware_id="BIN-EMG-302").first():
            db.session.add(SmartBin(
                hardware_id="BIN-EMG-302",
                latitude=18.0565, longitude=83.4040,
                level=90, battery_level=64,
                temperature=72.1, methane=850.0,
                status="Critical",
                ward="Ward 1 - MVGR College Area",
                precompaction_enabled=False,
            ))
            bins_created += 1

        # ── Fleet workers (one per sector) ──
        # Sector centers pulled from routes.py SECTOR_POLYGONS bounding boxes.
        sectors = {
            "CV-01": (18.0560, 83.4050),
            "CV-02": (18.0680, 83.4090),
            "CV-03": (18.0710, 83.4155),
            "CV-04": (18.0650, 83.4000),
            "CV-05": (18.0755, 83.4200),
        }
        workers_created = 0
        for vid, (lat, lon) in sectors.items():
            uname = f"driver_{vid.lower()}"
            user = User.query.filter_by(username=uname).first()
            if not user:
                user = User(
                    username=uname,
                    password_hash=generate_password_hash("24331A4441WORKER"),
                    role="worker",
                    phone=f"+9198765{30000 + int(vid[3:]):05d}",
                    is_approved=True,
                )
                db.session.add(user)
                db.session.flush()
            if WorkerProfile.query.filter_by(vehicle_id=vid).first():
                continue
            db.session.add(WorkerProfile(
                user_id=user.id,
                vehicle_id=vid,
                latitude=lat,
                longitude=lon,
                status="Active",
                performance_rating=round(4.5 + (int(vid[3:]) % 3) * 0.25, 2),
                ppe_compliance=True,
                training_completed=True,
                insurance_enrolled=True,
                # CV-05 starts outside its box to demo geofence violation flagging
                geofence_violation=(vid == "CV-05"),
            ))
            workers_created += 1

        db.session.commit()
        total_bins = SmartBin.query.count()
        total_workers = WorkerProfile.query.count()
        print(f"Done. Bins added: {bins_created} (total {total_bins}), "
              f"workers added: {workers_created} (total {total_workers}).")


if __name__ == "__main__":
    main()
