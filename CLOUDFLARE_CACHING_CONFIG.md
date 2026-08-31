# Cloudflare Edge Caching Configuration

## Why This Matters

Your site already runs behind Cloudflare (`Server: cloudflare` header), but HTML pages show `cf-cache-status: DYNAMIC` — meaning Cloudflare passes every request to Render's origin server (0.94s TTFB). After this config, Cloudflare will serve cached HTML from 300+ edge locations worldwide (<100ms TTFB).

## What Changed (App-Side)

The Flask app now:
1. **Strips `Vary: Cookie`** from public HTML pages (logged-out users) — this was preventing Cloudflare from caching
2. **Sets `s-maxage=300`** — tells Cloudflare to cache HTML for 5 minutes at the edge
3. **Keeps `max-age=60`** — browser cache for 1 minute (shorter, so users see updates faster)

## Step-by-Step: Cloudflare Dashboard Setup

### Step 1: Log in to Cloudflare
1. Go to: https://dash.cloudflare.com
2. Log in with your Cloudflare account

### Step 2: Select Your Domain
1. Click on your domain (the one pointing to smartgarbage.onrender.com)

### Step 3: Create a Cache Rule (Recommended Method)
1. Go to **Caching** → **Cache Rules** (left sidebar)
2. Click **Create rule**
3. Configure:

```
Rule name: Cache public HTML pages
When: Hostname equals smartgarbage.onrender.com
      AND URI Path does not start with /static/
      AND URI Path does not start with /api/
      AND URI Path does not start with /admin/
      AND URI Path does not start with /dashboard/
      AND URI Path does not start with /login
      AND URI Path does not start with /register
      AND URI Path does not start with /logout
Then: Cache eligibility = Eligible for cache
      Edge TTL = Override = 5 minutes (300 seconds)
      Browser TTL = Override = 1 minute (60 seconds)
```

4. Click **Deploy**

### Step 4: Create a Static Assets Rule
1. Click **Create rule** again
2. Configure:

```
Rule name: Cache static assets permanently
When: Hostname equals smartgarbage.onrender.com
      AND URI Path starts with /static/
Then: Cache eligibility = Eligible for cache
      Edge TTL = Override = 1 month (2,592,000 seconds)
      Browser TTL = Override = 1 year (31,536,000 seconds)
```

3. Click **Deploy**

### Step 5: Create a Bypass Rule for Dynamic Routes
1. Click **Create rule** again
2. Configure:

```
Rule name: Bypass cache for dynamic routes
When: Hostname equals smartgarbage.onrender.com
      AND URI Path starts with /admin/
      OR URI Path starts with /dashboard/
      OR URI Path starts with /api/
      OR URI Path starts with /report
      OR URI Path starts with /login
      OR URI Path starts with /register
Then: Cache eligibility = Bypass cache
```

3. Click **Deploy**

### Step 6: Enable Development Mode (Optional - for testing)
1. Go to **Caching** → **Configuration**
2. Toggle **Development Mode** ON (this bypasses cache for 3 hours)
3. Test your site: `curl -I https://smartgarbage.onrender.com/`
4. You should see: `cf-cache-status: HIT` (instead of DYNAMIC)
5. Turn Development Mode OFF when done testing

### Step 7: Purge Cache After Deploy
1. Go to **Caching** → **Configuration**
2. Click **Purge Everything** (safe — your site regenerates quickly)
3. Or use **Custom Purge** to purge specific URLs

## Verification

After configuring, test with:

```bash
# Check if Cloudflare is caching HTML
curl -sI https://smartgarbage.onrender.com/ | grep -i "cf-cache-status"
# Should show: cf-cache-status: MISS (first request) or HIT (subsequent)

# Check TTFB
curl -o /dev/null -s -w "TTFB: %{time_starttransfer}s\n" https://smartgarbage.onrender.com/
# Should show: TTFB: 0.0Xs (under 100ms on cache hit)
```

## What to Expect

| Metric | Before | After |
|--------|--------|-------|
| **cf-cache-status** | DYNAMIC | HIT (after first request) |
| **TTFB (cold)** | 0.94s | <100ms |
| **TTFB (warm)** | 0.94s | <10ms |
| **Cache hit ratio** | 0% | ~85% |

## Troubleshooting

### If cf-cache-status is still DYNAMIC:
1. Check that `Vary: Cookie` is NOT in the response headers
2. Run: `curl -sI https://smartgarbage.onrender.com/ | grep -i vary`
3. Should only show: `Vary: Accept-Encoding` (no Cookie)
4. If Cookie is still there, the app update hasn't deployed yet — wait for Render to redeploy

### If TTFB is still high:
1. Check Cloudflare cache hit ratio in **Caching** → **Configuration** → **Cache Analytics**
2. Make sure the Cache Rule is deployed and active
3. Try purging cache and testing again

### If logged-in pages are cached (security issue):
1. The bypass rule should prevent this
2. Check that `/admin/`, `/dashboard/`, `/login`, `/register` are in the bypass rule
3. Flask's `Cache-Control: no-store` for logged-in users also prevents caching

## Cost: ₹0 (Free Cloudflare Plan)

The free Cloudflare plan includes:
- ✅ Unlimited bandwidth
- ✅ 3 Page Rules (we use 3)
- ✅ Cache Everything (via Cache Rules)
- ✅ Brotli compression
- ✅ DDoS protection
- ✅ Free SSL
