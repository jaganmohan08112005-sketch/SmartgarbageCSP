#!/usr/bin/env python3
"""Run pytest against a bundled local Postgres (the CI mirror).

No Supabase account, no ``TEST_DATABASE_URL`` to set: this boots an embedded
``pgserver`` cluster in the temp directory, exports its URI as
``TEST_DATABASE_URL``, runs pytest, and shuts the cluster down again. It is the
identical harness the ``tests`` workflow uses on CI (``run_pg_suite.py -q``), so
a green local run means the same thing as a green CI run.

The cluster handling itself lives in ``scripts/local_pg.py``, shared with
``scripts/run_local_stack.py``; this file only owns the pytest invocation.

Usage:
    python run_pg_suite.py [pytest args...]      # e.g. -q, tests/test_auth.py, -k foo
    python run_pg_suite.py --fresh               # throw the temp cluster away first
    python run_pg_suite.py --fast [-q]           # pre-commit fast lane: curated
                                                 # high-value subset, < 2 min end to end

Notes:
  * ``--fast`` is the pre-commit iteration lane: it selects FAST_LANE below
    (authentication/MFA, the end-to-end portal walkthrough, security headers,
    migration coverage, error-summary contracts, doc integrity and the repo/
    harness guard tests) and nothing else — the tests that catch the most
    regressions per second. It is a subset for *iteration only*: the full run
    (every test, as CI runs it) remains the gate before opening a PR. Extra
    pytest args still apply, so ``--fast -k mfa`` narrows further and explicit
    test paths are additive.
  * Parallel by default: each pytest-xdist worker gets its OWN PostgreSQL
    database (``tests/conftest.py`` points TEST_DATABASE_URL at
    ``sg_test_<worker>`` in the same cluster), so workers may drop/recreate
    the schema per test without clobbering each other. Sequential mode stays
    available by passing ``-n 0`` explicitly.
  * The per-test timeout (``--timeout=180``) is appended so one genuinely hung
    test fails fast instead of stalling a worker longer than CI allows.
  * The cluster lives in the temp dir and survives runs, which keeps startup
    fast. If a previous run was killed hard (or Windows Defender interrupted a
    boot), that data directory can be unusable; the runner then retires it and
    initialises a fresh cluster instead of failing with a confusing
    "could not open file base/..." error. ``--fresh`` forces that path.
"""
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

from scripts import local_pg  # noqa: E402

# Disposable by design: the suite drops/recreates the schema per test, unlike
# the demo stack's directory, which holds seeded rows worth keeping.
PGDATA_NAME = "sg_pgdata_full"

# The --fast lane: highest-value coverage per second for pre-commit loops.
# Auth/MFA (tests/test_auth.py) and the end-to-end citizen/worker/admin
# walkthrough (tests/test_walkthrough.py) exercise the flows a change is most
# likely to break; the CSP, migration-coverage and error-summary files are
# small security/contract checks; doc links plus the local_pg/no-banner/
# bounded-scan/sqlite-adapter guards protect the repo and this very harness
# (they need no database at all, so they are nearly free). Deliberately
# EXCLUDED: tests/qa/browser E2E (Playwright + live server, minutes) and the
# test_features.py bulk — both belong to the full pre-PR run / CI.
FAST_LANE = (
    "tests/test_auth.py",
    "tests/test_walkthrough.py",
    "tests/test_template_csp.py",
    "tests/test_error_summaries.py",
    "tests/test_migration_coverage.py",
    "tests/test_doc_links.py",
    "tests/test_doc_link_scan_bounded.py",
    "tests/test_local_pg_helper.py",
    "tests/test_no_unadapted_sqlite_bindings.py",
    "tests/test_no_section_banners.py",
)

argv = sys.argv[1:]
fresh = "--fresh" in argv
fast = "--fast" in argv
argv = [a for a in argv if a not in ("--fresh", "--fast")]
if fast:
    argv = argv + list(FAST_LANE)

db, _pgdata, _uri = local_pg.boot_and_export(
    PGDATA_NAME, "TEST_DATABASE_URL", label="runner", fresh=fresh)

# Overwritten by pytest.main; kept nonzero so a pytest-import failure inside
# the try cannot make the finally-print/sys.exit report a misleading zero.
rc = 2
try:
    import pytest

    # Parallel by default: each xdist worker owns its own database (see
    # tests/conftest.py), so the per-test schema drop/recreate cannot collide
    # across workers. Sequential remains available via an explicit -n 0.
    rc = pytest.main(argv + ["--timeout=180"])
finally:
    db.cleanup()
    print(f"[runner] PostgreSQL stopped; pytest exit code {rc}")
sys.exit(rc)
