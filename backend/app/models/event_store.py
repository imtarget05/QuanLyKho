"""Append-only Inventory Event Store model for Event Sourcing + CQRS (Milestone ES).

Implements:
- InventoryEvent: immutable event record per aggregate (LOT / SKU / BRANCH).
- InventoryEventType: enum of supported domain event types.
- UniqueConstraint on (aggregate_id, sequence_number) prevents duplicate sequences.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    CheckConstraint,
    Column,
    DateTime,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.types import CHAR, TypeDecorator

from app.db.base import Base

# ---------------------------------------------------------------------------
# Platform-independent UUID type (mirrors audit.py's GUID)
# ---------------------------------------------------------------------------

class GUID(TypeDecorator):
    """Platform-independent GUID/UUID type.

    Stores as UUID in PostgreSQL and CHAR(36) in SQLite.
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


# ---------------------------------------------------------------------------
# Enum
# ---------------------------------------------------------------------------

class InventoryEventType(str, enum.Enum):  # noqa: UP042 — str-subclass giữ nguyên giá trị lưu DB
    RECEIPT_POSTED = "RECEIPT_POSTED"
    ISSUE_POSTED = "ISSUE_POSTED"
    ADJUSTMENT_POSTED = "ADJUSTMENT_POSTED"
    ADJUSTMENT_REVERSED = "ADJUSTMENT_REVERSED"
    LOT_EXPIRED = "LOT_EXPIRED"


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------

class InventoryEvent(Base):
    """Append-only event record for a single domain event affecting an aggregate.

    Guarantees:
    - sequence_number is monotonically increasing per aggregate_id.
    - UniqueConstraint(aggregate_id, sequence_number) prevents duplicates at DB level.
    - CheckConstraint ensures sequence_number >= 0.
    """

    __tablename__ = "inventory_events"
    __table_args__ = (
        UniqueConstraint("aggregate_id", "sequence_number", name="uq_inventory_events_aggregate_seq"),
        CheckConstraint("sequence_number >= 0", name="ck_inventory_events_seq_non_negative"),
        Index("ix_inventory_events_aggregate_id", "aggregate_id"),
        {"extend_existing": True},
    )

    id: str = Column(GUID(), primary_key=True, default=lambda: str(uuid.uuid4()))
    aggregate_id: str = Column(GUID(), nullable=False)
    aggregate_type: str = Column(String(50), nullable=False)
    sequence_number: int = Column(Integer, nullable=False)
    event_type: str = Column(String(80), nullable=False)
    payload: Any = Column(JSON, nullable=False, default=dict)
    caused_by_idempotency_key: str | None = Column(String(255), nullable=True)
    created_at: datetime = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    def __repr__(self) -> str:
        return (
            f"<InventoryEvent aggregate={self.aggregate_id} "
            f"seq={self.sequence_number} type={self.event_type}>"
        )
