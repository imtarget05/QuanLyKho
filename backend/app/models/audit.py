"""Cryptographic Hash-Chained Audit Trail Model (Milestone M5).

Implements:
1. AuditEntry: Institutional-grade append-only audit model with SHA-256 hash chaining.
   Formula: H_n = SHA-256(H_{n-1} || timestamp_iso || actor_id || action || entity_type || entity_id || payload_hash)
2. Aliases: AuditLogEntry, AuditTrailRecord, AuditChainRecord for full compatibility.
3. WORM (Write Once, Read Many) enforcement: SQLAlchemy event listeners reject any UPDATE or DELETE operations.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    event,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.types import CHAR, JSON, TypeDecorator

from app.db.base import Base

GENESIS_HASH: str = "0" * 64


class AuditImmutabilityException(PermissionError):
    """Raised when an attempt to mutate (UPDATE/DELETE) an append-only audit trail record is detected."""

    pass


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


class JSONOrText(TypeDecorator):
    """Store JSON safely across SQLite and PostgreSQL, accepting dict or serialized JSON string."""

    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect: Any) -> Any:
        if dialect.name == "postgresql":
            return dialect.type_descriptor(JSONB(astext_type=Text()))
        return dialect.type_descriptor(JSON())

    def process_bind_param(self, value: Any, dialect: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, str):
            try:
                return json.loads(value)
            except Exception:
                return value
        return value

    def process_result_value(self, value: Any, dialect: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, str):
            try:
                return json.loads(value)
            except Exception:
                return value
        return value


class AuditEntry(Base):
    """Institutional-grade append-only cryptographic hash-chained audit record.

    Chain formulation:
        H_0 = GENESIS_HASH ("0" * 64)
        H_n = SHA-256(H_{n-1} || timestamp_iso || actor_id || action || entity_type || entity_id || payload_hash)
    """

    __tablename__ = "audit_trail"
    __table_args__ = (
        Index("ix_audit_trail_entity", "entity_type", "entity_id"),
        {"extend_existing": True},
    )

    id: int = Column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    event_id: str = Column(GUID(), nullable=False, default=lambda: str(uuid.uuid4()), unique=True)
    actor_id: str = Column(String(128), nullable=False, index=True)
    action: str = Column(String(128), nullable=False, index=True)
    entity_type: str = Column(String(128), nullable=False, index=True)
    entity_id: str = Column(String(128), nullable=False, index=True)
    state_payload: Any = Column(JSONOrText, nullable=False, default=dict)
    payload_hash: str = Column(String(64), nullable=False)
    prev_hash: str = Column(String(64), nullable=False, index=True)
    current_hash: str = Column(String(64), nullable=False, index=True)
    timestamp: datetime = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )

    def to_dict(self) -> dict[str, Any]:
        """Convert entry to serializable dictionary."""
        payload = self.state_payload
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except Exception:
                pass
        ts = self.timestamp
        if ts is not None and ts.tzinfo is None:
            ts = ts.replace(tzinfo=UTC)
        ts_str = ts.isoformat() if ts is not None else None

        return {
            "id": self.id,
            "event_id": self.event_id,
            "actor_id": self.actor_id,
            "action": self.action,
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
            "state_payload": payload,
            "payload_hash": self.payload_hash,
            "prev_hash": self.prev_hash,
            "current_hash": self.current_hash,
            "timestamp": ts_str,
        }

    def __repr__(self) -> str:
        return (
            f"<AuditEntry id={self.id} actor={self.actor_id} action={self.action} "
            f"entity={self.entity_type}:{self.entity_id} hash={self.current_hash[:8]}...>"
        )


# Backward compatibility aliases
AuditLogEntry = AuditEntry
AuditTrailRecord = AuditEntry
AuditChainRecord = AuditEntry


# WORM (Write Once, Read Many) enforcement at the SQLAlchemy ORM layer
@event.listens_for(AuditEntry, "before_update", propagate=True)
def _guard_audit_no_update(mapper: Any, connection: Any, target: Any) -> None:
    raise AuditImmutabilityException("Audit trail is immutable and append-only: UPDATE is forbidden.")


@event.listens_for(AuditEntry, "before_delete", propagate=True)
def _guard_audit_no_delete(mapper: Any, connection: Any, target: Any) -> None:
    raise AuditImmutabilityException("Audit trail is immutable and append-only: DELETE is forbidden.")
