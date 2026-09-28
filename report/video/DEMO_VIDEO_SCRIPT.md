# SmartGarbage Chintalavalasa — Demo Video Script (v5, matches `_make_video_live.py`)
**Full walkthrough: every public page + all three roles (Citizen / Worker / Admin) — no idle scenes.**
Renderer: `report/video/_make_video_live.py` (Playwright drives the real site at `http://127.0.0.1:5057`
via `scripts/run_local_stack.py`; swap `BASE` to the live URL after redeploy). Output: 1280×720 H.264.
Every scene = one on-screen caption band naming the feature + verbatim narration (SAPI TTS Zira).

**Demo credentials (seeded, also in `docs/REVIEW.md`):**

| Role | Username | Password | Login flow | MFA email |
|---|---|---|---|---|
| Citizen | `24331A4441CITIZEN` | `24331A4441CITIZEN` | direct → `/dashboard` | — |
| Worker | `24331A4441WORKER` | `24331A4441WORKER` | password → OTP → `/worker` | rama18072005@gmail.com |
| Admin | `24331A4441ADMIN` | `24331A4441ADMIN` | password → OTP → `/admin` (superadmin) | jaganmohan08112005@gmail.com |

On localhost the OTP is flashed on screen ("Dev OTP (localhost)"); on a real deploy use the
**✉️ Email me the code** button on the MFA page — the code arrives at the role's email above.

---

## Title card (0:00–0:05)
`card_title.png` + fade-in.

## 1. Home (`01_home`)
**Caption:** Homepage - SmartGarbage Chintalavalasa Portal
**Say:** "Welcome to SmartGarbage Chintalavalasa — the community waste-management portal for the
five wards of Chintalavalasa Gram Panchayat. Let me walk you through the live website, feature by
feature, including all three roles: citizen, worker, and admin."

## 2. Home scroll (`02_home_scroll`)
**Caption:** Live ward data, collection days & helpline 1800 119 9111
**Say:** "This is the public homepage. Notice the helpline number 1800 119 9111 and the collection
schedule quick search right at the top. As we scroll, you see ward-wise collection days, the
transparency statistics, and the community impact numbers — all live from the database."

## 3. Schedule (`03_schedule`)
**Caption:** Collection Schedule - pick your ward: pickup days + AI overflow risk
**Say:** "Every citizen can check their ward's collection schedule here. Pick a ward — watch as I
select Ward 2, Junction — and the portal shows the pickup days plus a machine-learning
overflow-risk prediction for the coming days. No phone calls, no guesswork."

## 4. Report (`04_report`)
**Caption:** Report a Missed Pickup - GPS location, photo proof, tracking token
**Say:** "Reporting a missed pickup takes under a minute. The form captures your ward, the location
with automatic GPS, and a photo as proof — the photo's GPS is cross-checked against your device,
so only live, on-site photos are accepted. Every submission gets a tracking token, and duplicates
within 100 metres or 30 minutes are rejected automatically."

## 5. Footer CTA (`05_whatsapp`)
**Caption:** WhatsApp fallback & toll-free helpline - always reachable
**Say:** "Below every page sits the rescue strip: the WhatsApp fallback card that opens a saved
chat, and the free toll-free grievance helpline 1800 119 9111. Citizens without internet are
covered by the offline-first PWA."

## 6. Transparency (`06_transparency`)
**Caption:** Transparency Dashboard - open complaint & collection data
**Say:** "The ward transparency dashboard is the accountability view: complaint counts by status,
resolution times, and the waste-collection statistics for every ward — published openly for
residents."

## 7. Impact & Contact (`07_impact`)
**Caption:** Impact & Contact - community results and every contact channel
**Say:** "The impact page summarises the community's environmental and social gains so far, and
the contact page lists every way to reach the panchayat team — WhatsApp, the toll-free helpline,
email, and a dedicated grievance form for formal complaints."

## 8. About & FAQ (`08_about_faq`)
**Caption:** About & FAQ - segregation, Green Points and PAYT explained
**Say:** "The About page explains the initiative and the five wards it serves. The FAQ page answers
the common questions — what can be recycled, how Green Points work, and how PAYT billing is
calculated."

## 9. Secure Login & MFA (`09_track_auth`)
**Caption:** Track Complaints & Secure Login - token tracking, staff MFA
**Say:** "Every complaint also gets a signed tracking link, so its status can never vanish. Staff
sign-in is where security shows: a password plus a second factor — a six-digit one-time code that
can arrive by email with one click, no SMS gateway required. Watch the worker sign in now; the
one-time code screen is the gate to the worker and admin portals."
**On camera:** worker submits credentials → MFA screen (✉️ Email me the code + 📱 Resend via
WhatsApp/SMS visible) → OTP typed → **"MFA Verified"** → lands on the Driver Portal.

## 10. Citizen dashboard (`12_citizen`) — role 1 of 3
**Caption:** Citizen Dashboard - Green Points, declarations, PAYT billing
**Say:** "Logged in as a citizen, the dashboard shows Green Points earned for segregation, the
eco-champions leaderboard, daily four-stream waste declarations, PAYT invoices with UPI payment
and receipts, and real-time notifications when a complaint moves."

## 11. Worker portal (`13_worker`) — role 2 of 3
**Caption:** Worker Portal - MFA entry, ML-ranked dispatch, geofenced proof
**Say:** "The worker portal opens after MFA. It shows today's dispatch queue ranked by predicted
fill, maintenance tasks, and the geofenced bin checklist — a bin can only be cleared on site, with
a live after-photo as proof. Offload logs close the loop at the dump yard."

## 12. Admin control room (`14_admin`) — role 3 of 3
**Caption:** Admin Control Room - live telemetry, SLA, exports, audit
**Say:** "The admin control room is the operational brain: live bin telemetry with fire, methane
and tilt alerts, SLA-escalating complaints, worker monitoring, OTA firmware pushes, audit trail,
failed-job alerts, and one-click state compliance exports."

## 13. Mobile PWA (`15_pwa`)
**Caption:** Installable PWA - works offline, syncs when back online
**Say:** "SmartGarbage is an installable Progressive Web App. On a phone, the browser offers an
install button; after that the app opens full-screen and keeps working without internet — pages
are cached and complaints filed offline sync automatically when connectivity returns."

## 14. Under the hood (`16_deploy`)
**Caption:** Powered by Render + Supabase + Cloudflare - 100% free tier
**Say:** "Under the hood: GitHub pushes auto-deploy to Render, PostgreSQL runs on Supabase,
Cloudflare serves the edge, and GitHub Actions pings the health endpoint every fifteen minutes.
The entire stack is free-tier."

## 15. Close (`17_close`)
**Caption:** Schedules, complaints, ML dispatch, gamification - bilingual, zero cost
**Say:** "That is SmartGarbage — schedules, complaints, ML dispatch, gamification and billing, all
bilingual in English and Telugu, running at zero cost for the panchayat. Thank you."

---

## Outro card
`card_outro.png` + fade-out.

## Recording checklist
- [ ] `python scripts/run_local_stack.py` up (or live URL in `BASE`), `/` returns 200
- [ ] Demo accounts work: citizen direct, worker/admin via OTP (dev OTP or Email-me-the-code)
- [ ] `python report/video/_make_video_live.py` — record, narrate, caption, concat (one command)
- [ ] No other tabs; browser zoom 100%; mic level checked (TTS path needs no mic)
