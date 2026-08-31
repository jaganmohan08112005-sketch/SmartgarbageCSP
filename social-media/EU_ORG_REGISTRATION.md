# eu.org Free Domain Registration — Step-by-Step

## Register Domain (15 minutes)

### Step 1: Go to eu.org
```
https://nic.eu.org
```

### Step 2: Click "Create an account"
- Top right corner

### Step 3: Fill in Registration Form
```
Handle: smartgarbage
First Name: [Your first name]
Last Name: [Your last name]
Email: [Your email address]
Phone: [Your phone number]
Organisation: Chintalavalasa Gram Panchayat Community Project
```

### Step 4: Click "Create account"

### Step 5: Check Email
- Look for email from `admin@nic.eu.org`
- Subject: "Account confirmation"
- Click the verification link

### Step 6: Log In
- Go to: https://nic.eu.org
- Click "Log in"
- Enter your handle and password

### Step 7: Register Domain
- Click "New Domain" (top menu)
- Enter: `smartgarbage.eu.org`
- Click "Submit"

### Step 8: Add DNS Records
You'll see a page asking for DNS configuration. Add:

```
Type: CNAME
Name: @
Target: smartgarbage.onrender.com
```

If CNAME doesn't work, use A records:
```
Type: A
Name: @
Value: [Get Render's IP from their dashboard]
```

### Step 9: Click "Submit"

### Step 10: Wait for Approval
- You'll see: "Domain registered. Waiting for approval."
- Approval takes 1-2 weeks
- You'll receive an email when approved

### Step 11: Update Cloudflare
After approval:
1. Go to Cloudflare dashboard
2. Click your domain
3. Go to DNS → Records
4. Update CNAME to point to `smartgarbage.onrender.com`

---

## After Approval

### Step 1: Update Render
1. Go to: https://dashboard.render.com
2. Click your web service
3. Go to "Settings" → "Custom Domains"
4. Click "Add Custom Domain"
5. Enter: `smartgarbage.eu.org`
6. Render will verify the DNS

### Step 2: Update App Environment
In Render dashboard → Environment:
```
RENDER_EXTERNAL_URL=https://smartgarbage.eu.org
```

### Step 3: Test
```bash
curl -sI https://smartgarbage.eu.org/
```

Should return HTTP 200 with Cloudflare headers.

---

## Troubleshooting

### "Domain already registered"
- Try: `smartgarbage-cv.eu.org` or `smartgarbage-chintalavalasa.eu.org`

### "DNS not resolving"
- Wait 24-48 hours after adding DNS records
- Check: `dig smartgarbage.eu.org`

### "Approval taking too long"
- eu.org is run by volunteers
- Average approval time: 1-2 weeks
- Check status at: https://nic.eu.org/cgi-bin/nic-track.cgi

---

## Timeline

| Day | Action |
|-----|--------|
| Day 1 | Register account + domain |
| Day 1 | Add DNS records |
| Day 1-14 | Wait for approval |
| Day 14+ | Update Cloudflare + Render |
| Day 14+ | Test and verify |
