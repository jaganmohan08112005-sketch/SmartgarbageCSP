# Demo Script — Anonymous Report → Resolution Lifecycle
### SmartGarbage · Chintalavalasa Gram Panchayat · ~8 minutes

> All URLs live at https://smartgarbage.onrender.com. Numbers in brackets
> are talking points — say them while the page loads.

---

## 1. The problem (30s) — on the homepage

[One bin overflowing in a panchayat ward becomes a week of missed
collections because nobody reports it, and nobody can prove it got fixed.]

Open **/** — point out: no login needed to file a report; the awareness
banner (Swachh Bharat segregation messaging); live impact numbers pulled
from the same database you're about to write to.

## 2. File anonymously (2 min) — no account

1. Click **Report a Problem** → `/report`.
2. Fill: name **"Anonymous Resident"** (or leave default), ward
   **Ward 1 - MVGR College Area**, describe an overflowing bin.
3. Note the map **grabbing your GPS automatically** — [anti-spam: every
   report is geo-verified, max 15/hour, duplicate reports suppressed].
4. Attach a photo (any JPG). Submit.

**You get a signed tracking link** — no account, no email, but the token
is unguessable (itsdangerous-signed, 90-day expiry).

## 3. Track like a citizen (1 min)

Open the tracking link: **status timeline** (Submitted → …), SLA
countdown (48h), the ward it landed in. [Every state change is a
first-class timeline event — the citizen sees exactly what happened,
when, with what note.]

## 4. Control room: triage + MFA (2 min)

1. **Staff Login** → `24331A4441ADMIN` / password (ask presenter).
2. **MFA step** — a 6-digit OTP goes to the admin's phone via WhatsApp
   Cloud API (free inside the 24h window) with Brevo-email fallback.
   [Brute-force-proof: OTPs are hashed at rest; wrong attempts count
   toward lockout; the super-admin console is unreachable until the OTP
   is verified — direct URLs bounce to /mfa-verify.]
3. In the Admin Control Center: GIS map with live bin telemetry, then
   **Resolve** the new complaint. [SLA clock, escalation policy, and the
   notification chain fire automatically.]

## 5. Worker closes the loop with proof (1.5 min)

1. Log in as `fieldworker_ravi` (worker, MFA as above) → `/worker`.
2. Show the **dispatch queue** (overflow bins ranked by urgency, accept
   button) and the maintenance work orders.
3. Resolve the complaint via the worker path: the form **demands a live
   photo + on-site GPS** — the server Haversine-checks the GPS against
   the ward's bins before accepting. [A worker can't "resolve" from the
   truck. Photo is EXIF-stripped and stored as image-only — no raw-file
   injection.]

## 6. The resident rates it (1 min)

Back on the tracking link: status **Resolved**, timeline shows the
worker's proof event, and the **post-resolution 5-star survey** appears.
Rate it 5★.

[One rating per resolved ticket, DB-enforced; a salted fingerprint so
nobody can rate twice — no identity stored.]

## 7. The civic loop closes (1 min) — transparency pages

1. **/impact** — resolution rate, 93% recycling rate, CO₂ saved, ward
   rankings, Green Points economy — all computed from the actions you
   just performed.
2. **/reports/ward-satisfaction** — wards ranked by average stars this
   month, each ward's **Green Points segregation bonus** for next month.
   [Satisfaction feeds the reward economy: better-served wards earn
   households extra points — a real incentive loop, not a poster.]
3. `/admin` → **Satisfaction Survey** dashboard: the 5★ you just gave is
   already in the distribution chart and ward breakdown.

## Closing line (15s)

[Every layer you just saw — anonymous filing, signed tracking, MFA'd
control room, GPS-proven cleanup, rated resolutions, and a public
dashboard that turns both complaints and praise into household rewards —
runs on free-tier infrastructure: Render + Supabase + Cloudflare.]

---

### Fallbacks if the network misbehaves
- Cold start: the first page load can take ~50s on Render free — open the
  homepage before you begin talking.
- OTP delivery: WhatsApp Cloud needs one "Hi" from the presenter's phone
  in the prior 24h; otherwise the Brevo email path still delivers.
- Photos: the worker proof upload works with any JPG on the demo phone.
