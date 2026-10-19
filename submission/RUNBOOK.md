# Submission-Day Runbook — R24 package

**Due:** 09/10/2026 (as recorded in [README.md](README.md)) · one BOOK per batch,
plus the softcopy, demo video, PPT and code.

Run the steps in this order. Steps 5–8 are the *post-print* work — do not start
them before the paper copies are in your hand, because refreshing the archive
(step 6) must happen after the final commit (step 5).

```bash
venv/Scripts/python.exe submission/_scratch/verify_submission.py   # 1. gate
# 2-4. print, bind, copy the files
git add <paths> && git commit && git push                          # 5. commit + push
venv/Scripts/python.exe submission/_scratch/build_code_zip.py --write   # 6. refresh zip
venv/Scripts/python.exe submission/_scratch/verify_submission.py        # 7. re-gate
# 8. GitHub → Settings → Secrets and variables → Actions
```

---

## 1. Run the gate first (2 minutes)

```bash
venv/Scripts/python.exe submission/_scratch/verify_submission.py
```

Every line must read `PASS` and the command must exit **0** (`echo $?`). It
re-checks all five artifacts — page geometry and numbering, DOCX/PPTX integrity,
video streams, zip manifest and hashes — and fails if an artifact drifted from
the source it was built from. If it complains about the **zip** (`drifted from
the source tree … rebuild with build_code_zip.py --write`), run step 6 first and
re-run. Do not print a BOOK the gate has not passed.

`--selftest` proves the gate itself still works (it doctors a copy of each
artifact and asserts the check fails); run it if you ever doubt a green result.

## 2. Print checklist (Executive Bond, colour, one side)

- [ ] Print `book/SmartGarbage_BOOK_R24.pdf` — **89 pages**, complete, colour,
      **one side only**, US Letter (8.5 × 11 in).
- [ ] Print **2 copies of the CERTIFICATE page** — it is **absolute page 2** of the
      PDF. One copy goes to the Project Coordinator (the R24 note); the other
      stays in the book.
- [ ] Check the first printed sheet: no page number on the title/certificate/
      declaration/acknowledgement/abstract pages.
- [ ] Check the footer of the **LIST OF ABBREVIATIONS** page reads `1`, and that
      Chapter 1 (`1. INTRODUCTION`) reads `5` — that is the re-based numbering the
      BOOK is accepted with.
- [ ] Bind as **ONE BOOK per batch**.

If any of those numbers are wrong, the PDF you printed is not the verified one —
stop and re-run step 1.

## 3. The exact set to hand in

Five files, all under `submission/`. Nothing else in this repo is a deliverable.
(The video carries its sidecar caption files — row 3a, English + Telugu, no
text burned into the picture — so the walkthrough stays watchable muted. An
optional aid rides in the same folder for reviewers whose player cannot load
sidecars: `video/SmartGarbage_Demo_Video.en.burned.mp4`, the English captions
burned into the picture of the identical cut. Rebuild it with
`report/video/_burn_subtitles.py`; the delivered MP4 of row 3 is never rewritten
by that script. It is an alternative, not a sixth deliverable — hand in the same
five files unless the panel asks for the burned copy.)

| # | Path | Form | Identity |
|---|---|---|---|
| 1 | `book/SmartGarbage_BOOK_R24.pdf` | **printed**, bound (above) | 89 pp, Letter, TNR 16/14/12, numbering from LoA = 1 |
| 2 | `documentation/SmartGarbage_Documentation_Softcopy.docx` | digital | 19 tables, 20 figures, Times New Roman |
| 3 | `video/SmartGarbage_Demo_Video.mp4` | digital | 9:50, 1280×720 h264 + AAC |
| 3a | `video/SmartGarbage_Demo_Video.{en,te}.{srt,vtt}` | digital | sidecar captions (English + Telugu) for the same cut |
| 4 | `ppt/SmartGarbage_Presentation.pptx` | digital | 20 slides, R24 chrome, IEEE refs |
| 5 | `code/SmartGarbage_Source_Code.zip` | digital | 411-file source archive |

- [ ] Copy 2–5 to the submission media (and/or the shared drive).
- [ ] Copy the **printed** book's PDF as well if the department accepts PDF for
      the record; if not, hand over the bound copy only.
- [ ] `submission/_scratch/` (manifest, builders, the verifier) and `_archive/`
      are **not** deliverables — never include them.
- [ ] `submission/code/*.zip` is git-ignored, so the archive you hand in is the
      one you build locally in step 6, not something you can clone.

## 4. Pre-print sanity (30 seconds)

- [ ] `smartgarbage.onrender.com` answers and `/health` is healthy (the video and
      the report both point at it). On Render's free tier the service **sleeps**;
      wake it 5–10 minutes before a review or demo instead of in front of the
      panel (the keepalive/uptime workflows are what keep it warm in normal use).
- [ ] The DOCX opens in Word and the deck opens in PowerPoint — the verifier
      proves the files are intact, not that your Office can render them.
- [ ] The video plays to the end with sound.

## 5. Commit and push

The branch is `feat/uptime-monitoring`, tracking `origin/feat/uptime-monitoring`
and already **18 commits ahead** of it. A further **22 paths** are uncommitted as
this runbook was written:

| State | Paths |
|---|---|
| modified (15) | `.github/workflows/ci.yml`, `.github/workflows/tests.yml`, `.gitignore`, `app/templates/notification_preferences.html`, `docs/PROJECT_STRUCTURE.md`, `report/video/DEMO_VIDEO_SCRIPT.md`, `report/video/_make_video_live.py`, `report/video/_verify_video.py`, `report/video/_video_live/tts.ps1`, `scripts/check_doc_links.py`, `submission/README.md`, `submission/_scratch/build_code_zip.py`, `submission/_scratch/code_list.txt`, `submission/video/SmartGarbage_Demo_Video.mp4`, `tests/test_features.py` |
| deleted (1) | `submission/_scratch/verify_book_pdf.py` (superseded by `verify_submission.py`) |
| new (6) | `report/video/_probe_{pages,new_scenes,route_coverage,encode_size}.py`, `tests/test_doc_link_scan_bounded.py`, `submission/_scratch/verify_submission.py` |

- [ ] `git status` and review the diff yourself — do not `git add -A`.
- [ ] Commit in logical groups (CSP template fix + gate; video pipeline;
      docs/submission package), matching the repo's `type(scope): summary` style.
- [ ] `git push` (pushes the 18 existing commits plus the new ones).
- [ ] Confirm the run: the push immediately triggers the **tests** workflow (full
      suite on embedded Postgres, 90-minute timeout) — expect a long run, and a
      red one is visible before any PR is opened. `a11y-audit` runs on PRs.
- [ ] Open the PR into `main` when the suite is green.

> Scheduling cannot be turned on from a feature branch. Cron workflows run **only
> from the default branch**, and a `workflow_dispatch` button appears in the
> Actions UI only once the file exists on `main`. So `uptime.yml` (15 min),
> `sw-drift.yml` (6 h) and `keepalive.yml` (5 min) stay dormant until this branch
> is merged. GitHub also auto-disables scheduled workflows after ~60 days of repo
> inactivity — re-enable from the Actions tab if that happens.

## 6. Refresh the source archive (after the final commit)

The archive must match the committed tree, so it is rebuilt **last**:

```bash
venv/Scripts/python.exe submission/_scratch/build_code_zip.py --write
```

It refreshes `submission/_scratch/code_list.txt` (drops files that no longer
exist, adds new sources, never includes `venv/`, `node_modules/`, `.env`,
`submission/`, or the separately-delivered report binaries) and rewrites
`submission/code/SmartGarbage_Source_Code.zip`. Expect ~411 files; the script
asserts the count matches the manifest and that `csp-events.js` is present.

- [ ] Re-run the gate (step 7) and confirm the ZIP lines read
      `all 411 entries hash-match the source tree`.
- [ ] The `N archived file(s) have uncommitted edits` warning should now be
      **gone** — it means the archive contains work that is still uncommitted.
- [ ] Copy the fresh zip to the submission media (it is freshly built, so any
      earlier copy is stale).

## 7. Re-run the gate

```bash
venv/Scripts/python.exe submission/_scratch/verify_submission.py
```

Exit 0 and six `PASS` lines (the video's sidecar captions are checked as their
own deliverable), or fix and repeat step 6. This is the last check
before the files leave your machine.

## 8. Enable the workflows' secrets

**Where:** GitHub repo → **Settings** → **Secrets and variables** → **Actions** →
**New repository secret**. Names are case-sensitive. Full walkthroughs:
[docs/OPS_SECRETS_CHECKLIST.md](../docs/OPS_SECRETS_CHECKLIST.md) (SMTP +
`DATABASE_URL`) and [docs/PHOTO_GATE_RUNBOOK.md](../docs/PHOTO_GATE_RUNBOOK.md)
(Kaggle).

**Only one secret pair is new with this branch:**

| Secret | For | Needed? |
|---|---|---|
| `KAGGLE_USERNAME` | `retrain-photo-classifier.yml` (new, manual dispatch) | **Optional** — without it the dataset rebuild falls back to Wikimedia; with it the TrashNet fetch is fast |
| `KAGGLE_KEY` | same | same |

**Already needed by workflows that exist on `main`** — set these if they are not
set yet, or the jobs stay *green but silent*:

| Secret(s) | Workflow | Behaviour without it |
|---|---|---|
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USE_TLS`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `DIGEST_FROM`, `DIGEST_TO` | `health-digest.yml` | Green, summary says "email skipped"; digest saved as an artifact instead of mailed |
| `DATABASE_URL` (Supabase **pooler** string) | `reliability-report.yml` | Green, logs "SMOKE MODE: skipping the weekly append" |
| `RENDER_STAGING_HOOK` | `ci.yml` → `deploy-staging` job, **only** on the `staging` branch | That job **fails** if it is unset when triggered; main/PR runs are unaffected |

**Workflows that need no secrets at all:** `uptime.yml`, `keepalive.yml`,
`sw-drift.yml`, `a11y-audit.yml`, `tests.yml`, `playwright.yml`. They declare
their own `permissions:` (`contents: write` / `issues: write`), so the
repo-level *Workflow permissions* setting does not need changing.

- [ ] `KAGGLE_USERNAME` + `KAGGLE_KEY` added (or consciously skipped).
- [ ] Confirm the pre-existing SMTP/`DATABASE_URL` secrets are still present
      (rotating nothing, just verifying they exist).
- [ ] After the merge to `main`: Actions → **Uptime monitor** → *Run workflow*,
      and confirm the scheduled runs appear (uptime every 15 min, sw-drift every
      6 h, keepalive every 5 min).
- [ ] After the merge: Actions → **Reliability report** → *Run workflow* to
      prove `DATABASE_URL` works end to end.

## If something drifts

| Symptom | What it means | Fix |
|---|---|---|
| `archive drifted from the source tree … <file>` | A source file changed after the zip was written (including a doc that ships inside it, like `docs/PROJECT_STRUCTURE.md`) | Rebuild the zip (step 6) |
| `drift: <generator> was committed after this artifact` | A generator changed after the BOOK/DOCX/PPTX/video was committed | Regenerate that artifact, copy it into `submission/`, re-run step 1 |
| `page count N != expected 89` | The report genuinely changed length | Review the change, then update `EXPECTED_BOOK_PAGES` in the verifier and re-run |
| `duration 30.09s != 590s` | A truncated or re-encoded cut | Re-record / re-copy the video, re-run step 1 |
| `N archived file(s) have uncommitted edits` (warning) | The archive matches your working tree, not `HEAD` | Commit (step 5) then rebuild (step 6) |
| A check prints `cannot verify - dependency missing` | The venv lost `pypdf` / `python-docx` / `python-pptx` / `imageio-ffmpeg` | `pip install pypdf python-docx python-pptx imageio-ffmpeg` |
