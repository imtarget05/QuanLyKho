"""Tests for IAM Admin, Employee Provisioning, Scopes, and Invariants (Phase 1).

Verifies:
  - Non-admin receives 403 on all /admin/users/* endpoints
  - Public registration /auth/register is forbidden (403)
  - Admin creates employee with temporary password (must_change_password=True)
  - Admin creates employee with invite token
  - First-time login password change via /auth/change-initial-password
  - Invariant: Admin cannot self-lock
  - Invariant: Admin cannot self-escalate roles
  - Immediate token invalidation via auth_version increment on lock or session revocation
"""

import uuid

DEMO_PASSWORD = "DemoPass123!"


def _login(client, username: str, password: str = DEMO_PASSWORD) -> dict[str, str]:
    r = client.post("/auth/login", data={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _idem(headers: dict[str, str]) -> dict[str, str]:
    return {**headers, "Idempotency-Key": str(uuid.uuid4())}


class TestIamAdmin:
    def test_public_registration_is_disabled(self, client):
        r = client.post(
            "/auth/register",
            json={"username": "new_user", "password": "Password123!", "full_name": "Test User"},
        )
        assert r.status_code == 403
        data = r.json()
        assert "PUBLIC_REGISTRATION_DISABLED" in str(data)

    def test_non_admin_forbidden_on_admin_endpoints(self, client):
        maker_auth = _login(client, "demo_maker")
        r = client.get("/admin/users", headers=maker_auth)
        assert r.status_code == 403

        r = client.post(
            "/admin/users",
            headers=_idem(maker_auth),
            json={"username": "test_emp", "full_name": "Test Emp", "onboarding_method": "temporary_password"},
        )
        assert r.status_code == 403

    def test_admin_list_branches_and_roles(self, client):
        admin_auth = _login(client, "demo_admin")
        r = client.get("/admin/branches", headers=admin_auth)
        assert r.status_code == 200
        assert "branches" in r.json()

        r = client.get("/admin/roles", headers=admin_auth)
        assert r.status_code == 200
        assert "roles" in r.json()

    def test_branch_scoped_user_cannot_list_other_branch_inventory(self, client):
        """A user assigned to an empty branch must not receive HO inventory rows."""
        admin_auth = _login(client, "demo_admin")
        branches = client.get("/admin/branches", headers=admin_auth).json()["branches"]
        other_branch = next(branch for branch in branches if branch["code"] == "CN_BEN_THANH")
        username = f"branch_staff_{uuid.uuid4().hex[:6]}"
        created = client.post(
            "/admin/users",
            headers=_idem(admin_auth),
            json={
                "username": username,
                "display_name": "Nhân viên chi nhánh tách biệt",
                "branch_id": other_branch["id"],
                "roles": ["approver"],
            },
        )
        assert created.status_code == 201, created.text

        ho_balance = client.get("/inventory/balances", headers=admin_auth).json()["balances"][0]
        asset = client.post(
            "/inventory/assets",
            headers=_idem(admin_auth),
            json={
                "serial": f"BRANCH-SCOPE-{uuid.uuid4().hex[:8]}",
                "item_id": ho_balance["item_id"],
                "location_id": ho_balance["location_id"],
            },
        )
        assert asset.status_code == 201, asset.text

        ho_request = client.post(
            "/inventory/requests",
            headers=_idem(admin_auth),
            json={
                "kind": "receipt",
                "dest_id": ho_balance["location_id"],
                "lines": [{"item_id": ho_balance["item_id"], "quantity": "1"}],
            },
        )
        assert ho_request.status_code == 201, ho_request.text

        temp_password = created.json()["temporary_password"]
        scoped_auth = _login(client, username, temp_password)
        # S13 — user cấp mật khẩu tạm thời phải đổi mật khẩu trước khi dùng
        # nghiệp vụ; đổi xong đăng nhập lại để tiếp tục kiểm tra branch scope.
        changed = client.post(
            "/auth/change-initial-password",
            headers=_idem(scoped_auth),
            json={
                "current_password": temp_password,
                "new_password": "BranchScopedPass123!",
            },
        )
        assert changed.status_code == 200, changed.text
        scoped_auth = _login(client, username, "BranchScopedPass123!")
        balances = client.get("/inventory/balances", headers=scoped_auth)

        assert balances.status_code == 200, balances.text
        assert balances.json()["balances"] == []

        locations = client.get("/inventory/locations", headers=scoped_auth)
        assert locations.status_code == 200, locations.text
        assert locations.json()["locations"] == []

        assets = client.get("/inventory/assets", headers=scoped_auth)
        assert assets.status_code == 200, assets.text
        assert assets.json()["assets"] == []

        requests = client.get("/inventory/requests", headers=scoped_auth)
        assert requests.status_code == 200, requests.text
        assert requests.json()["requests"] == []

        request_detail = client.get(
            f"/inventory/requests/{ho_request.json()['id']}", headers=scoped_auth
        )
        assert request_detail.status_code in (403, 404), request_detail.text

        write = client.post(
            "/inventory/assets",
            headers=_idem(scoped_auth),
            json={
                "serial": f"CROSS-BRANCH-{uuid.uuid4().hex[:8]}",
                "item_id": ho_balance["item_id"],
                "location_id": ho_balance["location_id"],
            },
        )
        assert write.status_code in (403, 404), write.text

        cross_branch_receipt = client.post(
            "/inventory/requests",
            headers=_idem(scoped_auth),
            json={
                "kind": "receipt",
                "dest_id": ho_balance["location_id"],
                "lines": [{"item_id": ho_balance["item_id"], "quantity": "1"}],
            },
        )
        assert cross_branch_receipt.status_code in (403, 404), cross_branch_receipt.text

    def test_admin_create_user_with_temp_password_and_first_login_flow(self, client):
        admin_auth = _login(client, "demo_admin")
        username = f"emp_temp_{uuid.uuid4().hex[:6]}"
        r = client.post(
            "/admin/users",
            headers=_idem(admin_auth),
            json={
                "username": username,
                "email": f"{username}@bankops.vn",
                "display_name": "Nhân viên Mới",
                "roles": ["staff"],
                "onboarding_method": "temporary_password",
            },
        )
        assert r.status_code == 201, r.text
        data = r.json()
        temp_pass = data.get("temporary_password")
        assert temp_pass is not None
        assert data["user"]["must_change_password"] is True

        # Login with temp pass succeeds and reports must_change_password
        login_res = client.post("/auth/login", data={"username": username, "password": temp_pass})
        assert login_res.status_code == 200
        login_data = login_res.json()
        assert login_data.get("user", {}).get("must_change_password") is True or login_data.get("must_change_password") is True
        emp_token = {"Authorization": f"Bearer {login_data['access_token']}"}

        # Change initial password
        new_pass = "MyNewSecretPass123!"
        change_res = client.post(
            "/auth/change-initial-password",
            headers=_idem(emp_token),
            json={"current_password": temp_pass, "new_password": new_pass},
        )
        assert change_res.status_code == 200
        assert change_res.json()["must_change_password"] is False

        # Login with old pass fails, new pass succeeds
        assert client.post("/auth/login", data={"username": username, "password": temp_pass}).status_code == 401
        assert client.post("/auth/login", data={"username": username, "password": new_pass}).status_code == 200

    def test_admin_create_user_with_invite_token(self, client):
        admin_auth = _login(client, "demo_admin")
        username = f"emp_inv_{uuid.uuid4().hex[:6]}"
        r = client.post(
            "/admin/users",
            headers=_idem(admin_auth),
            json={
                "username": username,
                "email": f"{username}@bankops.vn",
                "display_name": "Nhân viên Mời",
                "roles": ["staff"],
                "onboarding_method": "invite_email",
            },
        )
        assert r.status_code == 201, r.text
        data = r.json()
        invite_token = data.get("invite_token")
        assert invite_token is not None

        # Accept invite
        init_pass = "SecureInitPassword123!"
        accept_res = client.post(
            "/auth/accept-invite",
            json={"invite_token": invite_token, "new_password": init_pass},
        )
        assert accept_res.status_code == 200

        # Login works now
        login_res = client.post("/auth/login", data={"username": username, "password": init_pass})
        assert login_res.status_code == 200

    def test_invite_email_requires_real_email(self, client):
        """Invite qua email BẮT BUỘC email thật có format hợp lệ (yêu cầu khách hàng)."""
        admin_auth = _login(client, "demo_admin")

        # Thiếu email -> 422 EMAIL_REQUIRED
        r = client.post(
            "/admin/users",
            headers=_idem(admin_auth),
            json={
                "username": f"emp_noemail_{uuid.uuid4().hex[:6]}",
                "display_name": "Nhân Viên Không Email",
                "onboarding_method": "invite_email",
            },
        )
        assert r.status_code == 422, r.text
        assert "EMAIL_REQUIRED" in str(r.json())

        # Email sai format -> 422 EMAIL_INVALID
        r = client.post(
            "/admin/users",
            headers=_idem(admin_auth),
            json={
                "username": f"emp_bademail_{uuid.uuid4().hex[:6]}",
                "email": "khong-phai-email",
                "display_name": "Nhân Viên Email Sai",
                "onboarding_method": "invite_email",
            },
        )
        assert r.status_code == 422, r.text
        assert "EMAIL_INVALID" in str(r.json())

    def test_resend_invite_requires_valid_email(self, client):
        """Gửi lại lời mời cho user chưa có email thật -> 422 (không gửi invite mò)."""
        admin_auth = _login(client, "demo_admin")
        username = f"emp_nores_{uuid.uuid4().hex[:6]}"
        r = client.post(
            "/admin/users",
            headers=_idem(admin_auth),
            json={"username": username, "display_name": "Nhân Viên Không Email 2"},
        )
        assert r.status_code == 201, r.text
        user_id = r.json()["user"]["id"]

        r = client.post(f"/admin/users/{user_id}/invite", headers=_idem(admin_auth))
        assert r.status_code == 422, r.text
        assert "EMAIL_REQUIRED" in str(r.json())

    def test_admin_cannot_self_lock(self, client):
        admin_auth = _login(client, "demo_admin")
        me = client.get("/me", headers=admin_auth).json()
        my_id = me["id"]

        r = client.post(
            f"/admin/users/{my_id}/status",
            headers=_idem(admin_auth),
            json={"status": "locked", "reason": "Self locking attempt"},
        )
        assert r.status_code in (400, 409, 422)
        assert "CANNOT_LOCK_SELF" in str(r.json())

    def test_admin_cannot_self_escalate_roles(self, client):
        admin_auth = _login(client, "demo_admin")
        me = client.get("/me", headers=admin_auth).json()
        my_id = me["id"]

        r = client.put(
            f"/admin/users/{my_id}/roles",
            headers=_idem(admin_auth),
            json={"role_codes": ["system_admin", "super_god_mode"]},
        )
        assert r.status_code in (400, 403, 409, 422)

    def test_instant_session_revocation_invalidates_token(self, client):
        # 1. Login demo_maker
        maker_auth = _login(client, "demo_maker")
        # Verify token works
        assert client.get("/inventory/items", headers=maker_auth).status_code == 200

        # 2. Admin revokes maker's sessions
        admin_auth = _login(client, "demo_admin")
        # find maker id
        users = client.get("/admin/users?search=demo_maker", headers=admin_auth).json()["users"]
        maker_id = users[0]["id"]

        revoke_res = client.post(f"/admin/users/{maker_id}/sessions/revoke", headers=_idem(admin_auth))
        assert revoke_res.status_code == 200

        # 3. Old maker token is immediately rejected with 401
        check_res = client.get("/inventory/items", headers=maker_auth)
        assert check_res.status_code == 401
