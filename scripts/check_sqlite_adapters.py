#!/usr/bin/env python3
"""Fail on sqlite3 datetime bindings that lack the adapter recipe.

Python 3.12 deprecated sqlite3's implicit datetime adapters: binding a raw
date/datetime object into sqlite3 without a registered adapter now emits
DeprecationWarning per binding, and pytest.ini turns that warning class into
an ERROR suite-wide. The suite's defense is the documented replacement recipe
registered once in ``tests/conftest.py`` (covering every module under ``tests/``,
each xdist worker, and everything loaded under pytest), plus per-file
registration for any binding that can run OUTSIDE pytest — e.g. a script whose
production path binds datetimes through SQLAlchemy to a ``sqlite://`` URL.

This guard makes the third, silent failure mode loud instead: a NEW module
introduces a sqlite binding surface (direct ``sqlite3`` import/connect or a
``sqlite://`` URL) together with a datetime/date import, but no adapter
recipe — neither the tests/conftest.py registration nor a registration of its
own. Structural approximation (like check_doc_links.py): regexes over source,
bounded walk, no AST, stdlib-only.

Usage:
    python scripts/check_sqlite_adapters.py [root]    # default: repo root

Exit codes:
    0  every sqlite+datetime surface is covered by the recipe
    1  one or more unadapted binding surfaces found
"""

import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Same skip policy as scripts/check_doc_links.py: generated, archived,
# vendored or third-party subtrees cannot carry a binding this repo maintains.
SKIP_DIR_NAMES = {
    '.git', 'node_modules', 'venv', '.venv', '__pycache__',
    '_archive', '_qa', '_imgqa', 'test-results', 'playwright-report',
    '.freebuff', 'report', '.kilo', 'audit',
}
SKIP_SUBTREES = {'.github/skills'}

# Never hand an unbounded file to the reader (see check_doc_links.py).
MAX_SCAN_BYTES = 1_000_000

# This guard's own sources quote the patterns as examples — never scan them.
SELF_FILES = {
    Path(__file__).resolve(),
    (ROOT / 'tests' / 'test_no_unadapted_sqlite_bindings.py').resolve(),
}

# A sqlite binding surface: the stdlib module touched at all, or a SQLAlchemy
#/other DSN that ends up binding Python objects to the sqlite3 layer.
SQLITE_SURFACE_RE = re.compile(
    r'\bimport\s+sqlite3\b'
    r'|\bfrom\s+sqlite3\s+import\b'
    r'|\bsqlite3\.(?:connect|register_adapter)\b'
    r'|\bsqlite:///'
)

# A datetime binding source: the module imports names that can be bound.
DATETIME_IMPORT_RE = re.compile(
    r'(?m)^[^#\n]*\bfrom\s+datetime\s+import\b[^#\n]*\b(?:date|datetime)\b'
    r'|^[^#\n]*\bimport\s+datetime\b'
)

# The registered recipe: BOTH adapters, called (not merely mentioned in prose).
ADAPTER_CALL_RE = re.compile(
    r'\bsqlite3\.register_adapter\(\s*date\b'
)
DATETIME_ADAPTER_CALL_RE = re.compile(
    r'\bsqlite3\.register_adapter\(\s*datetime\b'
)

# Modules under tests/ are covered by the recipe registered at
# tests/conftest.py import time — for the duration of every pytest run,
# including each xdist worker. Anything OUTSIDE tests/ must register the
# recipe itself: production code binds datetimes without pytest around.
COVERED_PREFIXES = ('tests/', 'tests\\')


def _iter_files(root: Path):
    """Pruned walk over every .py file under root (see check_doc_links._iter_files)."""
    found = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIR_NAMES)
        rel_dir = Path(dirpath).relative_to(root)
        for name in filenames:
            if Path(name).suffix.lower() != '.py':
                continue
            path = Path(dirpath) / name
            posix = (rel_dir / name).as_posix()
            if any(posix == sub or posix.startswith(sub + '/')
                   for sub in SKIP_SUBTREES):
                continue
            if path.resolve() in SELF_FILES:
                continue
            try:
                if path.stat().st_size > MAX_SCAN_BYTES:
                    continue
            except OSError:
                continue
            found.append(path)
    yield from sorted(found)


def _recipe_registered(text: str) -> bool:
    """True when BOTH documented adapter registrations appear in source."""
    return bool(ADAPTER_CALL_RE.search(text) and DATETIME_ADAPTER_CALL_RE.search(text))


def find_offenders(root: Path):
    """Return [(path, reason), ...] for every unadapted sqlite+datetime surface."""
    offenders = []

    # 1. The shared recipe must still exist — removing it silently regresses
    #    every module under tests/ at once. Only meaningful for roots that
    #    actually carry a tests/ tree (the guard's tmp_path self-tests don't).
    conftest = root / 'tests' / 'conftest.py'
    if (root / 'tests').is_dir() and not conftest.is_file():
        offenders.append((conftest, 'tests/conftest.py is missing — the adapter recipe has no home'))
    elif conftest.is_file():
        try:
            ctext = conftest.read_text(encoding='utf-8', errors='replace')
        except OSError as exc:
            offenders.append((conftest, f'unreadable: {exc}'))
        else:
            if not _recipe_registered(ctext):
                offenders.append((
                    conftest,
                    'register_adapter(date) and register_adapter(datetime) recipe '
                    'no longer registered — every tests/ sqlite binding regresses'))

    # 2. Every existing sqlite+datetime binding surface must be covered:
    #    either inside tests/ (conftest recipe) or self-registering.
    for path in _iter_files(root):
        try:
            text = path.read_text(encoding='utf-8', errors='replace')
        except OSError:
            continue
        if not SQLITE_SURFACE_RE.search(text):
            continue
        if not DATETIME_IMPORT_RE.search(text):
            continue
        posix = path.relative_to(root).as_posix()
        if posix.startswith(COVERED_PREFIXES):
            continue
        if _recipe_registered(text):
            continue
        offenders.append((
            path,
            'sqlite + datetime binding surface without the adapter recipe '
            '(register the documented recipe in-file, or keep the module under tests/)'))

    return offenders


def main():
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT
    hits = find_offenders(root)
    if not hits:
        print('sqlite3 adapter scan: ok (every datetime binding is covered)')
        return 0
    print('%d sqlite3 datetime-binding surface(s) without the adapter recipe:' % len(hits))
    for path, reason in hits:
        print('- %s: %s' % (path, reason))
    print('The recipe lives in tests/conftest.py; see '
          'https://docs.python.org/3/library/sqlite3.html#sqlite3-adapters')
    return 1


if __name__ == '__main__':
    sys.exit(main())
