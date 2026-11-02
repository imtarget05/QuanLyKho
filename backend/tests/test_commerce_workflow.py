"""End-to-end commercial workflows against the isolated PostgreSQL test DB."""

import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta

import pytest

DEMO_PASSWORD = "DemoPass123!"


def _login(client, username: str) -> dict[str, str]:
    response = client.post(
        "/auth/login", data={"username": username, "password": DEMO_PASSWORD}
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _key(headers: dict[str, str]) -> dict[str, str]:
    return {**headers, "Idempotency-Key": str(uuid.uuid4())}


def _catalog(client, headers):
    locations = client.get("/inventory/locations", headers=headers)
    items = client.get("/inventory/items", headers=headers)
    assert locations.status_code == items.status_code == 200
    location = locations.json()["locations"][0]
    item = items.json()["items"][0]
    balances = client.get(
        "/inventory/balances",
        params={"location_id": location["id"], "item_id": item["id"]},
        headers=headers,
    )
    assert balances.status_code == 200, balances.text
    quantity = float(balances.json()["balances"][0]["quantity"])
    return location, item, quantity


@pytest.fixture
def commerce_users(client):
    return client, _login(client, "demo_maker"), _login(client, "demo_checker")


def test_quote_sale_approval_and_receivable_are_one_workflow(commerce_users):
    client, maker, checker = commerce_users
    location, item, before = _catalog(client, maker)
    assert before >= 1

    customer = client.post(
        "/commerce/customers",
        headers=_key(maker),
        json={"code": f"KH-{uuid.uuid4().hex[:12]}", "name": f"Khách {uuid.uuid4().hex}"},
    )
    assert customer.status_code == 201, customer.text
    quote = client.post(
        "/commerce/documents",
        headers=_key(maker),
        json={
            "document_type": "quote",
            "customer_id": customer.json()["id"],
            "lines": [{"item_id": item["id"], "quantity": 1, "unit_price": 1000}],
        },
    )
    assert quote.status_code == 201, quote.text
    assert quote.json()["status"] == "draft"

    converted = client.post(
        f"/commerce/documents/{quote.json()['id']}/convert",
        headers=_key(maker),
        json={"location_id": location["id"]},
    )
    assert converted.status_code == 201, converted.text
    sale = converted.json()
    assert sale["status"] == "pending_inventory"

    approval = client.post(
        f"/inventory/requests/{sale['inventory_request_id']}/approve",
        headers=_key(checker),
        json={},
    )
    assert approval.status_code == 200, approval.text

    documents = client.get(
        "/commerce/documents",
        params={"location_id": location["id"]},
        headers=maker,
    )
    approved_sale = next(
        row for row in documents.json()["documents"] if row["id"] == sale["id"]
    )
    assert approved_sale["status"] == "confirmed"
    converted_quote = next(
        row for row in documents.json()["documents"] if row["id"] == quote.json()["id"]
    )
    assert converted_quote["status"] == "converted"

    balance = client.get(
        "/inventory/balances",
        params={"location_id": location["id"], "item_id": item["id"]},
        headers=maker,
    )
    assert float(balance.json()["balances"][0]["quantity"]) == before - 1

    payment_headers = _key(maker)
    payment = client.post(
        f"/commerce/documents/{sale['id']}/payments",
        headers=payment_headers,
        json={"amount": 500, "method": "cash"},
    )
    assert payment.status_code == 201, payment.text
    assert payment.json()["paid"] == "500.00"
    assert payment.json()["outstanding"] == "500.00"

    replay = client.post(
        f"/commerce/documents/{sale['id']}/payments",
        headers=payment_headers,
        json={"amount": 500, "method": "cash"},
    )
    assert replay.status_code == 201, replay.text
    assert replay.json()["id"] == payment.json()["id"]

    documents = client.get(
        "/commerce/documents",
        params={"location_id": location["id"]},
        headers=maker,
    )
    replayed_sale = next(
        row for row in documents.json()["documents"] if row["id"] == sale["id"]
    )
    assert replayed_sale["paid"] == "500.00"
    assert len(replayed_sale["payments"]) == 1


def test_customer_create_replays_and_rejects_key_reuse(commerce_users):
    client, maker, _checker = commerce_users
    headers = _key(maker)
    customer_payload = {
        "code": f"KH-{uuid.uuid4().hex[:12]}",
        "name": f"Khách {uuid.uuid4().hex}",
    }
    first = client.post(
        "/commerce/customers", headers=headers, json=customer_payload
    )
    assert first.status_code == 201, first.text

    replay = client.post(
        "/commerce/customers", headers=headers, json=customer_payload
    )
    assert replay.status_code == 201, replay.text
    assert replay.json()["id"] == first.json()["id"]

    conflict = client.post(
        "/commerce/customers",
        headers=headers,
        json={**customer_payload, "name": "Tên khác"},
    )
    assert conflict.status_code == 409, conflict.text
    assert conflict.json()["error"]["code"] == "IDEMPOTENCY_KEY_REUSED"

    duplicate_code = client.post(
        "/commerce/customers",
        headers=_key(maker),
        json={**customer_payload, "name": "Khách trùng mã"},
    )
    assert duplicate_code.status_code == 409, duplicate_code.text
    assert duplicate_code.json()["error"]["code"] == "CUSTOMER_CODE_EXISTS"


def test_concurrent_customer_create_with_same_key_creates_one_customer(
    commerce_users,
):
    client, maker, _checker = commerce_users
    headers = _key(maker)
    payload = {
        "code": f"KH-{uuid.uuid4().hex[:12]}",
        "name": f"Khách {uuid.uuid4().hex}",
    }

    def create_customer(_):
        return client.post("/commerce/customers", headers=headers, json=payload)

    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(executor.map(create_customer, range(2)))

    assert [response.status_code for response in responses] == [201, 201], [
        response.text for response in responses
    ]
    assert responses[0].json()["id"] == responses[1].json()["id"]


def test_purchase_receipt_adds_stock_only_after_checker_approval(commerce_users):
    client, maker, checker = commerce_users
    location, item, before = _catalog(client, maker)
    supplier = client.post(
        "/commerce/suppliers",
        headers=_key(maker),
        json={"code": f"NCC-{uuid.uuid4().hex[:12]}", "name": f"Nhà cung cấp {uuid.uuid4().hex}"},
    )
    assert supplier.status_code == 201, supplier.text

    purchase = client.post(
        "/commerce/documents",
        headers=_key(maker),
        json={
            "document_type": "purchase",
            "location_id": location["id"],
            "supplier_id": supplier.json()["id"],
            "lines": [
                {
                    "item_id": item["id"],
                    "quantity": 2,
                    "unit_price": 500,
                    "lot_no": f"LOT-{uuid.uuid4().hex[:10]}",
                    "expiry_date": (date.today() + timedelta(days=90)).isoformat(),
                }
            ],
        },
    )
    assert purchase.status_code == 201, purchase.text
    assert purchase.json()["status"] == "pending_inventory"

    balance = client.get(
        "/inventory/balances",
        params={"location_id": location["id"], "item_id": item["id"]},
        headers=maker,
    )
    assert float(balance.json()["balances"][0]["quantity"]) == before

    approval = client.post(
        f"/inventory/requests/{purchase.json()['inventory_request_id']}/approve",
        headers=_key(checker),
        json={},
    )
    assert approval.status_code == 200, approval.text

    balance = client.get(
        "/inventory/balances",
        params={"location_id": location["id"], "item_id": item["id"]},
        headers=maker,
    )
    assert float(balance.json()["balances"][0]["quantity"]) == before + 2
    documents = client.get(
        "/commerce/documents",
        params={"location_id": location["id"]},
        headers=maker,
    )
    posted_purchase = next(
        row
        for row in documents.json()["documents"]
        if row["id"] == purchase.json()["id"]
    )
    assert posted_purchase["status"] == "confirmed"


def test_rejected_sale_releases_its_stock_reservation(commerce_users):
    client, maker, checker = commerce_users
    location, item, before = _catalog(client, maker)
    customer = client.post(
        "/commerce/customers",
        headers=_key(maker),
        json={"code": f"KH-{uuid.uuid4().hex[:12]}", "name": f"Khách {uuid.uuid4().hex}"},
    )
    assert customer.status_code == 201, customer.text
    sale = client.post(
        "/commerce/documents",
        headers=_key(maker),
        json={
            "document_type": "sale",
            "location_id": location["id"],
            "customer_id": customer.json()["id"],
            "lines": [{"item_id": item["id"], "quantity": 1, "unit_price": 1000}],
        },
    )
    assert sale.status_code == 201, sale.text

    rejected = client.post(
        f"/inventory/requests/{sale.json()['inventory_request_id']}/reject",
        headers=checker,
        json={"reason": "Khách hủy đơn"},
    )
    assert rejected.status_code == 200, rejected.text
    documents = client.get(
        "/commerce/documents",
        params={"location_id": location["id"]},
        headers=maker,
    )
    rejected_sale = next(
        row for row in documents.json()["documents"] if row["id"] == sale.json()["id"]
    )
    assert rejected_sale["status"] == "cancelled"
    balance = client.get(
        "/inventory/balances",
        params={"location_id": location["id"], "item_id": item["id"]},
        headers=maker,
    )
    assert float(balance.json()["balances"][0]["quantity"]) == before
