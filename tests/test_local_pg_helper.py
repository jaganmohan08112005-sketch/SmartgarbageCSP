"""Unit tests for scripts/local_pg.py — the one home for cluster handling.

The boot/retry/wipe rules used to exist twice (run_pg_suite.py and
scripts/run_local_stack.py) and had drifted: only one caller could clear
leftover postgres processes, and only it retired a failed data directory
instead of re-using the directory a still-attached postgres keeps open. These
tests pin the merged behaviour, and the last one fails if cluster handling is
ever copy-pasted back into an entry point.

No Postgres is booted here: the cluster module and the connection module are
substituted through ``sys.modules`` so the retry/wipe logic is exercised
without a cluster, and the *real* cluster boot is covered by the suite runner
that runs this very file.
"""
import os
import subprocess
import sys
import time
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import local_pg  # noqa: E402


class FakeServer:
    def __init__(self, uri):
        self._uri = uri

    def get_uri(self):
        return self._uri

    def ensure_postgres_running(self):
        return self


def _install_fake_pgserver(monkeypatch, behaviours, seen):
    """Substitute pgserver.get_server with one that walks ``behaviours``.

    Each entry is either an exception instance to raise or a URI string to
    succeed with; ``seen`` records the pgdata path of every call.
    """
    def get_server(pgdata):
        seen.append(pgdata)
        behaviour = behaviours[min(len(seen) - 1, len(behaviours) - 1)]
        if isinstance(behaviour, Exception):
            raise behaviour
        return FakeServer(behaviour)

    monkeypatch.setitem(sys.modules, "pgserver",
                        types.SimpleNamespace(get_server=get_server))


def _cleanup(*paths):
    import shutil
    for path in paths:
        shutil.rmtree(path, ignore_errors=True)


def test_widen_pg_ctl_timeout_rewrites_only_the_short_timeout(monkeypatch):
    """The shim widens a short pg_ctl timeout and leaves every other call alone."""
    calls = []
    monkeypatch.setattr(local_pg, "_patched", False)
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: calls.append(kw) or "ran")

    local_pg.widen_pg_ctl_timeout(timeout=10, widened=120)
    patched = subprocess.run
    patched(["pg_ctl", "start"], timeout=10)
    patched(["pg_ctl", "stop"], timeout=30)
    patched(["something", "else"])

    assert [c.get("timeout") for c in calls] == [120, 30, None], (
        "only the short timeout is rewritten: %r" % calls)

    # Idempotent: a second call must not stack a second shim (each entry point
    # calls it, and stacked shims would rewrite an already-widened value).
    local_pg.widen_pg_ctl_timeout(timeout=10, widened=120)
    assert subprocess.run is patched, "widen_pg_ctl_timeout is not idempotent"


def test_wipe_cluster_dir_empties_the_directory(tmp_path):
    """A wipe leaves an existing, empty directory behind and reports leftovers."""
    pgdata = tmp_path / "sg_pgdata_unit"
    pgdata.mkdir()
    (pgdata / "postgresql.conf").write_text("port = 51000", encoding="utf-8")
    (pgdata / "base").mkdir()

    leftover = local_pg.wipe_cluster_dir(str(pgdata))

    assert leftover == [], "an emptied directory reports no leftover files"
    assert pgdata.is_dir(), "the directory itself is recreated, not deleted"
    assert list(pgdata.iterdir()) == []


def test_kill_attached_postgres_ignores_unrelated_directories(tmp_path):
    """Only postgres processes naming *this* data directory are touched."""
    assert local_pg.kill_attached_postgres(str(tmp_path / "sg_pgdata_absent")) == []


# The command lines below are the real shapes: pgserver starts postgres with a
# forward-slash -D path under the backslash temp dir tempfile.gettempdir()
# returns. The old substring test matched neither, so leftovers were never
# cleared on Windows.
PGDATA_WIN = r"C:\Users\chand\AppData\Local\Temp\sg_pgdata_v3"
POSTGRES_CMDLINE = (
    '"C:/Users/chand/SmartGarbage/venv/Lib/site-packages/pgserver/pginstall/bin/'
    'postgres.exe"  -D "C:/Users/chand/AppData/Local/Temp/sg_pgdata_v3" '
    '-h "127.0.0.1" -p 54811'
)


def test_is_postgres_for_matches_across_separators_and_case():
    assert local_pg.is_postgres_for(PGDATA_WIN, POSTGRES_CMDLINE), (
        "the postmaster's forward-slash -D path must match the backslash temp path")
    assert local_pg.is_postgres_for(PGDATA_WIN.replace("\\", "/"), POSTGRES_CMDLINE)
    assert local_pg.is_postgres_for(PGDATA_WIN.upper(), POSTGRES_CMDLINE), (
        "Windows paths are case-insensitive")


def test_is_postgres_for_does_not_match_siblings_or_other_dirs():
    assert not local_pg.is_postgres_for(
        r"C:\Users\chand\AppData\Local\Temp\sg_pgdata_v3_ab12cd", POSTGRES_CMDLINE), (
        "a retired sibling directory must not claim this postmaster")
    assert not local_pg.is_postgres_for(
        r"C:\Users\chand\AppData\Local\Temp\sg_pgdata_full", POSTGRES_CMDLINE), (
        "the suite cluster must not claim the stack's postmaster")
    assert not local_pg.is_postgres_for(PGDATA_WIN, "postgres.exe --forkaux 5452 3")


def test_boot_cluster_retries_in_a_fresh_directory(monkeypatch, capsys):
    """A failed boot retires the data directory and retries in a new one."""
    seen = []
    _install_fake_pgserver(
        monkeypatch,
        [RuntimeError("could not open file base/1/2610"), RuntimeError("still bad"),
         "postgresql://postgres:@127.0.0.1:51999/postgres"],
        seen)

    server, pgdata = local_pg.boot_cluster("sg_pgdata_unit_retry", label="unit")

    try:
        assert len(seen) == 3, "the runner retries up to three attempts: %r" % seen
        assert seen[0] != seen[1], "a failed directory is retired, never re-used"
        assert not Path(seen[0]).exists(), "the retired directory is deleted"
        assert seen[1].startswith(seen[0]), "the retry starts a sibling directory"
        assert pgdata == seen[2]
        assert server.get_uri().startswith("postgresql://")
        out = capsys.readouterr().out
        assert "[unit] PostgreSQL up at postgresql://" in out
        assert out.count("re-initialising from scratch") == 2
    finally:
        _cleanup(*set(seen), pgdata)


def test_boot_cluster_raises_the_last_failure(monkeypatch):
    """Three failed attempts propagate the error instead of returning nothing."""
    seen = []
    _install_fake_pgserver(monkeypatch, [RuntimeError("nope")], seen)

    with pytest.raises(RuntimeError, match="nope"):
        local_pg.boot_cluster("sg_pgdata_unit_fail", label="unit")

    assert len(seen) == 3, "every attempt is made before giving up: %r" % seen
    _cleanup(*set(seen))


def test_boot_cluster_fresh_discards_the_cached_directory(monkeypatch, tmp_path, capsys):
    """--fresh empties the cached cluster before booting it."""
    data_dir_name = "sg_pgdata_unit_fresh"
    cached = Path(local_pg.tempfile.gettempdir()) / data_dir_name
    cached.mkdir(exist_ok=True)
    (cached / "PG_VERSION").write_text("16", encoding="utf-8")
    seen = []
    _install_fake_pgserver(monkeypatch, ["postgresql://postgres:@127.0.0.1:52000/postgres"], seen)

    try:
        _server, pgdata = local_pg.boot_cluster(data_dir_name, label="unit", fresh=True)
        assert seen == [str(cached)], "the cached directory is reused after the wipe"
        assert list(cached.iterdir()) == [], "the previous cluster data is gone"
        assert "--fresh: discarding" in capsys.readouterr().out
    finally:
        _cleanup(str(cached), pgdata)


def test_wait_until_connectable_retries_then_succeeds(monkeypatch):
    """Cluster readiness is proven by a connection, not by the boot call."""
    attempts = []
    sleeps = []

    class FakeOperationalError(Exception):
        pass

    def connect(uri, connect_timeout=None):
        attempts.append((uri, connect_timeout))
        if len(attempts) < 3:
            raise FakeOperationalError("the database system is starting up")
        return types.SimpleNamespace(close=lambda: None)

    monkeypatch.setitem(sys.modules, "psycopg2", types.SimpleNamespace(
        connect=connect, OperationalError=FakeOperationalError))
    # wait_until_connectable imports time itself; both names are the same module
    # object, so patching the attribute here keeps the test instant.
    monkeypatch.setattr(time, "sleep", lambda s: sleeps.append(s))

    local_pg.wait_until_connectable("postgresql://x", label="unit", attempts=5, delay=2.0)

    assert len(attempts) == 3, "it keeps pinging until the cluster answers"
    assert sleeps == [2.0, 2.0], "it waits between attempts, not after success"


def test_wait_until_connectable_gives_up_loudly(monkeypatch):
    """An unreachable cluster fails with the timeout it actually spent."""
    class FakeOperationalError(Exception):
        pass

    def connect(uri, connect_timeout=None):
        raise FakeOperationalError("connection refused")

    monkeypatch.setitem(sys.modules, "psycopg2", types.SimpleNamespace(
        connect=connect, OperationalError=FakeOperationalError))
    monkeypatch.setattr(time, "sleep", lambda s: None)

    with pytest.raises(RuntimeError, match="after 4 seconds"):
        local_pg.wait_until_connectable("postgresql://x", attempts=2, delay=2.0)


def test_boot_and_export_publishes_the_uri_under_the_declared_var(monkeypatch, capsys):
    """The cluster head: boot + export happen in one call, no drift surface."""
    seen = []
    _install_fake_pgserver(
        monkeypatch,
        ["postgresql://postgres:@127.0.0.1:53001/postgres"], seen)
    monkeypatch.setenv("SG_UNIT_TEST_DB_URL", "sentinel-not-yet-booted")

    server, pgdata, uri = local_pg.boot_and_export(
        "sg_pgdata_unit_export", "SG_UNIT_TEST_DB_URL", label="unit")

    try:
        assert uri == "postgresql://postgres:@127.0.0.1:53001/postgres"
        assert os.environ["SG_UNIT_TEST_DB_URL"] == uri, (
            "the runner-visible environment must carry exactly the booted URI")
        assert server.get_uri() == uri, (
            "the returned server and the exported URI cannot disagree")
        assert uri in capsys.readouterr().out, (
            "the boot line must log the same URI that was exported")
    finally:
        _cleanup(*set(seen), pgdata)


def test_boot_and_export_exports_nothing_when_boot_fails(monkeypatch):
    """A failed boot must not leave a half-booted URI in the environment."""
    seen = []
    _install_fake_pgserver(monkeypatch, [RuntimeError("nope")], seen)
    monkeypatch.setenv("SG_UNIT_TEST_DB_URL", "sentinel-survives")

    with pytest.raises(RuntimeError, match="nope"):
        local_pg.boot_and_export(
            "sg_pgdata_unit_export_fail", "SG_UNIT_TEST_DB_URL", label="unit")

    assert os.environ["SG_UNIT_TEST_DB_URL"] == "sentinel-survives", (
        "a failed boot must propagate BEFORE exporting anything")
    _cleanup(*set(seen))


def test_cluster_handling_is_not_duplicated_in_the_entry_points():
    """The boot blocks must stay merged — including the env-export head.

    The regression this guards is duplication itself — a second copy of the
    retry/wipe rules silently drifts (that is how the two copies disagreed
    about re-using a failed data directory), and the three-line cluster head
    (boot → get_uri → os.environ export) is the same trap one level up: the
    runners already differed in label and echo lines before they were merged.
    Both entry points must go through local_pg, and the CI composite action
    must keep delegating to the stack script instead of growing cluster code
    of its own.
    """
    suite_runner = (ROOT / "run_pg_suite.py").read_text(encoding="utf-8")
    stack = (ROOT / "scripts" / "run_local_stack.py").read_text(encoding="utf-8")
    action = (ROOT / ".github" / "actions" / "boot-local-stack" / "action.yml").read_text(
        encoding="utf-8")

    for name, text in (("run_pg_suite.py", suite_runner),
                       ("scripts/run_local_stack.py", stack)):
        assert "from scripts import local_pg" in text, f"{name} must use the shared helper"
        assert "local_pg.boot_and_export(" in text, (
            f"{name} must boot AND publish the URI through local_pg.boot_and_export "
            "— the hand-written boot_cluster() + os.environ export head is the "
            "boilerplate this helper absorbed")
        # Match code, not prose: the comments and docstrings may (and should)
        # still explain subprocess/pg_ctl behaviour.
        for duplicate in ("pgserver.get_server", "ensure_postgres_running",
                          "import subprocess", "shutil.rmtree", "mkdtemp",
                          "psutil", "local_pg.boot_cluster(", ".get_uri()",
                          'os.environ["TEST_DATABASE_URL"] =',
                          'os.environ["DATABASE_URL"] ='):
            assert duplicate not in text, (
                f"{name} has its own copy of cluster handling ({duplicate}); "
                "move it into scripts/local_pg.py (the env-export head into "
                "local_pg.boot_and_export)")

    assert "scripts/run_local_stack.py" in action, (
        "the composite action must boot through the stack script")
    for duplicate in ("get_server", "ensure_postgres_running", "pg_ctl", "PGDATA"):
        assert duplicate not in action, (
            f"the composite action has grown its own cluster code ({duplicate}); "
            "it should only start scripts/run_local_stack.py and poll it")
