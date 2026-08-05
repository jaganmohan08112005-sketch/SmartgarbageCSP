"""add complaint status log for citizen tracking timeline

Revision ID: g4a5b6c7d8e9
Revises: f3a4b5c6d7e8
Create Date: 2026-08-03

Citizen complaint-tracking: a complaint's status timeline (Submitted →
Under Review → Assigned → In Progress → Escalated → Resolved → Closed)
is recorded as one row per transition in complaint_status_log, so the
public /track/<token> page shows a real history instead of just the
current status. batch DDL keeps SQLite and Postgres on the same path.
"""
from alembic import op
import sqlalchemy as sa

revision = 'g4a5b6c7d8e9'
down_revision = '20260803120000'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'complaint_status_log',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('complaint_id', sa.Integer(),
                  sa.ForeignKey('complaint.id'), nullable=False, index=True),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('note', sa.String(length=300), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
    )
    with op.batch_alter_table('complaint_status_log') as batch_op:
        batch_op.create_index('ix_complaint_status_log_complaint_created',
                              ['complaint_id', 'created_at'])


def downgrade():
    with op.batch_alter_table('complaint_status_log') as batch_op:
        batch_op.drop_index('ix_complaint_status_log_complaint_created')
    op.drop_table('complaint_status_log')
