import sys
import uuid
from datetime import UTC, datetime
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app.services.kafka_publisher import KafkaOutboxPublisher, json_serializer


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


@pytest.mark.asyncio
async def test_kafka_producer_starts_sends_and_stops(monkeypatch):
    producer = SimpleNamespace(
        start=AsyncMock(), send_and_wait=AsyncMock(), stop=AsyncMock()
    )
    factory = Mock(return_value=producer)
    aiokafka = ModuleType("aiokafka")
    aiokafka.AIOKafkaProducer = factory
    monkeypatch.setitem(sys.modules, "aiokafka", aiokafka)

    publisher = KafkaOutboxPublisher(
        bootstrap_servers="kafka.test:9092", environment="production"
    )
    event = SimpleNamespace(
        id=uuid.uuid4(),
        event_type="cash receipt",
        aggregate_id="request-2",
        payload_json=None,
        created_at=datetime(2026, 11, 5, tzinfo=UTC),
    )

    assert await publisher.publish(event) is True
    factory.assert_called_once_with(
        bootstrap_servers="kafka.test:9092",
        enable_idempotence=True,
        acks="all",
        value_serializer=json_serializer,
    )
    producer.start.assert_awaited_once()
    producer.send_and_wait.assert_awaited_once()
    topic = producer.send_and_wait.await_args.args[0]
    value = producer.send_and_wait.await_args.kwargs["value"]
    assert topic == "quanlykho.cash-receipt"
    assert value["created_at"] == "2026-11-05T00:00:00+00:00"
    assert value["payload"] == {}
    assert json_serializer(value).startswith(b'{"aggregate_id":"request-2"')

    await publisher.close()
    await publisher.close()
    producer.stop.assert_awaited_once()
