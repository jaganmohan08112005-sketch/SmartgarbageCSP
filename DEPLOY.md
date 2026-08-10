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
NOTE — the recurring "old robots.txt" audit finding is now fully diagnosed:
Render's platform edge intermittently serves a DEFAULT blocking robots.txt
(`User-agent: *` + `Disallow: /`) for *.onrender.com platform domains. It is
NOT a code regression — the app's route always serves the open file (CI-
enforced by `test_robots_txt_never_blocks_crawlers`), and no commit in this
repo's history ever produced a sitewide `Disallow: /`. Proof: the exact path
`/robots.txt` returns the edge default while `/robots.txt?cb=<ts>` and
no-cache requests return the app's open file (the edge response also carries
none of the app's headers — no `Cache-Control`, no CSP). The reliable fix is a
CUSTOM DOMAIN (see §8.2.1) — the platform default applies to *.onrender.com
subdomains, so the scan should be pointed at the custom domain.

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

**Important:** because Render's edge may serve its default blocking robots.txt
for the exact path `/robots.txt` on the *.onrender.com platform domain, ALWAYS
verify with a cache-busting query string (which reaches the app directly):

```bash
curl -s "https://smartgarbage.onrender.com/robots.txt?cb=$(date +%s)"
curl -sI https://smartgarbage.onrender.com/sitemap.xml
```

**robots.txt must (check the cache-busted response):**
- Contain `Allow: /` and **no** sitewide `Disallow: /` line — the audit's
  #1 visibility blocker.
- Have explicit AI-bot groups — `GPTBot`, `OAI-SearchBot`, `ClaudeBot`,
  `Google-Extended`, `PerplexityBot` — each `Allow: /` plus the four
  private-path disallows (`/admin`, `/api/`, `/worker`, `/dashboard`).
- End with `Sitemap: https://smartgarbage.onrender.com/sitemap.xml`.
- Send `Cache-Control: no-store` (both `robots.txt` and `sitemap.xml` do;
  keep the header and the `test_robots_txt_never_blocks_crawlers` /
  `test_sitemap_lists_all_public_pages` tests green if these routes change).

If the **plain** `/robots.txt` (no query string) returns only
`User-agent: *` + `Disallow: /` with none of the app's headers, that is
Render's edge default, NOT a code bug — proceed to §8.2.1.

**sitemap.xml must** return `200` with `application/xml` and list `/`,
`/schedule`, `/report`, `/transparency`, `/register`, `/register/picker`,
`/privacy`.

### 8.2.1 The robots.txt edge-default problem → use a custom domain

Render's platform edge intermittently serves a default blocking robots.txt
for `*.onrender.com` subdomains, and the app cannot change that (the request
never reaches gunicorn — the response carries none of the app's headers).
The reliable fix is a custom domain:

1. Register a domain (e.g. `smartgarbage-chintalavalasa.in`).
2. Render Dashboard → the service → **Settings → Custom Domains → Add
   Domain**, then add the DNS records Render provides (CNAME/ALIAS to
   `smartgarbage.onrender.com`). Render provisions the SSL certificate.
3. Verify the app's own robots.txt is served on the custom domain:
   ```bash
   curl -s "https://YOURDOMAIN/robots.txt?cb=$(date +%s)"   # must contain Allow: /
   curl -sI https://YOURDOMAIN/robots.txt                    # must show Cache-Control: no-store
   ```
4. Point the Stackra scan, Search Console property and sitemap at the
   custom domain from then on.

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

Add the property `https://smartgarbage.onrender.com/` (URL-prefix) and verify
ownership one of two ways — both are config-only, no repo changes (DNS is
not available on the `*.onrender.com` subdomain; it becomes an option on a
custom domain, §8.2.1):

- **Google Analytics (preferred):** after §8.3 is done, Search Console offers
  the "Google Analytics" method because the GA4 data-stream URL matches.
- **HTML tag (fallback):** Search Console → HTML tag method → copy the
  `content="…"` token → Render Dashboard → **Environment** → add
  `GOOGLE_SITE_VERIFICATION=<token>` → redeploy. The meta tag is
  config-gated in `base.html` (`{% if config.get('GOOGLE_SITE_VERIFICATION') %}`)
  and renders on every page only while the env var is set — no token ships
  otherwise.

Then:
1. **Sitemaps** → submit `https://smartgarbage.onrender.com/sitemap.xml`.
2. **URL Inspection** → for `/`, `/schedule`, `/report`, `/transparency`:
   "Test live URL" → "Request indexing" (do this after the robots fix so
   the crawler is actually allowed in).
3. After ~24 h, re-run the Stackra scan and confirm "Blocked from Search"
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
