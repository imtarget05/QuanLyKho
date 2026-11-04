"""At-least-once Kafka publishing for committed transactional outbox events."""

import json
import logging
import os
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)

_TOPIC_PREFIX = "quanlykho."


class KafkaOutboxPublisher:
    def __init__(
        self,
        *,
        bootstrap_servers: str | None = None,
        producer: Any = None,
        environment: str | None = None,
    ) -> None:
        self.environment = (
            environment or os.environ.get("APP_ENV", "production")
        ).strip().lower()
        self.bootstrap_servers = (
            bootstrap_servers
            if bootstrap_servers is not None
            else os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "").strip()
        )
        if self.environment == "production" and not self.bootstrap_servers:
            raise RuntimeError(
                "KAFKA_BOOTSTRAP_SERVERS is required in production"
            )
        self._producer = producer
        self._started = False

    async def _ensure_producer(self):
        if self._producer is not None:
            return self._producer
        if not self.bootstrap_servers:
            return None
        try:
            from aiokafka import AIOKafkaProducer
        except ImportError as exc:
            raise RuntimeError(
                "aiokafka is required when KAFKA_BOOTSTRAP_SERVERS is configured"
            ) from exc
        self._producer = AIOKafkaProducer(
            bootstrap_servers=self.bootstrap_servers,
            enable_idempotence=True,
            acks="all",
            value_serializer=json_serializer,
        )
        await self._producer.start()
        self._started = True
        return self._producer

    async def publish(self, event: Any) -> bool:
        producer = await self._ensure_producer()
        if producer is None:
            return False
        event_type = str(event.event_type).strip().replace(" ", "-")
        topic = _TOPIC_PREFIX + event_type
        created_at = event.created_at
        if isinstance(created_at, datetime):
            created_at = created_at.isoformat()
        value = {
            "event_id": str(event.id),
            "event_type": event_type,
            "aggregate_id": str(event.aggregate_id),
            "created_at": created_at,
            "payload": event.payload_json if isinstance(event.payload_json, dict) else {},
        }
        await producer.send_and_wait(
            topic,
            value=value,
            key=str(event.aggregate_id).encode("utf-8"),
        )
        return True

    async def close(self) -> None:
        if self._producer is not None and self._started:
            await self._producer.stop()
            self._started = False


def json_serializer(value: dict[str, Any]) -> bytes:
    return json.dumps(value, separators=(",", ":"), sort_keys=True).encode("utf-8")
