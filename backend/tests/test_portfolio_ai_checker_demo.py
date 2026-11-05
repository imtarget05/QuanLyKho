"""Interview demo: AI advice never posts inventory without a human checker."""

import hashlib
import uuid
from datetime import date, timedelta
from decimal import Decimal

from app.api.errors import AppError
from app.api.routes import ai as ai_routes
from app.api.routes import inventory as inventory_routes


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


def test_receipt_issue_audit_and_failed_post_are_atomic(client, monkeypatch):
    maker = _headers(client, "demo_maker")
    checker = _headers(client, "demo_checker")
    auditor = _headers(client, "demo_auditor")
    items = client.get("/api/v1/inventory/items", headers=maker).json()["items"]
    locations = client.get("/api/v1/inventory/locations", headers=maker).json()["locations"]
    item_id = next(item["id"] for item in items if not item.get("tracked_serial"))
    location_id = locations[0]["id"]

    def balance_quantity() -> Decimal:
        response = client.get(
            "/api/v1/inventory/balances",
            headers=maker,
            params={"location_id": location_id, "item_id": item_id},
        )
        assert response.status_code == 200, response.text
        rows = response.json()["balances"]
        return Decimal(rows[0]["quantity"]) if rows else Decimal("0")

    before = balance_quantity()
    receipt = client.post(
        "/api/v1/inventory/requests",
        headers={**maker, "Idempotency-Key": str(uuid.uuid4())},
        json={
            "kind": "receipt",
            "dest_id": location_id,
            "reason": "Portfolio inventory receipt",
            "lines": [{
                "item_id": item_id,
                "quantity": "12",
                "lot_no": f"PORTFOLIO-{uuid.uuid4().hex[:12]}",
                "expiry_date": (date.today() + timedelta(days=30)).isoformat(),
            }],
        },
    )
    assert receipt.status_code == 201, receipt.text
    receipt_id = receipt.json()["id"]
    assert client.post(
        f"/api/v1/inventory/requests/{receipt_id}/submit", headers=maker
    ).status_code == 200
    approved_receipt = client.post(
        f"/api/v1/inventory/requests/{receipt_id}/approve",
        headers={**checker, "Idempotency-Key": str(uuid.uuid4())},
    )
    assert approved_receipt.status_code == 200, approved_receipt.text
    assert balance_quantity() == before + Decimal("12")
    receipt_movements = client.get(
        "/api/v1/inventory/movements",
        headers=checker,
        params={"request_id": receipt_id},
    )
    assert receipt_movements.status_code == 200, receipt_movements.text
    assert [
        Decimal(row["quantity_signed"])
        for row in receipt_movements.json()["movements"]
    ] == [Decimal("12")]

    issue = client.post(
        "/api/v1/inventory/requests",
        headers={**maker, "Idempotency-Key": str(uuid.uuid4())},
        json={
            "kind": "issue",
            "sub_kind": "sale",
            "source_id": location_id,
            "reason": "Portfolio stock issue",
            "lines": [{"item_id": item_id, "quantity": "5"}],
        },
    )
    assert issue.status_code == 201, issue.text
    issue_id = issue.json()["id"]
    assert client.post(
        f"/api/v1/inventory/requests/{issue_id}/submit", headers=maker
    ).status_code == 200
    approved_issue = client.post(
        f"/api/v1/inventory/requests/{issue_id}/approve",
        headers={**checker, "Idempotency-Key": str(uuid.uuid4())},
    )
    assert approved_issue.status_code == 200, approved_issue.text
    assert balance_quantity() == before + Decimal("7")

    movements = client.get(
        "/api/v1/inventory/movements",
        headers=checker,
        params={"request_id": issue_id},
    )
    assert movements.status_code == 200, movements.text
    assert [Decimal(row["quantity_signed"]) for row in movements.json()["movements"]] == [
        Decimal("-5")
    ]

    events = client.get(
        "/api/v1/audit-events", headers=auditor, params={"limit": 100}
    )
    assert events.status_code == 200, events.text
    approved_subjects = {
        event["subject"]
        for event in events.json()["audit_events"]
        if event["action"] == "inventory.request.approved"
    }
    assert any(receipt_id in subject for subject in approved_subjects)
    assert any(issue_id in subject for subject in approved_subjects)

    failed_receipt = client.post(
        "/api/v1/inventory/requests",
        headers={**maker, "Idempotency-Key": str(uuid.uuid4())},
        json={
            "kind": "receipt",
            "dest_id": location_id,
            "reason": "Injected failure must roll back",
            "lines": [{"item_id": item_id, "quantity": "3"}],
        },
    )
    assert failed_receipt.status_code == 201, failed_receipt.text
    failed_id = failed_receipt.json()["id"]
    assert client.post(
        f"/api/v1/inventory/requests/{failed_id}/submit", headers=maker
    ).status_code == 200

    async def fail_subledger_posting(*args, **kwargs):
        raise AppError(503, "POSTING_UNAVAILABLE", "Injected posting failure")

    monkeypatch.setattr(inventory_routes, "_post_inventory_journal", fail_subledger_posting)
    failed_approval = client.post(
        f"/api/v1/inventory/requests/{failed_id}/approve",
        headers={**checker, "Idempotency-Key": str(uuid.uuid4())},
    )
    assert failed_approval.status_code == 503, failed_approval.text

    unchanged = client.get(
        f"/api/v1/inventory/requests/{failed_id}", headers=maker
    )
    assert unchanged.status_code == 200, unchanged.text
    assert unchanged.json()["status"] == "submitted"
    assert balance_quantity() == before + Decimal("7")
    failed_movements = client.get(
        "/api/v1/inventory/movements",
        headers=checker,
        params={"request_id": failed_id},
    )
    assert failed_movements.status_code == 200, failed_movements.text
    assert failed_movements.json()["movements"] == []
    after_failure_events = client.get(
        "/api/v1/audit-events", headers=auditor, params={"limit": 100}
    )
    assert after_failure_events.status_code == 200, after_failure_events.text
    assert not any(
        failed_id in event["subject"]
        and event["action"] == "inventory.request.approved"
        for event in after_failure_events.json()["audit_events"]
    )
