# Project audit — consistency, functioning, cruft, real-world comparison

Date: 2026-10-16 · Scope: whole repo (code, tests, docs, deliverables) · Method: static scans
(standard-library Python: byte-duplication, template/endpoint cross-referencing, dependency
cross-check, code-zip manifest reconciliation), the CI-identical test harness
(`run_pg_suite.py`), and two web-research briefs (smart-waste product landscape; Flask-on-Render
operations and security baselines). All figures below are measured, not estimated.

## 1. Functioning verdict

| Run | Result | Meaning |
|---|---|---|
| plain `pytest -q` (no DB) | 3 failed, 98 passed, 361 errors (30.8 s) | The 361 "errors" are **by design**: `tests/qa/conftest.py` refuses to run without `TEST_DATABASE_URL` (a real PostgreSQL). This is the documented entry-point behavior — `run_pg_suite.py` is the sanctioned harness. Not a project defect. |
| 3 "DB-less failures" | `test_csrf_rejection_is_400_not_500_with_talisman_active`, `test_consent_endpoint_works_with_csrf_enabled`, `test_feedback_endpoint_works_with_csrf_enabled` | **Re-produced individually during the audit: same root cause as the 361 errors** — each test body checks `TEST_DATABASE_URL` itself and raises `RuntimeError('TEST_DATABASE_URL required...')` (e.g. `tests/test_features.py:6363`). Not CSRF/Talisman bugs; **genuine DB-less failures: 0**. |
| `run_pg_suite.py -q` (CI mirror, embedded Postgres) | **see §1.1** | The green/red signal that matches CI. |

### 1.1 PG-backed (CI-mirror) verdict — **now closed with the full run**

**Full run executed 2026-10-17:** `run_pg_suite.py -q` (embedded Postgres, sequential
`-n 0`, per-test schema rebuild) over the entire `tests/` tree, log-teed with pipefail:

> **462 passed, 0 failed, 0 errors, 0 skipped, 1 warning — exit 0 — in 0:45:28**
> (`[runner] PostgreSQL stopped; pytest exit code 0`; no stray postgres.exe processes
> afterwards, verified by process check).

The single remaining warning is a third-party `gotrue` package deprecation
(supabase SDK, `tests/test_features.py::test_worker_can_resolve_bin_with_after_photo_and_gps`)
— not the sqlite3 datetime-adapter class, which is *promoted to an error* suite-wide via
`pytest.ini` filterwarnings and CI `PYTHONWARNINGS` (this run is the live proof that guard
holds: zero adapter warnings anywhere in 462 tests).

End-to-end boot/run/teardown confirmed on the full suite: one persistent cluster booted,
all test files collected and executed against it (fixtures drop/recreate the schema per
test), and the runner's teardown stopped the cluster cleanly.

**Parallel verdict (2026-10-17, same harness, `-n auto`):** the sequential `-n 0` pass is
no longer required — each pytest-xdist worker now creates and owns its own database
(`sg_test_<worker>` in the same cluster, created by `tests/conftest.py` at worker start),
so the per-test `drop_all()`/`create_all()` cannot collide across workers. Two consecutive
full parallel runs on this machine:

> **Run A: 462 passed, 0 failed — 0:08:52 — exit 0** · **Run B: 462 passed, 0 failed — 0:08:34 — exit 0**

Identical results to the sequential 462-green baseline at **~5.2× speed** (45:28 → 8:34–8:52),
zero failures across both runs, no stray `postgres.exe`/`python.exe` after teardown, and no
new warning classes (only the third-party `gotrue` DeprecationWarning; its occurrence count
varies with which worker imports supabase first). Per-worker isolation was verified mid-run
by listing the cluster while workers were executing: six databases `sg_test_gw0`…`sg_test_gw5`,
each holding its own live sessions.

One parallel-only bug was found and fixed during this proof: `tests/test_features.py` does
`from tests.conftest import _complete_mfa`, which re-imports the conftest under a second
sys.modules key (`tests/` has no `__init__.py`) and re-ran the worker-database bootstrap
while the worker's own connections were open — dying deterministically with
`psycopg2.errors.ObjectInUse` (the "other session" was the worker itself; sequential runs
were immune because the bootstrap returns early without `PYTEST_XDIST_WORKER`). The
bootstrap is now guarded by a process-wide marker (`_SG_TEST_WORKER_DB` in
`tests/conftest.py`), which is why runs A and B above are green; the pre-fix parallel run
failed exactly that one test (461/462) every time — a bug, not a flake.

Earlier bounded verification (kept for provenance):

- The previously-errored feature tests + the CSRF trio
  (`waste_declaration_persists`, `photo_rejection_relabel_workflow`,
  `retrain_batch_export_marks_rows_once`, `harvest_flags_uncertain_and_notifies_once`,
  `consent_endpoint_works_with_csrf_enabled`, `csrf_rejection_is_400_not_500_with_talisman_active`,
  `feedback_endpoint_works` selection): **6 passed, 294 deselected, exit 0** (runner even
  self-recovered one stale cluster and re-initialised cleanly).
- Portal-flow breadth `tests/test_walkthrough.py`: **15 passed, exit 0**.
- The earlier DB-less pass: **98 passed, 0 genuine failures** (the 3 "failures" and 361
  "errors" were all the intentional no-`TEST_DATABASE_URL` guard).

Verdict: **functioning — no failing features found.** The previously-deferred full
CI-mirror run has now completed green (above); no release-grade test debt remains.

## 2. Consistency findings (repo-wide)

**Consistent (checks that passed):**
- Doc links: `scripts/check_doc_links.py` → `OK`, exit 0.
- Code-zip manifest `submission/_scratch/code_list.txt`: 411 entries, **0 dangling** (every
  listed file exists on disk).
- Templates: **no orphans.** `base.html`, `_icons.html`, `_breadcrumbs.html` are false
  positives from a render-only scan — they are referenced via `{% extends %}/{% include %}`
  from 404/about/admin pages and others. The `_qa/`, `report/_deck_qa/`, `report/_inputs/`
  HTML files are QA fixtures, not app templates.
- Endpoints: **no dead `url_for` targets.** `static` is Flask's built-in; the bare-`report`
  flag resolves to `citizen.py:740 def report` (registered). Every other referenced endpoint
  is defined.
- Video/deliverable chain (README · RUNBOOK · generator · sidecars · burned cut) was
  reconciled in the caption/video work of 2026-10-16; `test_make_subtitles.py` passes 16/16.

**Inconsistent / gaps (found, each a small targeted fix):**
1. `scripts/local_pg.py` and `tests/test_local_pg_helper.py` are **not in the code-zip
   manifest**, although the zip's README claims "tests, CI" and `run_pg_suite.py` (which the
   CI mirror uses) imports `scripts/local_pg.py`. Either add both to
   `code_list.txt` before the next zip rebuild, or document the exclusion explicitly.
2. `report/video/_burn_subtitles.py` (new tool) is likewise missing from the manifest — add
   it with the next `build_code_zip.py` refresh, or exclude by policy with a prose note.
3. `docs/INSPECTION_REPORT.md` is on disk but unlisted in the manifest; decide include/exclude.
4. `requirements.txt` pins many **transitive** packages (blinker, click, certifi, colorama,
   jinja2, markupsafe, urllib3, …). Harmless for reproducibility, but the file mixes direct
   and transitive pins without sections — if deliberate, mark transitives with a comment
   block so future editors don't prune wrong lines; otherwise narrow to direct deps.
5. `launch spikes on disk`: `playwright-report/index.html`, `pytest_full_tail.txt` at the repo
   root are generated run artifacts, untracked and unlisted — add `playwright-report/` and
   one-line scratch patterns to `.gitignore`, delete the strays.

## 3. Duplicates, unused, unrelated (measured)

| Item | Finding | Action |
|---|---|---|
| `app/static/icon-192.png` ≡ `app/static/icon-512.png` | **Byte-identical** (729 B each). One of them was never exported at 512 px. Browsers scale, PWA still installs, but the 512 entry is a copy — flag for a real 512 raster next time the manifest icons are touched. | Low-priority replace; zero runtime risk. |
| `app/static/uploads/**` | Thousands of demo artifacts; large byte-identical groups (most `after_*.jpg` collapse to one blob). Disk bloat only — **excluded from code zip and docs by design**; copying is how the seeded demo works. | Leave; consider a deduplicating seeder only if disk pressure appears. |
| `_dataset/**/*__dup1.jpg` | Intentional augmentation duplicates for ML training. | Leave. |
| `.kilo/`, `.kimi-memory/`, `.venv-1/`, `_archive/`, `_imgqa/` | Local environment debris (agent worktrees, a second venv, retired assets). None are referenced by project code; none are in git. | Safe local deletions when disk matters; keep `_archive` (retired report versions) until submission is accepted. |
| `requirements-dev.txt` vs runtime | Verified no runtime-only import missing at boot; heavy deps used only by tooling (torch, kagglehub, pptx, IPython, cloudinary imports appear in report/ML scripts) are guarded options, not web-runtime requirements. Runtime render path (`flask-limiter`, `flask-talisman`, `flask-compress`…) **is** imported and matching. | Keep as-is. |
| Files referenced by nothing | Scan found **no candidate orphan code files** (`.py/.html/.js/.css`) outside the QA-fixture directories and env debris above. | Nothing to delete from the deliverable chain. |

## 4. Real-world comparison (evidence-based)

Full briefs with URLs were compiled during this audit (smart-waste product landscape;
Flask/Render operations + OWASP baselines). Key comparisons against state of practice for a
small-town civic portal:

**Where the project matches or beats the practice baseline**
- Citizen complaint flow (photo + GPS, signed tracking page, SLA window, reopen, satisfaction
  rate) mirrors the Swachhata-MoHUA workflow (photo/location intake, assignment, reopening)
  and is closer to spec than most vendor demos: evidence gating (EXIF/photos), consent
  screens, and a privacy policy exist.
- Multilingual English + Telugu at the caption/narrative level; the practitioner guidance
  (MoHUA nine languages) makes deeper i18n of form fields/SMS the next step, not a gap in
  kind.
- PWA/offline-first service-worker work ships with tests (`tests/js/offline_queue.test.js`,
  `service_worker_fetch.test.js`) and complies with the network-first/cache-first split the
  MDN/Workbox references prescribe.
- Export/audit machinery (CSRD, CSR&D, state-portal compliance file, performance PDF) is the
  "audit accountability" tier reviewers say is table stakes for administration; having it
  differentiates the project from vendor-lite demos.

**Where reality would bite (document, don't oversell)**
- **Render free tier is demo-class:** free web services sleep after 15 min idle and take \
  ~1 min to wake; free Postgres expires after 30 days with no backups; local disk is
  ephemeral. The 15-minute GitHub Actions keep-alive ping is a hobby-deployment pattern —
  fine for the walkthrough, but the README/OPS pages should say "demo on free tier; paid
  always-on for production" explicitly, and production media must move to object storage.
- **Sensors ≠ ground truth.** The seeded `sensor_fault` scenario is exactly right; extend it
  with shown "last-seen at" staleness on bin cards if a reviewer asks about real rural
  deployments (connectivity, battery, LoRaWAN caveats).
- **GPS presence is not proof of collection** (the SWM-ops review's #1 pitfall). The portal
  already refuses reports "from nowhere" (GPS mandatory) — the same standard should be
  described for worker events if the docs promise verification.
- **Regulatory clock moved:** SWM Rules **2026** (S.O. 388(E), notified 2026-01-27, effective
  2026-04-01, four-stream segregation mandate) supersedes the 2016 Rules commonly cited in
  student projects. If docs cite "SWM Rules 2016" as *current*, update the citation to
  reference both rules with the transition — a one-paragraph keeper.
- **PAYT naming:** user-fee/flat-charge ≠ measured PAYT. The project's PAYT invoice module is
  a design showcase; docs should scope it ("tariff engine for a legal framework, not a
  live billing system") to match reviewer expectations.

## 5. Safe-cleanup list (ranked, risk-rated)

1. Delete root strays `pytest_full_tail.txt`, `playwright-report/` (regenerable), and this
   audit's own scratch (`scan_result.json`, `scan_err.txt`, `pytest_audit*.log`) — risk: none.
2. `.gitignore` additions: `playwright-report/`, `*.flow.log`-style scratch — risk: none.
3. Manifest additions (`code_list.txt`): `scripts/local_pg.py`, `tests/test_local_pg_helper.py`,
   `report/video/_burn_subtitles.py`, decide `docs/INSPECTION_REPORT.md` — risk: none (zip
   grows by 3 files; next `build_code_zip.py` rebuild applies it).
4. Comment the transitive pin block in `requirements.txt` — risk: none (doc-only).
5. Replace `icon-512.png` with a true 512 raster — risk: low; do before any PWA icon work.

No mass deletions were performed; every removal suggestion is listed here for a decision, not
executed behind the user's back.
