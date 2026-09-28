"""enforce unique user.phone and user.email

Registration uniqueness for mobile number and email was enforced only in
application code (SELECT-then-INSERT in ``register()``), which is a
time-of-check/time-of-use race: two concurrent registrations carrying the
same phone or email could both pass the SELECT and both INSERT, permanently
creating duplicate accounts with no cleanup path. ``username`` was the only
column with a DB-level guard.

This migration closes the race at the database level:

1. Normalise existing emails to lower case (the registration path always
   lower-cases before comparing, so mixed-case legacy rows could otherwise
   dodge the unique index and never match the app's lookups).
2. De-duplicate pre-existing rows. Duplicates are NOT deleted — the account
   and all of its history (complaints, PAYT invoices, audit entries) are
   retained. The *later* duplicate simply has its phone/email cleared, which
   is exactly the state an account has before those fields were collected.
   The earliest row (lowest id) keeps the value.
3. Add unique indexes on both columns. Postgres treats NULLs as distinct
   under a unique index, so accounts legitimately without a phone or an
   email (phone-OTP registrations, informal waste-pickers) are unaffected
   and may still coexist.

Revision ID: l1m2n3o4p5q6
Revises: a8d0e2f4c6b8
Create Date: 2026-09-26
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'l1m2n3o4p5q6'
down_revision = 'a8d0e2f4c6b8'
branch_labels = None
depends_on = None


def upgrade():
    # 1. Normalise legacy mixed-case emails to the canonical lower-case form.
    op.execute(
        "UPDATE \"user\" SET email = lower(email) "
        "WHERE email IS NOT NULL AND email <> lower(email)"
    )

    # 2. De-duplicate phones: keep the earliest account's value, clear the
    #    rest (history is preserved, only the identifier is released).
    op.execute(
        """
        UPDATE "user" u
           SET phone = NULL
         FROM (
               SELECT id,
                      row_number() OVER (PARTITION BY phone ORDER BY id) AS rn
                 FROM "user"
                WHERE phone IS NOT NULL
              ) d
        WHERE u.id = d.id
          AND d.rn > 1
        """
    )

    # 3. Same for emails (already lower-cased in step 1).
    op.execute(
        """
        UPDATE "user" u
           SET email = NULL
         FROM (
               SELECT id,
                      row_number() OVER (PARTITION BY email ORDER BY id) AS rn
                 FROM "user"
                WHERE email IS NOT NULL
              ) d
        WHERE u.id = d.id
          AND d.rn > 1
        """
    )

    # 4. Enforce uniqueness at the database level. NULLs remain distinct, so
    #    accounts without a phone/email (phone-OTP, waste-pickers) still work.
    op.create_index('uq_user_phone', 'user', ['phone'], unique=True)
    # The unique index below fully covers the plain ix_user_email index added
    # by f4b16da954ad; drop the redundant one so email lookups only pay for
    # a single index. IF EXISTS keeps this idempotent on databases that never
    # received the old index.
    op.execute("DROP INDEX IF EXISTS ix_user_email")
    op.create_index('uq_user_email', 'user', ['email'], unique=True)


def downgrade():
    op.drop_index('uq_user_email', table_name='user')
    op.create_index('ix_user_email', 'user', ['email'], unique=False)
    op.drop_index('uq_user_phone', table_name='user')
