# Cloudflare CDN Setup for SmartGarbage

## Why Cloudflare?

Render free tier has cold starts (~1-2s TTFB). Cloudflare's free plan caches
HTML at edge locations worldwide, serving repeat visitors instantly (<100ms).

## Setup Steps

### 1. Create Cloudflare Account (free)
- Go to https://dash.cloudflare.com/sign-up
- Create free account

### 2. Add Domain
- Click "Add a Site" → enter your domain
- Cloudflare scans existing DNS records
- Select "Free" plan

### 3. Update Nameservers
- Cloudflare provides 2 nameserver addresses
- Go to your domain registrar (GoDaddy, Namecheap, etc.)
- Replace existing nameservers with Cloudflare's
- Wait 24-48 hours for propagation

### 4. Configure Cache Rules
In Cloudflare Dashboard → Rules → Page Rules:

**Rule 1: Cache HTML pages**
```
URL: smartgarbage.onrender.com/*
Setting: Cache Level → Standard
Browser Cache TTL: 4 hours
```

**Rule 2: Cache static assets aggressively**
```
URL: smartgarbage.onrender.com/static/*
Setting: Cache Level → Cache Everything
Edge Cache TTL: 1 month
Browser Cache TTL: 1 year
```

### 5. Enable Brotli Compression
- Go to Network → Speed → Optimization → Content Optimization
- Enable "Brotli" compression
- This compresses responses at the edge

### 6. Enable HTTP/3 (QUIC)
- Go to Network → Speed → Optimization → HTTP/3 (QUIC)
- Enable for faster connections

### 7. Configure Security Headers
- Go to Security → Settings
- Enable "Always Use HTTPS"
- Enable "Automatic HTTPS Rewrites"

## Expected Results

| Metric | Before Cloudflare | After Cloudflare |
|---|---|---|
| TTFB (repeat visit) | 1.06s | **<100ms** |
| TTFB (cold start) | 1.06s | 1.06s (first hit) |
| HTML size (compressed) | 10KB | 10KB |
| Static assets | Loaded from Render | **Served from edge** |
| SSL/TLS | Render terminates | **Cloudflare terminates** |

## Cost

**$0/month** — Cloudflare free plan includes:
- CDN caching
- Brotli compression
- DDoS protection
- SSL/TLS
- Basic analytics

## Verification

After setup, test with:
```bash
# Check if Cloudflare is active
curl -sI https://smartgarbage.onrender.com/ | grep -i "cf-ray"

# Check cache status
curl -sI https://smartgarbage.onrender.com/ | grep -i "cf-cache-status"
# Should show "HIT" for cached responses
```

## Alternative: Fly.io Free Tier

If Cloudflare doesn't work for your setup, deploy on Fly.io alongside Render:

```bash
# Install flyctl
curl -L https://fly.io/install.sh | sh

# Launch app
fly launch

# Deploy
fly deploy
```

Fly.io free tier: 3 shared CPUs, 256MB RAM, better cold starts than Render.
