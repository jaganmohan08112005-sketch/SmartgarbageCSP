"""add_timescaledb_hypertable_for_telemetry

Revision ID: 20260803104714
Revises: 66d344fab3f9
Create Date: 2026-08-03 10:47:14

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '20260803104714'
down_revision: Union[str, None] = '66d344fab3f9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Convert BinTelemetryLog into a TimescaleDB hypertable when the extension
    # is available (Supabase / self-hosted Postgres with timescaledb enabled).
    # On SQLite or Postgres without timescaledb, the table is unchanged.
    conn = op.get_bind()
    try:
        conn.execute(sa.text("CREATE EXTENSION IF NOT EXISTS timescaledb"))
        conn.execute(sa.text("""
            SELECT create_hypertable('bin_telemetry_log', 'timestamp',
                                     chunk_time_interval => INTERVAL '7 days',
                                     if_not_exists => TRUE);
        """))
    except Exception:
        # timescaledb extension not available (SQLite, non-Timescale Postgres).
        # The existing index on (bin_id, timestamp) still serves point queries.
        pass


def downgrade() -> None:
    conn = op.get_bind()
    try:
        conn.execute(sa.text("SELECT drop_hypertable('bin_telemetry_log', if_exists => TRUE);"))
    except Exception:
        pass
