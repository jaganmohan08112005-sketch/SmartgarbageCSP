from app import create_app, socketio

app = create_app()

# Render's native-Python runtime (this is how the live service actually runs:
# it ignores the Dockerfile and starts `gunicorn app:app`) never executes the
# Dockerfile's `flask db upgrade` step, so apply pending migrations at boot.
# Idempotent: a no-op whenever the schema is already at head (e.g. on the
# Docker path, where `flask db upgrade` runs before gunicorn starts).
with app.app_context():
    from flask_migrate import upgrade
    upgrade()
