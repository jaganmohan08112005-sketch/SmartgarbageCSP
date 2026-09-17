"""Resolve a complaint as a worker — with mandatory photo proof.

Closes the loop the same way /resolve-bin does for bins: the worker must
upload a live photo of the site (stored through save_compressed_photo's
image-only pipeline) and share on-site GPS within CLEAR_RADIUS_M of the
nearest bin in the complaint's ward. Admin resolves (no field evidence)
remain available from the control room.
"""
from flask import jsonify, request
from ..models import Complaint, SmartBin, utcnow
from ..auth import worker_required
from .. import db
from . import (main, _notify_status_change, haversine_m, write_audit,
               record_complaint_event, save_compressed_photo)
from .worker import CLEAR_RADIUS_M


@main.route('/resolve-complaint/<int:complaint_id>', methods=['POST'])
@worker_required
def resolve_complaint_with_proof(complaint_id):
    complaint = Complaint.query.get_or_404(complaint_id)
    if complaint.status in ('Resolved', 'Closed'):
        return jsonify({"success": False,
                        "message": "This complaint is already resolved."}), 409

    # ── 1. Photo proof is mandatory ──
    photo_file = request.files.get('resolution_photo')
    if not photo_file or photo_file.filename == '':
        return jsonify({"success": False,
                        "message": "A live photo of the site is required to mark this complaint resolved."}), 400

    # ── 2. On-site GPS is mandatory and ward-plausible ──
    try:
        w_lat = float(request.form.get('lat', ''))
        w_lon = float(request.form.get('lon', ''))
    except (TypeError, ValueError):
        w_lat = w_lon = None
    if w_lat is None or w_lon is None or not (-90 <= w_lat <= 90) or not (-180 <= w_lon <= 180):
        return jsonify({"success": False,
                        "message": "Enable location so your GPS can verify you are on site."}), 400

    ward_bins = SmartBin.query.filter_by(ward=complaint.ward).all()
    if ward_bins:
        dist_m = min(haversine_m(w_lat, w_lon, b.latitude, b.longitude)
                     for b in ward_bins)
        if dist_m > CLEAR_RADIUS_M:
            return jsonify({"success": False,
                            "message": f"Your GPS ({dist_m:.0f}m from the ward's nearest bin) is out of range. Go to the site and retry."}), 400

    # ── 3. Persist evidence, then resolve ──
    # save_compressed_photo returns None for non-image uploads (fail-closed):
    # no decodable proof, no resolution.
    photo_path = save_compressed_photo(photo_file, 'resolution')
    if not photo_path:
        return jsonify({"success": False,
                        "message": "The photo could not be processed as an image. Upload a real photo of the site."}), 400

    complaint.status = 'Resolved'
    complaint.resolved_at = utcnow()
    complaint.resolution_photo = photo_path
    record_complaint_event(complaint, 'Resolved',
                           'Resolved by sanitation worker — photo proof attached.',
                           commit=False)
    db.session.commit()
    write_audit("WORKER_RESOLVE_COMPLAINT", target=f"Complaint #{complaint_id}",
                detail=f"Ward: {complaint.ward}; proof: {photo_path[:80]}")
    _notify_status_change(complaint)
    return jsonify({"success": True,
                    "message": f"Complaint #{complaint_id} resolved with photo proof.",
                    "photo": photo_path})
