"""add maintenance_work_order (sensor-health follow-up workflow)

Revision ID: b0b1c2d3e4f5
Revises: 9f3a1c2b4d5e
Create Date: 2026-08-06
"""
from alembic import op
import sqlalchemy as sa

revision = 'b0b1c2d3e4f5'
down_revision = '9f3a1c2b4d5e'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'maintenance_work_order',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('bin_id', sa.Integer(), sa.ForeignKey('smart_bin.id'), nullable=False),
        sa.Column('worker_id', sa.Integer(), sa.ForeignKey('worker_profile.id'), nullable=True),
        sa.Column('created_by', sa.Integer(), sa.ForeignKey('user.id'), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='Scheduled'),
        sa.Column('due_date', sa.DateTime(), nullable=True),
        sa.Column('notes', sa.String(length=300), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('completed_by', sa.Integer(), sa.ForeignKey('user.id'), nullable=True),
        sa.Index('ix_maintenance_status_due', 'status', 'due_date'),
        sa.Index('ix_maintenance_worker_status', 'worker_id', 'status'),
    )


def downgrade():
    op.drop_table('maintenance_work_order')
