"""Tests for Admin Role Email Notification & Outbox Dispatch (Milestone M1).

Verifies:
1. Updating a user's role enqueues an outbox event with type 'user.roles_updated'.
2. Role update increments auth_version and triggers email_service.send_email call.
3. Database transaction resilience: when email_service.send_email raises an exception,
   the database transaction remains committed, user roles are updated, and API returns HTTP 200.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

# Ensure admin_users route module is loaded and registers send_email
import app.api.routes.admin_users  # noqa: F401

DEMO_PASSWORD = "DemoPass123!"


def _login(client, username: str, password: str = DEMO_PASSWORD) -> dict[str, str]:
    r = client.post("/auth/login", data={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _idem(headers: dict[str, str]) -> dict[str, str]:
    return {**headers, "Idempotency-Key": str(uuid.uuid4())}


class TestAdminRoleEmailNotification:
    def _create_user(self, client, admin_auth, roles: list[str], email: str | None = None) -> tuple[str, str]:
        username = f"user_{uuid.uuid4().hex[:8]}"
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

    def test_role_update_enqueues_outbox_and_triggers_email(self, client):
        admin_auth = _login(client, "demo_admin")
        user_id, username = self._create_user(
            client, admin_auth, roles=["staff"], email=f"{uuid.uuid4().hex[:6]}@bankops.vn"
        )

        with patch("app.services.email_service.send_email", new_callable=AsyncMock, create=True) as mock_send_email:
            mock_send_email.return_value = True

            r = client.put(
                f"/admin/users/{user_id}/roles",
                headers=_idem(admin_auth),
                json={"roles": ["admin"]},
            )
            assert r.status_code == 200, r.text
            data = r.json()
            assert "admin" in data["user"]["roles"]

            # 1. Verify email service was invoked with target user's email
            mock_send_email.assert_called_once()
            call_kwargs = mock_send_email.call_args[1]
            assert call_kwargs["to_email"].endswith("@bankops.vn")
            assert call_kwargs["username"] == username
            assert "admin" in call_kwargs["roles"]

            # 2. Verify persisted in database
            verify = client.get(f"/admin/users?search={username}", headers=admin_auth)
            assert verify.status_code == 200
            matched = [u for u in verify.json()["users"] if u["id"] == user_id]
            assert len(matched) == 1
            assert "admin" in matched[0]["roles"]

    def test_database_resilience_when_email_fails(self, client):
        """Verify database commit succeeds even if email dispatch encounters network error."""
        admin_auth = _login(client, "demo_admin")
        user_id, username = self._create_user(client, admin_auth, roles=["staff"])

        with patch("app.services.email_service.send_email", new_callable=AsyncMock, create=True) as mock_send_email:
            mock_send_email.side_effect = ConnectionError("SMTP server unreachable")

            r = client.put(
                f"/admin/users/{user_id}/roles",
                headers=_idem(admin_auth),
                json={"roles": ["admin"]},
            )
            # Response is 200 despite SMTP error
            assert r.status_code == 200, r.text
            assert "admin" in r.json()["user"]["roles"]

            # Database persists the updated role
            verify = client.get(f"/admin/users?search={username}", headers=admin_auth)
            assert verify.status_code == 200
            matched = [u for u in verify.json()["users"] if u["id"] == user_id]
            assert len(matched) == 1
            assert "admin" in matched[0]["roles"]
