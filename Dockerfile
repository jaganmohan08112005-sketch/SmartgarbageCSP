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
# a queue.
#
# Worker scaling: eventlet + Redis message queue supports MULTIPLE gunicorn
# workers sharing socket.io state. `-w 2` lets HTTP and WebSocket traffic
# contend across two processes instead of stalling a single eventlet loop.
# When REDIS_URL is unset (SQLite dev), fall back to a single worker — the
# in-memory rate-limiter and socket.io room state would otherwise silently
# multiply/desync across processes.
CMD ["sh", "-c", "flask db upgrade && if [ \"$SEED_DEMO\" = \"true\" ]; then python seed_db.py; fi && (python worker.py &) && if [ -n \"$REDIS_URL\" ]; then exec gunicorn wsgi:app --bind 0.0.0.0:${PORT:-10000} --worker-class eventlet -w ${GUNICORN_WORKERS:-2} --timeout 120 --keep-alive 5; else exec gunicorn wsgi:app --bind 0.0.0.0:${PORT:-10000} --worker-class eventlet -w 1 --timeout 120 --keep-alive 5; fi"]