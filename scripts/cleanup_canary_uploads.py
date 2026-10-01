"""One-off cleanup of orphaned canary/test uploads in Supabase Storage.

Deletes exactly the orphaned objects identified by the read-only census query
and re-verified on 2026-10-01 (no surviving illegal_dump_report row references
them, and all predate the canary-suppression fix that went live 2026-09-30):

    illegal/illegal_18039_trash_00830.jpg   2026-09-29 14:52   canary accept-probe (pre-fix)
    illegal/illegal_74338_t.jpg             2026-09-29 16:01   canary reject-probe
    illegal/illegal_34845_trash_00830.jpg   2026-09-29 16:30   canary accept-probe (pre-fix)

RETAINED (do NOT delete): illegal/illegal_89655_office.jpg — although it also
dates from session-era test traffic, it is still referenced by report id=4
("live verification probe", 2026-09-28). The original Sep-30 census missed that
reference; the re-verification reference-check caught it before any deletion,
which is exactly what that check exists for.

Safety properties:
- No wildcards/patterns: deletes exactly the names below, nothing else.
- Re-lists the bucket first and aborts if the listing changed since the census
  (an object appeared or vanished) or if any target is unexpectedly referenced
  by a surviving report row.
- Uses the same SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY credentials the app
  itself uses for storage removal in app/jobs.py — but talks to the Storage
  REST API directly via requests: the pinned supabase-py==2.15.0 validates
  keys with a legacy-JWT-only regex and raises "Invalid API key" on the new
  sb_secret_… key format before ever hitting the network. The REST API
  accepts both formats.
"""

import sys

from dotenv import load_dotenv

load_dotenv()
import os  # noqa: E402  (after load_dotenv so os.environ sees .env)

import requests  # noqa: E402

# The exact orphan set re-verified on 2026-10-01, name -> expected size.
TARGETS = {
    "illegal/illegal_18039_trash_00830.jpg": 5174,
    "illegal/illegal_74338_t.jpg": 14227,
    "illegal/illegal_34845_trash_00830.jpg": 5174,
}

# Known objects that stay (referenced by surviving rows); see docstring.
RETAINED = {"illegal/illegal_89655_office.jpg"}

BUCKET = "uploads"
PREFIX = "illegal/"


def _storage_headers(key):
    # sb_secret_ keys require the key in BOTH the apikey header and the
    # Authorization Bearer header; legacy JWTs work with Bearer alone, and
    # sending apikey too is harmless for them.
    return {"Authorization": "Bearer %s" % key, "apikey": key,
            "Content-Type": "application/json"}


def _storage_list(base_url, headers, prefix):
    """List objects under `prefix` via POST /storage/v1/object/list/{bucket}.
    Returns names relative to the bucket root (leading prefix stripped)."""
    r = requests.post("%s/storage/v1/object/list/%s" % (base_url, BUCKET),
                      headers=headers,
                      json={"prefix": prefix, "limit": 100, "offset": 0,
                            "sortBy": {"column": "name", "order": "asc"}},
                      timeout=30)
    r.raise_for_status()
    names = []
    for item in r.json():
        name = (item or {}).get("name") or ""
        if name.startswith(prefix):
            name = name[len(prefix):]
        if name:
            names.append(name)
    return sorted(set(names))


def _storage_remove(base_url, headers, paths):
    """Bulk-remove objects via DELETE /storage/v1/object/{bucket}
    (the same endpoint supabase-py's .remove() wraps)."""
    r = requests.delete("%s/storage/v1/object/%s" % (base_url, BUCKET),
                        headers=headers, json={"prefixes": paths}, timeout=30)
    r.raise_for_status()
    return r.json()


def main() -> int:
    url = os.environ.get("SUPABASE_URL")
    key = (os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
           or os.environ.get("SUPABASE_ANON_KEY"))
    if not url or not key:
        print("ABORT: SUPABASE_URL / service key not configured in .env")
        return 2

    client_headers = _storage_headers(key)

    # ---- Step 1: re-verify the live listing against the census -------------
    try:
        live_names = set(_storage_list(url, client_headers, PREFIX))
    except Exception as exc:
        print(f"ABORT: could not list bucket {BUCKET}/{PREFIX}: {exc}")
        return 2
    expected_stems = {name.split("/", 1)[1] for name in TARGETS}

    unexpected = live_names - expected_stems - {p.split("/", 1)[1] for p in RETAINED}
    missing = expected_stems - live_names
    if unexpected or missing:
        print("ABORT: bucket listing changed since the census — manual review needed")
        print(f"  unexpected objects: {sorted(unexpected) or 'none'}")
        print(f"  census objects missing: {sorted(missing) or 'none'}")
        return 2

    # ---- Step 2: cross-check no surviving report row references them -------
    # (Defence in depth: the census query already proved this, but re-check.)
    # CANARY_CLEANUP_DB_VERIFIED=external skips the local Flask-based check —
    # only for machines where DATABASE_URL is unavailable — and requires the
    # operator to have verified 0 references externally (e.g. via the Supabase
    # MCP execute_sql) IMMEDIATELY BEFORE the run. The default is strict.
    if os.environ.get('CANARY_CLEANUP_DB_VERIFIED') == 'external':
        print('NOTE: DB reference check bypassed via CANARY_CLEANUP_DB_VERIFIED=external')
        print('      (operator attests fresh external verification of 0 references)')
    else:
        try:
            from app import create_app  # noqa: F401  -- only needed for db context
            from app.models import IllegalDumpReport
            from app import db

            app = create_app()
            with app.app_context():
                urls = [row[0] for row in
                        db.session.query(IllegalDumpReport.scrubbed_photo).all()
                        if row[0]]
                hits = [u for u in urls
                        if any(t.rstrip("/") in u for t in TARGETS)]
                if hits:
                    print("ABORT: a report row now references a target — do not delete")
                    for h in hits:
                        print("  referenced:", h)
                    return 2
        except Exception as exc:
            print(f"ABORT: could not verify report references ({exc}) — manual review")
            return 2

    # ---- Step 3: delete exactly the three known names -----------------------
    print("Deleting:")
    for name, size in sorted(TARGETS.items()):
        print(f"  {name}  ({size} bytes)")

    try:
        paths = sorted(TARGETS)
        removed = _storage_remove(url, client_headers, paths)
        print("Storage API response:", removed)
    except Exception as exc:
        print(f"FAILED during remove(): {exc}")
        return 1

    # ---- Step 4: verify ------------------------------------------------------
    try:
        remaining = [n for n in _storage_list(url, client_headers, PREFIX)
                     if n not in {p.split("/", 1)[1] for p in RETAINED}]
        if remaining:
            print(f"WARNING: unexpected objects still present after delete: {remaining}")
            return 1
        print("Verified: uploads/illegal/ holds only the retained object(s).")
    except Exception as exc:
        print(f"Could not re-list after delete: {exc}")
        return 1

    print("Cleanup complete: %d orphaned canary JPEGs removed." % len(TARGETS))
    return 0


if __name__ == "__main__":
    sys.exit(main())
