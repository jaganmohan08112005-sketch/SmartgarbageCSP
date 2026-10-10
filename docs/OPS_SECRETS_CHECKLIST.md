# Ops Secrets Checklist — SMTP + production `DATABASE_URL`

**For:** the panchayat ops person who keeps SmartGarbage running.
**Time needed:** about 20 minutes.
**Why it matters:** two automated jobs run for you every day/week. Until the
secrets below are added they stay *green but silent* — they do not fail, they
just don't mail anything or write a real weekly snapshot. Ten minutes of setup
turns them on.

| What it does | When it runs | Needs |
|---|---|---|
| **Daily health digest** — emails the panchayat inbox a summary of `/health` | Every day ~08:00 IST | SMTP + digest secrets (GitHub) |
| **Weekly reliability snapshot** — appends the trailing-7-day photo-gate numbers to [PHOTO_GATE_RELIABILITY_REPORT.md](PHOTO_GATE_RELIABILITY_REPORT.md) | Mondays ~08:30 IST | `DATABASE_URL` (GitHub) |
| **In-app breach alerts + email/SMS fan-out** — pages you if the photo-gate canary breaks | On breach | `MAIL_*` + `PHOTO_GATE_ALERT_*` (Render) |

> **Two different dashboards — do not mix them up.** The two workflows run on
> **GitHub's** servers, so their secrets live in **GitHub → repo Settings →
> Secrets and variables → Actions**. The live app runs on **Render**, so its
> mail/alerts live in the **Render Dashboard → Environment**. A value set in one
> place does **not** reach the other, even when it is the same SMTP account.

---

## Part A — GitHub repository secrets (for the two workflows)

**Where:** open the repo on GitHub → **Settings** → **Secrets and variables** →
**Actions** → **New repository secret**. Add each row below with the **exact
name** in the left column. Names are case-sensitive and must match exactly.

| Secret name | What to paste | Required? |
|---|---|---|
| `DATABASE_URL` | Supabase connection string — see **Part A.1** | **Yes** (real weekly snapshots) |
| `SMTP_HOST` | Your mail provider's SMTP host, e.g. `smtp-relay.brevo.com` | **Yes** (digest email) |
| `SMTP_PORT` | `587` (STARTTLS). If sends time out, try `2525` | **Yes** |
| `SMTP_USE_TLS` | `true` | **Yes** |
| `SMTP_USERNAME` | Your SMTP login (usually your account email) | **Yes** |
| `SMTP_PASSWORD` | Your SMTP password / API key (never your account password) | **Yes** |
| `DIGEST_FROM` | The From address, e.g. `alerts@panchayat.gov.in`. If blank it falls back to `SMTP_USERNAME` | Recommended |
| `DIGEST_TO` | Comma-separated recipients, e.g. `ops@panchayat.gov.in,secretary@panchayat.gov.in` | **Yes** |

**Notes the scripts enforce**

- All four of `SMTP_HOST` + `SMTP_USERNAME` + `SMTP_PASSWORD` + `DIGEST_TO` must
  be present before a digest is sent. If any is missing the run is **green** and
  the digest is saved to the workflow's *Artifacts* instead of mailed.
- `SMTP_USE_TLS` defaults to `true`; leave it `true`.
- `DIGEST_TO` splits on commas (a semicolon also works). Extra spaces are
  trimmed, so `a@x.gov.in, b@x.gov.in` is fine.
- The digest runs on GitHub's hosted runners, which — unlike Render — are **not**
  subject to Render's outbound SMTP port blackhole, so `SMTP_PORT=587` normally
  works. If the send fails with a connection timeout, switch to `2525`.

### A.1 — Where to get `DATABASE_URL`

This is the **production** Postgres (Supabase) connection string. It gives full
read/write access, so treat it like a master password.

1. Supabase Dashboard → your SmartGarbage project (ref `pofuuaohiajcfjrrtoqh`).
2. **Settings** → **Database** → **Connection pooling**.
3. Copy the **Transaction mode** connection string. It looks like:
   ```
   postgresql://postgres.<ref>:<password>@aws-0-<region>.pooler.supabase.com:5432/postgres
   ```
   Use the **pooler** host (`...pooler.supabase.com`), not the direct `db.<ref>.supabase.co`
   host — the pooler is what works from CI and the app.
4. Paste it as the value of the `DATABASE_URL` secret. If your connection string
   contains characters like `@`, `#` or `/` in the password, URL-encode them.

> **Read-only is better if you can.** The weekly job only runs `SELECT`s. If
> your team later creates a read-only Postgres role, swap `DATABASE_URL` to that
> URL — nothing in the workflow writes to the database, only to the docs report.

### A.2 — Where to get the SMTP values

Use the **same mail account** that Render uses for breach emails if you have one;
otherwise your provider's SMTP credentials. Example with **Brevo** (free tier is
enough for this volume):

| Brevo field | Becomes the secret |
|---|---|
| SMTP server `smtp-relay.brevo.com` | `SMTP_HOST` |
| Port `587` | `SMTP_PORT` |
| SMTP login (your account email) | `SMTP_USERNAME` |
| SMTP key (not the account password) | `SMTP_PASSWORD` |

Other providers (Zoho, Gmail-with-app-password, Amazon SES) work the same way —
find their "SMTP settings" page and map host / port / username / key.

### A.3 — Paste it in (2 minutes)

1. GitHub repo → **Settings** → **Secrets and variables** → **Actions**.
2. **New repository secret** → type the exact name → paste the value → **Add
   secret**. Repeat for each row in the Part A table.
3. That's it — no code change, no redeploy. The next scheduled run picks them up.

### A.4 — Verify

1. GitHub repo → **Actions** tab → **Health digest** → **Run workflow**
   (`main` branch) → wait ~1 minute.
2. Open the run. Good outcomes:
   - **Green + you receive the digest email** → SMTP is fully working.
   - **Green, summary says "email skipped — SMTP… not set yet"** → the secrets
     didn't land on the repo (check the exact names) — this is the current
     no-secrets state, not a failure.
   - **Red with "email send FAILED"** → the SMTP values are wrong; re-check
     `SMTP_HOST` / `SMTP_PORT` / `SMTP_USERNAME` / `SMTP_PASSWORD`.
3. Then **Reliability report** → **Run workflow** → a new
   `docs: weekly reliability snapshot …` commit appears on `main` if
   `DATABASE_URL` is valid. Without it, the run stays green and logs
   **"SMOKE MODE: skipping the weekly append."**

---

## Part B — Render environment variables (for the live app)

These are **not** GitHub secrets. Set them in **Render Dashboard → your
`smartgarbage` web service → Environment**. Full details and the exact paste
steps are in [PHOTO_GATE_ALERTS.md](PHOTO_GATE_ALERTS.md); the short version:

| Key | Purpose |
|---|---|
| `MAIL_SERVER` | SMTP relay host for the app's own email |
| `MAIL_PORT` | **Use `2525` on Render.** Render blackholes outbound ports 25 / 465 / 587 — use your provider's alternate (Brevo supports `2525`) |
| `MAIL_USE_TLS` | `true` |
| `MAIL_USERNAME` | SMTP login |
| `MAIL_PASSWORD` | SMTP key |
| `MAIL_DEFAULT_SENDER` | From address for app mail |
| `PHOTO_GATE_ALERT_EMAIL` | Comma-separated addresses for breach emails (opt-in) |
| `PHOTO_GATE_ALERT_SMS` | Comma-separated numbers (with country code) for breach SMS/WhatsApp (opt-in) |

**Render gotcha:** port `587` is *blackholed* (the connection hangs instead of
failing), so the app's mail must use `2525` (or another permitted port your
provider offers). This is the biggest difference from the GitHub-side SMTP
secret above, where `587` is fine.

After **Save changes** Render redeploys automatically. Confirm with
`https://smartgarbage.onrender.com/health` → the `checks.mail` field must **not**
say `"no MAIL_SERVER configured"`.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Digest run green, no email | Secrets not set (or set on the wrong repo/environment) | Re-check the exact names in **Part A**; note names are case-sensitive |
| Digest red: "email send FAILED" | Wrong SMTP host/port/user/password | Re-paste from the provider's SMTP page; try `SMTP_PORT=2525` |
| Weekly report stays "SMOKE MODE" | `DATABASE_URL` unset or empty | Add it (Part A.1) |
| Weekly report red, "DATABASE_URL missing/invalid" | Malformed / expired connection string | Re-copy the **pooler** string; URL-encode special password characters |
| `/health` says mail unconfigured | `MAIL_*` not set on Render | Set them (Part B) with `MAIL_PORT=2525` |
| Breach alerts never arrive | `PHOTO_GATE_ALERT_*` not set (they are opt-in) | Set them on **Render**, not GitHub (Part B) |

## Security rules

- **Never** paste these values into code, docs, chat, or a commit. `.env` is
  git-ignored — keep it that way; use the dashboards for anything shared.
- `DATABASE_URL` and SMTP keys are full-credential secrets: anyone with them can
  read/write the production database or send mail as the panchayat. Store them
  only in GitHub/Render, and rotate if ever exposed.
- Prefer a provider-supplied **SMTP key** over an account password, and revoke a
  key immediately if a device is lost.

## Your values (fill in offline, then delete this page copy)

| Secret | Source | Value set? |
|---|---|---|
| `DATABASE_URL` | Supabase → Settings → Database → Connection pooling | ☐ |
| `SMTP_HOST` | Mail provider SMTP settings | ☐ |
| `SMTP_PORT` | `587` | ☐ |
| `SMTP_USE_TLS` | `true` | ☐ |
| `SMTP_USERNAME` | Mail provider | ☐ |
| `SMTP_PASSWORD` | Mail provider (key) | ☐ |
| `DIGEST_FROM` | Panchayat From address | ☐ |
| `DIGEST_TO` | Panchayat recipients | ☐ |

## Done checklist

- [ ] Added all 8 GitHub Actions secrets (Part A).
- [ ] Re-ran **Health digest** and received the email.
- [ ] Re-ran **Reliability report** and saw a snapshot commit on `main`.
- [ ] Set `MAIL_*` on Render with `MAIL_PORT=2525`; `/health` mail check is green.
- [ ] Set `PHOTO_GATE_ALERT_EMAIL` (and optionally `PHOTO_GATE_ALERT_SMS`) on Render.
