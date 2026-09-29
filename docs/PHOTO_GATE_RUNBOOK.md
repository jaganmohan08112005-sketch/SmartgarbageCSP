# Photo-Gate Operations Runbook

The anti-fake-report photo gate runs on **both citizen upload surfaces**
(`/report` and the anonymous `/report-illegal`). This runbook covers
everything an operator needs: reading `/health`, forcing the gate off,
tuning the threshold, monitoring, and rebuilding the model from the repo.

---

## 1. What `/health` says about the gate

`GET /health` → `checks.photo_classifier`:

```json
"photo_classifier": {"detail": "photo_classifier.onnx, 2 classes", "status": "active"}
```

| `status`      | Meaning                                                                 | Action                                                     |
|---------------|-------------------------------------------------------------------------|------------------------------------------------------------|
| `active`      | ONNX session loaded; every upload is being classified                   | Nothing — this is healthy                                  |
| `off`         | Explicitly disabled via `PHOTO_CLASSIFIER_MODEL=off` (see §2)            | Expected only if someone turned it off deliberately        |
| `unloaded`    | Not yet loaded in this process (also shown when a stale env path fell back to the bundled artifact) | Hit `/health` again — the check forces the lazy load and warms the session |
| `error`       | Model file unreadable / ONNX runtime failure — the gate **fails open** (only the decodability gate is enforcing) | Check `detail` in the same object; redeploy or roll back. The canary (§4) will also be firing |

Reading the detail string:

- `photo_classifier.onnx, 2 classes` — bundled artifact loaded (normal).
- `env path missing: <path>; using bundled` — a dashboard env var points at
  a file that doesn't exist in the container; the loader fell back to the
  bundled model. Remove the stale env var or fix the path.
- Anything else is the load exception (`error` mode).

Note: `/health` **forces** the lazy load, so it both reports and warms the
classifier — the first citizen upload after a deploy pays no cold start.

## 2. Force the gate off (kill switch)

Set the env var `PHOTO_CLASSIFIER_MODEL` in the Render dashboard to one of:
`off`, `none`, `disabled`, `0`.

- Deployed enablement is **code-level** (the bundled `app/photo_classifier.onnx`
  IS the switch), so an env-var ADD/CHANGE needs a Render dashboard apply or
  a redeploy to take effect — the Blueprint `render.yaml` intentionally does
  not set these vars.
- To restore: remove the env var (bundled artifact resumes) or set it to a
  valid ONNX path.
- While off, the **decodability gate stays on** (uploads must still decode as
  real images), and `/health` reports `status: "off"` with
  `detail: "disabled via PHOTO_CLASSIFIER_MODEL"`.
- The canary (§4) treats "probe not rejected" as a breach — if you disable
  the gate deliberately, expect (and can ignore) the daily canary alert, or
  also stop the canary by not scheduling it (see §4).

There is no threshold env var needed to disable classification only: setting
`PHOTO_CLASSIFIER_THRESHOLD=1.1` effectively accepts everything while still
running inference (useful for shadow-mode measurements).

## 3. Threshold tuning

Accept rule: an upload passes when `p(garbage) > PHOTO_CLASSIFIER_THRESHOLD`
(default **0.3**, ROC-chosen — see below). Override via the dashboard env var.

The operating point was chosen from the validation-set ROC (AUC 0.9959):
non-garbage rejection is **flat at 0.983 across thresholds 0.25–0.65**, while
waste-photo acceptance climbs as the threshold drops. 0.30 sits mid-plateau:
3.0% of genuine waste photos are bounced (vs 6.0% at the old 0.6) at
unchanged strictness. Lower than ~0.25 starts eroding strictness (0.977 at
0.10, 0.973 at 0.05) — only go there if the rejection panel (§5) shows
residual false positives and the panchayat tolerates more fake reports.

## 4. Monitoring: the photo-gate canary

Every 30 minutes (deployed Render environments only) `photo_gate_canary_job`
POSTs an embedded ~7 KB non-garbage probe photo to the **live**
`/report-illegal` and verifies the response lands on `?photo=rejected` with
the rejection banner. Failures (probe accepted, banner missing, HTTP error)
raise → RQ retries once after 2 min → admins get an in-app **Notification**
(deduped to at most one per UTC day) and a `PHOTO_GATE_BREACH` webhook; each
run's outcome also shows up on `/health` → `jobs.per_function` as
`photo_gate_canary_job`.

Why a canary: `/health` only proves the model *file* loads; the canary proves
the **request path** still enforces the gate — the exact failure class that
once shipped silently (a wrong bundled-path lookup disabled prod for weeks).

- Local/CI: the job no-ops (returns `False`) unless `RENDER=true` or an
  explicit `base_url` is passed.
- `PHOTO_GATE_CANARY_URL` — override the probed base URL.
- `PHOTO_GATE_CANARY_TIMEOUT` — HTTP timeout in seconds (default 60).
- The probe self-identifies (`description: "PHOTO-GATE CANARY probe..."`) so
  canary traffic is distinguishable from abuse in the rejection panel.

## 5. The admin rejection panel

`/admin/photo-rejections` lists every refusal with a thumbnail, surface,
stage (`classifier` / `decodability`), the verifier note including the
p-score, and time. Use it to:

- **Spot false positives**: a "does not look like waste" thumbnail that is
  obviously waste is a miss — feed similar scenes into the next retraining
  round as garbage examples (and consider lowering the threshold a notch).
- Track rejection volume per surface and stage.
- Each canary alert links here (`#canary-YYYYMMDD`).

Privacy: the only stored identifier is a salted SHA-256 fingerprint of
(IP + user-agent); thumbnails are ~112 px JPEGs kept in the DB, and the log
self-prunes to the newest 500 rows.

## 6. Retrain / re-export the ONNX model

One-time env: `PYTHONUTF8=1` (Windows), `onnxscript` installed (ONNX export).

```bash
# 1. (Re)build the dataset: TrashNet garbage + COCO val2017 non-garbage
#    + Wikimedia hard negatives (dump-yards, dumpsters, clean streets).
venv/Scripts/python.exe scripts/fetch_photo_dataset.py --hard-negatives 250

# 2. Train (3 epochs, CPU) and export app/photo_classifier.onnx + sidecar.
#    --hard-neg-oversample 1 duplicates the scarce hard negatives once.
venv/Scripts/python.exe scripts/train_photo_classifier.py --hard-neg-oversample 1

# 3. Evaluate BEFORE shipping: val accuracy must be >= the previous model's,
#    garbage-accept must not collapse (an earlier retrain hit 0.825 and was
#    discarded). The val transform matches the runtime contract (direct
#    resize), so offline numbers reflect production.
# 4. Commit app/photo_classifier.onnx + .onnx.json; deploy runs the rest.
```

- The torch checkpoint (`app/photo_classifier.pt`, git-ignored) enables
  `--export-only` re-exports without retraining.
- The sidecar JSON carries labels + preprocessing; the runtime picks the
  reject class by name (`non`/`clean`/`not`).
- **Rollback**: the previous ONNX is in git history — `git revert` the model
  commit and redeploy (the gate fails open meanwhile; the canary will be
  alerting until the rollback lands).
- After any retrain, re-run the ROC sweep (§3) — the optimal threshold moves
  with the model.

## 7. Known-gotcha history (do not re-learn these the hard way)

1. **Bundled-path bug**: the loader once looked in `app/routes/` instead of
   `app/` → prod ran with the gate off. Fixed; the canary exists because of
   this class of bug.
2. **Render Blueprint env vars don't auto-apply** — enablement is code-level
   by design; dashboard edits need an explicit apply.
3. **Fail-open semantics are intentional**: a model outage must never block
   citizen reports. That means a silent outage is only visible via `/health`
   (`error`) and the canary — watch both.
