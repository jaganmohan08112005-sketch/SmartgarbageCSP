# Render native-Python runtime (ignores the Dockerfile): run both the web
# process and the RQ worker from one service. gevent yields on SSE/SocketIO
# I/O so streams don't pin a sync worker; -w 1 keeps the in-memory rate-limiter
# (and socket room state, when REDIS_URL is unset) consistent in one process.
web: gunicorn wsgi:app --bind 0.0.0.0:$PORT -w 1 --worker-class gevent --timeout 120 --keep-alive 5
worker: python worker.py
