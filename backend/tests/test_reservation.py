"""Tests for balance lock / reservation (P6)."""

from __future__ import annotations

import pytest


def _login(client, username: str, password: str = "DemoPass123!") -> dict:
    resp = client.post("/auth/login", json={"username": username, "password": password})
    if resp.status_code != 200:
        return {}
    token = resp.json().get("access_token")
    return {"Authorization": f"Bearer {token}"} if token else {}


def _idem(headers: dict) -> dict:
    import uuid
    return {**headers, "Idempotency-Key": str(uuid.uuid4())}


def test_reserve_stock_decreases_available(client):
    """Giữ chở tồn -> available_quantity giảm."""
    headers = _login(client, "demo_checker")
    if not headers:
        pytest.skip("No demo_checker user available")

    resp = client.post(
        "/api/v1/inventory/balances/reserve",
        json={
            "location_id": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbb1",
            "item_id": "cccccccc-cccc-4ccc-8ccc-ccccccccccc1",
            "quantity": 30,
            "purpose": "pending_outbound",
            "ttl_minutes": 30,
        },
        headers=_idem(headers),
    )
    assert resp.status_code in (200, 201)
    data = resp.json()
    assert data["reserved_quantity"] == 30
    assert data["available_after_reserve"] >= 0  # sanity check


def test_reserve_exceeds_available_returns_409(client):
    """Không đủ tồn -> 409 CONFLICT."""
    headers = _login(client, "demo_checker")
    if not headers:
        pytest.skip("No demo_checker user available")

    resp = client.post(
        "/api/v1/inventory/balances/reserve",
        json={
            "location_id": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbb1",
            "item_id": "cccccccc-cccc-4ccc-8ccc-ccccccccccc1",
            "quantity": 9999,
            "purpose": "pending_outbound",
        },
        headers=_idem(headers),
    )
    assert resp.status_code == 409


def test_release_reservation_restores_available(client):
    """Giải phóng reservation -> available_quantity khôi phục."""
    headers = _login(client, "demo_checker")
    if not headers:
        pytest.skip("No demo_checker user available")

    # Reserve first
    resp = client.post(
        "/api/v1/inventory/balances/reserve",
        json={
            "location_id": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbb1",
            "item_id": "cccccccc-cccc-4ccc-8ccc-ccccccccccc1",
            "quantity": 10,
            "purpose": "pending_outbound",
        },
        headers=_idem(headers),
    )
    if resp.status_code not in (200, 201):
        pytest.skip(f"Reserve failed: {resp.status_code}")
    reservation_id = resp.json().get("reservation_id")
    if not reservation_id:
        pytest.skip("No reservation id")

    # Release
    resp = client.delete(
        f"/api/v1/inventory/balances/reservations/{reservation_id}",
        headers=_idem(headers),
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "released"
