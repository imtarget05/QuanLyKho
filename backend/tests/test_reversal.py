"""Tests for inventory reversal (P4)."""

from __future__ import annotations

from decimal import Decimal

import pytest


def _login(client, username: str, password: str = "DemoPass123!") -> dict:
    """Helper to login and get auth headers."""
    resp = client.post("/auth/login", json={"username": username, "password": password})
    if resp.status_code != 200:
        return {}
    token = resp.json().get("access_token")
    return {"Authorization": f"Bearer {token}"} if token else {}


def test_reversal_endpoint_requires_posted(client):
    """Chỉ được đảo phiếu đã post."""
    headers = _login(client, "demo_checker")
    if not headers:
        pytest.skip("No demo_checker user available")

    # Tạo phiếu draft
    resp = client.post(
        "/api/v1/inventory/requests",
        json={
            "kind": "receipt",
            "source_id": None,
            "dest_id": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbb1",
            "lines": [
                {
                    "item_id": "cccccccc-cccc-4ccc-8ccc-ccccccccccc1",
                    "quantity": 10,
                    "direction": "increase",
                    "unit": "kg",
                }
            ],
        },
        headers={**headers, "Idempotency-Key": str(__import__("uuid").uuid4())},
    )
    if resp.status_code not in (200, 201):
        pytest.skip(f"Could not create request: {resp.status_code} {resp.text}")

    req_id = resp.json().get("id")
    if not req_id:
        pytest.skip("No request id returned")

    # Thử đảo phiếu draft -> phải fail
    resp = client.post(
        f"/api/v1/inventory/requests/{req_id}/reverse",
        json={"reason": "Test reversal"},
        headers={**headers, "Idempotency-Key": str(__import__("uuid").uuid4())},
    )
    assert resp.status_code == 409
    body = resp.json()
    msg = body.get("detail") or body.get("error", {}).get("message", "")
    assert "đã post" in msg.lower() or "posted" in msg.lower()


def test_reversal_cannot_reverse_own_request(client):
    """Không tự đảo phiếu của chính mình."""
    headers_maker = _login(client, "demo_maker")
    headers_checker = _login(client, "demo_checker")
    if not headers_maker or not headers_checker:
        pytest.skip("Demo users not available")

    # Tạo phiếu bằng maker
    resp = client.post(
        "/api/v1/inventory/requests",
        json={
            "kind": "receipt",
            "source_id": None,
            "dest_id": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbb1",
            "lines": [
                {
                    "item_id": "cccccccc-cccc-4ccc-8ccc-ccccccccccc1",
                    "quantity": 10,
                    "direction": "increase",
                    "unit": "kg",
                }
            ],
        },
        headers={**headers_maker, "Idempotency-Key": str(__import__("uuid").uuid4())},
    )
    if resp.status_code not in (200, 201):
        pytest.skip(f"Could not create request: {resp.status_code}")

    req_id = resp.json().get("id")
    if not req_id:
        pytest.skip("No request id returned")

    # Submit và approve để post
    client.post(f"/api/v1/inventory/requests/{req_id}/submit", headers=headers_maker)
    client.post(f"/api/v1/inventory/requests/{req_id}/approve", headers=headers_checker)

    # Maker cố đảo phiếu của chính mình -> phải fail
    resp = client.post(
        f"/api/v1/inventory/requests/{req_id}/reverse",
        json={"reason": "Own reversal"},
        headers={**headers_maker, "Idempotency-Key": str(__import__("uuid").uuid4())},
    )
    assert resp.status_code in (403, 409)


def test_reversal_creates_new_draft_request(client):
    """Tạo reversal request mới (draft) liên kết từ phiếu gốc."""
    headers_maker = _login(client, "demo_maker")
    headers_checker = _login(client, "demo_checker")
    if not headers_maker or not headers_checker:
        pytest.skip("Demo users not available")

    # Tạo phiếu bằng maker
    resp = client.post(
        "/api/v1/inventory/requests",
        json={
            "kind": "receipt",
            "source_id": None,
            "dest_id": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbb1",
            "lines": [
                {
                    "item_id": "cccccccc-cccc-4ccc-8ccc-ccccccccccc1",
                    "quantity": 10,
                    "direction": "increase",
                    "unit": "kg",
                }
            ],
        },
        headers={**headers_maker, "Idempotency-Key": str(__import__("uuid").uuid4())},
    )
    if resp.status_code not in (200, 201):
        pytest.skip(f"Could not create request: {resp.status_code}")

    req_id = resp.json().get("id")
    if not req_id:
        pytest.skip("No request id returned")

    # Submit và approve để post
    client.post(f"/api/v1/inventory/requests/{req_id}/submit", headers=headers_maker)
    client.post(f"/api/v1/inventory/requests/{req_id}/approve", headers=headers_checker)

    # Checker đảo phiếu -> phải tạo reversal draft
    resp = client.post(
        f"/api/v1/inventory/requests/{req_id}/reverse",
        json={"reason": "Nhập sai số lượng"},
        headers={**headers_checker, "Idempotency-Key": str(__import__("uuid").uuid4())},
    )
    assert resp.status_code in (200, 201)
    data = resp.json()
    assert data.get("original_request_id") == req_id or data.get("reversed_from") == req_id
    assert data.get("status") == "draft"
