import os
import threading

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

# In-process RQ worker for Render's native-Python runtime.
#
# The live Render service ignores the Dockerfile, so the Dockerfile's
# `(python worker.py &)` line never runs and — without a separate worker
# service — background jobs (SMS/WhatsApp, webhook dispatch, exports, PAYT
# dunning, retention/sweeps) would silently never execute in production.
# When REDIS_URL is set we therefore run the RQ worker in a daemon thread
# inside the web process (jobs share the same queue; RQ supports multiple
# workers draining one queue). The Docker path spawns a real worker process
# itself and sets RQ_IN_PROCESS_WORKER=false to avoid double execution.
if (os.environ.get('REDIS_URL')
        and os.environ.get('RQ_IN_PROCESS_WORKER', 'true').lower()
        not in ('0', 'false', 'no')):

    def _run_in_process_worker():
        try:
            from redis import Redis
            from rq import Worker, Queue, Connection
            conn = Redis.from_url(os.environ['REDIS_URL'])
            with Connection(conn):
                Worker([Queue('smartgarbage')]).work()
        except Exception as e:  # defensive: a worker failure must not crash boot
            app.logger.error('in_process_worker_failed', exc_info=e)

    threading.Thread(target=_run_in_process_worker,
                     name='rq-in-process', daemon=True).start()
    app.logger.info('in_process_worker_started')
