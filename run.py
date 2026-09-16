import os
from app import create_app, socketio

# Local dev only. Run `flask db upgrade` once after cloning.
# Preview servers SHOULD set PORT to avoid clashing with other instances.
app = create_app()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    socketio.run(app, host='0.0.0.0', port=port,
                  debug=os.environ.get('FLASK_ENV') == 'development')