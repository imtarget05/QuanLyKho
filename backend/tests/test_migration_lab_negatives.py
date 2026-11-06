"""Negative cases per docs/QA_PLAN.md, modeled on tests/test_business_journey_full.py.

Covers QA_PLAN error paths not already asserted in the journey suite:
- R02: receipt with past expiry -> 422 EXPIRED_LOT
- F03: issue exceeding available stock -> 409 INSUFFICIENT_STOCK
- S05: maker self-approves own request -> 403 SELF_APPROVAL_FORBIDDEN
"""

import uuid
from datetime import date, timedelta

DEMO_PASSWORD = "DemoPass123!"


def _login(client, username="demo_maker"):
    response = client.post(
        "/auth/login", data={"username": username, "password": DEMO_PASSWORD}
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _h(client, method, path, token=None, **kw):
    headers = dict(kw.pop("headers", {}) or {})
    if isinstance(token, dict):
        headers.update(token)
    elif token:
        headers["Authorization"] = f"Bearer {token}"
    if method.upper() in {"POST", "PUT", "PATCH", "DELETE"}:
        headers.setdefault("Idempotency-Key", str(uuid.uuid4()))
    return client.request(method, f"/api/v1{path}", headers=headers, **kw)


def _item_and_loc(client, maker):
    items = _h(client, "GET", "/inventory/items", token=maker).json()["items"]
    assert items, "cần seed nguyên liệu trà sữa"
    item = items[0]["id"]
    locs = _h(client, "GET", "/inventory/locations", token=maker).json()["locations"]
    loc = next((l for l in locs if l["code"] == "BAR-MAIN"), locs[0])["id"]
    return item, loc


def _approve(client, checker, request_id):
    return _h(
        client,
        "POST",
        f"/inventory/requests/{request_id}/approve",
        token=checker,
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )


def test_receipt_past_expiry_rejected_422_expired_lot(client):
    """QA_PLAN R02: expiry_date before receipt day -> 422 EXPIRED_LOT."""
    maker = _login(client)
    item, loc = _item_and_loc(client, maker)
    past = (date.today() - timedelta(days=1)).isoformat()
    bad = _h(
        client,
        "POST",
        "/inventory/requests",
        token=maker,
        json={
            "kind": "receipt",
            "dest_id": loc,
            "supplier": "NCC Neg",
            "lines": [{"item_id": item, "quantity": "2", "lot_no": "LOT-PAST", "expiry_date": past}],
        },
    )
    assert bad.status_code == 422, bad.text
    assert bad.json()["error"]["code"] == "EXPIRED_LOT", bad.text


def test_issue_exceeding_stock_rejected_409_insufficient_stock(client):
    """QA_PLAN F03: issue exceeding available stock -> 409 INSUFFICIENT_STOCK."""
    maker = _login(client)
    checker = _login(client, "demo_checker")
    item, loc = _item_and_loc(client, maker)
    future = (date.today() + timedelta(days=30)).isoformat()

    # Receipt 5 units and approve -> stock becomes 5.
    r = _h(
        client,
        "POST",
        "/inventory/requests",
        token=maker,
        json={
            "kind": "receipt",
            "dest_id": loc,
            "supplier": "NCC Neg",
            "lines": [{"item_id": item, "quantity": "5", "lot_no": "LOT-STOCK", "expiry_date": future}],
        },
    )
    assert r.status_code == 201, r.text
    request_id = r.json()["id"]
    assert _h(client, "POST", f"/inventory/requests/{request_id}/submit", token=maker).status_code == 200
    assert _approve(client, checker, request_id).status_code == 200

    # Issue 999 units though only 5 available -> 409 INSUFFICIENT_STOCK.
    big = _h(
        client,
        "POST",
        "/inventory/requests",
        token=maker,
        json={
            "kind": "issue",
            "sub_kind": "sale",
            "source_id": loc,
            "lines": [{"item_id": item, "quantity": "999"}],
        },
    )
    assert big.status_code == 201, big.text
    big_id = big.json()["id"]
    res = _h(client, "POST", f"/inventory/requests/{big_id}/submit", token=maker)
    assert res.status_code == 409, res.text
    assert res.json()["error"]["code"] == "INSUFFICIENT_STOCK", res.text


def test_maker_self_approve_forbidden_403(client):
    """QA_PLAN S05: maker must not approve own request -> 403 SELF_APPROVAL_FORBIDDEN."""
    maker = _login(client)
    item, loc = _item_and_loc(client, maker)
    future = (date.today() + timedelta(days=30)).isoformat()
    r = _h(
        client,
        "POST",
        "/inventory/requests",
        token=maker,
        json={
            "kind": "receipt",
            "dest_id": loc,
            "supplier": "NCC Neg",
            "lines": [{"item_id": item, "quantity": "2", "lot_no": "LOT-SELF", "expiry_date": future}],
        },
    )
    assert r.status_code == 201, r.text
    request_id = r.json()["id"]
    assert _h(client, "POST", f"/inventory/requests/{request_id}/submit", token=maker).status_code == 200
    # Maker approves own request -> 403 SELF_APPROVAL_FORBIDDEN.
    self_appr = _h(
        client,
        "POST",
        f"/inventory/requests/{request_id}/approve",
        token=maker,
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert self_appr.status_code == 403, self_appr.text
    assert self_appr.json()["error"]["code"] == "SELF_APPROVAL_FORBIDDEN", self_appr.text
