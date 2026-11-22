"""A7 — Concurrency: hai transfer song song không được âm quỹ."""

from __future__ import annotations

import asyncio
import uuid

from tests.graphql_helpers import gql, new_account_code, read_balance, seed_accounts

TRANSFER = """
mutation($input: TransferFundsInput!) {
  transferFunds(input: $input) {
    success status message
    sourceBalance { ledgerBalance availableBalance }
    destBalance { ledgerBalance availableBalance }
  }
}
"""


async def test_concurrent_transfers_never_overdraw(async_client):
    source, dest = new_account_code(), new_account_code()
    await seed_accounts([source], available_cents=1_000_000)
    await seed_accounts([dest], available_cents=0)

    async def transfer(key: str):
        return await gql(
            async_client,
            TRANSFER,
            {"input": {"sourceAccountId": source, "destAccountId": dest, "amount": "6000.00"}},
            idempotency_key=key,
        )

    results = await asyncio.gather(
        transfer(f"tr-{uuid.uuid4()}"), transfer(f"tr-{uuid.uuid4()}")
    )

    succeeded = [b for _, b in results if (b.get("data") or {}).get("transferFunds")]
    assert len(succeeded) == 1, results
    failed = [b for _, b in results if b.get("errors")]
    assert len(failed) == 1, results

    src = await read_balance(source)
    dst = await read_balance(dest)
    assert src["available"] == 400_000
    assert src["available"] >= 0
    assert dst["available"] == 600_000


async def test_transfer_to_same_account_is_rejected(async_client):
    code = new_account_code()
    await seed_accounts([code], available_cents=500_000)

    status, body = await gql(
        async_client,
        TRANSFER,
        {"input": {"sourceAccountId": code, "destAccountId": code, "amount": "1.00"}},
        idempotency_key=f"tr-{uuid.uuid4()}",
    )
    assert status == 200
    assert "phải khác nhau" in body["errors"][0]["message"]
