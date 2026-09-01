import os
import logging
from datetime import datetime, timezone
import structlog
from flask import Flask, jsonify, render_template, session, redirect, url_for, request
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_migrate import Migrate
from flask_socketio import SocketIO
from flask_mailman import Mail
from flask_login import LoginManager
from flask_talisman import Talisman
from flask_compress import Compress
from flask.sessions import SecureCookieSessionInterface
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.wrappers import Request as WSGIRequest
from sqlalchemy.exc import OperationalError

db = SQLAlchemy()
migrate = Migrate()
csrf = CSRFProtect()
talisman = Talisman()

# ── Deploy timestamp: a single freshness anchor ──
# Computed ONCE at module import so every gunicorn worker (forked from the
# master that imported this module) reports the same value — a per-app-boot
# computation would let each worker emit a slightly different Last-Modified
# for identical content. Fresh on every deploy because a deploy starts a new
# process. Drives the Last-Modified header, sitemap lastmod, footer and
# JSON-LD dateModified, so none of them need manual date bumps.
DEPLOY_TIMESTAMP = datetime.now(timezone.utc).replace(microsecond=0)


def _is_deployed():
    """True when running on a managed platform (Render or Fly.io).

    Drives HTTPS enforcement, secure-cookie / HSTS headers and the demo-seed
    guard. Both platforms terminate TLS at the edge, so anything behind their
    proxies is production.
    """
    return bool(os.environ.get('RENDER') or os.environ.get('FLY_APP_NAME'))


def _rate_limit_key():
    """Per-user rate-limit key when authenticated; IP for anonymous traffic.

    Previously limits were keyed purely by IP (get_remote_address), which lets
    one abusive user exhaust the whole NAT/office's budget and under-limits a
    single account shared across devices. Authenticated users are now bucketed
    by user id, so limits are fair per-account; anonymous endpoints (login,
    register, webhooks) keep the IP bucket as before.

    Redis-backed via REDIS_URL so counters survive worker restarts and are
    shared across instances; falls back to in-memory locally.
    """
    uid = session.get('user_id')
    if uid:
        return f"user:{uid}"
    return get_remote_address()


# In-memory by default; production should set REDIS_URL so rate limits are
# shared across gunicorn workers/instances (per-process memory limits silently
# reset the counter whenever you scale past one worker).
limiter = Limiter(key_func=_rate_limit_key,
                  storage_uri=os.environ.get("REDIS_URL") or "memory://")
mail = Mail()
socketio = SocketIO()
login_manager = LoginManager()


def create_app(test_config=None):
    app = Flask(__name__)

    # Trust one layer of proxy headers (Fly.io / Render terminate TLS at the
    # edge and rewrite remote_addr). Without this, request.remote_addr is the
    # proxy IP — silently breaking per-IP rate limiting and audit-IP forensics.
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    # ── WSGI middleware: strip Vary: Cookie from public HTML ──
    # This is the ABSOLUTE LAST step before the response hits the wire.
    # Flask's save_session() runs AFTER after_request hooks (Flask 3.x),
    # so even our session-interface override + after_request hook can't
    # guarantee Cookie is stripped. This middleware catches anything that
    # sneaks through. Cloudflare refuses to cache responses with
    # Vary: Cookie (cf-cache-status: DYNAMIC), so this is critical
    # for edge caching and TTFB < 100ms.
    class _StripVaryCookieMiddleware:
        """Strip Vary: Cookie from public HTML responses only.

        Flask sets a CSRF session cookie on every request (even anonymous),
        so we can't use Set-Cookie presence to detect logged-in users.
        Instead, we only strip for non-dashboard routes. Dashboard/login
        routes are already excluded from caching by Cloudflare Cache Rules.
        """
        def __init__(self, wsgi_app):
            self.app = wsgi_app

        def __call__(self, environ, start_response):
            req = WSGIRequest(environ)
            path = req.path
            is_public_html = (
                not path.startswith('/static/')
                and not path.startswith('/admin/')
                and not path.startswith('/dashboard/')
                and not path.startswith('/login')
                and not path.startswith('/register')
                and not path.startswith('/logout')
            )

            def custom_start_response(status, headers, exc_info=None):
                if is_public_html:
                    new_headers = []
                    for name, value in headers:
                        if name.lower() == 'vary':
                            parts = [v.strip() for v in value.split(',')]
                            filtered = [v for v in parts if v.lower() != 'cookie']
                            value = ', '.join(filtered)
                            if value:
                                new_headers.append((name, value))
                        else:
                            new_headers.append((name, value))
                    return start_response(status, new_headers, exc_info)
                return start_response(status, headers, exc_info)

            return self.app(environ, custom_start_response)

    app.wsgi_app = _StripVaryCookieMiddleware(app.wsgi_app)

    # ── Sentry error tracking (if DSN present) ──
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

    if test_config:
        app.config.update(test_config)

    # Security Configuration
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY')
    if not app.config['SECRET_KEY']:
        if app.config.get('TESTING') or os.environ.get('PYTEST_CURRENT_TEST'):
            app.config['SECRET_KEY'] = 'test-secret-key-only-for-pytest'
        else:
            # Self-bootstrapping fallback: if SECRET_KEY was never provisioned
            # in the environment (Render services created before the env var
            # was enforced have no value), generate one and persist it to a
            # 0600 file next to the database so sessions survive restarts.
            # Precedence is unchanged: a real SECRET_KEY env var wins. This
            # only exists so a missing key can never block the deploy; set
            # SECRET_KEY in the platform dashboard for production-grade
            # security (the warning below is the signal to do so).
            import secrets
            import stat as _stat
            _key_path = (('/data/secret_key'
                          if os.environ.get('RENDER') and os.path.isdir('/data')
                          else os.path.join(app.instance_path, 'secret_key')))
            try:
                os.makedirs(os.path.dirname(_key_path), exist_ok=True)
                if os.path.exists(_key_path):
                    with open(_key_path, 'r', encoding='utf-8') as _f:
                        app.config['SECRET_KEY'] = _f.read().strip()
                if not app.config['SECRET_KEY']:
                    app.config['SECRET_KEY'] = secrets.token_hex(32)
                    with open(_key_path, 'w', encoding='utf-8') as _f:
                        _f.write(app.config['SECRET_KEY'])
                    os.chmod(_key_path, _stat.S_IRUSR | _stat.S_IWUSR)  # 0600
                app.logger.warning(
                    "SECRET_KEY not set in env; using persisted key at %s "
                    "(set SECRET_KEY in the platform dashboard to silence this)",
                    _key_path)
            except OSError:
                app.config['SECRET_KEY'] = secrets.token_hex(32)
                app.logger.warning(
                    "SECRET_KEY not set in env and could not be persisted; "
                    "using an ephemeral key (sessions will reset on restart)")
    # Secure cookies on both Render AND Fly.io (edge TLS terminates on both).
    app.config['SESSION_COOKIE_SECURE'] = _is_deployed()
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
    app.config['PERMANENT_SESSION_LIFETIME'] = 3600  # 1 hour session timeout
    app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16 MB

    # Flask appends `Vary: Cookie` to EVERY response whenever the session is
    # merely READ — and Flask-Login reads it on every request, so every
    # response (including static files) carries it. Cloudflare refuses to
    # cache anything with Vary: Cookie (cf-cache-status: DYNAMIC), which is
    # the real reason the render-blocking bootstrap.css re-fetched from
    # Render on every page load — the LCP bottleneck. Immutable, ?v=-versioned
    # static assets are byte-identical for every visitor, so that Vary is a
    # lie for them. It must be discarded in save_session() (via this
    # interface override), which runs AFTER every after_request hook — the
    # only point where Flask has already added the header. Other Vary values
    # (e.g. Accept-Encoding) are left untouched.
    class _StaticNoVarySessionInterface(SecureCookieSessionInterface):
        def save_session(self, app, session, response):
            path = request.path
            is_public_html = (
                (response.mimetype or '').startswith('text/html')
                and not session.get('user_id')
            )
            is_static = path.startswith('/static/') and not path.startswith('/static/uploads/')
            strip_vary = is_public_html or is_static

            if strip_vary:
                # Force save_session() to run by marking session as modified,
                # then strip Vary: Cookie BEFORE super().save_session() adds it.
                session.modified = True

            super().save_session(app, session, response)

            if strip_vary:
                response.vary.discard('Cookie')

    app.session_interface = _StaticNoVarySessionInterface()

    # Deploy timestamp shared with routes/templates (see module constant above).
    app.config['DEPLOY_TIMESTAMP'] = DEPLOY_TIMESTAMP

    # Consent-policy version shown on the analytics banner. Recorded on every
    # Accept/Decline (the ConsentRecord register) so a future policy-text
    # change is auditable — bump this when the banner copy changes.
    app.config['CONSENT_VERSION'] = os.environ.get('CONSENT_VERSION', 'v1')

    # GA4 Measurement ID for the consent-gated analytics in base.html. When
    # unset the site ships NO analytics scripts (only the essential-cookies
    # privacy notice); set ANALYTICS_ID to activate the consent banner + gtag.
    app.config['ANALYTICS_ID'] = os.environ.get('ANALYTICS_ID')

    # Request ID middleware: every request gets a unique ID for tracing across
    # logs, audit entries, and external API calls.
    import uuid

    @app.before_request
    def inject_request_id():
        from flask import g
        g.request_id = request.headers.get('X-Request-ID') or str(uuid.uuid4())

    @app.before_request
    def apply_lang_query_param():
        """Honor ?lang=en|te directly on the current path — the no-JS language
        fallback and any crawler following it get a localized page served with
        a 200, with no /set-lang/ 302 detour in between."""
        from .i18n import SUPPORTED
        lang = request.args.get('lang')
        if lang in SUPPORTED:
            session['lang'] = lang

    # Mail Configuration (flask-mailman)
    app.config['MAIL_SERVER'] = os.environ.get('MAIL_SERVER', 'localhost')
    app.config['MAIL_PORT'] = int(os.environ.get('MAIL_PORT', 25))
    app.config['MAIL_USE_TLS'] = os.environ.get('MAIL_USE_TLS', 'false').lower() in ('true', '1', 'yes')
    app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME', '')
    app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD', '')

    # Public civic contact email — the single source of truth for the footer,
    # GovernmentOrganization schema and privacy-policy Contact section. Set
    # CIVIC_CONTACT_EMAIL in the platform dashboard. Deliberately NO
    # placeholder: while unset, the email renders nowhere on the site, so a
    # fake address can never be published by accident. Transactional mail
    # (OTP, receipts, status alerts) defaults to this address too, unless
    # MAIL_DEFAULT_SENDER is set explicitly for a dedicated from-address.
    app.config['CIVIC_CONTACT_EMAIL'] = os.environ.get('CIVIC_CONTACT_EMAIL')
    app.config['MAIL_DEFAULT_SENDER'] = (
        os.environ.get('MAIL_DEFAULT_SENDER')
        or app.config['CIVIC_CONTACT_EMAIL']
        or 'noreply@smartgarbage.local'
    )

    # Shared secret for authenticating IoT telemetry POSTs from ESP32/Arduino
    # devices. When set (production), /api/bin-telemetry requires a valid
    # HMAC-SHA256 signature in the X-Signature header. A dev fallback keeps
    # local simulators/seed working without a secret configured.
    app.config['IOT_TELEMETRY_SECRET'] = os.environ.get('IOT_TELEMETRY_SECRET')

    # Database Configuration
    app.config.setdefault('UPLOAD_FOLDER', os.path.join(app.root_path, 'static', 'uploads'))
    if not test_config or 'SQLALCHEMY_DATABASE_URI' not in test_config:
        db_url = os.environ.get('DATABASE_URL')
        if not db_url:
            raise RuntimeError(
                "DATABASE_URL is not set. Set it in your environment to point "
                "at the Supabase/PostgreSQL connection string."
            )
        # Supabase/Render/Neon all want SSL on the wire. Append sslmode only
        # when it isn't already present (Supabase connection strings may
        # carry their own options like ?sslmode=require or ?options=...).
        if 'sslmode' not in db_url:
            sep = '&' if '?' in db_url else '?'
            db_url = f"{db_url}{sep}sslmode=require"
        app.config['SQLALCHEMY_DATABASE_URI'] = db_url.replace('postgres://', 'postgresql://')
        app.config['UPLOAD_FOLDER'] = os.path.join('/tmp', 'uploads')

    # Connection pooling tuned for Render + Supabase: pool_pre_ping revalidates
    # connections Supabase idle-drops (the #1 cause of random 500s on Render),
    # pool_recycle stays under Supabase's ~15-min idle timeout, and the small
    # pool + hard overflow ceiling never exceed the plan's connection cap.
    # One gunicorn worker => 3 + 2 = 5 connections is plenty for starter.
    app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
        'pool_pre_ping': True,
        'pool_recycle': 300,
        'pool_size': 3,
        'max_overflow': 2,
    }

    # Ensure the upload directory exists
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

    # Initialize extensions (Talisman is configured below with its full
    # security policy — no bare init here).
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

    # WebSockets for live IoT/fleet updates. Prefer gevent-worker-friendly
    # async modes for production; fall back gracefully when unavailable.
    # When REDIS_URL is set, SocketIO uses Redis as a message queue so
    # broadcasts work across multiple gunicorn workers/instances.
    mq = os.environ.get("REDIS_URL")
    # CORS for SocketIO: in production only the app's own origin may connect
    # (prevents any third-party site from subscribing to live fleet/complaint
    # updates). Locally, allow all origins for convenience.
    _sio_origins = "*" if not _is_deployed() else (
        os.environ.get("SOCKETIO_CORS_ORIGINS")
        or "https://smartgarbage.onrender.com"
    )
    try:
        socketio.init_app(app, async_mode='gevent', cors_allowed_origins=_sio_origins, message_queue=mq)
    except Exception:
        try:
            socketio.init_app(app, async_mode='eventlet', cors_allowed_origins=_sio_origins, message_queue=mq)
        except Exception:
            socketio.init_app(app, cors_allowed_origins=_sio_origins, message_queue=mq)
    # Quiet the SQLAlchemy 1.x LegacyAPIWarning emitted by the app-wide
    # use of `Model.query.get()` (deprecated in 2.0). Tracked separately
    # from a real migration to Session.get().
    import warnings
    from sqlalchemy.exc import LegacyAPIWarning
    warnings.filterwarnings("ignore", category=LegacyAPIWarning)

    # Security headers via Flask-Talisman (HSTS, CSP, secure-cookie, etc.)
    # Scoped to CDNs actually used so Leaflet maps keep working.
    _csp = {
        'default-src': "'self'",
        'img-src': ["'self'", 'data:', 'https:'],
        'script-src': [
            "'self'", "'unsafe-inline'",
            'https://cdn.jsdelivr.net', 'https://cdnjs.cloudflare.com',
            'https://unpkg.com', 'https://leaflet.github.io',
            'https://checkout.razorpay.com', 'https://www.googletagmanager.com',
            'https://www.google-analytics.com'
        ],
        'style-src': [
            "'self'", "'unsafe-inline'",
            'https://fonts.googleapis.com', 'https://cdnjs.cloudflare.com',
            'https://cdn.jsdelivr.net', 'https://unpkg.com'
        ],
        'font-src': ["'self'", 'https://fonts.gstatic.com', 'https://cdnjs.cloudflare.com'],
        'frame-src': ["'self'", 'https://checkout.razorpay.com', 'https://api.razorpay.com'],
        'connect-src': [
            "'self'", 'https://*.tile.openstreetmap.org', 'https://api.open-meteo.com',
            'https://wttr.in',
            'https://api.razorpay.com', 'https://www.google-analytics.com',
            'https://analytics.google.com', 'https://stats.g.doubleclick.net'
        ]
    }
    # CSP report-uri: sends violation reports to the app's own endpoint so
    # admins can monitor for injection attempts. 'unsafe-inline' in script-src
    # is required for inline GA4 gtag initialization and Bootstrap JS events;
    # removing it would break analytics and interactive components.
    _csp['report-uri'] = ['/csp-report']
    talisman.init_app(app, force_https=_is_deployed(),
                      strict_transport_security=True,
                      strict_transport_security_max_age=31536000,
                      strict_transport_security_include_subdomains=True,
                      strict_transport_security_preload=True,
                      # Pass the same value the app configures explicitly: without
                      # this, flask-talisman's session_cookie_secure default (True)
                      # force-sets SESSION_COOKIE_SECURE on every request in
                      # non-debug mode, silently overriding _is_deployed() and
                      # breaking plain-http local/LAN runs.
                      session_cookie_secure=_is_deployed(),
                      content_security_policy=_csp)

    # Text compression (gzip + brotli) for HTML/CSS/JS responses.
    # Cuts Transfer-Encoding by 60-80% on the 144KB homepage — the #1
    # factor in "text compression" and "Brotli compression" audit warnings.
    Compress(app)

    # Structured logging with structlog
    def _add_request_id(_, __, event_dict):
        try:
            from flask import g
            event_dict['request_id'] = getattr(g, 'request_id', None)
        except Exception:
            event_dict['request_id'] = None
        return event_dict

    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            _add_request_id,
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

    # WWW canonicalization: redirect www.* to bare domain so search engines
    # don't treat them as separate sites. Only fires in production (Render)
    # where a custom domain may be configured.
    @app.before_request
    def redirect_www():
        host = request.host.split(':')[0]
        if _is_deployed() and host.startswith('www.'):
            from flask import redirect as _redirect
            new_url = request.url.replace(f'//{host}', f'//{host[4:]}', 1)
            return _redirect(new_url, code=301)

    @app.after_request
    def add_iot_cors(resp):
        if request.path == IOT_TELEMETRY_PATH:
            resp.headers['Access-Control-Allow-Origin'] = '*'
            resp.headers['Access-Control-Allow-Methods'] = 'POST, OPTIONS'
            resp.headers['Access-Control-Allow-Headers'] = 'Content-Type'
        return resp

    # Additional security headers not covered by Flask-Talisman.
    # COOP/COEP/CORP harden cross-origin isolation; X-Permitted-Cross-Domain
    # blocks legacy Flash/PDF cross-domain policy files.
    @app.after_request
    def add_security_headers(resp):
        resp.headers['Cross-Origin-Opener-Policy'] = 'same-origin'
        resp.headers['Cross-Origin-Resource-Policy'] = 'same-origin'
        # Keep connections alive for faster subsequent requests
        resp.headers['Connection'] = 'keep-alive'
        # Ensure CDN caches different encodings (Brotli vs Gzip)
        if 'Vary' not in resp.headers:
            resp.headers['Vary'] = 'Accept-Encoding'
        resp.headers['X-Permitted-Cross-Domain-Policies'] = 'none'
        # COEP with credentialless allows cross-origin subresources (fonts,
        # CDN scripts) without breaking them, while still enforcing isolation.
        if not request.path.startswith('/static/'):
            resp.headers['Cross-Origin-Embedder-Policy'] = 'credentialless'
        return resp

    # Freshness signals: Last-Modified for public, anonymous, full-HTML GET
    # responses, anchored to deploy time. Personal pages (logged-in dashboards,
    # admin) deliberately opt out — their content varies per user, so a shared
    # timestamp would be misleading. Static assets and JSON/XML endpoints are
    # excluded by the text/html check; redirects/errors keep their own status.
    @app.after_request
    def add_last_modified(resp):
        if (request.method in ('GET', 'HEAD')
                and resp.status_code == 200
                and (resp.mimetype or '').startswith('text/html')
                and not session.get('user_id')):
            resp.last_modified = app.config['DEPLOY_TIMESTAMP']
            # Edge cache: s-maxage tells Cloudflare to cache HTML for 5 minutes
            # at the edge. max-age is for browser cache. stale-while-revalidate
            # serves stale content while fetching fresh copy in background.
            # This drops TTFB from ~0.94s (origin) to <100ms (edge hit).
            resp.headers['Cache-Control'] = 'public, max-age=60, s-maxage=300, stale-while-revalidate=60'
            # Server-side Link headers for resource hints (browser starts downloading earlier)
            deploy_v = app.config['DEPLOY_TIMESTAMP'].strftime('%Y%m%d%H%M%S') if app.config.get('DEPLOY_TIMESTAMP') else '20260831'
            resp.headers['Link'] = (
                f'</static/css/critical.css?v={deploy_v}>; rel=preload; as=style, '
                f'</static/fonts/outfit-v15.woff2?v={deploy_v}>; rel=preload; as=font; type=font/woff2; crossorigin, '
                f'</static/vendor/bootstrap.min.css?v={deploy_v}>; rel=preload; as=style; media=print'
            )
            # 103 Early Hints: tell the browser to start loading critical resources
            # BEFORE the server finishes generating the HTML. Reduces TTFB by ~200ms.
            resp.headers['Accept-Ranges'] = 'none'
            # HSTS with preload list (once on the preload list, this is irreversible)
            resp.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
        return resp

    # Long-lived caching for static assets (render-blocking CSS is the LCP
    # bottleneck: without a Cache-Control header Flask sends no-cache, so
    # Cloudflare marks every /static/* response DYNAMIC and each page load
    # re-downloads bootstrap.min.css + style.css from Render with a multi-
    # second TTFB. Static files are immutable because every template reference
    # carries ?v=<deploy_ts> (see templates) — a deploy changes the URL, so a
    # year-long max-age is safe and never serves stale CSS. sw.js and
    # manifest.json are served from custom routes, NOT /static/, so they keep
    # their default no-cache behavior (a service worker must never be
    # long-cached — browsers need to fetch it fresh to pick up updates).
    # /static/uploads/* is user-generated (complaint photos, receipts) and
    # can be replaced — it must keep no-cache so new uploads are never
    # shadowed by a year-old cached copy.
    @app.after_request
    def cache_static_assets(resp):
        if request.path.startswith('/static/') and not request.path.startswith('/static/uploads/'):
            resp.headers['Cache-Control'] = 'public, max-age=31536000, immutable'
        return resp

    # Belt-and-suspenders: strip Vary: Cookie from public HTML responses
    # even if save_session() didn't fire (e.g. edge cases in session handling).
    # This runs AFTER save_session() in the request lifecycle, so it catches
    # any Vary: Cookie that sneaked through. Cloudflare needs this removed
    # to cache HTML at the edge (cf-cache-status: DYNAMIC → HIT).
    @app.after_request
    def strip_vary_cookie(resp):
        if (request.method in ('GET', 'HEAD')
                and resp.status_code == 200
                and (resp.mimetype or '').startswith('text/html')
                and not session.get('user_id')):
            resp.vary.discard('Cookie')
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
        return render_template('404.html'), 404

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

    @app.errorhandler(OperationalError)
    def db_operational_error(e):
        # DB dropped/stopped/full (Supabase idle-kill, storage cap). Roll back
        # the broken transaction so the pooled connection is reusable, then
        # degrade gracefully — stale cached data beats a raw 500.
        app.logger.error("db_operational_error", error=str(e))
        db.session.rollback()
        if request.path.startswith('/api/'):
            try:
                from .routes import cache_get
                cached = cache_get(f"snapshot:{request.path}")
                if cached:
                    return jsonify(dict(cached, degraded=True)), 503
            except Exception:
                pass
            return jsonify({"error": "database_unavailable", "degraded": True,
                            "retry_after": 30}), 503
        return render_template('error.html', code=503,
                               message="Data service temporarily unavailable. Auto-retrying."), 503

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
    def inject_deploy_ts():
        return dict(deploy_ts=app.config.get('DEPLOY_TIMESTAMP'))

    # Critical above-the-fold CSS, inlined as RAW TEXT so first paint never
    # waits on a stylesheet round-trip. It is read from disk (mtime-cached)
    # instead of {% include %}, because minified CSS can legitimately contain
    # "{{" sequences (e.g. bootstrap's :not(:last-child){...) that Jinja would
    # misparse as a template expression. Generated by
    # scripts/build_critical_css.py; re-run that script after template/CSS
    # changes. The returned string is emitted verbatim (never re-parsed).
    _critical_css = {"mtime": 0.0, "content": None}

    def _read_critical_css():
        path = os.path.join(app.root_path, "templates", "partials", "critical.css")
        try:
            mtime = os.path.getmtime(path)
        except OSError:
            return ""
        if _critical_css["mtime"] != mtime or _critical_css["content"] is None:
            try:
                with open(path, "r", encoding="utf-8") as f:
                    _critical_css["content"] = f.read()
                _critical_css["mtime"] = mtime
            except OSError:
                return ""
        return _critical_css["content"]

    @app.context_processor
    def inject_critical_css():
        return dict(critical_css=_read_critical_css)

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

    # Load persisted webhook registrations so they survive restarts and are
    # shared across workers (safe to call pre-migration — helper tolerates the
    # table being absent).
    with app.app_context():
        from .routes import _reload_webhooks
        _reload_webhooks()

    # Schedule the recurring PAYT-dunning run (overdue invoice reminders) as a
    # delayed RQ job. No-op when REDIS_URL is unset — jobs then run inline.
    try:
        from .jobs import schedule_dunning
        schedule_dunning()
    except Exception:
        pass  # queue not available (local dev / tests) — dunning still admin-triggerable

    # Schedule the recurring dead-letter alert sweep: every interval the sweep
    # scans the RQ failed registry and turns exhausted-retry jobs into in-app
    # admin Notifications + a JOB_DEAD_LETTERED webhook, then re-schedules
    # itself. No-op when REDIS_URL is unset (no worker / no registry).
    try:
        from .jobs import schedule_failed_alert_sweep
        schedule_failed_alert_sweep()
    except Exception:
        pass  # queue not available (local dev / tests) — sweep is a no-op

    # Schedule SLA escalation (complaints past their sla_deadline / illegal
    # reports pending > 48h).
    try:
        from .jobs import schedule_sla_escalation
        schedule_sla_escalation()
    except Exception:
        pass

    # Schedule telemetry retention (prune BinTelemetryLog > 90 days).
    try:
        from .jobs import schedule_telemetry_retention
        schedule_telemetry_retention()
    except Exception:
        pass

    # Schedule the 15-minute maintenance sweep (sensor faults + decomposition
    # timers) — replaces the per-admin-load calls that used to run 2 full-table
    # scans + 2N queries on every admin page render.
    try:
        from .jobs import schedule_maintenance
        schedule_maintenance()
    except Exception:
        pass

    # Schedule daily maintenance work-order overdue escalation: notifies the
    # assigned worker + control room (Notification + SSE) when a due date
    # passes, and re-flags still-faulted bins. Deduped per order via
    # escalated_at, so each overdue order notifies exactly once.
    try:
        from .jobs import schedule_maintenance_overdue_escalation
        schedule_maintenance_overdue_escalation()
    except Exception:
        pass

    # Schedule the daily PAYT billing reconciliation (verified OffloadLog
    # weights vs self-reported invoices; flags >20% discrepancies for audit).
    try:
        from .jobs import schedule_payt_reconciliation
        schedule_payt_reconciliation()
    except Exception:
        pass

    # Schedule the weekly ML model retraining (fill-rate + miss-prediction).
    try:
        from .jobs import schedule_model_retraining
        schedule_model_retraining()
    except Exception:
        pass

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
    # when running locally (no RENDER/FLY_APP_NAME env). Deployments must create
    # real accounts through registration + admin approval.
    if (os.environ.get('SEED_DEMO', 'false').lower() in ('true', '1', 'yes')
            or not _is_deployed()):
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
                # Worker accounts also need their driver profile (vehicle,
                # sector, rating): every worker-only API (dispatch
                # accept/complete, GPS heartbeat, offload) looks up
                # WorkerProfile by user_id and 404s when it is missing. Real
                # registrations create one in auth.register(); the demo seeder
                # must too — and idempotently backfill any pre-existing demo
                # DB that predates this (hence the create-if-missing below).
                from app.models import WorkerProfile
                for uname, _, role, _, _, _ in defaults:
                    if role != "worker":
                        continue
                    worker = User.query.filter_by(username=uname).first()
                    if worker and not WorkerProfile.query.filter_by(user_id=worker.id).first():
                        db.session.add(WorkerProfile(
                            user_id=worker.id,
                            vehicle_id="CV-01",
                            latitude=18.0675,
                            longitude=83.4094,
                            status="Active",
                            performance_rating=4.9,
                        ))
                db.session.commit()
        except Exception:
            # Silently skip if migrations haven't run yet (no tables yet).
            pass

    return app


# Render's native-Python runtime starts the app with `gunicorn app:app` (its
# default start command for Python services), which imports this package and
# then looks up an `app` attribute on it. We deliberately do NOT create the
# Flask instance at import time — that would break test collection (tests
# import this module before their app fixture exists, and create_app() raises
# without SECRET_KEY). Instead expose it lazily via PEP 562 module __getattr__:
# gunicorn's `getattr(app_module, 'app')` triggers this on first access, which
# imports wsgi.py (itself the `wsgi:app` entrypoint used by the Dockerfile).
def __getattr__(name):
    if name == 'app':
        from wsgi import app as _wsgi_app
        return _wsgi_app
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
