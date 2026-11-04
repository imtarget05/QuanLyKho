import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app.services.kafka_publisher import KafkaOutboxPublisher


@pytest.mark.asyncio
async def test_kafka_publisher_maps_event_types_to_stable_topics(monkeypatch):
    producer = Mock()
    producer.send_and_wait = AsyncMock()
    publisher = KafkaOutboxPublisher(
        bootstrap_servers="kafka.test:9092",
        producer=producer,
        environment="production",
    )
    event = SimpleNamespace(
        id=uuid.uuid4(),
        event_type="inventory.request.approved",
        aggregate_id="request-1",
        payload_json={"request_id": "request-1"},
        created_at="2026-11-03T00:00:00Z",
    )

    await publisher.publish(event)

    producer.send_and_wait.assert_awaited_once()
    topic = producer.send_and_wait.await_args.args[0]
    value = producer.send_and_wait.await_args.kwargs["value"]
    assert topic == "quanlykho.inventory.request.approved"
    assert value["event_id"] == str(event.id)
    assert value["aggregate_id"] == "request-1"
    assert value["payload"]["request_id"] == "request-1"


@pytest.mark.asyncio
async def test_production_publisher_requires_configured_bootstrap_servers():
    with pytest.raises(RuntimeError, match="KAFKA_BOOTSTRAP_SERVERS"):
        KafkaOutboxPublisher(bootstrap_servers="", environment="production")


@pytest.mark.asyncio
async def test_development_without_kafka_is_best_effort():
    publisher = KafkaOutboxPublisher(bootstrap_servers="", environment="test")
    event = SimpleNamespace(
        id=uuid.uuid4(),
        event_type="inventory.request.approved",
        aggregate_id="request-1",
        payload_json={},
        created_at=None,
    )

    assert await publisher.publish(event) is False
