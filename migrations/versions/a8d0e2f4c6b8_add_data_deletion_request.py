"""add data_deletion_request table (DPDP Act, 2023 right-to-erasure workflow)

Backs the /data-deletion request form and the admin queue that resolves it.
Completing a request pseudonymizes the account (personal fields scrubbed,
history retained) rather than hard-deleting rows the panchayat must keep.

Revision ID: a8d0e2f4c6b8
Revises: a7c9e1f3b5d7
Create Date: 2026-09-21
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a8d0e2f4c6b8'
down_revision = 'a7c9e1f3b5d7'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'data_deletion_request',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('user.id'), nullable=True),
        sa.Column('identifier', sa.String(length=120), nullable=False),
        sa.Column('reason', sa.Text(), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('fingerprint', sa.String(length=64), nullable=False),
        sa.Column('requested_at', sa.DateTime(), nullable=True),
        sa.Column('resolved_at', sa.DateTime(), nullable=True),
        sa.Column('resolved_by', sa.Integer(), sa.ForeignKey('user.id'), nullable=True),
        sa.Column('resolution_note', sa.String(length=300), nullable=True),
    )
    op.create_index('ix_data_deletion_request_user_id', 'data_deletion_request',
                    ['user_id'], unique=False)
    op.create_index('ix_data_deletion_request_requested_at', 'data_deletion_request',
                    ['requested_at'], unique=False)
    op.create_index('ix_data_deletion_request_resolved_by', 'data_deletion_request',
                    ['resolved_by'], unique=False)
    op.create_index('ix_ddr_status_requested', 'data_deletion_request',
                    ['status', 'requested_at'], unique=False)


def downgrade():
    op.drop_index('ix_ddr_status_requested', table_name='data_deletion_request')
    op.drop_index('ix_data_deletion_request_resolved_by', table_name='data_deletion_request')
    op.drop_index('ix_data_deletion_request_requested_at', table_name='data_deletion_request')
    op.drop_index('ix_data_deletion_request_user_id', table_name='data_deletion_request')
    op.drop_table('data_deletion_request')
