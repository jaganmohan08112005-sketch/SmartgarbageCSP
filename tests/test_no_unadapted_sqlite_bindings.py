"""Guard: every sqlite3 datetime binding must be covered by the adapter recipe.

Python 3.12 deprecated sqlite3's implicit datetime adapters and pytest.ini
turns surviving default-adapter warnings into suite-wide ERRORs. The recipe is
registered once in tests/conftest.py; scripts/check_sqlite_adapters.py scans
the repo structurally for a NEW binding surface — a module mentioning sqlite
(direct import/connect or a `sqlite:///` DSN) together with a datetime/date
import — that is neither covered by the conftest recipe (anything under
tests/) nor registers the recipe itself (anything that can run outside
pytest). Failing surface is named by path, like the other repo guards.

The scanner is stdlib-only and regex-based on purpose (see scripts/
check_sqlite_adapters.py); these tests pin both the real-tree result and that
the scanner actually catches what it claims to catch.
"""
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

import scripts.check_sqlite_adapters as checker


def test_repo_has_no_unadapted_sqlite_datetime_bindings():
    """The real tree: zero unadapted binding surfaces, by name."""
    hits = checker.find_offenders(checker.ROOT)
    assert hits == [], (
        "sqlite3 datetime-binding surface(s) without the adapter recipe:\n"
        + '\n'.join(f"{p.relative_to(ROOT)}: {r}" for p, r in hits)
        + "\nThe recipe is registered once in tests/conftest.py; modules that "
        "can run outside pytest must register it in-file. See "
        "scripts/check_sqlite_adapters.py."
    )


def test_scanner_catches_unadapted_binding(tmp_path):
    """Self-test: sqlite + datetime import without registration is flagged."""
    bad = tmp_path / 'misbehaving_script.py'
    bad.write_text(
        "import sqlite3\n"
        "from datetime import datetime\n"
        "conn = sqlite3.connect('x.db')\n"
        "conn.execute('CREATE TABLE t (ts TIMESTAMP)')\n"
        "conn.execute('INSERT INTO t VALUES (?)', (datetime(2026, 1, 1),))\n",
        encoding='utf-8',
    )
    hits = checker.find_offenders(tmp_path)
    assert [p.name for p, _ in hits] == ['misbehaving_script.py']


def test_scanner_accepts_self_registering_module(tmp_path):
    """Self-test: registering BOTH adapters in-file closes the surface."""
    good = tmp_path / 'adapted_script.py'
    good.write_text(
        "import sqlite3\n"
        "from datetime import date, datetime\n"
        "sqlite3.register_adapter(date, lambda v: v.isoformat())\n"
        "sqlite3.register_adapter(datetime, lambda v: v.isoformat(' '))\n"
        "conn = sqlite3.connect('x.db')\n",
        encoding='utf-8',
    )
    assert checker.find_offenders(tmp_path) == []


def test_scanner_accepts_datetime_without_sqlite(tmp_path):
    """Self-test: importing datetime in a non-sqlite module is not flagged."""
    other = tmp_path / 'plain_module.py'
    other.write_text(
        "from datetime import datetime, timedelta\n"
        "now = datetime.now()\n",
        encoding='utf-8',
    )
    assert checker.find_offenders(tmp_path) == []


def test_conftest_recipe_still_registered():
    """The recipe in tests/conftest.py is what covers every tests/ binding —
    the scan must fail the moment it is removed."""
    text = (ROOT / 'tests' / 'conftest.py').read_text(encoding='utf-8')
    assert checker._recipe_registered(text), (
        'tests/conftest.py no longer registers both sqlite3 datetime adapters — '
        'every test module binding a datetime regresses; restore the documented '
        'recipe block (see https://docs.python.org/3/library/sqlite3.html#sqlite3-adapters).')


@pytest.mark.parametrize('permuted', [True, False])
def test_recipe_detection_requires_both_adapters(tmp_path, permuted):
    """Self-test: one adapter registered without the other is NOT recipe
    coverage (each flags independently), keeping the registry complete."""
    half = tmp_path / ('sub' if permuted else 'other') / 'half_recipe.py'
    half.parent.mkdir(parents=True, exist_ok=True)
    half.write_text(
        "import sqlite3\n"
        "from datetime import date, datetime\n"
        "sqlite3.register_adapter(date, lambda v: v.isoformat())\n",  # datetime one missing
        encoding='utf-8',
    )
    hits = checker.find_offenders(tmp_path)
    assert any(p.name == 'half_recipe.py' for p, _ in hits)
