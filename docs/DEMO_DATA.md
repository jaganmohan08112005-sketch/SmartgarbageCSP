# SmartGarbage — Demo Accounts, Credentials & Database Contents

**Live stack for the demo:** `python scripts/run_local_stack.py` → http://127.0.0.1:5057
(bundled Postgres on port 55713; data survives restarts). On the live deployment
(https://smartgarbage.onrender.com) the same core accounts work when `SEED_DEMO=true`.
On localhost the OTP is flashed on screen ("Dev OTP (localhost)"); in production use the
**✉️ Email me the code** button — the code goes to the account's registered email below.
OTPs are SHA-256 hashed at rest and expire after **5 minutes**.

---

## 1. All accounts (password = username for every demo account)

| Username | Password | Role | Phone | Email | Notes |
|---|---|---|---|---|---|
| `24331A4441ADMIN` | `24331A4441ADMIN` | Admin (superadmin) | +91 98765 43210 | **jaganmohan08112005@gmail.com** | Login → OTP → `/admin` control room |
| `24331A4441WORKER` | `24331A4441WORKER` | Worker (CV-01) | +91 98765 43212 | **rama18072005@gmail.com** | Login → OTP → `/worker` portal |
| `24331A4441CITIZEN` | `24331A4441CITIZEN` | Citizen | +91 98765 43211 | citizen4441@gmail.com | Direct login → `/dashboard` (no MFA), 120 GP |
| `rama_citizen` | `rama_citizen` | Citizen | +91 98765 43220 | rama18072005.citizen@gmail.com | 340 GP — leaderboard top |
| `lakshmi_resident` | `lakshmi_resident` | Citizen | +91 98765 43221 | lakshmi.resident@gmail.com | 210 GP |
| `sai_kumar` | `sai_kumar` | Citizen | +91 98765 43222 | sai.kumar@gmail.com | 95 GP |
| `worker_cv02` | `worker_cv02` | Worker (CV-02) | +91 98765 43230 | cv02.worker@gmail.com | Login → OTP → `/worker` |
| `worker_cv03` | `worker_cv03` | Worker (CV-03) | +91 98765 43231 | cv03.worker@gmail.com | Login → OTP → `/worker` |

**MFA rule:** only `worker` and `admin` roles require OTP. One phone ↔ one account, one
email ↔ one account (DB-enforced, `uq_user_phone` / `uq_user_email`) — that is why the two
staff accounts use different emails.

---

## 2. Database contents (27 tables, ~410 rows)

| Table | Rows | What's in it |
|---|---|---|
| `user` | 8 | 3 core + 3 citizens + 2 workers (above) |
| `worker_profile` | 3 | CV-01 (Active, 4.9★), CV-02, CV-03 |
| `schedule` | 10 | 2 collection days per ward, slots CV-01…05 |
| `smart_bin` | 40 | 8 bins per ward × 5 wards (BIN-101…508) |
| `bin_telemetry_log` | 244 | ~6 pings/bin over 48 h → ML fill-rate velocity |
| `complaint` | 6 | Every ward: Resolved ×3, Submitted ×2, Assigned ×1 |
| `waste_declaration` | 9 | 4-stream weights for 3 citizens (Green Points fuel) |
| `incident_log` | 5 | Overflow incidents incl. BIN-101 Active/High |
| `dispatch_assignment` | 1 | Worker claim from the AI dispatch queue |
| `audit_log` | 79 | Every privileged action (logins, MFA, registrations) |
| others | 0 | PAYT invoices, offload logs, firmware, webhooks… empty until you act in the UI |

### Sample bins (of 40)
BIN-101 Ward 1 92% Critical · BIN-106 Ward 1 100% Critical · BIN-107 Ward 1 103% Critical ·
BIN-108 Ward 1 95% Pending Clearance · BIN-102 31% Safe · BIN-201–204 Ward 2 Safe/Warning…

### Schedules (all wards, slot 06:00–08:30 AM)
Ward 1 Mon+Thu (CV-01) · Ward 2 Tue+Fri (CV-02) · Ward 3 Wed+Sat (CV-03) ·
Ward 4 Mon+Thu (CV-04) · Ward 5 Tue+Fri (CV-05)

---

## 3. Feature verification log (all tested live today)

| # | Feature | Result |
|---|---|---|
| 1 | 8 public pages (home, schedule, report, transparency, impact, contact, about+faq, track) | ✅ PASS ×8 |
| 2 | Registration uniqueness — duplicate **phone** rejected ("already registered") | ✅ PASS |
| 3 | Registration uniqueness — duplicate **email** rejected | ✅ PASS |
| 4 | No duplicate account leaked into DB after rejected attempts | ✅ PASS (0 rows) |
| 5 | Fake/sequential phone rejected server-side (`validate_indian_phone`) | ✅ PASS (9876543210 is a descending run → rejected) |
| 6 | Citizen login: direct, no MFA → `/dashboard` with Green Points + PAYT | ✅ PASS |
| 7 | Worker login: password → OTP screen with ✉️ **Email me the code** + 📱 Resend options | ✅ PASS |
| 8 | OTP verify → `/worker` Driver Portal (dispatch queue, route map, tasks) | ✅ PASS |
| 9 | Admin login: OTP → `/admin` control room (live bin tiles) | ✅ PASS |
| 10 | RBAC: citizen hitting `/admin` or `/worker` → **403** page | ✅ PASS |
| 11 | Anonymous hitting `/admin` → redirected to login | ✅ PASS |
| 12 | `/health` → JSON `healthy` (DB pass, storage, queue, mail posture) | ✅ PASS (after fix, below) |
| 13 | Security headers: CSP, HSTS, X-Content-Type-Options, X-Frame-Options, Referrer-Policy, Permissions-Policy | ✅ all 6 present |
| 14 | PWA: `/manifest.json` + `/sw.js` served | ✅ PASS |
| 15 | Open data API `/api/data` (CC-BY licence) | ✅ PASS |
| 16 | IoT telemetry in **production mode** (`RENDER=1` + secret): unsigned → 403, bad sig → 403, valid HMAC → 200 | ✅ PASS |
| 17 | ML: BIN-101 overflow **ETA = 3.6 h** from real telemetry slope; Ward-2 miss prediction fires on live weather | ✅ PASS |
| 18 | ML overflow alert webhook fired on high reading (`overflow_forecast_alert`) | ✅ PASS |

### Bug found & fixed during this audit
`/health` crashed with **500** on every deployment — `health_check()` referenced an
undefined `queue_posture`. Fixed in `app/routes/public.py` to call
`worker_health()` from `app/jobs.py`; verified returning
`{"status":"healthy", "checks":{"database":"pass"...}, "queue":{...}}`.

### Known local-mode notes (not bugs)
- Local dev accepts unsigned telemetry **by design** (no secret configured); the HMAC gate
  was proven in production mode (test 16) and is mandatory on Render/Fly (`503` if unset).
- `/api/devices/register` requires a CSRF token (it is not exempt like bin-telemetry);
  provisioning is done from the admin UI in normal use.
- Demo login test earlier hit the **header search** form because its button is the first
  `type=submit` on the page — page behaves correctly for humans; scripts must scope to
  `#password-login` / `form[action='/register']`.

---

## 4. Quick demo script

1. **Public:** show schedule lookup (Ward 2) → transparency → file a report with GPS.
2. **Citizen:** login `24331A4441CITIZEN` → dashboard (GP, declarations, PAYT) → leaderboard (`rama_citizen` 340 GP).
3. **Worker:** login `24331A4441WORKER` → OTP (Dev OTP on screen / **Email me the code**) → accept a dispatch from the AI queue → bin proof flow.
4. **Admin:** login `24331A4441ADMIN` → OTP → control room: BIN-101 Critical + Active incident, ML forecast, exports.
