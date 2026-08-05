"""merge heads + dispatch assignment table

Two parallel feature branches (telemetry history b2c3d4e5f6a7 and razorpay
b1c2d3e4f5a6) were created off the same parent c9d8e7f6a5b4, leaving alembic
with two heads. This revision merges them (down_revision is a tuple) AND
creates the proactive-dispatch assignment table, so `flask db upgrade` works
on a fresh DB in one linear chain.

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7, b1c2d3e4f5a6
Create Date: 2026-08-02
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'c3d4e5f6a7b8'
down_revision = ('b2c3d4e5f6a7', 'b1c2d3e4f5a6')
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'dispatch_assignment',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('bin_id', sa.Integer(), sa.ForeignKey('smart_bin.id'), nullable=False),
        sa.Column('worker_id', sa.Integer(), sa.ForeignKey('worker_profile.id'), nullable=True),
        sa.Column('eta_hours', sa.Float(), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('assigned_at', sa.DateTime(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )
    op.create_index('ix_dispatch_bin_status', 'dispatch_assignment', ['bin_id', 'status'])
    op.create_index('ix_dispatch_worker_status', 'dispatch_assignment', ['worker_id', 'status'])
    # Race guard: at most one Assigned assignment per bin (partial unique
    # index — supported on both SQLite and Postgres).
    op.create_index('uq_dispatch_bin_assigned', 'dispatch_assignment', ['bin_id'],
                    unique=True,
                    sqlite_where=sa.text("status = 'Assigned'"),
                    postgresql_where=sa.text("status = 'Assigned'"))


def downgrade():
    op.drop_index('uq_dispatch_bin_assigned', table_name='dispatch_assignment')
    op.drop_index('ix_dispatch_worker_status', table_name='dispatch_assignment')
    op.drop_index('ix_dispatch_bin_status', table_name='dispatch_assignment')
    op.drop_table('dispatch_assignment')
