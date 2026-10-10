"""add the three web-push tables that models.py never migrated

Commit 79a25f9 ("Add web push notifications for complaint status changes")
declared PushSubscription, PushNotificationLog and NotificationPreference in
app/models.py but added no revision, so no database built the way this project
builds them ever got their tables. The schema is owned by Alembic only —
app/__init__.py deliberately never calls db.create_all(), and the Dockerfile
runs `flask db upgrade` before gunicorn — so on any migrated database:

  * GET /notifications/preferences  -> 500 (ProgrammingError: relation
    "notification_preference" does not exist), the citizen preferences page;
  * POST /api/push/subscribe        -> 500, so web push could never be enabled;
  * the admin push-health analytics -> 500.

(This was invisible to the test suite because the pytest fixtures build their
schema with db.create_all(), which does create these tables.)

Written defensively like f4b16da954ad (user.email): each table is created only
if absent, so a database that already has it — e.g. a dev box that once ran
db.create_all() — is a no-op instead of an "already exists" failure that would
abort the upgrade and leave the deploy half-migrated.

The DDL is kept identical to the models (no server_defaults, same index names,
including push_subscription's redundant ix_push_sub_user) so that a future
`flask db migrate` autogenerate stays empty.

Revision ID: p3q4r5s6t7u8
Revises: n2o3p4q5r6s7
Create Date: 2026-10-10 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'p3q4r5s6t7u8'
down_revision = 'n2o3p4q5r6s7'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing = set(inspector.get_table_names())

    # ── Per-user notification preferences (one row per user, opt-out model) ──
    if 'notification_preference' not in existing:
        op.create_table(
            'notification_preference',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('user_id', sa.Integer(), nullable=False),
            # Complaint lifecycle
            sa.Column('complaint_submitted', sa.Boolean(), nullable=False),
            sa.Column('complaint_assigned', sa.Boolean(), nullable=False),
            sa.Column('complaint_in_progress', sa.Boolean(), nullable=False),
            sa.Column('complaint_resolved', sa.Boolean(), nullable=False),
            sa.Column('complaint_escalated', sa.Boolean(), nullable=False),
            # System
            sa.Column('schedule_reminder', sa.Boolean(), nullable=False),
            sa.Column('green_points_earned', sa.Boolean(), nullable=False),
            sa.Column('weekly_summary', sa.Boolean(), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.Column('updated_at', sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(['user_id'], ['user.id'], ),
            sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_notification_preference_user_id'),
                        'notification_preference', ['user_id'], unique=True)

    # ── Browser push subscriptions (VAPID endpoints) ──
    if 'push_subscription' not in existing:
        op.create_table(
            'push_subscription',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('user_id', sa.Integer(), nullable=False),
            sa.Column('endpoint', sa.Text(), nullable=False),
            sa.Column('p256dh', sa.Text(), nullable=False),
            sa.Column('auth', sa.Text(), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.Column('last_used_at', sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(['user_id'], ['user.id'], ),
            sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_push_subscription_user_id'),
                        'push_subscription', ['user_id'], unique=False)
        op.create_index('ix_push_sub_user', 'push_subscription',
                        ['user_id'], unique=False)

    # ── Delivery log for the admin push-health view ──
    if 'push_notification_log' not in existing:
        op.create_table(
            'push_notification_log',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('user_id', sa.Integer(), nullable=False),
            sa.Column('title', sa.String(length=200), nullable=False),
            sa.Column('body', sa.Text(), nullable=False),
            sa.Column('url', sa.String(length=200), nullable=True),
            sa.Column('status', sa.String(length=20), nullable=False),
            sa.Column('error', sa.Text(), nullable=True),
            sa.Column('endpoint', sa.Text(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(['user_id'], ['user.id'], ),
            sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_push_notification_log_user_id'),
                        'push_notification_log', ['user_id'], unique=False)
        op.create_index(op.f('ix_push_notification_log_status'),
                        'push_notification_log', ['status'], unique=False)
        op.create_index(op.f('ix_push_notification_log_created_at'),
                        'push_notification_log', ['created_at'], unique=False)
        op.create_index('ix_push_log_user_created', 'push_notification_log',
                        ['user_id', 'created_at'], unique=False)
        op.create_index('ix_push_log_status_created', 'push_notification_log',
                        ['status', 'created_at'], unique=False)


def downgrade():
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing = set(inspector.get_table_names())

    if 'push_notification_log' in existing:
        for name in ('ix_push_log_status_created', 'ix_push_log_user_created',
                     'ix_push_notification_log_created_at',
                     'ix_push_notification_log_status',
                     'ix_push_notification_log_user_id'):
            op.drop_index(name, table_name='push_notification_log')
        op.drop_table('push_notification_log')

    if 'push_subscription' in existing:
        for name in ('ix_push_sub_user', 'ix_push_subscription_user_id'):
            op.drop_index(name, table_name='push_subscription')
        op.drop_table('push_subscription')

    if 'notification_preference' in existing:
        op.drop_index(op.f('ix_notification_preference_user_id'),
                      table_name='notification_preference')
        op.drop_table('notification_preference')
