"""Tests for scripts/migrate_sqlite_to_pg.py.

Uses two temp SQLite files as stand-ins for source and target so the tests
run without a real Postgres: the script's idempotency and FK-order logic is
dialect-agnostic, and SQLite supports ON CONFLICT DO NOTHING exactly like
Postgres does for the paths exercised here.
"""

import os
import sys
import tempfile
from datetime import datetime, timezone

import sqlalchemy as sa

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.migrate_sqlite_to_pg import migrate  # noqa: E402


def _build_db(path):
    """Create ward + complaint tables (FK) and seed rows; returns the seed datetime."""
    eng = sa.create_engine(f"sqlite:///{path}")
    meta = sa.MetaData()
    sa.Table(
        "ward", meta,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
    )
    sa.Table(
        "complaint", meta,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("ward_id", sa.Integer, sa.ForeignKey("ward.id"), nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=False)),
    )
    meta.create_all(eng)
    dt = datetime(2026, 8, 1, 10, 30, 0)  # naive on purpose (SQLite has no tz)
    with eng.begin() as conn:
        conn.execute(meta.tables["ward"].insert(),
                     [{"name": "Ward 1 - MVGR"}, {"name": "Ward 2 - Junction"}])
        conn.execute(meta.tables["complaint"].insert(), [
            {"ward_id": 1, "description": "Missed pickup", "created_at": dt},
            {"ward_id": 2, "description": "Bin overflow", "created_at": dt},
        ])
    eng.dispose()
    return dt


def _build_target(path, created_at_tz=False):
    meta = sa.MetaData()
    sa.Table(
        "ward", meta,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
    )
    sa.Table(
        "complaint", meta,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("ward_id", sa.Integer, sa.ForeignKey("ward.id"), nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=created_at_tz)),
    )
    eng = sa.create_engine(f"sqlite:///{path}")
    meta.create_all(eng)
    eng.dispose()


def _read(path):
    eng = sa.create_engine(f"sqlite:///{path}")
    meta = sa.MetaData()
    meta.reflect(bind=eng)
    ward_t, comp_t = meta.tables["ward"], meta.tables["complaint"]
    with eng.connect() as conn:
        wards = conn.execute(sa.select(sa.func.count()).select_from(ward_t)).scalar()
        complaints = conn.execute(sa.select(sa.func.count()).select_from(comp_t)).scalar()
        dt = conn.execute(sa.select(comp_t.c.created_at).where(comp_t.c.id == 1)).scalar()
        orphans = conn.execute(sa.text(
            "SELECT COUNT(*) FROM complaint c LEFT JOIN ward w ON c.ward_id = w.id "
            "WHERE w.id IS NULL")).scalar()
    eng.dispose()
    return wards, complaints, dt, orphans


def _paths():
    fd, src = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    fd2, dst = tempfile.mkstemp(suffix=".db")
    os.close(fd2)
    return src, dst


def test_migrates_rows_in_fk_order():
    src, dst = _paths()
    try:
        dt = _build_db(src)
        _build_target(dst)

        stats = migrate(src, dst)
        assert stats["ward"]["inserted"] == 2
        assert stats["complaint"]["inserted"] == 2

        wards, complaints, got_dt, orphans = _read(dst)
        assert wards == 2
        assert complaints == 2
        assert orphans == 0  # FK integrity preserved across the copy
        # naive stays naive for a tz-less target column (SQLite drops tz anyway)
        assert got_dt == dt
    finally:
        for p in (src, dst):
            try:
                os.remove(p)
            except OSError:
                pass


def test_idempotent_rerun_inserts_nothing():
    src, dst = _paths()
    try:
        _build_db(src)
        _build_target(dst)
        migrate(src, dst)
        stats2 = migrate(src, dst)
        assert stats2["ward"]["inserted"] == 0
        assert stats2["complaint"]["inserted"] == 0
        wards, complaints, _, _ = _read(dst)
        assert wards == 2
        assert complaints == 2
    finally:
        for p in (src, dst):
            try:
                os.remove(p)
            except OSError:
                pass


def test_dry_run_writes_nothing():
    src, dst = _paths()
    try:
        _build_db(src)
        _build_target(dst)
        stats = migrate(src, dst, dry_run=True)
        assert stats["ward"]["dry_run"] is True
        assert stats["complaint"]["dry_run"] is True
        wards, complaints, _, _ = _read(dst)
        assert wards == 0
        assert complaints == 0
    finally:
        for p in (src, dst):
            try:
                os.remove(p)
            except OSError:
                pass


def test_naive_datetime_becomes_aware_for_tz_column():
    src, dst = _paths()
    try:
        _build_db(src)  # naive source datetimes
        _build_target(dst, created_at_tz=True)  # timestamptz-equivalent target

        migrate(src, dst)
        _, _, got_dt, _ = _read(dst)
        # SQLite cannot persist tz offsets, so the observable guarantee here is
        # that the wall-clock value survives unshifted (aware-UTC conversion is
        # asserted directly against the normalizer below).
        assert got_dt == datetime(2026, 8, 1, 10, 30, 0)
    finally:
        for p in (src, dst):
            try:
                os.remove(p)
            except OSError:
                pass


def test_datetime_normalizer_converts_naive_to_aware_utc():
    """Direct check of the tz branch SQLite can't observe: naive -> aware UTC."""
    from scripts.migrate_sqlite_to_pg import _datetime_normalizers

    meta = sa.MetaData()
    t = sa.Table("t", meta, sa.Column("id", sa.Integer, primary_key=True),
                 sa.Column("created_at", sa.DateTime(timezone=True)))
    norm = _datetime_normalizers(t)
    naive = datetime(2026, 8, 1, 10, 30, 0)
    out = norm["created_at"](naive)
    assert out.tzinfo is not None
    assert out == datetime(2026, 8, 1, 10, 30, 0, tzinfo=timezone.utc)
    # aware input is passed through in UTC
    aware = datetime(2026, 8, 1, 15, 0, 0, tzinfo=timezone.utc)
    assert norm["created_at"](aware) == aware

    meta2 = sa.MetaData()
    t2 = sa.Table("t2", meta2, sa.Column("id", sa.Integer, primary_key=True),
                  sa.Column("created_at", sa.DateTime(timezone=False)))
    norm2 = _datetime_normalizers(t2)
    out2 = norm2["created_at"](aware)  # aware -> naive UTC (tz-less target)
    assert out2.tzinfo is None
    assert out2 == datetime(2026, 8, 1, 15, 0, 0)


def test_missing_target_table_is_skipped():
    src, dst = _paths()
    try:
        _build_db(src)
        # target only has `ward` — complaint must be skipped, not fatal
        meta = sa.MetaData()
        sa.Table("ward", meta,
                 sa.Column("id", sa.Integer, primary_key=True),
                 sa.Column("name", sa.String(100), nullable=False))
        eng = sa.create_engine(f"sqlite:///{dst}")
        meta.create_all(eng)
        eng.dispose()

        stats = migrate(src, dst)
        assert stats["ward"]["inserted"] == 2
        assert stats["complaint"]["missing_target"] is True
    finally:
        for p in (src, dst):
            try:
                os.remove(p)
            except OSError:
                pass
