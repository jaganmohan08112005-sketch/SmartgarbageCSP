"""add complaint.resolution_photo (worker close-the-loop evidence)

Nullable VARCHAR(200), matching the photo columns already on Complaint and
SmartBin.after_photo. Workers must upload a live site photo when marking a
complaint resolved (same contract as the bin-clear flow), so the control
room and the transparency pages can audit cleanup claims.

Revision ID: k9l0m1n2o3p4
Revises: j7k8m9n0p1q2
Create Date: 2026-09-17
"""
from alembic import op
import sqlalchemy as sa

revision = 'k9l0m1n2o3p4'
down_revision = 'j7k8m9n0p1q2'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('complaint') as batch:
        batch.add_column(
            sa.Column('resolution_photo', sa.String(length=200), nullable=True))


def downgrade():
    with op.batch_alter_table('complaint') as batch:
        batch.drop_column('complaint', 'resolution_photo')
