"""add webhook table, firmware sha256 and hot-path indexes

Revision ID: d4a5b6c7d8e9
Revises: c9d8e7f6a5b4
Create Date: 2026-08-01 13:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd4a5b6c7d8e9'
down_revision = 'c9d8e7f6a5b4'
branch_labels = None
depends_on = None


def upgrade():
    # Persisted webhook registrations (survive restarts, shared across workers).
    op.create_table(
        'webhook',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('url', sa.String(length=500), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('url')
    )
    # Firmware artifact integrity hash.
    op.add_column('firmware_release', sa.Column('sha256', sa.String(length=64), nullable=True))
    # Hot-path query indexes (ward sweeps + per-user ledger views).
    op.create_index('ix_complaint_ward_status', 'complaint', ['ward', 'status'])
    op.create_index('ix_bwg_declaration_user_id', 'bwg_declaration', ['user_id'])


def downgrade():
    op.drop_index('ix_bwg_declaration_user_id', table_name='bwg_declaration')
    op.drop_index('ix_complaint_ward_status', table_name='complaint')
    op.drop_column('firmware_release', 'sha256')
    op.drop_table('webhook')
