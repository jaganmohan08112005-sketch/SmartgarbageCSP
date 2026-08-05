"""Guard against monolith-era '# SECTION n' banner comments returning.

The 2,800-line monolith (app/routes.py) was split into blueprint modules and
all 18 decorative '# SECTION n —' banners were removed. This test (run in both
the SQLite and Postgres CI jobs) fails if any such banner reappears in
app/routes/, backed by the same stdlib-only scanner scripts/ CI uses.
"""

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_SCRIPT = ROOT / 'scripts' / 'check_no_section_banners.py'


def _load_checker():
    spec = importlib.util.spec_from_file_location('check_no_section_banners', _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


checker = _load_checker()


def test_no_section_banners_in_routes():
    """app/routes/*.py must contain zero '# SECTION n' banner comments."""
    hits = checker.find_banners(checker.DEFAULT_TARGET)
    assert hits == [], (
        "Monolith-era '# SECTION n' banners found — remove them "
        "(see scripts/check_no_section_banners.py):\n"
        + '\n'.join(f"{p}:{n}: {l.strip()}" for p, n, l in hits)
    )


def test_banner_scanner_catches_a_section_marker(tmp_path):
    """The scanner itself must detect a reintroduced banner (self-test)."""
    bad = tmp_path / 'demo.py'
    bad.write_text(
        "# ──────────────────────────────\n"
        "# SECTION 12 — ROUTE REGISTRATION\n"
        "# ──────────────────────────────\n"
        "def dummy():\n"
        "    pass\n",
        encoding='utf-8',
    )
    hits = checker.find_banners(tmp_path)
    assert len(hits) == 1
    assert hits[0][2].strip() == '# SECTION 12 — ROUTE REGISTRATION'


def test_banner_scanner_ignores_prose_comments(tmp_path):
    """Prose mentioning a section number mid-comment must NOT be flagged.

    The anchor is start-of-comment: a banner is a line that OPENS with
    'SECTION <n>', so prose that merely references a section elsewhere in
    the comment ("see section 12 ...") stays green."""
    ok = tmp_path / 'fine.py'
    ok.write_text(
        "# See section 12 of the maintenance manual for bin cleaning.\n"
        "# The box-drawn SECTION 12 marker was removed in the refactor.\n"
        "def dummy():\n"
        "    pass\n",
        encoding='utf-8',
    )
    assert checker.find_banners(tmp_path) == []
