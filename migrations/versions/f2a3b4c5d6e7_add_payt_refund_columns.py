"""add payt refund columns

Revision ID: f2a3b4c5d6e7
Revises: e1f2a3b4c5d6
Create Date: 2026-08-02

Admin waive/refund of PAYT invoices: refund_id (Razorpay refund id) is the
idempotency guard for the Refunds API, refunded_at records when the money
moved, refund_reason records the admin's justification. All strictly
informational — invoice.status remains the source of truth (Refunded once
Razorpay accepts the refund; Waived when the debt is forgiven without money
moving).
"""
from alembic import op
import sqlalchemy as sa

revision = 'f2a3b4c5d6e7'
down_revision = 'e1f2a3b4c5d6'
branch_labels = None
depends_on = None


def upgrade():
    # batch_alter_table keeps SQLite (ALTER TABLE ADD COLUMN is limited) and
    # Postgres on the same path.
    with op.batch_alter_table('payt_invoice') as batch_op:
        batch_op.add_column(sa.Column('refund_id', sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column('refunded_at', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('refund_reason', sa.String(length=200), nullable=True))
        batch_op.create_index('ix_payt_invoice_refund_id', ['refund_id'])


def downgrade():
    with op.batch_alter_table('payt_invoice') as batch_op:
        batch_op.drop_index('ix_payt_invoice_refund_id')
        batch_op.drop_column('refund_reason')
        batch_op.drop_column('refunded_at')
        batch_op.drop_column('refund_id')
