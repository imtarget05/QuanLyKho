"""A7 — Transactional outbox qua GraphQL."""

from __future__ import annotations

import uuid

EMIT = """
mutation($input: EmitOutboxEventInput!) {
  emitOutboxEvent(input: $input) { success eventId topic status }
}
"""


async def test_emit_outbox_event_persists_and_is_queryable(async_client):
    from tests.graphql_helpers import gql

    aggregate_id = f"agg-{uuid.uuid4()}"
    topic = f"test.{uuid.uuid4().hex[:8]}"

    status, body = await gql(
        async_client,
        EMIT,
        {
            "input": {
                "topic": topic,
                "eventType": "test.event",
                "aggregateId": aggregate_id,
                "payload": '{"hello":"world"}',
                "traceId": "trace-outbox",
            }
        },
        idempotency_key=f"outbox-key-{uuid.uuid4()}",
    )
    assert status == 200, body
    emitted = body["data"]["emitOutboxEvent"]
    assert emitted["success"] is True
    assert emitted["topic"] == topic
    assert emitted["status"] == "PENDING"

    status, body = await gql(
        async_client,
        """
        query($id: UUID!) {
          outboxEvent(id: $id) {
            id topic eventType aggregateId payload traceId status attempts
          }
        }
        """,
        {"id": emitted["eventId"]},
    )
    assert status == 200, body
    row = body["data"]["outboxEvent"]
    assert row["aggregateId"] == aggregate_id
    assert row["eventType"] == "test.event"
    assert row["traceId"] == "trace-outbox"

    status, body = await gql(
        async_client,
        "query($topic: String!) { outboxEvents(topic: $topic) { id topic } }",
        {"topic": topic},
    )
    assert status == 200, body
    assert [e["id"] for e in body["data"]["outboxEvents"]] == [emitted["eventId"]]


async def test_emit_outbox_event_requires_aggregate_id(async_client):
    from tests.graphql_helpers import gql

    status, body = await gql(
        async_client,
        EMIT,
        {"input": {"topic": "t.missing", "eventType": "x.y"}},
        idempotency_key=f"outbox-key-{uuid.uuid4()}",
    )
    assert status == 200
    assert "aggregateId" in body["errors"][0]["message"]
