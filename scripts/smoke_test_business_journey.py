#!/usr/bin/env python3
"""Smoke test business journey nhập–xuất–tồn (P1 #5)."""

from __future__ import annotations

import sys
import uuid
from decimal import Decimal

from fastapi.testclient import TestClient

from app.main import app

DEMO_PASSWORD = "DemoPass123!"
ITEM_SKU = "SUA-DAC-1KG"
LOCATION_CODE = "BAR-MAIN"
RECEIPT_QTY = "12.000"

failures: list[str] = []


def check(condition: bool, msg: str) -> None:
    if condition:
        print(f"  [PASS] {msg}")
    else:
        print(f"  [FAIL] {msg}")
        failures.append(msg)


def main() -> None:
    print("=== Smoke test: business journey nhập–xuất–tồn ===")
    client = TestClient(app)

    # --- 1. Login demo_maker ---
    print("\n[1] Login demo_maker...")
    r = client.post(
        "/auth/login",
        data={"username": "demo_maker", "password": DEMO_PASSWORD},
    )
    check(r.status_code == 200, f"demo_maker login -> {r.status_code}")
    if r.status_code != 200:
        print(f"  Cannot continue without maker token: {r.text[:200]}")
        sys.exit(1)
    maker_token = r.json()["access_token"]
    maker_hdr = {"Authorization": f"Bearer {maker_token}"}

    # --- 2. Lấy item + location ---
    print("\n[2] Lấy danh sách items và locations...")
    r = client.get("/inventory/items", headers=maker_hdr)
    check(r.status_code == 200, f"GET /inventory/items -> {r.status_code}")
    items = r.json().get("items", []) if r.status_code == 200 else []
    item = next((i for i in items if i.get("sku") == ITEM_SKU), None)
    check(item is not None, f"Tìm thấy item SKU={ITEM_SKU}")
    item_id = item["id"] if item else None

    r = client.get("/inventory/locations", headers=maker_hdr)
    check(r.status_code == 200, f"GET /inventory/locations -> {r.status_code}")
    locations = r.json().get("locations", []) if r.status_code == 200 else []
    location = next((l for l in locations if l.get("code") == LOCATION_CODE), None)
    check(location is not None, f"Tìm thấy location code={LOCATION_CODE}")
    location_id = location["id"] if location else None

    if item_id is None or location_id is None:
        print("  Thiếu item hoặc location -> không thể tiếp tục")
        sys.exit(1)

    # --- 3. Đọc balance trước khi nhập ---
    print("\n[3] Đọc balance trước khi nhập...")
    r = client.get(
        "/inventory/balances",
        headers=maker_hdr,
        params={"location_id": location_id, "item_id": item_id},
    )
    check(r.status_code == 200, f"GET /inventory/balances -> {r.status_code}")
    before_qty = Decimal("0")
    if r.status_code == 200:
        balances = r.json().get("balances", [])
        if balances:
            before_qty = Decimal(str(balances[0]["quantity"]))
    print(f"  Balance trước: {before_qty}")

    # --- 4. Tạo request nhập kho ---
    print("\n[4] Tạo request nhập kho (receipt)...")
    idem_key = str(uuid.uuid4())
    r = client.post(
        "/inventory/requests",
        headers={**maker_hdr, "Idempotency-Key": idem_key},
        json={
            "kind": "receipt",
            "source_id": location_id,
            "lines": [
                {
                    "item_id": item_id,
                    "quantity": RECEIPT_QTY,
                    "unit_price": "42000",
                    "note": f"Smoke test receipt {idem_key[:8]}",
                }
            ],
        },
    )
    check(r.status_code in (200, 201), f"POST /inventory/requests -> {r.status_code}")
    if r.status_code not in (200, 201):
        print(f"  Cannot continue: {r.text[:200]}")
        sys.exit(1)
    req_id = r.json()["id"]
    req_version = r.json().get("version", 1)
    print(f"  Request ID: {req_id}")

    # --- 5. Submit request ---
    print("\n[5] Submit request...")
    r = client.post(
        f"/inventory/requests/{req_id}/submit",
        headers={**maker_hdr, "If-Match": str(req_version)},
    )
    check(r.status_code in (200, 201), f"POST /submit -> {r.status_code}")

    # --- 6. Login demo_checker và duyệt ---
    print("\n[6] Login demo_checker và duyệt phiếu...")
    r = client.post(
        "/auth/login",
        data={"username": "demo_checker", "password": DEMO_PASSWORD},
    )
    check(r.status_code == 200, f"demo_checker login -> {r.status_code}")
    if r.status_code != 200:
        print("  Không thể tiếp tục mà không có checker token")
        sys.exit(1)
    checker_token = r.json()["access_token"]
    checker_hdr = {"Authorization": f"Bearer {checker_token}"}

    r = client.get(f"/inventory/requests/{req_id}", headers=checker_hdr)
    check(r.status_code == 200, f"GET request {req_id} as checker -> {r.status_code}")

    approve_idem = str(uuid.uuid4())
    r = client.post(
        f"/inventory/requests/{req_id}/approve",
        headers={**checker_hdr, "Idempotency-Key": approve_idem},
        json={},
    )
    check(r.status_code in (200, 201), f"POST /approve -> {r.status_code}")
    if r.status_code in (200, 201):
        check(r.json().get("status") == "posted", "Request status = posted")

    # --- 7. Đọc balance sau khi duyệt -> phải tăng ---
    print("\n[7] Đọc balance sau khi duyệt...")
    r = client.get(
        "/inventory/balances",
        headers=maker_hdr,
        params={"location_id": location_id, "item_id": item_id},
    )
    check(r.status_code == 200, f"GET /inventory/balances (after) -> {r.status_code}")
    after_qty = Decimal("0")
    if r.status_code == 200:
        balances = r.json().get("balances", [])
        if balances:
            after_qty = Decimal(str(balances[0]["quantity"]))
    print(f"  Balance sau: {after_qty}")
    expected = before_qty + Decimal(RECEIPT_QTY)
    check(after_qty == expected, f"Balance tăng đúng: {before_qty} + {RECEIPT_QTY} = {expected} (thực: {after_qty})")

    # --- 8. Kiểm tra movement đã được ghi ---
    print("\n[8] Kiểm tra movement đã được ghi...")
    r = client.get(
        "/inventory/movements",
        headers=maker_hdr,
        params={"request_id": req_id},
    )
    check(r.status_code == 200, f"GET /inventory/movements -> {r.status_code}")
    movements = []
    if r.status_code == 200:
        movements = r.json().get("movements", [])
    check(len(movements) >= 1, f"Có ít nhất 1 movement cho request {req_id} (thực: {len(movements)})")