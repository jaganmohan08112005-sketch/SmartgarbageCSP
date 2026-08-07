# SmartGarbage — Deployment Guide (Supabase + Fly.io)

## 1. Create Supabase Project

1. Go to [supabase.com](https://supabase.com) → New Project
2. Choose a strong DB password — save it.
3. After creation, go to **Settings → Database → Connection pooling**.
4. Copy the **Transaction mode (port 5432)** connection string. It looks like:
   ```
   postgresql://postgres.[ref]:[password]@aws-0-[region].pooler.supabase.com:5432/postgres
   ```
5. Also copy:
   - `SUPABASE_URL` from **Settings → API** (e.g. `https://xyz.supabase.co`)
   - `SUPABASE_SERVICE_ROLE_KEY` from **Settings → API** (secret, server-side only)

## 2. Create Storage Bucket

1. In Supabase dashboard → **Storage** → New bucket
2. Name: `uploads`
3. Public bucket: **ON** (we serve images publicly; RLS is optional since the app controls access)
4. Set file size limit to 16MB to match Flask's `MAX_CONTENT_LENGTH`

## 3. Run Migrations

Locally (or in a one-off Fly.io shell):

```bash
export DATABASE_URL="postgresql://postgres.[ref]:[pw]@...pooler.supabase.com:5432/postgres"
flask db upgrade
```

## 4. Deploy on Fly.io (recommended)

```bash
# Install flyctl
curl -L https://fly.io/install.sh | sh

# Login
fly auth login

# Launch (first time)
fly launch --no-deploy

# Set secrets
fly secrets set \
  SECRET_KEY="$(openssl rand -hex 32)" \
  DATABASE_URL="postgresql://postgres.[ref]:[pw]@...pooler.supabase.com:5432/postgres" \
  SUPABASE_URL="https://xyz.supabase.co" \
  SUPABASE_SERVICE_ROLE_KEY="eyJ..." \
  IOT_TELEMETRY_SECRET="$(openssl rand -hex 32)" \
  REDIS_URL="redis://:your-redis-password@your-region.upstash.io:6379" \
  TWILIO_ACCOUNT_SID="AC..." \
  TWILIO_AUTH_TOKEN="..." \
  TWILIO_FROM_NUMBER="+1..." \
  TWILIO_WHATSAPP_NUMBER="whatsapp:+1..." \
  RAZORPAY_KEY_ID="rzp_live_..." \
  RAZORPAY_KEY_SECRET="..." \
  RAZORPAY_WEBHOOK_SECRET="$(openssl rand -hex 32)"

> `REDIS_URL` is recommended when running more than one machine/worker — it
> makes rate-limit counters shared across instances (the app falls back to
> in-memory counters when unset). Twilio vars enable SMS/WhatsApp OTP and
> complaint status alerts; leave them unset to fall back to email/dev display.

## Background job queue (RQ)

SMS/WhatsApp sends, webhook dispatch, export generation and PAYT dunning run
through an RQ worker over the same `REDIS_URL` (the Dockerfile starts
`python worker.py` alongside gunicorn). Without `REDIS_URL` every job executes
inline, so local dev and the test-suite need no extra process.

# Deploy
fly deploy
```

## 5. Alternative: Render Starter + Supabase

Update `render.yaml` (already configured for starter plan + Supabase env vars):

1. In Render dashboard → New Web Service → connect repo
2. Set `plan: starter`
3. Add env vars: `DATABASE_URL`, `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `SECRET_KEY`, `IOT_TELEMETRY_SECRET`, `REDIS_URL` (Upstash free tier)
4. Remove the Render managed Postgres database (Supabase is your DB now)
5. Deploy

### Background jobs on Render (important)

Background jobs (SMS/WhatsApp sends, webhook dispatch, export generation, PAYT
dunning, retention/sweeps) run through an RQ worker on `REDIS_URL`. Two paths:

- **Blueprint (recommended):** `render.yaml` defines a `smartgarbage-worker`
  service (runs `python worker.py`). If your service was created from this
  blueprint, that worker executes the queue automatically.
- **Native-Python services (the current live one):** Render created it as a
  native Python service, so it ignores `render.yaml` and the Dockerfile, and
  starts `gunicorn app:app`. The app detects this: when `REDIS_URL` is set,
  `wsgi.py` runs the RQ worker in an in-process thread (set
  `RQ_IN_PROCESS_WORKER=false` to disable when a dedicated worker exists).
  The Docker path spawns `python worker.py` itself and sets that flag for you.

Without `REDIS_URL` every job executes inline, so local dev and the test-suite
need no extra process.

### Start Command (native-Python services)

If the live service is native Python, set its Start Command to:

```
gunicorn wsgi:app --bind 0.0.0.0:$PORT -w 1 --worker-class gevent --timeout 120
```

(`wsgi:app` triggers the same boot path as `app:app` — migrations + the
in-process worker — and binds the port Render routes to.)

## 6. Seed Data (local / staging only)

```bash
export SEED_DEMO=true
flask db upgrade
python seed_db.py
```

**Never set `SEED_DEMO=true` in production.**

## 7. Post-Deploy Checks

```bash
# Health
curl https://your-app.fly.dev/health

# DB connection
curl https://your-app.fly.dev/api/analytics-data

# Storage
# Submit a complaint with photo → verify image URL starts with your Supabase project URL
```

## 8. SEO & Analytics Go-Live Checklist

Run this after every deploy that touches routing, robots.txt, or analytics.
The Stackra audit caught the live site serving an OLD robots.txt that blocked
all crawlers (`Disallow: /`) — verify each time, not just once.

### 8.1 Deploy to Render

1. Push to `main` (Render auto-deploys from the connected repo) or use
   Dashboard → **Manual Deploy → Deploy latest commit**.
2. For a **native-Python service**, confirm the Start Command is:
   ```
   gunicorn wsgi:app --bind 0.0.0.0:$PORT -w 1 --worker-class gevent --timeout 120
   ```
   (`wsgi:app` runs migrations + the in-process RQ worker — see §5.)
3. Wait for the deploy log to show migrations applied and `/health` returning
   `200` before continuing.

### 8.2 Verify robots.txt & sitemap.xml on the live domain

```bash
curl -s https://smartgarbage.onrender.com/robots.txt
curl -s https://smartgarbage.onrender.com/sitemap.xml
```

**robots.txt must:**
- Contain `Allow: /` and **no** `Disallow: /` line (that was the audit's
  #1 visibility blocker).
- Have explicit AI-bot groups — `GPTBot`, `OAI-SearchBot`, `ClaudeBot`,
  `Google-Extended`, `PerplexityBot` — each `Allow: /` plus the four
  private-path disallows (`/admin`, `/api/`, `/worker`, `/dashboard`).
- End with `Sitemap: https://smartgarbage.onrender.com/sitemap.xml`.

**sitemap.xml must** return `200` with `application/xml` and list `/`,
`/schedule`, `/report`, `/transparency`, `/register`, `/register/picker`,
`/privacy`.

### 8.3 Enable privacy-first analytics (optional)

1. Create a GA4 property → copy the Measurement ID (`G-XXXXXXX`).
2. Render Dashboard → the service → **Environment** → add
   `ANALYTICS_ID=G-XXXXXXX` (read at boot; redeploy to apply).
3. Redeploy and verify:
   - The consent banner ("We use anonymous analytics…") appears to new
     visitors — it only renders when `ANALYTICS_ID` is set.
   - `curl -s https://smartgarbage.onrender.com/ | grep gtag` shows the
     loader and `analytics_storage: denied` as the consent default.
   - Accepting the banner logs an anonymized choice to the consent register
     (`/admin` → audit) before any events fire.
4. If the banner copy ever changes, bump the `CONSENT_VERSION` env var too —
   it is recorded with every consent choice for auditability.

### 8.4 Submit to Google Search Console

1. Add the property `https://smartgarbage.onrender.com/` (URL-prefix is
   fine; no DNS changes needed if you use the HTML-tag verification).
2. **Sitemaps** → submit `https://smartgarbage.onrender.com/sitemap.xml`.
3. **URL Inspection** → for `/`, `/schedule`, `/report`, `/transparency`:
   "Test live URL" → "Request indexing" (do this after the robots fix so
   the crawler is actually allowed in).
4. After ~24 h, re-run the Stackra scan and confirm "Blocked from Search"
   and "AI crawlers blocked" are gone.

### 8.5 Publish a civic contact email

1. Confirm a real, monitored inbox (e.g. a panchayat grievance/DPO address) —
   never invent one.
2. Render Dashboard → the service → **Environment** → add
   `CIVIC_CONTACT_EMAIL=name@example.in` (read at boot; redeploy to apply).
3. Redeploy and verify the address renders in the **footer**, the **privacy
   policy → Contact** section, and the **GovernmentOrganization schema**
   (`curl -s https://smartgarbage.onrender.com/ | grep -o 'name@example.in'`).
   Until the env var is set, the email renders NOWHERE on the site — there is
   no placeholder to leak.
4. Transactional mail (OTP, PAYT receipts, status alerts) sends **from** this
   address by default; set `MAIL_DEFAULT_SENDER` explicitly if you want a
   separate noreply from-address.

## 9. Migrating Existing Data from Render Postgres

If you have data on Render's old Postgres:

1. Install `pg_dump` locally
2. Dump from Render:
   ```bash
   pg_dump "$RENDER_DATABASE_URL" > dump.sql
   ```
3. Import to Supabase:
   ```bash
   psql "$SUPABASE_DATABASE_URL" < dump.sql
   ```
4. Run `flask db upgrade` on Supabase to apply any pending Alembic migrations

## 10. Rollback Plan

- **Fly.io**: `fly deploy --image flyio/smartgarbage:previous-tag` or use the Fly dashboard
- **Render**: Previous deploy is available in the dashboard; just click Rollback
- **Supabase**: Database branching lets you snapshot before migrations; restore from backup if needed
