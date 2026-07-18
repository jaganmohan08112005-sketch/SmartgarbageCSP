import os
from app import create_app

# Local dev only. Run `flask db upgrade` once after cloning.
app = create_app()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=os.environ.get('FLASK_ENV') == 'development')