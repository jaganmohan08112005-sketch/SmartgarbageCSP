import os
import logging
import structlog
from flask import Flask, render_template, session, redirect, url_for, current_app, request
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_migrate import Migrate
from flask_socketio import SocketIO
from flask_mailman import Mail
from flask_login import LoginManager

db = SQLAlchemy()
migrate = Migrate()
csrf = CSRFProtect()
# In-memory by default; production should set REDIS_URL so rate limits are
# shared across gunicorn workers/instances (per-process memory limits silently
# reset the counter whenever you scale past one worker).
limiter = Limiter(key_func=get_remote_address,
                  storage_uri=os.environ.get("REDIS_URL") or "memory://")
mail = Mail()
socketio = SocketIO()
login_manager = LoginManager()


def create_app(test_config=None):
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

    if test_config:
        app.config.update(test_config)

    # Security Configuration
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY')
    if not app.config['SECRET_KEY']:
        if app.config.get('TESTING') or os.environ.get('PYTEST_CURRENT_TEST'):
            app.config['SECRET_KEY'] = 'test-secret-key-only-for-pytest'
        else:
            raise RuntimeError("SECRET_KEY environment variable is required")
    app.config['SESSION_COOKIE_SECURE'] = os.environ.get('RENDER') is not None
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
    app.config['PERMANENT_SESSION_LIFETIME'] = 3600  # 1 hour session timeout
    app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16 MB

    @app.before_request
    def enforce_https():
        if app.config.get('TESTING') or not os.environ.get('RENDER'):
            return None
        if request.headers.get('X-Forwarded-Proto') != 'https':
            return redirect(request.url.replace('http://', 'https://', 1), code=301)

    # Mail Configuration (flask-mailman)
    app.config['MAIL_SERVER'] = os.environ.get('MAIL_SERVER', 'localhost')
    app.config['MAIL_PORT'] = int(os.environ.get('MAIL_PORT', 25))
    app.config['MAIL_USE_TLS'] = os.environ.get('MAIL_USE_TLS', 'false').lower() in ('true', '1', 'yes')
    app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME', '')
    app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD', '')
    app.config['MAIL_DEFAULT_SENDER'] = os.environ.get('MAIL_DEFAULT_SENDER', 'noreply@smartgarbage.local')

    # Shared secret for authenticating IoT telemetry POSTs from ESP32/Arduino
    # devices. When set (production), /api/bin-telemetry requires a valid
    # HMAC-SHA256 signature in the X-Signature header. A dev fallback keeps
    # local simulators/seed working without a secret configured.
    app.config['IOT_TELEMETRY_SECRET'] = os.environ.get('IOT_TELEMETRY_SECRET')

    # Database Configuration
    app.config.setdefault('UPLOAD_FOLDER', os.path.join(app.root_path, 'static', 'uploads'))
    if not test_config or 'SQLALCHEMY_DATABASE_URI' not in test_config:
        db_url = os.environ.get('DATABASE_URL')
        if db_url:
            # Supabase/Render/Neon all want SSL on the wire. Append sslmode only
            # when it isn't already present (Supabase connection strings may
            # carry their own options like ?sslmode=require or ?options=...).
            if 'sslmode' not in db_url:
                sep = '&' if '?' in db_url else '?'
                db_url = f"{db_url}{sep}sslmode=require"
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
    mail.init_app(app)

    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(user_id):
        from .models import User
        return User.query.get(int(user_id))

    # WebSockets for live IoT/fleet updates.

    # WebSockets for live IoT/fleet updates. Prefer gevent-worker-friendly
    # async modes for production; fall back gracefully when unavailable.
    # When REDIS_URL is set, SocketIO uses Redis as a message queue so
    # broadcasts work across multiple gunicorn workers/instances.
    mq = os.environ.get("REDIS_URL")
    try:
        socketio.init_app(app, async_mode='gevent', cors_allowed_origins="*", message_queue=mq)
    except Exception:
        try:
            socketio.init_app(app, async_mode='eventlet', cors_allowed_origins="*", message_queue=mq)
        except Exception:
            socketio.init_app(app, cors_allowed_origins="*", message_queue=mq)
    # Quiet the SQLAlchemy 1.x LegacyAPIWarning emitted by the app-wide
    # use of `Model.query.get()` (deprecated in 2.0). Tracked separately
    # from a real migration to Session.get().
    import warnings
    from sqlalchemy.exc import LegacyAPIWarning
    warnings.filterwarnings("ignore", category=LegacyAPIWarning)

    # Security headers via after_request (HSTS/secure cookie/CSP scoped to CDNs
    # actually used so Leaflet maps keep working)
    @app.after_request
    def set_security_headers(resp):
        resp.headers['X-Frame-Options'] = 'SAMEORIGIN'
        resp.headers['X-Content-Type-Options'] = 'nosniff'
        resp.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        if os.environ.get('RENDER'):
            resp.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
        resp.headers['Content-Security-Policy'] = (
            "default-src 'self'; "
            "img-src 'self' data: https:; "
            "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com https://unpkg.com https://leaflet.github.io; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://cdnjs.cloudflare.com https://cdn.jsdelivr.net https://unpkg.com; "
            "font-src 'self' https://fonts.gstatic.com https://cdnjs.cloudflare.com; "
            "connect-src 'self' https://*.tile.openstreetmap.org https://api.open-meteo.com"
        )
        return resp

    # Structured logging with structlog
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer()
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )
    logger = structlog.get_logger("smartgarbage")
    app.config['STRUCTLOG_LOGGER'] = logger

    # Keep Python stdlib logging compatible with structlog
    logging.basicConfig(format="%(message)s", level=logging.INFO)
    logging.getLogger().handlers[0].setFormatter(structlog.stdlib.ProcessorFormatter(
        processor=structlog.processors.JSONRenderer()
    ))

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

    # Global error handlers — log traceback, show friendly page
    @app.errorhandler(500)
    def internal_error(e):
        app.logger.error("Unhandled exception: %s", e, exc_info=True)
        return render_template('error.html', code=500, message="Something went wrong on our side."), 500

    @app.errorhandler(404)
    def not_found(e):
        return render_template('error.html', code=404, message="Page not found."), 404

    @app.errorhandler(403)
    def forbidden(e):
        return render_template('error.html', code=403,
                               message="You don't have permission to view this page."), 403

    @app.errorhandler(413)
    def too_large(e):
        return render_template('error.html', code=413,
                               message="That file is too large (max 16 MB)."), 413

    @app.errorhandler(429)
    def too_many(e):
        return render_template('error.html', code=429,
                               message="Too many requests. Please wait a moment and try again."), 429

    @app.errorhandler(400)
    def bad_request(e):
        # CSRF rejections surface as 400 — log them for triage.
        app.logger.warning("bad_request: %s", e)
        return render_template('error.html', code=400,
                               message="That request could not be processed."), 400

    # Register blueprints
    from .routes import main
    app.register_blueprint(main)

    # ── i18n: language toggle route + template globals ──
    from .i18n import translate, SUPPORTED, DEFAULT_LANG
    @app.context_processor
    def inject_i18n():
        lang = session.get('lang', DEFAULT_LANG)
        return dict(_=lambda t: translate(t, lang), lang=lang)

    @app.context_processor
    def inject_current_user():
        from .models import User
        user = None
        if session.get('user_id'):
            user = User.query.get(session['user_id'])
        if user is None:
            class AnonymousUser:
                is_authenticated = False
                role = None
                username = None
                is_superadmin = False
            user = AnonymousUser()
        return dict(current_user=user)

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
    #
    # Lightweight idempotent default-user seeder (no table creation, just
    # INSERT-if-missing so the three login credentials always work without
    # requiring re-registration).
    #
    # SECURITY: these demo accounts have publicly-known credentials, so they are
    # NEVER auto-created in production. They only exist when SEED_DEMO=true or
    # when running locally (no RENDER env). Deployments must create real
    # accounts through registration + admin approval.
    if (os.environ.get('SEED_DEMO', 'false').lower() in ('true', '1', 'yes')
            or not os.environ.get('RENDER')):
        try:
            with app.app_context():
                from app.models import User
                from werkzeug.security import generate_password_hash
                defaults = [
                    ("24331A4441ADMIN", "24331A4441ADMIN", "admin", "+919876543210", True, True),
                    ("24331A4441CITIZEN", "24331A4441CITIZEN", "citizen", "+919876543211", True, False),
                    ("24331A4441WORKER", "24331A4441WORKER", "worker", "+919876543212", True, False),
                ]
                for uname, pwd, role, phone, approved, superadmin in defaults:
                    if not User.query.filter_by(username=uname).first():
                        user = User(
                            username=uname,
                            password_hash=generate_password_hash(pwd),
                            role=role,
                            phone=phone,
                            is_approved=approved,
                            is_superadmin=superadmin,
                            green_points=120 if role == "citizen" else 0,
                        )
                        db.session.add(user)
                db.session.commit()
        except Exception:
            # Silently skip if migrations haven't run yet (no tables yet).
            pass

    return app
