"""add maintenance overdue escalation dedupe column

Revision ID: c1d2e3f4a5b6
Revises: b0b1c2d3e4f5
Create Date: 2026-08-06
"""
from alembic import op
import sqlalchemy as sa

revision = 'c1d2e3f4a5b6'
down_revision = 'b0b1c2d3e4f5'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'maintenance_work_order',
        sa.Column('escalated_at', sa.DateTime(), nullable=True),
    )


def downgrade():
    op.drop_column('maintenance_work_order', 'escalated_at')
