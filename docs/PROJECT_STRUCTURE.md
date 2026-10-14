# SmartGarbage — Project Structure, Architecture & Workflow

> **SmartGarbage Chintalavalasa** — Community-Based Smart Waste Management and Digital
> Governance System for the five wards of Chintalavalasa Gram Panchayat.
> Live: https://smartgarbage.onrender.com · Branch: CSE (Data Science), Dept. of Data Engineering, MVGR (A)
> Team: M. Jaganmohan (24331A4441), L. Reshma (24331A4434), P. Narasimha Murthy (24331A4446), K. Augustin Paul Kumar (24331A4426)

---

## 1. Top-Level Layout

The deployment platform (Render + Docker) runs the app **from the repository root**
(`Dockerfile` → `COPY . .` → `gunicorn wsgi:app`), so the runtime stack stays at the root.
Student report / deliverable tooling is grouped in `report/`; documentation in `docs/`.

```
SmartGarbage/
├── app/                    ← THE APPLICATION (backend + frontend)
│   ├── __init__.py         Flask app factory (create_app) — config, blueprints, extensions
│   ├── routes/             ← BACKEND CONTROLLERS (all HTTP endpoints)
│   │   ├── public.py       Public pages: home, schedule, transparency, about, faq, contact, impact, track, search
│   │   ├── citizen.py      Citizen features: report form, complaints, Green Points, notifications, PAYT
│   │   ├── auth.py         Login / register / MFA / password reset / email verification
│   │   ├── admin.py        Admin dashboard, ward ops, audit log, data-deletion tools
│   │   ├── worker.py       Sanitation-worker app (routes + issue resolution)
│   │   ├── iot.py          IoT bin-telemetry ingest (HMAC-signed sensor payloads)
│   │   ├── webhook.py      WhatsApp / Twilio / Razorpay webhook receivers
│   │   └── analytics.py    Transparency statistics & analytics JSON APIs
│   ├── models.py           SQLAlchemy ORM models (User, Complaint, Bin, Ward, Payment, …)
│   ├── ml_model.py         ML: bin-overflow risk classification + fill-level ETA regression
│   │                          (ml_model.pkl, ml_fill_model.pkl shipped alongside)
│   ├── jobs.py             RQ background jobs (OTP mail, receipts, WhatsApp sends)
│   ├── alerting.py         Health/stall alerting rules
│   ├── push.py             Web-push notifications
│   ├── search_index.py     Site search index
│   ├── i18n.py             Bilingual strings (English / Telugu)
│   ├── mail_probe.py       Mail health probe (used by /health)
│   │
│   ├── templates/          ← FRONTEND — Jinja2 pages (47: base + every page incl. offline.html)
│   │   └── base.html       Shared shell: nav, footer, helpline strip, WhatsApp card, PWA hooks
│   ├── static/             ← FRONTEND assets (served by Flask/Cloudflare CDN)
│   │   ├── style.css       Main stylesheet (theme: dark-teal SmartGarbage brand)
│   │   ├── css/critical.css  Inlined above-the-fold CSS (performance)
│   │   ├── vendor/         bootstrap.min.css / bootstrap.bundle.min.js (vendored, no CDN risk)
│   │   ├── js/             admin.js, chatbot.js, offline.js, global.min.js, weather.min.js
│   │   ├── img/            Site imagery: hero-recycle.jpg, about-workers.jpg, about-sorting.jpg
│   │   ├── fonts/          Self-hosted fonts (offline-capable PWA)
│   │   ├── sw.js           Service worker: offline cache tiers + background sync
│   │   ├── manifest.json   PWA manifest (installable app, icons 192/512)
│   │   └── uploads/        Citizen-uploaded complaint photos (runtime data)
│   └── __pycache__/        Python bytecode cache (git-ignored, auto-generated)
│
├── migrations/             Alembic DB migrations (flask db upgrade on deploy)
├── tests/                  Pytest suite (run_pg_suite.py mirrors CI against local Postgres)
├── scripts/                Ops/maintenance scripts (local_pg.py: the one embedded-Postgres
│                           boot / retry / wipe helper, shared by run_pg_suite.py and
│                           run_local_stack.py — and via it, the CI Playwright/a11y jobs)
├── docs/                   ← DOCUMENTATION (this file, DEPLOY, ARCHITECTURE, guides/, wiki refs)
├── report/                 ← STUDENT REPORT TOOLING & DELIVERABLES
│   ├── generate_final_report.py  Builds DOCUMENTATION_UPDATED.docx (→ submission/documentation/)
│   ├── generate_pdf.py           Builds DOCUMENTATION_UPDATED.pdf (--record, then plain; → submission/book/)
│   ├── report_figures.py         Draws design diagrams (fig7_2 defence rings, fig7_3 rewards loop)
│   ├── _diagrams/                Diagram PNGs + live-site screenshots used in the report
│   ├── _inputs/                  Templates (doc_template.docx, ppt_template.pptx, prev_deck.pptx)
│   ├── build_deck_v2.py          Builds DOCUMENT_FINAL.pptx (20 slides, IEEE refs)
│   ├── _render_qa.py             Renders the delivered deck to QA images
│   ├── smartgarbage-deployment.excalidraw  Editable deployment architecture diagram
│   └── video/
│       └── _make_video_live.py   Demo-video builder (Playwright live-site capture + TTS + ffmpeg)
│
├── submission/             ← R24 DELIVERY PACKAGE (one copy of each deliverable)
│   ├── book/SmartGarbage_BOOK_R24.pdf              BOOK print master (89 pp, letter)
│   ├── documentation/SmartGarbage_Documentation_Softcopy.docx
│   ├── video/SmartGarbage_Demo_Video.mp4           9:50 live-website walkthrough (720p)
│   ├── ppt/SmartGarbage_Presentation.pptx          20-slide deck (R24 chrome)
│   ├── code/SmartGarbage_Source_Code.zip           409-file source archive (git-ignored)
│   ├── RUNBOOK.md                                  Submission-day runbook (print/bind, hand-in set, post-submission)
│   └── _scratch/verify_submission.py               One gate for all five deliverables (see below)
│
├── wsgi.py                 Production entrypoint (gunicorn wsgi:app; starts in-process RQ worker)
├── worker.py               Standalone RQ worker entrypoint (optional, Render worker service)
├── seed_db.py              Demo-data seeder (SEED_DEMO=true on first deploy)
├── manage.py               Flask CLI helpers
├── run.py                  Local dev launcher (python run.py)
├── run_pg_suite.py         Runs pytest against a bundled local Postgres (CI mirror)
├── Dockerfile              Render container build (installs, migrations, gunicorn CMD)
├── render.yaml             Render service definition (web service; worker block documented/disabled)
├── requirements.txt        Runtime Python dependencies
├── requirements-dev.txt    Dev/test dependencies
├── pytest.ini              Test configuration
├── .env.example            Template for required environment variables (never commit .env)
├── .dockerignore / .gitignore
├── README.md               Project overview & quick start
├── ARCHITECTURE.md         Deep-dive: modules, data model, security design
├── DEPLOY.md               Step-by-step deployment & operations runbook
├── SECURITY.md             Security policy & disclosure
├── CONTRIBUTING.md         Contribution workflow
└── LICENSE                 Project license
```

---

## 2. Architecture (the 30-second version)

```
                    ┌─────────────────── CITIZENS / WORKERS / ADMINS ───────────────────┐
                    │  Browser (desktop/mobile PWA) · WhatsApp · Toll-free helpline     │
                    └───────────────┬──────────────────────────────┬────────────────────┘
                                    │ HTTPS                        │ webhook callbacks
                    ┌───────────────▼──────────────┐   ┌───────────▼─────────────┐
                    │  Cloudflare (CDN, DNS, TLS)  │   │ Meta WhatsApp Cloud API │
                    └───────────────┬──────────────┘   └───────────┬─────────────┘
                                    │                              │
┌──────────────┐    ┌──────────────▼──────────────────────────────▼─────────────┐
│ IoT bin      │───▶│  RENDER (Docker, gunicorn+gevent, 2 workers)              │
│ sensors      │HMAC│  Flask app factory (app/__init__.py)                      │
└──────────────┘    │  ├─ routes/  → 9 blueprints (public, citizen, auth, …)    │
                    │  ├─ ml_model.py → overflow risk + fill ETA                │
                    │  ├─ jobs.py → RQ queue (mail, WhatsApp, receipts)         │
                    │  └─ static/ → PWA (sw.js offline cache, manifest)         │
                    └───────┬──────────────────────────┬────────────────────────┘
                            │ SQLAlchemy               │ RQ jobs
                 ┌──────────▼──────────┐    ┌──────────▼─────────┐
                 │ SUPABASE Postgres   │    │ Redis (optional)   │
                 │ (primary datastore) │    │ (job broker)       │
                 └─────────────────────┘    └────────────────────┘
```

Full design details (module responsibilities, data model, security layers): see
[ARCHITECTURE.md](../ARCHITECTURE.md). Deployment runbook: [DEPLOY.md](../DEPLOY.md).

---

## 3. Request Workflow (example: citizen reports a missed pickup)

1. **Citizen** opens `/report` (PWA-cached, works offline) → picks ward, GPS auto-locate,
   attaches photo proof → submits.
2. **routes/citizen.py** validates input, rejects duplicates (same location ≤100 m within
   30 min), stores the complaint via **models.py**, issues a tracking token.
3. Photo goes to `static/uploads/`; a confirmation email/WhatsApp message is queued as an
   RQ job (**jobs.py**) — sent inline if Redis is not configured.
4. **routes/worker.py** (staff app) assigns and resolves the issue; status changes are
   visible instantly on `/track` and on the admin dashboard.
5. **routes/analytics.py** feeds the numbers to `/transparency` and `/impact`;
   **ml_model.py** uses accumulated telemetry for overflow-risk predictions on `/schedule`.

---

## 4. Frontend / Backend Split

| Layer | Location | Notes |
|---|---|---|
| Backend (Python/Flask) | `app/routes/`, `app/models.py`, `app/ml_model.py`, `app/jobs.py` | 9 route modules, all endpoints |
| Frontend (server-rendered) | `app/templates/` | Jinja2, bilingual (i18n.py), 47 pages |
| Frontend assets | `app/static/` | CSS, JS, images, fonts, service worker |
| Database schema | `migrations/` + `app/models.py` | Alembic migrations run on deploy |
| Background jobs | `app/jobs.py`, `worker.py`, `wsgi.py` | RQ; in-process worker by default |

---

## 5. Cleanups Applied (consistency pass)

- Removed empty root `static/` (legacy duplicate of `app/static/`).
- Removed unreferenced `app/templates/partials/critical.css` (real one: `app/static/css/critical.css`).
- Removed unused `app/static/survey_chart.png` and stale `app/static/shots/` screenshots.
- Deleted 10 leftover test SQLite databases from `instance/` (kept `garbage.db`, `secret_key`).
- Removed scratch QA artifacts (`_deck_render/`, `_figcheck.html`, root `__pycache__/`).
- Consolidated scattered docs into `docs/` and report tooling into `report/` (generators
  made location-independent so they still rebuild the docx/pdf/video from their new home).

## 6. How to Rebuild the Deliverables

```bash
# Final report (Word):
python report/generate_final_report.py          # → report/DOCUMENTATION_UPDATED.docx
# Final report (PDF): --record first, then plain run:
python report/generate_pdf.py --record && python report/generate_pdf.py
# Presentation diagrams:
python report/report_figures.py                 # → report/_diagrams/report/fig7_*.png
# Deck:
python report/build_deck_v2.py                  # → report/DOCUMENT_FINAL.pptx
# Demo video (records the local stack on 127.0.0.1:5057):
python report/video/_make_video_live.py         # → submission/video/SmartGarbage_Demo_Video.mp4
# Source-code zip:
python submission/_scratch/build_code_zip.py --write
# Verify all five deliverables (geometry/numbering, DOCX+PPTX integrity,
# video streams, zip manifest+hashes, and drift from the committed source):
python submission/_scratch/verify_submission.py
```

After regenerating, copy the build output over the matching file in `submission/`
(one delivered copy of each artifact; see `submission/README.md`), then run
`verify_submission.py` — it exits non-zero when an artifact drifted.
