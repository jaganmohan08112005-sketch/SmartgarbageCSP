# Backup & Restore — Supabase Postgres

## Backing up

Use the bundled script (custom-format dump, 14-dump retention):

```bash
# Get the URI from Supabase Dashboard → Connect → Session pooler (port 5432).
# IPv4-only home networks cannot reach db.<ref>.supabase.co directly — the
# pooler host works everywhere.
export DATABASE_URL="postgresql://postgres.<ref>:<password>@aws-0-<region>.pooler.supabase.com:5432/postgres"
./scripts/backup_db.sh            # writes to ./backups/
./scripts/backup_db.sh /mnt/e     # or any target folder
```

Requirements: `pg_dump`/`pg_restore` version ≥ the server's (17.x). On
Windows use the Git Bash shell so `date`/`du`/`ls` behave.

Supabase free tier also keeps its own daily automatic backups for a short
window, but the only backup you control is one you downloaded yourself.

## Restoring (documented procedure)

### 1. Restore into a fresh/empty database (disaster recovery)

```bash
# Option A — same project, schema was lost (drop_all-style recovery):
psql "$DATABASE_URL" -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"
pg_restore --clean --if-exists --no-owner --no-privileges \
  -d "$DATABASE_URL" backups/smartgarbage_<stamp>.dump

# Option B — brand-new Supabase project:
#   1. Create the project; copy its session-pooler URI into NEW_DATABASE_URL
#   2. Restore:
pg_restore --no-owner --no-privileges \
  -d "$NEW_DATABASE_URL" backups/smartgarbage_<stamp>.dump
#   3. Point Render's DATABASE_URL at the new project and redeploy.
```

### 2. Restore a single table (surgical fix)

```bash
# List the tables inside the archive:
pg_restore --list backups/smartgarbage_<stamp>.dump | grep TABLE

# Restore just one, data included:
pg_restore --clean --if-exists --no-owner -d "$DATABASE_URL" \
  -t '"user"' backups/smartgarbage_<stamp>.dump      # note: "user" is quoted (reserved word)
pg_restore --clean --if-exists --no-owner -d "$DATABASE_URL" \
  -t complaint -t complaint_status_log backups/smartgarbage_<stamp>.dump
```

### 3. After any restore — verify before serving traffic

```bash
# The app's own health endpoint runs SELECT 1; deeper checks:
psql "$DATABASE_URL" -c 'SELECT count(*) FROM "user";'
psql "$DATABASE_URL" -c "SELECT alembic_version FROM alembic_version;"
curl -s https://smartgarbage.onrender.com/health
```

If `alembic_version` disagrees with the code's migration head, run
`flask db upgrade` (the Dockerfile does this automatically on deploy).

### 4. What is intentionally NOT in the dumps

`auth`, `storage`, `vault`, `extensions` schemas are excluded — they hold
Supabase platform state (auth users if you use Supabase Auth, storage
buckets), which the app does not read. Uploaded complaint photos live in
Supabase Storage (bucket `smartgarbage-uploads`); back that up separately
with `supabase storage` CLI sync if photo history matters to you.
