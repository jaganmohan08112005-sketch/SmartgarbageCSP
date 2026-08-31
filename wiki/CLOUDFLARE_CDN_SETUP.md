# Cloudflare CDN Setup Guide — SmartGarbage Chintalavalasa

> **Goal:** Reduce cold TTFB from ~1.2s to <100ms by caching HTML at Cloudflare's global edge (300+ locations).
> **Cost:** Free (Cloudflare Free plan).
> **Time:** ~30 minutes.

---

## Why Cloudflare?

| Metric | Before (Render only) | After (Cloudflare + Render) |
|---|---|---|
| **Cold TTFB** | 1.2s (Oregon server) | **<100ms** (nearest edge) |
| **Repeat TTFB** | <10ms (browser cache) | **<10ms** (edge cache) |
| **SSL** | Render-managed | Cloudflare edge SSL |
| **DDoS protection** | None | Free unlimited |
| **Brotli compression** | Render-managed | Cloudflare-optimised |
| **HTTP/3 (QUIC)** | Render-managed | Cloudflare edge |

---

## Prerequisites

Before starting, you need:

1. ✅ A Cloudflare account (free) — [sign up](https://dash.cloudflare.com/sign-up)
2. ✅ A custom domain name (required — Cloudflare cannot proxy `*.onrender.com` subdomains directly)
3. ✅ Access to your domain's registrar (to change nameservers)

> **Why a custom domain?**
> Cloudflare requires you to own a domain to proxy traffic. The free plan includes
> unlimited bandwidth, SSL, DDoS protection, and caching. Domain registration costs
> ~₹500–800/year (~$6–10) through Cloudflare Registrar (at-cost pricing, no markup).

---

## Step 1: Register or Acquire a Domain

### Option A: Buy through Cloudflare Registrar (Recommended — Cheapest)

1. Go to [dash.cloudflare.com](https://dash.cloudflare.com)
2. Click **"Domain Registration"** → **"Register Domains"**
3. Search for your domain (e.g., `smartgarbage.in`, `smartgarbagechintalavalasa.in`)
4. Add to cart and complete purchase (~₹500–800/year)

```
┌─────────────────────────────────────────────────────┐
│  🔍 Search for a domain                             │
│  ┌───────────────────────────────────────────┐      │
│  │ smartgarbage.in                           │      │
│  └───────────────────────────────────────────┘      │
│                          [Search]                    │
│                                                     │
│  Results:                                           │
│  ✅ smartgarbage.in          ₹649/yr   [Add to cart]│
│  ✅ smartgarbagechintalavalasa.in ₹599/yr [Add to]  │
│  ✅ chintalavalasagarbage.in ₹799/yr   [Add to]    │
└─────────────────────────────────────────────────────┘
```

### Option B: Use an Existing Domain

If you already own a domain (e.g., `chintalavalasa.gov.in`):
1. Go to your domain registrar
2. We'll change the nameservers in Step 3

### Option C: Use a Free Subdomain Service

If you want zero cost, use a free subdomain provider:
- `smartgarbage.lovable.app` (Lovable)
- `smartgarbage.netlify.app` (Netlify — but doesn't help with TTFB)

> ⚠️ Free subdomains don't give you Cloudflare proxy benefits. Option A is recommended.

---

## Step 2: Add Your Domain to Cloudflare

1. Go to [dash.cloudflare.com](https://dash.cloudflare.com)
2. Click **"+ Add a Site"**
3. Enter your domain (e.g., `smartgarbage.in`)
4. Select the **Free** plan
5. Click **"Continue"**

```
┌─────────────────────────────────────────────────────┐
│  Add a site to Cloudflare                           │
│                                                     │
│  Enter your site:                                   │
│  ┌───────────────────────────────────────────┐      │
│  │ smartgarbage.in                           │      │
│  └───────────────────────────────────────────┘      │
│                                                     │
│  Plan:  ○ Pro ($20/mo)                              │
│         ○ Business ($200/mo)                        │
│         ● Free ($0)              ← Select this      │
│                                                     │
│                            [Continue]               │
└─────────────────────────────────────────────────────┘
```

---

## Step 3: Change Nameservers

Cloudflare will give you **two nameservers**. You need to update your domain's nameservers.

### What Cloudflare Shows You:

```
┌─────────────────────────────────────────────────────┐
│  ⚠️ Change your nameservers at smartgarbage.in       │
│                                                     │
│  Delete these nameservers:                          │
│    ns1.old-registrar.com                            │
│    ns2.old-registrar.com                            │
│                                                     │
│  Use these Cloudflare nameservers:                  │
│    ◉ ada.ns.cloudflare.com                          │
│    ◉ bob.ns.cloudflare.com                          │
│                                                     │
│  [Copy] [I've updated my nameservers]               │
└─────────────────────────────────────────────────────┘
```

### How to Update (at your registrar):

1. Log in to your domain registrar (GoDaddy, Namecheap, Cloudflare, etc.)
2. Go to **DNS Settings** or **Nameserver Management**
3. Replace existing nameservers with Cloudflare's
4. Save changes

> **Propagation time:** 24–48 hours (usually <1 hour). You'll get an email from Cloudflare when active.

---

## Step 4: Add DNS Records

Once nameservers propagate, add these DNS records in Cloudflare:

1. Go to **DNS** → **Records** → **Add Record**

```
┌─────────────────────────────────────────────────────────────────┐
│  DNS Management for smartgarbage.in                             │
│                                                                 │
│  Type    Name    Content                    Proxy   TTL         │
│  ─────   ────    ───────                    ─────   ───         │
│  CNAME   @       smartgarbage.onrender.com   🟠 ON   Auto        │
│  CNAME   www     smartgarbage.onrender.com   🟠 ON   Auto        │
│                                                                 │
│  🟠 = Proxied (orange cloud) — traffic goes through Cloudflare  │
│  ⚪ = DNS only (grey cloud) — traffic goes direct to Render     │
└─────────────────────────────────────────────────────────────────┘
```

### Record Details:

| Type | Name | Content | Proxy | Notes |
|---|---|---|---|---|
| **CNAME** | `@` | `smartgarbage.onrender.com` | 🟠 **ON** | Root domain |
| **CNAME** | `www` | `smartgarbage.onrender.com` | 🟠 **ON** | www subdomain |

> **Critical:** The proxy must be **ON** (orange cloud) for CDN caching to work.
> If it's OFF (grey cloud), traffic bypasses Cloudflare entirely.

---

## Step 5: Configure SSL/TLS

1. Go to **SSL/TLS** → **Overview**
2. Set encryption mode to **"Full (Strict)"**

```
┌─────────────────────────────────────────────────────┐
│  SSL/TLS encryption mode                            │
│                                                     │
│  ○ Off (not secure)                                 │
│  ○ Flexible    — encrypts browser↔Cloudflare only   │
│  ● Full (Strict) — encrypts browser↔Cloudflare     │
│                     AND Cloudflare↔Render ← SELECT  │
│                                                     │
│  Full (Strict) requires a valid SSL certificate     │
│  on Render (which you already have).                │
└─────────────────────────────────────────────────────┘
```

3. Enable **"Always Use HTTPS"**:
   - Go to **SSL/TLS** → **Edge Certificates**
   - Toggle **"Always Use HTTPS"** → ON

4. Enable **"Automatic HTTPS Rewrites"**:
   - Same page, toggle **"Automatic HTTPS Rewrites"** → ON

---

## Step 6: Create Page Rules for Caching

This is the most important step — it tells Cloudflare to cache HTML pages.

1. Go to **Rules** → **Page Rules** → **Create Page Rule**

### Rule 1: Cache HTML Pages (Most Important)

```
┌─────────────────────────────────────────────────────────────────┐
│  Create a Page Rule                                             │
│                                                                 │
│  URL pattern:                                                   │
│  ┌───────────────────────────────────────────────────────┐      │
│  │ *smartgarbage.in/*                                    │      │
│  └───────────────────────────────────────────────────────┘      │
│                                                                 │
│  Settings:                                                      │
│  ┌───────────────────────────────────────────────────────┐      │
│  │ Cache Level          → Cache Everything               │      │
│  │ Edge Cache TTL       → 2 hours                        │      │
│  │ Browser Cache TTL    → Respect Existing Headers       │      │
│  └───────────────────────────────────────────────────────┘      │
│                                                                 │
│                              [Save and Deploy]                  │
└─────────────────────────────────────────────────────────────────┘
```

### Rule 2: Bypass Cache for Dynamic Routes

Create a second rule for routes that must never be cached:

```
┌─────────────────────────────────────────────────────────────────┐
│  Create a Page Rule                                             │
│                                                                 │
│  URL pattern:                                                   │
│  ┌───────────────────────────────────────────────────────┐      │
│  │ *smartgarbage.in/(admin|login|register|report|        │      │
│  │   api/*|contact|webhook/*)                            │      │
│  └───────────────────────────────────────────────────────┘      │
│                                                                 │
│  Settings:                                                      │
│  ┌───────────────────────────────────────────────────────┐      │
│  │ Cache Level          → Bypass                         │      │
│  └───────────────────────────────────────────────────────┘      │
│                                                                 │
│                              [Save and Deploy]                  │
└─────────────────────────────────────────────────────────────────┘
```

> **Free plan limit:** 3 Page Rules. You've used 2. Keep the 3rd for future use.

---

## Step 7: Enable Performance Features

### 7.1 Enable Brotli Compression

1. Go to **Speed** → **Optimization** → **Content Optimization**
2. Toggle **"Brotli"** → ON

### 7.2 Enable HTTP/3 (QUIC)

1. Go to **Speed** → **Optimization** → **Content Optimization**
2. Toggle **"HTTP/3 (QUIC)"** → ON

### 7.3 Enable Early Hints

1. Same page, toggle **"103 Early Hints"** → ON

### 7.4 Enable Auto Minify (if not already done by app)

1. Go to **Speed** → **Optimization** → **Content Optimization**
2. Check: **JavaScript**, **CSS**, **HTML** → all ON
3. (The app already minifies, but Cloudflare catches any misses)

```
┌─────────────────────────────────────────────────────┐
│  Content Optimization                               │
│                                                     │
│  Brotli compression     [██████████] ON             │
│  HTTP/3 (QUIC)          [██████████] ON             │
│  103 Early Hints        [██████████] ON             │
│  Auto Minify                                        │
│    ☑ JavaScript         ☑ CSS          ☑ HTML       │
└─────────────────────────────────────────────────────┘
```

---

## Step 8: Configure Cache Rules (Newer Method)

Cloudflare's newer **Cache Rules** override Page Rules. Use these for finer control:

1. Go to **Rules** → **Cache Rules** → **Create Rule**

### Rule: Cache Static Assets at Edge

```
┌─────────────────────────────────────────────────────────────────┐
│  Cache Rule: Static Assets                                      │
│                                                                 │
│  Rule name: Cache static assets at edge                         │
│                                                                 │
│  When incoming requests match:                                   │
│  ┌───────────────────────────────────────────────────────┐      │
│  │ (http.request.uri.path matches "^/static/.*")         │      │
│  └───────────────────────────────────────────────────────┘      │
│                                                                 │
│  Then:                                                          │
│  ┌───────────────────────────────────────────────────────┐      │
│  │ Cache eligibility   → Eligible for cache              │      │
│  │ Edge TTL            → Override: 2592000 (30 days)     │      │
│  │ Browser TTL         → Override: 31536000 (1 year)     │      │
│  └───────────────────────────────────────────────────────┘      │
│                                                                 │
│                              [Deploy]                           │
└─────────────────────────────────────────────────────────────────┘
```

### Rule: Cache HTML Pages at Edge

```
┌─────────────────────────────────────────────────────────────────┐
│  Cache Rule: HTML Pages                                         │
│                                                                 │
│  Rule name: Cache homepage and content pages                    │
│                                                                 │
│  When incoming requests match:                                   │
│  ┌───────────────────────────────────────────────────────┐      │
│  │ (http.request.uri.path eq "/") or                      │      │
│  │ (http.request.uri.path in {"/schedule" "/about"        │      │
│  │   "/terms" "/privacy" "/faq" "/transparency"           │      │
│  │   "/report-illegal"})                                  │      │
│  └───────────────────────────────────────────────────────┘      │
│                                                                 │
│  Then:                                                          │
│  ┌───────────────────────────────────────────────────────┐      │
│  │ Cache eligibility   → Eligible for cache              │      │
│  │ Edge TTL            → Override: 300 (5 minutes)       │      │
│  │ Browser TTL         → Override: 300 (5 minutes)       │      │
│  └───────────────────────────────────────────────────────┘      │
│                                                                 │
│                              [Deploy]                           │
└─────────────────────────────────────────────────────────────────┘
```

### Rule: Never Cache Authenticated/Dynamic Routes

```
┌─────────────────────────────────────────────────────────────────┐
│  Cache Rule: Bypass dynamic routes                              │
│                                                                 │
│  Rule name: Bypass cache for dynamic routes                     │
│                                                                 │
│  When incoming requests match:                                   │
│  ┌───────────────────────────────────────────────────────┐      │
│  │ (http.request.uri.path contains "/admin") or           │      │
│  │ (http.request.uri.path contains "/login") or           │      │
│  │ (http.request.uri.path contains "/register") or        │      │
│  │ (http.request.uri.path contains "/report") or          │      │
│  │ (http.request.uri.path contains "/api/") or            │      │
│  │ (http.request.uri.path contains "/contact") or         │      │
│  │ (http.request.uri.path contains "/webhook/") or        │      │
│  │ (http.request.uri.path contains "/dashboard") or       │      │
│  │ (http.request.uri.path contains "/set-lang")           │      │
│  └───────────────────────────────────────────────────────┘      │
│                                                                 │
│  Then:                                                          │
│  ┌───────────────────────────────────────────────────────┐      │
│  │ Cache eligibility   → Bypass cache                    │      │
│  └───────────────────────────────────────────────────────┘      │
│                                                                 │
│                              [Deploy]                           │
└─────────────────────────────────────────────────────────────────┘
```

---

## Step 9: Add Custom Domain to Render

Now tell Render about your new domain so it accepts traffic:

1. Go to [render.com](https://render.com) → Dashboard
2. Select your **smartgarbage** web service
3. Go to **Settings** → **Custom Domains**
4. Click **"Add Custom Domain"**
5. Enter your domain (e.g., `smartgarbage.in`)
6. Render will show you a CNAME record to add

```
┌─────────────────────────────────────────────────────┐
│  Custom Domains                                     │
│                                                     │
│  ┌─────────────────────────────────────────────┐    │
│  │ smartgarbage.in                             │    │
│  │ Status: ✓ SSL certificate issued            │    │
│  │ DNS: CNAME → smartgarbage.onrender.com      │    │
│  └─────────────────────────────────────────────┘    │
│                                                     │
│  [Add Custom Domain]                                │
└─────────────────────────────────────────────────────┘
```

> **Note:** Since Cloudflare is proxying, the CNAME record is already set.
> Render just needs to know about the domain for SSL certificate provisioning.

---

## Step 10: Update Application Settings

Update the app to use the new domain:

### 10.1 Update RENDER_EXTERNAL_URL

In Render Dashboard → Environment:

```
RENDER_EXTERNAL_URL=https://smartgarbage.in
```

### 10.2 Update Canonical URLs

The app auto-detects the domain from `request.host`, so canonical URLs
and Open Graph tags will update automatically.

### 10.3 Update Sitemap

The sitemap already uses `_external=True` in URL generation, so it will
automatically use the new domain.

---

## Step 11: Test the Setup

### 11.1 Verify Cloudflare is Active

```bash
# Check for cf-ray header (proves traffic goes through Cloudflare)
curl -sI https://smartgarbage.in/ | grep -i "cf-ray"
```

Expected output:
```
cf-ray: 8a1b2c3d4e5f6789-DEL
```

### 11.2 Check Cache Status

```bash
# First request (should be MISS — cached on first hit)
curl -sI https://smartgarbage.in/ | grep -i "cf-cache-status"
# Expected: cf-cache-status: MISS

# Second request (should be HIT — served from edge)
curl -sI https://smartgarbage.in/ | grep -i "cf-cache-status"
# Expected: cf-cache-status: HIT
```

### 11.3 Measure TTFB Improvement

```bash
# Before Cloudflare (direct to Render)
echo "=== Direct TTFB (before) ==="
curl -s -o /dev/null -w "TTFB: %{time_starttransfer}s\n" \
  https://smartgarbage.onrender.com/

# After Cloudflare (first visit — cold edge)
echo "=== Cloudflare TTFB (first visit) ==="
curl -s -o /dev/null -w "TTFB: %{time_starttransfer}s\n" \
  https://smartgarbage.in/

# After Cloudflare (repeat visit — edge cached)
echo "=== Cloudflare TTFB (repeat) ==="
curl -s -o /dev/null -w "TTFB: %{time_starttransfer}s\n" \
  https://smartgarbage.in/

# After Cloudflare (static assets)
echo "=== Static CSS TTFB ==="
curl -sI https://smartgarbage.in/static/style.css | grep -i "cf-cache-status"
```

Expected results:

```
=== Direct TTFB (before) ===
TTFB: 1.2s

=== Cloudflare TTFB (first visit) ===
TTFB: 0.15s

=== Cloudflare TTFB (repeat) ===
TTFB: 0.02s

=== Static CSS ===
cf-cache-status: HIT
```

### 11.4 Check Compressed Size

```bash
# Check Brotli compression at Cloudflare edge
curl -sI -H "Accept-Encoding: br" https://smartgarbage.in/ | grep -i "content-encoding"
# Expected: content-encoding: br

# Check content size
curl -sI -H "Accept-Encoding: br" https://smartgarbage.in/ | grep -i "content-length"
# Expected: ~12KB (compressed from 58KB HTML)
```

### 11.5 Verify SSL

```bash
# Check SSL certificate details
curl -sI https://smartgarbage.in/ | grep -i "strict-transport"
# Expected: strict-transport-security: max-age=31536000; includeSubDomains; preload
```

---

## Step 12: Configure WAF (Optional — Free)

Add basic security rules:

1. Go to **Security** → **WAF** → **Custom Rules**

### Rule: Block Bot Traffic

```
┌─────────────────────────────────────────────────────────────────┐
│  WAF Rule: Block bad bots                                       │
│                                                                 │
│  Rule name: Block known bad bots                                │
│                                                                 │
│  When incoming requests match:                                   │
│  ┌───────────────────────────────────────────────────────┐      │
│  │ (http.user_agent contains "sqlmap") or                 │      │
│  │ (http.user_agent contains "nikto") or                  │      │
│  │ (http.user_agent contains "masscan") or                │      │
│  │ (http.user_agent contains "nmap")                      │      │
│  └───────────────────────────────────────────────────────┘      │
│                                                                 │
│  Then:                                                          │
│  ┌───────────────────────────────────────────────────────┐      │
│  │ Action → Block                                        │      │
│  └───────────────────────────────────────────────────────┘      │
│                                                                 │
│                              [Deploy]                           │
└─────────────────────────────────────────────────────────────────┘
```

### Rule: Rate Limit Login Attempts

1. Go to **Security** → **WAF** → **Rate Limiting Rules**
2. Create rule:

```
┌─────────────────────────────────────────────────────────────────┐
│  Rate Limiting Rule                                             │
│                                                                 │
│  Rule name: Rate limit login attempts                           │
│                                                                 │
│  When incoming requests match:                                   │
│  ┌───────────────────────────────────────────────────────┐      │
│  │ (http.request.uri.path eq "/login") and                │      │
│  │ (http.request.method eq "POST")                        │      │
│  └───────────────────────────────────────────────────────┘      │
│                                                                 │
│  Then:                                                          │
│  ┌───────────────────────────────────────────────────────┐      │
│  │ Perform action → Block                                 │      │
│  │ Duration      → 600 seconds (10 minutes)               │      │
│  │ Requests      → 5 requests per 10 minutes              │      │
│  └───────────────────────────────────────────────────────┘      │
│                                                                 │
│                              [Deploy]                           │
└─────────────────────────────────────────────────────────────────┘
```

---

## Step 13: Set Up Monitoring

### 13.1 Enable Cloudflare Analytics

1. Go to **Analytics & Logs** → **HTTP Analytics**
2. Monitor: Cache hit ratio, bandwidth saved, threat score

### 13.2 Set Up Cache Purge Alerts

1. Go to **Notifications** → **Add Notification**
2. Select **"Cache Purge"** → get notified when cache is purged

### 13.3 Monitor Cache Hit Ratio

Target: **>80%** cache hit ratio for static assets, **>50%** for HTML pages.

```
┌─────────────────────────────────────────────────────┐
│  Analytics Overview                                 │
│                                                     │
│  Cache Hit Ratio:  ████████████████░░░░ 82%         │
│  Bandwidth Saved:  4.2 GB (from 5.1 GB total)       │
│  Threats Blocked:  12                               │
│  Requests:         1.2M (last 24 hours)             │
└─────────────────────────────────────────────────────┘
```

---

## Troubleshooting

### Issue: "Too many redirects" (ERR_TOO_MANY_REDIRECTS)

**Cause:** SSL set to "Flexible" but Render redirects HTTP→HTTPS.
**Fix:** Change SSL to **"Full (Strict)"** in Cloudflare dashboard.

### Issue: Content not caching (cf-cache-status: DYNAMIC)

**Cause:** Flask sends `Vary: Cookie` which prevents caching.
**Fix:** The app already strips `Vary: Cookie` for static assets. For HTML,
the `Cache-Control: public, max-age=300` header should override.

If still not caching, add a Cache Rule:
```
(http.request.uri.path eq "/") and (http.cookie eq "")
→ Cache Level: Cache Everything
→ Edge TTL: 300
```

### Issue: robots.txt blocked on custom domain

**Cause:** Cloudflare might cache the wrong robots.txt.
**Fix:** Add a Cache Rule:
```
(http.request.uri.path eq "/robots.txt")
→ Cache Level: Bypass
```

### Issue: Render shows wrong IP (not Cloudflare)

**Cause:** Render's `ProxyFix` middleware reads `X-Forwarded-For`.
**Fix:** Cloudflare adds this header automatically. No code changes needed.

### Issue: WebSocket connections failing

**Cause:** Cloudflare Free plan doesn't support WebSockets by default.
**Fix:** Go to **Network** → **WebSockets** → Toggle ON.

---

## Expected Results

After setup, your site should achieve:

| Metric | Before | After | Improvement |
|---|---|---|---|
| **Cold TTFB** | 1.2s | **<100ms** | **12x faster** |
| **Repeat TTFB** | <10ms | **<10ms** | Same |
| **Static asset delivery** | From Oregon | **From nearest edge** | **Global** |
| **Brotli compression** | 13KB | **12KB** | -8% |
| **DDoS protection** | None | **Unlimited free** | ✅ |
| **SSL** | Render-managed | **Cloudflare edge** | ✅ |
| **HTTP/3** | Render-managed | **Cloudflare edge** | ✅ |
| **Bot protection** | None | **WAF rules** | ✅ |

---

## Quick Reference Card

```
┌─────────────────────────────────────────────────────────────────┐
│  SmartGarbage Cloudflare CDN — Quick Reference                  │
│                                                                 │
│  Domain:        smartgarbage.in (or your chosen domain)         │
│  Origin:        smartgarbage.onrender.com                       │
│  Plan:          Free                                            │
│  SSL:           Full (Strict)                                   │
│  Proxy:         ON (orange cloud)                               │
│                                                                 │
│  Cache Rules:                                                   │
│    HTML pages:     Edge TTL 300s, Browser TTL 300s              │
│    Static assets:  Edge TTL 30 days, Browser TTL 1 year         │
│    Dynamic routes: Bypass cache                                 │
│                                                                 │
│  Features Enabled:                                              │
│    ✅ Brotli compression                                        │
│    ✅ HTTP/3 (QUIC)                                             │
│    ✅ 103 Early Hints                                           │
│    ✅ Always Use HTTPS                                          │
│    ✅ Auto Minify (JS, CSS, HTML)                               │
│    ✅ WebSockets                                                │
│                                                                 │
│  Monitoring:                                                    │
│    Dashboard: dash.cloudflare.com/analytics                     │
│    Cache status: curl -sI URL | grep cf-cache-status            │
│    TTFB: curl -s -o /dev/null -w "%{time_starttransfer}" URL   │
└─────────────────────────────────────────────────────────────────┘
```

---

## Cost Summary

| Item | Cost |
|---|---|
| Cloudflare Free plan | ₹0 |
| Cloudflare Registrar (.in domain) | ~₹649/year |
| Domain privacy protection | Included free |
| SSL certificate | Included free |
| DDoS protection | Included free |
| CDN bandwidth | Unlimited free |
| **Total** | **~₹649/year (~$8/year)** |

> Compare: Render Starter plan alone costs $7/month ($84/year).
> Cloudflare adds CDN, DDoS, WAF, and edge caching for just $8/year.
