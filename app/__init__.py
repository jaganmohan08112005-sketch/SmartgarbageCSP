import os
import logging
from flask import Flask, render_template, session, redirect, url_for, current_app, request
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_migrate import Migrate
from flask_socketio import SocketIO

db = SQLAlchemy()
migrate = Migrate()
csrf = CSRFProtect()
limiter = Limiter(key_func=get_remote_address, storage_uri="memory://")

# Live updates: socketio drives real-time bin/fleet pushes to the admin
# control room. async_mode is chosen at init time in create_app() so it
# can fall back gracefully when eventlet/gevent are unavailable locally.
socketio = SocketIO()


def create_app():
    app = Flask(__name__)

    # ── Sentry error tracking (if DSN present) ──
    import os
    sentry_dsn = os.getenv('SENTRY_DSN')
    if sentry_dsn:
        try:
            import sentry_sdk
            from sentry_sdk.integrations.flask import FlaskIntegration
            sentry_sdk.init(
                dsn=sentry_dsn,
                integrations=[FlaskIntegration()],
                auto_setup=False,   # we let Flask register manually
            )
        except ImportError:
            # Sentry is optional — don't crash the app if the package is absent.
            app.logger.warning("SENTRY_DSN set but sentry_sdk not installed; skipping init.")

# (File ends at line 125)

    # Security Configuration
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-fallback-key-change-in-production')
    app.config['SESSION_COOKIE_SECURE'] = os.environ.get('RENDER') is not None
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
    app.config['PERMANENT_SESSION_LIFETIME'] = 3600  # 1 hour session timeout
    app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16 MB

    # Shared secret for authenticating IoT telemetry POSTs from ESP32/Arduino
    # devices. When set (production), /api/bin-telemetry requires a valid
    # HMAC-SHA256 signature in the X-Signature header. A dev fallback keeps
    # local simulators/seed working without a secret configured.
    app.config['IOT_TELEMETRY_SECRET'] = os.environ.get('IOT_TELEMETRY_SECRET')

    # Database Configuration
    # On Render's FREE tier there is NO persistent disk, so SQLite would
    # reset on every restart. Instead we use Render's free PostgreSQL
    # instance (auto-injected as DATABASE_URL) — it survives restarts.
    # When DATABASE_URL is absent (local dev), fall back to local SQLite.
    db_url = os.environ.get('DATABASE_URL')
    if db_url:
        # Render appends sslmode=require sometimes; ensure it's present for PG
        if '?' not in db_url:
            db_url = db_url + '?sslmode=require'
        app.config['SQLALCHEMY_DATABASE_URI'] = db_url.replace('postgres://', 'postgresql://')
        app.config['UPLOAD_FOLDER'] = os.path.join('/tmp', 'uploads')
    elif os.environ.get('RENDER') and os.path.isdir('/data'):
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:////data/garbage.db'
        app.config['UPLOAD_FOLDER'] = '/data/uploads'
    else:
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///garbage.db'
        app.config['UPLOAD_FOLDER'] = os.path.join(app.root_path, 'static', 'uploads')

    # Ensure the upload directory exists
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

    # Initialize extensions
    db.init_app(app)
    migrate.init_app(app, db)
    csrf.init_app(app)
    limiter.init_app(app)

    # WebSockets for live IoT/fleet updates. Prefer eventlet (needed for the
    # async Gunicorn worker in production); fall back to threading for plain
    # `flask run` local dev where eventlet isn't installed.
    try:
        socketio.init_app(app, async_mode='eventlet', cors_allowed_origins="*")
    except Exception:
        socketio.init_app(app, cors_allowed_origins="*")
    # Quiet the SQLAlchemy 1.x LegacyAPIWarning emitted by the app-wide
    # use of `Model.query.get()` (deprecated in 2.0). Tracked separately
    # from a real migration to Session.get().
    import warnings
    from sqlalchemy.exc import LegacyAPIWarning
    warnings.filterwarnings("ignore", category=LegacyAPIWarning)

    # Security headers via after_request (Talisman handles HSTS/secure cookie;
    # CSP scoped to the CDNs actually used so Leaflet maps keep working)
    @app.after_request
    def set_security_headers(resp):
        resp.headers['X-Frame-Options'] = 'SAMEORIGIN'
        resp.headers['X-Content-Type-Options'] = 'nosniff'
        resp.headers['Content-Security-Policy'] = (
            "default-src 'self'; "
            "img-src 'self' data: https:; "
            "script-src 'self' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com https://unpkg.com; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://cdnjs.cloudflare.com; "
            "font-src 'self' https://fonts.gstatic.com https://cdnjs.cloudflare.com; "
            "connect-src 'self' https://*.tile.openstreetmap.org https://api.open-meteo.com"
        )
        return resp

    # Structured logging
    if not app.debug and not app.testing:
        logging.basicConfig(level=logging.INFO,
                                 format='%(asctime)s [%(levelname)s] %(name)s: %(message)s')

    # CORS for the IoT telemetry endpoint only.
    # ESP32/NodeMCU sensors POST cross-origin (from the device's own network /
    # cellular gateway) to the Render server, so the ingest route must return
    # permissive CORS headers + answer OPTIONS preflight. We scope it to just
    # /api/bin-telemetry so the authenticated admin/citizen APIs stay locked
    # to same-origin. (Avoids pulling in flask-cors for the whole app.)
    IOT_TELEMETRY_PATH = '/api/bin-telemetry'

    @app.after_request
    def add_iot_cors(resp):
        if request.path == IOT_TELEMETRY_PATH:
            resp.headers['Access-Control-Allow-Origin'] = '*'
            resp.headers['Access-Control-Allow-Methods'] = 'POST, OPTIONS'
            resp.headers['Access-Control-Allow-Headers'] = 'Content-Type'
        return resp

    @app.route(IOT_TELEMETRY_PATH, methods=['OPTIONS'])
    def iot_telemetry_preflight():
        # CORS preflight responder for cross-origin sensor POSTs.
        return ('', 204)

    # Global 500 handler — log traceback, show generic page
    @app.errorhandler(500)
    def internal_error(e):
        app.logger.error("Unhandled exception: %s", e, exc_info=True)
        return render_template('error.html'), 500

    # Register blueprints
    from .routes import main
    app.register_blueprint(main)

    # ── i18n: language toggle route + template globals ──
    from .i18n import translate, SUPPORTED, DEFAULT_LANG
    @app.context_processor
    def inject_i18n():
        lang = session.get('lang', DEFAULT_LANG)
        return dict(_=lambda t: translate(t, lang), lang=lang)

    @app.route('/set-lang/<lang>')
    def set_lang(lang):
        if lang not in SUPPORTED:
            lang = DEFAULT_LANG
        session['lang'] = lang

        next_url = request.args.get('next', '').strip()
        if next_url.startswith('/'):
            return redirect(next_url)

        return redirect(request.referrer or url_for('main.dashboard'))

    # Schema is owned by Flask-Migrate/Alembic (see migrations/). Do NOT call
    # db.create_all() here: it silently creates tables/columns matching the
    # current models, and then Alembic's own ADD COLUMN/CREATE TABLE fails with
    # "duplicate column"/"already exists" the next time `flask db upgrade` runs.
    # Run `flask db upgrade` once after cloning (Dockerfile does this
    # automatically before starting gunicorn in production).

    return app
