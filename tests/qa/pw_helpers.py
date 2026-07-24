
import pytest
from playwright.sync_api import expect


class PlaywrightHelpers:
    def __init__(self, page, base_url):
        self.page = page
        self.base = base_url.rstrip("/")

    def goto(self, path):
        self.page.goto(f"{self.base}{path}")

    def login_citizen(self):
        self.goto("/login")
        self.page.fill('input[name="username"]', "qa_citizen")
        self.page.fill('input[name="password"]', "testpass123")
        self.page.click('button[type="submit"]')
        self.page.wait_for_url("**/dashboard", timeout=10000)

    def login_admin(self, app):
        from conftest import _complete_mfa
        from app import create_app
        application = create_app()
        with application.app_context():
            from app.models import User
            u = User.query.filter_by(username="qa_admin").first()
            otp = u.otp if u else None
        self.goto("/login")
        self.page.fill('input[name="username"]', "qa_admin")
        self.page.fill('input[name="password"]', "testpass123")
        self.page.click('button[type="submit"]')
        self.page.fill('input[name="otp"]', otp or "")
        self.page.click('button[type="submit"]')
        self.page.wait_for_url("**/admin", timeout=10000)

    def assert_has_text(self, text):
        expect(self.page).to_contain_text(text)

    def assert_no_alert(self):
        alerts = self.page.locator(".alert").all()
        for a in alerts:
            if "danger" in a.get_attribute("class") or "error" in a.get_attribute("class"):
                pytest.fail(f"Unexpected error alert: {a.inner_text()}")
