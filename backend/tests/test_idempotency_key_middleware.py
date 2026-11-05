"""Idempotency-Key middleware tests (docs/10 A3/A4) against POST /inventory/requests."""

from __future__ import annotations

import uuid

DEMO_PASSWORD = "DemoPass123!"
MAKER = "demo_maker"


def _login(client, username=MAKER, password=DEMO_PASSWORD):
    r = client.post(
        "/auth/login", data={"username": username, "password": password}
    )
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _first_location_and_item(client, headers):
    locs = client.get("/inventory/locations", headers=headers).json()["locations"]
    assert locs, "cannot find locations"
    items = client.get("/inventory/items", headers=headers).json()["items"]
    assert items, "cannot find items"
    return locs[0]["id"], items[0]["id"]


def _receipt_body(dest_id, item_id):
    return {
        "kind": "receipt",
        "dest_id": dest_id,
        "lines": [{"item_id": item_id, "quantity": "5", "unit_price": "10000"}],
        "supplier": "NCC Test",
    }


def test_same_key_same_body_returns_cached_response(client, demo_mode):
    headers = _login(client)
    dest_id, item_id = _first_location_and_item(client, headers)
    key = f"idem-{uuid.uuid4().hex[:6]}"
    body = _receipt_body(dest_id, item_id)

    r1 = client.post(
        "/inventory/requests",
        headers={**headers, "Idempotency-Key": key},
        json=body,
    )
    assert r1.status_code == 201, r1.text

    r2 = client.post(
        "/inventory/requests",
        headers={**headers, "Idempotency-Key": key},
        json=body,
    )
    assert r2.status_code == 201, r2.text
    assert r2.json()["id"] == r1.json()["id"]
    assert r2.json()["status"] == r1.json()["status"]


def test_same_key_different_body_returns_409(client, demo_mode):
    headers = _login(client)
    dest_id, item_id = _first_location_and_item(client, headers)
    key = f"idem-{uuid.uuid4().hex[:6]}"
    body1 = _receipt_body(dest_id, item_id)
    body2 = dict(_receipt_body(dest_id, item_id))
    body2["supplier"] = "NCC Khac"

    r1 = client.post(
        "/inventory/requests",
        headers={**headers, "Idempotency-Key": key},
        json=body1,
    )
    assert r1.status_code == 201, r1.text

    r2 = client.post(
        "/inventory/requests",
        headers={**headers, "Idempotency-Key": key},
        json=body2,
    )
    assert r2.status_code == 409, r2.text
    assert r2.json()["error"]["code"] == "IDEMPOTENCY_KEY_REUSED"


def test_new_key_normal_processing(client, demo_mode):
    headers = _login(client)
    dest_id, item_id = _first_location_and_item(client, headers)
    key = f"idem-{uuid.uuid4().hex[:6]}"
    body = _receipt_body(dest_id, item_id)

    r = client.post(
        "/inventory/requests",
        headers={**headers, "Idempotency-Key": key},
        json=body,
    )
    assert r.status_code == 201, r.text
    assert r.json()["status"] == "draft"
    assert r.json()["kind"] == "receipt"
    assert r.json()["maker_id"]


def test_no_idempotency_key_middleware_skips(client, demo_mode):
    headers = _login(client)
    dest_id, item_id = _first_location_and_item(client, headers)
    body = _receipt_body(dest_id, item_id)

    r = client.post("/inventory/requests", headers=headers, json=body)
    assert r.status_code == 400, r.text
    assert r.json()["error"]["code"] == "IDEMPOTENCY_KEY_REQUIRED"
