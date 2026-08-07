"""add anonymized consent record (GDPR/DPDP consent evidence)

Revision ID: e7f8a9b0c1d2
Revises: c1d2e3f4a5b6
Create Date: 2026-08-07
"""
from alembic import op
import sqlalchemy as sa

revision = 'e7f8a9b0c1d2'
down_revision = 'c1d2e3f4a5b6'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'consent_record',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('choice', sa.String(length=10), nullable=False),
        sa.Column('version', sa.String(length=20), nullable=False),
        sa.Column('source', sa.String(length=200), nullable=True),
        sa.Column('fingerprint', sa.String(length=64), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
    )
    op.create_index('ix_consent_choice_created', 'consent_record',
                    ['choice', 'created_at'])
    op.create_index('ix_consent_record_created_at', 'consent_record',
                    ['created_at'])


def downgrade():
    op.drop_index('ix_consent_record_created_at', table_name='consent_record')
    op.drop_index('ix_consent_choice_created', table_name='consent_record')
    op.drop_table('consent_record')
