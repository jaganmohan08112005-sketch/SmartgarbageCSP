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

## 📦 Deployment

Deployed on Render.com using:
- Dockerfile for containerization
- Auto-deploy from GitHub main branch
- PostgreSQL database

## 🧪 Testing

```bash
# Run tests
pytest tests/ -v

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