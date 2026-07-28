"""QA audit tests for admin flows (MFA, cross-role oversight)."""

import json
import pytest
from app import db
from app.models import Complaint, BWGDeclaration, PAYTInvoice, Notification, WasteDeclaration, User


class TestAdminAccess:
    def test_admin_login_requires_mfa(self, client):
        r = client.post("/login", data={"username": "qa_admin", "password": "testpass123"}, follow_redirects=False)
        assert r.status_code in (302, 303)
        with client.session_transaction() as sess:
            assert sess.get("mfa_pending") is True

    def test_admin_dashboard_loads_after_mfa(self, client):
        from conftest import _complete_mfa
        _complete_mfa(client, "qa_admin")
        r = client.get("/admin", follow_redirects=False)
        assert r.status_code == 200

    def test_admin_dashboard_contains_kpis(self, client):
        from conftest import _complete_mfa
        _complete_mfa(client, "qa_admin")
        body = client.get("/admin", follow_redirects=True).data.decode()
        assert "total_bins" in body or "Control Room" in body or "Admin" in body

    def test_admin_audit_requires_superadmin(self, app):
        from conftest import _complete_mfa
        with app.app_context():
            reg = User(
                username="qa_regadmin",
                email="regadmin@example.com",
                password_hash="pbkdf2:sha256:260000$test$test",
                role="admin",
                phone="+919876540002",
                is_approved=True,
                is_superadmin=False,
            )
            db.session.add(reg)
            db.session.commit()
        client = app.test_client()
        _complete_mfa(client, "qa_regadmin")
        r = client.get("/admin/audit", follow_redirects=False)
        assert r.status_code in (302, 303, 403)


class TestAdminCrossRoleOversight:
    def test_admin_sees_citizen_complaint(self, client, app):
        from conftest import _complete_mfa
        _complete_mfa(client, "qa_admin")
        with app.app_context():
            c = Complaint.query.filter_by(name="qa_citizen").first()
            assert c is not None
            cid = c.id
        r = client.get("/admin", follow_redirects=False)
        assert r.status_code == 200

    def test_admin_resolves_citizen_complaint(self, client, app):
        from conftest import _complete_mfa
        _complete_mfa(client, "qa_admin")
        with app.app_context():
            c = Complaint.query.filter_by(name="qa_citizen").first()
            cid = c.id
        r = client.get(f"/resolve/{cid}", follow_redirects=False)
        assert r.status_code == 302
        with app.app_context():
            c = Complaint.query.get(cid)
            assert c.status == "Resolved"

    def test_resolution_creates_notification(self, client, app):
        from conftest import _complete_mfa
        _complete_mfa(client, "qa_admin")
        with app.app_context():
            c = Complaint.query.filter_by(name="qa_citizen").first()
            cid = c.id
            citizen_id = c.user_id
        client.get(f"/resolve/{cid}", follow_redirects=False)
        with app.app_context():
            notes = Notification.query.filter_by(user_id=citizen_id).all()
            assert len(notes) >= 1
            assert "resolved" in notes[-1].message.lower() or "Resolved" in notes[-1].message

    def test_admin_approves_bwg_request(self, client, app):
        from conftest import _complete_mfa
        _complete_mfa(client, "qa_admin")
        with app.app_context():
            u = User.query.filter_by(username="qa_citizen").first()
            decl = BWGDeclaration(
                user_id=u.id,
                entity_name="QA Mall",
                entity_type="commercial",
                composting_kg=10,
                recyclable_kg=10,
                landfill_kg=10,
                request_bulk_pickup=True,
                pickup_status="Pending",
            )
            db.session.add(decl)
            db.session.commit()
            did = decl.id
        r = client.get(f"/admin/bwg-approve/{did}", follow_redirects=False)
        assert r.status_code == 302
        with app.app_context():
            decl = BWGDeclaration.query.get(did)
            assert decl.pickup_status == "Approved"

    def test_admin_fleet_location_returns_json(self, client):
        from conftest import _complete_mfa
        _complete_mfa(client, "qa_admin")
        r = client.get("/api/fleet-location", follow_redirects=False)
        assert r.status_code == 200
        data = json.loads(r.data)
        assert isinstance(data, list)

    def test_admin_illegal_reports_api(self, client):
        from conftest import _complete_mfa
        _complete_mfa(client, "qa_admin")
        r = client.get("/api/illegal-reports", follow_redirects=False)
        assert r.status_code == 200
        data = json.loads(r.data)
        assert isinstance(data, list)

    def test_admin_state_portal_export(self, client):
        from conftest import _complete_mfa
        _complete_mfa(client, "qa_admin")
        r = client.get("/analytics/state-portal-export", follow_redirects=False)
        assert r.status_code == 200
        data = json.loads(r.data)
        assert "indicators" in data

    def test_admin_trend_segregation_api(self, client):
        from conftest import _complete_mfa
        _complete_mfa(client, "qa_admin")
        r = client.get("/api/trend/segregation", follow_redirects=False)
        assert r.status_code == 200
        data = json.loads(r.data)
        assert "months" in data and "series" in data

    def test_admin_analytics_page_loads(self, client):
        from conftest import _complete_mfa
        _complete_mfa(client, "qa_admin")
        r = client.get("/analytics", follow_redirects=False)
        assert r.status_code == 200

    def test_admin_firmware_hub_loads(self, client):
        from conftest import _complete_mfa
        _complete_mfa(client, "qa_admin")
        r = client.get("/admin/firmware", follow_redirects=False)
        assert r.status_code == 200

    def test_superadmin_can_create_admin(self, client):
        from conftest import _complete_mfa
        _complete_mfa(client, "qa_admin")
        r = client.post(
            "/admin/super",
            data={"action": "create_admin", "username": "qa_newadmin", "password": "testpass123", "phone": "+919876540003"},
            follow_redirects=False,
        )
        assert r.status_code in (302, 303)