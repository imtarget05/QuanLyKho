"""POST write endpoints cho inventory (requests, submit, approve, reject)."""

from __future__ import annotations

import uuid

import pytest
from portfolio_test_helpers import async_sql as _sql
from portfolio_test_helpers import first_location_and_item as _first_location_and_item
from portfolio_test_helpers import idem_headers as _idem
from portfolio_test_helpers import login_headers as _headers

DEMO_PASSWORD = "DemoPass123!"
MAKER = "demo_maker"
CHECKER = "demo_checker"
BRANCH_HO = "11111111-1111-4111-8111-111111111111"


async def _ensure_staff_user(username: str) -> str:
    """Tao user co role staff (co inventory:create_request, KHONG co inventory:approve_request)."""
    from app.api.routes.auth_utils import get_password_hash

    rows = await _sql("SELECT id FROM iam_users WHERE username = :u", u=username)
    if rows:
        user_id = str(rows[0][0])
        await _sql(
            "UPDATE iam_users SET password_hash = :p, status = 'active', branch_id = :b WHERE id = :id",
            p=get_password_hash(DEMO_PASSWORD),
            b=BRANCH_HO,
            id=user_id,
        )
    else:
        user_id = str(uuid.uuid4())
        await _sql(
            "INSERT INTO iam_users (id, username, password_hash, status, display_name_demo, email, branch_id) "
            "VALUES (:id, :u, :p, 'active', :d, :e, :b)",
            id=user_id,
            u=username,
            p=get_password_hash(DEMO_PASSWORD),
            d=f"Staff {username}",
            e=f"{username}@bankops.internal",
            b=BRANCH_HO,
        )
    await _sql("DELETE FROM iam_user_roles WHERE user_id = :id", id=user_id)
    await _sql("INSERT INTO iam_user_roles (user_id, role_code) VALUES (:id, 'staff')", id=user_id)
    return username


async def _create_receipt(async_client, headers, dest_id: str, item_id: str, quantity: str = "5"):
    return await async_client.post(
        "/inventory/requests",
        headers=_idem(headers),
        json={
            "kind": "receipt",
            "dest_id": dest_id,
            "lines": [
                {"item_id": item_id, "quantity": quantity, "unit_price": "10000"}
            ],
            "supplier": "NCC Test",
        },
    )


@pytest.mark.asyncio
async def test_create_inventory_request_returns_201(async_client):
    maker = await _headers(async_client, MAKER)
    dest_id, item_id = await _first_location_and_item(async_client, maker)
    r = await _create_receipt(async_client, maker, dest_id, item_id)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["status"] == "draft"
    assert body["kind"] == "receipt"
    assert body["maker_id"]


@pytest.mark.asyncio
async def test_submit_inventory_request(async_client):
    maker = await _headers(async_client, MAKER)
    dest_id, item_id = await _first_location_and_item(async_client, maker)
    r = await _create_receipt(async_client, maker, dest_id, item_id)
    assert r.status_code == 201, r.text
    request_id = r.json()["id"]

    r = await async_client.post(
        f"/inventory/requests/{request_id}/submit", headers=maker
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "submitted"


@pytest.mark.asyncio
async def test_approve_inventory_request_with_capability(async_client):
    maker = await _headers(async_client, MAKER)
    checker = await _headers(async_client, CHECKER)
    dest_id, item_id = await _first_location_and_item(async_client, maker)
    r = await _create_receipt(async_client, maker, dest_id, item_id)
    assert r.status_code == 201, r.text
    request_id = r.json()["id"]

    r = await async_client.post(
        f"/inventory/requests/{request_id}/submit", headers=maker
    )
    assert r.status_code == 200, r.text

    r = await async_client.post(
        f"/inventory/requests/{request_id}/approve",
        headers=_idem(checker),
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "posted"


@pytest.mark.asyncio
async def test_approve_denied_without_approve_capability(async_client):
    maker = await _headers(async_client, MAKER)
    staff = await _headers(
        async_client, await _ensure_staff_user(f"staff_nocap_{uuid.uuid4().hex[:8]}")
    )
    dest_id, item_id = await _first_location_and_item(async_client, maker)
    r = await _create_receipt(async_client, maker, dest_id, item_id)
    assert r.status_code == 201, r.text
    request_id = r.json()["id"]

    r = await async_client.post(
        f"/inventory/requests/{request_id}/submit", headers=maker
    )
    assert r.status_code == 200, r.text

    r = await async_client.post(
        f"/inventory/requests/{request_id}/approve",
        headers=_idem(staff),
    )
    assert r.status_code == 403, r.text
    assert r.json()["error"]["code"] == "FORBIDDEN", r.text


@pytest.mark.asyncio
async def test_reject_inventory_request(async_client):
    maker = await _headers(async_client, MAKER)
    checker = await _headers(async_client, CHECKER)
    dest_id, item_id = await _first_location_and_item(async_client, maker)
    r = await _create_receipt(async_client, maker, dest_id, item_id)
    assert r.status_code == 201, r.text
    request_id = r.json()["id"]

    r = await async_client.post(
        f"/inventory/requests/{request_id}/submit", headers=maker
    )
    assert r.status_code == 200, r.text

    r = await async_client.post(
        f"/inventory/requests/{request_id}/reject",
        headers=checker,
        json={"reason": "Khong duoc duyet"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "rejected"
