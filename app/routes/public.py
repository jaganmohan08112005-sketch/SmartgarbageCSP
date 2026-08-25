import hashlib
import os
import threading
import time
import requests

from datetime import datetime, timezone

from flask import (abort, current_app, jsonify, render_template, request, send_from_directory)

from ..models import (Complaint, ComplaintStatusLog, ConsentRecord, Schedule,
                      SmartBin, WasteDeclaration, utcnow)

from ..ml_model import predict_miss

from .. import db, limiter

from . import (DEFAULT_LAT, DEFAULT_LON, WARD_COORDINATES, _redis_client,
               _ward_sla_hours, cache_get, cache_set, get_wmo_phrase, logger, main,
               verify_complaint_token)


# impact_stats (wards / smart-bins / resolved complaints on the hero card)
# has the same flaw the weather block once had: without REDIS_URL, cache_get
# and cache_set are silent no-ops, so the two COUNT queries below ran on
# EVERY homepage render — and against the Supabase pooler each pair costs
# ~1.5–3s, the homepage TTFB bottleneck (all other pages: ~0.5s). A tiny
# in-process TTL cache (10 minutes, matching the Redis TTL) collapses that
# to one query batch per window per worker. Each gunicorn worker keeps its
# own copy; freshness to within one window is fine for hero-card numbers.
_impact_stats_cache = {'at': 0.0, 'value': None}

# Weather widget stale-while-revalidate cache (in-process). cache_get/cache_set
# are Redis-only no-ops without REDIS_URL, so on the free plan EVERY weather
# request previously blocked on a synchronous open-meteo call (~1.6s per load
# — the slowest resource on the homepage). This layer serves the last known
# payload instantly and refreshes open-meteo in the background, so the widget
# never waits on the upstream API and a slow/down provider can't stall it.
_weather_swr = {}           # cache_key -> {'at': monotonic ts, 'value': payload}
_weather_refreshing = set() # keys with a background refresh already in flight
_WEATHER_TTL_S = 600        # must match the Redis TTL used in _weather_store
_WEATHER_SWR_MAX = 64       # bound the dict (GPS lat/lon keys vary per visitor)


def _weather_fetch(lat, lon, city_label):
    """Try Open-Meteo first; fall back to wttr.in if it fails.

    Open-Meteo occasionally rate-limits Render's shared egress IPs (403/429).
    wttr.in uses a different JSON schema so its response is normalised into
    the same widget payload dict.  Each provider gets an independent 4-second
    timeout so the worst-case synchronous path (cold cache miss) is ~8s, not
    10s.  A warning-level log fires on primary failure so egress blocks are
    visible in Sentry without being error-level.
    """
    # ── Primary: Open-Meteo ──────────────────────────────────────────
    try:
        api_url = (f"https://api.open-meteo.com/v1/forecast?latitude={lat}"
                   f"&longitude={lon}&current=temperature_2m,relative_humidity_2m,"
                   f"weather_code,wind_speed_10m&wind_speed_unit=kmh")
        response = requests.get(api_url, timeout=4)
        if response.status_code == 200:
            wd = response.json().get('current', {})
            return {
                "city": city_label,
                "temp": f"{round(wd.get('temperature_2m'))}°C",
                "humidity": f"{wd.get('relative_humidity_2m')}%",
                "wind": f"{wd.get('wind_speed_10m')} km/h",
                "condition": get_wmo_phrase(wd.get('weather_code', 0))
            }
        logger.warning("weather_primary_failed",
                        provider="open-meteo", status=response.status_code)
    except Exception as e:
        logger.warning("weather_primary_failed",
                        provider="open-meteo", error=str(e))

    # ── Fallback: wttr.in ────────────────────────────────────────────
    try:
        wttr_url = f"https://wttr.in/{lat},{lon}?format=j1"
        resp = requests.get(wttr_url, timeout=4)
        if resp.status_code == 200:
            cc = resp.json().get('current_condition', [{}])[0]
            desc = (cc.get('weatherDesc') or [{}])[0].get('value', '')
            return {
                "city": city_label,
                "temp": f"{cc.get('temp_C', '--')}°C",
                "humidity": f"{cc.get('humidity', '--')}%",
                "wind": f"{cc.get('windspeedKmph', '--')} km/h",
                "condition": desc or "Normal Seasonal Conditions"
            }
    except Exception as e:
        logger.error("weather_fallback_error", provider="wttr.in", error=str(e))
    return None


def _weather_store(cache_key, payload):
    """Store a fresh payload in both cache layers (Redis when present + SWR)."""
    cache_set(cache_key, payload, ttl_seconds=_WEATHER_TTL_S)
    if len(_weather_swr) >= _WEATHER_SWR_MAX:
        _weather_swr.pop(next(iter(_weather_swr)))
    _weather_swr[cache_key] = {'at': time.monotonic(), 'value': payload}


def _weather_refresh(cache_key, lat, lon, city_label):
    """Background open-meteo refresh; a failed fetch keeps the stale entry
    serving (last-known weather beats an error). The in-flight set dedupes
    concurrent refreshes so a spike of visitors can't hammer open-meteo."""
    try:
        payload = _weather_fetch(lat, lon, city_label)
        if payload is not None:
            _weather_store(cache_key, payload)
    finally:
        _weather_refreshing.discard(cache_key)


def _homepage_impact():
    cached = _impact_stats_cache
    if time.monotonic() - cached['at'] < 600 and cached['value'] is not None:
        return cached['value']
    impact = {'wards': len(WARD_COORDINATES), 'bins': 0, 'resolved': 0}
    try:
        impact['bins'] = SmartBin.query.count()
        impact['resolved'] = Complaint.query.filter_by(status='Resolved').count()
        cache_set('impact_stats', impact, ttl_seconds=600)
        cached['at'] = time.monotonic()
        cached['value'] = impact
    except Exception as e:
        logger.error("impact_stats_error", error=str(e))
    return impact


@main.route('/')
def home():
    if request.args.get('fetch_weather') == 'true':
        lat = request.args.get('lat')
        lon = request.args.get('lon')
        ward = request.args.get('ward')
        if lat and lon:
            target_lat, target_lon = lat, lon
            city_label = "My Location"
        elif ward in WARD_COORDINATES:
            target_lat = WARD_COORDINATES[ward]['lat']
            target_lon = WARD_COORDINATES[ward]['lon']
            city_label = ward
        else:
            target_lat = DEFAULT_LAT
            target_lon = DEFAULT_LON
            city_label = "Chintalavalasa"
        # Stale-while-revalidate: the Redis cache is checked first (survives
        # restarts when a broker is configured); the in-process layer serves
        # the last known payload instantly even without Redis and refreshes
        # open-meteo in the background — a stale answer beats a ~1.6s wait.
        #
        # NOTE: city_label varies by request mode ("My Location" for lat/lon
        # args, the ward name for ?ward=, "Chintalavalasa" for defaults) and
        # several modes can resolve to the same coordinates (default coords ==
        # Ward 2) — so the label MUST be part of the key or one mode's cached
        # city would poison the others.
        cache_key = f"weather:{city_label}:{target_lat}:{target_lon}"
        cached = cache_get(cache_key)
        if cached:
            _weather_swr[cache_key] = {'at': time.monotonic(), 'value': cached}
            return jsonify(cached)
        entry = _weather_swr.get(cache_key)
        if entry:
            payload = entry['value']
            if (time.monotonic() - entry['at'] >= _WEATHER_TTL_S
                    and cache_key not in _weather_refreshing):
                # Stale: answer now, refresh open-meteo in the background.
                _weather_refreshing.add(cache_key)
                threading.Thread(target=_weather_refresh,
                                 args=(cache_key, target_lat, target_lon, city_label),
                                 daemon=True).start()
            return jsonify(payload)
        # Cache miss (first request for this location): fetch synchronously.
        payload = _weather_fetch(target_lat, target_lon, city_label)
        if payload is None:
            return jsonify({"error": "Weather API unavailable"}), 500
        _weather_store(cache_key, payload)
        return jsonify(payload)
    # Community-impact figures for the homepage card: wards from the coverage
    # map (static), smart-bin and resolved-complaint counts from the DB.
    # Cached for 10 minutes like the weather block — Redis when configured,
    # otherwise the in-process _homepage_impact() TTL cache (without a
    # broker these COUNT queries were the homepage's multi-second TTFB
    # bottleneck). A DB outage must never take down the homepage, so
    # failures fall back to the ward count only.
    impact = cache_get('impact_stats')
    if impact is None:
        impact = _homepage_impact()
    return render_template('index.html', impact=impact)


# Ward collection timetables are public civic information — no login wall so
# crawlers and anonymous residents can read them (the homepage hero links here
# for anonymous visitors too). Nothing user-specific is rendered. The POST runs
# the ML prediction, so it is throttled like /report to stop anonymous hammering.
@main.route('/api/consent', methods=['POST'])
@limiter.limit("10/minute")
def consent_record():
    """Anonymized GDPR/DPDP-style consent capture for the analytics banner.

    Logs the citizen's Accept/Decline choice so the Gram Panchayat can prove
    consent was captured. Deliberately anonymized: the only identifier stored
    is a salted SHA-256 of (IP + user-agent), so the register shows choice
    counts and distinct choosers without ever retaining anything that could
    identify an individual. Fire-and-forget from the client; a failure to log
    must never block the citizen's choice from being applied.
    """
    data = request.get_json(silent=True) or {}
    choice = (data.get('choice') or '').strip().lower()
    if choice not in ('accept', 'decline'):
        return jsonify({'success': False, 'message': 'Invalid choice.'}), 400
    # Consent-policy version the banner showed. Defaults to the deployment's
    # CONSENT_VERSION so bumping the banner copy bumps the audited version.
    version = str(data.get('version') or current_app.config.get('CONSENT_VERSION', 'v1'))[:20]
    source = str(data.get('source') or '')[:200]
    raw = (request.headers.get('User-Agent', '') or '') + '|' + (request.remote_addr or '')
    # Salted with the deployment's SECRET_KEY (self-bootstrapped + persisted,
    # stable across restarts): the fingerprint cannot be recomputed without the
    # key, so a DB leak or source read cannot de-anonymize a visitor.
    salt = current_app.config.get('SECRET_KEY') or 'sg-consent'
    fingerprint = hashlib.sha256((salt + '|' + raw).encode('utf-8')).hexdigest()
    db.session.add(ConsentRecord(choice=choice, version=version,
                                 source=source, fingerprint=fingerprint))
    db.session.commit()
    return jsonify({'success': True})


@main.route('/schedule', methods=['GET', 'POST'])
@limiter.limit("30/hour")
def schedule():
    schedules = []
    prediction = None
    selected_ward = None
    if request.method == 'POST':
        selected_ward = request.form.get('ward')
        schedules = Schedule.query.filter_by(ward=selected_ward).all()
        try:
            prediction = predict_miss(selected_ward)
        except Exception as e:
            logger.error("ml_prediction_error", error=str(e))
    return render_template('schedule.html', schedules=schedules, prediction=prediction, selected_ward=selected_ward)


# Ward transparency — read-only, no login: civic accountability per
# waste-governance norms (public ward health dashboard).
@main.route('/ward/<path:ward_name>')
@main.route('/transparency')
def ward_transparency(ward_name=None):
    wards = list(WARD_COORDINATES.keys())
    if ward_name is None:
        ward_name = wards[0]
    bins = SmartBin.query.filter_by(ward=ward_name).all()
    complaints = Complaint.query.filter_by(ward=ward_name).all()
    open_complaints = [c for c in complaints if c.status != 'Resolved']
    resolved = [c for c in complaints if c.status == 'Resolved']
    avg_fill = round(sum(b.level for b in bins) / len(bins), 1) if bins else 0
    from datetime import timedelta
    cutoff = utcnow() - timedelta(days=30)
    # Ward-scoped: only count declarations made inside the selected ward.
    decls = WasteDeclaration.query.filter(
        WasteDeclaration.ward == ward_name,
        WasteDeclaration.timestamp >= cutoff).all()
    total_w = sum(d.wet_kg + d.dry_kg + d.sanitary_kg + d.hazardous_kg for d in decls) or 1
    segregated_w = sum(d.wet_kg + d.dry_kg for d in decls)
    segregation_rate = round((segregated_w / total_w) * 100, 1)
    return render_template('ward_transparency.html',
                           ward_name=ward_name, wards=wards, bin_count=len(bins),
                           avg_fill=avg_fill, open_complaints=len(open_complaints),
                           resolved=len(resolved), segregation_rate=segregation_rate)


@main.route('/track/<token>')
def track_complaint(token):
    """Public complaint-tracking page for a signed token.

    The token (issued to the reporter at filing time — SMS, success page, and
    dashboard) is a URLSafeTimedSerializer signature over the complaint id, so
    complaints can't be enumerated: an invalid OR expired token 404s, and a
    tampered signature never resolves. The page shows the status timeline
    (ComplaintStatusLog rows, with a synthesized fallback for complaints filed
    before the log existed) and the ward's average resolution time.
    """
    complaint_id = verify_complaint_token(token)
    if complaint_id is None:
        abort(404)
    complaint = Complaint.query.get(complaint_id)
    if complaint is None:
        abort(404)
    events = (ComplaintStatusLog.query
              .filter_by(complaint_id=complaint.id)
              .order_by(ComplaintStatusLog.created_at.asc(), ComplaintStatusLog.id.asc())
              .all())
    # Legacy complaints (pre-status-log) get a minimal synthesized timeline.
    # Only append the current-status step when it isn't a duplicate of the
    # Submitted filing step (a complaint still in Submitted has no second event).
    if events:
        timeline = [{'status': e.status, 'note': e.note, 'at': e.created_at} for e in events]
    else:
        timeline = [{'status': 'Submitted', 'note': 'Complaint filed.',
                     'at': complaint.created_at}]
        if complaint.status != 'Submitted':
            timeline.append({'status': complaint.status,
                             'note': 'Current status at the time this link was generated.',
                             'at': complaint.resolved_at or complaint.closed_at or complaint.sla_deadline})
    sla_hours = _ward_sla_hours().get(complaint.ward)
    return render_template('track.html', complaint=complaint, timeline=timeline,
                           sla_hours=sla_hours)


@main.route('/sw.js')
def serve_sw():
    return send_from_directory(os.path.join(current_app.root_path, 'static'),
                               'sw.js', mimetype='application/javascript')


@main.route('/manifest.json')
def serve_manifest():
    return send_from_directory(os.path.join(current_app.root_path, 'static'),
                               'manifest.json', mimetype='application/json')


@main.route('/offline')
def offline():
    return render_template('offline.html')


@main.route('/privacy')
def privacy_policy():
    return render_template('privacy_policy.html', now=datetime.now(timezone.utc))


# About — public civic information (who operates the portal, service area,
# contact): no login wall so crawlers and residents can read it, and it gives
# the trust audits their "About Page" signal.
@main.route('/about')
def about():
    return render_template('about.html', wards=list(WARD_COORDINATES.keys()))


@main.route('/robots.txt')
def robots_txt():
    from flask import Response
    # AI retrieval bots (ChatGPT live answers, Google AI Overviews, Perplexity)
    # get explicit Allow groups so they outrank the catch-all: a public-service
    # portal WANTS to be citable in AI answers. These are deliberately listed
    # before the generic group so their intent is visible in the file itself.
    ai_bots = ['GPTBot', 'OAI-SearchBot', 'ClaudeBot', 'Google-Extended',
               'PerplexityBot']
    # Non-public paths stay off-limits for EVERY bot: robots.txt applies only
    # the most specific matching group, so an AI group that only said
    # "Allow: /" would silently drop the private-path disallows below.
    private_paths = ("Disallow: /admin\n"
                     "Disallow: /api/\n"
                     "Disallow: /worker\n"
                     "Disallow: /dashboard\n")
    ai_rules = ''.join(f"User-agent: {bot}\nAllow: /\n{private_paths}\n"
                       for bot in ai_bots)
    body = (ai_rules +
            "User-agent: *\n"
            "Allow: /\n"
            + private_paths +
            f"Sitemap: {request.url_root.rstrip('/')}/sitemap.xml\n")
    # no-store: a stale cached robots.txt (the DEPLOY.md §8.2 documented
    # failure — the live site once served an OLD version blocking all
    # crawlers with `Disallow: /`) must never be served by Cloudflare or
    # any proxy/CDN after a deploy. Crawl-control docs should always be
    # fetched fresh from origin.
    return Response(body, mimetype='text/plain',
                    headers={'Cache-Control': 'no-store, max-age=0'})


@main.route('/sitemap.xml')
def sitemap_xml():
    from flask import Response
    base = request.url_root.rstrip('/')
    # lastmod anchored to deploy time (set in create_app) so the freshness
    # date auto-updates on every deploy instead of going stale by hand.
    last_mod = current_app.config.get('DEPLOY_TIMESTAMP')
    last_mod_str = last_mod.strftime('%Y-%m-%d') if last_mod else '2026-08-06'
    paths = ['/', '/about', '/schedule', '/report', '/transparency',
             '/register', '/register/picker', '/privacy']
    urls = ''.join(
        f"  <url><loc>{base}{p}</loc><lastmod>{last_mod_str}</lastmod></url>\n"
        for p in paths)
    body = ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
            + urls + '</urlset>\n')
    # no-store: same reasoning as robots.txt — a stale cached sitemap must
    # never persist across deploys (URL list changes with new pages).
    return Response(body, mimetype='application/xml',
                    headers={'Cache-Control': 'no-store, max-age=0'})


@main.route('/csp-report', methods=['POST'])
def csp_report():
    """Receive CSP violation reports from the browser.

    The report-uri CSP directive sends JSON payloads here when the browser
    blocks a resource that violates the policy. Logged for triage; never
    returns error to the reporter (best-effort).
    """
    try:
        report = request.get_json(silent=True) or {}
        logger.warning("csp_violation", report=report,
                        violation=report.get('csp-report', {}).get('violated-directive', 'unknown'))
    except Exception:
        pass
    return ('', 204)


@main.route('/health')
def health_check():
    import time
    import sqlalchemy
    start = time.time()
    db_ok = False
    db_error = None
    try:
        db.session.execute(sqlalchemy.text('SELECT 1'))
        db_ok = True
    except Exception as e:
        db_error = str(e)
    elapsed_ms = round((time.time() - start) * 1000, 2)

    # Redis check (only when configured) — the rate-limiter + KPI cache depend
    # on it in production, so surface a degraded state instead of silent failure.
    redis_ok, redis_error, redis_ms = None, None, None
    r = _redis_client()
    if r is not None:
        rstart = time.time()
        try:
            r.ping()
            redis_ok = True
        except Exception as e:
            redis_ok = False
            redis_error = str(e)
        redis_ms = round((time.time() - rstart) * 1000, 2)

    checks = {
        'database': {
            'status': 'pass' if db_ok else 'fail',
            'response_time_ms': elapsed_ms,
            'error': db_error,
        }
    }
    if redis_ok is not None:
        checks['redis'] = {
            'status': 'pass' if redis_ok else 'fail',
            'response_time_ms': redis_ms,
            'error': redis_error,
        }
    # Job-queue instrumentation: duration / retry / dead-letter KPIs from the
    # shared counters. Read-only and never affects the health verdict — a
    # dead-lettered job is a signal, not an outage.
    jobs_kpis = None
    try:
        from ..jobs import _counter_snapshot, _job_kpis
        jobs_kpis = _job_kpis(_counter_snapshot())
    except Exception:
        jobs_kpis = None
    healthy = db_ok and (redis_ok is not False)
    payload = {
        'status': 'healthy' if healthy else 'unhealthy',
        'checks': checks,
        'timestamp': datetime.now(timezone.utc).isoformat(),
    }
    if jobs_kpis is not None:
        payload['jobs'] = jobs_kpis
    if not healthy:
        return jsonify(payload), 503
    return jsonify(payload), 200
