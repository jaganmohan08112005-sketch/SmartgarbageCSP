# WWW Canonicalization Setup

Multiple SEO auditors flag that `www.smartgarbage.onrender.com` doesn't redirect to the apex domain. The Flask redirect middleware already exists in `app/__init__.py` (line 390-396), but the www subdomain doesn't resolve to Render's servers.

## Option 1: Cloudflare Page Rule (Recommended)

1. Log in to Cloudflare dashboard
2. Select the `smartgarbage.onrender.com` zone
3. Go to **Rules** → **Page Rules**
4. Click **Create Page Rule**
5. Set URL: `www.smartgarbage.onrender.com/*`
6. Set Setting: **Forwarding URL** (301 - Permanent Redirect)
7. Set Destination: `https://smartgarbage.onrender.com/$1`
8. Click **Save and Deploy**

## Option 2: Render Dashboard

1. Log in to Render dashboard
2. Go to the SmartGarbage web service
3. Go to **Settings** → **Custom Domains**
4. Add `www.smartgarbage.onrender.com` as a custom domain
5. Render will auto-generate a CNAME record
6. Add a redirect rule in Render's **Redirects** section

## Option 3: DNS Provider

1. Log in to your DNS provider (where the domain is managed)
2. Add a CNAME record:
   - Name: `www`
   - Value: `smartgarbage.onrender.com`
   - TTL: 300
3. The Flask middleware in `app/__init__.py` will handle the redirect

## Verification

After setup, test:
```bash
curl -sI https://www.smartgarbage.onrender.com/ | head -5
# Should show: HTTP/1.1 301 Moved Permanently
# Location: https://smartgarbage.onrender.com/
```

## Notes

- The Flask middleware already handles the redirect if the request reaches the server
- The issue is that `www.smartgarbage.onrender.com` currently returns a 530 error (DNS not configured)
- Option 1 (Cloudflare) is fastest and doesn't require Render config changes
