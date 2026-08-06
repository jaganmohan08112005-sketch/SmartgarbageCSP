"""add lid_open to smart_bin (v5 sensor-noise layer)

Revision ID: 9f3a1c2b4d5e
Revises: h5b6c7d8e9f0
Create Date: 2026-08-05
"""
from alembic import op
import sqlalchemy as sa

revision = '9f3a1c2b4d5e'
down_revision = 'h5b6c7d8e9f0'
branch_labels = None
depends_on = None


def upgrade():
    # Backfill existing rows as 'closed'. The server_default stays (SQLite has
    # no ALTER COLUMN ... DROP DEFAULT, and it matches the model's False
    # default exactly, so there is no drift between the two paths).
    op.add_column('smart_bin',
                  sa.Column('lid_open', sa.Boolean(), nullable=False,
                            server_default=sa.false()))


def downgrade():
    op.drop_column('smart_bin', 'lid_open')
