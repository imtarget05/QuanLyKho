"""Milk-tea inventory role/action and branch-scope acceptance matrix.

This exercises the HTTP boundary with real seeded capabilities. The generated
branch and user are isolated from demo accounts and cannot see the demo branch.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import date, timedelta

import pytest

from app.api.routes.auth_utils import get_password_hash
from app.database import AsyncSessionLocal
from app.models.iam import Branch, User, UserRole
from app.models.inventory import Location

DEMO_PASSWORD = "DemoPass123!"
LOCATION_BAR = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbb1"


def _login(client, username: str, password: str = DEMO_PASSWORD) -> dict[str, str]:
    response = client.post("/auth/login", data={"username": username, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _write_headers(headers: dict[str, str]) -> dict[str, str]:
    return {**headers, "Idempotency-Key": str(uuid.uuid4())}


def _create_request(client, headers: dict[str, str], location_id: str = LOCATION_BAR):
    return client.post(
        "/inventory/requests",
        headers=_write_headers(headers),
        json={"kind": "issue", "source_id": location_id, "lines": []},
    )


def _page_ids(client, headers: dict[str, str]) -> set[str]:
    ids: set[str] = set()
    cursor = None
    while True:
        response = client.get(
            "/inventory/requests",
            headers=headers,
            params={"limit": 100, **({"cursor": cursor} if cursor else {})},
        )
        assert response.status_code == 200, response.text
        page = response.json()
        ids.update(row["id"] for row in page["requests"])
        cursor = page.get("next_cursor")
        if not cursor:
            return ids


@pytest.fixture
def isolated_manager():
    """Create a manager and location in a branch unrelated to BAR-MAIN."""
    branch_id = uuid.uuid4()
    user_id = uuid.uuid4()
    location_id = uuid.uuid4()
    username = f"uat_manager_{uuid.uuid4().hex[:12]}"
    password = f"Uat-{uuid.uuid4().hex}!"

    async def _insert() -> None:
        async with AsyncSessionLocal() as db:
            db.add(Branch(id=branch_id, code=f"UAT-{uuid.uuid4().hex[:10]}", name="UAT isolated branch"))
            db.add(User(
                id=user_id,
                username=username,
                password_hash=get_password_hash(password),
                status="active",
                display_name_demo="UAT manager",
                branch_id=branch_id,
            ))
            db.add(UserRole(user_id=user_id, role_code="inventory_manager"))
            db.add(Location(
                id=location_id,
                code=f"UAT-{uuid.uuid4().hex[:10]}",
                name="UAT isolated location",
                active=True,
                branch_id=branch_id,
            ))
            await db.commit()

    asyncio.run(_insert())
    return username, password, str(location_id)


def _role_only_user(role: str) -> tuple[str, str]:
    user_id = uuid.uuid4()
    username = f"uat_{role}_{uuid.uuid4().hex[:12]}"
    password = f"Uat-{uuid.uuid4().hex}!"

    async def _insert() -> None:
        async with AsyncSessionLocal() as db:
            db.add(User(
                id=user_id,
                username=username,
                password_hash=get_password_hash(password),
                status="active",
                display_name_demo=f"UAT {role} only",
            ))
            db.add(UserRole(user_id=user_id, role_code=role))
            await db.commit()

    asyncio.run(_insert())
    return username, password


@pytest.fixture
def admin_only(client):
    """Admin must not gain create permission only through a second staff role."""
    return _role_only_user("admin")


@pytest.fixture
def approver_only(client):
    return _role_only_user("approver")


def test_role_matrix_create_and_auditor_read_without_write(client, isolated_manager, approver_only):
    """Staff and manager create; auditor reads another user's request only."""
    maker = _login(client, "demo_maker")
    checker = _login(client, *approver_only)
    auditor = _login(client, "demo_auditor")
    manager = _login(client, isolated_manager[0], isolated_manager[1])

    created = _create_request(client, maker)
    assert created.status_code == 201, created.text
    req_id = created.json()["id"]

    manager_created = _create_request(client, manager, isolated_manager[2])
    assert manager_created.status_code == 201, manager_created.text

    # Approver is a checker role, not a creator; auditor is read-only.
    assert _create_request(client, checker).status_code == 403
    assert _create_request(client, auditor).status_code == 403
    assert req_id in _page_ids(client, auditor)
    assert client.get(f"/inventory/requests/{req_id}", headers=auditor).status_code == 200


def test_admin_only_role_can_create_request(client, admin_only):
    admin = _login(client, *admin_only)
    created = _create_request(client, admin)
    assert created.status_code == 201, created.text


def test_branch_scope_denies_manager_cross_branch_read_write_and_approval(client, isolated_manager):
    maker = _login(client, "demo_maker")
    manager = _login(client, isolated_manager[0], isolated_manager[1])
    created = _create_request(client, maker)
    assert created.status_code == 201, created.text
    req_id = created.json()["id"]

    assert _create_request(client, manager, LOCATION_BAR).status_code == 404
    assert client.get(f"/inventory/requests/{req_id}", headers=manager).status_code == 404
    assert req_id not in _page_ids(client, manager)
    denied = client.post(
        f"/inventory/requests/{req_id}/approve",
        headers=_write_headers(manager),
    )
    assert denied.status_code == 404


def test_admin_cannot_approve_own_submitted_request(client, admin_only):
    """Maker != checker still applies when the maker has approval capability."""
    admin = _login(client, *admin_only)
    created = _create_request(client, admin)
    assert created.status_code == 201, created.text
    req_id = created.json()["id"]
    submitted = client.post(
        f"/inventory/requests/{req_id}/submit",
        headers=_write_headers(admin),
    )
    assert submitted.status_code == 200, submitted.text
    denied = client.post(
        f"/inventory/requests/{req_id}/approve",
        headers=_write_headers(admin),
    )
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "SELF_APPROVAL_FORBIDDEN"


def test_checker_approves_staff_receipt_while_auditor_cannot(client):
    maker = _login(client, "demo_maker")
    checker = _login(client, "demo_checker")
    auditor = _login(client, "demo_auditor")
    items = client.get("/inventory/items", headers=maker)
    assert items.status_code == 200, items.text
    item_id = items.json()["items"][0]["id"]
    created = client.post(
        "/inventory/requests",
        headers=_write_headers(maker),
        json={
            "kind": "receipt",
            "dest_id": LOCATION_BAR,
            "supplier": "RBAC UAT supplier",
            "lines": [{
                "item_id": item_id,
                "quantity": "1",
                "lot_no": f"RBAC-{uuid.uuid4().hex[:12]}",
                "expiry_date": (date.today() + timedelta(days=30)).isoformat(),
            }],
        },
    )
    assert created.status_code == 201, created.text
    request_id = created.json()["id"]
    submitted = client.post(
        f"/inventory/requests/{request_id}/submit",
        headers=_write_headers(maker),
    )
    assert submitted.status_code == 200, submitted.text

    denied = client.post(
        f"/inventory/requests/{request_id}/approve",
        headers=_write_headers(auditor),
    )
    assert denied.status_code == 403
    approved = client.post(
        f"/inventory/requests/{request_id}/approve",
        headers=_write_headers(checker),
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "posted"
