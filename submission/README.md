# SmartGarbage — R24 Community Project Submission Package

**Due: 09/10/2026** — 1 BOOK per batch · Documentation (softcopy) · Demo video · PPT · Code.
Print: complete colour copy, one-side, on Executive Bond papers.

This folder is the **single copy** of every deliverable. The generators in
`report/` are build tooling; their outputs are regenerated on demand and are not
kept as a second copy in the repository.

**On submission day, follow [RUNBOOK.md](RUNBOOK.md)** — it sequences the gate,
the print/bind checklist, the exact hand-in file set, and the post-submission
commit / zip-refresh / workflow-secret steps.

## Contents

| Folder | File | What it is |
|---|---|---|
| `book/` | `SmartGarbage_BOOK_R24.pdf` | **The BOOK** (print master). 89 pages, US Letter 8.5×11 in, 1" margins, TNR 16/14/12, page numbering starts at List of Abbreviations = 1. |
| `documentation/` | `SmartGarbage_Documentation_Softcopy.docx` | Softcopy of the same report (Times New Roman throughout, 19 tables, 20 figures/diagrams). |
| `video/` | `SmartGarbage_Demo_Video.mp4` | 9:50 live walkthrough — 31 scenes covering every page the app serves: the public site, all three portals page by page (citizen, worker, admin), and the writes performed on camera (waste declaration, preference change, complaint filing with its signed tracking page, issue report, offload). 1280×720 H.264 + AAC (Playwright capture + TTS + ffmpeg). |
| `ppt/` | `SmartGarbage_Presentation.pptx` | Final deck: 20 slides, R24 title/footer chrome, IEEE-numbered references (`[1] Author(s), "Title," …`). |
| `code/` | `SmartGarbage_Source_Code.zip` | Full project source: 409 files — Flask app, IoT + ML modules, tests, CI, docs, and the committed narration generator (`report/video/_video_live/tts.ps1`). No venv/node_modules, no report binaries (the BOOK/softcopy/deck are delivered above, not inside the code archive). Git-ignored; rebuild with `build_code_zip.py`. |
| `_scratch/` | — | Working scripts (manifest, the verifier, builders). Not part of the submission. |
| — | `RUNBOOK.md` | Submission-day runbook: gate, print/bind checklist, hand-in set, post-submission steps. |

## Before you print (Executive Bond, colour, one-side)

1. Run the verifier below and get exit 0 — do not print a BOOK the gate has not
   passed.
2. Print `book/SmartGarbage_BOOK_R24.pdf` — 89 pages, one side only, colour.
3. Print **2 copies of the CERTIFICATE** page — absolute page 2 of the PDF (one
   goes to the Project Coordinator per the R24 note).
4. Bind as ONE BOOK per batch.

[RUNBOOK.md](RUNBOOK.md) has the full checklist plus the post-submission steps.

## What was verified against the R24 template

- Page size US Letter (8.5 × 11 in) with 1-inch margins.
- Front-matter order CERTIFICATE → DECLARATION → ACKNOWLEDGEMENT → ABSTRACT →
  **LIST OF ABBREVIATIONS → LIST OF FIGURES → LIST OF TABLES → TABLE OF CONTENTS** → chapters.
  The same order is used by the DOCX softcopy and the R24 template's contents list
  (Figures before Tables).
- Page numbering starts at **LIST OF ABBREVIATIONS = 1**; title/certificate/declaration/
  acknowledgement/abstract carry no page numbers; TOC, List of Tables and List of Figures
  print the same re-based numbers (cross-checked against footers; Ch.1 = 5).
- Title date **October, 2026**; academic year **2026-2027**; register numbers
  24331A4441 / 24331A4434 / 24331A4446 / 24331A4426 everywhere.
- Headings TNR 16 bold caps (chapters) / 14 bold (sub-heads) / 12 body; tables 1.15,
  body 1.5 line spacing; table captions on top, figure captions at bottom; IEEE references.
- Deck follows the R24 slide order (Title → Abstract → … → References → Q&A) with two
  extra honest additions (Deployment, ML photo-gate QA) before the results slides.

## Verify before you print

One command re-checks all five deliverables and exits non-zero if any of them
drifted from the source it was built from:

```bash
venv/Scripts/python.exe submission/_scratch/verify_submission.py
```

| # | Deliverable | Re-checked against |
|---|---|---|
| 1 | `book/SmartGarbage_BOOK_R24.pdf` | page size (Letter, ±0.5pt), 1-inch text margins, front-matter order, re-based numbering (LoA = 1, no numbers in front matter), current date/year/register facts |
| 2 | `documentation/…Softcopy.docx` | OOXML container + XML parses, 19 tables, 20 figures, Times New Roman dominant, front-matter order, current facts |
| 3 | `ppt/SmartGarbage_Presentation.pptx` | OOXML container + XML parses, 20 slides, 16:9, IEEE references `[1]…[n]` with author/year entries, closing Q&A slide |
| 4 | `video/SmartGarbage_Demo_Video.mp4` | container readable, 9:50 ±5s, h264 1280×720, AAC audio |
| 5 | `code/SmartGarbage_Source_Code.zip` | entry set/order == `code_list.txt`, no forbidden paths, no duplicates, and every entry's SHA-256 equals the source tree (byte-for-byte drift) |

Two failure kinds are both fatal: **CONTRACT** (the artifact no longer meets the
R24 requirement it was reviewed against) and **DRIFT** (a code file changed after
the zip was written, or a generator was committed after the artifact).
`--selftest` proves the gate is not vacuous: it doctors a throwaway copy of each
artifact and asserts the matching check fails on it.

## Regenerating any artifact

Generators write into `report/`; copy the fresh output over the matching file in
this folder afterwards (that copy is the one that gets submitted).

```bash
# BOOK PDF (two-pass so TOC/list page numbers are filled)
cd report
../venv/Scripts/python.exe generate_pdf.py --record
../venv/Scripts/python.exe generate_pdf.py
#   → report/DOCUMENTATION_UPDATED.pdf  → copy to submission/book/SmartGarbage_BOOK_R24.pdf

# DOCX softcopy
../venv/Scripts/python.exe generate_final_report.py
#   → report/DOCUMENTATION_UPDATED.docx → copy to submission/documentation/SmartGarbage_Documentation_Softcopy.docx

# PPT deck (R24 chrome + IEEE references)
../venv/Scripts/python.exe build_deck_v2.py
#   → report/DOCUMENT_FINAL.pptx        → copy to submission/ppt/SmartGarbage_Presentation.pptx

# Demo video (records the local stack on 127.0.0.1:5057; segments are resumable)
../venv/Scripts/python.exe report/video/_make_video_live.py
#   → submission/video/SmartGarbage_Demo_Video.mp4

# Source-code zip (refreshes the curated manifest, then rebuilds)
../venv/Scripts/python.exe submission/_scratch/build_code_zip.py --write
```

## Housekeeping rules for this package

- One copy of each deliverable, here. Do not re-add `report/DOCUMENTATION_UPDATED.*`,
  `report/DOCUMENT_FINAL.pptx` or a second video copy — the regenerated files are
  build outputs and the delivered copies live in this folder.
- `submission/code/*.zip` is git-ignored on purpose (size); rebuild it with
  `build_code_zip.py --write` after code changes so the archive matches HEAD.
- Run `verify_submission.py` after any regeneration (and before printing) — it is
  the single gate for all five deliverables.
- `_archive/` keeps historical report versions; it is an archive by design and is
  not part of the submission.
