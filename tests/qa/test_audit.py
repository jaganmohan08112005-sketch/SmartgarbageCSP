
import os
import sqlite3

import pytest
from app import create_app, db
from app.models import User, SmartBin, Schedule, Complaint, WorkerProfile


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
    def test_sqlite_file_is_writable(self, app):
        path = app.config["SQLALCHEMY_DATABASE_URI"].replace("sqlite:///", "")
        assert os.path.exists(path)
        conn = sqlite3.connect(path)
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("CREATE TABLE IF NOT EXISTS _probe__(id INTEGER PRIMARY KEY)")
        conn.execute("INSERT INTO _probe__ DEFAULT VALUES")
        conn.execute("DROP TABLE _probe__")
        conn.commit()
        conn.close()

    def test_foreign_key_user_complaint_enforced(self, app):
        from sqlalchemy import text
        from app import db as sa_db
        with app.app_context():
            with sa_db.session.connection() as conn:
                conn.exec_driver_sql("PRAGMA foreign_keys = ON")
                with pytest.raises(Exception):
                    conn.exec_driver_sql(
                        "INSERT INTO complaint (name, phone, ward, address, description, status, user_id) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?)",
                        ("x", "+919876543210", "Ward 1", "addr", "desc", "Pending", 999999),
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
