"""add email_verified to user

Revision ID: a1b49b048963
Revises: e7f8a9b0c1d2
Create Date: 2026-08-25

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a1b49b048963'
down_revision = 'e7f8a9b0c1d2'
branch_labels = None
depends_on = None


def upgrade():
    # Add email_verified boolean to user table.
    # server_default='0' ensures existing rows get False without a
    # full-table UPDATE (which would be slow on large tables).
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('email_verified', sa.Boolean(), nullable=False,
                      server_default=sa.text('0'))
        )

    # After the column is live, drop the server_default so new inserts
    # use the ORM default (False) instead of the raw SQL default.
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.alter_column('email_verified', server_default=None)


def downgrade():
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.drop_column('email_verified')
