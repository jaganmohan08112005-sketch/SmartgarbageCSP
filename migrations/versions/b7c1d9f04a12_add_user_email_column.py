"""add user email column

Revision ID: b7c1d9f04a12
Revises: e11a6badfb75
Create Date: 2026-07-25 02:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b7c1d9f04a12'
down_revision = 'e11a6badfb75'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.add_column(sa.Column('email', sa.String(length=120), nullable=True))
        batch_op.create_index(batch_op.f('ix_user_email'), ['email'], unique=False)


def downgrade():
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_user_email'))
        batch_op.drop_column('email')
