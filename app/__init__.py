import os
import logging
from flask import Flask, render_template
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_migrate import Migrate

db = SQLAlchemy()
migrate = Migrate()
csrf = CSRFProtect()
limiter = Limiter(key_func=get_remote_address, storage_uri="memory://")


def create_app():
    app = Flask(__name__)

    # Security Configuration
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-fallback-key-change-in-production')
    app.config['SESSION_COOKIE_SECURE'] = os.environ.get('RENDER') is not None
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
    app.config['PERMANENT_SESSION_LIFETIME'] = 3600  # 1 hour session timeout
    app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16 MB

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
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com; "
            "connect-src 'self' https://*.tile.openstreetmap.org https://api.open-meteo.com"
        )
        return resp

    # Structured logging
    if not app.debug and not app.testing:
        logging.basicConfig(level=logging.INFO,
                                format='%(asctime)s [%(levelname)s] %(name)s: %(message)s')

    # Global 500 handler — log traceback, show generic page
    @app.errorhandler(500)
    def internal_error(e):
        app.logger.error("Unhandled exception: %s", e, exc_info=True)
        return render_template('error.html'), 500

    # Register blueprints
    from .routes import main
    app.register_blueprint(main)

    # Schema owned by migrations. create_all() kept as a
    # zero-config safety net for fresh local installs only.
    with app.app_context():
        db.create_all()

    return app
