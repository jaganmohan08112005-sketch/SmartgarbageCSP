# SmartGarbage — R24 Community Project Submission Package

**Due: 09/10/2026** — 1 BOOK per batch · Documentation (softcopy) · PPT · Code.
Print: complete colour copy, one-side, on Executive Bond papers.

## Contents

| Folder | File | What it is |
|---|---|---|
| `book/` | `SmartGarbage_BOOK_R24.pdf` | **The BOOK** (print master). 89 pages, US Letter, 1" margins, TNR 16/14/12, page numbering starts at List of Abbreviations = 1 per R24. |
| `documentation/` | `SmartGarbage_Documentation_Softcopy.docx` | Softcopy of the same report (Times New Roman throughout, 19 tables, 20 figures/diagrams). |
| `ppt/` | `SmartGarbage_Presentation.pptx` | Final presentation deck (DOCUMENT_FINAL). |
| `code/` | `SmartGarbage_Source_Code.zip` | Full project source (399 files): Flask app, IoT+ML modules, tests, CI, docs. No venv/node_modules/artifacts. |
| `_scratch/` | — | Working scripts (not part of the submission). |

## Before you print (Executive Bond, colour, one-side)

1. Print `book/SmartGarbage_BOOK_R24.pdf` — 89 pages, one side only, colour.
2. Title page + CERTIFICATE page: print 2 extra copies of the certificate
   (one goes to the Project Coordinator per the R24 note).
3. Bind as ONE BOOK per batch.

## What was verified before this package was built

- Page size US Letter (8.5 × 11 in) with 1-inch margins (template attachment is letter).
- Page numbering starts at **LIST OF ABBREVIATIONS = 1**; title/certificate/declaration/
  acknowledgement/abstract carry no page numbers; TOC, List of Tables and List of Figures
  print the same re-based numbers (cross-checked against footers).
- Title date **October, 2026**; academic year **2026-2027**; register numbers
  24331A4441 / 24331A4434 / 24331A4446 / 24331A4426 everywhere (two typos fixed).
- Front-matter order CERTIFICATE → DECLARATION → ACKNOWLEDGEMENT → ABSTRACT →
  LIST OF ABBREVIATIONS → LIST OF FIGURES → LIST OF TABLES → TABLE OF CONTENTS → chapters
  (matches the filled sample BOOK shipped with the template).
- Headings TNR 16 bold caps (chapters) / 14 bold (sub-heads) / 12 body; tables 1.15,
  body 1.5 line spacing; table captions on top, figure captions at bottom.

## Regenerating any artifact

```bash
# BOOK PDF (two-pass so TOC/list page numbers are filled)
cd report
../venv/Scripts/python.exe generate_pdf.py --record
../venv/Scripts/python.exe generate_pdf.py

# DOCX softcopy
../venv/Scripts/python.exe generate_final_report.py

# PPT deck
../venv/Scripts/python.exe build_deck_v2.py
```

Then copy the fresh outputs into this folder (BOOK → `book/`, DOCX → `documentation/`).
