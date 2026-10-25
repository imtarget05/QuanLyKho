"""Shift stock-count workflow from the tea-shop SRS."""
import uuid

from conftest import open_shift

DEMO_PASSWORD = "DemoPass123!"


def _login(client) -> dict[str, str]:
    response = client.post(
        "/auth/login", data={"username": "demo_maker", "password": DEMO_PASSWORD}
    )
    assert response.status_code == 200, response.text
    return {
        "Authorization": f"Bearer {response.json()['access_token']}",
        "Idempotency-Key": str(uuid.uuid4()),
    }


def _idempotent(headers: dict[str, str]) -> dict[str, str]:
    return {**headers, "Idempotency-Key": str(uuid.uuid4())}


def test_staff_shift_count_calculates_theoretical_balance_and_variance(client):
    headers = _login(client)
    locations = client.get("/inventory/locations", headers=headers).json()["locations"]
    items = client.get("/inventory/items", headers=headers).json()["items"]

    # Unique far-future business date: guard blocks a second OPEN shift per
    # (location, date, shift), so today/near dates collide across runs.
    opened, st_id = open_shift(
        client, _idempotent(headers), locations[0]["id"]
    )
    assert opened.json()["shift_code"] == "morning"
    # SRS §3.3: staff only enters used/count; opening is seeded by the system.
    seeded = client.get(f"/inventory/stocktakes/{st_id}", headers=headers).json()["lines"]
    opening = float(
        next(line for line in seeded if line["item_id"] == items[0]["id"])["opening_qty"]
    )

    updated = client.put(
        f"/inventory/stocktakes/{st_id}/lines",
        headers=_idempotent(headers),
        json={
            "lines": [
                {
                    "item_id": items[0]["id"],
                    "used_qty": "25",
                    "counted_qty": "43",
                }
            ]
        },
    )
    assert updated.status_code == 200, updated.text
    line = next(line for line in updated.json()["lines"] if line["item_id"] == items[0]["id"])
    theoretical = opening - 25
    assert float(line["theoretical_qty"]) == theoretical
    assert float(line["variance"]) == 43 - theoretical


def test_stocktake_offline_retry_keeps_one_version_and_rejects_stale_write(client):
    headers = _login(client)
    location = client.get("/inventory/locations", headers=headers).json()["locations"][0]
    item = client.get("/inventory/items", headers=headers).json()["items"][0]
    open_headers = _idempotent(headers)
    opened, stocktake_id = open_shift(client, open_headers, location["id"])
    assert opened.json()["version"] == 1
    open_retry = client.post("/inventory/stocktakes", headers=open_headers, json={
        "location_id": location["id"],
        "shift_code": "morning",
        "business_date": opened.json()["business_date"],
    })
    assert open_retry.status_code == 201, open_retry.text
    assert open_retry.json()["id"] == stocktake_id
    path = f"/inventory/stocktakes/{stocktake_id}/lines"
    payload = {"lines": [{"item_id": item["id"], "counted_qty": "12", "used_qty": "1"}]}
    write_headers = {**headers, "Idempotency-Key": str(uuid.uuid4()), "If-Match": "1"}

    first = client.put(path, headers=write_headers, json=payload)
    assert first.status_code == 200, first.text
    assert first.json()["version"] == 2
    retry = client.put(path, headers=write_headers, json=payload)
    assert retry.status_code == 200, retry.text
    assert retry.json()["version"] == 2
    stale = client.put(path, headers={**_idempotent(headers), "If-Match": "1"}, json=payload)
    assert stale.status_code == 409, stale.text
    assert stale.json()["error"]["code"] == "VERSION_CONFLICT"

    submit_headers = {**_idempotent(headers), "If-Match": "2"}
    submitted = client.post(f"/inventory/stocktakes/{stocktake_id}/submit", headers=submit_headers)
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["version"] == 3
    repeated = client.post(f"/inventory/stocktakes/{stocktake_id}/submit", headers=submit_headers)
    assert repeated.status_code == 200, repeated.text
    assert repeated.json()["version"] == 3
