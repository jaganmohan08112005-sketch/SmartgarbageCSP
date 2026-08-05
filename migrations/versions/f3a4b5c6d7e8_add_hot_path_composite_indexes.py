"""add hot-path composite indexes

Revision ID: f3a4b5c6d7e8
Revises: f2a3b4c5d6e7
Create Date: 2026-08-02

Quick-win performance indexes flagged by the production review:

- ix_notification_user_read_created on notification(user_id, read, created_at):
  the citizen dashboard loads a user's notifications filtered by read-state and
  sorted by recency, and the PAYT dunning dedupe looks up (user_id, link) —
  both scanned the table before.

- ix_waste_declaration_ward_timestamp on waste_declaration(ward, timestamp):
  ward-scoped transparency views and the trend/segregation analytics GROUP BY
  month across a ward's rows — a full-table scan before.

batch_alter_table keeps SQLite and Postgres on the same DDL path.
"""
from alembic import op
import sqlalchemy as sa

revision = 'f3a4b5c6d7e8'
down_revision = 'f2a3b4c5d6e7'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('notification') as batch_op:
        batch_op.create_index('ix_notification_user_read_created',
                              ['user_id', 'read', 'created_at'])
    with op.batch_alter_table('waste_declaration') as batch_op:
        batch_op.create_index('ix_waste_declaration_ward_timestamp',
                              ['ward', 'timestamp'])


def downgrade():
    with op.batch_alter_table('waste_declaration') as batch_op:
        batch_op.drop_index('ix_waste_declaration_ward_timestamp')
    with op.batch_alter_table('notification') as batch_op:
        batch_op.drop_index('ix_notification_user_read_created')
