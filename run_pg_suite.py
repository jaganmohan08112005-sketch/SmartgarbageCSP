"""Run pytest against a bundled local Postgres (CI mirror).

Usage: python run_pg_suite.py [pytest args...]
"""
import os
import sys
import tempfile

import pgserver

PGDATA = os.path.join(tempfile.gettempdir(), 'sg_pgdata_full')
os.makedirs(PGDATA, exist_ok=True)
db = pgserver.get_server(pgdata=PGDATA)
db.ensure_postgres_running()
os.environ['TEST_DATABASE_URL'] = db.get_uri()
print(f"[runner] PostgreSQL up at {db.get_uri()}")

try:
    import pytest
    rc = pytest.main(sys.argv[1:] + ['-n', '0', '--timeout=180'])
finally:
    db.cleanup()
    print(f"[runner] PostgreSQL stopped; pytest exit code {rc}")
sys.exit(rc)