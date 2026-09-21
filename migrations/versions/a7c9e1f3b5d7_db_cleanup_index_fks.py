"""DB cleanup: drop duplicate survey index, index all unindexed FKs.

Supabase advisors (2026-09-21):
  - duplicate_index: survey_response carried TWO identical indexes on
    complaint_id (ix_survey_response_complaint_id and uq_survey_complaint —
    the column's unique=True constraint already creates a covering index).
    Dropping the redundant explicit index halves the write cost on that path.
  - unindexed_foreign_keys: 12 FK columns had no covering index. Postgres
    does not auto-index FK columns; unindexed FKs slow JOINs, ON DELETE
    cascades, and admin JOIN lookups as tables grow.

The index set mirrors app/models.py exactly (every column below carries
index=True in the model), so a future autogenerate has zero drift.

Idempotent: every operation checks the live catalog first, so re-running
against a database that is already in any intermediate state is a no-op.

Revision ID: a7c9e1f3b5d7
Revises: k9l0m1n2o3p4
Create Date: 2026-09-21
"""
from alembic import op

revision = 'a7c9e1f3b5d7'
down_revision = 'k9l0m1n2o3p4'
branch_labels = None
depends_on = None

# (table, column) pairs matching the 12 unindexed FKs from the Supabase
# performance advisor. Index names follow SQLAlchemy's ix_<table>_<column>
# convention so the model's index=True and the database stay in lockstep.
_FK_INDEXES = [
    ('audit_log', 'user_id'),
    ('complaint', 'assigned_worker_id'),
    ('firmware_release', 'uploaded_by'),
    ('incident_log', 'bin_id'),
    ('maintenance_work_order', 'bin_id'),
    ('maintenance_work_order', 'completed_by'),
    ('maintenance_work_order', 'created_by'),
    ('offline_delivery', 'complaint_id'),
    ('offline_delivery', 'illegal_report_id'),
    ('offline_delivery', 'user_id'),
    ('offload_log', 'worker_id'),
    ('payt_invoice', 'user_id'),
]

# Duplicate of the uq_survey_complaint unique index on the same column.
_SURVEY_DUP_INDEX = 'ix_survey_response_complaint_id'


def _existing_indexes(table):
    bind = op.get_bind()
    from sqlalchemy import inspect
    return {ix['name'] for ix in inspect(bind).get_indexes(table)}


def upgrade():
    # 1. Drop the redundant survey index (uq_survey_complaint still covers it).
    if _SURVEY_DUP_INDEX in _existing_indexes('survey_response'):
        op.drop_index(_SURVEY_DUP_INDEX, table_name='survey_response')

    # 2. Add the 12 missing FK indexes (skip any that already exist).
    for table, column in _FK_INDEXES:
        name = f'ix_{table}_{column}'
        if name not in _existing_indexes(table):
            op.create_index(name, table, [column])


def downgrade():
    for table, column in _FK_INDEXES:
        name = f'ix_{table}_{column}'
        if name in _existing_indexes(table):
            op.drop_index(name, table_name=table)

    if _SURVEY_DUP_INDEX not in _existing_indexes('survey_response'):
        op.create_index(_SURVEY_DUP_INDEX, 'survey_response', ['complaint_id'])
