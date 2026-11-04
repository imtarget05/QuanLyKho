"""Middleware Idempotency-Key tren cac thao tac ghi (POST /inventory/requests)."""

from __future__ import annotations

import asyncio
import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.database import AsyncSessionLocal

DEMO_PASSWORD = "DemoPass123!"
MAKER = "demo_maker"


def _sql(sql: str, **params):
    async def _run():
        async with AsyncSessionLocal() as session:
            result = await session.execute(text(sql), params)
            await session.commit()
            if not result.returns_rows:
                return []
            return result.fetchall()

    return asyncio.run(_run())


@pytest.fixture
async def async_client(app):
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        yield client


async def _maker_headers(async_client) -> dict:
    r = await async_client.post(
        "/auth/login",
        data={"username": MAKER, "password": DEMO_PASSWORD},
    )
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def _first_location_and_item(async_client, headers) -> tuple:
    locs = (
        await async_client.get("/inventory/locations", headers=headers)
    ).json()["locations"]
    assert locs, "Can it kho"
    items = (
        await async_client.get("/inventory/items", headers=headers)
    ).json()["items"]
    assert items, "Can it hang"
    return locs[0]["id"], items[0]["id"]


def _idem(headers: dict) -> dict:
    return {**headers, "Idempotency-Key": str(uuid.uuid4())}


def _payload(source_id: str, item_id: str, quantity: str = "2") -> dict:
    return {
        "kind": "issue",
        "sub_kind": "spoilage",
        "source_id": source_id,
        "lines": [{"item_id": item_id, "quantity": quantity}],
        "reason": "Hang hong khi boc do",
    }


@pytest.mark.asyncio
async def test_same_key_same_payload_returns_cached_response(async_client):
    headers = await _maker_headers(async_client)
    source_id, item_id = await _first_location_and_item(async_client, headers)
    key = str(uuid.uuid4())
    req_headers = {**headers, "Idempotency-Key": key}

    r1 = await async_client.post(
        "/inventory/requests",
        headers=req_headers,
        json=_payload(source_id, item_id),
    )
    assert r1.status_code == 201, r1.text
    request_id = r1.json()["id"]

    r2 = await async_client.post(
        "/inventory/requests",
        headers=req_headers,
        json=_payload(source_id, item_id),
    )
    assert r2.status_code == 201, r2.text
    assert r2.json()["id"] == request_id, "Cung key + cung payload phai replay response cu"


@pytest.mark.asyncio
async def test_same_key_different_payload_409(async_client):
    headers = await _maker_headers(async_client)
    source_id, item_id = await _first_location_and_item(async_client, headers)
    key = str(uuid.uuid4())
    req_headers = {**headers, "Idempotency-Key": key}

    r1 = await async_client.post(
        "/inventory/requests",
        headers=req_headers,
        json=_payload(source_id, item_id, "2"),
    )
    assert r1.status_code == 201, r1.text

    r2 = await async_client.post(
        "/inventory/requests",
        headers=req_headers,
        json=_payload(source_id, item_id, "9"),
    )
    assert r2.status_code == 409, r2.text
    assert r2.json()["error"]["code"] == "IDEMPOTENCY_KEY_REUSED", r2.text


@pytest.mark.asyncio
async def test_new_key_normal_processing(async_client):
    headers = await _maker_headers(async_client)
    source_id, item_id = await _first_location_and_item(async_client, headers)

    key_a = str(uuid.uuid4())
    r1 = await async_client.post(
        "/inventory/requests",
        headers={**headers, "Idempotency-Key": key_a},
        json=_payload(source_id, item_id, "1"),
    )
    assert r1.status_code == 201, r1.text

    key_b = str(uuid.uuid4())
    r2 = await async_client.post(
        "/inventory/requests",
        headers={**headers, "Idempotency-Key": key_b},
        json=_payload(source_id, item_id, "1"),
    )
    assert r2.status_code == 201, r2.text
    assert r2.json()["id"] != r1.json()["id"], "Key moi phai tao phieu moi"
