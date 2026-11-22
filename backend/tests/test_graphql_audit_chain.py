"""A7 — Audit trail & hash-chain integrity qua GraphQL."""

from __future__ import annotations

import uuid

from tests.graphql_helpers import gql

CREATE = """
mutation($input: CreateTransactionInput!) {
  createTransaction(input: $input) { success debitTotal creditTotal }
}
"""


async def _create(async_client, reference: str):
    return await gql(
        async_client,
        CREATE,
        {
            "input": {
                "entries": [
                    {"accountCode": "1011", "debit": "7.00", "credit": "0"},
                    {"accountCode": "4011", "debit": "0", "credit": "7.00"},
                ],
                "reference": reference,
            }
        },
        idempotency_key=f"tx-{uuid.uuid4()}",
    )


async def test_create_transaction_writes_audit_trail(async_client):
    reference = f"REF-{uuid.uuid4()}"
    status, body = await _create(async_client, reference)
    assert status == 200, body
    assert body["data"]["createTransaction"]["success"] is True

    status, body = await gql(
        async_client,
        """
        query($entityId: String!) {
          auditTrail(entityType: "ledger_transaction", entityId: $entityId) {
            totalCount
            entries { action entityType entityId payloadHash prevHash currentHash }
          }
        }
        """,
        {"entityId": reference},
    )
    assert status == 200, body
    connection = body["data"]["auditTrail"]
    assert connection["totalCount"] >= 1
    entry = connection["entries"][0]
    assert entry["action"] == "CREATE_TRANSACTION"
    assert entry["entityId"] == reference
    assert entry["payloadHash"] and entry["currentHash"]


async def test_global_chain_verification_is_valid(async_client):
    reference = f"REF-{uuid.uuid4()}"
    status, body = await _create(async_client, reference)
    assert status == 200 and body["data"]["createTransaction"]["success"] is True

    status, body = await gql(
        async_client,
        "query { verifyAuditChain(subject: \"global\") }",
    )
    assert status == 200, body
    assert body["data"]["verifyAuditChain"] is True

    status, body = await gql(
        async_client,
        "mutation { verifyAuditChainSubject(subject: \"global\") { subject isValid reason } }",
    )
    assert status == 200, body
    verification = body["data"]["verifyAuditChainSubject"]
    assert verification["isValid"] is True
    assert verification["reason"] is None
