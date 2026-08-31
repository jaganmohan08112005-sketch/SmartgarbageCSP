# Register smartgarbage.eu.org — Free Domain Guide

## Why eu.org?

| Feature | eu.org | .onrender.com |
|---------|--------|---------------|
| **Authority** | Professional .org subdomain | Generic hosting subdomain |
| **SEO** | Better domain authority | Low authority |
| **Trust** | Looks like official org | Looks like free hosting |
| **Cost** | ₹0 (free forever) | ₹0 |
| **Approval** | 1-2 weeks (manual) | Instant |
| **URL** | smartgarbage.eu.org | smartgarbage.onrender.com |

---

## Step 1: Create eu.org Account (5 minutes)

1. **Open**: https://nic.eu.org
2. **Click**: "Create an account"
3. **Fill in these EXACT details**:

```
Handle:      smartgarbage
Name:        Jagan Mohan
Email:       [YOUR EMAIL ADDRESS]
Organisation: Chintalavalasa Gram Panchayat Community Service Project
```

4. **Click**: "Create account"
5. **Check your email** for verification link
6. **Click** the verification link
7. **Log in** with your handle and password

---

## Step 2: Register the Domain (5 minutes)

1. **Log in** at https://nic.eu.org
2. **Click**: "New Domain"
3. **Enter**: `smartgarbage.eu.org`
4. **Click**: "Submit"

---

## Step 3: Add DNS Record (2 minutes)

When prompted for DNS configuration, add this record:

```
Type:    CNAME
Name:    @
Target:  smartgarbage.onrender.com
```

**Important**: Use CNAME (not A record). This tells eu.org to forward all traffic to your Render site.

---

## Step 4: Wait for Approval (1-2 weeks)

eu.org is run by volunteers. Approval typically takes:
- **Fast**: 3-5 days
- **Normal**: 1-2 weeks
- **Slow**: 3-4 weeks (rare)

You'll receive an email when approved.

---

## Step 5: After Approval — Add to Render (3 minutes)

1. **Go to**: https://dashboard.render.com
2. **Click** your `smartgarbage` service
3. **Go to**: Settings → Custom Domains
4. **Click**: "Add Custom Domain"
5. **Enter**: `smartgarbage.eu.org`
6. **Click**: "Save"

Render will automatically:
- Verify the CNAME record
- Provision SSL certificate
- Start serving traffic on the new domain

---

## Step 6: Update App Configuration (2 minutes)

After Render confirms the custom domain is live, add this environment variable:

1. **Go to**: Render Dashboard → your service → Environment
2. **Add**:
```
Key:   RENDER_EXTERNAL_URL
Value: https://smartgarbage.eu.org
```

This ensures all links, canonical tags, and schema markup use the new domain.

---

## Step 7: Test Everything (5 minutes)

After the domain is active, run these checks:

```bash
# 1. Test DNS resolution
nslookup smartgarbage.eu.org
# Should show: smartgarbage.onrender.com

# 2. Test HTTPS
curl -sI https://smartgarbage.eu.org/
# Should show: HTTP/2 200, Server: cloudflare

# 3. Test Cloudflare CDN (if configured)
curl -sI https://smartgarbage.eu.org/ | grep cf-cache-status
# Should show: cf-cache-status: HIT (after configuring Cache Rules)

# 4. Test TTFB
curl -o /dev/null -s -w "TTFB: %{time_starttransfer}s\n" https://smartgarbage.eu.org/
# Should show: TTFB: 0.0Xs (under 100ms)
```

---

## Step 8: Update External Profiles (5 minutes)

Update your links on these platforms:

| Platform | Where to Update |
|----------|----------------|
| GitHub repo | Update description, homepage URL |
| LinkedIn | Update website URL |
| Dev.to article | Edit article, update links |
| Reddit posts | Can't edit, but new posts use new URL |
| Twitter | Update bio URL |
| Wikidata | Update official website property |
| README.md | Update all URLs in the file |

---

## Timeline Summary

| Step | Time | When |
|------|------|------|
| Create account | 5 min | Today |
| Register domain | 5 min | Today |
| Add DNS | 2 min | Today |
| Wait for approval | 1-2 weeks | Automatic |
| Add to Render | 3 min | After approval |
| Update config | 2 min | After approval |
| Test | 5 min | After approval |
| Update profiles | 5 min | After approval |
| **Total active time** | **27 min** | |
| **Total wait time** | **1-2 weeks** | |

---

## Troubleshooting

### "Domain already registered"
- Try: `smartgarbage-cv.eu.org` or `sg-chintalavalasa.eu.org`

### "DNS record not found"
- Make sure you added CNAME (not A record)
- Target must be `smartgarbage.onrender.com` (no https://, no trailing slash)

### Approval takes too long
- eu.org is volunteer-run
- Check spam folder for approval email
- You can reply to the approval email to expedite

### Render says "DNS not configured"
- Wait 24-48 hours after eu.org approval for DNS propagation
- Use https://dnschecker.org to verify CNAME is live

---

## What You Get After

| Before | After |
|--------|-------|
| `smartgarbage.onrender.com` | `smartgarbage.eu.org` |
| Looks like free hosting | Looks like official organization |
| Low SEO authority | Higher authority |
| No trust signal | Professional trust signal |

**Cost: ₹0 | Time: 27 minutes active + 1-2 weeks wait**
