"""Middleware Idempotency-Key tren cac thao tac ghi (POST /inventory/requests)."""

from __future__ import annotations

import uuid

import pytest
from portfolio_test_helpers import first_location_and_item as _first_location_and_item
from portfolio_test_helpers import login_headers

DEMO_PASSWORD = "DemoPass123!"
MAKER = "demo_maker"


async def _maker_headers(async_client) -> dict:
    return await login_headers(async_client, MAKER, DEMO_PASSWORD)


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
