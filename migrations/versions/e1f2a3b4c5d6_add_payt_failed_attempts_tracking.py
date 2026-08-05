"""add payt failed-attempt tracking

Revision ID: e1f2a3b4c5d6
Revises: c3d4e5f6a7b8
Create Date: 2026-08-02 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e1f2a3b4c5d6'
down_revision = 'c3d4e5f6a7b8'
branch_labels = None
depends_on = None


def upgrade():
    # Razorpay payment.failed webhooks bump a per-invoice failed-attempt
    # counter and record when/why the last attempt failed. Status stays
    # capture-driven — these columns are informational only (retry UX + audit).
    # batch_alter_table emits ADD COLUMN on Postgres and a table-rebuild on
    # SQLite, so `flask db upgrade` works on both backends.
    with op.batch_alter_table('payt_invoice') as batch:
        batch.add_column(sa.Column('failed_attempts', sa.Integer(),
                                   nullable=False, server_default='0'))
        batch.add_column(sa.Column('last_failed_at', sa.DateTime(), nullable=True))
        batch.add_column(sa.Column('last_failed_reason', sa.String(length=200),
                                   nullable=True))


def downgrade():
    with op.batch_alter_table('payt_invoice') as batch:
        batch.drop_column('last_failed_reason')
        batch.drop_column('last_failed_at')
        batch.drop_column('failed_attempts')
