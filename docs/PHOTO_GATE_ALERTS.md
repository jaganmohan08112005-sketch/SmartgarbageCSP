# Breach Alert Channels — exact Render env-var setup

The photo-gate canary (see [PHOTO_GATE_RUNBOOK.md](PHOTO_GATE_RUNBOOK.md) §4)
alerts **in-app** on every breach. Two opt-in environment variables extend that
fan-out to email and SMS/WhatsApp so the panchayat is reached with the admin
dashboard closed. They are consumed by `_alert_photo_gate_channels` in
`app/jobs.py` and parsed by `_photo_gate_alert_recipients` (comma **or**
semicolon separated; entries are trimmed; empty entries ignored).

## The two variables (exact values)

Render Dashboard → your `smartgarbage` web service → **Environment** → add:

| Key | Example value | Delivery path |
|---|---|---|
| `PHOTO_GATE_ALERT_EMAIL` | `ops@panchayat.gov.in,secretary@panchayat.gov.in` | `send_email_job` → `send_email_via_smtp` (SMTP) |
| `PHOTO_GATE_ALERT_SMS` | `+919876543210,+919123456789` | `send_sms_job` → WhatsApp Cloud first, Twilio fallback |

Rules the parser enforces (`app/jobs.py::_photo_gate_alert_recipients`):

- Separator: `,` or `;` — both work, don't mix needlessly.
- Whitespace around entries is trimmed: `a@x.gov.in, b@x.gov.in` is fine.
- Invalid entries are **not** validated up front — a malformed phone number
  simply fails at send time (logged as `photo_gate_alert_sms_error`), so copy
  the values carefully.
- Both variables are **independent**: set only the one(s) you want.
- Leave a variable **unset** (not empty-string) to disable that channel
  entirely; nothing is ever sent without explicit opt-in because an outbound
  WhatsApp send outside a citizen's 24 h service window can cost money.

## Step-by-step (5 minutes)

1. **Prerequisite — SMTP must already work on Render.** The email channel
   reuses the app's normal SMTP chain. Check
   `https://smartgarbage.onrender.com/health` → `checks.mail`: it must NOT say
   `"no MAIL_SERVER configured"`. If it does, first set (values from your
   mail provider, e.g. Brevo — note Render blackholes ports 25/465/587, so use
   your provider's 2465/2587-style alternates, see `app/mail_probe.py`):
   - `MAIL_SERVER`, `MAIL_PORT`, `MAIL_USE_TLS=true`
   - `MAIL_USERNAME`, `MAIL_PASSWORD`, `MAIL_DEFAULT_SENDER`
2. **Prerequisite — SMS channel (only if you set the SMS var).** SMS reuses
   the citizen notification chain: set `WHATSAPP_CLOUD_TOKEN` +
   `WHATSAPP_CLOUD_PHONE_NUMBER_ID` (free-first) or `TWILIO_ACCOUNT_SID` +
   `TWILIO_AUTH_TOKEN` (+ optionally `TWILIO_WHATSAPP_NUMBER`) if they are not
   already present on the service.
3. In Render → **Environment**, click *Add Environment Variable* and add
   `PHOTO_GATE_ALERT_EMAIL` with the comma-separated panchayat addresses.
   Add `PHOTO_GATE_ALERT_SMS` the same way if wanted. **Never commit these to
   git** (`.env.example` intentionally does not list them).
4. Click **Save changes** — Render redeploys the service automatically. No
   code change or manual deploy is needed (dashboard edits apply on the next
   boot; see runbook §7 gotcha 2 for why no in-app toggle exists).
5. **Verify without waiting for a real breach.** After the deploy finishes:
   - In-app path: the admin Notifications bell must already be wired (it is —
     the in-app alert exists since the canary shipped).
   - Email path: send yourself one test mail through the same job:
     `venv/Scripts/python.exe -c "from app import create_app; from app.jobs import send_email_job; app=create_app(); app.app_context().push(); print(send_email_job('YOU@EXAMPLE.ORG','[SmartGarbage] alert channel test','If you can read this, the breach email path works.'))"`
     (run it locally against a test SMTP or temporarily from a Render shell).
   - SMS path: same call with `send_sms_job('+91XXXXXXXXXX','test')`.
6. **Trust the wiring end-to-end:** the behaviour (day-deduped, one alert per
   breach day, external fan-out only when `created:`) is   pinned by `test_photo_gate_breach_alert_channels` in `tests/test_features.py`,
   which monkeypatches `enqueue` and asserts the email/SMS jobs are enqueued
   to the env-listed recipients.

## What a breach email contains

The message is direction-neutral ("the photo gate canary FAILED — either the
reject-probe was accepted or the accept-probe was rejected") with the per-probe
failure detail appended, so a single channel handles both failure classes.

## Cost & safety notes

- Email: normal SMTP volume — breaches are day-deduped, so at most 1 email +
  1 SMS per recipient per UTC day even if the gate keeps failing.
- SMS/WhatsApp: opt-in for exactly the reason above — outside a citizen's
  24 h free service window, business-initiated sends can be billed (WhatsApp
  Cloud has a free monthly service-message allowance; Twilio is pay-per-send).
- The external channels are **best-effort**: a failing SMTP/WhatsApp call never
  blocks or breaks the canary job; the in-app alert always fires first.
