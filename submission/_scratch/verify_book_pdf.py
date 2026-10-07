"""Verify the regenerated BOOK PDF against the R24 template requirements."""
from pypdf import PdfReader

PDF = r"report\DOCUMENTATION_UPDATED.pdf"
r = PdfReader(PDF)
pages = [(p.extract_text() or "") for p in r.pages]
n = len(pages)
fail = []

def line1(page_text):
    return page_text.strip().splitlines()[0].strip() if page_text.strip() else ""

def head_lines(page_text, k=3):
    return [l.strip().lower() for l in page_text.strip().splitlines() if l.strip()][:k]

# 1. page size letter
b = r.pages[0].mediabox
w, h = float(b.width) / 72, float(b.height) / 72
print(f"[size] {w} x {h} in")
if abs(w - 8.5) > 0.02 or abs(h - 11.0) > 0.02:
    fail.append("page size not letter")

# 2. find key chapter start pages (absolute, 1-based)
starts = {}
for i, t in enumerate(pages):
    l1 = line1(t)
    for key in ("LIST OF ABBREVIATIONS", "1. INTRODUCTION", "CERTIFICATE", "TITLE"):
        pass
titles = [
    "SMARTGARBAGE CHINTALAVALASA", "CERTIFICATE", "DECLARATION", "ACKNOWLEDGEMENT",
    "ABSTRACT", "LIST OF ABBREVIATIONS", "TABLE OF CONTENTS", "LIST OF TABLES",
    "LIST OF FIGURES", "1. INTRODUCTION", "REFERENCES", "APPENDIX A", "APPENDIX B",
    "PAPER PUBLICATIONS",
]
abs_pages = {}
used = set()
for t in titles:
    key = t.lower()
    for i, pt in enumerate(pages):
        if i in used:
            continue
        # chapter titles sit on line 2 (after the running header); scan the
        # top few lines for an exact match so body text can't collide
        if any(l == key for l in head_lines(pt)):
            abs_pages[t] = i + 1
            used.add(i)
            break
for t in titles:
    print(f"[chap] {t!r}: absolute page {abs_pages.get(t, 'NOT FOUND')}")

abbr = abs_pages.get("LIST OF ABBREVIATIONS")
if abbr is None:
    fail.append("LIST OF ABBREVIATIONS chapter not found")

# 3. front matter (before LoA) must have no trailing page number
for i, pt in enumerate(pages[: (abbr or 1) - 1]):
    fl = [l for l in pt.strip().splitlines() if l.strip()]
    if fl and fl[-1].strip().isdigit():
        fail.append(f"front matter page {i+1} shows a number: {fl[-1]!r}")

# 4. LoA page footer must be '1'
tt = pages[abbr - 1]
tail = [l.strip() for l in tt.strip().splitlines() if l.strip()]
tail.append(next((l.strip() for l in pages[abbr].strip().splitlines() if l.strip().isdigit()), None))
print("[loa] first lines:", tt.strip().splitlines()[:3], "| tail numbers:", [l for l in tail if l and l.isdigit()])
if not any(l == "1" for l in tail):
    fail.append("LoA footer is not 1: " + str([l for l in tail if l and l.isdigit()][-3:]))

# 5. TOC agreement: AoM footer of a later chapter should equal abs - abbr + 1
intro = abs_pages.get("1. INTRODUCTION")
if intro and abbr:
    ip = pages[intro - 1]
    fl = [l.strip() for l in ip.strip().splitlines() if l.strip()]
    nums = [l for l in fl if l.isdigit()]
    expect = str(intro - abbr + 1)
    print(f"[intro] expected footer {expect}, got {nums[-1] if nums else None}")
    if not nums or nums[-1] != expect:
        fail.append(f"intro footer {nums[-1] if nums else None} != {expect}")

# 6. year strings
allt = "\n".join(pages)
if "October, 2025" in allt:
    fail.append("stale title date October, 2025")
if "October, 2026" not in allt:
    fail.append("missing October, 2026")
if "2025-2026" in allt:
    fail.append("stale academic year 2025-2026")
if "2026-2027" not in allt:
    fail.append("missing academic year 2026-2027")
if "2433144441" in allt:
    fail.append("register typo 2433144441 still present")
if "2433144446" in allt:
    fail.append("register typo 2433144446 still present")
if "24331A4441" not in allt or "24331A4446" not in allt:
    fail.append("corrected register numbers missing")

print(f"[pages] {n}")
if fail:
    print("FAILURES:")
    for f in fail:
        print(" -", f)
    raise SystemExit(1)
print("ALL BOOK-PDF CHECKS PASSED")
