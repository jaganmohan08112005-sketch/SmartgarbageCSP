import hashlib
import os
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
        # Cache per-location weather for 10 minutes (Redis when configured;
        # cache_get/set are silent no-ops without a broker). The landing page
        # previously hit open-meteo synchronously on EVERY render — a slow or
        # down API stalled the whole homepage for up to 5s.
        #
        # NOTE: city_label varies by request mode ("My Location" for lat/lon
        # args, the ward name for ?ward=, "Chintalavalasa" for defaults) and
        # several modes can resolve to the same coordinates (default coords ==
        # Ward 2) — so the label MUST be part of the key or one mode's cached
        # city would poison the others.
        cache_key = f"weather:{city_label}:{target_lat}:{target_lon}"
        cached = cache_get(cache_key)
        if cached:
            return jsonify(cached)
        try:
            api_url = (f"https://api.open-meteo.com/v1/forecast?latitude={target_lat}"
                       f"&longitude={target_lon}&current=temperature_2m,relative_humidity_2m,"
                       f"weather_code,wind_speed_10m&wind_speed_unit=kmh")
            response = requests.get(api_url, timeout=5)
            if response.status_code == 200:
                wd = response.json().get('current', {})
                payload = {
                    "city": city_label,
                    "temp": f"{round(wd.get('temperature_2m'))}°C",
                    "humidity": f"{wd.get('relative_humidity_2m')}%",
                    "wind": f"{wd.get('wind_speed_10m')} km/h",
                    "condition": get_wmo_phrase(wd.get('weather_code', 0))
                }
                cache_set(cache_key, payload, ttl_seconds=600)
                return jsonify(payload)
        except Exception as e:
            logger.error("weather_api_error", error=str(e))
        return jsonify({"error": "Weather API unavailable"}), 500
    return render_template('index.html')


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
    return Response(body, mimetype='text/plain')


@main.route('/sitemap.xml')
def sitemap_xml():
    from flask import Response
    base = request.url_root.rstrip('/')
    # lastmod anchored to deploy time (set in create_app) so the freshness
    # date auto-updates on every deploy instead of going stale by hand.
    last_mod = current_app.config.get('DEPLOY_TIMESTAMP')
    last_mod_str = last_mod.strftime('%Y-%m-%d') if last_mod else '2026-08-06'
    paths = ['/', '/schedule', '/report', '/transparency', '/register',
             '/register/picker', '/privacy']
    urls = ''.join(
        f"  <url><loc>{base}{p}</loc><lastmod>{last_mod_str}</lastmod></url>\n"
        for p in paths)
    body = ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
            + urls + '</urlset>\n')
    return Response(body, mimetype='application/xml')


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
