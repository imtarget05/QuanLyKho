"""Transactional Outbox and Consumer Deduplication models (Milestone M3).

Implements:
1. OutboxEventRecord: Atomically persisted business events matching PROJECT.md § Interface Contracts.
2. ProcessedEventRecord: Deduplication registry for exactly-once consumer processing.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.types import CHAR, TypeDecorator

from app.db.base import Base


class GUID(TypeDecorator):
    """Platform-independent GUID/UUID type.

    Stores as UUID in PostgreSQL and CHAR(36) in SQLite.
    Accepts both str and uuid.UUID seamlessly.
    """

    impl = CHAR(36)
    cache_ok = True

    def load_dialect_impl(self, dialect: Any) -> Any:
        if dialect.name == "postgresql":
            return dialect.type_descriptor(PG_UUID(as_uuid=False))
        return dialect.type_descriptor(CHAR(36))

    def process_bind_param(self, value: Any, dialect: Any) -> Any:
        if value is None:
            return None
        return str(value)

    def process_result_value(self, value: Any, dialect: Any) -> Any:
        if value is None:
            return None
        return str(value)


class OutboxEventRecord(Base):
    """Transactional Outbox Event Persistence.

    Atomically committed in the exact same database transaction as business operations.
    Maintains dual compatibility:
    - payload (Text) for PROJECT.md and banking E2E suite
    - payload_json (JSON) for legacy activity.py and worker.py
    """

    __tablename__ = "outbox_events"
    __table_args__ = (
        Index("ix_outbox_events_topic", "topic"),
        Index("ix_outbox_events_aggregate_id", "aggregate_id"),
        Index("ix_outbox_events_trace_id", "trace_id"),
        Index("ix_outbox_events_status", "status"),
        {"extend_existing": True},
    )

    id: str = Column(GUID(), primary_key=True, default=lambda: str(uuid.uuid4()))
    topic: str = Column(String(128), nullable=False, default="")
    event_type: str = Column(String(128), nullable=False)
    aggregate_id: str = Column(String(128), nullable=False)
    payload: str = Column(Text, nullable=True, default="{}")
    payload_json: Any = Column(JSON, nullable=True, default=dict)
    trace_id: str = Column(String(64), nullable=False, default="")
    status: str = Column(String(32), nullable=False, default="PENDING")  # PENDING, PUBLISHED, FAILED
    attempts: int = Column(Integer, nullable=False, default=0)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )
    published_at = Column(DateTime(timezone=True), nullable=True)

    def __init__(self, **kwargs: Any) -> None:
        if "payload" in kwargs and "payload_json" not in kwargs:
            p = kwargs["payload"]
            if isinstance(p, dict):
                kwargs["payload_json"] = p
                kwargs["payload"] = json.dumps(p)
            elif isinstance(p, str):
                kwargs["payload"] = p
                try:
                    kwargs["payload_json"] = json.loads(p)
                except Exception:
                    kwargs["payload_json"] = {}
        elif "payload_json" in kwargs and "payload" not in kwargs:
            pj = kwargs["payload_json"]
            kwargs["payload_json"] = pj
            kwargs["payload"] = json.dumps(pj) if isinstance(pj, (dict, list)) else str(pj)
        elif "payload" not in kwargs and "payload_json" not in kwargs:
            kwargs["payload"] = "{}"
            kwargs["payload_json"] = {}
        super().__init__(**kwargs)

    def __repr__(self) -> str:
        return f"<OutboxEventRecord {self.event_type} topic={self.topic} status={self.status}>"


class ProcessedEventRecord(Base):
    """Consumer Deduplication Registry for Exactly-Once Processing.

    Composite primary key (event_id, consumer_group) guarantees that each consumer group
    executes business logic for a given event ID at most once.
    """

    __tablename__ = "processed_events"
    __table_args__ = (
        {"extend_existing": True},
    )

    event_id: str = Column(String(36), primary_key=True)
    consumer_group: str = Column(String(64), primary_key=True)
    processed_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )

    def __repr__(self) -> str:
        return f"<ProcessedEventRecord event_id={self.event_id} group={self.consumer_group}>"


# Contract aliases for banking and test suite parity
OutboxEvent = OutboxEventRecord
