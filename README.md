# SmartGarbage — Smart Waste Management System

A Flask-based digital reporting and monitoring platform for municipal solid waste management, built for compliance with India's Solid Waste Management Rules, 2026.

## 🏷️ Project Overview

**SmartGarbage** is a comprehensive waste management solution serving:
- **Citizens**: Report overflowing bins, declare segregated waste, earn Green Points
- **Sanitation Workers**: Receive optimized routes, track performance, report status
- **Municipal Administration**: Monitor ward health, manage complaints, generate reports

## 🔗 Key Features by User Role

| Role | Core Features |
|------|---------------|
| **Citizen** | GPS-enabled overflow reporting, 4-stream waste declaration, PAYT billing, Green Points rewards, OTP login |
| **Worker** | Route optimization, GPS tracking, performance dashboard, bulk pickup requests |
| **Admin** | Ward analytics, illegal dump monitoring, sensor health checks, worker management |
| **IoT** | Smart bin telemetry, emergency detection (temperature, methane), automated alerts |

## 🏗️ Tech Stack

| Layer | Technology |
|-------|------------|
| **Backend** | Python 3.11, Flask, SQLAlchemy, Flask-Migrate |
| **Frontend** | Bootstrap 5, Leaflet.js, Chart.js |
| **Database** | SQLite (dev), PostgreSQL (production) |
| **Deployment** | Docker, Render.com |
| **Messaging** | Twilio WhatsApp, Telegram Bot API |

## 🚀 Quick Start (Local Development)

```bash
# Clone and enter directory
git clone https://github.com/jaganmohan08112005-sketch/SmartgarbageCSP.git
cd SmartGarbage

# Create virtual environment
python -m venv venv
.\venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Initialize database
python manage.py db init
python manage.py db migrate
python manage.py db upgrade

# Run development server
python run.py
```

**Default Demo Accounts** (CHANGE THESE IN PRODUCTION):
- Admin: `admin` / `admin123` (requires MFA)
- Worker: `worker` / `worker123` (requires MFA)  
- Citizen: `user` / `user123` (direct entry)

## 📋 Compliance with SWM Rules, 2026

| Rule Requirement | App Implementation |
|------------------|-------------------|
| 4-way segregation | `WasteDeclaration` model with wet/dry/sanitary/hazardous fields |
| Bulk Waste Generators | `BWGDeclaration` with PAYT invoicing |
| Digital reporting | Web + WhatsApp + Telegram reporting channels |
| Sensor monitoring | IoT integration with emergency detection |
| Segregation penalties | PAYT invoicing with compliance scoring |

## 🗺️ System Architecture

```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│   Citizen   │────│   Flask     │────│   Admin     │
│   Portal    │    │   Backend   │    │   Console   │
└─────────────┘    └─────────────┘    └─────────────┘
                         │
        ┌────────────────┼────────────────┐
        │                │                │
┌───────▼──────┐  ┌──────▼──────┐  ┌──────▼──────┐
│  WhatsApp    │  │   Telegram  │  │     IoT     │
│   Bot API    │  │   Bot API   │  │   Sensors   │
└──────────────┘  └─────────────┘  └─────────────┘
```

## ⚙️ Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `SECRET_KEY` | Yes | Flask session secret (auto-generated if missing) |
| `DATABASE_URL` | No | Database connection URL (default: SQLite) |
| `FLASK_ENV` | No | Set to `production` for production mode |
| `REDIS_URL` | No | Redis for shared rate limits + KPI cache (needed when running >1 worker) |
| `SUPABASE_URL` / `SUPABASE_SERVICE_ROLE_KEY` | No | Supabase Storage for photos (recommended in production) |
| `TWILIO_ACCOUNT_SID` / `TWILIO_AUTH_TOKEN` / `TWILIO_FROM_NUMBER` | No | SMS delivery for OTP + complaint status alerts |
| `TWILIO_WHATSAPP_NUMBER` | No | WhatsApp delivery (e.g. `whatsapp:+14155238886`) |
| `MAIL_SERVER` / `MAIL_USERNAME` / `MAIL_PASSWORD` | No | SMTP email fallback (OTP, status alerts, password reset) |
| `RAZORPAY_KEY_ID` / `RAZORPAY_KEY_SECRET` | No | Server-side PAYT order creation + Checkout (falls back to UPI deep-link when unset) |
| `RAZORPAY_WEBHOOK_SECRET` | No | Verifies `/webhook/razorpay` capture signatures (HMAC-SHA256, like Twilio) |

## 📦 Deployment

Deployed via Docker on Fly.io (recommended) or Render.com:
- `fly.toml` / `render.yaml` deploy configs
- Auto-deploy from GitHub main branch (CI runs pytest + flake8)
- Supabase PostgreSQL + Storage (see `DEPLOY.md`)

## 🧪 Testing

```bash
# Install test tooling (first time only)
pip install -r requirements-dev.txt

# Run tests — parallel (pytest-xdist) with a 180s per-test timeout so a
# genuinely hung test fails with a traceback instead of stalling the run
pytest tests/ -v

# Sequential run (required for the shared-DB Postgres parity job)
pytest tests/ -n 0

# Run with coverage
pytest tests/ --cov=app --cov-report=html
```

## 🤝 Contributing

1. Fork repository
2. Create feature branch
3. Implement changes
4. Add tests for new functionality
5. Submit pull request

## 📄 License

MIT License — see LICENSE file for details.