import os

# Must run before anything imports the stdlib socket/time modules: SocketIO is
# initialised with async_mode='eventlet', and the /api/notifications/stream SSE
# generator sleeps between pushes. Without monkey patching, that sleep blocks
# the whole eventlet hub and every other request hangs. Gunicorn's eventlet
# worker does this for us in production; plain `python run.py` does not.
try:
    import eventlet
    eventlet.monkey_patch()
except ImportError:
    pass

from app import create_app, socketio  # noqa: E402

# Local dev only. Run `flask db upgrade` once after cloning.
app = create_app()

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000,
                  debug=os.environ.get('FLASK_ENV') == 'development')
