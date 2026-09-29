# SmartGarbage — REVIEW PREP (Reviewer / HR / Project-Head Q&A)

> **SmartGarbage Chintalavalasa** — Community Waste Management Portal for the five wards of
> Chintalavalasa Gram Panchayat, Denkada Mandal, Vizianagaram district, Andhra Pradesh (~12,000 residents).
> **Live:** https://smartgarbage.onrender.com · **Repo layout:** see `docs/PROJECT_STRUCTURE.md`
> **Team (Batch 2):** M. Jaganmohan (24331A4441) · L. Reshma (24331A4434) · P. Narasimha Murthy (24331A4446) · K. Augustin Paul Kumar (24331A4426)
> **Course:** R24MSCSP001 · Branch: CSE (Data Science) · Dept: Data Engineering · Sem V Sec A, Reg R24 · Guide: Mrs. S. Nikhila

**How to use this file:** it is organised the way a review panel thinks — project head (why/what/how),
tech stack & alternatives, datasets, ML, security, traffic & capacity, then a rapid-fire section.
Every answer ends with a one-line **sound-bite** you can say verbatim.

---

## 0. Demo credentials (seeded by `seed_db.py` when SEED_DEMO=true)

| Role | Username | Password | Login flow |
|---|---|---|---|
| **Citizen** | `24331A4441CITIZEN` | `24331A4441CITIZEN` | Direct → `/dashboard` (no MFA) |
| **Worker** | `24331A4441WORKER` | `24331A4441WORKER` | MFA → `/worker` |
| **Admin** | `24331A4441ADMIN` | `24331A4441ADMIN` | MFA → `/admin` (superadmin) |

- **MFA for worker/admin:** on the MFA page use **✉️ Email me the code** — the OTP is emailed to the
  account's registered email: **admin → jaganmohan08112005@gmail.com**, **worker → rama18072005@gmail.com**
  (unique index `uq_user_email` forbids two accounts sharing one address, so staff emails are split).
  Also available: 📱 **Resend via WhatsApp / SMS** (Meta WhatsApp Cloud → Twilio → email fallback chain).
- **Local runs (`python run.py`):** the OTP is also flashed on screen ("Dev OTP (localhost): 123456").
- OTPs are **SHA-256 hashed at rest**, expire in **5 minutes**, and wrong entries count toward the
  same lockout counter as passwords.
- These are **publicly-known demo accounts** (documented here) for review purposes only;
  a production deploy sets `SEED_DEMO=false` and creates real accounts via registration + admin approval.

---

## 1. Project head: the why / what / how

**Q. Why does this project exist? What real problem does it solve?**
Chintalavalasa's ~12,000 residents across 5 wards had **no digital channel** for waste services:
paper notices (if any) for collection timing, no way to report missed pickups or dumped garbage,
no visibility into what the Panchayat actually collects, and segregation was voluntary with no proof
or incentive. Missed pickups were reported by word-of-mouth; there was no data for the Gram
Panchayat to plan routes or prove compliance to the state.
**Sound-bite:** *"We replaced a notice board and a phone tree with one accountable, data-producing portal."*

**Q. What exactly is it?**
A **Flask web portal (PWA)** with four experience layers:
1. **Public (no login):** street-level collection schedule per ward, transparency dashboard
   (live bin telemetry + collection stats), FAQ, grievance contacts, WhatsApp reporting entry point.
2. **Citizen:** dashboard with **Green Points**, complaint filing with **signed tracking links**,
   daily 4-stream waste declarations, PAYT invoices & UPI payment, notifications.
3. **Worker:** route with **geofence enforcement**, pickup confirmation (scan/PIN), offload logs with
   impurity flags, truck telemetry (CV-01…).
4. **Admin:** control room — 10 smart bins, incidents (fire/methane/tilt), SLA-escalating complaints,
   worker monitoring, OTA firmware pushes, audit trail, export centre (CSV/PDF/JSON state returns).

Plus **machine learning** layered on real telemetry (see §4) and **IoT ingestion** (HMAC-signed pings).

**Q. How is it built (one paragraph)?**
Flask 3 app factory → 9 route modules (public, citizen, admin, worker, auth, analytics, iot, webhook,
worker_resolve) over **PostgreSQL** (Supabase, 23 tables, 29 Alembic migrations), Socket.IO for
real-time dashboards, RQ+Redis for background jobs, an offline-first service worker (PWA), and
scikit-learn models trained on bin telemetry. Deployed as **Docker on Render**, health-checked at
`/health`. The whole pipeline is reproducible: `flask db upgrade → seed_db.py → gunicorn`.

**Q. Why a portal and not just an app?**
Users here span **basic Android phones and desktops in the Panchayat office**. A PWA installs from the
browser (no Play Store barrier, no update friction), works offline through the service worker, and
costs zero store fees. WhatsApp is the second front-end — residents already use it, so reporting
garbage needs **no new app at all**.

**Q. Who are the users and what does each get?**
- **Citizen (resident):** schedule, report, track, earn Green Points, pay PAYT.
- **Sanitation worker:** daily route, geofence, pickup confirmation, offload proof.
- **Panchayat admin:** live operations picture, SLA enforcement, audit-grade records, exports.
- **State reviewers:** standard compliance exports (`state_portal_compliance.csv/json`, CSR-D JSON).

---

## 2. Tech stack — what we used, and **why not the alternatives**

| Layer | We use | Why this | Why not X |
|---|---|---|---|
| Language/framework | **Python 3.12 + Flask 3** | Small team knows it; sync request model is easy to reason about; enormous extension ecosystem | **Django** ships an ORM/admin we'd fight (our schema is custom; its admin UI hides the data-engineering work); **FastAPI** is great for pure APIs but we need server-rendered pages + sessions + templates for a public portal — a SPA would double the work |
| Database | **PostgreSQL (Supabase)** | Relational integrity for 23 interlocked tables (bins→telemetry→incidents→work orders), transactional, JSONB where needed; Supabase = free managed Postgres + connection pooler | **MongoDB**: our data is highly relational (foreign keys everywhere), no schema-flex need; **MySQL**: fine, but Postgres adds JSONB, better window functions for analytics, RLS policies we ship (`rls_policies.sql`) |
| Real-time | **Flask-SocketIO + gevent** | Live bin levels/incidents on the admin wall; gevent workers give cheap concurrency on 1 vCPU | **Celery/websockets separate service**: another moving part on a free-tier budget; Socket.IO reuses the same process (worker thread) |
| Background jobs | **RQ over Redis** (in-process worker fallback) | Durable queue for SMS/email/webhooks/exports with **per-job retry policies + dead-letter dashboard**; degrades to inline when Redis absent (tests/dev) | **Celery**: heavier, needs its own broker+beat process; we only need simple retryable jobs, and RQ's failed-registry gives us ops visibility for free |
| Cache/limits | Redis (optional) + **Flask-Limiter** | Rate-limit login/OTP endpoints, cache hot reads; graceful no-Redis mode | — |
| Auth/security | Flask-Login, **Flask-WTF CSRF**, Flask-Talisman, hashed OTPs, account lockout, signed tracking tokens (itsdangerous), HMAC IoT ingestion | Defense-in-depth on a civic system that stores citizen phones | JWT: we're a cookie-session server-rendered app; sessions revocation is simpler than token rotation |
| Payments | **Razorpay + UPI** | India-native, UPI-first, webhook-capture flow with receipts | Stripe: no UPI autopay depth for small municipalities, harder KYC |
| Messaging | **Meta WhatsApp Cloud API → Twilio → SMTP email** chain | WhatsApp is free in the citizen's 24h service window (Rs 0 at panchayat volumes), no DLT sandbox hassle; Twilio as business-initiated fallback; email (Gmail SMTP/Brevo) last — and now an explicit **"Email me the code"** MFA option | **MSG91/DLT SMS** routes need DLT registration and per-SMS cost; WhatsApp-first is both cheaper and what residents actually read |
| ML | **scikit-learn RandomForest** for tabular telemetry (RandomForestClassifier ward miss-risk, RandomForestRegressor fill-rate, linear velocity fit for overflow ETA) + a **PyTorch-trained MobileNetV3 (ONNX)** for garbage-vs-non-garbage photo verification | Tabular telemetry → forests train in seconds in-process, resist overfit on small data, need no feature scaling, ship as pickled `.pkl` artifacts with a transparent heuristic fallback; the photo model is the one place deep learning earns its keep (transfer learning on ~4,300 images, 6 MB ONNX, CPU inference) | **TensorFlow**: heavier runtime for the same ONNX result; **XGBoost/LightGBM**: extra dependency for a marginal delta at this data size; **HistGradientBoosting**: our features are always complete, so its NaN handling buys nothing |
| Frontend | Jinja2 templates (46), Bootstrap 5, vanilla JS (admin.js, offline.js, chatbot.js), **service-worker PWA** | Zero build step — the Panchayat's volunteers can edit templates without a node toolchain | React/Vue SPA: build pipeline + SEO loss + no offline story without extra work; we already get installability + offline via SW |
| Tests | pytest, **359 tests** across 8 suites, pgserver-embedded Postgres — **all green** on a full local run and gating every branch push via the `tests` workflow | Tests run against *real* Postgres (not sqlite mocks), so migration/RLS bugs surface locally; CI runs the identical harness (`run_pg_suite.py`) | — |
| Observability | structlog, Sentry (prod-only), `/health` (DB+queue posture+worker+mail checks, incl. a starvation **warning** when Redis is configured with zero live workers), Prometheus-style `/metrics` job counters | Reviewer-visible ops story: failed jobs alert admins in-app before anyone complains | — |
| Deploy | **Docker on Render** (gunicorn+gevent, 2 workers), `render.yaml` IaC, health-check `/health` | Reproducible image; one free web service; in-process RQ worker avoids the $7/mo worker service | Heroku (paid), Vercel (not for long-running Socket.IO + RQ) |

**Q. Why is the DB "Postgres-only"? (code refuses sqlite)**
Bin telemetry queries use Postgres window functions and JSONB; tests run on embedded pgserver so dev
and prod run the *same* engine — no "works in dev, breaks in prod" class of bug.

**Q. Why so many Flask extensions — isn't that fragile?**
Each maps to a named production concern (CSRF, rate-limit, sessions, compress, talisman). All are
pinned in `requirements.txt`, and the factory wires them conditionally so a missing optional
dependency (e.g. Redis) degrades instead of crashing.

---

## 3. Datasets — what data exists, where it came from, and honesty about it

**Q. What datasets power the system?**
1. **Field/primary data (survey):** community interviews + field observation of the 5 wards — ward
   boundaries, street-level collection days/time slots per vehicle (CV-01…CV-05), pickup pain points.
   This became the seeded `schedules` table (10 rows) and the ward list.
2. **Smart-bin telemetry:** ultrasonic fill level %, temperature, methane ppm, battery, tilt/ping
   cadence from the 10 seeded bins (BIN-101…502) via HMAC-signed `/api/iot/telemetry` pings.
3. **Synthetic historical grid (600 rows):** the review-honest part — **no Panchayat has last year's
   per-bin history**, so we generated a 48h-per-bin ramping telemetry grid to give the fill-rate model
   *velocity* data on a fresh install. It is **documented as a limitation** (deck: Challenges; docx §7),
   and the moment real pings accumulate the model retrains on live data only.
4. **Operational seed data:** incidents (fire/methane/tilt), worker geofences, offload logs with
   impurity flags, declarations, PAYT invoice — enough for every dashboard to demonstrate real flows.

**Q. Is the data real?**
Schedules/wards/contacts: **real, from field observation**. Bin telemetry on the live demo:
**seeded simulation** driven through the *real* ingestion path (same HMAC endpoint a real ESP32 would
call). We never claim production telemetry; the claim is the *pipeline* is production-real.

**Q. Dataset size — isn't 600 rows too small for ML?**
For tabular gradient boosting, 600 rows × 6 features is enough for a calibrated first model, and
`model_retraining_job` retrains as telemetry accumulates. We explicitly chose models that degrade
gracefully and expose confidence, not a deep net pretending to know more than the data does.

---

## 4. ML — why each model, and what it's *for*

| Model (in `app/ml_model.py`) | Input → Output | Why THIS model | Used by |
|---|---|---|---|
| **Fill-rate + overflow ETA** (`predict_overflow_eta_hours` + RandomForestRegressor `ml_fill_model.pkl`) | Recent level pings (least-squares velocity over the last window) + ML blend → hours-to-95% | Velocity fit is interpretable and zero-latency on a fresh install; the forest learns from accumulated pings as they arrive; both degrade gracefully to the linear path | Route prioritisation, citizen "bin full?" hints, dispatch queue ranking |
| **Ward miss predictor** (`predict_miss` + RandomForestClassifier `ml_model.pkl`) | day_of_week, season_idx (live wttr.in weather override), complaints_last7, ward_id → miss-risk flag | Trained forest on operational history with a **transparent heuristic fallback** (≥3 complaints/week or monsoon ⇒ elevated) so `/schedule` NEVER errors when the artifact is missing | Schedule page early-warning badge |
| **Rule-based incident triggers** (`app/routes/iot.py`) | level/temperature/methane thresholds per ping → fire/methane/overflow incidents + stuck-sensor classifier | Incident thresholds are physics, not statistics — deterministic, auditable, zero false-negative risk from a model; the "stuck sensor" detector (constant ≥95% across 5 pings) is a data-quality guard | Incident feed, emergency webhooks |
| **Route ranking** (deterministic + ETA blend, `/api/route-optimize`) | Bins × ETA × road-distance cost | Reproducible, explainable ordering — a worker must trust and argue with a route | Worker route |
| **Photo garbage classifier** (`_ai_verify_photo` + MobileNetV3-Small `photo_classifier.onnx`) | citizen photo upload → garbage / non-garbage + probability | Transfer learning beats from-scratch on ~4,300 images (hard negatives included); runs in-process on CPU via onnxruntime (6.3 MB, single-threaded) with **fail-open** semantics — a model outage can never block a report | /report + /report-illegal upload gates |

**Q. Why not a neural net / LSTM for prediction?**
No long history (the dataset question above), 512 MB container, and the decisions ("empty bin X
first", "this ward may be missed") need **explainability**. Random forests + simple physics beat an
untrainable LSTM here. The honest line: *we sized the model to the data, not the fashion.*

**Q. Why Random Forest specifically (a panel favourite)?**
Bagged decision trees average out noise, so they don't overfit our 600-row history the way a deep
net would; they need **no feature scaling** (mixed units: %, ppm, °C, weekday); they give
**feature importances** a reviewer can inspect; and a forest retrain inside the app process takes
seconds — required by `model_retraining_job` on a 512 MB free-tier container. Artifacts are pickled
(`ml_model.pkl` classifier, `ml_fill_model.pkl` regressor) and hot-swapped with atomic rename.

**Q. Are the artifacts reproducible from the repo?**
Yes — every model is one command away. `python train_model.py` rebuilds both telemetry forests
with the exact inference-time feature contracts, evaluates on a held-out split and sanity-probes
before saving; `scripts/fetch_photo_dataset.py --hard-negatives 250 && scripts/train_photo_classifier.py --hard-neg-oversample 1` refetches
the ~4,300-image dataset (TrashNet + COCO + Wikimedia hard negatives: landfill/dumpster
dump-yards and clean street scenes, added after production showed dump-yard photos were
bounced) and retrains the photo classifier (a torch checkpoint is kept so re-exports never
retrain). Every artifact ships inside the Docker image — including
`ml_fill_model.pkl`, which a `.dockerignore` rule once excluded and silently pushed prod onto
the heuristic ETA path; the build now carries every trained model.

**Q. How do models stay current?**
`model_retraining_job` (RQ, retry policy 600s) retrains from the telemetry log on schedule; the
job-metrics dashboard shows retrain outcomes; a failed retrain alerts admins (dead-letter alerting).

---

## 5. Traffic & capacity — the numbers a project head asks for

**Q. How much traffic can the live deployment handle?**
- **Current free-tier shape:** Render web service, Docker, **2 gunicorn gevent workers**,
  Supabase Postgres through its pooler, Socket.IO in-process.
- **Realistic capacity:** gevent multiplexes I/O-bound requests; with p95 page renders ~120–180 ms
  (cached reads faster), one gevent worker sustains roughly **50–80 concurrent I/O-bound requests**;
  two workers ≈ **100–160 concurrent**, i.e. on the order of **150k–300k requests/day** for this
  request mix (mostly schedule checks + telemetry writes). Peak-hour behaviour is smoothed by:
  **Flask-Compress**, Redis cache of hot reads, HTTP caching, and the **service worker serving the
  shell offline** (repeat visits don't even hit the server for static).
- **The choke points we identified and handled:** the DB is the first ceiling (pooler caps
  connections) → we cache and batch; Socket.IO long-polls are pinned to one worker family → Redis
  message queue shares state; background sends must never hold a request thread → RQ queue.
- **If the Panchayat scaled to all of Vizianagaram (~2 lakh residents):** horizontal path is already
  built — stateless app containers behind load balancer, Redis for rate-limit/socket state, RQ
  worker processes separated (`RQ_IN_PROCESS_WORKER=false` + worker service), Postgres read replicas.
  No code rewrite, only config.
- **Measured guardrails:** `/health` (checks DB, mail path, storage, and the queue — a Redis backend with zero live workers is reported as a loud **"queued jobs will not run"** warning instead of a green flash),
  `/metrics` job counters, Sentry-only-in-prod, in-app dead-letter alerts.

**Q. What happens when traffic spikes (collection-day morning)?**
Reads are cacheable and the PWA shell is local; writes (telemetry pings) are tiny HMAC POSTs batched
per bin; the rate limiter protects auth endpoints specifically (10 OTPs/hour, 30 MFA/min) so an
attacker can't crowd out residents.

---

## 6. Security & governance quick answers

- **OTPs:** 6-digit `secrets`-generated, **SHA-256 hashed at rest**, 5-min TTL, brute-force counts
  toward account lockout, delivered via WhatsApp→SMS→**email** chain (staff can force email).
- **IoT ingestion:** every telemetry POST must carry an **HMAC-SHA256 signature** (`IOT_TELEMETRY_SECRET`)
  with timestamp tolerance — a spoofed bin can't poison the model.
- **Complaint tracking:** 90-day **signed tokens** (itsdangerous) — complaint IDs can't be enumerated.
- **CSRF** on every form (bucketed time-window tokens), **Talisman** security headers, sessions
  regenerated at login (fixation defense), audit log on privileged actions, RLS policies shipped.
- **Payments:** Razorpay webhook signature verification; receipts generated off-request-path.
- **Privacy:** phones are the only PII; leaderboard shows usernames only; data-export/retention jobs
  run on schedule.

---

## 6A. Inputs & data integrity — the questions a sharp reviewer asks

**Q. How many people can register with the same mobile number or email?**
**Exactly one account per phone number and one per email — enforced by the database, not just the form.**
Three layers of defence (`app/routes/auth.py: register` + migration `l1m2n3o4p5q6`):
1. **Friendly pre-check** — `User.query.filter_by(...)` rejects a duplicate username/phone/email with a clear message before inserting.
2. **Race guard** — two people submitting the same phone at the same instant both pass the pre-check; the INSERT is wrapped in `try/except IntegrityError`, so the loser gets the same friendly message instead of a duplicate row (a classic TOCTOU hole, closed).
3. **DB law** — unique indexes **`uq_user_phone`** and **`uq_user_email`** on the `user` table. Even raw SQL or a bug cannot create a second account with the same identifier.
- **NULLs are distinct in Postgres:** accounts legitimately without a phone or email (phone-OTP registrations, informal waste-pickers via `/register/picker`) can still coexist.
- **Why the demo worker email differs:** because of `uq_user_email`, `seed_db.py` now registers **admin → jaganmohan08112005@gmail.com, worker → rama18072005@gmail.com** (sharing one address would fail the seed).
- **No duplicates via formatting:** `validate_indian_phone()` normalises every input to `+91XXXXXXXXXX`, so `98765 43210`, `+919876543210` and `919876543210` are **the same identifier**; fake numbers (all-same digits like `9999999999`, sequential runs like `1234567890`) are rejected; emails are lower-cased before comparison (legacy rows were normalised by the migration). Username is unique + non-null (≤ 100 chars) by the first migration.
- Registration endpoint is rate-limited to **10/hour/IP**.
**Sound-bite:** *"One phone, one email, one account — the form is friendly, the transaction is guarded, and the database is the final law."*

**Q. Does the site take only garbage images? How are images differentiated?**
**Images-only is enforced; garbage-vs-not-garbage *content* classification is an honest roadmap item.**
- Every photo passes `save_compressed_photo()` (`app/routes/__init__.py`): it is opened with **Pillow and must decode as a real image — fail-closed**. An `.exe/.php/.html` arriving with a `.jpg` extension is rejected and never stored (the old fallback stored raw bytes — an audit finding, now fixed). A complaint with an unreadable photo still files; it just carries no image.
- The photo is re-encoded to RGB JPEG (1280 px longest edge, q=82): **all EXIF is stripped**, including location — privacy by construction.
- **Anti-fake-report cross-check:** before compression, EXIF GPS is read and compared to the submitter's device GPS (haversine). More than **100 m apart** (`GPS_VERIFY_RADIUS_M`) → rejected: *"Photo location does not match your device location — submit a live, on-site photo."* Screenshots and internet images have no matching GPS, so they fail this check.
- `_ai_verify_photo()` **runs a trained garbage-vs-non-garbage classifier**: a MobileNetV3-Small fine-tuned on TrashNet (waste) vs. COCO val2017 + Wikimedia hard negatives (landfill/dumpster dump-yards, clean street scenes) — ~4,300 images, **96.6% validation accuracy** (direct-resize eval matching the runtime contract; 98.3% of non-waste uploads refused incl. dump-yard scenes) — exported to a 6.3 MB ONNX file that ships in the Docker image and runs in-process via onnxruntime. Uploads scoring high non-waste probability are rejected with the score in the message (`PHOTO_CLASSIFIER_THRESHOLD`, 0.6 in prod), and any model error fails **open** to the decodability gate, so an inference outage can never block a citizen report. Both citizen upload surfaces — `/report` and the anonymous `/report-illegal` — run this gate; worker after-photos are exempt because they photograph the *cleared* site. Fully reproducible: `scripts/fetch_photo_dataset.py` → `scripts/train_photo_classifier.py`.
- **Close-the-loop proof:** a worker can only clear a bin/ticket by uploading a **live after-photo** — the same image pipeline validates it.
- Storage posture: **Supabase Storage → Cloudinary → persistent disk**; a write to ephemeral `/tmp` in production is refused and alerts admins rather than silently losing photos.
**Sound-bite:** *"We guarantee every upload is a real, on-site, metadata-stripped image; a garbage-vs-junk classifier is the next drop-in upgrade, and the pipeline is already waiting for it."*

**Q. What are ALL the inputs the system accepts?**
| Surface | Inputs (all length-fitted with `fit_length`, all forms CSRF-protected, all rate-limited) |
|---|---|
| **Identity** | username (≤100, unique), password (≥8, ≠ username), role (whitelisted `citizen\|worker\|admin`, anything else → citizen), email (valid, ≤120, unique, lower-cased), phone (Indian 6–9-start, normalised, unique); informal-picker variant (name/password/phone/area ≤100) |
| **Citizen content** | complaint (ward, address, description, GPS lat/lon, photo, report time), illegal-dump report (category, entity name/type, photo), 4-stream waste declarations (wet/dry/sanitary/hazardous weights), BWG bulk-pickup requests, PAYT payments (Razorpay order → verify → confirm), complaint reopen + satisfaction survey via signed token, data-deletion requests, notification preferences, push subscriptions, reward redemptions |
| **Worker / IoT** | pickup confirmations (PIN/scan), mandatory after-photos, offload logs (dump yard, impurity flags), bin-issue reports, worker GPS; telemetry POSTs `{hardware_id, level, temperature, methane, battery_level}` **HMAC-SHA256-signed**; device registration (unique hardware_id) |
| **Admin / ops** | worker assignment, complaint resolution, maintenance orders (notes ≤300), refunds/waivers (reason ≤200), firmware uploads (version + **magic-byte check** so a `.bin` can't be an HTML payload), webhook URLs (SSRF-blocked hosts), data-deletion approvals, BWG approvals, exports (CSV/PDF/JSON) |
| **System** | consent record, page feedback, CSP violation reports, cookie settings |

**Q. Walk me through the system design — front end, back end, connectivity, speed, security.**
```
   Browsers/PWA (citizen·worker·admin, offline-first service worker)
        │ HTTPS (Cloudflare edge → Render)
        ▼
   Flask 3 app factory ── 9 blueprints, 131 routes ── gunicorn + gevent (2 workers)
     │            │             │
     ▼            ▼             ▼
 PostgreSQL    Redis + RQ     Socket.IO
 (Supabase,    (rate-limit,   (live bin tiles, incident feed,
  23 tables,    cache, jobs    complaint pushes)
  29 migrations) w/ retries)
     ▲
     │ HMAC-signed telemetry every ping
   ESP32 smart bins (BIN-101…502)

   Outbound jobs: WhatsApp→SMS→email OTP, push notifications, PDF receipts,
   state-compliance exports, ML retraining (600-row history + live pings)
   Inbound webhooks: Razorpay payments (signature-verified)
```
- **Front end:** 46 Jinja2 templates, Bootstrap 5, vanilla JS (no build step), installable PWA with offline shell + IndexedDB queue, bilingual English/Telugu, WCAG-minded.
- **Back end:** app factory + blueprints (public, citizen, worker, admin, auth, analytics, iot, webhook, worker_resolve); SQLAlchemy over Postgres; Flask-Migrate/Alembic evolution; RQ background jobs with per-job retry + dead-letter dashboard.
- **Connectivity:** every channel above; graceful degradation is designed-in — no Redis → in-process queue; no WhatsApp/Twilio keys → **email OTP path always works**; no Cloudinary → Supabase; no network at all → service worker + background sync.
- **Speed:** Flask-Compress, cached hot reads, Postgres pooler, offline shell for repeat visits, p95 page render ~120–180 ms on the free tier (see §5 for capacity).
- **Security:** the full picture is §6 — hashed OTPs, HMAC devices, signed tracking tokens, CSRF + Talisman + CSP, lockouts, audit log, RLS policies.

---

## 7. Rapid-fire (the questions panels actually ask)

- **Team size / your part?** Batch of 4 (rolls 24331A4441/4434/4446/4426) — full-stack shared;
  23 tables, 29 migrations, 359 tests, and 3 retrainable ML artifacts
  (`train_model.py` + `scripts/train_photo_classifier.py`) are the artefact trail.
- **Cost to run?** ₹0 today: Render free web + Supabase free Postgres; WhatsApp service messages free;
  Redis optional (in-process fallback). First paid step only if scaling beyond one ward cluster.
- **What's not real / limitations?** Seeded telemetry + 600-row synthetic history (documented);
  payments in demo mode; SMS gateway needs env keys on a fresh deploy (email OTP path always works).
- **Biggest engineering challenge?** Making the *free tier reliable*: queue-without-worker starvation,
  rate-limit multiplication across gevent workers, single-event-loop stalls — all fixed and documented
  in `render.yaml` comments with the measurements that forced each decision.
- **What would you build next?** Live ESP32 firmware on real bins (OTA channel already in the admin),
  route optimisation as a nightly job, ward-level analytics API for the district office.
- **Why "Data Science" branch fits:** the portal is the *data producer*; the ML layer (ETA, anomaly,
  miss prediction) and the transparency dashboards are the *data consumer* — the project is a
  full data-engineering loop, not just a CRUD site.

---

*Prepared for the internal review — answers here mirror the code as of this revision
(email-OTP MFA option included; see `app/routes/auth.py: mfa-resend`, `seed_db.py` for credentials).
Reviewed & verified against source: unique phone/email enforcement (`l1m2n3o4p5q6`), image pipeline
(`save_compressed_photo`), input inventory per blueprint, 131 routes / 29 migrations / 359 tests,
and model artifacts (`ml_model.pkl` RandomForestClassifier, `ml_fill_model.pkl`
RandomForestRegressor — inspected from the pickles themselves).*
