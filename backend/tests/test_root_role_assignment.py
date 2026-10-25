"""A catalog root role can be the only role without weakening IAM controls."""

import asyncio
import uuid

import pytest
from sqlalchemy import delete, select

from app.database import AsyncSessionLocal
from app.models.iam import User, UserRole


def _login(client, username: str = "demo_admin", password: str = "DemoPass123!") -> dict[str, str]:
    response = client.post("/auth/login", data={"username": username, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _headers(auth: dict[str, str]) -> dict[str, str]:
    return {**auth, "Idempotency-Key": str(uuid.uuid4())}


def _create_staff(client, auth: dict[str, str]) -> str:
    response = client.post(
        "/admin/users",
        headers=_headers(auth),
        json={
            "username": f"root_target_{uuid.uuid4().hex[:10]}",
            "display_name": "Root role target",
            "roles": ["staff"],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["user"]["id"]


@pytest.fixture
def root_admin_auth(client):
    admin_auth = _login(client)
    user_id = uuid.UUID(client.get("/me", headers=admin_auth).json()["id"])

    async def grant_root() -> set[str]:
        async with AsyncSessionLocal() as db:
            original = set((await db.execute(
                select(UserRole.role_code).where(UserRole.user_id == user_id)
            )).scalars().all())
            if "root_admin" not in original:
                db.add(UserRole(user_id=user_id, role_code="root_admin"))
            user = await db.get(User, user_id)
            user.auth_version += 1
            await db.commit()
            return original

    original_roles = asyncio.run(grant_root())
    try:
        yield user_id, _login(client)
    finally:
        async def restore_roles() -> None:
            async with AsyncSessionLocal() as db:
                await db.execute(delete(UserRole).where(UserRole.user_id == user_id))
                await db.flush()
                db.add_all(UserRole(user_id=user_id, role_code=role) for role in original_roles)
                user = await db.get(User, user_id)
                user.auth_version += 1
                await db.commit()

        asyncio.run(restore_roles())


def test_regular_admin_cannot_grant_root_to_existing_user(client):
    auth = _login(client)
    target_id = _create_staff(client, auth)

    response = client.put(
        f"/admin/users/{target_id}/roles",
        headers=_headers(auth),
        json={"roles": ["root_admin"]},
    )

    assert response.status_code == 403, response.text
    detail = client.get(f"/admin/users/{target_id}", headers=auth).json()["user"]
    assert detail["roles"] == ["staff"]


def test_regular_admin_cannot_self_grant_root(client):
    auth = _login(client)
    user_id = client.get("/me", headers=auth).json()["id"]

    response = client.put(
        f"/admin/users/{user_id}/roles",
        headers=_headers(auth),
        json={"roles": ["admin", "root_admin"]},
    )

    assert response.status_code == 403, response.text
    assert "root_admin" not in client.get("/me", headers=auth).json()["roles"]


def test_regular_admin_cannot_create_root_user(client):
    auth = _login(client)
    response = client.post(
        "/admin/users",
        headers=_headers(auth),
        json={
            "username": f"root_create_{uuid.uuid4().hex[:10]}",
            "display_name": "Unauthorized root target",
            "roles": ["root_admin"],
        },
    )

    assert response.status_code == 403, response.text
    assert "ROOT_ROLE_FORBIDDEN" in response.text


def test_root_admin_can_replace_existing_user_roles_with_root_only(client, root_admin_auth):
    _, auth = root_admin_auth
    target_id = _create_staff(client, auth)

    for _ in range(2):
        response = client.put(
            f"/admin/users/{target_id}/roles",
            headers=_headers(auth),
            json={"roles": ["root_admin"]},
        )
        assert response.status_code == 200, response.text
        assert response.json()["user"]["roles"] == ["root_admin"]


def test_root_admin_can_create_root_only_user(client, root_admin_auth):
    _, auth = root_admin_auth
    response = client.post(
        "/admin/users",
        headers=_headers(auth),
        json={
            "username": f"root_create_{uuid.uuid4().hex[:10]}",
            "display_name": "Authorized root target",
            "roles": ["root_admin"],
        },
    )

    assert response.status_code == 201, response.text
    assert response.json()["user"]["roles"] == ["root_admin"]


def test_root_admin_can_keep_only_root_when_editing_own_roles(client, root_admin_auth):
    user_id, auth = root_admin_auth
    before_locations = client.get("/inventory/locations", headers=auth)
    assert before_locations.status_code == 200, before_locations.text

    response = client.put(
        f"/admin/users/{user_id}/roles",
        headers=_headers(auth),
        json={"roles": ["root_admin"]},
    )

    assert response.status_code == 200, response.text
    assert response.json()["user"]["roles"] == ["root_admin"]
    assert client.get("/admin/users", headers=auth).status_code == 401
    fresh_auth = _login(client)
    profile = client.get("/me", headers=fresh_auth).json()
    assert "iam:root" in profile["capabilities"]
    assert "inventory:view_balances" in profile["capabilities"]
    assert client.get("/admin/users", headers=fresh_auth).status_code == 200
    after_locations = client.get("/inventory/locations", headers=fresh_auth)
    assert after_locations.status_code == 200, after_locations.text
    assert after_locations.json() == before_locations.json()


def test_regular_admin_cannot_remove_another_users_root_role(client):
    auth = _login(client)
    target_id = _create_staff(client, auth)

    async def grant_root_to_target() -> None:
        async with AsyncSessionLocal() as db:
            db.add(UserRole(user_id=uuid.UUID(target_id), role_code="root_admin"))
            await db.commit()

    asyncio.run(grant_root_to_target())
    response = client.put(
        f"/admin/users/{target_id}/roles",
        headers=_headers(auth),
        json={"roles": ["staff"]},
    )

    assert response.status_code == 403, response.text
    detail = client.get(f"/admin/users/{target_id}", headers=auth).json()["user"]
    assert set(detail["roles"]) == {"staff", "root_admin"}


def test_catalog_role_can_be_assigned_as_only_role(client):
    auth = _login(client)
    target_id = _create_staff(client, auth)

    response = client.put(
        f"/admin/users/{target_id}/roles",
        headers=_headers(auth),
        json={"roles": ["inventory_manager"]},
    )

    assert response.status_code == 200, response.text
    assert response.json()["user"]["roles"] == ["inventory_manager"]


def test_unknown_role_is_rejected_instead_of_creating_user_without_access(client):
    auth = _login(client)
    response = client.post(
        "/admin/users",
        headers=_headers(auth),
        json={
            "username": f"invalid_role_{uuid.uuid4().hex[:10]}",
            "display_name": "Invalid role target",
            "roles": ["teller"],
        },
    )

    assert response.status_code == 422, response.text
    assert "INVALID_ROLES" in response.text


def test_admin_cannot_expand_own_data_scope(client):
    auth = _login(client)
    user_id = client.get("/me", headers=auth).json()["id"]
    branches = client.get("/admin/branches", headers=auth).json()["branches"]

    response = client.put(
        f"/admin/users/{user_id}/scopes",
        headers=_headers(auth),
        json={"scopes": [{"branch_id": branches[0]["id"]}]},
    )

    assert response.status_code == 403, response.text
    assert "CANNOT_CHANGE_OWN_SCOPES" in response.text
