"""add photo_rejection table (photo-gate rejection log for admin monitoring)

Every upload the photo gate refuses (stage-1 decodability or the ONNX
garbage-vs-non-garbage classifier) is logged with a small thumbnail so
admins can eyeball false positives on /admin/photo-rejections and tune the
model. Privacy posture matches PageFeedback/ConsentRecord: the only
identifier is a salted fingerprint of (IP + user-agent); thumbnails live in
the DB (LargeBinary) because containers are ephemeral and rejected uploads
should not get a second life in object storage.

Revision ID: m1n2o3p4q5r6
Revises: l1m2n3o4p5q6
Create Date: 2026-09-29
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'm1n2o3p4q5r6'
down_revision = 'l1m2n3o4p5q6'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'photo_rejection',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('surface', sa.String(length=40), nullable=False),
        sa.Column('stage', sa.String(length=20), nullable=False),
        sa.Column('note', sa.String(length=200), nullable=False),
        sa.Column('fingerprint', sa.String(length=64), nullable=False),
        sa.Column('thumbnail', sa.LargeBinary(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
    )
    op.create_index('ix_photo_rejection_created', 'photo_rejection',
                    ['created_at'], unique=False)
    op.create_index('ix_photo_rejection_stage', 'photo_rejection',
                    ['stage', 'created_at'], unique=False)


def downgrade():
    op.drop_index('ix_photo_rejection_stage', table_name='photo_rejection')
    op.drop_index('ix_photo_rejection_created', table_name='photo_rejection')
    op.drop_table('photo_rejection')
