"""add v3 architectural improvements (complaint lifecycle, billing integrity, indexes, ETA throttle)

Revision ID: 20260803120000
Revises: 20260803104714
Create Date: 2026-08-03 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '20260803120000'
down_revision = '20260803104714'
branch_labels = None
depends_on = None


def upgrade():
    # ── User: household size for waste-declaration plausibility ──
    op.add_column('user', sa.Column('household_size', sa.Integer(), nullable=False, server_default='1'))

    # ── Complaint: lifecycle state machine + SLA + escalation ──
    op.add_column('complaint', sa.Column('bin_id', sa.Integer(), nullable=True))
    op.add_column('complaint', sa.Column('assigned_worker_id', sa.Integer(), nullable=True))
    op.add_column('complaint', sa.Column('sla_deadline', sa.DateTime(), nullable=True))
    op.add_column('complaint', sa.Column('escalated', sa.Boolean(), nullable=False, server_default='0'))
    op.add_column('complaint', sa.Column('resolved_at', sa.DateTime(), nullable=True))
    op.add_column('complaint', sa.Column('closed_at', sa.DateTime(), nullable=True))
    # SQLite cannot ALTER constraints directly — batch mode recreates the table
    # (copy-and-move); on Postgres the same ops run natively. Without batch,
    # a fresh full upgrade to this revision fails on SQLite.
    with op.batch_alter_table('complaint') as batch_op:
        batch_op.create_foreign_key('fk_complaint_bin_id', 'smart_bin', ['bin_id'], ['id'])
        batch_op.create_foreign_key('fk_complaint_assigned_worker', 'worker_profile', ['assigned_worker_id'], ['id'])
        batch_op.create_index('ix_complaint_bin_id', ['bin_id'])
        batch_op.create_index('ix_complaint_status_created', ['status', 'created_at'])

    # ── SmartBin: ETA recompute throttle column + dispatch index ──
    op.add_column('smart_bin', sa.Column('last_eta_computed_at', sa.DateTime(), nullable=True))
    op.create_index('ix_smart_bin_eta_level', 'smart_bin', ['overflow_eta_hours', 'level'])

    # ── AuditLog: webhook dedupe index ──
    op.create_index('ix_audit_action_target', 'audit_log', ['action', 'target'])

    # ── WasteDeclaration: plausibility flag ──
    op.add_column('waste_declaration', sa.Column('flagged_outlier', sa.Boolean(), nullable=False, server_default='0'))

    # ── PAYTInvoice: billing integrity (verified weights) ──
    op.add_column('payt_invoice', sa.Column('billing_status', sa.String(20), nullable=False, server_default='Self-Reported'))
    op.add_column('payt_invoice', sa.Column('verified_weight_kg', sa.Float(), nullable=True))
    op.add_column('payt_invoice', sa.Column('discrepancy_pct', sa.Float(), nullable=True))


def downgrade():
    op.drop_column('payt_invoice', 'discrepancy_pct')
    op.drop_column('payt_invoice', 'verified_weight_kg')
    op.drop_column('payt_invoice', 'billing_status')
    op.drop_column('waste_declaration', 'flagged_outlier')
    op.drop_index('ix_audit_action_target', table_name='audit_log')
    op.drop_index('ix_smart_bin_eta_level', table_name='smart_bin')
    op.drop_column('smart_bin', 'last_eta_computed_at')
    op.drop_index('ix_complaint_status_created', table_name='complaint')
    op.drop_index('ix_complaint_bin_id', table_name='complaint')
    with op.batch_alter_table('complaint') as batch_op:
        batch_op.drop_constraint('fk_complaint_assigned_worker', type_='foreignkey')
        batch_op.drop_constraint('fk_complaint_bin_id', type_='foreignkey')
    op.drop_column('complaint', 'closed_at')
    op.drop_column('complaint', 'resolved_at')
    op.drop_column('complaint', 'escalated')
    op.drop_column('complaint', 'sla_deadline')
    op.drop_column('complaint', 'assigned_worker_id')
    op.drop_column('complaint', 'bin_id')
    op.drop_column('user', 'household_size')