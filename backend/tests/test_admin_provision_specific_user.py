"""Tests provisioning a new Admin user with email mainguyenbinhtan2005@gmail.com.

Verifies end-to-end:
1. Current Admin provisions new user with email mainguyenbinhtan2005@gmail.com and role 'admin'.
2. Invite token generation and accept-invite flow.
3. Newly activated admin logs in and executes admin-only capabilities.
4. Auto-cleanup/unlinking of test user emails before and after execution.
"""
from __future__ import annotations

import asyncio
import uuid

import pytest
from sqlalchemy import update

from app.database import AsyncSessionLocal
from app.models.iam import User

DEMO_PASSWORD = "DemoPass123!"


def _login(client, username: str, password: str = DEMO_PASSWORD) -> dict[str, str]:
    r = client.post("/auth/login", data={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _idem(headers: dict[str, str]) -> dict[str, str]:
    return {**headers, "Idempotency-Key": str(uuid.uuid4())}


@pytest.fixture(autouse=True)
def clean_test_emails():
    """Ensure clean slate for mainguyenbinhtan2005 emails without violating immutable audit logs."""
    async def _cleanup():
        async with AsyncSessionLocal() as db:
            await db.execute(
                update(User)
                .where(User.email.like("mainguyenbinhtan2005%"))
                .values(email=None)
            )
            await db.commit()

    asyncio.run(_cleanup())
    yield
    asyncio.run(_cleanup())


class TestAdminProvisionSpecificUser:
    def test_admin_invites_new_admin_with_specific_email(self, client, monkeypatch):
        """Current admin provisions new admin with email mainguyenbinhtan2005@gmail.com via invite."""
        monkeypatch.setattr("app.config.settings.smtp_user", "test@gmail.com")
        monkeypatch.setattr("app.config.settings.smtp_password", "test_app_pass")
        monkeypatch.setattr("app.services.email_service._send_smtp_sync", lambda **kwargs: (True, "Gửi email thành công"))
        admin_auth = _login(client, "demo_admin")
        username = f"tan_{uuid.uuid4().hex[:6]}"
        target_email = "mainguyenbinhtan2005@gmail.com"

        # 1. Provision new admin
        res = client.post(
            "/admin/users",
            headers=_idem(admin_auth),
            json={
                "username": username,
                "display_name": "Mai Nguyễn Bình Tân",
                "email": target_email,
                "roles": ["admin"],
                "onboarding_method": "invite_email",
            },
        )
        assert res.status_code == 201, res.text
        body = res.json()
        user_data = body["user"]

        assert user_data["username"] == username
        assert user_data["email"] == target_email
        assert "admin" in user_data["roles"]
        assert user_data["has_pending_invite"] is True

        invite_token = body.get("invite_token")
        assert invite_token is not None, "Invite token must be generated for invite_email"
        assert body.get("invite_email_sent") is True, f"Email delivery failed: {body.get('email_delivery_message')}"
        assert body.get("invite_link") is not None
        assert "quan-ly-kho-tra-sua.tanmainguyenbinh.workers.dev/accept-invite" in body["invite_link"]

        # 2. Tan Admin accepts invite and sets password
        new_password = "BinhTanAdminSecret2026!#"
        accept_res = client.post(
            "/auth/accept-invite",
            json={
                "invite_token": invite_token,
                "new_password": new_password,
            },
        )
        assert accept_res.status_code == 200, accept_res.text
        accept_body = accept_res.json()
        assert "access_token" in accept_body
        assert "admin" in accept_body["user"]["roles"]

        # 3. Tan Admin logs in with credentials
        login_res = client.post(
            "/auth/login",
            data={"username": username, "password": new_password},
        )
        assert login_res.status_code == 200, login_res.text
        tan_token = {"Authorization": f"Bearer {login_res.json()['access_token']}"}

        # 4. Verify Tan Admin has full admin privileges
        # Can access admin users list
        users_list = client.get("/admin/users", headers=tan_token)
        assert users_list.status_code == 200, users_list.text

        # Can manage catalog (create item)
        new_sku = f"ADMIN_TEA_{uuid.uuid4().hex[:6].upper()}"
        item_res = client.post(
            "/inventory/items",
            headers=_idem(tan_token),
            json={
                "sku": new_sku,
                "name": "Trà Thiết Quan Âm Thượng Hạng",
                "unit": "kg",
                "cost_price": "250000",
                "selling_price": "400000",
            },
        )
        assert item_res.status_code == 201, item_res.text
        assert item_res.json()["sku"] == new_sku

    def test_admin_creates_new_admin_with_temp_password(self, client):
        """Current admin provisions new admin with temporary password."""
        admin_auth = _login(client, "demo_admin")
        username = f"tan_temp_{uuid.uuid4().hex[:6]}"
        target_email = "mainguyenbinhtan2005@gmail.com"

        res = client.post(
            "/admin/users",
            headers=_idem(admin_auth),
            json={
                "username": username,
                "display_name": "Mai Nguyễn Bình Tân (Temp)",
                "email": target_email,
                "roles": ["admin"],
                "onboarding_method": "temporary_password",
            },
        )
        assert res.status_code == 201, res.text
        body = res.json()
        temp_pass = body.get("temporary_password")
        assert temp_pass is not None

        # Login with temp pass requires password change
        login_res = client.post(
            "/auth/login",
            data={"username": username, "password": temp_pass},
        )
        assert login_res.status_code == 200
        login_data = login_res.json()
        must_change = login_data.get("must_change_password") or login_data.get("user", {}).get("must_change_password")
        assert must_change is True
        token = {"Authorization": f"Bearer {login_data['access_token']}"}

        # Change password
        ch_res = client.post(
            "/auth/change-initial-password",
            headers=_idem(token),
            json={"current_password": temp_pass, "new_password": "NewPermanentPass123!#"},
        )
        assert ch_res.status_code == 200

    def test_smtp_status_endpoint(self, client, monkeypatch):
        """Admin can check SMTP server connection health."""
        async def _mock_check():
            return {
                "configured": True,
                "host": "smtp.gmail.com",
                "port": 587,
                "user": "test@gmail.com",
                "status": "connected",
                "message": "Kết nối và xác thực SMTP thành công",
            }

        monkeypatch.setattr("app.features.admin.routes.check_smtp_health", _mock_check)
        admin_auth = _login(client, "demo_admin")
        res = client.get("/admin/smtp-status", headers=admin_auth)
        assert res.status_code == 200, res.text
        data = res.json()
        assert data["configured"] is True
        assert data["host"] == "smtp.gmail.com"
        assert data["status"] == "connected"

