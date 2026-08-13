# Keep-alive & infrastructure alternatives (Cloudflare-free)

This directory explains how to replace each Cloudflare piece of the SmartGarbage
setup with technology the project **already uses** — Supabase, Render, and GitHub
Actions — so you don't need a separate Cloudflare account or zone.

| Cloudflare piece | Replacement | Integrated with | Cost |
|---|---|---|---|
| Worker cron keep-alive (`worker.js` + `wrangler.toml`) | Supabase `pg_cron` + `pg_net` job — see [`supabase_keepalive.sql`](supabase_keepalive.sql) | Supabase Postgres (already the app DB) | Free |
| Custom domain zone (DNS, SSL) | Render native custom domains + managed TLS | Render (already the host) | Free |
| Edge caching of static assets | Render Starter upgrade (zero code) **or** inline critical CSS (code) | Render (already the host) | ~$7/mo or free |

## Why this exists

Cloudflare was proposed for three jobs. Two of them are achievable with existing
stack pieces; the third (edge caching) has a cheaper, code-only equivalent.

1. **Keep-alive (exact 5-minute cadence).** GitHub's free-tier scheduler delays
   `schedule` events for low-activity repos (verified: this repo's workflow fired
   ~hourly, not every 5 min). Supabase `pg_cron` runs **inside** the Postgres the
   app already uses and supports an HTTP request per job via `pg_net` — official
   Supabase Cron, free tier, no new account.

2. **Custom domain.** Render's free plan officially supports custom domains with
   managed TLS (Let's Encrypt, auto-renewed) — no Cloudflare needed to own the
   domain, get a Search Console domain property, or serve the real `/robots.txt`
   and `/sitemap.xml`. See "Render custom domain" below.

3. **Edge caching.** Render free does **not** support edge caching (official
   docs). Two alternatives, pick one:
   - **Upgrade the service to Render Starter (~$7/mo)** — zero code, and it also
     removes the 15-minute spin-down, the `/robots.txt` "disallow all" while
     spun down, and the free 750-hour/month cap. This is the single highest
     ROI change for the Stackra LCP reading.
   - **Inline critical CSS in `base.html`** — removes the render-blocking
     `bootstrap.min.css` fetch from the first-paint path so a slow origin TTFB
     no longer delays LCP. Free, but a real code change with visual-regression
     risk; test at 320–768px before deploying.

## What was removed

`worker.js` + `wrangler.toml` (the Cloudflare Worker keep-alive) were deleted —
they are superseded by `supabase_keepalive.sql`. They remain in git history
(`git show 68ddad1:keepalive/worker.js`) if you ever do set up Cloudflare.

## Render custom domain (free)

1. Dashboard → your `smartgarbage` service → **Settings → Custom Domains**.
2. Add the domain (e.g. `chintalavalasa.in` or `smartgarbage-chintalavalasa.in`).
3. In your registrar's DNS:
   - **Apex** (`@`): two `A` records pointing at the Render load-balancer IPs
     shown in the dashboard.
   - **Subdomain** (`www`): `CNAME` to `smartgarbage.onrender.com`.
4. Render verifies ownership and issues/renews the TLS certificate
   automatically (Let's Encrypt). Propagation 5 min–24 h.

The app is host-agnostic (verified: no `onrender.com` string in code; canonical,
sitemap, robots, og:image and JSON-LD all follow the `Host` header), so nothing
in the codebase needs to change. CSP uses `'self'` + explicit hosts — no edit.

## Keep-alive layering (after this switch)

- **UptimeRobot** (today): 5-min external pings.
- **Supabase pg_cron + pg_net** (primary): exact 5-min cadence from inside the
  app's own database.
- **GitHub Actions** (backup): fires on every push + best-effort hourly schedule.

With Render free's 750 instance-hours/month, a strict 5-minute keep-alive runs
the instance ~720 h/month — just under the cap. If that margin is uncomfortable,
drop the pg_cron cadence to `*/10 * * * *` (Render's sleep threshold is 15 min)
or rely on the GitHub/UptimeRobot pings alone.

## Verification

- Keep-alive: watch `cron.job_run_details` for `Succeeded` runs, or check
  Render logs for periodic `/health` 200s.
- Domain: `curl -I https://<your-domain>/` returns 200 with a Render-issued
  cert; `/robots.txt` returns the app's real file while the instance is warm.
- Caching: `curl -I https://<your-domain>/static/...` shows
  `Cache-Control: public, max-age=31536000, immutable` (browser/Cloudflare-free
  caching relies on this header + the `?v=` deploy stamp for invalidation).
