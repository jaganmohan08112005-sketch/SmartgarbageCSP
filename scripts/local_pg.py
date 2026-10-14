"""Embedded-Postgres cluster handling for every local harness — in one place.

Two entry points boot the bundled ``pgserver`` Postgres:

  * ``run_pg_suite.py``              — pytest against a real Postgres (the CI mirror)
  * ``scripts/run_local_stack.py``   — pgserver + Flask on :5057, the seeded stack
                                       used for recording and by the a11y/Playwright
                                       CI jobs

``.github/actions/boot-local-stack`` is the CI front door for the second one: it
runs that script and polls it for readiness. It holds no cluster code of its own,
so it needs no change when cluster handling changes here.

Both Python callers used to carry their own copy of the same four pieces — the
subprocess-timeout shim, the data-directory lifecycle, killing postgres
processes that still hold a retired directory open, and the boot-with-retry
loop — and the copies had drifted: only the suite runner could clear leftovers,
and only it retired a failed directory instead of re-using it (a still-attached
``postgres.exe`` keeps files open inside the directory, which is exactly what
makes ``initdb`` refuse it, so re-use is the retry path that keeps failing).
This module is the single home for that logic so a fix lands everywhere at once.

Each caller deliberately keeps its own data directory:

  * the suite drops and recreates the schema per test, so its cluster is
    disposable (``sg_pgdata_full``);
  * the demo stack holds seeded demo rows that the recorded walkthrough and the
    audit fixtures depend on (``sg_pgdata_v3``), so wiping it stays opt-in
    (``fresh=True``, which ``run_pg_suite.py --fresh`` also uses).

The directories live in the temp dir and survive runs, which is what keeps
startup fast (an already-initialised cluster is reused as-is, cached port and
all).
"""
import os
import re
import shutil
import subprocess
import tempfile

# pgserver passes pg_ctl a hardcoded timeout. On Windows, Defender's first scan
# of a freshly-spawned postgres.exe can outlast a short one, which then looks
# exactly like a broken cluster; widen it before booting. (Measured against the
# pinned pgserver==0.1.4: its pg_ctl call already passes timeout=120 and nothing
# else passes a timeout at all, so this shim is currently inert — it is kept
# because both callers came to depend on it and a future version that shortens
# the timeout must not turn a slow scan into a failed boot. pgserver resolves
# ``subprocess.run`` at call time, so installing the shim after ``import
# pgserver`` would work too; ``boot_cluster`` installs it first regardless.)
SHORT_PG_CTL_TIMEOUT = 10
WIDENED_PG_CTL_TIMEOUT = 120

_patched = False


def widen_pg_ctl_timeout(timeout=SHORT_PG_CTL_TIMEOUT, widened=WIDENED_PG_CTL_TIMEOUT):
    """Rewrite the given ``subprocess.run`` timeout to ``widened``, once.

    Safe to call from every entry point: the second call is a no-op, so the
    shim is never stacked twice.
    """
    global _patched
    if _patched:
        return
    original = subprocess.run

    def run_with_widened_timeout(*args, **kwargs):
        if kwargs.get("timeout") == timeout:
            kwargs["timeout"] = widened
        return original(*args, **kwargs)

    run_with_widened_timeout.sg_original = original
    subprocess.run = run_with_widened_timeout
    _patched = True


def is_postgres_for(pgdata, cmdline):
    """True when ``cmdline`` is a postgres process attached to ``pgdata``.

    Separators and case are normalised because the two sides do not agree on a
    platform where it matters: pgserver starts postgres with a forward-slash
    ``-D "C:/Users/.../sg_pgdata_v3"`` (measured on Windows), while
    ``tempfile.gettempdir()`` hands back backslashes. A plain substring test
    therefore never matched on Windows, so the leftovers below were never
    cleared there — the failure the wipe/retry path exists to survive.

    The match must end on a boundary so retiring ``sg_pgdata_v3`` cannot take
    down a sibling cluster such as ``sg_pgdata_v3_ab12cd`` (which is exactly
    what a previous retirement creates).
    """
    needle = os.path.normpath(pgdata).replace("\\", "/").lower()
    haystack = cmdline.replace("\\", "/").lower()
    return re.search(re.escape(needle) + r'(?=$|[\s"\'/])', haystack) is not None


def kill_attached_postgres(pgdata):
    """Terminate postgres processes still attached to this data directory.

    A killed or failed run leaves postgres.exe holding files open inside
    ``pgdata``, so nothing below can delete them. pgserver does the same thing
    internally before initdb, but it needs an empty directory to get that far.
    Only processes whose command line names *this* directory are touched.
    """
    import psutil  # ships with pgserver

    killed = []
    for proc in psutil.process_iter(attrs=["name", "cmdline"]):
        cmd = " ".join(proc.info.get("cmdline") or [])
        if proc.info.get("name", "").startswith("postgres") and is_postgres_for(pgdata, cmd):
            try:
                proc.terminate()
                proc.wait(3)
            except psutil.TimeoutExpired:
                proc.kill()
            except psutil.Error:
                continue
            killed.append(proc.pid)
    return killed


def wipe_cluster_dir(pgdata):
    """Empty the data directory; return whatever could not be removed."""
    kill_attached_postgres(pgdata)
    shutil.rmtree(pgdata, ignore_errors=True)
    os.makedirs(pgdata, exist_ok=True)
    return sorted(os.listdir(pgdata))


def retire_cluster_dir(pgdata, data_dir_name):
    """Abandon an unusable directory and hand back a brand-new, empty one.

    Retiring beats emptying: a postgres still attached to the old directory
    keeps files open there, which is what makes an in-place retry fail with
    "could not open file base/..." instead of booting.
    """
    kill_attached_postgres(pgdata)
    shutil.rmtree(pgdata, ignore_errors=True)
    return tempfile.mkdtemp(prefix=data_dir_name + "_")


def boot_cluster(data_dir_name, label="pg", fresh=False, attempts=3):
    """Boot the embedded cluster; return ``(server, pgdata)``.

    ``data_dir_name`` is the directory under the temp dir to reuse across runs.
    ``fresh=True`` discards it first (``--fresh``). A boot failure retires the
    directory and retries in a new one, because a failure usually means the
    cached cluster is unusable; the last failure propagates.
    """
    widen_pg_ctl_timeout()
    import pgserver  # noqa: E402  (after the timeout shim, see module docstring)

    pgdata = os.path.join(tempfile.gettempdir(), data_dir_name)
    if fresh:
        print(f"[{label}] --fresh: discarding {pgdata}")
        leftover = wipe_cluster_dir(pgdata)
        if leftover:
            retired, pgdata = pgdata, tempfile.mkdtemp(prefix=data_dir_name + "_")
            print(f"[{label}] {retired} still holds {leftover[:3]}; "
                  f"starting in a fresh cluster at {pgdata}")
    else:
        os.makedirs(pgdata, exist_ok=True)

    for attempt in range(1, attempts + 1):
        try:
            server = pgserver.get_server(pgdata=pgdata)
            server.ensure_postgres_running()
        except Exception as exc:
            print(f"[{label}] attempt {attempt} on {pgdata} failed: {exc}")
            if attempt == attempts:
                raise
            pgdata = retire_cluster_dir(pgdata, data_dir_name)
            print(f"[{label}] re-initialising from scratch at {pgdata}")
            continue
        print(f"[{label}] PostgreSQL up at {server.get_uri()} (attempt {attempt})")
        return server, pgdata


def wait_until_connectable(uri, label="pg", attempts=20, delay=2.0):
    """Block until the cluster really accepts connections, then return.

    ``ensure_postgres_running()`` only proves the server process was started, so
    anything that is about to run migrations in-process waits for a raw
    connection first instead of racing the first connect.
    """
    import time

    import psycopg2

    for attempt in range(1, attempts + 1):
        try:
            conn = psycopg2.connect(uri, connect_timeout=5)
            conn.close()
            print(f"[{label}] DB ping OK")
            return
        except psycopg2.OperationalError as exc:
            print(f"[{label}] DB ping attempt {attempt}/{attempts} failed: {exc}")
            time.sleep(delay)
    raise RuntimeError(f"Could not connect to pgserver after {int(attempts * delay)} seconds")
