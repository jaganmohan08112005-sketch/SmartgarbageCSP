# Cloudflare Edge Caching — Setup Guide

## Why This Matters

Your site already runs behind Cloudflare (`Server: cloudflare`), but HTML pages show `cf-cache-status: DYNAMIC` — meaning Cloudflare passes every request to Render's origin server (~0.80s TTFB). After this config, Cloudflare will serve cached HTML from 300+ edge locations worldwide (**<100ms TTFB**).

## What Changed (App-Side) ✅ DONE

The Flask app now has **three layers** of `Vary: Cookie` removal:

| Layer | How It Works | Status |
|-------|-------------|--------|
| **1. Session interface override** | `_StaticNoVarySessionInterface.save_session()` strips `Cookie` after `super().save_session()` adds it | ✅ Deployed |
| **2. after_request hook** | `strip_vary_cookie()` strips `Cookie` as a belt-and-suspenders backup | ✅ Deployed |
| **3. WSGI middleware** | `_StripVaryCookieMiddleware` strips `Cookie` at the lowest level — after Flask has finished everything | ✅ Deployed |

Additionally:
- `s-maxage=300` tells Cloudflare to cache HTML for 5 minutes
- `max-age=60` for browser cache (shorter, so users see updates faster)
- Static assets get `max-age=31536000, immutable` (1 year)

**You don't need to change any code.** Just configure Cloudflare's dashboard.

---

## Step-by-Step: Cloudflare Dashboard Setup (5 minutes)

### Step 1: Log in to Cloudflare
1. Open: **https://dash.cloudflare.com**
2. Log in with your Cloudflare account

### Step 2: Select Your Domain
1. Click on your domain (the one pointing to smartgarbage.onrender.com)

### Step 3: Create Cache Rule for HTML Pages
1. Go to **Caching** → **Cache Rules** (left sidebar)
2. Click **Create rule**
3. Fill in:

**Rule name:** `Cache public HTML pages`

**When (Field → Operator → Value):**
```
Hostname    equals    smartgarbage.onrender.com
```

**And (click "+ And"):**
```
URI Path    does not start with    /static/
```

**And (click "+ And"):**
```
URI Path    does not start with    /admin/
```

**And (click "+ And"):**
```
URI Path    does not start with    /login
```

**And (click "+ And"):**
```
URI Path    does not start with    /register
```

**And (click "+ And"):**
```
URI Path    does not start with    /dashboard/
```

**Then:**
```
Cache eligibility:  Eligible for cache
Edge TTL:           Override → 5 minutes (300 seconds)
Browser TTL:        Override → 1 minute (60 seconds)
```

4. Click **Deploy**

### Step 4: Create Cache Rule for Static Assets
1. Click **Create rule** again
2. Fill in:

**Rule name:** `Cache static assets permanently`

**When:**
```
Hostname    equals    smartgarbage.onrender.com
AND
URI Path    starts with    /static/
```

**Then:**
```
Cache eligibility:  Eligible for cache
Edge TTL:           Override → 1 month (2,592,000 seconds)
Browser TTL:        Override → 1 year (31,536,000 seconds)
```

3. Click **Deploy**

### Step 5: Create Bypass Rule for Dynamic Routes
1. Click **Create rule** again
2. Fill in:

**Rule name:** `Bypass cache for login/register`

**When:**
```
Hostname    equals    smartgarbage.onrender.com
AND
URI Path    starts with    /login
OR
URI Path    starts with    /register
OR
URI Path    starts with    /admin/
OR
URI Path    starts with    /dashboard/
```

**Then:**
```
Cache eligibility:  Bypass cache
```

3. Click **Deploy**

---

## Verification

After configuring, wait 1-2 minutes then test:

```bash
# Check if Cloudflare is caching HTML
curl -sI https://smartgarbage.onrender.com/ | grep -i "cf-cache-status"
# Should show: cf-cache-status: MISS (first request) or HIT (subsequent)

# Check Vary header (should NOT contain Cookie)
curl -sI https://smartgarbage.onrender.com/ | grep -i "vary"
# Should show: vary: Accept-Encoding (no Cookie)

# Check TTFB
curl -o /dev/null -s -w "TTFB: %{time_starttransfer}s\n" https://smartgarbage.onrender.com/
# Should show: TTFB: 0.0Xs (under 100ms on cache hit)
```

---

## What to Expect

| Metric | Before | After |
|--------|--------|-------|
| **cf-cache-status** | DYNAMIC | **HIT** (after first request) |
| **Vary header** | Accept-Encoding, Cookie | **Accept-Encoding** (no Cookie) |
| **TTFB (cold)** | 0.80s | **<100ms** |
| **TTFB (warm)** | 0.80s | **<10ms** |
| **Cache hit ratio** | 0% | **~85%** |

---

## Troubleshooting

### If cf-cache-status is still DYNAMIC:
1. Check that `Vary: Cookie` is NOT in the response: `curl -sI https://smartgarbage.onrender.com/ | grep -i vary`
2. Should only show: `Vary: Accept-Encoding`
3. If Cookie is still there, the WSGI middleware hasn't deployed yet — wait for Render to redeploy
4. Try: **Caching** → **Configuration** → **Purge Everything**

### If TTFB is still high:
1. Check Cloudflare cache hit ratio: **Caching** → **Configuration** → **Cache Analytics**
2. Make sure the Cache Rules are deployed and active (green toggle)
3. Try purging cache and testing again

### If logged-in pages are cached (security issue):
1. The bypass rule should prevent this
2. Flask's `Cache-Control: no-store` for logged-in users also prevents caching
3. The WSGI middleware only strips `Vary: Cookie` from responses WITHOUT `Set-Cookie`

---

## Cost: ₹0 (Free Cloudflare Plan)

The free Cloudflare plan includes:
- ✅ Unlimited bandwidth
- ✅ 3 Cache Rules (we use 3)
- ✅ Cache Everything (via Cache Rules)
- ✅ Brotli compression
- ✅ DDoS protection
- ✅ Free SSL
