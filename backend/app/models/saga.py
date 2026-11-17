"""Saga orchestration models (Milestone M4, interview-prep 02/05 §4).

Implements:
1. SagaInstance: State machine for distributed sagas (PENDING, RUNNING, COMPLETED, COMPENSATING, COMPENSATED, FAILED).
2. SagaStepLog: Execution and compensation audit log for saga steps (PENDING, EXECUTED, COMPENSATED, FAILED).
3. SagaStep & CompensatingLog: Preserved for backwards compatibility with existing banking saga workflows.

Uses platform-independent GUID and JSONOrText TypeDecorators for dual-dialect SQLite and PostgreSQL support.
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
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import relationship
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


class JSONOrText(TypeDecorator):
    """Store JSON safely across SQLite and PostgreSQL, accepting dict or serialized JSON string."""

    impl = JSON
    cache_ok = True

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
        return value


class SagaInstance(Base):
    """Trạng thái tổng thể của một Saga instance (State Machine)."""

    __tablename__ = "saga_instances"
    __table_args__ = ({"extend_existing": True},)

    id: str = Column(GUID(), primary_key=True, default=lambda: str(uuid.uuid4()))
    saga_name: str = Column(String(128), nullable=False, default="", index=True)
    saga_type: str = Column(String(64), nullable=True, index=True)
    status: str = Column(
        String(32),
        nullable=False,
        default="PENDING",
        index=True,
    )  # PENDING | RUNNING | COMPENSATING | COMPENSATED | COMPLETED | FAILED
    current_step: str | None = Column(String(128), nullable=True)
    context_data: Any = Column(JSONOrText, nullable=False, default=dict)
    context_json: Any = Column(JSONOrText, nullable=True, default=dict)
    error_message: str | None = Column(Text, nullable=True)

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    # Relationships
    steps = relationship(
        "SagaStep", back_populates="saga", cascade="all, delete-orphan", lazy="selectin"
    )
    step_logs = relationship(
        "SagaStepLog",
        back_populates="saga",
        cascade="all, delete-orphan",
        order_by="SagaStepLog.step_index.asc()",
        lazy="selectin",
    )
    compensations = relationship(
        "CompensatingLog", back_populates="saga", cascade="all, delete-orphan", lazy="selectin"
    )

    def __init__(self, **kwargs: Any) -> None:
        if "saga_name" in kwargs and "saga_type" not in kwargs:
            kwargs["saga_type"] = kwargs["saga_name"]
        elif "saga_type" in kwargs and "saga_name" not in kwargs:
            kwargs["saga_name"] = kwargs["saga_type"]

        if "context_data" in kwargs and "context_json" not in kwargs:
            kwargs["context_json"] = kwargs["context_data"]
        elif "context_json" in kwargs and "context_data" not in kwargs:
            kwargs["context_data"] = kwargs["context_json"]
        elif "context" in kwargs:
            ctx = kwargs.pop("context")
            kwargs["context_data"] = ctx
            kwargs["context_json"] = ctx

        if "id" in kwargs and kwargs["id"] is not None:
            kwargs["id"] = str(kwargs["id"])

        super().__init__(**kwargs)

    @property
    def context(self) -> Any:
        return self.context_data or self.context_json or {}

    @context.setter
    def context(self, val: Any) -> None:
        self.context_data = val
        self.context_json = val

    def __repr__(self) -> str:
        return f"<SagaInstance {self.id} name={self.saga_name} status={self.status}>"


class SagaStepLog(Base):
    """Audit log cho từng bước thực thi và bù trừ trong Saga."""

    __tablename__ = "saga_step_logs"
    __table_args__ = (
        Index("ix_saga_step_logs_step_index", "saga_id", "step_index"),
        {"extend_existing": True},
    )

    id: str = Column(GUID(), primary_key=True, default=lambda: str(uuid.uuid4()))
    saga_id: str = Column(
        GUID(),
        ForeignKey("saga_instances.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    step_name: str = Column(String(128), nullable=False)
    step_index: int = Column(Integer, nullable=False, default=1)
    status: str = Column(
        String(32),
        nullable=False,
        default="PENDING",
    )  # PENDING | EXECUTED | COMPENSATED | FAILED | COMPLETED
    input_data: Any = Column(JSONOrText, nullable=True)
    output_data: Any = Column(JSONOrText, nullable=True)
    error_message: str | None = Column(Text, nullable=True)
    executed_at = Column(DateTime(timezone=True), nullable=True)
    compensated_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )

    saga = relationship("SagaInstance", back_populates="step_logs")

    def __init__(self, **kwargs: Any) -> None:
        if "id" in kwargs and kwargs["id"] is not None:
            kwargs["id"] = str(kwargs["id"])
        if "saga_id" in kwargs and kwargs["saga_id"] is not None:
            kwargs["saga_id"] = str(kwargs["saga_id"])

        if "step_order" in kwargs and "step_index" not in kwargs:
            kwargs["step_index"] = kwargs.pop("step_order")
        if "result" in kwargs and "output_data" not in kwargs:
            kwargs["output_data"] = kwargs.pop("result")
        if "error" in kwargs and "error_message" not in kwargs:
            kwargs["error_message"] = kwargs.pop("error")
        if "completed_at" in kwargs and "executed_at" not in kwargs:
            kwargs["executed_at"] = kwargs.pop("completed_at")

        super().__init__(**kwargs)

    @property
    def step_order(self) -> int:
        return self.step_index

    @step_order.setter
    def step_order(self, val: int) -> None:
        self.step_index = val

    @property
    def result(self) -> Any:
        return self.output_data

    @result.setter
    def result(self, val: Any) -> None:
        self.output_data = val

    @property
    def error(self) -> str | None:
        return self.error_message

    @error.setter
    def error(self, val: str | None) -> None:
        self.error_message = val

    @property
    def completed_at(self) -> datetime | None:
        return self.executed_at

    @completed_at.setter
    def completed_at(self, val: datetime | None) -> None:
        self.executed_at = val

    def __repr__(self) -> str:
        return f"<SagaStepLog {self.step_name} index={self.step_index} status={self.status}>"


class SagaStep(Base):
    """Một bước trong Saga truyền thống (giữ tương thích ngược)."""

    __tablename__ = "saga_steps"
    __table_args__ = ({"extend_existing": True},)

    id: str = Column(GUID(), primary_key=True, default=lambda: str(uuid.uuid4()))
    saga_id: str = Column(
        GUID(),
        ForeignKey("saga_instances.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    step_name: str = Column(String(128), nullable=False)
    status: str = Column(
        String(32),
        nullable=False,
        default="pending",
    )  # pending | done | failed | compensated
    action_json: Any = Column(JSONOrText, nullable=False, default=dict)
    compensate_json: Any = Column(JSONOrText, nullable=False, default=dict)
    retry_count: int = Column(Integer, nullable=False, default=0)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )
    completed_at = Column(DateTime(timezone=True), nullable=True)

    saga = relationship("SagaInstance", back_populates="steps")

    def __repr__(self) -> str:
        return f"<SagaStep {self.step_name} status={self.status}>"


class CompensatingLog(Base):
    """Nhật ký hành động bù trừ (giữ tương thích ngược)."""

    __tablename__ = "compensating_logs"
    __table_args__ = ({"extend_existing": True},)

    id: str = Column(GUID(), primary_key=True, default=lambda: str(uuid.uuid4()))
    saga_id: str = Column(
        GUID(),
        ForeignKey("saga_instances.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    step_name: str = Column(String(128), nullable=False)
    action: str = Column(String(64), nullable=False)
    status: str = Column(
        String(32),
        nullable=False,
        default="pending",
    )  # pending | done | failed
    detail_json: Any = Column(JSONOrText, nullable=False, default=dict)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )

    saga = relationship("SagaInstance", back_populates="compensations")

    def __repr__(self) -> str:
        return f"<CompensatingLog {self.step_name} action={self.action} status={self.status}>"


# Aliases matching PROJECT.md and E2E test contracts
SagaInstanceRecord = SagaInstance
SagaStepLogRecord = SagaStepLog
