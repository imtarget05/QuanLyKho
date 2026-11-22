"""A7 — schema GraphQL: health, query cơ bản, field quan hệ + DataLoader (A6)."""

from __future__ import annotations

import asyncio

import pytest

from app.graphql.loaders import LedgerEntryLoader
from app.graphql.loaders.base import BatchLoader
from tests.graphql_helpers import gql, new_account_code, read_balance, seed_accounts


async def test_health_query(async_client):
    status, body = await gql(async_client, "{ health { status service } }")
    assert status == 200
    assert body["data"]["health"]["status"] == "healthy"
    assert body["data"]["health"]["service"] == "quanlykho-graphql"


async def test_account_and_accounts_query(async_client):
    code = new_account_code()
    await seed_accounts([code], available_cents=123_400)

    status, body = await gql(
        async_client,
        "query($id: UUID!) { account(id: $id) { id code availableBalance currency version } }",
        {"id": code},
    )
    assert status == 200, body
    account = body["data"]["account"]
    assert account["code"] == code
    assert account["availableBalance"] == "123400"

    status, body = await gql(async_client, "{ accounts(limit: 200) { code } }")
    assert status == 200
    assert code in {row["code"] for row in body["data"]["accounts"]}


async def test_nested_ledger_entries_use_one_batch(async_client, monkeypatch):
    """N+1 guard: 3 account × ledgerEntries ⇒ đúng 1 lần batch load."""

    codes = [new_account_code() for _ in range(3)]
    await seed_accounts(codes, available_cents=50_000)

    calls: list[list[str]] = []
    original = LedgerEntryLoader.batch_load_fn

    async def counting_batch(self, keys):
        calls.append(list(keys))
        return await original(self, keys)

    monkeypatch.setattr(LedgerEntryLoader, "batch_load_fn", counting_batch)

    status, body = await gql(
        async_client, "{ accounts(limit: 200) { code ledgerEntries(limit: 5) { id } } }"
    )
    assert status == 200, body

    # Mọi tài khoản trong response được gom vào đúng một batch.
    assert len(calls) == 1, f"kỳ vọng 1 batch, nhận {len(calls)}: {calls}"


async def test_batch_loader_batches_concurrent_keys():
    class CountingLoader(BatchLoader[str, str]):
        def __init__(self) -> None:
            super().__init__()
            self.batches: list[list[str]] = []

        async def batch_load_fn(self, keys):
            self.batches.append(list(keys))
            return [key.upper() for key in keys]

    loader = CountingLoader()
    results = await asyncio.gather(*(loader.load(k) for k in ("a", "b", "a", "c")))
    assert results == ["A", "B", "A", "C"]
    assert loader.batches == [["a", "b", "c"]]

    # Cache: lần load lại không phát batch mới.
    assert await loader.load("a") == "A"
    assert loader.batches == [["a", "b", "c"]]


async def test_unknown_account_returns_null(async_client):
    status, body = await gql(
        async_client,
        "query($id: UUID!) { account(id: $id) { code } }",
        {"id": new_account_code()},
    )
    assert status == 200
    assert body["data"]["account"] is None


@pytest.mark.parametrize("bad_id", ["not-a-uuid", "123"])
async def test_account_rejects_invalid_uuid(async_client, bad_id):
    response = await async_client.post(
        "/graphql",
        json={"query": "query($id: UUID!) { account(id: $id) { code } }", "variables": {"id": bad_id}},
    )
    # graphql-core trả lỗi coerce variable dưới dạng `errors` (HTTP 200).
    assert response.status_code == 200
    assert response.json()["errors"]


async def test_seed_helper_sets_balance():
    code = new_account_code()
    await seed_accounts([code], available_cents=777)
    balance = await read_balance(code)
    assert balance is not None
    assert balance["available"] == 777
