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
    # Use 'false' (not 0) so PostgreSQL BOOLEAN accepts the default.
    # batch_alter_table is required for SQLite; PostgreSQL uses regular DDL.
    default_val = sa.text('false')
    dialect = op.get_bind().dialect.name
    if dialect == 'sqlite':
        with op.batch_alter_table('user', schema=None) as batch_op:
            batch_op.add_column(
                sa.Column('email_verified', sa.Boolean(), nullable=False,
                          server_default=default_val)
            )
    else:
        op.add_column(
            'user',
            sa.Column('email_verified', sa.Boolean(), nullable=False,
                      server_default=default_val)
        )


def downgrade():
    dialect = op.get_bind().dialect.name
    if dialect == 'sqlite':
        with op.batch_alter_table('user', schema=None) as batch_op:
            batch_op.drop_column('email_verified')
    else:
        op.drop_column('user', 'email_verified')
