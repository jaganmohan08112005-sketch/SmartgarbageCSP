"""Add indexes to hot query columns

Revision ID: a1b2c3d4e5f
Revises: 6cdf00e23730
Create Date: 2026-07-19 00:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a1b2c3d4e5f'
down_revision = '6cdf00e23730'
branch_labels = None
depends_on = None


def upgrade():
    # Speed up the most frequent WHERE/filter columns:
    #   complaint.ward, complaint.created_at, complaint.user_id
    #   smart_bin.ward, smart_bin.last_updated
    #   audit_log.timestamp
    #   waste_declaration.user_id
    #   illegal_dump_report.ward, illegal_dump_report.timestamp
    op.create_index('ix_complaint_ward', 'complaint', ['ward'])
    op.create_index('ix_complaint_created_at', 'complaint', ['created_at'])
    op.create_index('ix_complaint_user_id', 'complaint', ['user_id'])
    op.create_index('ix_smart_bin_ward', 'smart_bin', ['ward'])
    op.create_index('ix_smart_bin_last_updated', 'smart_bin', ['last_updated'])
    op.create_index('ix_audit_log_timestamp', 'audit_log', ['timestamp'])
    op.create_index('ix_waste_declaration_user_id', 'waste_declaration', ['user_id'])
    op.create_index('ix_illegal_dump_report_ward', 'illegal_dump_report', ['ward'])
    op.create_index('ix_illegal_dump_report_timestamp', 'illegal_dump_report', ['timestamp'])


def downgrade():
    op.drop_index('ix_illegal_dump_report_timestamp', table_name='illegal_dump_report')
    op.drop_index('ix_illegal_dump_report_ward', table_name='illegal_dump_report')
    op.drop_index('ix_waste_declaration_user_id', table_name='waste_declaration')
    op.drop_index('ix_audit_log_timestamp', table_name='audit_log')
    op.drop_index('ix_smart_bin_last_updated', table_name='smart_bin')
    op.drop_index('ix_smart_bin_ward', table_name='smart_bin')
    op.drop_index('ix_complaint_user_id', table_name='complaint')
    op.drop_index('ix_complaint_created_at', table_name='complaint')
    op.drop_index('ix_complaint_ward', table_name='complaint')
