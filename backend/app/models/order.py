"""Order domain models for RetailOps Agent MVP.

Single source of truth for customer orders within QuanLyKho modular monolith.
ADR-002: QuanLyKho owns inventory + order; no second order service.
ADR-003: Agent proposes, backend decides (price, stock, permission, commit).
ADR-004: User confirmation required before commit; manager approval for cancel.
"""

from __future__ import annotations

from decimal import Decimal
from enum import Enum as PyEnum
from typing import Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.base import Base, TimestampMixin, utc_now


class OrderStatus(PyEnum):
    """Business order lifecycle (agent draft state lives in LangGraph, not here)."""

    DRAFT = "draft"          # quote created, not yet confirmed by user
    CONFIRMED = "confirmed"  # user confirmed; stock decremented atomically
    CANCELLED = "cancelled"  # cancelled (with manager approval if policy requires)
    FULFILLED = "fulfilled"  # fulfilled (only if fulfillment backend exists later)


class Order(Base, TimestampMixin):
    """A customer order placed through RetailOps Agent or direct API."""

    __tablename__ = "retail_orders"

    id = Column(UUID(as_uuid=True), primary_key=True, index=True)
    # Tenant/branch scope — every order belongs to one branch/location.
    branch_id = Column(
        UUID(as_uuid=True),
        ForeignKey("org_branches.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    # Actor who created the order (sales employee / customer service).
    actor_id = Column(
        UUID(as_uuid=True),
        ForeignKey("iam_users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    # Optional end-customer reference (anonymous allowed; no PII forced).
    customer_ref = Column(String(128), nullable=True, index=True)
    status = Column(
        String(32),
        nullable=False,
        default=OrderStatus.DRAFT.value,
        index=True,
    )
    # Monetary totals decided by backend pricing service, not LLM.
    subtotal = Column(Numeric(14, 2), nullable=False, default=0)
    tax = Column(Numeric(14, 2), nullable=False, default=0)
    total_amount = Column(Numeric(14, 2), nullable=False, default=0)
    currency = Column(String(8), nullable=False, default="VND")
    # Idempotency: one key = one committed order. Same key+payload replays.
    idempotency_key = Column(String(128), nullable=True, index=True)
    idempotency_payload_hash = Column(String(64), nullable=True)
    # Confirmation binding: token issued at quote time, verified at commit.
    confirmation_token = Column(String(128), nullable=True, index=True)
    confirmation_at = Column(DateTime(timezone=True), nullable=True)
    confirmed_by = Column(
        UUID(as_uuid=True),
        ForeignKey("iam_users.id", ondelete="SET NULL"),
        nullable=True,
    )
    # TTL for draft; expired drafts are not committable.
    expires_at = Column(DateTime(timezone=True), nullable=True)
    # Reason for cancellation (user-facing).
    cancel_reason = Column(Text, nullable=True)
    # Manager approval for cancellation (subject_type=retail_order).
    approval_required = Column(Boolean, nullable=False, default=False)
    approval_decision_id = Column(
        UUID(as_uuid=True),
        ForeignKey("approval_decisions.id", ondelete="SET NULL"),
        nullable=True,
    )

    __table_args__ = (
        # Prevent double commit for the same idempotency key + payload.
        Index("uq_retail_order_idempotent", "idempotency_key", "idempotency_payload_hash",
              unique=True, postgresql_where=text("idempotency_key IS NOT NULL")),
        CheckConstraint("total_amount >= 0", name="retail_order_total_non_negative"),
        CheckConstraint("subtotal >= 0", name="retail_order_subtotal_non_negative"),
        CheckConstraint("tax >= 0", name="retail_order_tax_non_negative"),
    )

    actor = relationship("User", foreign_keys=[actor_id], lazy="selectin")
    confirmed_by_user = relationship("User", foreign_keys=[confirmed_by], lazy="selectin")
    approval_decision = relationship("ApprovalDecision", lazy="selectin")
    lines = relationship("OrderLine", back_populates="order", cascade="all, delete-orphan")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Order {self.id} status={self.status} total={self.total_amount}>"


class OrderLine(Base, TimestampMixin):
    """One line item within an order."""

    __tablename__ = "retail_order_lines"

    id = Column(UUID(as_uuid=True), primary_key=True, index=True)
    order_id = Column(
        UUID(as_uuid=True),
        ForeignKey("retail_orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    item_id = Column(
        UUID(as_uuid=True),
        ForeignKey("inv_items.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    location_id = Column(
        UUID(as_uuid=True),
        ForeignKey("inv_locations.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    quantity = Column(Numeric(14, 3), nullable=False, default=0)
    unit_price = Column(Numeric(14, 2), nullable=False, default=0)
    line_total = Column(Numeric(14, 2), nullable=False, default=0)

    __table_args__ = (
        CheckConstraint("quantity > 0", name="retail_order_line_quantity_positive"),
        CheckConstraint("unit_price >= 0", name="retail_order_line_price_non_negative"),
        CheckConstraint("line_total >= 0", name="retail_order_line_total_non_negative"),
    )

    order = relationship("Order", back_populates="lines")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<OrderLine order={self.order_id} item={self.item_id} qty={self.quantity}>"
