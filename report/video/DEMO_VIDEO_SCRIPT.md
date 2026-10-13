# SmartGarbage Chintalavalasa — Demo Video Script (v6, matches `_make_video_live.py`)
**Full walkthrough: every page the route table serves as a page — public, Citizen, Worker and
Admin — 31 scenes, no idle scenes.** Of the 41 routes that render a page, 39 are visited
directly, `/mfa-verify` is filmed as part of the worker/admin sign-in, and the only page left out is
`/reset-password/<token>`, whose token arrives by email (the form that sends it is filmed, and so is
its sibling `/resend-verification`). Machine endpoints (`/api/*`, `/sitemap.xml`, `/health`, the
service worker, the manifest) are not demo surfaces.
**That ledger is checked, not asserted:** `python report/video/_probe_route_coverage.py` reads the
Flask url_map, classifies each GET route by what its handler returns (41 pages, 5 downloads, 6
redirects, 6 utility actions) and exits non-zero if any *page* route is neither filmed nor listed as
a documented exception — re-run it after adding a route.
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

## Opening (0:00)
The video opens straight on the live homepage — no title card is spliced in, so every
frame is the website itself.

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

## 13. Citizen — waste declaration (`20_citizen_declare`)
**Caption:** Citizen - four-stream waste declaration feeding Green Points
**Say:** "Back in the citizen portal - still signed in. The dashboard carries a bin status search,
one-tap issue reporting, the cleanliness leaderboard, and the daily segregation declaration: wet,
dry, sanitary and hazardous waste in kilograms. Watch me declare today's waste and submit it - the
weights feed the household's Green Points and the ward's pay-as-you-throw billing."
**On camera:** ward picked, four stream weights typed, **Declare Segregated Waste** submitted →
"Waste declaration submitted (flagged for weight verification). Earned +14 Green Points".

## 14. Citizen — notification preferences (`21_citizen_prefs`)
**Caption:** Notification Preferences - per-event push switches
**Say:** "Notification preferences: the citizen chooses which events trigger a push notification -
complaint submitted, assigned, in progress, resolved or escalated, schedule reminders, Green
Points earned, and a weekly summary. I'll switch the weekly summary on and save."
**On camera:** Weekly Summary checked → **Save Preferences** → "Notification preferences updated."

## 15. Citizen — PAYT billing (`22_citizen_payt`)
**Caption:** PAYT billing - invoice, UPI / Razorpay payment, PDF receipt
**Say:** "Pay-as-you-throw billing. This is the outstanding August invoice - 363 rupees, billed on
62.9 percent segregation compliance with the penalty multiplier shown openly. The citizen pays by
UPI or card through Razorpay right here, and every settled invoice has a downloadable PDF receipt."

## 16. Citizen — tracking & data deletion (`23_citizen_track_delete`)
**Caption:** Signed tracking links & DPDP right-to-erasure request
**Say:** "Every complaint gets a signed tracking link - the tracking page explains how to use it,
how to reopen a resolved complaint, and how to rate the resolution. Under the Digital Personal Data
Protection Act a citizen can also file a right-to-erasure request here, which lands in the admin
queue."

## 17. Worker — issue report & offload (`24_worker_actions`)
**Caption:** Worker - raise a bin issue, log the dump-yard offload
**Say:** "The worker's side of the loop. A driver can raise a bin issue - damage or blockage -
straight from the portal instead of by phone, and at the end of the round logs the offload at the
dump yard, which closes the collection record for that truck."
**On camera:** bin + issue type picked, details typed → **Dispatch Issue Report**; then the offload
weight → **Log & Verify Digital Manifest**.

## 18. Admin — firmware & queues (`25_admin_firmware_ops`)
**Caption:** Admin - OTA firmware, offline deliveries, dead-letter queue
**Say:** "Admin operations, continued. OTA firmware management pushes ESP32 and Arduino updates to
the bins over Wi-Fi, with a release history and a per-bin connectivity report - no physical access
needed. The offline deliveries view audits complaints and photos that arrived through the PWA
queue, and the dead-letter queue exposes background jobs that exhausted their retry budget."

## 19. Admin — photo gate & audit trail (`26_admin_photogate_audit`)
**Caption:** Admin - photo-gate relabelling & the immutable audit trail
**Say:** "This is the photo gate's feedback loop: uploads the anti-fake-report model refused land
here so an admin can relabel a false positive, and the relabelled set downloads as the next
retraining batch. Behind everything sits the immutable audit trail - tamper-proof, with every
action from all three roles recorded."

## 20. Admin — analytics & compliance (`27_admin_analytics`)
**Caption:** Analytics & Compliance - ESG, carbon, state portal exports
**Say:** "The analytics and compliance hub: predictive collection heatmaps, an ESG compliance
audit, the carbon-footprint tracker and circular-economy reports - plus one-click exports, the
state portal compliance file, the CSRD export and a performance PDF."

## 21. Admin — privacy & super-admin (`28_admin_privacy_super`)
**Caption:** Admin - DPDP deletion queue & super-admin console
**Say:** "Governance. The deletion queue lists right-to-erasure requests with their acknowledge and
completion deadlines, and the super-admin console is the only place a new administrator account can
be created - public registration never grants a staff role."

## 22. Public — registration & waste pickers (`29_public_picker_register`)
**Caption:** Public - account registration & the informal waste picker register
**Say:** "Registration is open to citizens, and the informal waste picker register is a flow of its
own: recognition under Swachh Bharat Mission Phase Two for the people who already keep the ward
clean."

## 23. Public — BWG ledger & search (`30_public_bwg_search`)
**Caption:** BWG ledger - bulk generators declare, panchayat approves
**Say:** "Bulk waste generators - hotels, shops, institutions - declare their waste in the BWG
ledger, which drives the panchayat's bulk collection approvals. And site-wide search jumps straight
to any of these services."

## 24. Public — offline, consent & satisfaction (`31_public_offline_satisfaction`)
**Caption:** Offline PWA, cookie consent & ward satisfaction rankings
**Say:** "Rural connectivity is the default, so the offline page states exactly what still works -
draft a report now, it syncs when the signal returns. Cookie settings give granular consent, and
the ward satisfaction report ranks all five wards by the ratings citizens give after a resolution."

## 25. Public — anonymous dump channel & grievance (`32_public_illegal_grievance`)
**Caption:** Anonymous illegal-dumping report & grievance redressal officer
**Say:** "Illegal dumping has its own anonymous channel: an eyewitness files a dump report with a
photo and the location, and the system strips EXIF and never stores who reported it. If a complaint
is mishandled, the grievance page names the redressal officer and the order in which a grievance
escalates."

## 26. Citizen — file a complaint & track it (`33_citizen_file_track`)
**Caption:** File a complaint & track it - signed link, live timeline, SLA, reopen
**Say:** "Filing and tracking, end to end. The report form takes the ward, the address and the
description, and tags the exact device coordinates - GPS is mandatory, so a report cannot be filed
from nowhere. On submit the citizen lands on the signed tracking page: the live status timeline,
the ward's SLA window, the one-tap reopen if a resolution does not hold, and the satisfaction
rating once it closes. Back on the dashboard the complaint is listed with its tracking link."
**On camera:** ward + address + description → **Submit Report to Panchayat Sanitation Team** →
success panel with the tracking link → the link followed to `/track/<token>` → the dashboard row.

## 27. Public — legal & accessibility (`34_public_legal_a11y`)
**Caption:** Privacy policy, terms of service & accessibility statement
**Say:** "The legal and inclusion layer. The privacy policy sets out what the portal collects and
why under the data-protection framework, the terms of service state the rules of use, and the
accessibility statement publishes the WCAG commitments - keyboard support, heading structure and
contrast."

## 28. Public — account recovery (`35_password_recovery`)
**Caption:** Account recovery - password reset & a fresh verification link
**Say:** "Account recovery, for the moment a password or the verification mail goes missing: a
citizen enters the username and the portal mails a single-use reset link, or, if the verification
email never arrived, asks for a fresh verification link against the address on the account. Both
links are for one use only."

## 29. Mobile PWA (`15_pwa`)
**Caption:** Installable PWA - works offline, syncs when back online
**Say:** "SmartGarbage is an installable Progressive Web App. On a phone, the browser offers an
install button; after that the app opens full-screen and keeps working without internet — pages
are cached and complaints filed offline sync automatically when connectivity returns."

## 30. Under the hood (`16_deploy`)
**Caption:** Powered by Render + Supabase + Cloudflare - 100% free tier
**Say:** "Under the hood: GitHub pushes auto-deploy to Render, PostgreSQL runs on Supabase,
Cloudflare serves the edge, and GitHub Actions pings the health endpoint every fifteen minutes.
The entire stack is free-tier."

## 31. Close (`17_close`)
**Caption:** Schedules, complaints, ML dispatch, gamification - bilingual, zero cost
**Say:** "That is SmartGarbage — schedules, complaints, ML dispatch, gamification and billing, all
bilingual in English and Telugu, running at zero cost for the panchayat. Thank you."

---

## Closing
Scene 30's last page holds to a fade-out. There is no outro card — the video ends on the
website.

## Recording checklist
- [ ] `python scripts/run_local_stack.py` up (or live URL in `BASE`), `/` returns 200
- [ ] `flask db upgrade` applied — the tour films `/notifications/preferences`, which 500s on a
      database missing the web-push tables (revision `p3q4r5s6t7u8` creates them)
- [ ] `python scripts/seed_payt_invoices.py` — the PAYT scene needs a real invoice (`/payt/pay/3`)
- [ ] Demo accounts work: citizen direct, worker/admin via OTP (dev OTP or Email-me-the-code)
- [ ] `python report/video/_probe_pages.py` — every tour page returns 200 as its role
- [ ] `python report/video/_probe_new_scenes.py` — the write flow (report → tracking page →
      dashboard row) still submits, so scene 26 is never filmed as a form that never leaves itself
- [ ] `python report/video/_make_video_live.py` — record, narrate, caption, concat (one command)
- [ ] `python report/video/_probe_route_coverage.py` — exits 0 only while every page route the
      url_map serves is filmed (or is a documented exception), so a new page cannot be missed
- [ ] `python report/video/_verify_video.py` — segments, order, frozen tails, blank frames, captions
- [ ] No other tabs; browser zoom 100%; mic level checked (TTS path needs no mic)

## How the tour scenes work (v6)
The 16 scenes after `14_admin` are data, not code: each is a
`("tour", auth_role, steps)` tuple, and `record()` plays the steps in order — `go`, `scroll`,
`pick` (select a real option in a `<select>`), `fill`, `check`, `submit`, `click`, `wait`. Every step
is guarded individually, so a selector that moved costs one beat instead of the take. Tour scenes
that need a role harvest that role's session in an unrecorded browser (the sign-in itself is filmed
once per role), so no password is typed twice. Scenes that write — the waste declaration, the
preference change, the complaint filing, the issue report and the offload — submit the real forms,
which is why the admin views later in the cut show activity from this session.

The recording context also gets a live device position (geolocation granted and pinned to Ward 2):
`/report` refuses a filing without a GPS fix, so without it the filing scene would film a form that
never submits. `click` follows a link the page renders — the success panel's tracking link carries
`target="_blank"`, so the take drops the attribute and follows it in the same tab.
