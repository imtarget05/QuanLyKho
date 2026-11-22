"""A7 — Saga compensation: thiếu tiền thì rollback, số dư không đổi."""

from __future__ import annotations

import uuid

from tests.graphql_helpers import gql, new_account_code, read_balance, seed_accounts

SAGA = """
mutation($input: ExecuteSagaInput!) {
  executeSaga(input: $input) {
    success sagaId status completedSteps failedStep error
  }
}
"""


async def _run_saga(async_client, source: str, dest: str, amount_cents: int, key: str):
    return await gql(
        async_client,
        SAGA,
        {
            "input": {
                "sagaName": "InterWarehouseTransferSaga",
                "sourceAccountId": source,
                "destAccountId": dest,
                "amountCents": amount_cents,
                "transferId": f"tr-{uuid.uuid4()}",
            }
        },
        idempotency_key=key,
    )


async def test_saga_moves_funds_between_accounts(async_client):
    source, dest = new_account_code(), new_account_code()
    await seed_accounts([source], available_cents=1_000_000)
    await seed_accounts([dest], available_cents=0)

    status, body = await _run_saga(async_client, source, dest, 250_000, f"saga-{uuid.uuid4()}")
    assert status == 200, body
    result = body["data"]["executeSaga"]
    assert result["success"] is True, result
    assert result["status"] in ("COMPLETED", "SUCCESS")

    assert (await read_balance(source))["available"] == 750_000
    assert (await read_balance(dest))["available"] == 250_000


async def test_saga_with_insufficient_funds_compensates(async_client):
    source, dest = new_account_code(), new_account_code()
    await seed_accounts([source], available_cents=100_000)
    await seed_accounts([dest], available_cents=0)

    status, body = await _run_saga(async_client, source, dest, 900_000, f"saga-{uuid.uuid4()}")
    assert status == 200, body
    result = body["data"]["executeSaga"]
    assert result["success"] is False
    assert result["failedStep"]
    assert result["error"]

    # Compensation: không account nào bị trừ/ghi có, hold được giải phóng.
    src = await read_balance(source)
    dst = await read_balance(dest)
    assert src["available"] == 100_000
    assert src["hold"] == 0
    assert dst["available"] == 0
    assert dst["hold"] == 0
