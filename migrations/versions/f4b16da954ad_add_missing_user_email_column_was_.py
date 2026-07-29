"""add missing user.email column (was declared in models.py but never migrated)

Revision ID: f4b16da954ad
Revises: e11a6badfb75
Create Date: 2026-07-29 04:28:39.249420

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f4b16da954ad'
down_revision = 'e11a6badfb75'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [col['name'] for col in inspector.get_columns('user')]
    if 'email' not in columns:
        op.add_column('user', sa.Column('email', sa.String(length=120), nullable=True))
        op.create_index(op.f('ix_user_email'), 'user', ['email'], unique=False)


def downgrade():
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [col['name'] for col in inspector.get_columns('user')]
    if 'email' in columns:
        op.drop_index(op.f('ix_user_email'), table_name='user')
        op.drop_column('user', 'email')
