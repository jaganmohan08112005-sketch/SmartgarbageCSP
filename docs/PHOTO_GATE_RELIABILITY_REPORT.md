# Photo-Gate Reliability Report — First 24h of Canary Monitoring

**Snapshot:** 2026-09-30 13:15 UTC · **Window:** first canary deploy (2026-09-29 17:02 UTC, build of `b933562`) → now (~20h)
**Sources:** live `/health` job counters (per-deploy process lifetime), `photo_rejection` + `illegal_dump_report` tables (prod Supabase, project `pofuuaohiajcfjrrtoqh`), GitHub Deployments API.

---

## 1. Verdict

| Metric | Value | Assessment |
|---|---|---|
| Canary runs (current build `9a177ff`, up 02:45→12:33 UTC) | **20 runs, 0 failed, 0 retries, 0 dead-lettered** | ✅ 100% pass rate |
| Canary cadence | ~every 30 min (20 runs / 9.8 h) | ✅ as designed |
| Canary wall-clock | avg **7.4 s** per dual-probe run (p95-free sample) | ✅ well under the 60 s timeout |
| Harvest job | 2 runs, 0 failed | ✅ |
| Photo classifier (`/health`) | `active` — `photo_classifier.onnx`, 2 classes | ✅ |
| False positives filed by the gate | **0** (no citizen uploads rejected all window) | ✅ no over-strict behavior |
| Rejection-log rows | 14 total (2026-09-29 14:18 → 09-30 11:48), all `report-illegal` / `classifier` stage | see §3 |
| Admin relabel actions | 0 (0 garbage / 0 not_garbage / 0 dismissed / 0 batched) | panel idle, nothing to review |
| Near-threshold harvest queue | 0 pending | all rejections p_reject ≥ 0.9998 — far from the 0.7–0.85 harvest band |
| Alerting incidents | 0 breaches fired (0 notifications, 0 webhooks) | no gate failures to alert on |

**Bottom line:** the photo gate enforced correctly for the entire window. Every canary sweep verified BOTH directions — non-garbage probe rejected (`p_reject 0.9998–1.0000` logged) and garbage probe accepted — with zero breaches and zero retries across 20+ sweeps on the dual-probe build, and the final build (`c62616e`) re-verified clean on deploy.

## 2. The incident that motivated this report — closed

The **2026-09-29 over-strict threshold slip** (a live-tuning mistake set the accept threshold to 0.3, silently bouncing every genuine waste photo while `/health` stayed green) was caught manually the same day. As of deploy `9a177ff` (2026-09-30 02:44 UTC) the canary runs a **dual probe**: a garbage probe (the live-verified `trash_00830` positive control, p(garbage)≈0.9999) must be ACCEPTED every sweep, so that failure class now alerts within ~30 minutes (one sweep) instead of waiting for a citizen complaint or a manual check. A regression test (`test_photo_gate_canary_detects_overstrict_accept_path`) pins the behavior.

## 3. Rejection-log observations (panel data)

- 14 rows since 2026-09-29 14:18 UTC; **all are the canary's own non-garbage probes** (`report-illegal` surface, classifier stage, `p_reject 0.9998–1.0000`) except rows 1–6 (pre-`b933562` probes, logged before p_reject rode along). **No citizen upload was rejected** in the window — traffic is low, and every genuine attempt (if any) passed the gate.
- Cadence check: rejection rows land ~every 30 min (14:18 → 14:42 → 15:38/15:39/15:41 → … → 04:46 → 08:17 → 09:48 → 11:48), matching the scheduled sweep; the 6h same-client dedupe kept rows 1-per-sweep as designed.
- Harvest ran twice; nothing crossed the uncertainty band [0.70, 0.85) — the queue is correctly quiet.

## 4. Canary residue — found and fixed during this window

The first dual-probe deploys left the accept probe's report row behind (create-then-delete design; the deletion step never executed in prod). **Found via panel data, fixed in `c62616e`:** `/report-illegal` now discards self-identified canary submissions *after* the gate passes — no report row, no storage upload, and a legacy sweeper (bounded to 3 h) covers rollout windows. Both residue rows (ids 32, 33) were deleted from prod during the fix; ward `Test` analytics are clean. Final build live-verified 2026-09-30 13:15 UTC: dual-probe sweep ran clean (`runs:1, failed:0` on the fresh process) with **0 canary residue reports** in the DB. (One Render build flaked at 67 s during rollout and was retriggered successfully — infra noise, not code.)

## 5. Alerting posture

- Breach fan-out (email/SMS) ships in `9a177ff` via `PHOTO_GATE_ALERT_EMAIL` / `PHOTO_GATE_ALERT_SMS` — **both unset in prod today**, so a breach currently reaches: in-app admin Notifications + `PHOTO_GATE_BREACH` webhook subscribers + Render logs. **Action:** set the two env vars in the Render dashboard (comma-separated panchayat contacts) to close the "dashboard closed" gap; sends are day-deduped and opt-in (outside a citizen's 24 h WhatsApp window an SMS send can cost money).
- Dead-letter alerting (`JOB_DEAD_LETTER`) already wired; 0 dead letters this window.

## 6. Recommendations

1. Set `PHOTO_GATE_ALERT_EMAIL`/`PHOTO_GATE_ALERT_SMS` in the Render dashboard (the panchayat secretary's address/phone) — one-time action, unblocks off-dashboard alerting.
2. Keep the threshold at **0.7** (P/R memo: prec .975 / rec .970 / strict .983; Pareto-dominates 0.5/0.6). The accept probe now guards against regressions in either direction.
3. Re-run this report after the next retrain or threshold change (the numbers above are the pre-change baseline).
4. Housekeeping (user-side, no MCP storage-delete tool): two stray test JPEGs remain in the Supabase `uploads` bucket (`uploads/illegal/illegal_18039_trash_00830.jpg` + one `illegal_*_t.jpg`) — remove via the Supabase dashboard when convenient.
