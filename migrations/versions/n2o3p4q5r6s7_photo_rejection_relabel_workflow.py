"""add relabel workflow columns to photo_rejection

The admin rejection panel gains a relabel action: an admin can mark a
rejected upload as actually-waste (a false positive -> queued for the next
retraining batch), confirm the rejection, or dismiss it as noise. Also
records the classifier's non-garbage score (p_reject) so the harvest job
can flag UNCERTAIN rows near the operating threshold for review, and
batched_at so exports are idempotent.

Revision ID: n2o3p4q5r6s7
Revises: m1n2o3p4q5r6
Create Date: 2026-09-29
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'n2o3p4q5r6s7'
down_revision = 'm1n2o3p4q5r6'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('photo_rejection',
                  sa.Column('p_reject', sa.Float(), nullable=True))
    op.add_column('photo_rejection',
                  sa.Column('relabel_status', sa.String(length=20),
                            nullable=False, server_default='auto'))
    op.add_column('photo_rejection',
                  sa.Column('relabeled_by', sa.Integer(),
                            sa.ForeignKey('user.id'), nullable=True))
    op.add_column('photo_rejection',
                  sa.Column('relabeled_at', sa.DateTime(), nullable=True))
    op.add_column('photo_rejection',
                  sa.Column('batched_at', sa.DateTime(), nullable=True))
    op.create_index('ix_photo_rejection_relabel_status', 'photo_rejection',
                    ['relabel_status'], unique=False)


def downgrade():
    op.drop_index('ix_photo_rejection_relabel_status',
                  table_name='photo_rejection')
    op.drop_column('photo_rejection', 'batched_at')
    op.drop_column('photo_rejection', 'relabeled_at')
    # The FK on user.id is dropped with the column on Postgres.
    op.drop_column('photo_rejection', 'relabeled_by')
    op.drop_column('photo_rejection', 'relabel_status')
    op.drop_column('photo_rejection', 'p_reject')
