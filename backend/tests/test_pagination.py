"""Keyset pagination regression tests (docs/06).

Every list endpoint exposes ``limit`` (1..100) and an opaque ``cursor``.
A cursor encodes the sort-key values of the last row on the page; passing
it back must filter the queryset to rows *after* that row in the endpoint's
stable sort order — never return the same rows again.
"""
from __future__ import annotations

import pytest

from app.api.errors import AppError
from app.api.pagination import (
    clamp_limit,
    coerce_timestamp,
    decode_cursor,
    encode_cursor,
)

DEMO_PASSWORD = "DemoPass123!"


async def _login(client, username: str) -> dict[str, str]:
    r = await client.post("/auth/login", data={"username": username, "password": DEMO_PASSWORD})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _page_keys(url: str, items_key: str, id_key: str = "id") -> list[str]:
    """Collect the ids of a full single-page listing (guard helper)."""
    return [str(row[id_key]) for row in url]


class TestPaginationUnit:
    async def test_clamp_limit_bounds(self):
        assert clamp_limit(1000) == 100
        assert clamp_limit(10**9) == 100
        assert clamp_limit(0) == 1
        assert clamp_limit(-5) == 1
        assert clamp_limit(None) == 50
        assert clamp_limit("not-a-number") == 50
        assert clamp_limit(25) == 25

    async def test_cursor_round_trip(self):
        payload = {"posted_at": "2026-01-02T03:04:05+00:00", "id": "some-uuid"}
        assert decode_cursor(encode_cursor(payload)) == payload

    async def test_decode_invalid_cursor_raises_400(self):
        with pytest.raises(AppError) as exc_info:
            decode_cursor("!!!not-base64-or-json!!!")
        assert exc_info.value.http_status == 400
        assert exc_info.value.code == "INVALID_CURSOR"

    async def test_decode_legacy_balances_cursor(self):
        import base64

        # Legacy cursors were plain base64("location_id:item_id"), no JSON framing.
        legacy = base64.urlsafe_b64encode(b"loc-1:item-9").decode().rstrip("=")
        assert decode_cursor(legacy) == {"location_id": "loc-1", "item_id": "item-9"}

    async def test_coerce_timestamp_naive_and_aware(self):
        naive = coerce_timestamp("2026-03-04T05:06:07")
        aware = coerce_timestamp("2026-03-04T05:06:07+00:00")
        assert naive.year == 2026 and aware.year == 2026


class TestKeysetEndpoints:
    async def test_balances_round_trip_no_overlap(self, client):
        headers = await _login(client, "demo_admin")
        first = await client.get("/inventory/balances", headers=headers, params={"limit": 2})
        assert first.status_code == 200, first.text
        body = first.json()
        assert body["limit"] == 2
        if not body.get("next_cursor"):
            pytest.skip("not enough balances to exercise keyset paging")
        second = await client.get(
            "/inventory/balances", headers=headers, params={"limit": 2, "cursor": body["next_cursor"]}
        )
        assert second.status_code == 200, second.text
        first_ids = {b["location_id"] + ":" + b["item_id"] for b in body["balances"]}
        second_ids = {b["location_id"] + ":" + b["item_id"] for b in second.json()["balances"]}
        assert first_ids.isdisjoint(second_ids), "page 2 must not repeat page 1 rows"

    async def test_movements_round_trip_no_overlap(self, client):
        headers = await _login(client, "demo_admin")
        first = await client.get("/inventory/movements", headers=headers, params={"limit": 2})
        assert first.status_code == 200, first.text
        body = first.json()
        if not body.get("next_cursor"):
            pytest.skip("not enough movements to exercise keyset paging")
        second = await client.get(
            "/inventory/movements", headers=headers, params={"limit": 2, "cursor": body["next_cursor"]}
        )
        assert second.status_code == 200, second.text
        first_ids = {m["id"] for m in body["movements"]}
        second_ids = {m["id"] for m in second.json()["movements"]}
        assert first_ids.isdisjoint(second_ids)

    async def test_requests_round_trip_no_overlap(self, client):
        headers = await _login(client, "demo_admin")
        first = await client.get("/inventory/requests", headers=headers, params={"limit": 2})
        assert first.status_code == 200, first.text
        body = first.json()
        if not body.get("next_cursor"):
            pytest.skip("not enough requests to exercise keyset paging")
        second = await client.get(
            "/inventory/requests", headers=headers, params={"limit": 2, "cursor": body["next_cursor"]}
        )
        assert second.status_code == 200, second.text
        first_ids = {r["id"] for r in body["requests"]}
        second_ids = {r["id"] for r in second.json()["requests"]}
        assert first_ids.isdisjoint(second_ids)

    async def test_invalid_cursor_returns_400_envelope(self, client):
        headers = await _login(client, "demo_admin")
        for url in ("/inventory/balances", "/inventory/movements", "/inventory/requests"):
            r = await client.get(url, headers=headers, params={"cursor": "!!!bad!!!"})
            assert r.status_code == 400, (url, r.text)
            assert r.json()["error"]["code"] == "INVALID_CURSOR"

    async def test_limit_clamped_to_100(self, client):
        headers = await _login(client, "demo_admin")
        r = await client.get("/inventory/balances", headers=headers, params={"limit": 1000})
        assert r.status_code == 200, r.text
        assert r.json()["limit"] == 100
