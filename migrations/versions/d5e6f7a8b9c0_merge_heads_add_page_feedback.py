"""merge heads + add page_feedback table

Two parallel branches (device auth 66d344fab3f9 and email_verified
a1b49b048963) left alembic with two heads, so `flask db upgrade` would be
ambiguous. This revision merges them (down_revision is a tuple, same pattern
as c3d4e5f6a7b8) AND creates the page_feedback table backing the GOV.UK-style
"Is this page useful?" widget, restoring a single linear chain.

Revision ID: d5e6f7a8b9c0
Revises: 66d344fab3f9, a1b49b048963
Create Date: 2026-09-05
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd5e6f7a8b9c0'
down_revision = ('66d344fab3f9', 'a1b49b048963')
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'page_feedback',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('page', sa.String(length=200), nullable=False),
        sa.Column('useful', sa.Boolean(), nullable=False),
        sa.Column('comment', sa.Text(), nullable=True),
        sa.Column('fingerprint', sa.String(length=64), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
    )
    op.create_index('ix_page_feedback_page', 'page_feedback', ['page'], unique=False)
    op.create_index('ix_page_feedback_page_created', 'page_feedback', ['page', 'created_at'], unique=False)
    op.create_index('ix_page_feedback_created_at', 'page_feedback', ['created_at'], unique=False)


def downgrade():
    op.drop_index('ix_page_feedback_created_at', table_name='page_feedback')
    op.drop_index('ix_page_feedback_page_created', table_name='page_feedback')
    op.drop_index('ix_page_feedback_page', table_name='page_feedback')
    op.drop_table('page_feedback')