# Cloudflare Setup Guide — SmartGarbage eu.org

**When to use this guide:** After `smartgarbage.eu.org` resolves on DNS (eu.org approved).

**Time required:** 10 minutes

**Result:** TTFB drops from ~0.7s to <0.1s

---

## Step 0: Verify Domain Is Approved

Run this in your terminal:

```bash
nslookup smartgarbage.eu.org 8.8.8.8
```

**If it shows an IP address → proceed.**
**If it shows "Non-existent domain" → eu.org hasn't approved yet. Wait.**

---

## Step 1: Add Domain to Cloudflare

1. Go to **https://dash.cloudflare.com**
2. Click **"Add a Site"** (top right)
3. Enter: `smartgarbage.eu.org`
4. Click **"Continue"**
5. Select **"Free"** plan → Click **"Continue"**
6. Cloudflare scans existing DNS records → Click **"Continue"**
7. Cloudflare shows 2 nameservers (e.g., `anna.ns.cloudflare.com`, `bob.ns.cloudflare.com`)
8. **⚠️ DO NOT change nameservers at eu.org** — keep HE's NS for eu.org to work
9. Click **"Continue"** (skip nameserver change)

---

## Step 2: Add CNAME Record

1. In Cloudflare Dashboard → Click **"DNS"** in left sidebar
2. Click **"Records"** tab
3. Click **"Add Record"**
4. Fill in:

| Field | Value |
|-------|-------|
| **Type** | `CNAME` |
| **Name** | `@` |
| **Target** | `smartgarbage.onrender.com` |
| **Proxy status** | **Proxied** (orange cloud ON) |
| **TTL** | Auto |

5. Click **"Save"**
6. Add another record for `www`:

| Field | Value |
|-------|-------|
| **Type** | `CNAME` |
| **Name** | `www` |
| **Target** | `smartgarbage.eu.org` |
| **Proxy status** | **Proxied** (orange cloud ON) |
| **TTL** | Auto |

7. Click **"Save"**

You should now see:

```
Type    Name    Content                     Proxy Status
CNAME   @       smartgarbage.onrender.com   Proxied (orange)
CNAME   www     smartgarbage.eu.org         Proxied (orange)
```

---

## Step 3: Create Page Rule for HTML Caching

This is the **most important step** — it enables edge caching for HTML pages.

1. In Cloudflare Dashboard → Click **"Rules"** in left sidebar
2. Click **"Page Rules"** tab
3. Click **"Create Page Rule"**
4. Fill in:

| Field | Value |
|-------|-------|
| **URL (matches)** | `*smartgarbage.eu.org/*` |
| **Setting** | **Cache Level** |
| **Value** | **Cache Everything** |

5. Click **"Save and Deploy"**

**That's it.** Cloudflare will now cache all HTML responses at the edge for 5 minutes.

---

## Step 4: Add Custom Domain in Render

1. Go to **https://dashboard.render.com**
2. Click on your **SmartGarbage** service
3. Click **"Settings"** in left sidebar
4. Scroll to **"Custom Domains"** section
5. Click **"Add Custom Domain"**
6. Enter: `smartgarbage.eu.org`
7. Click **"Add"**
8. Render will verify DNS and issue SSL certificate
9. Wait 1-2 minutes for SSL to provision

---

## Step 5: Update Canonical URLs in Code

Once live, update the canonical URL in your templates:

1. Open `app/templates/base.html`
2. Find the canonical URL line:
   ```html
   <link rel="canonical" href="{{ request.base_url }}">
   ```
3. This should auto-update since it uses `request.base_url`
4. But update the Open Graph URL if hardcoded:
   ```html
   <meta property="og:url" content="{{ request.url }}">
   ```
5. Update the manifest.json if needed

---

## Step 6: Verify Everything Works

Run these checks:

### Check 1: DNS Resolution
```bash
nslookup smartgarbage.eu.org 8.8.8.8
```
Should show Cloudflare IPs (104.x.x.x or 172.x.x.x)

### Check 2: HTTPS Access
```bash
curl -I https://smartgarbage.eu.org/
```
Should show:
- HTTP/2 200
- `cf-ray: ...` (Cloudflare header)
- `cf-cache-status: HIT` (after first visit)

### Check 3: TTFB
```bash
curl -so /dev/null -w "TTFB=%{time_starttransfer}s\n" https://smartgarbage.eu.org/
```
Should be **<0.1s** (after cache warms up)

### Check 4: Old Domain Redirect
```bash
curl -I https://smartgarbage.onrender.com/
```
Should still work (backwards compatibility)

---

## Step 7: Set Up Redirect (Optional)

Redirect old `onrender.com` domain to new `eu.org` domain:

1. In Render Dashboard → Settings → Custom Domains
2. Add `smartgarbage.onrender.com` (already there)
3. In Cloudflare → Rules → Redirect Rules
4. Create rule:

| Field | Value |
|-------|-------|
| **When** | Hostname equals `smartgarbage.onrender.com` |
| **Then** | Dynamic redirect to `https://smartgarbage.eu.org${uri}` |
| **Status** | 301 Permanent |

---

## Expected Results

| Metric | Before (onrender.com) | After (eu.org + Cloudflare) |
|--------|----------------------|----------------------------|
| **TTFB (warm)** | 0.68s | **<0.1s** |
| **TTFB (cold)** | 1.83s | **<0.1s** (cached) |
| **vs GOV.UK (0.18s)** | 3.8× slower | **1.8× faster** |
| **SSL** | Render-managed | Cloudflare-managed |
| **DDoS protection** | None | Cloudflare free tier |
| **CDN** | None | 200+ edge locations |
| **HTTP/2** | ✅ | ✅ |
| **Brotli compression** | ✅ | ✅ (edge-level) |

---

## Troubleshooting

### "ERR_NAME_NOT_RESOLVED"
- eu.org hasn't approved yet — wait

### "ERR_TOO_MANY_REDIRECTS"
- Cloudflare SSL mode is wrong → set to "Full (Strict)"

### "502 Bad Gateway"
- Render can't reach your app → check Render dashboard

### cf-cache-status: DYNAMIC
- Page Rule not applied → check `*smartgarbage.eu.org/*` rule exists

### cf-cache-status: MISS
- First visit — second visit should be HIT

### SSL certificate error
- Wait 2-3 minutes for Render to provision certificate
