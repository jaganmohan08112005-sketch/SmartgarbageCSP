#!/usr/bin/env python3
"""One-time SQLite -> PostgreSQL/Supabase data migration.

Copies every table present in the source SQLite database into the target
PostgreSQL database (e.g. Supabase), in foreign-key-safe order and
idempotently: rows whose primary key already exists in the target are
skipped, so re-running after a partial failure is safe.

Datetime values are normalized per the *target* column type so Postgres
timestamptz / timestamp columns never reject rows that SQLite happily
stored (SQLite has no timezone awareness): naive values are assumed UTC.

Usage:
    python scripts/migrate_sqlite_to_pg.py                          # env defaults
    python scripts/migrate_sqlite_to_pg.py --source /data/garbage.db --target "$DATABASE_URL"
    python scripts/migrate_sqlite_to_pg.py --dry-run                # report only
    python scripts/migrate_sqlite_to_pg.py --source local.db --target "$DATABASE_URL" --verbose

Env fallbacks:
    SQLITE_PATH       source path (default garbage.db)
    DATABASE_URL      target URL  (default none -> requires --target)
"""

import argparse
import sys
from collections import defaultdict, deque
from datetime import datetime, timezone

import sqlalchemy as sa
from sqlalchemy import MetaData, Table, create_engine, inspect


def _topological_tables(src_meta):
    """Order tables so referenced (parent) tables come before referencing ones."""
    deps = {t.name: set() for t in src_meta.tables.values()}
    for t in src_meta.tables.values():
        for fk in t.foreign_keys:
            ref = fk.column.table.name
            if ref in deps and ref != t.name:
                deps[t.name].add(ref)
    ready = [name for name, d in deps.items() if not d]
    ordered = []
    while ready:
        ready.sort()
        name = ready.pop(0)
        ordered.append(name)
        for other, d in deps.items():
            if name in d:
                d.discard(name)
                if not d:
                    ready.append(other)
    leftovers = [n for n, d in deps.items() if d]  # cycles (none expected)
    return ordered + sorted(leftovers)


def _datetime_normalizers(tgt_table):
    """Return {col_name: callable(value)->value} for DateTime columns."""
    norm = {}
    for col in tgt_table.columns:
        if isinstance(col.type, sa.DateTime):
            tz = bool(getattr(col.type, "timezone", False))
            if tz:
                def _to_aware(v):
                    if v is None:
                        return None
                    return v if v.tzinfo is not None else v.replace(tzinfo=timezone.utc)
                norm[col.name] = _to_aware
            else:
                def _to_naive(v):
                    if v is None:
                        return None
                    return v.astimezone(timezone.utc).replace(tzinfo=None) if v.tzinfo is not None else v
                norm[col.name] = _to_naive
    return norm


def _row_mapping(row, cols):
    return {c.name: row[c.name] for c in cols}


def _coerce_url(url):
    """Accept either a full SQLAlchemy URL or a bare file path (-> SQLite)."""
    return url if "://" in url else f"sqlite:///{url}"


def migrate(source_path, target_url, dry_run=False, verbose=False):
    """Copy all data from source SQLite into target DB. Returns per-table stats."""
    src_engine = create_engine(_coerce_url(source_path))
    tgt_engine = create_engine(_coerce_url(target_url), pool_pre_ping=True)
    try:
        src_meta = MetaData()
        src_meta.reflect(bind=src_engine)

        tgt_insp = inspect(tgt_engine)
        tgt_tables = set(tgt_insp.get_table_names())

        order = _topological_tables(src_meta)
        if verbose:
            print(f"copy order: {order}")

        stats = {}
        total_inserted = 0
        for name in order:
            src_table = src_meta.tables[name]
            if name not in tgt_tables:
                if verbose:
                    print(f"[skip] {name}: not present in target (target may be newer)")
                stats[name] = {"rows": 0, "inserted": 0, "skipped": 0, "missing_target": True}
                continue

            with src_engine.connect() as conn:
                rows = conn.execute(sa.select(src_table)).mappings().all()

            if dry_run:
                stats[name] = {"rows": len(rows), "inserted": 0, "skipped": 0, "dry_run": True}
                if verbose:
                    print(f"[dry]  {name}: {len(rows)} row(s) would be copied")
                continue

            if not rows:
                stats[name] = {"rows": 0, "inserted": 0, "skipped": 0}
                continue

            tgt_table = Table(name, MetaData(), autoload_with=tgt_engine)
            norm = _datetime_normalizers(tgt_table)
            cols = [c for c in src_table.columns if c.name in tgt_table.c]
            pk_cols = [c.name for c in tgt_table.primary_key.columns]

            inserted = 0
            skipped = 0
            with tgt_engine.begin() as conn:
                for row in rows:
                    payload = {c.name: row[c.name] for c in cols}
                    for col_name, fn in norm.items():
                        if col_name in payload:
                            payload[col_name] = fn(payload[col_name])
                    dialect = tgt_engine.dialect.name
                    if dialect == "postgresql":
                        from sqlalchemy.dialects.postgresql import insert as _insert
                        stmt = _insert(tgt_table).values(**payload).on_conflict_do_nothing(
                            index_elements=pk_cols or None)
                    elif dialect == "sqlite":
                        from sqlalchemy.dialects.sqlite import insert as _insert
                        stmt = _insert(tgt_table).values(**payload).on_conflict_do_nothing(
                            index_elements=pk_cols or None)
                    else:
                        stmt = tgt_table.insert().values(**payload)
                    result = conn.execute(stmt)
                    inserted += result.rowcount if result.rowcount and result.rowcount > 0 else 0
                    skipped += 0 if (result.rowcount and result.rowcount > 0) else 1
            stats[name] = {"rows": len(rows), "inserted": inserted, "skipped": skipped}
            total_inserted += inserted
            if verbose:
                print(f"[ok]   {name}: {len(rows)} read, {inserted} inserted, {skipped} skipped (conflict)")

        print(f"done: {total_inserted} row(s) inserted across {len(order)} table(s)"
              + (" [DRY RUN — nothing written]" if dry_run else ""))
        return stats
    finally:
        src_engine.dispose()
        tgt_engine.dispose()


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", default=None, help="SQLite file (default: $SQLITE_PATH or garbage.db)")
    ap.add_argument("--target", default=None, help="Target PostgreSQL URL (default: $DATABASE_URL)")
    ap.add_argument("--dry-run", action="store_true", help="Report row counts without writing")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    source = args.source or os_environ("SQLITE_PATH") or "garbage.db"
    target = args.target or os_environ("DATABASE_URL")
    if not target:
        print("error: no target URL — pass --target or set DATABASE_URL", file=sys.stderr)
        return 2
    try:
        migrate(source, target, dry_run=args.dry_run, verbose=args.verbose)
        return 0
    except Exception as e:
        print(f"error: migration failed: {e}", file=sys.stderr)
        return 1


def os_environ(key):
    import os
    return os.environ.get(key)


if __name__ == "__main__":
    sys.exit(main())
