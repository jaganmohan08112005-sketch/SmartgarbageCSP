from datetime import datetime, timezone

from flask import (abort, jsonify, render_template, request)

from ..models import (WasteDeclaration)

from .. import db

from ..auth import admin_required

from . import (WARD_COORDINATES, _compute_analytics, _csrd_payload, _performance_pdf_bytes, _state_portal_indicators, main)


@main.route('/analytics')
@admin_required
def analytics():
    d = _compute_analytics()
    # circular_economy / carbon_data are still passed for the static text displays
    return render_template('analytics.html',
                           circular_economy=d['circular'],
                           carbon_data=d['carbon'])


@main.route('/api/analytics-data')
@admin_required
def analytics_data():
    return jsonify(_compute_analytics())


@main.route('/analytics/state-portal-export')
@admin_required
def state_portal_export():
    indicators = _state_portal_indicators()
    fmt = request.args.get('format', 'json')
    if fmt == 'csv':
        import csv, io
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["indicator", "value"])
        for k, v in indicators.items():
            w.writerow([k, v])
        buf.seek(0)
        return buf.getvalue(), 200, {
            'Content-Type': 'text/csv',
            'Content-Disposition': 'attachment; filename=state_portal_compliance.csv'
        }
    return jsonify({
        "report_title": "State Portal SWM Compliance Return",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "indicators": indicators
    })


@main.route('/api/trend/segregation')
@admin_required
def trend_segregation():
    """Monthly segregation % per ward — aggregated in SQL.

    Previously pulled EVERY WasteDeclaration row into Python (a full-table
    scan that would OOM the 1 GB Fly VM once declarations grow). Now the
    database does the bucketing: group by (month, ward) with per-group sums,
    using the month expression that matches each dialect (strftime on SQLite,
    to_char on Postgres — same parity discipline as the dunning ilike guard).
    The new ix_waste_declaration_ward_timestamp index serves the filter+group.
    """
    from sqlalchemy import func
    from collections import defaultdict

    if db.engine.dialect.name == 'postgresql':
        month_expr = func.to_char(WasteDeclaration.timestamp, 'YYYY-MM')
    else:
        month_expr = func.strftime('%Y-%m', WasteDeclaration.timestamp)

    rows = (db.session.query(
        month_expr.label('month'),
        WasteDeclaration.ward,
        func.sum(WasteDeclaration.wet_kg + WasteDeclaration.dry_kg).label('seg'),
        func.sum(WasteDeclaration.wet_kg + WasteDeclaration.dry_kg +
                 WasteDeclaration.sanitary_kg + WasteDeclaration.hazardous_kg).label('tot'),
    ).filter(WasteDeclaration.timestamp.isnot(None))
     .group_by(month_expr, WasteDeclaration.ward)
     .all())

    # [segregated, total] per (month, ward)
    buckets = defaultdict(lambda: defaultdict(lambda: [0.0, 0.0]))
    for month, ward, seg, tot in rows:
        buckets[month][ward][0] += seg or 0.0
        buckets[month][ward][1] += tot or 0.0
    months = sorted(buckets.keys())
    series = {}
    for wd in WARD_COORDINATES:
        series[wd] = [
            round((buckets[m][wd][0] / buckets[m][wd][1]) * 100, 1)
            if buckets[m].get(wd, [0, 0])[1] else 0.0
            for m in months
        ]
    return jsonify({"months": months, "series": series})


@main.route('/analytics/csrd-export')
@admin_required
def csrd_export():
    return jsonify(_csrd_payload())


@main.route('/analytics/performance-pdf')
@admin_required
def performance_pdf():
    content, filename = _performance_pdf_bytes()
    return content, 200, {
        'Content-Type': 'application/pdf',
        'Content-Disposition': f'attachment; filename={filename}'
    }


@main.route('/analytics/export/request')
@admin_required
def export_request():
    kind = request.args.get('kind', 'state-portal')
    fmt = request.args.get('format', 'json')
    if kind not in ('state-portal', 'csrd', 'performance-pdf'):
        abort(400)
    import uuid
    from ..jobs import enqueue, generate_export_job
    job_id = uuid.uuid4().hex
    enqueue(generate_export_job, job_id, kind, fmt)
    return jsonify({"job_id": job_id, "kind": kind, "status": "queued"})


@main.route('/analytics/export/status/<job_id>')
@admin_required
def export_status(job_id):
    from ..jobs import fetch_artifact
    return jsonify({"job_id": job_id, "status": "ready" if fetch_artifact(job_id) else "processing"})


@main.route('/analytics/export/result/<job_id>')
@admin_required
def export_result(job_id):
    from ..jobs import fetch_artifact
    artifact = fetch_artifact(job_id)
    if artifact is None:
        return jsonify({"error": "Artifact not ready yet."}), 202
    content, content_type, filename = artifact
    return content, 200, {
        'Content-Type': content_type,
        'Content-Disposition': f'attachment; filename={filename}'
    }
