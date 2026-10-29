"""S4 — Reviewer read-only mode.

`demo_auditor` (role `auditor`) có capability `inventory:review`: xem được toàn
bộ dữ liệu kho (số dư, phiếu, kiểm kê, lô, tài sản) KHÔNG được tạo/sửa/duyệt
bất kỳ thao tác ghi nào. Mọi write route phải trả 403 cho reviewer.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

DEMO_PASSWORD = "DemoPass123!"

LOCATION_BAR = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbb1"  # BAR-MAIN
ITEM_TRA_DEN = "cccccccc-cccc-4ccc-8ccc-ccccccccccc1"  # Tra Den Loc Phat So 9


def _login(client: TestClient, username: str) -> str:
    r = client.post(
        "/auth/login", data={"username": username, "password": DEMO_PASSWORD}
    )
    assert r.status_code == 200, f"login({username}) -> {r.status_code} {r.text[:300]}"
    return r.json()["access_token"]


def _h(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


class TestReviewerReadOnly:
    def test_reviewer_can_read_all_inventory_endpoints(self, client: TestClient):
        """Reviewer xem được mọi endpoint chỉ-read của kho."""
        token = _login(client, "demo_auditor")
        headers = _h(token)
        read_paths = [
            "/inventory/items",
            "/inventory/items/" + ITEM_TRA_DEN,
            "/inventory/locations",
            "/inventory/balances",
            "/inventory/movements",
            "/inventory/requests",
            "/inventory/stocktakes",
            "/inventory/assets",
            "/inventory/stock-levels",
            "/inventory/low-stock-alerts",
            "/inventory/expiry-alerts",
        ]
        for path in read_paths:
            r = client.get(path, headers=headers)
            assert r.status_code == 200, (
                f"reviewer GET {path} -> {r.status_code} {r.text[:300]}"
            )

    def test_reviewer_can_read_request_made_by_another_user(self, client: TestClient):
        """Reviewer (không phải maker) vẫn đọc được phiếu trong phạm vi scope."""
        maker_token = _login(client, "demo_maker")
        maker_headers = _h(maker_token)
        created = client.post(
            "/inventory/requests",
            headers={**maker_headers, "Idempotency-Key": str(__import__("uuid").uuid4())},
            json={"kind": "issue", "source_id": LOCATION_BAR, "lines": []},
        )
        assert created.status_code in (200, 201), (
            f"tạo phiếu test -> {created.status_code} {created.text[:300]}"
        )
        req_id = created.json()["id"]

        auditor_token = _login(client, "demo_auditor")
        auditor_headers = _h(auditor_token)
        r = client.get(f"/inventory/requests/{req_id}", headers=auditor_headers)
        assert r.status_code == 200, (
            f"reviewer đọc phiếu của người khác -> {r.status_code} {r.text[:300]}"
        )
        assert r.json()["id"] == req_id

    def test_reviewer_cannot_create_request(self, client: TestClient):
        """Create request (write) bị từ chối 403 với reviewer."""
        token = _login(client, "demo_auditor")
        headers = _h(token)
        r = client.post(
            "/inventory/requests",
            headers={**headers, "Idempotency-Key": str(__import__("uuid").uuid4())},
            json={"kind": "issue", "source_id": LOCATION_BAR, "lines": []},
        )
        assert r.status_code == 403, (
            f"reviewer create_request -> {r.status_code} {r.text[:300]}"
        )

    def test_reviewer_cannot_create_stocktake(self, client: TestClient):
        """Tạo ca kiểm kê (write) bị từ chối 403 với reviewer."""
        token = _login(client, "demo_auditor")
        headers = _h(token)
        r = client.post(
            "/inventory/stocktakes",
            headers={**headers, "Idempotency-Key": str(__import__("uuid").uuid4())},
            json={"location_id": LOCATION_BAR, "shift_code": "morning"},
        )
        assert r.status_code == 403, (
            f"reviewer create_stocktake -> {r.status_code} {r.text[:300]}"
        )

    def test_reviewer_cannot_approve_submitted_request(self, client: TestClient):
        """Duyệt phiếu (write) bị từ chối 403 với reviewer dù phiếu tồn tại."""
        import uuid as _uuid

        maker_token = _login(client, "demo_maker")
        maker_headers = _h(maker_token)
        created = client.post(
            "/inventory/requests",
            headers={**maker_headers, "Idempotency-Key": str(_uuid.uuid4())},
            json={
                "kind": "receipt",
                "dest_id": LOCATION_BAR,
                "lines": [
                    {
                        "item_id": ITEM_TRA_DEN,
                        "quantity": "10",
                        "unit_price": "65000",
                        "lot_no": "LOT-REVIEW-TEST",
                        "expiry_date": "2028-01-01",
                    }
                ],
            },
        )
        assert created.status_code in (200, 201), (
            f"tạo phiếu receipt -> {created.status_code} {created.text[:300]}"
        )
        req_id = created.json()["id"]
        version = created.json()["version"]

        submitted = client.post(
            f"/inventory/requests/{req_id}/submit",
            headers={
                **maker_headers,
                "Idempotency-Key": str(_uuid.uuid4()),
                "If-Match": str(version),
            },
        )
        assert submitted.status_code in (200, 201), (
            f"submit phiếu -> {submitted.status_code} {submitted.text[:300]}"
        )

        auditor_token = _login(client, "demo_auditor")
        auditor_headers = _h(auditor_token)
        r = client.post(
            f"/inventory/requests/{req_id}/approve",
            headers={
                **auditor_headers,
                "Idempotency-Key": str(_uuid.uuid4()),
                "If-Match": str(submitted.json().get("version", 2)),
            },
        )
        assert r.status_code == 403, (
            f"reviewer approve_request -> {r.status_code} {r.text[:300]}"
        )

    def test_demo_reset_chua_co_token_tra_401(self, client: TestClient):
        """/demo/reset yêu cầu auth -> 401 khi không có token."""
        r = client.post("/demo/reset")
        assert r.status_code == 401, f"/demo_reset không auth -> {r.status_code}"

    def test_demo_reset_ngoai_demo_mode_tra_404(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ):
        """/demo/reset fail-closed: 404 khi KHÔNG ở demo mode (dù đã auth admin)."""
        import app.features.demo.routes as demo_mod

        monkeypatch.setattr(
            demo_mod.settings.__class__,
            "is_demo_mode",
            property(lambda self: False),
        )
        admin_token = _login(client, "demo_admin")  # có admin:user_management
        headers = _h(admin_token)
        r = client.post("/demo/reset", headers=headers)
        assert r.status_code == 404, (
            f"/demo_reset ngoài demo mode -> {r.status_code} {r.text[:300]}"
        )

    def test_demo_reset_tra_200_va_goi_reseed_khi_demo_mode(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ):
        """/demo/reset trả 200 và gọi reset_demo_database khi ở demo mode."""
        import app.features.demo.routes as demo_mod

        called = {"reset": False}

        async def _fake_reset():
            called["reset"] = True

        monkeypatch.setattr(demo_mod, "reset_demo_database", _fake_reset)
        monkeypatch.setattr(
            demo_mod.settings.__class__,
            "is_demo_mode",
            property(lambda self: True),
        )

        admin_token = _login(client, "demo_admin")
        headers = _h(admin_token)
        r = client.post("/demo/reset", headers=headers)
        assert r.status_code == 200, f"/demo_reset demo mode -> {r.status_code} {r.text[:300]}"
        assert called["reset"] is True
        body = r.json()
        assert body["status"] == "reset_complete"
