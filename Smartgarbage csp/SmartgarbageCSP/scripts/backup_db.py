#!/usr/bin/env python3
"""Automated daily backup script for SmartGarbage SQLite database.

Intended to run via `python scripts/backup_db.py` or a cron/systemd timer.
Backups are compressed and timestamped; the latest N backups are kept, older ones
are pruned automatically.
"""

import os, gzip, shutil
from datetime import datetime, timezone
from pathlib import Path

# Resolve database path from Flask app settings or fallback
DB_PATH = os.getenv("SQLITE_PATH", "garbage.db")
BACKUP_DIR = Path(os.getenv("BACKUP_DIR", "backups"))

# Keep last N backups
MAX_BACKUPS = int(os.getenv("MAX_BACKUPS", 7))

def run_backup():
    if not os.path.exists(DB_PATH):
        print(f"Database not found at {DB_PATH}")
        return False
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
    gz_name = f"garbage_{ts}.db.gz"
    gz_path = BACKUP_DIR / gz_name
    # Copy + compress (atomic so we don't corrupt backup on failure)
    tmp = BACKUP_DIR / f".tmp_{gz_name}"
    with open(DB_PATH, 'rb') as f_in:
        with gzip.open(tmp, 'wb') as f_out:
            shutil.copyfileobj(f_in, f_out)
    tmp.rename(gz_path)
    print(f"Backup created: {gz_path}")

    # Prune old backups (keep newest MAX_BACKUPS)
    backups = sorted(BACKUP_DIR.glob("garbage_*.db.gz"), key=os.path.getmtime, reverse=True)
    for old in backups[MAX_BACKUPS:]:
        old.unlink()
        print(f"Pruned old backup: {old}")
    return True

if __name__ == "__main__":
    run_backup()