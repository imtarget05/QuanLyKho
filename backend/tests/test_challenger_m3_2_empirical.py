"""Empirical Challenge & Stress Test Suite: Milestone 3.

Authored by Challenger M3-2.
Empirically challenges Worker 1 & Milestone 3 implementation:
1. Permutations of non-admin role transitions (staff <-> approver <-> inventory_manager <-> cash_sim_operator <-> auditor <-> integration_admin)
   NEVER trigger admin promotion email.
2. Promotion to admin (or system_admin) triggers admin email notification EXACTLY ONCE.
3. Modifying an existing admin's roles never re-triggers admin email.
4. Demotion then re-promotion triggers email notification on re-promotion.
5. Invalidation of sessions via auth_version:
   Tokens carrying stale auth_version are rejected with HTTP 401 ("Phiên đăng nhập đã bị thu hồi.")
   immediately across protected endpoints.
6. Multi-version progression under rapid sequential role updates.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

from app.services.email_service import EmailSendResult

DEMO_PASSWORD = "DemoPass123!"
PERMANENT_PASSWORD = "ChallengerTestPass123!"


def _login(client, username: str, password: str = DEMO_PASSWORD) -> dict[str, str]:
    r = client.post("/auth/login", data={"username": username, "password": password})
    assert r.status_code == 200, f"Login failed for {username}: {r.text}"
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _idem(headers: dict[str, str]) -> dict[str, str]:
    return {**headers, "Idempotency-Key": str(uuid.uuid4())}


def _create_and_activate_user(
    client,
    admin_auth: dict[str, str],
    roles: list[str],
    email: str | None = None,
) -> tuple[str, str, dict[str, str]]:
    """Helper to create a user and activate their password so they have a live token."""
    username = f"ch32_{uuid.uuid4().hex[:8]}"
    initial_password = f"InitPass_{uuid.uuid4().hex[:6]}!"
    payload = {
        "username": username,
        "display_name": f"User {username}",
        "roles": roles,
        "temporary_password": initial_password,
        "onboarding_method": "temporary_password",
    }
    if email:
        payload["email"] = email

    create_res = client.post("/admin/users", headers=_idem(admin_auth), json=payload)
    assert create_res.status_code == 201, create_res.text
    user_id = create_res.json()["user"]["id"]
    temp_pass = create_res.json().get("temporary_password") or initial_password

    # Log in with temporary password and change to permanent password
    temp_auth = _login(client, username, temp_pass)
    chg_res = client.post(
        "/auth/change-initial-password",
        headers=_idem(temp_auth),
        json={"current_password": temp_pass, "new_password": PERMANENT_PASSWORD},
    )
    assert chg_res.status_code == 200, chg_res.text

    # Log in with permanent password to obtain standard active token
    user_auth = _login(client, username, PERMANENT_PASSWORD)
    return user_id, username, user_auth


# ==============================================================================
# Challenge Suite 1: Role Update Permutations & Email State Machine
# ==============================================================================

class TestRoleUpdatePermutationsAndEmailTriggers:
    """Rigorous empirical testing of role transitions against the IAM email state machine."""

    def test_non_admin_role_permutations_never_trigger_admin_email(self, client):
        """Verify that transitioning between valid non-admin roles NEVER triggers admin promotion email."""
        admin_auth = _login(client, "demo_admin")
        user_id, username, _ = _create_and_activate_user(
            client, admin_auth, roles=["staff"], email=f"{uuid.uuid4().hex[:6]}@bankops.vn"
        )

        with patch("app.api.routes.admin_users.send_admin_role_granted_email", new_callable=AsyncMock) as mock_email:
            mock_email.return_value = EmailSendResult(True, "Sent")

            # Permutation 1: staff -> approver
            r1 = client.put(
                f"/admin/users/{user_id}/roles",
                headers=_idem(admin_auth),
                json={"roles": ["approver"]},
            )
            assert r1.status_code == 200, r1.text
            assert set(r1.json()["user"]["roles"]) == {"approver"}
            assert mock_email.call_count == 0

            # Permutation 2: approver -> inventory_manager
            r2 = client.put(
                f"/admin/users/{user_id}/roles",
                headers=_idem(admin_auth),
                json={"roles": ["inventory_manager"]},
            )
            assert r2.status_code == 200, r2.text
            assert set(r2.json()["user"]["roles"]) == {"inventory_manager"}
            assert mock_email.call_count == 0

            # Permutation 3: inventory_manager -> cash_sim_operator
            r3 = client.put(
                f"/admin/users/{user_id}/roles",
                headers=_idem(admin_auth),
                json={"roles": ["cash_sim_operator"]},
            )
            assert r3.status_code == 200, r3.text
            assert set(r3.json()["user"]["roles"]) == {"cash_sim_operator"}
            assert mock_email.call_count == 0

            # Permutation 4: cash_sim_operator -> auditor
            r4 = client.put(
                f"/admin/users/{user_id}/roles",
                headers=_idem(admin_auth),
                json={"roles": ["auditor"]},
            )
            assert r4.status_code == 200, r4.text
            assert set(r4.json()["user"]["roles"]) == {"auditor"}
            assert mock_email.call_count == 0

            # Permutation 5: auditor -> integration_admin
            r5 = client.put(
                f"/admin/users/{user_id}/roles",
                headers=_idem(admin_auth),
                json={"roles": ["integration_admin"]},
            )
            assert r5.status_code == 200, r5.text
            assert set(r5.json()["user"]["roles"]) == {"integration_admin"}
            assert mock_email.call_count == 0

            # Permutation 6: Multi-role bundle: staff + approver + inventory_manager + auditor
            r6 = client.put(
                f"/admin/users/{user_id}/roles",
                headers=_idem(admin_auth),
                json={"roles": ["staff", "approver", "inventory_manager", "auditor"]},
            )
            assert r6.status_code == 200, r6.text
            assert set(r6.json()["user"]["roles"]) == {"staff", "approver", "inventory_manager", "auditor"}
            assert mock_email.call_count == 0

            # Permutation 7: Strip down back to staff
            r7 = client.put(
                f"/admin/users/{user_id}/roles",
                headers=_idem(admin_auth),
                json={"roles": ["staff"]},
            )
            assert r7.status_code == 200, r7.text
            assert set(r7.json()["user"]["roles"]) == {"staff"}
            assert mock_email.call_count == 0

    def test_regular_to_admin_promotion_triggers_exactly_once(self, client):
        """Promotion triggers once; subsequent admin role modifications do not re-trigger;

        demoting and re-promoting triggers on the second promotion.
        """
        admin_auth = _login(client, "demo_admin")
        user_id, username, _ = _create_and_activate_user(
            client, admin_auth, roles=["staff"], email=f"{uuid.uuid4().hex[:6]}@bankops.vn"
        )

        with patch("app.api.routes.admin_users.send_admin_role_granted_email", new_callable=AsyncMock) as mock_email:
            mock_email.return_value = EmailSendResult(True, "Sent")

            # 1. Promote staff -> admin
            r1 = client.put(
                f"/admin/users/{user_id}/roles",
                headers=_idem(admin_auth),
                json={"roles": ["staff", "admin"]},
            )
            assert r1.status_code == 200, r1.text
            assert "admin" in r1.json()["user"]["roles"]
            assert mock_email.call_count == 1
            call1_kwargs = mock_email.call_args[1]
            assert call1_kwargs["username"] == username
            assert "admin" in call1_kwargs["new_roles"]

            # 2. Add approver to existing admin -> admin + approver
            r2 = client.put(
                f"/admin/users/{user_id}/roles",
                headers=_idem(admin_auth),
                json={"roles": ["admin", "approver"]},
            )
            assert r2.status_code == 200, r2.text
            assert set(r2.json()["user"]["roles"]) == {"admin", "approver"}
            # Must NOT re-trigger
            assert mock_email.call_count == 1

            # 3. Transition from admin -> system_admin (both are admin roles)
            r3 = client.put(
                f"/admin/users/{user_id}/roles",
                headers=_idem(admin_auth),
                json={"roles": ["system_admin"]},
            )
            assert r3.status_code == 200, r3.text
            assert set(r3.json()["user"]["roles"]) == {"system_admin"}
            # Must NOT re-trigger because before already contained an admin role
            assert mock_email.call_count == 1

            # 4. Demote system_admin -> staff
            r4 = client.put(
                f"/admin/users/{user_id}/roles",
                headers=_idem(admin_auth),
                json={"roles": ["staff"]},
            )
            assert r4.status_code == 200, r4.text
            assert set(r4.json()["user"]["roles"]) == {"staff"}
            # Demotion must NOT trigger admin email
            assert mock_email.call_count == 1

            # 5. Re-promote staff -> admin
            r5 = client.put(
                f"/admin/users/{user_id}/roles",
                headers=_idem(admin_auth),
                json={"roles": ["admin"]},
            )
            assert r5.status_code == 200, r5.text
            assert set(r5.json()["user"]["roles"]) == {"admin"}
            # Re-promotion MUST trigger admin email again (call_count == 2)
            assert mock_email.call_count == 2

    def test_user_without_email_promoted_to_admin_completes_without_error(self, client):
        """User without email promoted to admin commits safely and skips email dispatch."""
        admin_auth = _login(client, "demo_admin")
        user_id, username, _ = _create_and_activate_user(
            client, admin_auth, roles=["staff"], email=None
        )

        with patch("app.api.routes.admin_users.send_admin_role_granted_email", new_callable=AsyncMock) as mock_email:
            r = client.put(
                f"/admin/users/{user_id}/roles",
                headers=_idem(admin_auth),
                json={"roles": ["admin"]},
            )
            assert r.status_code == 200, r.text
            assert set(r.json()["user"]["roles"]) == {"admin"}
            mock_email.assert_not_called()

    def test_invalid_role_rejection(self, client):
        """Assigning invalid or empty roles is rejected with 422."""
        admin_auth = _login(client, "demo_admin")
        user_id, _, _ = _create_and_activate_user(client, admin_auth, roles=["staff"])

        # Non-existent role 'cashier'
        r1 = client.put(
            f"/admin/users/{user_id}/roles",
            headers=_idem(admin_auth),
            json={"roles": ["cashier"]},
        )
        assert r1.status_code == 422
        assert "INVALID_ROLES" in r1.text

        # Empty roles list
        r2 = client.put(
            f"/admin/users/{user_id}/roles",
            headers=_idem(admin_auth),
            json={"roles": []},
        )
        assert r2.status_code == 422
        assert "EMPTY_ROLES" in r2.text


# ==============================================================================
# Challenge Suite 2: Token Invalidation via auth_version Mismatch
# ==============================================================================

class TestTokenInvalidationOnAuthVersionMismatch:
    """Rigorous empirical verification of token invalidation when auth_version bumps."""

    def test_old_bearer_token_rejected_with_401_immediately_upon_role_update(self, client):
        """When an admin updates a user's roles, user.auth_version is incremented.

        The user's existing Bearer token must immediately receive HTTP 401 Unauthorized
        ("Phiên đăng nhập đã bị thu hồi.") on /auth/me and protected endpoints.
        """
        admin_auth = _login(client, "demo_admin")
        user_id, username, active_user_auth = _create_and_activate_user(
            client, admin_auth, roles=["staff"]
        )

        # 1. Old token works before role update
        me_before = client.get("/auth/me", headers=active_user_auth)
        assert me_before.status_code == 200, me_before.text
        assert me_before.json()["username"] == username
        assert "staff" in me_before.json()["roles"]
        assert "admin" not in me_before.json()["roles"]

        # 2. Admin updates user roles (bumps auth_version)
        update_res = client.put(
            f"/admin/users/{user_id}/roles",
            headers=_idem(admin_auth),
            json={"roles": ["staff", "approver"]},
        )
        assert update_res.status_code == 200, update_res.text

        # 3. Old token is immediately invalidated -> 401 on /auth/me
        me_after = client.get("/auth/me", headers=active_user_auth)
        assert me_after.status_code == 401, f"Expected 401 on stale token, got: {me_after.status_code} {me_after.text}"
        assert "Phiên đăng nhập đã bị thu hồi." in me_after.text

        # 4. Old token is also rejected on other protected endpoints
        items_after = client.get("/inventory/items", headers=active_user_auth)
        assert items_after.status_code == 401
        assert "Phiên đăng nhập đã bị thu hồi." in items_after.text

        # 5. User logs in again -> gets fresh token with new auth_version
        new_user_auth = _login(client, username, PERMANENT_PASSWORD)

        # 6. Fresh token succeeds and reflects updated roles
        me_fresh = client.get("/auth/me", headers=new_user_auth)
        assert me_fresh.status_code == 200, me_fresh.text
        assert set(me_fresh.json()["roles"]) == {"staff", "approver"}

    def test_rapid_sequential_role_updates_and_auth_version_progression(self, client):
        """Sequential role updates increment auth_version progressively, invalidating intermediate tokens."""
        admin_auth = _login(client, "demo_admin")
        user_id, username, token_v1 = _create_and_activate_user(
            client, admin_auth, roles=["staff"]
        )

        # Token v1 is valid
        assert client.get("/auth/me", headers=token_v1).status_code == 200

        # Update 1: staff -> approver
        r1 = client.put(f"/admin/users/{user_id}/roles", headers=_idem(admin_auth), json={"roles": ["approver"]})
        assert r1.status_code == 200

        # Token v1 now rejected
        assert client.get("/auth/me", headers=token_v1).status_code == 401

        # Token v2 issued
        token_v2 = _login(client, username, PERMANENT_PASSWORD)
        assert client.get("/auth/me", headers=token_v2).status_code == 200

        # Update 2: approver -> inventory_manager
        r2 = client.put(f"/admin/users/{user_id}/roles", headers=_idem(admin_auth), json={"roles": ["inventory_manager"]})
        assert r2.status_code == 200

        # Both Token v1 and Token v2 are now rejected
        assert client.get("/auth/me", headers=token_v1).status_code == 401
        assert client.get("/auth/me", headers=token_v2).status_code == 401

        # Token v3 issued
        token_v3 = _login(client, username, PERMANENT_PASSWORD)
        assert client.get("/auth/me", headers=token_v3).status_code == 200
        assert set(client.get("/auth/me", headers=token_v3).json()["roles"]) == {"inventory_manager"}
