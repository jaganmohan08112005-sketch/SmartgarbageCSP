# 🗑️ SmartGarbage Chintalavalasa

**Open-source digital waste management portal for Indian municipalities**

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Flask](https://img.shields.io/badge/Flask-3.x-orange.svg)](https://flask.palletsprojects.com/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15+-336791.svg)](https://www.postgresql.org/)
[![Docker](https://img.shields.io/badge/Docker-Ready-2496ED.svg)](https://www.docker.com/)
[![WCAG 2.1 AA](https://img.shields.io/badge/WCAG-2.1%20AA-brightgreen.svg)](https://www.w3.org/WAI/WCAG21/quickref/)
[![PRs Welcome](https://img.shields.io/badge/PRs-Welcome-brightgreen.svg)](CONTRIBUTING.md)

---

## 📋 Table of Contents

- [Overview](#overview)
- [Features](#features)
- [Tech Stack](#tech-stack)
- [Quick Start](#quick-start)
- [Deployment](#deployment)
- [Environment Variables](#environment-variables)
- [API Reference](#api-reference)
- [Testing](#testing)
- [Contributing](#contributing)
- [License](#license)
- [Acknowledgements](#acknowledgements)

---

## Overview

SmartGarbage is a comprehensive waste management platform built for compliance with India's [Solid Waste Management Rules, 2026](https://moef.gov.in/). It provides citizens, sanitation workers, and municipal administrators with digital tools for waste collection scheduling, complaint reporting, transparency dashboards, and civic incentive programmes.

### Who Is This For?

| User | What They Can Do |
|------|------------------|
| **Municipalities** | Deploy a complete waste management portal for your city/panchayat |
| **Developers** | Contribute to an open-source civic tech project |
| **Researchers** | Study digital governance and waste management systems |
| **Citizens** | Access waste services through a user-friendly portal |

### Key Highlights

- ✅ **Compliant** with Solid Waste Management Rules, 2026
- ✅ **Accessible** — WCAG 2.1 Level AA, bilingual (English + Telugu)
- ✅ **PWA** — works offline, installable on mobile devices
- ✅ **Open Data** — public JSON API for transparency
- ✅ **AI-Ready** — optimised for AI search engines (GEO)

---

## Features

### Citizen Features

| Feature | Description |
|---------|-------------|
| **Collection Schedules** | View ward-specific pickup timetables updated daily |
| **Missed Pickup Reporting** | File complaints with GPS + photo evidence |
| **Ward Transparency** | Live dashboards for bin fill levels, segregation rates |
| **Green Points** | Earn rewards for consistent waste segregation |
| **PAYT Billing** | Weight-based waste disposal billing with online payment |
| **Bilingual Interface** | English and Telugu language support |

### Worker Features

| Feature | Description |
|---------|-------------|
| **Route Optimisation** | ML-powered pickup route suggestions |
| **GPS Tracking** | Real-time location tracking during collection |
| **Performance Dashboard** | Track pickups, ratings, and efficiency metrics |
| **Bulk Pickup Requests** | Handle multiple pickup requests efficiently |

### Admin Features

| Feature | Description |
|---------|-------------|
| **Ward Analytics** | Monitor complaint volumes, resolution rates, segregation |
| **Worker Management** | Assign, track, and evaluate sanitation workers |
| **Illegal Dump Monitoring** | Track and respond to illegal dumping reports |
| **IoT Dashboard** | Monitor smart bin sensors (temperature, methane, fill level) |
| **MFA Security** | Multi-factor authentication for privileged accounts |
| **Audit Trail** | Complete activity logging for accountability |

### Technical Features

| Feature | Description |
|---------|-------------|
| **Service Worker** | 3-tier caching for instant repeat visits |
| **Dark Mode** | User-selectable theme with system preference detection |
| **Font Scaling** | Adjustable text size (A- A A+) for accessibility |
| **High Contrast** | Enhanced visibility mode for low-vision users |
| **Search Autocomplete** | Fuzzy search with keyboard navigation |
| **Mega Menu** | WCAG AA compliant desktop navigation |
| **Breadcrumb Navigation** | On every inner page with JSON-LD schema |
| **RSS Feed** | Notice syndication for news readers |
| **Open Data API** | Public JSON endpoint for transparency data |

---

## Tech Stack

| Layer | Technology | Purpose |
|-------|------------|---------|
| **Backend** | Python 3.11+, Flask | Web framework, API, business logic |
| **Database** | PostgreSQL (Supabase) | Data storage, connection pooling |
| **ORM** | SQLAlchemy + Flask-Migrate | Database models, migrations |
| **Frontend** | Bootstrap 5, Jinja2 | Responsive UI, server-side rendering |
| **Maps** | Leaflet.js | Interactive ward maps |
| **Charts** | Chart.js | Analytics visualisations |
| **ML** | scikit-learn | Missed collection prediction |
| **Cache** | Redis | Rate limiting, background jobs |
| **Queue** | RQ (Redis Queue) | Background job processing |
| **Auth** | Flask-Login, Flask-WTF | Authentication, CSRF protection |
| **SMS/WhatsApp** | Twilio | OTP delivery, status alerts |
| **Storage** | Supabase Storage | Photo uploads |
| **Monitoring** | Sentry | Error tracking |
| **Deployment** | Docker, Render/Fly.io | Containerised deployment |

---

## Quick Start

### Prerequisites

- Python 3.11+
- PostgreSQL (or Supabase account)
- Git

### 1. Clone the Repository

```bash
git clone https://github.com/jaganmohan08112005-sketch/SmartGarbage.git
cd SmartGarbage
```

### 2. Set Up Virtual Environment

```bash
# Linux/macOS
python -m venv venv
source venv/bin/activate

# Windows
python -m venv venv
venv\Scripts\activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure Environment

```bash
cp .env.example .env
# Edit .env with your database URL and secret key
```

At minimum, set:

```bash
DATABASE_URL=postgresql://user:pass@localhost:5432/smartgarbage
SECRET_KEY=your-random-secret-key-here
```

### 5. Initialize Database

```bash
flask db upgrade
```

### 6. Seed Demo Data (Optional)

```bash
SEED_DEMO=true python seed_db.py
```

Demo accounts:

| Role | Username | Password |
|------|----------|----------|
| Admin | `admin` | `admin123` |
| Worker | `worker` | `worker123` |
| Citizen | `user` | `user123` |

### 7. Run Development Server

```bash
python run.py
```

Visit [http://localhost:5000](http://localhost:5000)

---

## Deployment

### Docker (Recommended)

```bash
# Build image
docker build -t smartgarbage .

# Run container
docker run -p 10000:10000 \
  -e DATABASE_URL="postgresql://..." \
  -e SECRET_KEY="your-secret" \
  smartgarbage
```

### Render.com

1. Connect your GitHub repository
2. Render auto-detects `render.yaml`
3. Set environment variables in dashboard
4. Deploy

### Fly.io

```bash
fly auth login
fly launch --no-deploy
fly secrets set DATABASE_URL="postgresql://..." SECRET_KEY="..."
fly deploy
```

### Environment-Specific Notes

| Platform | Notes |
|----------|-------|
| **Render** | Free tier has cold starts (~1-2s). Use Cloudflare CDN for instant repeat visits. |
| **Fly.io** | Recommended for production. Supports multiple regions. |
| **Railway** | Alternative PaaS. Good for hobby projects. |

See [DEPLOY.md](DEPLOY.md) for detailed deployment instructions.

---

## Environment Variables

### Required

| Variable | Description |
|----------|-------------|
| `DATABASE_URL` | PostgreSQL connection string |
| `SECRET_KEY` | Flask session secret (generate with `openssl rand -hex 32`) |

### Optional

| Variable | Description |
|----------|-------------|
| `FLASK_ENV` | Set to `production` for production mode |
| `REDIS_URL` | Redis URL for rate limiting + background jobs |
| `SUPABASE_URL` | Supabase project URL for photo storage |
| `SUPABASE_SERVICE_ROLE_KEY` | Supabase service role key |
| `TWILIO_ACCOUNT_SID` | Twilio account SID for SMS/WhatsApp |
| `TWILIO_AUTH_TOKEN` | Twilio auth token |
| `TWILIO_FROM_NUMBER` | Twilio phone number |
| `TWILIO_WHATSAPP_NUMBER` | Twilio WhatsApp number |
| `MAIL_SERVER` | SMTP server for email fallback |
| `MAIL_USERNAME` | SMTP username |
| `MAIL_PASSWORD` | SMTP password |
| `RAZORPAY_KEY_ID` | Razorpay key for PAYT billing |
| `RAZORPAY_KEY_SECRET` | Razorpay secret |
| `RAZORPAY_WEBHOOK_SECRET` | Razorpay webhook secret |
| `SENTRY_DSN` | Sentry error tracking DSN |
| `ANALYTICS_ID` | Google Analytics measurement ID |
| `SEED_DEMO` | Set to `true` to seed demo data (dev only!) |

---

## API Reference

### Public Endpoints

| Method | Route | Description |
|--------|-------|-------------|
| `GET` | `/` | Homepage |
| `GET` | `/schedule` | Ward collection schedules |
| `GET` | `/transparency` | Ward transparency dashboards |
| `GET` | `/about` | About the portal |
| `GET` | `/contact` | Contact form |
| `GET` | `/faq` | Frequently asked questions |
| `GET` | `/search?q=` | Search results |
| `GET` | `/robots.txt` | Robots file |
| `GET` | `/sitemap.xml` | XML sitemap |
| `GET` | `/feed.xml` | RSS feed |

### Citizen Endpoints (Login Required)

| Method | Route | Description |
|--------|-------|-------------|
| `GET` | `/dashboard` | Citizen dashboard |
| `POST` | `/report` | Submit complaint |
| `POST` | `/dashboard/declare-waste` | Declare waste segregation |
| `GET` | `/api/payt-invoice` | Get PAYT invoices |

### Admin Endpoints (Admin Role Required)

| Method | Route | Description |
|--------|-------|-------------|
| `GET` | `/admin` | Admin console |
| `GET` | `/admin/audit` | Audit trail |
| `POST` | `/admin/firmware/upload` | Upload IoT firmware |
| `GET` | `/api/route-optimize` | Optimise collection routes |

### Open Data API

```bash
# Get transparency data (no auth required)
curl https://your-domain.com/api/v1/open-data

# Response includes:
# - Ward-wise complaint statistics
# - Segregation rates
# - Collection coverage
# - Resolution times
```

---

## Testing

### Run Tests

```bash
# Install test dependencies
pip install -r requirements-dev.txt

# Run all tests (parallel)
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=app --cov-report=html

# Run specific test file
pytest tests/test_auth.py -v
```

### Test Structure

```
tests/
├── conftest.py              # Shared fixtures
├── test_auth.py             # Authentication tests
├── test_features.py         # Feature tests
├── test_walkthrough.py      # End-to-end walkthrough
└── qa/                      # Browser E2E tests (Playwright)
```

### CI/CD

GitHub Actions runs on every push/PR:

- ✅ Pytest (parallel)
- ✅ Flake8 linting
- ✅ App import check
- ✅ Deployment to staging (on `staging` branch)

---

## Contributing

We welcome contributions! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for:

- Development setup instructions
- Code style guidelines
- Testing requirements
- Pull request process

### Good First Issues

Look for issues labeled `good first issue` — perfect for newcomers:

- Documentation improvements
- Test coverage additions
- Accessibility enhancements
- Translation support

---

## License

This project is licensed under the **MIT License** — see [LICENSE](LICENSE) for details.

```
MIT License

Copyright (c) 2026 Chintalavalasa Gram Panchayat
Directorate of Waste Management & Sanitation
```

---

## Acknowledgements

- [Swachh Bharat Mission](https://swachhbharatmission.gov.in/) — Government of India sanitation programme
- [Solid Waste Management Rules, 2026](https://moef.gov.in/) — Regulatory framework
- [Flask](https://flask.palletsprojects.com/) — Web framework
- [Supabase](https://supabase.com/) — Database and storage
- [Bootstrap](https://getbootstrap.com/) — UI framework
- [Leaflet](https://leafletjs.com/) — Interactive maps

---

## Support

- 📖 **Documentation**: [DEPLOY.md](DEPLOY.md), [ARCHITECTURE.md](ARCHITECTURE.md)
- 🐛 **Bug Reports**: [GitHub Issues](https://github.com/jaganmohan08112005-sketch/SmartGarbage/issues)
- 💡 **Feature Requests**: [GitHub Issues](https://github.com/jaganmohan08112005-sketch/SmartGarbage/issues)
- 🔒 **Security**: See [SECURITY.md](SECURITY.md)

---

<p align="center">
  Built with ❤️ for cleaner cities
</p>
