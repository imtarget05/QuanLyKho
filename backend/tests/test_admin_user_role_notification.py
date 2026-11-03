"""Tests for Admin User Role Notification & Database Resilience (Milestone 1).

Verifies:
1. Template generation for admin role grant (HTML, plain text, XSS safety, Vietnamese formatting).
2. Service layer `send_admin_role_granted_email` validation, demo mode, and SMTP dispatch.
3. API endpoint `PUT /admin/users/{user_id}/roles`:
   - Promoting a user to admin calls email dispatch with user's email, subject, and admin role content.
   - Database transaction resilience: when email dispatch raises an exception (SMTP timeout, network drop),
     the database update remains fully committed, user role is updated to admin, and API returns HTTP 200.
   - Assigning non-admin roles does NOT trigger admin email.
   - Already-admin user role updates do NOT re-trigger admin email.
   - Promoting a user without email completes safely.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest

from app.services.email_service import (
    EmailSendResult,
    _build_admin_role_granted_html,
    _build_admin_role_granted_plain,
    is_valid_email,
    send_admin_role_granted_email,
)

DEMO_PASSWORD = "DemoPass123!"


def _login(client, username: str, password: str = DEMO_PASSWORD) -> dict[str, str]:
    r = client.post("/auth/login", data={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _idem(headers: dict[str, str]) -> dict[str, str]:
    return {**headers, "Idempotency-Key": str(uuid.uuid4())}


# ==============================================================================
# 1. Template & Service Layer Unit Tests
# ==============================================================================

class TestAdminRoleEmailTemplates:
    def test_build_admin_role_granted_html_structure(self):
        html_content = _build_admin_role_granted_html(
            username="nguyenvana",
            to_email="vana@bankops.vn",
            display_name="Nguyễn Văn A",
            new_roles=["admin", "approver"],
            granted_by_username="super_admin",
            granted_at_str="14:30:00 ngày 02/11/2026 (Giờ Việt Nam)",
            app_url="https://app.khotrasua.vn",
        )

        # Brand header and styling
        assert "#0F172A" in html_content
        assert "HỆ THỐNG QUẢN TRỊ DOANH NGHIỆP" in html_content
        assert "ADMIN PRIVILEGE" in html_content

        # Explicit admin statement
        assert "Quản Trị Viên (Admin)" in html_content
        assert "Tài Khoản Đã Được Cấp Quyền Quản Trị Viên (Admin)" in html_content

        # Recipient and granter details
        assert "Nguyễn Văn A" in html_content
        assert "@nguyenvana" in html_content
        assert "vana@bankops.vn" in html_content
        assert "super_admin" in html_content
        assert "14:30:00 ngày 02/11/2026 (Giờ Việt Nam)" in html_content

        # Privilege & capabilities summary
        assert "TỔNG HỢP QUYỀN HẠN & PHẠM VI QUẢN TRỊ" in html_content
        assert "Quản trị người dùng & Phân quyền (IAM)" in html_content
        assert "Phê duyệt kho & Kiểm soát vận hành" in html_content
        assert "Quản lý sổ quỹ & Đối soát tài chính" in html_content
        assert "Cấu hình & Nhật ký kiểm toán" in html_content

        # Security and action link
        assert "LƯU Ý BẢO MẬT & AN NINH HỆ THỐNG" in html_content
        assert 'href="https://app.khotrasua.vn"' in html_content
        assert "Truy Cập Hệ Thống Quản Trị" in html_content
        assert "ISO 27001" in html_content

    def test_build_admin_role_granted_html_escapes_xss(self):
        html_content = _build_admin_role_granted_html(
            username="user<script>alert(1)</script>",
            to_email="test<img src=x onerror=alert(1)>@bankops.vn",
            display_name="Hacker <style>body{display:none}</style>",
            new_roles=["admin"],
            granted_by_username="Admin <script>hack</script>",
            granted_at_str="2026-11-02",
            app_url="https://app.khotrasua.vn",
        )

        assert "<script>" not in html_content
        assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html_content
        assert "<img src=x" not in html_content
        assert "&lt;img src=x" in html_content
        assert "<style>" not in html_content
        assert "&lt;style&gt;body{display:none}&lt;/style&gt;" in html_content
        assert "&lt;script&gt;hack&lt;/script&gt;" in html_content

    def test_build_admin_role_granted_plain_structure(self):
        plain_content = _build_admin_role_granted_plain(
            username="tranthib",
            to_email="thib@bankops.vn",
            display_name="Trần Thị B",
            new_roles=["admin"],
            granted_by_username="root_admin",
            granted_at_str="10:00:00 ngày 02/11/2026",
            app_url="https://app.khotrasua.vn",
        )

        assert "=== THÔNG BÁO CẤP QUYỀN QUẢN TRỊ VIÊN (ADMIN) ===" in plain_content
        assert "Trần Thị B" in plain_content
        assert "@tranthib" in plain_content
        assert "thib@bankops.vn" in plain_content
        assert "root_admin" in plain_content
        assert "Quản Trị Viên" in plain_content
        assert "Quản trị người dùng & Phân quyền (IAM)" in plain_content
        assert "Phê duyệt kho & Kiểm soát vận hành" in plain_content
        assert "Quản lý sổ quỹ & Đối soát tài chính" in plain_content
        assert "https://app.khotrasua.vn" in plain_content
        assert "LƯU Ý BẢO MẬT" in plain_content


class TestSendAdminRoleGrantedEmailService:
    @pytest.mark.asyncio
    async def test_invalid_or_empty_email_returns_failed_result(self):
        res_empty = await send_admin_role_granted_email(
            to_email="",
            username="test_user",
            display_name="Test",
            new_roles=["admin"],
        )
        assert bool(res_empty) is False
        assert "không có định dạng hợp lệ" in res_empty.message

        res_invalid = await send_admin_role_granted_email(
            to_email="not-an-email",
            username="test_user",
            display_name="Test",
            new_roles=["admin"],
        )
        assert bool(res_invalid) is False
        assert "không có định dạng hợp lệ" in res_invalid.message

    @pytest.mark.asyncio
    async def test_demo_mode_unconfigured_smtp_returns_clean_result(self, monkeypatch):
        from app.config import settings
        monkeypatch.setattr(settings, "smtp_user", "")
        monkeypatch.setattr(settings, "smtp_password", "")

        res = await send_admin_role_granted_email(
            to_email="admin_dev@bankops.vn",
            username="dev_admin",
            display_name="Dev Admin",
            new_roles=["admin"],
        )
        assert bool(res) is False
        assert "Chưa cấu hình tài khoản SMTP" in res.message

    @pytest.mark.asyncio
    async def test_configured_smtp_dispatches_successfully(self, monkeypatch):
        from app.config import settings
        monkeypatch.setattr(settings, "smtp_user", "sender@bankops.vn")
        monkeypatch.setattr(settings, "smtp_password", "strongpassword")
        monkeypatch.setattr(settings, "smtp_host", "smtp.bankops.vn")
        monkeypatch.setattr(settings, "smtp_port", 587)

        with patch("app.services.email_service._send_smtp_sync", return_value=(True, "Gửi email thành công")) as mock_smtp:
            res = await send_admin_role_granted_email(
                to_email="valid_admin@bankops.vn",
                username="valid_admin",
                display_name="Valid Admin",
                new_roles=["admin", "approver"],
                granted_by_username="head_admin",
            )
            assert bool(res) is True
            assert res.message == "Gửi email thành công"
            mock_smtp.assert_called_once()
            call_kwargs = mock_smtp.call_args[1]
            assert call_kwargs["to_email"] == "valid_admin@bankops.vn"
            assert "Quản Trị Viên (Admin)" in call_kwargs["subject"]
            assert "head_admin (Ban Quản Trị Hệ Thống)" in call_kwargs["from_name"]
            assert "Quản Trị Viên (Admin)" in call_kwargs["html_content"]


# ==============================================================================
# 2. Integration Tests: Role Update Endpoint & Transaction Resilience
# ==============================================================================

class TestAdminRoleNotificationIntegration:
    def _create_employee(self, client, admin_auth, roles: list[str], email: str | None = None) -> tuple[str, str]:
        username = f"emp_{uuid.uuid4().hex[:8]}"
        user_email = email if email is not None else f"{username}@bankops.vn"
        payload = {
            "username": username,
            "display_name": f"Nhân Viên {username}",
            "roles": roles,
            "onboarding_method": "temporary_password",
        }
        if user_email:
            payload["email"] = user_email

        r = client.post("/admin/users", headers=_idem(admin_auth), json=payload)
        assert r.status_code == 201, r.text
        return r.json()["user"]["id"], username

    def test_promote_user_to_admin_triggers_email(self, client):
        admin_auth = _login(client, "demo_admin")
        user_id, username = self._create_employee(client, admin_auth, roles=["staff"], email=f"{uuid.uuid4().hex[:6]}@bankops.vn")

        with patch("app.api.routes.admin_users.send_admin_role_granted_email", new_callable=AsyncMock) as mock_send_email:
            mock_send_email.return_value = EmailSendResult(True, "Email đã gửi thành công")

            r = client.put(
                f"/admin/users/{user_id}/roles",
                headers=_idem(admin_auth),
                json={"roles": ["admin"]},
            )
            assert r.status_code == 200, r.text
            data = r.json()
            assert "admin" in data["user"]["roles"]

            mock_send_email.assert_called_once()
            call_kwargs = mock_send_email.call_args[1]
            assert call_kwargs["username"] == username
            assert "admin" in call_kwargs["new_roles"]
            assert call_kwargs["granted_by_username"] == "demo_admin"
            assert is_valid_email(call_kwargs["to_email"])

    def test_database_resilience_when_email_raises_exception(self, client):
        """CRITICAL: When email dispatch fails/raises exception, DB transaction must still commit."""
        admin_auth = _login(client, "demo_admin")
        user_id, username = self._create_employee(client, admin_auth, roles=["staff"])

        with patch("app.api.routes.admin_users.send_admin_role_granted_email", new_callable=AsyncMock) as mock_send_email:
            # Simulate hard failure: SMTP server network timeout
            mock_send_email.side_effect = RuntimeError("SMTP connection timed out after 12s (Simulated Network Failure)")

            r = client.put(
                f"/admin/users/{user_id}/roles",
                headers=_idem(admin_auth),
                json={"roles": ["admin"]},
            )
            # 1. API endpoint MUST return 200 OK without unhandled 500 error
            assert r.status_code == 200, r.text
            data = r.json()
            assert "admin" in data["user"]["roles"]
            assert data["message"] == "Cập nhật vai trò thành công."

            # 2. Database transaction MUST be committed to PostgreSQL
            verify_res = client.get(f"/admin/users?search={username}", headers=admin_auth)
            assert verify_res.status_code == 200
            matched_users = [u for u in verify_res.json()["users"] if u["id"] == user_id]
            assert len(matched_users) == 1
            assert "admin" in matched_users[0]["roles"]

    def test_non_admin_role_update_does_not_trigger_email(self, client):
        admin_auth = _login(client, "demo_admin")
        user_id, _ = self._create_employee(client, admin_auth, roles=["staff"])

        with patch("app.api.routes.admin_users.send_admin_role_granted_email", new_callable=AsyncMock) as mock_send_email:
            r = client.put(
                f"/admin/users/{user_id}/roles",
                headers=_idem(admin_auth),
                json={"roles": ["staff", "approver"]},
            )
            assert r.status_code == 200, r.text
            assert "admin" not in r.json()["user"]["roles"]
            mock_send_email.assert_not_called()

    def test_already_admin_role_update_does_not_retrigger_email(self, client):
        admin_auth = _login(client, "demo_admin")
        # Start user with admin role
        user_id, _ = self._create_employee(client, admin_auth, roles=["admin"])

        with patch("app.api.routes.admin_users.send_admin_role_granted_email", new_callable=AsyncMock) as mock_send_email:
            # Update roles to include approver, retaining admin
            r = client.put(
                f"/admin/users/{user_id}/roles",
                headers=_idem(admin_auth),
                json={"roles": ["admin", "approver"]},
            )
            assert r.status_code == 200, r.text
            # Should NOT retrigger admin grant email because user was already admin
            mock_send_email.assert_not_called()

    def test_promote_user_without_email_completes_safely(self, client):
        admin_auth = _login(client, "demo_admin")
        # Employee without email
        user_id, username = self._create_employee(client, admin_auth, roles=["staff"], email="")

        with patch("app.api.routes.admin_users.send_admin_role_granted_email", new_callable=AsyncMock) as mock_send_email:
            r = client.put(
                f"/admin/users/{user_id}/roles",
                headers=_idem(admin_auth),
                json={"roles": ["admin"]},
            )
            assert r.status_code == 200, r.text
            assert "admin" in r.json()["user"]["roles"]
            # No email sent because user has no email
            mock_send_email.assert_not_called()

            # Verify persisted in database
            verify_res = client.get(f"/admin/users?search={username}", headers=admin_auth)
            matched_users = [u for u in verify_res.json()["users"] if u["id"] == user_id]
            assert "admin" in matched_users[0]["roles"]
