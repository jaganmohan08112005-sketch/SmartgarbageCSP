
import os
# sqlite3 removed — PostgreSQL only

import pytest
from app.models import User, Complaint, WorkerProfile


class TestAssetLinkage:
    def test_static_css_returns_200(self, client):
        r = client.get("/static/style.css")
        assert r.status_code == 200

    def test_static_js_returns_200(self, client):
        r = client.get("/static/chintalavalasa_locations.js")
        assert r.status_code == 200

    def test_manifest_and_service_worker(self, client):
        assert client.get("/manifest.json").status_code == 200
        assert client.get("/sw.js").status_code == 200

    def test_static_assets_are_long_cached(self, client):
        """Render-blocking /static assets must be immutable-cached so
        Cloudflare/browsers stop re-fetching bootstrap.css from Render on
        every page load (the LCP bottleneck). Versioned ?v= URLs bust the
        cache on deploy."""
        for path in ("/static/style.css", "/static/vendor/bootstrap.min.css"):
            r = client.get(path)
            assert r.status_code == 200
            cc = r.headers.get("Cache-Control") or ""
            assert "max-age=31536000" in cc, f"{path} not long-cached: {cc}"
            assert "immutable" in cc, f"{path} missing immutable: {cc}"
            # Flask-Login makes Flask add Vary: Cookie to every response,
            # which makes Cloudflare refuse to cache (DYNAMIC) — the exact
            # LCP bottleneck this fix targets. Static assets are identical
            # for every visitor, so the Vary must be stripped.
            assert "cookie" not in (r.headers.get("Vary") or "").lower(), \
                f"{path} still varies by cookie: {r.headers.get('Vary')}"

    def test_static_uploads_never_long_cached(self, client):
        """User-generated uploads (complaint photos, receipts) can be replaced
        in place — they must stay no-cache so a year-old cached copy never
        shadows a new upload."""
        r = client.get("/static/uploads/does_not_exist.jpg")
        cc = r.headers.get("Cache-Control") or ""
        assert "max-age=31536000" not in cc, f"uploads long-cached: {cc}"

    def test_base_template_renders_without_jinja_error(self, client):
        r = client.get("/")
        assert r.status_code == 200
        assert b"SmartGarbage" in r.data

    def test_login_template_renders_cleanly(self, client):
        assert client.get("/login").status_code == 200

    def test_register_template_renders_cleanly(self, client):
        assert client.get("/register").status_code == 200

    def test_admin_template_requires_auth(self, client):
        r = client.get("/admin", follow_redirects=False)
        assert r.status_code in (302, 303, 403)

    def test_dashboard_requires_auth(self, client):
        r = client.get("/dashboard", follow_redirects=False)
        assert r.status_code in (302, 303)


class TestDatabaseSchema:
    def test_postgres_connection_works(self, app):
        """Verify PostgreSQL connection is healthy."""
        from sqlalchemy import text
        from app import db as sa_db
        with app.app_context():
            with sa_db.session.connection() as conn:
                result = conn.execute(text("SELECT 1"))
                assert result.scalar() == 1

    def test_foreign_key_user_complaint_enforced(self, app):
        from sqlalchemy import text
        from app import db as sa_db
        with app.app_context():
            with sa_db.session.connection() as conn:
                # Postgres enforces FKs natively (no setup needed).
                with pytest.raises(Exception):
                    conn.execute(
                        text(
                            "INSERT INTO complaint (name, phone, ward, address, description, status, user_id) "
                            "VALUES (:name, :phone, :ward, :address, :description, :status, :uid)"
                        ),
                        {"name": "x", "phone": "+919876543210", "ward": "Ward 1",
                         "address": "addr", "description": "desc", "status": "Pending", "uid": 999999},
                    )

    def test_fk_worker_profile_points_to_user(self, app):
        with app.app_context():
            wp = WorkerProfile.query.first()
            assert wp is not None
            assert wp.user is not None
            assert wp.user.id == wp.user_id

    def test_fk_complaint_user_relation_via_query(self, app):
        with app.app_context():
            c = Complaint.query.first()
            assert c is not None
            assert c.user_id is not None
            u = User.query.get(c.user_id)
            assert u is not None
