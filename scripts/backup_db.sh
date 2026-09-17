#!/usr/bin/env bash
# pg_dump backup for the SmartGarbage Supabase database.
#
# Usage:
#   DATABASE_URL="postgresql://...supabase.co:5432/postgres" ./scripts/backup_db.sh
#   DATABASE_URL="postgresql://..." ./scripts/backup_db.sh /path/to/backups
#
# What it does:
#   1. pg_dump -Fc (custom format, compressed) the public schema
#   2. Keep the last N=14 dumps (2 weeks of daily), delete older
#   3. Print a one-line summary
#
# Supabase notes:
#   - Use the *session pooler* URI (ipv6-safe, works from home networks):
#     Supabase Dashboard → Connect → Session pooler, port 5432.
#   - The direct db.<ref>.supabase.co:5432 host fails on IPv4-only networks.
#   - -Fc gives a single restore-able archive: see docs/BACKUP_RESTORE.md.

set -euo pipefail

: "${DATABASE_URL:?Set DATABASE_URL to the Supabase session-pooler URI (postgresql://postgres.<ref>:<pw>@aws-0-<region>.pooler.supabase.com:5432/postgres)}"
BACKUP_DIR="${1:-backups}"
KEEP="${KEEP:-14}"

mkdir -p "$BACKUP_DIR"
STAMP="$(date +%Y%m%d_%H%M%S)"
OUT="$BACKUP_DIR/smartgarbage_${STAMP}.dump"

echo "Dumping to $OUT ..."
pg_dump "$DATABASE_URL" \
  --format=custom \
  --no-owner \
  --no-privileges \
  --exclude-schema='extensions' \
  --exclude-schema='auth' \
  --exclude-schema='storage' \
  --exclude-schema='pgsodium*' \
  --exclude-schema='vault' \
  --file="$OUT"

SIZE=$(du -h "$OUT" | cut -f1)
COUNT=$(pg_restore --list "$OUT" 2>/dev/null | grep -c "TABLE DATA" || echo "?")
echo "OK: $OUT ($SIZE, $COUNT tables)"

# Retention: keep the newest $KEEP dumps.
ls -1t "$BACKUP_DIR"/smartgarbage_*.dump 2>/dev/null | tail -n +"$((KEEP + 1))" | while read -r old; do
  rm -f "$old"
  echo "Pruned old backup: $old"
done
