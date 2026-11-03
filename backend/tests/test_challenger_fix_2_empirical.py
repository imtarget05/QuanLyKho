"""Challenger Fix 2 Empirical Verification & Adversarial Stress Suite.

Authored by Challenger fix_2.
Empirically stress-tests and verifies:
1. Access and refresh token invalidation on role update (`auth_version` mismatch).
2. Immediate privilege revocation upon role demotion across administrative endpoints.
3. Rapid successive role updates and monotonic `auth_version` progression.
4. Idempotent role update (same role assignment) session invalidation guarantee.
5. Forged/tampered `auth_version` token payload rejection.
6. Admin self-modification boundary invariants (CANNOT_ESCALATE_SELF, CANNOT_DEMOTE_SELF).
"""

from __future__ import annotations

import uuid
from datetime import timedelta

from app.api.routes.auth_utils import create_access_token

DEMO_PASSWORD = "DemoPass123!"
PERMANENT_PASSWORD = "ChallengerTestPass123!"


def _login(client, username: str, password: str = DEMO_PASSWORD) -> tuple[dict[str, str], str]:
    """Login helper returning (auth_headers, refresh_token)."""
    r = client.post("/auth/login", data={"username": username, "password": password})
    assert r.status_code == 200, f"Login failed for {username}: {r.text}"
    data = r.json()
    return {"Authorization": f"Bearer {data['access_token']}"}, data["refresh_token"]


def _idem(headers: dict[str, str]) -> dict[str, str]:
    return {**headers, "Idempotency-Key": str(uuid.uuid4())}


def _create_and_activate_user(
    client,
    admin_auth: dict[str, str],
    roles: list[str],
    email: str | None = None,
) -> tuple[str, str, dict[str, str], str]:
    """Helper to create a user and activate their password to obtain valid initial tokens."""
    username = f"ch_fix2_{uuid.uuid4().hex[:8]}"
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

    admin_auth, _ = _login(client, "demo_admin")
    create_res = client.post("/admin/users", headers=_idem(admin_auth), json=payload)
    assert create_res.status_code == 201, create_res.text
    user_id = create_res.json()["user"]["id"]
    temp_pass = create_res.json().get("temporary_password") or initial_password

    # Log in with temporary password and change to permanent password
    temp_auth, _ = _login(client, username, temp_pass)
    chg_res = client.post(
        "/auth/change-initial-password",
        headers=_idem(temp_auth),
        json={"current_password": temp_pass, "new_password": PERMANENT_PASSWORD},
    )
    assert chg_res.status_code == 200, chg_res.text

    # Log in with permanent password to obtain standard active token
    user_auth, refresh_token = _login(client, username, PERMANENT_PASSWORD)
    return user_id, username, user_auth, refresh_token


class TestChallengerFix2AuthVersionEmpirical:
    """Empirical adversarial verification of role updates and auth_version token invalidation."""

    def test_access_and_refresh_tokens_both_invalidated_on_role_update(self, client):
        """When admin updates user roles, auth_version is incremented.

        Both access token AND refresh token must be rejected with HTTP 401 immediately.
        """
        admin_auth, _ = _login(client, "demo_admin")
        user_id, username, old_auth, old_refresh = _create_and_activate_user(
            client, admin_auth, roles=["staff"]
        )

        # 1. Tokens work initially
        me_res = client.get("/auth/me", headers=old_auth)
        assert me_res.status_code == 200
        assert me_res.json()["username"] == username

        items_res = client.get("/inventory/items", headers=old_auth)
        assert items_res.status_code == 200

        # 2. Admin updates roles to include approver
        admin_auth, _ = _login(client, "demo_admin")
        up_res = client.put(
            f"/admin/users/{user_id}/roles",
            headers=_idem(admin_auth),
            json={"roles": ["staff", "approver"]},
        )
        assert up_res.status_code == 200, up_res.text

        # 3. Old access token rejected on /auth/me with 401
        me_after = client.get("/auth/me", headers=old_auth)
        assert me_after.status_code == 401
        assert "Phiên đăng nhập đã bị thu hồi." in me_after.text

        # 4. Old access token rejected on /inventory/items with 401
        items_after = client.get("/inventory/items", headers=old_auth)
        assert items_after.status_code == 401
        assert "Phiên đăng nhập đã bị thu hồi." in items_after.text

        # 5. Old refresh token rejected on /auth/refresh with 401
        ref_res = client.post("/auth/refresh", json={"refresh_token": old_refresh})
        assert ref_res.status_code == 401, f"Expected 401 on stale refresh token, got: {ref_res.status_code} {ref_res.text}"

        # 6. Fresh login works and grants approver role
        new_auth, new_refresh = _login(client, username, PERMANENT_PASSWORD)
        me_fresh = client.get("/auth/me", headers=new_auth)
        assert me_fresh.status_code == 200
        assert set(me_fresh.json()["roles"]) == {"staff", "approver"}

        # 7. Fresh refresh token succeeds
        ref_fresh = client.post("/auth/refresh", json={"refresh_token": new_refresh})
        assert ref_fresh.status_code == 200
        assert "access_token" in ref_fresh.json()

    def test_role_demotion_immediately_revokes_elevated_privileges(self, client):
        """Demoting an admin to regular staff immediately invalidates administrative token.

        Subsequent re-login reflects reduced capabilities (admin endpoints return 403).
        """
        admin_auth, _ = _login(client, "demo_admin")
        user_id, username, old_auth, _ = _create_and_activate_user(
            client, admin_auth, roles=["staff", "admin"]
        )

        # 1. User has admin capabilities with initial token
        admin_auth_user, _ = _login(client, username, PERMANENT_PASSWORD)
        adm_check = client.get(f"/admin/users/{user_id}", headers=admin_auth_user)
        assert adm_check.status_code == 200, adm_check.text

        # 2. Main admin demotes user to staff only
        admin_auth, _ = _login(client, "demo_admin")
        demote_res = client.put(
            f"/admin/users/{user_id}/roles",
            headers=_idem(admin_auth),
            json={"roles": ["staff"]},
        )
        assert demote_res.status_code == 200, demote_res.text

        # 3. Former admin token receives 401 immediately
        adm_after = client.get(f"/admin/users/{user_id}", headers=admin_auth_user)
        assert adm_after.status_code == 401

        # 4. User logs in with fresh token -> access to admin endpoint is now 403 Forbidden
        staff_auth, _ = _login(client, username, PERMANENT_PASSWORD)
        adm_fresh = client.get(f"/admin/users/{user_id}", headers=staff_auth)
        assert adm_fresh.status_code == 403, f"Expected 403 Forbidden, got: {adm_fresh.status_code} {adm_fresh.text}"

    def test_rapid_successive_role_updates_and_auth_version_monotonicity(self, client):
        """Verify auth_version progression over 5 successive role modifications.

        Tokens from versions v1, v2, v3, v4 must all remain revoked.
        """
        admin_auth, _ = _login(client, "demo_admin")
        user_id, username, token_v1, _ = _create_and_activate_user(
            client, admin_auth, roles=["staff"]
        )

        tokens = [token_v1]
        role_sequence = [
            ["approver"],
            ["inventory_manager"],
            ["auditor"],
            ["staff"],
        ]

        for roles in role_sequence:
            admin_auth, _ = _login(client, "demo_admin")
            up = client.put(
                f"/admin/users/{user_id}/roles",
                headers=_idem(admin_auth),
                json={"roles": roles},
            )
            assert up.status_code == 200
            tok, _ = _login(client, username, PERMANENT_PASSWORD)
            tokens.append(tok)

        # tokens contains [v1, v2, v3, v4, v5]
        # v1 through v4 must be rejected with 401
        for idx, old_tok in enumerate(tokens[:-1], start=1):
            res = client.get("/auth/me", headers=old_tok)
            assert res.status_code == 401, f"Token v{idx} was not rejected! Status: {res.status_code}"

        # v5 must be valid with final role ["staff"]
        v5_res = client.get("/auth/me", headers=tokens[-1])
        assert v5_res.status_code == 200
        assert set(v5_res.json()["roles"]) == {"staff"}

    def test_idempotent_role_update_still_increments_auth_version(self, client):
        """Updating user roles with the identical set of roles still bumps auth_version,

        guaranteeing intentional session invalidation when admin re-asserts permissions.
        """
        admin_auth, _ = _login(client, "demo_admin")
        user_id, username, old_auth, _ = _create_and_activate_user(
            client, admin_auth, roles=["staff"]
        )

        assert client.get("/auth/me", headers=old_auth).status_code == 200

        # Admin assigns identical role ["staff"]
        admin_auth, _ = _login(client, "demo_admin")
        same_roles_res = client.put(
            f"/admin/users/{user_id}/roles",
            headers=_idem(admin_auth),
            json={"roles": ["staff"]},
        )
        assert same_roles_res.status_code == 200

        # Old token MUST be invalidated
        assert client.get("/auth/me", headers=old_auth).status_code == 401

        # New login works
        fresh_auth, _ = _login(client, username, PERMANENT_PASSWORD)
        assert client.get("/auth/me", headers=fresh_auth).status_code == 200

    def test_forged_or_tampered_auth_version_token_rejected(self, client):
        """A validly signed JWT with a future or forged auth_version must be rejected with 401."""
        admin_auth, _ = _login(client, "demo_admin")
        user_id, username, _, _ = _create_and_activate_user(
            client, admin_auth, roles=["staff"]
        )

        # Forge token with future auth_version = 9999
        forged_token = create_access_token(
            {
                "sub": user_id,
                "username": username,
                "roles": ["staff"],
                "caps": ["inventory:read"],
                "auth_version": 9999,
            },
            timedelta(minutes=30),
        )

        res = client.get("/auth/me", headers={"Authorization": f"Bearer {forged_token}"})
        assert res.status_code == 401
        assert "Phiên đăng nhập đã bị thu hồi." in res.text

    def test_admin_self_escalation_and_demotion_prevention(self, client):
        """An admin user cannot self-escalate or self-demote."""
        admin_auth, _ = _login(client, "demo_admin")
        emp_id, emp_name, _, _ = _create_and_activate_user(
            client, admin_auth, roles=["admin", "staff"]
        )

        emp_auth, _ = _login(client, emp_name, PERMANENT_PASSWORD)

        # 1. Attempt self-escalation: admin tries to add approver role to self
        esc_res = client.put(
            f"/admin/users/{emp_id}/roles",
            headers=_idem(emp_auth),
            json={"roles": ["admin", "staff", "approver"]},
        )
        assert esc_res.status_code == 403
        assert "CANNOT_ESCALATE_SELF" in esc_res.text

        # 2. Attempt self-demotion: admin tries to drop admin role and keep staff only
        dem_res = client.put(
            f"/admin/users/{emp_id}/roles",
            headers=_idem(emp_auth),
            json={"roles": ["staff"]},
        )
        assert dem_res.status_code == 400
        assert "CANNOT_DEMOTE_SELF" in dem_res.text

        # Token is still valid because invalid self-modification aborted before commit
        emp_me = client.get("/auth/me", headers=emp_auth)
        assert emp_me.status_code == 200
