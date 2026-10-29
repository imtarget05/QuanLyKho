"""Interview demo: AI advice never posts inventory without a human checker."""

import hashlib
import uuid
from decimal import Decimal

from app.features.ai import routes as ai_routes


def _headers(client, username: str) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": "DemoPass123!"},
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _new_receipt(client, maker: dict[str, str], item_id: str, location_id: str) -> str:
    created = client.post(
        "/api/v1/inventory/requests",
        headers={**maker, "Idempotency-Key": str(uuid.uuid4())},
        json={
            "kind": "receipt",
            "dest_id": location_id,
            "reason": "Nhập thêm nguyên liệu cho ca sáng",
            "lines": [{"item_id": item_id, "quantity": "12", "lot_no": "DEMO-LOT"}],
        },
    )
    assert created.status_code == 201, created.text
    request_id = created.json()["id"]
    submitted = client.post(f"/api/v1/inventory/requests/{request_id}/submit", headers=maker)
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["status"] == "submitted"
    return request_id


def test_advice_then_checker_approve_or_reject_without_duplicate_post(client, monkeypatch):
    # Deterministic local policy exercises the real advisory endpoint without
    # sending a voucher or personal data to an external model.
    monkeypatch.setattr(ai_routes.settings, "ai_provider", "disabled")
    maker = _headers(client, "demo_maker")
    checker = _headers(client, "demo_checker")
    auditor = _headers(client, "demo_auditor")
    items = client.get("/api/v1/inventory/items", headers=maker).json()["items"]
    locations = client.get("/api/v1/inventory/locations", headers=maker).json()["locations"]
    item_id = next(item["id"] for item in items if not item.get("tracked_serial"))
    location_id = locations[0]["id"]

    approved_id = _new_receipt(client, maker, item_id, location_id)
    advice = client.post(
        "/api/v1/ai/assess-request",
        headers={**checker, "X-Request-ID": f"demo-{approved_id[:8]}"},
        json={
            "request_id": approved_id,
            "kind": "receipt",
            "amount_or_qty": "12",
            "maker": "demo_maker",
            "reason": "Nhập thêm nguyên liệu cho ca sáng",
        },
    )
    assert advice.status_code == 200, advice.text
    assert advice.json()["assessment_source"] == "heuristic_fallback"
    assert advice.json()["simulation"] is True
    assert len(advice.json()["audit_stamp"]) == 64
    assert advice.headers["X-Request-ID"].startswith("demo-")

    # AI advice is read-only. The maker cannot approve their own submitted request.
    movements_path = "/api/v1/inventory/movements"
    assert client.get(movements_path, headers=maker, params={"request_id": approved_id}).json()["movements"] == []
    denied = client.post(
        f"/api/v1/inventory/requests/{approved_id}/approve",
        headers={**maker, "Idempotency-Key": str(uuid.uuid4())},
        json={},
    )
    assert denied.status_code == 403, denied.text
    assert denied.json()["error"]["code"] == "SELF_APPROVAL_FORBIDDEN"

    approval_key = str(uuid.uuid4())
    approval_trace_id = f"approval-{approved_id[:8]}"
    approved = client.post(
        f"/api/v1/inventory/requests/{approved_id}/approve",
        headers={**checker, "Idempotency-Key": approval_key, "X-Request-ID": approval_trace_id},
        json={},
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "posted"
    replay = client.post(
        f"/api/v1/inventory/requests/{approved_id}/approve",
        headers={**checker, "Idempotency-Key": approval_key},
        json={},
    )
    assert replay.status_code == 200, replay.text
    assert replay.json() == approved.json()
    conflict = client.post(
        f"/api/v1/inventory/requests/{approved_id}/approve",
        headers={**checker, "Idempotency-Key": str(uuid.uuid4())},
        json={},
    )
    assert conflict.status_code == 409, conflict.text
    movements = client.get(movements_path, headers=checker, params={"request_id": approved_id})
    assert movements.status_code == 200, movements.text
    assert len(movements.json()["movements"]) == 1
    assert Decimal(movements.json()["movements"][0]["quantity_signed"]) == Decimal("12")

    rejected_id = _new_receipt(client, maker, item_id, location_id)
    long_trace_id = "rejection-" + "x" * 100
    rejected = client.post(
        f"/api/v1/inventory/requests/{rejected_id}/reject",
        headers={**checker, "X-Request-ID": long_trace_id},
        json={"reason": "Chứng từ nhập chưa khớp lô thực tế"},
    )
    assert rejected.status_code == 200, rejected.text
    assert rejected.json()["status"] == "rejected"
    assert client.get(movements_path, headers=checker, params={"request_id": rejected_id}).json()["movements"] == []

    audit = client.get("/api/v1/audit-events", headers=auditor, params={"limit": 100})
    assert audit.status_code == 200, audit.text
    events = audit.json()["audit_events"]
    approval_events = [
        e for e in events
        if e["action"] == "inventory.request.approved" and approved_id in e["subject"]
    ]
    assert len(approval_events) == 1
    assert approval_events[0]["request_id"] == approval_trace_id
    rejection_events = [
        e for e in events
        if e["action"] == "inventory.request.rejected" and rejected_id in e["subject"]
    ]
    assert len(rejection_events) == 1
    assert rejection_events[0]["request_id"] == hashlib.sha256(long_trace_id.encode()).hexdigest()
