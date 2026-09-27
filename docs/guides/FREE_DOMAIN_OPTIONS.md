# Free Domain Options for SmartGarbage

> **Goal:** Replace `.onrender.com` with a more authoritative domain for free.

---

## 🎯 Why Domain Matters

| Domain | Authority | TTFB | Cost | Notes |
|--------|-----------|------|------|-------|
| `smartgarbage.onrender.com` | Low | 0.87s | Free | Current |
| `smartgarbage.eu.org` | Medium | Same | Free | Free subdomain |
| `smartgarbage.freenom.com` | Low | Same | Free | Free .ml/.tk/.ga |
| `smartgarbage.vercel.app` | Medium | <100ms | Free | Fast hosting |
| `smartgarbage.netlify.app` | Medium | <100ms | Free | Fast hosting |
| `smartgarbage.pages.dev` | Medium | <100ms | Free | Cloudflare Pages |
| `smartgarbage.github.io` | Medium | <100ms | Free | GitHub Pages |
| `smartgarbage.in` | High | Same | ₹649/yr | Paid .in domain |
| `smartgarbagechintalavalasa.gov.in` | Very High | Same | Free | Government domain |

---

## 🟢 Free Options (Ranked by Quality)

### Option 1: Cloudflare Pages (Recommended Free)

**Why:** Fastest free hosting, global CDN, custom domains supported.

**Steps:**
1. Go to [pages.cloudflare.com](https://pages.cloudflare.com)
2. Connect GitHub repo
3. Build command: `pip install -r requirements.txt && flask db upgrade`
4. Output directory: `app/static/`
5. Get free subdomain: `smartgarbage.pages.dev`

**Pros:**
- ✅ Global CDN (fastest TTFB)
- ✅ Free SSL
- ✅ Free custom domain support
- ✅ Automatic deployments

**Cons:**
- ❌ Requires Flask app to be static (or use Workers)
- ❌ May not support full Flask backend

### Option 2: eu.org (Free Subdomain)

**Why:** Respected free subdomain, looks professional.

**Steps:**
1. Go to [nic.eu.org](https://nic.eu.org)
2. Create account
3. Register: `smartgarbage.eu.org`
4. Add DNS records pointing to Render
5. Configure in Render dashboard

**Pros:**
- ✅ Free
- ✅ Professional looking
- ✅ Supports custom DNS

**Cons:**
- ❌ Takes 1-2 weeks for approval
- ❌ No CDN benefits

### Option 3: Vercel (Free Tier)

**Why:** Fast hosting, generous free tier.

**Steps:**
1. Go to [vercel.com](https://vercel.com)
2. Import GitHub repo
3. Configure build settings
4. Get free subdomain: `smartgarbage.vercel.app`

**Pros:**
- ✅ Fast TTFB (<100ms)
- ✅ Free SSL
- ✅ Automatic deployments

**Cons:**
- ❌ May not support Flask well (Node.js focused)
- ❌ Free tier has limits

### Option 4: Netlify (Free Tier)

**Why:** Good for static sites, supports serverless functions.

**Steps:**
1. Go to [netlify.com](https://netlify.com)
2. Import GitHub repo
3. Configure build settings
4. Get free subdomain: `smartgarbage.netlify.app`

**Pros:**
- ✅ Fast TTFB
- ✅ Free SSL
- ✅ Serverless functions

**Cons:**
- ❌ Flask may need adaptation
- ❌ Free tier has limits

### Option 5: GitHub Pages (Free)

**Why:** Simple, reliable, integrates with GitHub.

**Steps:**
1. Go to repo Settings → Pages
2. Enable GitHub Pages
3. Get free subdomain: `jaganmohan08112005-sketch.github.io/SmartgarbageCSP`

**Pros:**
- ✅ Free
- ✅ Simple setup
- ✅ Integrates with GitHub

**Cons:**
- ❌ Static only (no Flask backend)
- ❌ Limited to Jekyll/Hugo

---

## 🟡 Paid Options (Best Value)

### Option 6: Cloudflare Registrar (₹649/year)

**Why:** Cheapest domain + free CDN.

**Steps:**
1. Go to [cloudflare.com](https://cloudflare.com)
2. Register domain: `smartgarbage.in` (~₹649/year)
3. Cloudflare CDN included free
4. Follow `wiki/CLOUDFLARE_CDN_SETUP.md`

**Pros:**
- ✅ Cheapest domain
- ✅ Free CDN
- ✅ Free SSL
- ✅ DDoS protection

**Cons:**
- ❌ Costs ₹649/year

### Option 7: Government Domain (Free)

**Why:** Maximum authority for government services.

**Steps:**
1. Contact Chintalavalasa Gram Panchayat
2. Request: `smartgarbage.chintalavalasa.gov.in`
3. Government domains are free for municipal services
4. Configure DNS to point to Render

**Pros:**
- ✅ Free
- ✅ Maximum authority
- ✅ Trusted by AI systems

**Cons:**
- ❌ Requires government approval
- ❌ May take weeks/months

---

## 🎯 Recommendation

| Scenario | Best Option | Cost |
|----------|-------------|------|
| **Zero budget, want speed** | Cloudflare Pages | Free |
| **Zero budget, want authority** | eu.org subdomain | Free |
| **Small budget, want best** | Cloudflare Registrar (.in) | ₹649/yr |
| **Government approval possible** | .gov.in subdomain | Free |

---

## 📋 Quick Setup: eu.org

```bash
# 1. Register at nic.eu.org
# 2. Wait for approval (1-2 weeks)
# 3. Add DNS records:
Type: CNAME
Name: @
Target: smartgarbage.onrender.com
Proxy: ON (if using Cloudflare)

# 4. Update Render:
# Dashboard → Settings → Custom Domains → Add: smartgarbage.eu.org

# 5. Update app:
export RENDER_EXTERNAL_URL=https://smartgarbage.eu.org
```

---

## 📋 Quick Setup: Cloudflare Pages

```bash
# 1. Push code to GitHub
# 2. Go to pages.cloudflare.com
# 3. Connect repo
# 4. Build settings:
#    Framework: Other
#    Build command: pip install -r requirements.txt
#    Output directory: .
# 5. Get subdomain: smartgarbage.pages.dev
```

---

## ⚠️ Important Notes

1. **Never use .tk/.ml/.ga domains** — they're associated with spam and have low authority
2. **Always use HTTPS** — all free options support this
3. **Update canonical URLs** — after changing domain, update `RENDER_EXTERNAL_URL`
4. **Redirect old domain** — keep `.onrender.com` redirecting to new domain
5. **Update sitemap** — regenerate sitemap with new domain
6. **Update schema.org** — update `url` in JSON-LD schemas
