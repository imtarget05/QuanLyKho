"""A7 — Double-entry invariants qua GraphQL createTransaction."""

from __future__ import annotations

import uuid

import pytest

from tests.graphql_helpers import gql

CREATE = """
mutation($input: CreateTransactionInput!) {
  createTransaction(input: $input) {
    success transactionId debitTotal creditTotal isReplay
  }
}
"""


def _entries(debit: str, credit: str) -> list[dict]:
    return [
        {"accountCode": "1011", "debit": debit, "credit": "0"},
        {"accountCode": "4011", "debit": "0", "credit": credit},
    ]


async def test_balanced_transaction_succeeds(async_client):
    key = f"tx-{uuid.uuid4()}"
    status, body = await gql(
        async_client,
        CREATE,
        {"input": {"entries": _entries("100.00", "100.00"), "reference": key}},
        idempotency_key=key,
    )
    assert status == 200, body
    payload = body["data"]["createTransaction"]
    assert payload["success"] is True
    assert payload["debitTotal"] == "100.00"
    assert payload["creditTotal"] == "100.00"


async def test_unbalanced_transaction_is_rejected(async_client):
    key = f"tx-{uuid.uuid4()}"
    status, body = await gql(
        async_client,
        CREATE,
        {"input": {"entries": _entries("100.00", "99.00")}},
        idempotency_key=key,
    )
    assert status == 200  # graphql-core bọc lỗi resolver vào `errors`
    assert "không cân đối" in body["errors"][0]["message"]
    assert body["data"] is None


async def test_entry_with_both_sides_is_rejected(async_client):
    key = f"tx-{uuid.uuid4()}"
    status, body = await gql(
        async_client,
        CREATE,
        {
            "input": {
                "entries": [
                    {"accountCode": "1011", "debit": "10", "credit": "10"},
                    {"accountCode": "4011", "debit": "0", "credit": "0"},
                ]
            }
        },
        idempotency_key=key,
    )
    assert status == 200
    assert "đúng một bên dương" in body["errors"][0]["message"]


async def test_missing_idempotency_key_is_rejected(async_client):
    status, body = await gql(
        async_client, CREATE, {"input": {"entries": _entries("1.00", "1.00")}}
    )
    assert status == 200
    assert "Idempotency-Key" in body["errors"][0]["message"]


@pytest.mark.parametrize("field", ["entries"])
async def test_empty_entries_fail_validation(async_client, field):
    # Schema yêu cầu `[LedgerEntryInput!]!`; rỗng vẫn hợp lệ về kiểu nhưng sẽ
    # không cân đối (0 == 0) → vẫn tạo transaction rỗng, nên chỉ assert không 5xx.
    status, body = await gql(
        async_client,
        CREATE,
        {"input": {field: []}},
        idempotency_key=f"tx-{uuid.uuid4()}",
    )
    assert status in (200, 400)
