FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PORT=10000
EXPOSE 10000

# Demo data (with publicly-known demo accounts) is ONLY seeded when SEED_DEMO=true.
# Production deployments must set SEED_DEMO=false (or omit it) and create real
# accounts via registration + admin approval.
#
# The RQ background worker (SMS/WhatsApp sends, webhook dispatch, export
# generation, PAYT dunning) is started alongside gunicorn. worker.py exits
# immediately when REDIS_URL is unset, so the same image works with or without
# a queue. RQ_IN_PROCESS_WORKER=false stops wsgi.py's fallback in-process
# worker thread (the dedicated `python worker.py` here is the real worker).
#
# Worker scaling: gevent + Redis message queue supports MULTIPLE gunicorn
# workers sharing socket.io state. `-w 2` lets HTTP and WebSocket traffic
# contend across two processes instead of stalling a single gevent loop.
# When REDIS_URL is unset, fall back to a single worker — the
# in-memory rate-limiter and socket.io room state would otherwise silently
# multiply/desync across processes.
#
# RENDER_WORKER=true: run as a dedicated queue worker (render.yaml's
# `smartgarbage-worker` service) instead of serving HTTP.
# RQ_IN_PROCESS_WORKER=false is exported FIRST (before `flask db upgrade`):
# with FLASK_APP unset the flask CLI auto-discovers wsgi.py, and importing
# wsgi.py with REDIS_URL set would start the in-process worker thread while
# migrations are still running.
CMD ["sh", "-c", "export RQ_IN_PROCESS_WORKER=false && flask db upgrade && if [ \"$RENDER_WORKER\" = \"true\" ]; then exec python worker.py; fi && if [ \"$SEED_DEMO\" = \"true\" ]; then python seed_db.py; fi && (python worker.py &) && if [ -n \"$REDIS_URL\" ]; then exec gunicorn wsgi:app --bind 0.0.0.0:${PORT:-10000} --worker-class gevent -w ${GUNICORN_WORKERS:-2} --timeout 120 --keep-alive 5; else exec gunicorn wsgi:app --bind 0.0.0.0:${PORT:-10000} --worker-class gevent -w 1 --timeout 120 --keep-alive 5; fi"]