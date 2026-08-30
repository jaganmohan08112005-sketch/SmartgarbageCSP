"""Preview server using the actual Flask app with Supabase PostgreSQL.

Requires DATABASE_URL environment variable pointing to Supabase PostgreSQL.
Example: DATABASE_URL=postgresql://user:pass@host:5432/dbname?sslmode=require
"""
import os

# Require DATABASE_URL — no SQLite fallback
if 'DATABASE_URL' not in os.environ:
    raise RuntimeError(
        "DATABASE_URL must be set to a Supabase PostgreSQL connection string.\n"
        "Example: export DATABASE_URL='postgresql://user:pass@host:5432/dbname?sslmode=require'"
    )

from app import create_app
app = create_app()

if __name__ == '__main__':
    print("Preview server running on http://127.0.0.1:5000")
    print(f"Database: {os.environ['DATABASE_URL'].split('@')[-1] if '@' in os.environ['DATABASE_URL'] else 'configured'}")
    app.run(host='127.0.0.1', port=5000, debug=False)
