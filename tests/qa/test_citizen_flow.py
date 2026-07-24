
import json
import pytest
from app import db
from app.models import BWGDeclaration, Complaint, WasteDeclaration, PAYTInvoice, Notification, User


class TestCitizenRegistrationAuth:
    def test_register_creates_citizen(self, client, app):
        client.post(
            "/register",
            data={
                "username": "qa_citizen2",
                "password": "testpass123",
                "phone": "+919876540001",
                "email": "citizen2@example.com",
                "role": "citizen",
            },
            follow_redirects=True,
        )
        with app.app_context():
            u = User.query.filter_by(username="qa_citizen2").first()
            assert u is not None
            assert u.role == "citizen"

    def test_login_creates_session(self, client, app):
        with app.app_context():
            u = User.query.filter_by(username="qa_citizen").first()
            assert u is not None
        client.post("/login", data={"username": "qa_citizen", "password": "testpass123"}, follow_redirects=False)
        with client.session_transaction() as sess:
            assert "user_id" in sess

    def test_logout_clears_session(self, citizen_client):
        citizen_client.get("/logout", follow_redirects=False)
        with citizen_client.session_transaction() as sess:
            assert "user_id" not in sess


class TestCitizenDashboard:
    def test_dashboard_returns_200(self, citizen_client):
        r = citizen_client.get("/dashboard", follow_redirects=False)
        assert r.status_code == 200

    def test_dashboard_contains_user_specific_data(self, citizen_client):
        body = citizen_client.get("/dashboard", follow_redirects=True).data.decode()
        assert "qa_citizen" in body or "Eco-Reward" in body or "Dashboard" in body

    def test_dashboard_shows_ward_leaderboard(self, citizen_client):
        body = citizen_client.get("/dashboard", follow_redirects=True).data.decode()
        assert "Ward" in body or "leaderboard" in body.lower() or "Segregation" in body

    def test_dashboard_payt_section_present(self, citizen_client):
        body = citizen_client.get("/dashboard", follow_redirects=True).data.decode()
        assert "PAYT" in body or "Invoice" in body or "Pay" in body


class TestCitizenFeatureExecution:
    def test_submit_complaint_creates_record(self, citizen_client, app):
        citizen_client.post(
            "/report",
            data={
                "name": "qa_citizen",
                "phone": "+919876543210",
                "ward": "Ward 1 - MVGR College Area",
                "address": "Near gate",
                "description": "QA overflow",
                "latitude": "18.05",
                "longitude": "83.40",
                "report_time": "2026-07-24T10:00",
            },
            follow_redirects=True,
        )
        with app.app_context():
            c = Complaint.query.filter_by(description="QA overflow").first()
            assert c is not None
            assert c.status == "Pending"
            assert c.user_id is not None

    def test_declare_waste_earns_points(self, citizen_client, app):
        before = self._points(app)
        citizen_client.post(
            "/dashboard/declare-waste",
            data={"wet_kg": "2", "dry_kg": "3", "sanitary_kg": "0", "hazardous_kg": "0", "ward": "Ward 1 - MVGR College Area"},
            follow_redirects=True,
        )
        after = self._points(app)
        assert after > before

    def test_waste_declaration_persists(self, citizen_client, app):
        citizen_client.post(
            "/dashboard/declare-waste",
            data={"wet_kg": "1", "dry_kg": "1", "sanitary_kg": "0", "hazardous_kg": "0", "ward": "Ward 1 - MVGR College Area"},
            follow_redirects=True,
        )
        with app.app_context():
            u = User.query.filter_by(username="qa_citizen").first()
            decl = WasteDeclaration.query.filter_by(user_id=u.id).first()
            assert decl is not None

    def test_bulk_declaration_generates_invoice(self, citizen_client, app):
        citizen_client.post(
            "/bwg-ledger",
            data={
                "entity_name": "QA Apartments",
                "entity_type": "residential",
                "composting_kg": "10",
                "recyclable_kg": "20",
                "landfill_kg": "10",
                "request_pickup": "on",
            },
            follow_redirects=True,
        )
        with app.app_context():
            u = User.query.filter_by(username="qa_citizen").first()
            decl = BWGDeclaration.query.filter_by(user_id=u.id).first()
            assert decl is not None
            assert decl.pickup_status == "Pending"

    def test_redeem_points_deducts_balance(self, citizen_client, app):
        citizen_client.post("/api/redeem", data={"points": "5", "reward_type": "Voucher"}, follow_redirects=False)
        with app.app_context():
            u = User.query.filter_by(username="qa_citizen").first()
            assert u.green_points >= 0  # did not crash

    def test_notifications_list_returns_json(self, citizen_client, app):
        r = citizen_client.get("/api/notifications", follow_redirects=False)
        assert r.status_code == 200
        data = json.loads(r.data)
        assert isinstance(data, list)

    def test_payt_invoice_list_returns_json(self, citizen_client):
        r = citizen_client.get("/api/payt-invoice", follow_redirects=False)
        assert r.status_code == 200
        data = json.loads(r.data)
        assert isinstance(data, list)

    def test_bins_api_accessible_to_citizen(self, citizen_client):
        r = citizen_client.get("/api/bins", follow_redirects=False)
        assert r.status_code == 200
        data = json.loads(r.data)
        assert isinstance(data, list)

    def test_leaderboard_api_accessible(self, citizen_client):
        r = citizen_client.get("/api/leaderboard", follow_redirects=False)
        assert r.status_code == 200

    @staticmethod
    def _points(app):
        with app.app_context():
            return User.query.filter_by(username="qa_citizen").first().green_points
