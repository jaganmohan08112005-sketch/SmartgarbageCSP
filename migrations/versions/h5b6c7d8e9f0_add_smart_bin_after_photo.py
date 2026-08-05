"""add smart_bin.after_photo for close-the-loop worker accountability

Revision ID: h5b6c7d8e9f0
Revises: g4a5b6c7d8e9
Create Date: 2026-08-03

Close-the-loop validation: a bin may only be cleared after the worker uploads
a real-time geotagged After-photo. This column keeps the evidence path on the
bin record so every clearance is auditable (photo path + worker GPS verified
server-side before the clear is accepted). batch DDL keeps SQLite and Postgres
on the same path.
"""
from alembic import op
import sqlalchemy as sa

revision = 'h5b6c7d8e9f0'
down_revision = 'g4a5b6c7d8e9'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('smart_bin') as batch_op:
        batch_op.add_column(sa.Column('after_photo', sa.String(length=200), nullable=True))


def downgrade():
    with op.batch_alter_table('smart_bin') as batch_op:
        batch_op.drop_column('after_photo')
