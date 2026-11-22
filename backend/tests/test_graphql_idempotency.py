"""A7 — Idempotency: replay trả cache, cùng key khác payload bị chặn."""

from __future__ import annotations

import uuid

from sqlalchemy import func, select

from app.database import AsyncSessionLocal
from app.models.audit import AuditEntry
from app.models.outbox import OutboxEventRecord
from tests.graphql_helpers import gql

CREATE = """
mutation($input: CreateTransactionInput!) {
  createTransaction(input: $input) { success transactionId debitTotal creditTotal }
}
"""


def _input(key: str) -> dict:
    return {
        "entries": [
            {"accountCode": "1011", "debit": "25.00", "credit": "0"},
            {"accountCode": "4011", "debit": "0", "credit": "25.00"},
        ],
        "description": "idempotency",
        "reference": key,
    }


async def _count(model, column, value) -> int:
    async with AsyncSessionLocal() as session:
        return int(
            (await session.execute(select(func.count()).select_from(model).where(column == value))).scalar_one()
        )


async def test_replay_returns_cached_body_without_duplicate_side_effects(async_client):
    key = f"tx-{uuid.uuid4()}"
    first_status, first = await gql(
        async_client, CREATE, {"input": _input(key)}, idempotency_key=key
    )
    second_status, second = await gql(
        async_client, CREATE, {"input": _input(key)}, idempotency_key=key
    )

    assert first_status == second_status == 200
    assert first["data"] == second["data"]

    audit_filters = (
        select(func.count())
        .select_from(AuditEntry)
        .where(AuditEntry.entity_id == key)
        .where(AuditEntry.entity_type == "ledger_transaction")
    )
    async with AsyncSessionLocal() as session:
        audit_count = (await session.execute(audit_filters)).scalar_one()
    assert int(audit_count) == 1
    assert await _count(OutboxEventRecord, OutboxEventRecord.aggregate_id, key) == 1


async def test_same_key_different_payload_is_rejected(async_client):
    key = f"tx-{uuid.uuid4()}"
    await gql(async_client, CREATE, {"input": _input(key)}, idempotency_key=key)

    changed = _input(key)
    changed["description"] = "payload khác"
    status, body = await gql(async_client, CREATE, {"input": changed}, idempotency_key=key)

    assert status == 409
    assert body["error"]["code"] == "IDEMPOTENCY_KEY_REUSED"
