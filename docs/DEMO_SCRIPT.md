# Demo Script — Anonymous Report → Resolution Lifecycle
### SmartGarbage · Chintalavalasa Gram Panchayat · ~8 minutes

> All URLs live at https://smartgarbage.onrender.com. Numbers in brackets
> are talking points — say them while the page loads.

---

## Verified demo credentials (all live-confirmed on smartgarbage.onrender.com)

| Account | Password | Role / lands on | Notes |
|---|---|---|---|
| `24331A4441CITIZEN` | `24331A4441CITIZEN` | Citizen → `/dashboard` (no MFA) | Green Points wallet, declarations, reports |
| `24331A4441WORKER` | `24331A4441WORKER` | Worker → MFA → `/worker` | Truck **CV-01**, Ward-1 sector, sees dispatch queue |
| `24331A4441ADMIN` | `24331A4441ADMIN` | Admin (superadmin) → MFA → `/admin` | Approves new admins in `/admin/super` |
| `fieldworker_ravi` | `WardOps@2026` | Worker → MFA → `/worker` | Truck **CV-90** (auto-created at registration) |
| `ward_admin_priya` | `WardOps@2026` | Admin → MFA → `/admin` | Non-super admin; registered via /register then approved |
| `driver_cv-01` | `24331A4441WORKER` | Worker → MFA → `/worker` | Seed fleet driver, CV-01 |

All staff accounts carry `smartgarbagecsp@gmail.com` (verified) so MFA
OTPs reach a real inbox via the Brevo fallback once `MAIL_*` is wired in
Render; WhatsApp Cloud is the primary OTP channel when the citizen has
messaged the number once. Workers/admins REQUIRE the MFA step — budget
~30s per staff login. Demo-citizens `demo_lakshmi` / `demo_suresh` /
`demo_padma` (password `Demo@2026`) hold 345 Green Points for the
impact-dashboard story.

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

1. **Staff Login** → `24331A4441ADMIN` / `24331A4441ADMIN`.
2. **MFA step** — a 6-digit OTP goes to the admin's registered contact
   via WhatsApp Cloud API (free inside the 24h window) with
   Brevo-email fallback to `smartgarbagecsp@gmail.com`. Until either
   gateway is wired in Render, the presenter completes MFA using the
   DB-delivery fallback (ask the operator) — the flow itself is
   unchanged. [Brute-force-proof: OTPs are hashed at rest; wrong
   attempts count toward lockout; the super-admin console is
   unreachable until the OTP is verified — direct URLs bounce to
   /mfa-verify (verified live).]
3. In the Admin Control Center: GIS map with live bin telemetry (41
   seeded bins across 5 wards), KPI cards, then **Resolve** the new
   complaint. [SLA clock, escalation policy, and the notification chain
   fire automatically. Status log records Submitted → Resolved with a
   timestamped note.]

## 5. Worker closes the loop with proof (2 min) — photo evidence

1. Log in as `24331A4441WORKER` / `24331A4441WORKER` (MFA as above) →
   `/worker` — header greets the account and shows truck **CV-01**.
2. Show the **dispatch queue** (overflow bins ranked by urgency, accept
   button) and the maintenance work orders. [Live-verified: the queue
   API returns the seeded Critical bins, e.g. BIN-207 Ward 2 at 103%.]
3. **Resolve the new complaint via the worker path** — the form is not
   a button, it's evidence intake, three gates enforced server-side
   (each live-tested on production):
   - **Live photo mandatory** — no upload, no resolution (400:
     "A live photo of the site is required").
   - **On-site GPS mandatory** — the server Haversine-checks the GPS
     against the ward's bins (200 m radius). A GPS from across the
     country is rejected: "Your GPS (9206449m from the ward's nearest
     bin) is out of range. Go to the site and retry."
   - **Image-only pipeline** — a text file renamed `.jpg` is refused
     ("The photo could not be processed as an image"), EXIF is stripped,
     and the proof lands in Supabase Storage with a public URL attached
     to the complaint's `resolution_photo`.
   [A worker can't "resolve" from the truck — the resolution record
   carries photographic evidence forever.]

## 6. The resident rates it (1 min)

Back on the tracking link: status **Resolved**, timeline shows the
worker's proof event ("Resolved by sanitation worker — photo proof
attached"), and the **post-resolution 5-star survey** appears. Rate it
5★. Trying to rate again is rejected (409, "This complaint has already
been rated") — say that out loud, it's a feature.

[One rating per resolved ticket, DB-enforced; a salted fingerprint so
nobody can rate twice — no identity stored. The rating appears instantly
in /admin's Satisfaction Survey dashboard and /reports/ward-satisfaction.]

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
  in the prior 24h; otherwise the Brevo email path still delivers (needs
  `MAIL_*` wired in Render). Until a gateway is live, the operator can
  stage the OTP via the DB — same hash the SMS would have carried.
- Photos: the worker proof upload works with any JPG on the demo phone.
- MFA is mandatory for staff: rehearse the OTP step so it doesn't eat
  your 8 minutes — or pre-open the admin session in a second tab.
- Cloudflare caches HTML for 60s: after filing a complaint, hard-refresh
  (Ctrl+Shift+R) pages that must show the new state.
