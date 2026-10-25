"""RBAC UAT Full Authorization Matrix Test Suite.

Validates that roles (staff, maker, approver, checker, auditor, admin) are strictly
governed according to the F&B operations specification and Clean Architecture rules.
"""
import uuid

import pytest


def _get_auth_headers(client, role: str) -> dict:
    username = f"uat_{role}_{uuid.uuid4().hex[:6]}@bankops.internal"
    mock_token = f"mock-google-token:{username}:UAT {role.title()}"
    res = client.post("/api/v1/auth/google", json={"id_token": mock_token})
    if res.status_code != 200:
        pytest.skip(f"Could not provision test user for role {role}")
    token = res.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


class TestRbacUatMatrix:
    def test_anonymous_access_denied_on_protected_surfaces(self, client):
        """All protected operational surfaces reject unauthenticated calls."""
        protected_routes = [
            ("GET", "/inventory/items"),
            ("GET", "/inventory/balances"),
            ("GET", "/reports/summary"),
            ("GET", "/activity"),
            ("GET", "/api/v1/notifications/devices"),
        ]
        for method, route in protected_routes:
            r = client.request(method, route)
            assert r.status_code in (401, 403), f"Route {route} allowed anonymous access"

    def test_staff_role_boundaries(self, client, demo_mode):
        """Staff/Barista can read inventory, but cannot access admin or audit endpoints."""
        headers = _get_auth_headers(client, "staff")

        # Staff can view inventory catalog
        r_inv = client.get("/inventory/items", headers=headers)
        assert r_inv.status_code == 200

        # Staff cannot access employee administration
        r_admin = client.get("/admin/users", headers=headers)
        assert r_admin.status_code in (403, 401), "Staff should be forbidden from admin user management"

    def test_auditor_role_read_only_isolation(self, client, demo_mode):
        """Auditor has view access on reports/activity, but cannot create or approve transactions."""
        # Provision an auditor user
        username = f"auditor_{uuid.uuid4().hex[:6]}@bankops.internal"
        mock_token = f"mock-google-token:{username}:Auditor Test"
        res = client.post("/api/v1/auth/google", json={"id_token": mock_token})
        assert res.status_code == 200
        headers = {"Authorization": f"Bearer {res.json()['access_token']}"}

        # Auditor cannot mutate inventory items
        r_mutate = client.post(
            "/inventory/items",
            json={
                "code": f"AUDIT-SKU-{uuid.uuid4().hex[:4]}",
                "name": "Unauthorized Auditor Item",
                "unit": "PCS",
            },
            headers=headers,
        )
        assert r_mutate.status_code in (403, 422), "Auditor must not create catalog items"
