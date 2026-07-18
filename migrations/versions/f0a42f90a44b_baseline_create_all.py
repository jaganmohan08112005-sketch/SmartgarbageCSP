"""baseline_create_all

Revision ID: f0a42f90a44b
Revises: 
Create Date: 2026-07-18 17:45:59.492153

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f0a42f90a44b'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    from app import db
    db.metadata.create_all(bind=op.get_bind())


def downgrade():
    from app import db
    db.metadata.drop_all(bind=op.get_bind())

