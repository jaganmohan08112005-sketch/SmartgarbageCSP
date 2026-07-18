FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PORT=10000
EXPOSE 10000

CMD ["sh", "-c", "flask db upgrade && python seed_db.py && gunicorn wsgi:app --bind 0.0.0.0:${PORT:-10000} --workers 1"]
