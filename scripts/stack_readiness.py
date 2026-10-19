#!/usr/bin/env python3
"""The single definition of what it means for the local stack to be "up".

Both readiness consumers read their verdict from this one module:

  * ``.github/actions/boot-local-stack`` (Playwright + a11y CI) polls the CLI
    below instead of its own ``curl GET /`` — a homepage 200 said nothing
    about the database.
  * ``scripts/run_local_stack.py`` (local boot + demo-video recording) takes
    its pre-migration DB gate and its post-boot contract from here too.

The contract, in two layers:

1. ``wait_postgres(uri, ...)`` — boot step, pre-migrations. The stack cannot
   run migrations before the cluster answers a raw connection, so this is a
   prerequisite, not the readiness verdict.

2. ``app_ready(base_url)`` — THE readiness verdict, identical for CI and
   local: ``GET {base_url}/health`` must answer HTTP 200 AND its JSON
   ``checks.database.status`` must be ``"pass"``. That check is a real
   ``SELECT 1`` executed by the app against the very Postgres it serves
   from, so the external poll and the script's own DB ping can no longer
   disagree about what "ready" means — they both defer to the same endpoint.
   (Seeding happens before the server starts in ``run_local_stack.py``, so a
   passing probe also implies the demo fixtures exist. Mail/Redis posture
   cannot fail the local verdict: an unconfigured transport reports
   ``warning: null`` and does not flip /health to 503.)

CI usage (bash loop keeps the polling cadence and log timestamps local):

    for i in $(seq 1 60); do
      if python scripts/stack_readiness.py --base-url http://127.0.0.1:5057 \\
         --attempts 1 --timeout 5; then break; fi
      sleep 3
    done

Exit code 0 = ready, 1 = not ready (with the failure reason on stdout).

Standard library only (urllib/json): importing the app here would slow every
poll by seconds and drag in env side effects (SECRET_KEY etc.).
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request

HEALTH_PATH = '/health'


def app_ready(base_url, timeout=5.0):
    """Return ``(ok, detail)`` for the shared stack-readiness contract."""
    url = base_url.rstrip('/') + HEALTH_PATH
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            status, body = resp.status, resp.read()
    except urllib.error.HTTPError as exc:
        # 503 unhealthy: decode the body so the failure names the check.
        try:
            payload = json.loads(exc.read() or b'{}')
            db = (payload.get('checks') or {}).get('database') or {}
            return False, (f"HTTP {exc.code}; database check "
                           f"'{db.get('status')}': {db.get('error')}")
        except Exception:
            return False, f"HTTP {exc.code} (unparsable body)"
    except Exception as exc:
        return False, f'not reachable: {exc}'
    if status != 200:
        return False, f'HTTP {status}'
    try:
        payload = json.loads(body)
    except Exception:
        return False, f'HTTP {status} with unparsable JSON body'
    db = (payload.get('checks') or {}).get('database') or {}
    if db.get('status') != 'pass':
        return False, (f"database check '{db.get('status')}': "
                       f"{db.get('error') or 'SELECT 1 failed'}")
    return True, 'database SELECT 1 pass'


def wait_postgres(uri, label='stack'):
    """Block until the cluster accepts connections (boot prerequisite).

    Delegates to ``scripts/local_pg.wait_until_connectable`` so the retry/
    wipe rules stay owned by the cluster module; hosted here so both
    readiness surfaces import the funnel from the same place.
    """
    from . import local_pg
    local_pg.wait_until_connectable(uri, label=label)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description='Probe the shared local-stack readiness contract '
                    f'({HEALTH_PATH} → 200 with database check "pass").')
    parser.add_argument('--base-url', required=True,
                        help='stack origin, e.g. http://127.0.0.1:5057')
    parser.add_argument('--attempts', type=int, default=1,
                        help='probe attempts before giving up (default 1)')
    parser.add_argument('--delay', type=float, default=3.0,
                        help='seconds between attempts (default 3)')
    parser.add_argument('--timeout', type=float, default=5.0,
                        help='per-probe socket timeout (default 5)')
    args = parser.parse_args(argv)

    for attempt in range(1, args.attempts + 1):
        ok, detail = app_ready(args.base_url, timeout=args.timeout)
        verdict = 'READY' if ok else 'not ready'
        print(f'[readiness] {args.base_url} {verdict} '
              f'(attempt {attempt}/{args.attempts}): {detail}')
        if ok:
            return 0
        if attempt < args.attempts:
            sys.stdout.flush()
            import time
            time.sleep(args.delay)
    return 1


if __name__ == '__main__':
    sys.exit(main())
