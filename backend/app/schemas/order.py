"""Pydantic schemas for RetailOps Order API.

All monetary values are decided by backend business service; LLM may propose
but never set price, tax, or total.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, condecimal


class OrderLineBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_id: UUID = Field(..., description="SKU/item ID from catalog")
    location_id: UUID = Field(..., description="Branch/location to fulfill from")
    quantity: condecimal(gt=0, max_digits=14, decimal_places=3) = Field(
        ..., description="Số lượng yêu cầu"
    )


class OrderLineRead(OrderLineBase):
    id: UUID
    order_id: UUID
    unit_price: Decimal
    line_total: Decimal


class OrderQuoteRequest(BaseModel):
    """Agent asks backend to quote (read/draft) before user confirmation."""

    model_config = ConfigDict(extra="forbid")

    branch_id: UUID = Field(..., description="Chi nhánh đặt hàng")
    lines: list[OrderLineBase] = Field(..., min_length=1, description="Dòng hàng")
    customer_ref: Optional[str] = Field(
        default=None, max_length=128, description="Mã tham chiếu khách hàng (tuỳ chọn)"
    )
    idempotency_key: Optional[str] = Field(
        default=None, max_length=128, description="Khóa idempotency để tránh đơn trùng"
    )


class OrderQuoteResponse(BaseModel):
    """Server-computed quote: price, total, draft_id, confirmation_token, expiry."""

    model_config = ConfigDict(extra="forbid")

    draft_id: UUID
    confirmation_token: str
    expires_at: str
    lines: list[OrderLineRead]
    subtotal: Decimal
    tax: Decimal
    total_amount: Decimal
    currency: str = "VND"
    # Stock check result per line (backend decision, not LLM).
    stock_ok: bool
    insufficient_items: list[dict] = Field(default_factory=list)


class OrderConfirmRequest(BaseModel):
    """User confirms a draft order. Backend re-validates stock/price/permission."""

    model_config = ConfigDict(extra="forbid")

    draft_id: UUID = Field(..., description="Mã đơn nháp đã được quote")
    confirmation_token: str = Field(..., description="Token xác nhận gắn với draft")
    idempotency_key: Optional[str] = Field(
        default=None, max_length=128, description="Khóa idempotency cho commit"
    )


class OrderCancelRequest(BaseModel):
    """Request to cancel an order. May require manager approval per policy."""

    model_config = ConfigDict(extra="forbid")

    order_id: UUID = Field(..., description="Mã đơn hàng cần hủy")
    reason: Optional[str] = Field(default=None, max_length=1024, description="Lý do hủy")
    idempotency_key: Optional[str] = Field(
        default=None, max_length=128, description="Khóa idempotency cho hủy"
    )


class OrderRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    branch_id: UUID
    actor_id: UUID
    customer_ref: Optional[str]
    status: str
    subtotal: Decimal
    tax: Decimal
    total_amount: Decimal
    currency: str
    idempotency_key: Optional[str]
    confirmation_token: Optional[str]
    confirmation_at: Optional[str]
    confirmed_by: Optional[UUID]
    expires_at: Optional[str]
    cancel_reason: Optional[str]
    approval_required: bool
    approval_decision_id: Optional[UUID]
    created_at: str
    updated_at: str
