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
CMD ["sh", "-c", "flask db upgrade && if [ \"$SEED_DEMO\" = \"true\" ]; then python seed_db.py; fi && gunicorn wsgi:app --bind 0.0.0.0:${PORT:-10000} --worker-class eventlet -w 1 --timeout 120 --keep-alive 5"]
