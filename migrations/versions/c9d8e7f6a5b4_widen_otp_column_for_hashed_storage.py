"""widen otp column for hashed storage

Revision ID: c9d8e7f6a5b4
Revises: f4b16da954ad
Create Date: 2026-07-31 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c9d8e7f6a5b4'
down_revision = 'f4b16da954ad'
branch_labels = None
depends_on = None


def upgrade():
    # OTPs are now stored as a sha256 hex digest (64 chars) instead of a
    # 6-digit plaintext, so widen the column from 10 to 128 chars.
    op.alter_column('user', 'otp',
                    existing_type=sa.String(length=10),
                    type_=sa.String(length=128),
                    existing_nullable=True)


def downgrade():
    op.alter_column('user', 'otp',
                    existing_type=sa.String(length=128),
                    type_=sa.String(length=10),
                    existing_nullable=True)
