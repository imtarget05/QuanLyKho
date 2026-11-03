"""Empirical Challenge Suite for Milestone 1: Admin Promotion Email & DB Resilience.

Authored by Challenger 2.
Directly and adversarially challenges Worker 1's implementation across:
1. Already-admin user receiving additional/modified roles (must NEVER trigger admin promotion email).
2. Users assigned non-admin roles (must NEVER trigger admin promotion email).
3. Users without an email address (must NEVER trigger email, must return 200 and commit DB).
4. System resilience under diverse email failure scenarios (RuntimeError, ConnectionRefused, Exception, dual failure).
   In all failure modes, the PostgreSQL transaction must remain 100% committed and HTTP status 200.
5. Promotion lifecycle: staff -> admin (triggers) -> staff (does not trigger) -> admin (triggers).
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest

from app.services.email_service import EmailSendResult

DEMO_PASSWORD = "DemoPass123!"


def _login(client, username: str, password: str = DEMO_PASSWORD) -> dict[str, str]:
    r = client.post("/auth/login", data={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _idem(headers: dict[str, str]) -> dict[str, str]:
    return {**headers, "Idempotency-Key": str(uuid.uuid4())}


class TestChallengerMilestone1Empirical:
    """Rigorous empirical stress test harness for Milestone 1."""

    def _create_user(
        self,
        client,
        admin_auth: dict[str, str],
        roles: list[str],
        email: str | None = None,
    ) -> tuple[str, str]:
        username = f"ch2_{uuid.uuid4().hex[:8]}"
        user_email = email if email is not None else f"{username}@bankops.vn"
        payload = {
            "username": username,
            "display_name": f"Challenger User {username}",
            "roles": roles,
            "onboarding_method": "temporary_password",
        }
        if user_email:
            payload["email"] = user_email

        r = client.post("/admin/users", headers=_idem(admin_auth), json=payload)
        assert r.status_code == 201, r.text
        return r.json()["user"]["id"], username

    # --------------------------------------------------------------------------
    # Challenge 1: Already-admin users receiving additional/modified roles
    # --------------------------------------------------------------------------
    def test_already_admin_granted_additional_roles_never_retriggers(self, client):
        """Verify that when an admin user is granted another role (e.g. admin + approver),

        no admin promotion email is triggered.
        """
        admin_auth = _login(client, "demo_admin")
        user_id, username = self._create_user(client, admin_auth, roles=["admin"])

        with patch("app.api.routes.admin_users.send_admin_role_granted_email", new_callable=AsyncMock) as mock_email:
            # Transition 1: admin -> admin + approver
            r1 = client.put(
                f"/admin/users/{user_id}/roles",
                headers=_idem(admin_auth),
                json={"roles": ["admin", "approver"]},
            )
            assert r1.status_code == 200, r1.text
            roles1 = set(r1.json()["user"]["roles"])
            assert roles1 == {"admin", "approver"}
            mock_email.assert_not_called()

            # Transition 2: admin + approver -> admin + approver + auditor
            r2 = client.put(
                f"/admin/users/{user_id}/roles",
                headers=_idem(admin_auth),
                json={"roles": ["admin", "approver", "auditor"]},
            )
            assert r2.status_code == 200, r2.text
            roles2 = set(r2.json()["user"]["roles"])
            assert roles2 == {"admin", "approver", "auditor"}
            mock_email.assert_not_called()

            # Transition 3: admin + approver + auditor -> admin (dropping non-admin roles)
            r3 = client.put(
                f"/admin/users/{user_id}/roles",
                headers=_idem(admin_auth),
                json={"roles": ["admin"]},
            )
            assert r3.status_code == 200, r3.text
            roles3 = set(r3.json()["user"]["roles"])
            assert roles3 == {"admin"}
            mock_email.assert_not_called()

            # Transition 4: admin -> admin (idempotent reassignment)
            r4 = client.put(
                f"/admin/users/{user_id}/roles",
                headers=_idem(admin_auth),
                json={"roles": ["admin"]},
            )
            assert r4.status_code == 200, r4.text
            roles4 = set(r4.json()["user"]["roles"])
            assert roles4 == {"admin"}
            mock_email.assert_not_called()

    # --------------------------------------------------------------------------
    # Challenge 2: Non-admin role assignments
    # --------------------------------------------------------------------------
    def test_non_admin_role_permutations_never_trigger_admin_email(self, client):
        """Verify that assigning any non-admin role or role permutation NEVER triggers admin promotion email."""
        admin_auth = _login(client, "demo_admin")
        user_id, username = self._create_user(client, admin_auth, roles=["staff"])

        with patch("app.api.routes.admin_users.send_admin_role_granted_email", new_callable=AsyncMock) as mock_email:
            # staff -> auditor
            r1 = client.put(
                f"/admin/users/{user_id}/roles",
                headers=_idem(admin_auth),
                json={"roles": ["auditor"]},
            )
            assert r1.status_code == 200, r1.text
            assert "admin" not in r1.json()["user"]["roles"]
            mock_email.assert_not_called()

            # auditor -> approver
            r2 = client.put(
                f"/admin/users/{user_id}/roles",
                headers=_idem(admin_auth),
                json={"roles": ["approver"]},
            )
            assert r2.status_code == 200, r2.text
            assert "admin" not in r2.json()["user"]["roles"]
            mock_email.assert_not_called()

            # approver -> staff + auditor + approver
            r3 = client.put(
                f"/admin/users/{user_id}/roles",
                headers=_idem(admin_auth),
                json={"roles": ["staff", "auditor", "approver"]},
            )
            assert r3.status_code == 200, r3.text
            assert "admin" not in r3.json()["user"]["roles"]
            mock_email.assert_not_called()

    # --------------------------------------------------------------------------
    # Challenge 3: User without email promoted to admin
    # --------------------------------------------------------------------------
    def test_promote_user_with_no_email_or_empty_email_never_triggers_and_persists(self, client):
        """Verify that when a user has no email address (empty string):

        1. send_admin_role_granted_email is NOT called.
        2. HTTP response is 200 OK.
        3. DB transaction is 100% committed with admin role persisted in PostgreSQL.
        """
        admin_auth = _login(client, "demo_admin")
        user_id, username = self._create_user(client, admin_auth, roles=["staff"], email="")

        with patch("app.api.routes.admin_users.send_admin_role_granted_email", new_callable=AsyncMock) as mock_email:
            r = client.put(
                f"/admin/users/{user_id}/roles",
                headers=_idem(admin_auth),
                json={"roles": ["admin"]},
            )
            assert r.status_code == 200, r.text
            data = r.json()
            assert "admin" in data["user"]["roles"]
            mock_email.assert_not_called()

            # Verify persisted in database across fresh GET query
            get_res = client.get(f"/admin/users?search={username}", headers=admin_auth)
            assert get_res.status_code == 200
            users = [u for u in get_res.json()["users"] if u["id"] == user_id]
            assert len(users) == 1
            assert "admin" in users[0]["roles"]

    # --------------------------------------------------------------------------
    # Challenge 4: Transaction resilience under diverse email failures
    # --------------------------------------------------------------------------
    @pytest.mark.parametrize(
        "simulated_exception",
        [
            RuntimeError("SMTP connection timeout after 15000ms"),
            ConnectionRefusedError("Connection refused on 127.0.0.1:587"),
            ValueError("Malformed envelope data"),
            Exception("Unhandled internal SMTP provider crash"),
        ],
    )
    def test_db_transaction_100_percent_committed_on_email_exception(self, client, simulated_exception):
        """Stress-test DB resilience when email dispatch raises various harsh exceptions.

        The database transaction MUST remain 100% committed, returning HTTP 200.
        """
        admin_auth = _login(client, "demo_admin")
        user_id, username = self._create_user(client, admin_auth, roles=["staff"])

        with patch(
            "app.api.routes.admin_users.send_admin_role_granted_email",
            new_callable=AsyncMock,
            side_effect=simulated_exception,
        ) as mock_email:
            r = client.put(
                f"/admin/users/{user_id}/roles",
                headers=_idem(admin_auth),
                json={"roles": ["admin"]},
            )
            # 1. API endpoint MUST return HTTP 200 OK without failing
            assert r.status_code == 200, f"Expected 200 but got {r.status_code}: {r.text}"
            data = r.json()
            assert "admin" in data["user"]["roles"]
            assert data["message"] == "Cập nhật vai trò thành công."
            mock_email.assert_called_once()

            # 2. Database transaction MUST be committed to PostgreSQL
            get_res = client.get(f"/admin/users?search={username}", headers=admin_auth)
            assert get_res.status_code == 200
            users = [u for u in get_res.json()["users"] if u["id"] == user_id]
            assert len(users) == 1
            assert "admin" in users[0]["roles"]

    def test_dual_email_failure_resilience(self, client):
        """Stress-test: when BOTH generic send_email AND send_admin_role_granted_email raise exceptions,

        the DB transaction must still be 100% committed and HTTP status 200.
        """
        admin_auth = _login(client, "demo_admin")
        user_id, username = self._create_user(client, admin_auth, roles=["staff"])

        with (
            patch(
                "app.api.routes.admin_users.email_service.send_email",
                new_callable=AsyncMock,
                side_effect=RuntimeError("Generic send_email socket timeout"),
            ),
            patch(
                "app.api.routes.admin_users.send_admin_role_granted_email",
                new_callable=AsyncMock,
                side_effect=ConnectionResetError("Admin grant email peer reset"),
            ),
        ):
            r = client.put(
                f"/admin/users/{user_id}/roles",
                headers=_idem(admin_auth),
                json={"roles": ["admin"]},
            )
            assert r.status_code == 200, r.text
            assert "admin" in r.json()["user"]["roles"]

            # Verify PostgreSQL state
            get_res = client.get(f"/admin/users?search={username}", headers=admin_auth)
            assert get_res.status_code == 200
            users = [u for u in get_res.json()["users"] if u["id"] == user_id]
            assert len(users) == 1
            assert "admin" in users[0]["roles"]

    # --------------------------------------------------------------------------
    # Challenge 5: Full promotion & demotion lifecycle
    # --------------------------------------------------------------------------
    def test_admin_promotion_lifecycle(self, client):
        """Test full lifecycle:

        1. staff -> admin: TRIGGERS email
        2. admin -> staff: DOES NOT trigger admin email
        3. staff -> admin: TRIGGERS email again
        """
        admin_auth = _login(client, "demo_admin")
        user_id, username = self._create_user(client, admin_auth, roles=["staff"])

        with patch("app.api.routes.admin_users.send_admin_role_granted_email", new_callable=AsyncMock) as mock_email:
            mock_email.return_value = EmailSendResult(True, "OK")

            # Step 1: Promote to admin -> should trigger
            r1 = client.put(
                f"/admin/users/{user_id}/roles",
                headers=_idem(admin_auth),
                json={"roles": ["admin"]},
            )
            assert r1.status_code == 200
            assert mock_email.call_count == 1

            # Step 2: Demote to staff -> should NOT trigger
            mock_email.reset_mock()
            r2 = client.put(
                f"/admin/users/{user_id}/roles",
                headers=_idem(admin_auth),
                json={"roles": ["staff"]},
            )
            assert r2.status_code == 200
            mock_email.assert_not_called()

            # Step 3: Re-promote to admin -> should trigger again
            mock_email.reset_mock()
            r3 = client.put(
                f"/admin/users/{user_id}/roles",
                headers=_idem(admin_auth),
                json={"roles": ["admin"]},
            )
            assert r3.status_code == 200
            assert mock_email.call_count == 1
