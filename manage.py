from app import create_app, db
from flask_migrate import cli as migrate_cli

app = create_app()
app.cli.add_command(migrate_cli, "db")

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
