import uuid

import pytest
from httpx import ASGITransport, AsyncClient

DEMO_PASSWORD = "DemoPass123!"
MAKER = "demo_maker"

@pytest.fixture
async def async_client(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as c:
        yield c

@pytest.mark.asyncio
async def test_probe(async_client):
    print("STEP login", flush=True)
    r = await async_client.post("/auth/login", data={"username": MAKER, "password": DEMO_PASSWORD})
    print("login", r.status_code, flush=True)
    assert r.status_code == 200, r.text
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    print("STEP locations", flush=True)
    r = await async_client.get("/inventory/locations", headers=h)
    print("locations", r.status_code, flush=True)
    locs = r.json()["locations"]
    print("STEP items", flush=True)
    r = await async_client.get("/inventory/items", headers=h)
    print("items", r.status_code, flush=True)
    items = r.json()["items"]
    print("STEP create", flush=True)
    r = await async_client.post(
        "/inventory/requests",
        headers={**h, "Idempotency-Key": str(uuid.uuid4())},
        json={"kind":"issue","sub_kind":"spoilage","source_id":locs[0]["id"],
              "lines":[{"item_id":items[0]["id"],"quantity":"2"}],
              "reason":"x"},
    )
    print("create", r.status_code, flush=True)
