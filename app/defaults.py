"""Built-in demo accounts.

These three accounts are provisioned automatically on every app start so the
portal can always be signed into without registering first. Username and
password are identical for each one.
"""
from werkzeug.security import generate_password_hash

DEFAULT_ACCOUNTS = [
    {"username": "24331A4441ADMIN", "role": "admin", "phone": "+919876500011"},
    {"username": "24331A4441CITIZEN", "role": "citizen", "phone": "+919876500012"},
    {"username": "24331A4441WORKER", "role": "worker", "phone": "+919876500013"},
]

DEFAULT_WORKER_VEHICLE = "CV-06"


def ensure_default_accounts(app):
    """Create (or repair) the built-in accounts. Safe to call repeatedly."""
    from . import db
    from .models import User, WorkerProfile

    with app.app_context():
        try:
            for spec in DEFAULT_ACCOUNTS:
                user = User.query.filter_by(username=spec["username"]).first()
                if user is None:
                    user = User(username=spec["username"], role=spec["role"], phone=spec["phone"])
                    db.session.add(user)
                # Password always matches the username, and admins stay approved,
                # so these accounts never get locked out of the portal.
                user.password_hash = generate_password_hash(spec["username"])
                user.role = spec["role"]
                user.is_approved = True
                if spec["role"] == "admin":
                    user.is_superadmin = True
            db.session.commit()

            worker = User.query.filter_by(username="24331A4441WORKER").first()
            if worker and not WorkerProfile.query.filter_by(user_id=worker.id).first():
                db.session.add(WorkerProfile(user_id=worker.id, vehicle_id=DEFAULT_WORKER_VEHICLE,
                                             latitude=18.0675, longitude=83.4094,
                                             status="Active", performance_rating=4.5))
                db.session.commit()
        except Exception as e:
            # The schema may not exist yet (fresh clone before `flask db upgrade`).
            db.session.rollback()
            app.logger.warning("Skipped default account provisioning: %s", e)
