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

Notes:
  * Tests MUST stay sequential (``-n 0``, forced below): they share ONE database
    and each test drops/recreates the schema, so parallel workers would clobber
    each other's tables.
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

argv = sys.argv[1:]
fresh = "--fresh" in argv
argv = [a for a in argv if a != "--fresh"]

db, _pgdata = local_pg.boot_cluster(PGDATA_NAME, label="runner", fresh=fresh)
os.environ["TEST_DATABASE_URL"] = db.get_uri()

try:
    import pytest

    # -n 0: one shared database, so the suite must stay sequential (see above).
    rc = pytest.main(argv + ["-n", "0", "--timeout=180"])
finally:
    db.cleanup()
    print(f"[runner] PostgreSQL stopped; pytest exit code {rc}")
sys.exit(rc)
