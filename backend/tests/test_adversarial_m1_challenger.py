"""Adversarial stress-test suite executed by Challenger 1 for Milestone 1.

This test suite empirically stresses:
1. Unusual email addresses (subaddressing, uppercase, leading/trailing whitespace, invalid formats, spaces).
2. Hard SMTP failures, timeouts, connection drops, and unexpected exceptions during email dispatch.
3. IAM / Admin endpoints integrity, regression resistance, self-escalation guards, and /auth/me capability sync.
"""

from __future__ import annotations

import asyncio
import smtplib
import ssl
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import delete

from app.database import AsyncSessionLocal
from app.models.iam import User, UserRole, UserStatus
from app.services.email_service import (
    _send_smtp_sync,
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
# CHALLENGE 1: Unusual Email Addresses & Normalization
# ==============================================================================

class TestAdversarialUnusualEmails:
    @pytest.mark.parametrize(
        ("email_input", "expected_valid", "description"),
        [
            ("alice+admin@bankops.vn", True, "Standard subaddressing / plus tagging"),
            ("first.last+sub_tag.123@sub.bankops.vn", True, "Complex subaddressing with subdomains and numbers"),
            ("ALICE.UPPERCASE@BANKOPS.VN", True, "All uppercase email"),
            ("User.Admin+Tag@Enterprise.Domain.VN", True, "Mixed case with plus tag"),
            ("  spaced.user@bankops.vn  ", True, "Leading and trailing spaces (valid once stripped)"),
            ("\ttabbed.user@bankops.vn\n", True, "Leading tab and trailing newline (valid once stripped)"),
            ("user-name_with.allowed!chars@bankops.vn", True, "Special allowed characters in local part"),
            ("user name with internal spaces@bankops.vn", False, "Invalid: internal spaces in local part"),
            ("user@domain with space.vn", False, "Invalid: internal spaces in domain"),
            ("user@localhost", False, "Invalid: single-label domain without dot"),
            ("user@bankops", False, "Invalid: no dot or TLD"),
            ("user@.vn", False, "Invalid: dot immediately following @"),
            ("@bankops.vn", False, "Invalid: missing local part"),
            ("user@bankops..vn", False, "Invalid: double dot in domain"),
            ("user@domain.c", False, "Invalid: TLD length < 2"),
            ("", False, "Invalid: empty string"),
            ("   ", False, "Invalid: whitespace only"),
            (None, False, "Invalid: NoneType"),
        ],
    )
    def test_is_valid_email_adversarial_matrix(self, email_input, expected_valid, description):
        result = is_valid_email(email_input)
        assert result is expected_valid, f"Failed for {description}: input={email_input!r}"

    @pytest.mark.asyncio
    async def test_send_admin_role_granted_email_cleans_and_dispatches_unusual_emails(self, monkeypatch):
        from app.config import settings
        monkeypatch.setattr(settings, "smtp_user", "sender@bankops.vn")
        monkeypatch.setattr(settings, "smtp_password", "strongpass")
        monkeypatch.setattr(settings, "smtp_host", "smtp.bankops.vn")
        monkeypatch.setattr(settings, "smtp_port", 587)

        # Test uppercase + subaddressing + outer whitespace
        unusual_email = "  ALICE.LEAD+ADMIN_TEST@BANKOPS.VN  "
        with patch("app.services.email_service._send_smtp_sync", return_value=(True, "OK")) as mock_smtp:
            res = await send_admin_role_granted_email(
                to_email=unusual_email,
                username="alice_lead",
                display_name="Alice Lead",
                new_roles=["admin"],
                granted_by_username="super_admin",
            )
            assert bool(res) is True
            mock_smtp.assert_called_once()
            call_kwargs = mock_smtp.call_args[1]
            # Must be strictly normalized to lowercase and trimmed
            assert call_kwargs["to_email"] == "alice.lead+admin_test@bankops.vn"

    @pytest.mark.asyncio
    async def test_send_admin_role_granted_email_rejects_internal_spaces_cleanly(self):
        res = await send_admin_role_granted_email(
            to_email="bad email with spaces@bankops.vn",
            username="bad_user",
            display_name="Bad User",
            new_roles=["admin"],
        )
        assert bool(res) is False
        assert "không có định dạng hợp lệ" in res.message

    def test_promote_user_with_various_email_formats_in_database(self, client, monkeypatch):
        from app.config import settings

        monkeypatch.setattr(settings, "smtp_user", "sender@bankops.vn")
        monkeypatch.setattr(settings, "smtp_password", "test-only-password")
        monkeypatch.setattr(settings, "smtp_host", "smtp.bankops.vn")
        monkeypatch.setattr(settings, "smtp_port", 587)
        admin_auth = _login(client, "demo_admin")

        test_matrix = [
            ("user+plus1@bankops.vn", True, "user+plus1@bankops.vn"),
            ("UPPER.CASE+TAG@BANKOPS.VN", True, "upper.case+tag@bankops.vn"),
            ("  outer_spaces@bankops.vn  ", True, "outer_spaces@bankops.vn"),
            ("internal space@bankops.vn", False, None),
            ("no-at-sign.bankops.vn", False, None),
        ]

        for raw_email, should_send, expected_clean_email in test_matrix:
            username = f"usr_{uuid.uuid4().hex[:8]}"
            create_payload = {
                "username": username,
                "display_name": f"User {username}",
                "roles": ["staff"],
                "onboarding_method": "temporary_password",
                "email": raw_email,
            }
            cr = client.post("/admin/users", headers=_idem(admin_auth), json=create_payload)
            # If the user creation endpoint itself accepts or rejects raw_email:
            if cr.status_code != 201:
                # User creation validated and rejected invalid email format directly
                continue

            user_id = cr.json()["user"]["id"]

            with patch("app.api.routes.admin_users.send_admin_role_granted_email", wraps=send_admin_role_granted_email):
                with patch("app.services.email_service._send_smtp_sync", return_value=(True, "OK")) as mock_smtp:
                    r = client.put(
                        f"/admin/users/{user_id}/roles",
                        headers=_idem(admin_auth),
                        json={"roles": ["admin"]},
                    )
                    # DB update must succeed in ALL cases
                    assert r.status_code == 200, f"Failed for email {raw_email}: {r.text}"
                    assert "admin" in r.json()["user"]["roles"]

                    # Verify email behavior
                    if should_send:
                        assert mock_smtp.called
                        call_to = mock_smtp.call_args[1]["to_email"]
                        assert call_to == expected_clean_email
                    else:
                        assert not mock_smtp.called


# ==============================================================================
# CHALLENGE 2: Hard SMTP Timeouts, Network Drops & Unhandled Exceptions
# ==============================================================================

class TestAdversarialSmtpExceptionsAndResilience:
    @pytest.mark.parametrize(
        "simulated_error",
        [
            smtplib.SMTPConnectError(421, b"4.3.2 Service not available, closing transmission channel"),
            smtplib.SMTPServerDisconnected("Connection unexpectedly closed by remote peer"),
            smtplib.SMTPAuthenticationError(535, b"5.7.8 Authentication credentials invalid"),
            smtplib.SMTPRecipientsRefused({"victim@bankops.vn": (550, b"User mailbox does not exist")}),
            TimeoutError("Socket read timed out after 12.0 seconds"),
            TimeoutError("Operation timed out"),
            ConnectionResetError("Connection reset by peer"),
            ConnectionRefusedError("Connection refused by SMTP daemon"),
            ssl.SSLError("SSL: CERTIFICATE_VERIFY_FAILED certificate verify failed"),
            RuntimeError("Thread executor worker crashed unexpectedly"),
            Exception("Catastrophic generic infrastructure error"),
        ],
    )
    def test_database_resilience_under_smtp_exceptions(self, client, simulated_error):
        """CRITICAL: Every type of socket/SMTP/network/runtime error MUST be caught.
        Database transaction MUST remain committed and API return HTTP 200.
        """
        admin_auth = _login(client, "demo_admin")
        username = f"emp_err_{uuid.uuid4().hex[:8]}"
        cr = client.post(
            "/admin/users",
            headers=_idem(admin_auth),
            json={
                "username": username,
                "display_name": f"Error Test {username}",
                "roles": ["staff"],
                "onboarding_method": "temporary_password",
                "email": f"{username}@bankops.vn",
            },
        )
        assert cr.status_code == 201, cr.text
        user_id = cr.json()["user"]["id"]

        with patch("app.api.routes.admin_users.send_admin_role_granted_email", new_callable=AsyncMock) as mock_send:
            mock_send.side_effect = simulated_error

            r = client.put(
                f"/admin/users/{user_id}/roles",
                headers=_idem(admin_auth),
                json={"roles": ["admin"]},
            )
            # 1. API endpoint returns 200 OK without 500 internal server error
            assert r.status_code == 200, f"Error {type(simulated_error)} leaked to HTTP response: {r.text}"
            data = r.json()
            assert "admin" in data["user"]["roles"]
            assert data["message"] == "Cập nhật vai trò thành công."

            # 2. Database transaction is guaranteed committed in PostgreSQL
            verify = client.get(f"/admin/users?search={username}", headers=admin_auth)
            if verify.status_code == 401:
                admin_auth = _login(client, "demo_admin")
                verify = client.get(f"/admin/users?search={username}", headers=admin_auth)
            assert verify.status_code == 200
            matched = [u for u in verify.json()["users"] if u["id"] == user_id]
            assert len(matched) == 1
            assert "admin" in matched[0]["roles"]

    def test_database_resilience_when_both_emails_raise(self, client):
        """Verify that when BOTH send_email and send_admin_role_granted_email raise, DB is intact."""
        admin_auth = _login(client, "demo_admin")
        username = f"emp_both_{uuid.uuid4().hex[:8]}"
        cr = client.post(
            "/admin/users",
            headers=_idem(admin_auth),
            json={
                "username": username,
                "display_name": f"Both Raise {username}",
                "roles": ["staff"],
                "onboarding_method": "temporary_password",
                "email": f"{username}@bankops.vn",
            },
        )
        assert cr.status_code == 201, cr.text
        user_id = cr.json()["user"]["id"]

        with patch("app.services.email_service.send_email", new_callable=AsyncMock, create=True) as mock_send_email:
            mock_send_email.side_effect = ConnectionError("SMTP primary crashed")
            with patch("app.api.routes.admin_users.send_admin_role_granted_email", new_callable=AsyncMock) as mock_send_admin:
                mock_send_admin.side_effect = TimeoutError("SMTP secondary timeout")

                r = client.put(
                    f"/admin/users/{user_id}/roles",
                    headers=_idem(admin_auth),
                    json={"roles": ["admin"]},
                )
                assert r.status_code == 200, r.text
                assert "admin" in r.json()["user"]["roles"]

                # Check persistence
                verify = client.get(f"/admin/users?search={username}", headers=admin_auth)
                matched = [u for u in verify.json()["users"] if u["id"] == user_id]
                assert len(matched) == 1
                assert "admin" in matched[0]["roles"]

    def test_send_smtp_sync_never_raises_on_any_network_failure(self):
        """_send_smtp_sync must internally catch all exceptions and return (False, msg)."""
        # Connect to unroutable IP (192.0.2.1 TEST-NET-1) or invalid port to trigger socket error
        ok, msg = _send_smtp_sync(
            host="127.0.0.1",
            port=65534,
            user="user@test.vn",
            password="pwd",
            to_email="dest@test.vn",
            subject="Test",
            html_content="<p>Test</p>",
            plain_text_content="Test",
            from_name="Test System",
        )
        assert ok is False
        assert msg != ""


# ==============================================================================
# CHALLENGE 3: IAM / Admin Regressions, Role Hierarchy & Transition Boundaries
# ==============================================================================

class TestAdversarialIamAndAdminRegressions:
    def _create_user(self, client, admin_auth, roles: list[str]) -> tuple[str, str]:
        username = f"iam_{uuid.uuid4().hex[:8]}"
        cr = client.post(
            "/admin/users",
            headers=_idem(admin_auth),
            json={
                "username": username,
                "display_name": f"IAM Test {username}",
                "roles": roles,
                "onboarding_method": "temporary_password",
                "email": f"{username}@bankops.vn",
            },
        )
        assert cr.status_code == 201, cr.text
        return cr.json()["user"]["id"], username

    def test_promote_to_system_admin_triggers_email(self, client):
        """Promoting from staff to system_admin MUST trigger admin notification email."""
        admin_auth = _login(client, "demo_admin")
        user_id, username = self._create_user(client, admin_auth, roles=["staff"])

        with patch("app.api.routes.admin_users.send_admin_role_granted_email", new_callable=AsyncMock) as mock_send:
            r = client.put(
                f"/admin/users/{user_id}/roles",
                headers=_idem(admin_auth),
                json={"roles": ["system_admin"]},
            )
            assert r.status_code == 200, r.text
            assert "system_admin" in r.json()["user"]["roles"]
            mock_send.assert_called_once()
            call_kwargs = mock_send.call_args[1]
            assert "system_admin" in call_kwargs["new_roles"]

    def test_promote_to_root_admin_triggers_email(self, client):
        """Promoting from staff to root_admin MUST trigger admin notification email."""
        admin_auth = _login(client, "demo_admin")
        user_id, username = self._create_user(client, admin_auth, roles=["staff"])

        root_actor_username = f"root_actor_{uuid.uuid4().hex[:8]}"
        root_actor_id = uuid.uuid4()

        async def setup_root_actor():
            async with AsyncSessionLocal() as db:
                from app.api.routes.auth_utils import get_password_hash
                u = User(
                    id=root_actor_id,
                    username=root_actor_username,
                    password_hash=get_password_hash(DEMO_PASSWORD),
                    display_name_demo="Temporary Root Actor",
                    status=UserStatus.active,
                )
                db.add(u)
                await db.flush()
                db.add(UserRole(user_id=root_actor_id, role_code="root_admin"))
                db.add(UserRole(user_id=root_actor_id, role_code="admin"))
                await db.commit()

        asyncio.run(setup_root_actor())
        root_auth = _login(client, root_actor_username)

        try:
            with patch("app.api.routes.admin_users.send_admin_role_granted_email", new_callable=AsyncMock) as mock_send:
                r = client.put(
                    f"/admin/users/{user_id}/roles",
                    headers=_idem(root_auth),
                    json={"roles": ["root_admin"]},
                )
                assert r.status_code == 200, r.text
                assert "root_admin" in r.json()["user"]["roles"]
                mock_send.assert_called_once()
        finally:
            async def cleanup_root_actor():
                async with AsyncSessionLocal() as db:
                    await db.execute(delete(UserRole).where(UserRole.user_id == root_actor_id))
                    u = await db.get(User, root_actor_id)
                    if u:
                        u.status = UserStatus.inactive
                    await db.commit()

            asyncio.run(cleanup_root_actor())

    def test_transition_between_admin_roles_does_not_retrigger_email(self, client):
        """Switching from admin to system_admin (already an admin tier) MUST NOT retrigger email."""
        admin_auth = _login(client, "demo_admin")
        user_id, username = self._create_user(client, admin_auth, roles=["admin"])

        with patch("app.api.routes.admin_users.send_admin_role_granted_email", new_callable=AsyncMock) as mock_send:
            r = client.put(
                f"/admin/users/{user_id}/roles",
                headers=_idem(admin_auth),
                json={"roles": ["system_admin"]},
            )
            assert r.status_code == 200, r.text
            assert "system_admin" in r.json()["user"]["roles"]
            mock_send.assert_not_called()

    def test_demote_admin_to_staff_does_not_trigger_email(self, client):
        """Demoting admin to staff must succeed and NOT trigger admin grant email."""
        admin_auth = _login(client, "demo_admin")
        user_id, username = self._create_user(client, admin_auth, roles=["admin"])

        with patch("app.api.routes.admin_users.send_admin_role_granted_email", new_callable=AsyncMock) as mock_send:
            r = client.put(
                f"/admin/users/{user_id}/roles",
                headers=_idem(admin_auth),
                json={"roles": ["staff"]},
            )
            assert r.status_code == 200, r.text
            assert "admin" not in r.json()["user"]["roles"]
            assert "staff" in r.json()["user"]["roles"]
            mock_send.assert_not_called()

    def test_admin_cannot_self_escalate_roles(self, client):
        """Admin must not be allowed to self-escalate roles via PUT /admin/users/{self_id}/roles."""
        admin_auth = _login(client, "demo_admin")
        # Get demo_admin ID from /auth/me
        me_r = client.get("/auth/me", headers=admin_auth)
        assert me_r.status_code == 200
        admin_id = me_r.json()["id"]

        r = client.put(
            f"/admin/users/{admin_id}/roles",
            headers=_idem(admin_auth),
            json={"roles": ["admin", "root_admin"]},
        )
        # Should be forbidden or return 400/403
        assert r.status_code in (400, 403), f"Self escalation should be blocked, got {r.status_code}: {r.text}"

    def test_promoted_user_receives_capabilities_at_auth_me(self, client):
        """When promoted to admin, user's subsequent /auth/me call reflects admin capabilities."""
        admin_auth = _login(client, "demo_admin")
        username = f"emp_me_{uuid.uuid4().hex[:8]}"
        password = "TemporaryPass123!"

        # Create user
        cr = client.post(
            "/admin/users",
            headers=_idem(admin_auth),
            json={
                "username": username,
                "display_name": f"Me Test {username}",
                "roles": ["staff"],
                "onboarding_method": "temporary_password",
                "temporary_password": password,
                "email": f"{username}@bankops.vn",
            },
        )
        assert cr.status_code == 201, cr.text
        user_id = cr.json()["user"]["id"]

        # Login as employee
        login_pass = cr.json().get("temporary_password") or password
        user_auth = _login(client, username, login_pass)
        me_before = client.get("/auth/me", headers=user_auth)
        assert me_before.status_code == 200
        assert "admin" not in me_before.json().get("roles", [])

        # Admin promotes employee to admin
        # Ensure fresh admin credentials with current auth_version
        admin_auth = _login(client, "demo_admin")
        pr = client.put(
            f"/admin/users/{user_id}/roles",
            headers=_idem(admin_auth),
            json={"roles": ["admin"]},
        )
        assert pr.status_code == 200

        # Note: Depending on auth_version implementation, session might require re-login or fresh token:
        user_auth_fresh = _login(client, username, login_pass)
        me_after = client.get("/auth/me", headers=user_auth_fresh)
        assert me_after.status_code == 200
        data = me_after.json()
        assert "admin" in data["roles"]
        assert any("iam:admin" in cap or "admin" in cap for cap in data.get("capabilities", []))
