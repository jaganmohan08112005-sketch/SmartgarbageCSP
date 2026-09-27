# ⚡ Cloudflare Cache Rules — 5-Minute Quick Start

> **Goal:** Reduce TTFB from 1.2s → <100ms by caching HTML at Cloudflare's edge.

## Prerequisites (Already Done ✅)

The Flask app already:
- Strips `Vary: Cookie` from all public responses (WSGI middleware)
- Sets `Cache-Control: public, max-age=60, s-maxage=300` for HTML
- Sets `Cache-Control: public, max-age=31536000, immutable` for static assets

**You just need to tell Cloudflare to actually cache them.**

---

## Step 1: Open Cloudflare

1. Go to **https://dash.cloudflare.com**
2. Select your domain

## Step 2: Create Rule 1 — Cache HTML

1. Left sidebar → **Caching** → **Cache Rules**
2. Click **Create rule**
3. Paste these exact values:

| Field | Value |
|-------|-------|
| **Rule name** | `Cache public HTML` |
| **When** | `Hostname` `equals` `smartgarbage.onrender.com` |
| **+ And** | `URI Path` `does not start with` `/static/` |
| **+ And** | `URI Path` `does not start with` `/admin/` |
| **+ And** | `URI Path` `does not start with` `/login` |
| **+ And** | `URI Path` `does not start with` `/register` |
| **+ And** | `URI Path` `does not start with` `/dashboard/` |
| **Then → Cache eligibility** | `Eligible for cache` |
| **Edge TTL** | `Override` → `300` seconds (5 min) |
| **Browser TTL** | `Override` → `60` seconds (1 min) |

4. Click **Deploy**

## Step 3: Create Rule 2 — Cache Static Assets

1. Click **Create rule** again
2. Paste these exact values:

| Field | Value |
|-------|-------|
| **Rule name** | `Cache static assets` |
| **When** | `Hostname` `equals` `smartgarbage.onrender.com` |
| **+ And** | `URI Path` `starts with` `/static/` |
| **Then → Cache eligibility** | `Eligible for cache` |
| **Edge TTL** | `Override` → `2592000` seconds (30 days) |
| **Browser TTL** | `Override` → `31536000` seconds (1 year) |

3. Click **Deploy**

## Step 4: Create Rule 3 — Bypass Dynamic Routes

1. Click **Create rule** again
2. Paste these exact values:

| Field | Value |
|-------|-------|
| **Rule name** | `Bypass dynamic routes` |
| **When** | `Hostname` `equals` `smartgarbage.onrender.com` |
| **+ And** | `URI Path` `starts with` `/login` |
| **+ Or** | `URI Path` `starts with` `/register` |
| **+ Or** | `URI Path` `starts with` `/admin/` |
| **+ Or** | `URI Path` `starts with` `/dashboard/` |
| **Then → Cache eligibility** | `Bypass cache` |

3. Click **Deploy**

---

## Step 5: Verify (2 minutes later)

Open terminal and run:

```bash
# Check if caching is active
curl -sI https://smartgarbage.onrender.com/ | grep -i "cf-cache-status"
# First request: MISS (cache populated)
# Second request: HIT (served from edge)

# Check TTFB
curl -o /dev/null -s -w "TTFB: %{time_starttransfer}s\n" https://smartgarbage.onrender.com/
# Should show: TTFB: 0.0Xs (under 100ms)

# Check Vary header (should NOT have Cookie)
curl -sI https://smartgarbage.onrender.com/ | grep -i vary
# Should show: Vary: Accept-Encoding
```

---

## Expected Results

| Metric | Before | After |
|--------|--------|-------|
| TTFB | 1.2s | **<100ms** |
| cf-cache-status | DYNAMIC | **HIT** |
| Cache hit ratio | 0% | **~85%** |

---

## Troubleshooting

**Still DYNAMIC?**
→ Purge cache: Caching → Configuration → Purge Everything → Purge

**TTFB still high?**
→ Check Rules are toggled ON (green switch)
→ Wait 2 minutes after creating rules

**Pages look broken after caching?**
→ Add `/report` to the bypass rule (dynamic form page)
