"""Migration gate: every model table must be created by a revision.

Alembic owns the schema. app/__init__.py deliberately never calls
db.create_all() (it would make the next `flask db upgrade` fail with "already
exists"), and the Dockerfile runs `flask db upgrade` before gunicorn — so a
model added without a revision means the table does not exist on any migrated
database, production included.

That failure mode is invisible to the rest of the suite: the pytest fixtures
build their schema with db.create_all(), which happily creates the missing
table, so every test that touches the new feature passes while the deployed app
raises ProgrammingError on the first query. It is exactly how the entire
web-push feature shipped broken — PushSubscription, PushNotificationLog and
NotificationPreference were declared in app/models.py by commit 79a25f9 with no
revision, so /notifications/preferences returned 500, /api/push/subscribe
returned 500 and web push could never be enabled (fixed by p3q4r5s6t7u8).

Two static checks, no database and no app context needed:

  1. every table in db.metadata is named by an op.create_table() (or a core
     sa.Table()) in migrations/versions/*.py;
  2. the revision graph has exactly one head — two heads make `flask db upgrade`
     abort with "Multiple head revisions are present", which would break a
     deploy rather than a test run.
"""
import glob
import os
import re

from alembic.config import Config
from alembic.script import ScriptDirectory

import app.models  # noqa: F401  (registers every model on db.metadata)
from app import db

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VERSIONS = os.path.join(ROOT, "migrations", "versions")

# op.create_table('push_subscription', ...) / sa.Table('x', metadata, ...) —
# allow either quote style and whitespace/newlines before the name.
CREATE_TABLE_RE = re.compile(
    r"(?:op\.create_table|sa\.Table)\(\s*[\"']([A-Za-z_][A-Za-z0-9_]*)[\"']")


def _created_tables():
    """Table names any revision creates, discovered by text scan.

    A text scan (rather than running the revisions) keeps this test fast and
    side-effect free, and matches how the migrations actually write DDL: no
    revision uses raw `CREATE TABLE` SQL.
    """
    names = set()
    for path in glob.glob(os.path.join(VERSIONS, "*.py")):
        with open(path, encoding="utf-8", errors="replace") as fh:
            names.update(CREATE_TABLE_RE.findall(fh.read()))
    return names


def test_migrations_are_present():
    """Guard the guard: the scan must find the version directory."""
    assert os.path.isdir(VERSIONS)
    assert len(_created_tables()) >= 20


def test_every_model_table_is_created_by_a_migration():
    model_tables = set(db.metadata.tables)
    created = _created_tables()
    missing = sorted(model_tables - created)
    assert not missing, (
        "These model tables are never created by a revision in "
        "migrations/versions/, so they do not exist on any database built with "
        "`flask db upgrade` (production included); the pytest fixtures hide it "
        "because they use db.create_all(). Add a revision that creates: %s"
        % ", ".join(missing))


def test_migration_graph_has_a_single_head():
    cfg = Config()
    cfg.set_main_option("script_location", os.path.join(ROOT, "migrations"))
    heads = ScriptDirectory.from_config(cfg).get_heads()
    assert len(heads) == 1, (
        "The revision graph has %d heads (%s). `flask db upgrade` on a fresh "
        "database fails with 'Multiple head revisions are present'; merge them "
        "with a revision whose down_revision is a tuple of the heads."
        % (len(heads), ", ".join(heads)))
