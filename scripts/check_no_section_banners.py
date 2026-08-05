#!/usr/bin/env python3
"""Fail when monolith-era '# SECTION n —' banner comments reappear.

The 2,800-line monolith (app/routes.py) was split into blueprint modules
(app/routes/{auth,citizen,admin,worker,iot,webhook,analytics,public}.py +
__init__.py), and all 18 decorative '# SECTION n —' banners were removed.
This guard keeps them from coming back after a future refactor: it scans
every *.py file under app/routes/ for banner-style section comments and
exits non-zero if any are found.

Usage:
    python scripts/check_no_section_banners.py [dir]
    (defaults to app/routes)

Exit codes:
    0  no banner comments found
    1  one or more banner comments found
"""

import re
import sys
from pathlib import Path

# Monolith-era banners were written as:
#   # ──────────────────────────────────────────────
#   # SECTION 12 — ROUTE REGISTRATION
#   # ──────────────────────────────────────────────
# Match the "# SECTION <n>" marker with optional surrounding box-drawing
# characters and an optional em-dash title. The marker alone is enough to
# flag a regression, so don't over-anchor on the box art.
SECTION_RE = re.compile(r'^#\s*SECTION\s+\d+\b', re.IGNORECASE)
DEFAULT_TARGET = Path(__file__).resolve().parent.parent / 'app' / 'routes'


def find_banners(target: Path) -> list:
    """Return [(path, lineno, line)] for every banner comment found."""
    hits = []
    # rglob (not glob) so a future refactor that nests packages under
    # app/routes/ (e.g. app/routes/subpackage/) stays covered.
    for pyfile in sorted(target.rglob('*.py')):
        try:
            text = pyfile.read_text(encoding='utf-8')
        except OSError:
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            stripped = line.lstrip()
            if stripped.startswith('#') and SECTION_RE.match(stripped):
                hits.append((pyfile, lineno, line))
    return hits


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    target = Path(argv[0]) if argv else DEFAULT_TARGET
    hits = find_banners(target)
    if not hits:
        print(f"OK: no '# SECTION n' banner comments in {target}")
        return 0
    for path, lineno, line in hits:
        print(f"{path}:{lineno}:1: SG1 monolith-era SECTION banner comment: {line.strip()}")
    print(f"\n{len(hits)} monolith-era SECTION banner(s) found — remove them.")
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
