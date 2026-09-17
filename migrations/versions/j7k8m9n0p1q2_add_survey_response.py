"""add survey_response table (post-resolution satisfaction survey)

Creates the table backing the 5-star "Rate this resolution" survey on the
public /track/<token> page. One row per resolved complaint (unique
complaint_id), with a salted-fingerprint identifier matching the existing
PageFeedback/ConsentRecord privacy posture. Denormalizes `ward` so the
admin summary can roll satisfaction up per ward without a join.

Revision ID: j7k8m9n0p1q2
Revises: d5e6f7a8b9c0
Create Date: 2026-09-17
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'j7k8m9n0p1q2'
down_revision = 'd5e6f7a8b9c0'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'survey_response',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('complaint_id', sa.Integer(),
                  sa.ForeignKey('complaint.id'), nullable=False),
        sa.Column('rating', sa.Integer(), nullable=False),
        sa.Column('ward', sa.String(length=100), nullable=True),
        sa.Column('fingerprint', sa.String(length=64), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.UniqueConstraint('complaint_id', name='uq_survey_complaint'),
    )
    op.create_index('ix_survey_response_complaint_id', 'survey_response',
                    ['complaint_id'], unique=True)
    op.create_index('ix_survey_response_ward', 'survey_response',
                    ['ward'], unique=False)
    op.create_index('ix_survey_response_created_at', 'survey_response',
                    ['created_at'], unique=False)
    op.create_index('ix_survey_ward_created', 'survey_response',
                    ['ward', 'created_at'], unique=False)
    op.create_index('ix_survey_rating_created', 'survey_response',
                    ['rating', 'created_at'], unique=False)


def downgrade():
    op.drop_index('ix_survey_rating_created', table_name='survey_response')
    op.drop_index('ix_survey_ward_created', table_name='survey_response')
    op.drop_index('ix_survey_response_created_at', table_name='survey_response')
    op.drop_index('ix_survey_response_ward', table_name='survey_response')
    op.drop_index('ix_survey_response_complaint_id', table_name='survey_response')
    op.drop_table('survey_response')
