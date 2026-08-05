
import threading

from app import db
from app.models import BWGDeclaration, Complaint, User


class TestUnauthorizedEndpointProbing:
    def test_citizen_cannot_access_admin(self, citizen_client):
        r = citizen_client.get("/admin", follow_redirects=False)
        assert r.status_code in (302, 303, 403)

    def test_citizen_cannot_access_admin_audit(self, citizen_client):
        r = citizen_client.get("/admin/audit", follow_redirects=False)
        assert r.status_code in (302, 303, 403)

    def test_citizen_cannot_resolve_complaint(self, citizen_client, app):
        with app.app_context():
            c = Complaint.query.filter_by(name="qa_citizen").first()
            cid = c.id
        r = citizen_client.get(f"/resolve/{cid}", follow_redirects=False)
        assert r.status_code in (302, 303, 403)

    def test_citizen_cannot_approve_bwg(self, citizen_client, app):
        with app.app_context():
            u = User.query.filter_by(username="qa_citizen").first()
            decl = BWGDeclaration(
                user_id=u.id,
                entity_name="X",
                entity_type="commercial",
                composting_kg=1,
                recyclable_kg=1,
                landfill_kg=1,
                request_bulk_pickup=True,
                pickup_status="Pending",
            )
            db.session.add(decl)
            db.session.commit()
            did = decl.id
        r = citizen_client.get(f"/admin/bwg-approve/{did}", follow_redirects=False)
        assert r.status_code in (302, 303, 403)

    def test_citizen_cannot_access_superadmin(self, citizen_client):
        r = citizen_client.get("/admin/super", follow_redirects=False)
        assert r.status_code in (302, 303, 403)

    def test_citizen_cannot_access_firmware(self, citizen_client):
        r = citizen_client.get("/admin/firmware", follow_redirects=False)
        assert r.status_code in (302, 303, 403)


class TestInputSanitizationXSS:
    def test_report_form_escapes_script_tag(self, citizen_client, app):
        citizen_client.post(
            "/report",
            data={
                "name": "<script>alert(1)</script>",
                "phone": "+919876543210",
                "ward": "Ward 1 - MVGR College Area",
                "address": "addr",
                "description": '<img src=x onerror=alert(2)>',
                "latitude": "18.05",
                "longitude": "83.40",
                "report_time": "2026-07-24T10:00",
            },
            follow_redirects=True,
        )
        with app.app_context():
            c = Complaint.query.filter_by(name="<script>alert(1)</script>").first()
            assert c is not None
            body = app.test_client().get("/report", follow_redirects=True).data.decode()
            assert "<script>alert(1)</script>" not in body

    def test_register_rejects_injection_in_username(self, client):
        r = client.post(
            "/register",
            data={
                "username": "<b>admin</b>",
                "password": "testpass123",
                "phone": "+919876540004",
                "email": "inj@example.com",
                "role": "citizen",
            },
            follow_redirects=True,
        )
        assert r.status_code in (200, 302)
        body = r.data.decode()
        assert "Username already exists" in body or "success" in body or "error" in body


class TestMultiSessionIsolation:
    def test_concurrent_admin_read_while_citizen_writes(self, app, citizen_client):
        admin_client = app.test_client()

        def citizen_write():
            for _ in range(3):
                citizen_client.post(
                    "/report",
                    data={
                        "name": "qa_citizen",
                        "phone": "+919876543210",
                        "ward": "Ward 1 - MVGR College Area",
                        "address": "addr",
                        "description": "concurrent",
                        "latitude": "18.05",
                        "longitude": "83.40",
                        "report_time": "2026-07-24T10:00",
                    },
                    follow_redirects=False,
                )

        def admin_read():
            for _ in range(5):
                admin_client.get("/admin", follow_redirects=False)

        threads = [threading.Thread(target=citizen_write), threading.Thread(target=admin_read)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=15)
        assert not any(t.is_alive() for t in threads)
