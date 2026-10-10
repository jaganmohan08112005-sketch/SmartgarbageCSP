# Cloudflare CDN & Edge Caching Setup — SmartGarbage

> **Goal:** cut cold TTFB from ~1.2s to <100ms by caching HTML and static assets
> at Cloudflare's global edge.
> **Cost:** Free (Cloudflare Free plan) + the price of a domain you own.
> **Time:** ~30 minutes (plus DNS propagation).

This is the **single canonical guide** for putting SmartGarbage behind
Cloudflare. It replaces four overlapping/out-of-date guides that used to live at
`wiki/CLOUDFLARE_CDN_SETUP.md`, `docs/guides/cloudflare/CLOUDFLARE_QUICK_START.md`,
`docs/guides/cloudflare/CLOUDFLARE_CACHING_CONFIG.md` and
`docs/guides/cloudflare/CLOUDFLARE_SETUP_GUIDE.md` — all retired in favour of
this file.

---

## Status & prerequisites

SmartGarbage runs on **Render** at `smartgarbage.onrender.com`. Render already
serves it through *its own* Cloudflare edge (`Server: cloudflare`,
`cf-cache-status: DYNAMIC`), but you cannot configure that edge — HTML is never
cached there.

To use *your own* Cloudflare (cache rules, WAF, Brotli, HTTP/3), you need:

1. ✅ A free Cloudflare account — [sign up](https://dash.cloudflare.com/sign-up)
2. ✅ **A domain you control.** Cloudflare can only proxy a zone you own; it
   cannot proxy or apply rules to `*.onrender.com`. Any cache rule written
   against `smartgarbage.onrender.com` can never be created — that hostname
   belongs to Render, not to you.
3. ✅ Access to that domain's registrar (to change nameservers).

The worked example throughout is **`smartgarbage.eu.org`** (free, via
[eu.org](https://nic.eu.org)); substitute your own domain if it differs. The
Render origin you point at stays `smartgarbage.onrender.com`.

> **Not live yet?** Until a custom domain resolves and is proxied by Cloudflare,
> there is nothing to configure in your Cloudflare zone — the sections below
> only apply once you own the domain and it is on Cloudflare's nameservers.

---

## What the app already does (no code changes needed)

The Flask app is already edge-cache friendly:

| Concern | How the app handles it |
|---|---|
| `Vary: Cookie` | Stripped from public responses in three layers — the session interface override, an `after_request` hook, and a WSGI middleware (covers responses without `Set-Cookie`). |
| HTML cache headers | `Cache-Control: public, max-age=60, s-maxage=300, stale-while-revalidate=60` |
| Static assets | `Cache-Control: public, max-age=31536000, immutable`, content-hashed URLs |
| Authenticated pages | `Cache-Control: no-store` |

The rest is Cloudflare dashboard configuration.

---

## Step 1 — Add your domain to Cloudflare

1. [dash.cloudflare.com](https://dash.cloudflare.com) → **+ Add a Site**
2. Enter your domain → select the **Free** plan → **Continue**

## Step 2 — Point the domain at Render (DNS)

Once Cloudflare shows your two nameservers, update them at your registrar
(propagation is usually <1 hour, up to 48h). Then in **DNS → Records**, add:

| Type | Name | Content | Proxy |
|---|---|---|---|
| CNAME | `@` | `smartgarbage.onrender.com` | 🟠 Proxied |
| CNAME | `www` | `smartgarbage.onrender.com` | 🟠 Proxied |

**The proxy must be ON (orange cloud)** — otherwise traffic bypasses Cloudflare
and nothing is cached.

> If you registered through Cloudflare Registrar the nameservers are already
> set; skip straight to the DNS records.

## Step 3 — SSL/TLS

1. **SSL/TLS → Overview** → set mode to **Full (Strict)**
   (Render has a valid certificate, so strict works; "Flexible" causes redirect loops.)
2. **SSL/TLS → Edge Certificates** → enable **Always Use HTTPS** and
   **Automatic HTTPS Rewrites**.

## Step 4 — Add the custom domain in Render

1. Render Dashboard → your **smartgarbage** service → **Settings**
2. **Custom Domains** → **Add Custom Domain** → enter your domain
3. Wait 1–2 minutes for Render to verify DNS and issue SSL

The app reads `request.host`, so canonical/Open Graph URLs and the sitemap
(`_external=True`) pick up the new domain automatically. If you set
`RENDER_EXTERNAL_URL`, update it to `https://smartgarbage.eu.org`.

## Step 5 — Cache Rules

**Rules → Cache Rules → Create rule.** Cache Rules are evaluated **in order and
the first match wins**, so create them in this order — the bypass rule must come
first so an authenticated page can never be cached by a later match.

### Rule 1 — Bypass dynamic / authenticated routes (create first)

- **When:** `http.request.uri.path` starts with any of `/admin`, `/login`,
  `/logout`, `/register`, `/dashboard`, `/report`, `/api/`, `/webhook/`,
  `/set-lang`, `/payt`, `/track`, `/mfa`, `/notifications`
- **Or** equals `/robots.txt`, `/sitemap.xml`, `/feed.xml`
- **Then:** Cache eligibility → **Bypass cache**

### Rule 2 — Cache static assets

- **When:** `http.request.uri.path` matches `^/static/`
- **Then:** Cache eligibility → **Eligible for cache**
  - Edge TTL → Override → `2592000` (30 days)
  - Browser TTL → Override → `31536000` (1 year)

### Rule 3 — Cache public HTML

- **When:** `http.request.uri.path` equals one of `/`, `/schedule`, `/about`,
  `/faq`, `/transparency`, `/privacy`, `/terms`
- **Then:** Cache eligibility → **Eligible for cache**
  - Edge TTL → Override → `300` (5 min)
  - Browser TTL → Override → `60` (1 min)

> **Why an allowlist, not "everything except…".** An earlier revision cached all
> paths except a short deny-list — which would have edge-cached a citizen's
> authenticated page (`/track/…`, `/payt/…`, `/dashboard`) and could serve it to
> the next visitor. The explicit allowlist above, plus bypass-first ordering,
> makes that impossible. The app also sends `Cache-Control: no-store` on
> authenticated pages as a second layer.

> Older guides suggested **Page Rules** matching `*smartgarbage.eu.org/*`. Page
> Rules still work but are limited to 3 on the Free plan and are superseded by
> Cache Rules; use Cache Rules unless you specifically need Page Rules.

## Step 6 — Performance features

Enable under **Speed → Optimization → Content Optimization**:

- ✅ Brotli compression
- ✅ HTTP/3 (QUIC)
- ✅ 103 Early Hints
- ✅ Auto Minify (JS, CSS, HTML — the app already minifies; this catches misses)

And under **Network**: enable **WebSockets** (Cloudflare disables them by default
on some plans).

## Step 7 — Verify

```bash
# 1. Cloudflare is in front (expect a cf-ray header)
curl -sI https://smartgarbage.eu.org/ | grep -i "cf-ray"

# 2. HTML is cached (first MISS, then HIT)
curl -sI https://smartgarbage.eu.org/ | grep -i "cf-cache-status"
curl -sI https://smartgarbage.eu.org/ | grep -i "cf-cache-status"

# 3. Vary must NOT contain Cookie
curl -sI https://smartgarbage.eu.org/ | grep -i vary          # expect: vary: Accept-Encoding

# 4. TTFB
curl -o /dev/null -s -w "TTFB: %{time_starttransfer}s\n" https://smartgarbage.eu.org/   # expect <0.1s on a HIT

# 5. Static assets cached at the edge
curl -sI https://smartgarbage.eu.org/static/style.css | grep -i "cf-cache-status"       # expect: HIT
```

Or run the whole check at once — Cloudflare presence, `vary`, static + HTML cache status, and TTFB:

```bash
bash scripts/verify_edge_caching.sh smartgarbage.eu.org
```

## Step 8 — Optional hardening (WAF, Free plan)

**Security → WAF → Custom Rules** — a bot rule, e.g. block user agents
containing `sqlmap`, `nikto`, `masscan`, `nmap`.

**Security → WAF → Rate Limiting Rules** — throttle `POST /login`
(for example, 5 requests / 10 minutes → block for 10 minutes).

## Step 9 — Monitoring

**Analytics & Logs → HTTP Analytics** for cache hit ratio and bandwidth saved.
Target **>80%** for static assets and **>50%** for HTML.

---

## Expected results

| Metric | Before (Render only) | After (Cloudflare) |
|---|---|---|
| Cold TTFB | ~1.2s | **<100ms** (edge cache hit) |
| Repeat TTFB | <10ms | **<10ms** |
| Static asset delivery | From origin region | **Nearest edge (300+ PoPs)** |
| `cf-cache-status` | DYNAMIC | **HIT** after first request |
| SSL | Render-managed | Cloudflare edge |
| DDoS protection | None | Free, unlimited |
| Brotli / HTTP/3 | Render-managed | Cloudflare edge |

## Cost

| Item | Cost |
|---|---|
| Cloudflare Free plan | ₹0 |
| Domain (e.g. Cloudflare Registrar) | ~₹600–800/year |
| SSL, DDoS protection, CDN bandwidth, privacy | Included free |
| **Total** | **≈₹600–800/year** |

---

## Automated setup

`scripts/cloudflare-setup.sh` performs the DNS records, SSL mode, performance
toggles and cache rules via the Cloudflare API:

```bash
export CF_API_TOKEN="your-api-token"   # https://dash.cloudflare.com/profile/api-tokens
export CF_ZONE_ID="your-zone-id"       # domain → Overview → Zone ID
bash scripts/cloudflare-setup.sh
```

The script points the CNAMEs at the Render origin (`smartgarbage.onrender.com`)
and writes the equivalent caching as three ordered Cache Rules — bypass dynamic
routes → cache static assets (30 d / 1 y) → cache the public HTML allowlist
(5 min / 1 min).

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `ERR_TOO_MANY_REDIRECTS` | SSL set to "Flexible" while Render forces HTTPS | Set SSL to **Full (Strict)** |
| `cf-cache-status: DYNAMIC` on HTML | Cache rule missing, or `Vary: Cookie` still present | Confirm the HTML rule is deployed; check `vary` header (Step 7) |
| `cf-cache-status: MISS` | First visit | Re-request — the next hit should be HIT |
| Login/dashboard pages cached | Bypass rule not matched | Add the paths to Rule 3; the app also sends `no-store` |
| `robots.txt` stale on the custom domain | Cached copy | Add a bypass Cache Rule for `/robots.txt` |
| WebSockets fail | Disabled on the zone | **Network → WebSockets** → ON |
| Render reports the wrong client IP | — | No action needed; Cloudflare sets `X-Forwarded-For`, which the app's `ProxyFix` already reads |
| Domain not resolving | Nameservers not updated / not propagated | Wait; verify at your registrar |
