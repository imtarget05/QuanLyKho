"""Request (invoice) domain models - phiếu nhập - xuất - điều chỉnh kho."""

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum


class RequestKind(StrEnum):
    """Loại phiếu tồn kho."""
    PURCHASE = "purchase"
    SALES = "sales"
    ADJUSTMENT = "adjustment"
    TRANSFER = "transfer"
    RETURN = "return"


class RequestStatus(StrEnum):
    """Trạng thái phiếu yêu cầu."""
    DRAFT = "draft"
    PENDING = "pending"
    POSTED = "posted"
    REJECTED = "rejected"
    CANCELLED = "cancelled"
    APPROVED = "approved"
    AWAITING_APPROVAL = "awaiting_approval"


@dataclass(frozen=True)
class InventoryRequestLine:
    """Dòng phiếu yêu cầu tồn kho (frontend-facing)."""
    id: str
    item_id: str
    quantity: float
    unit_price: float
    note: str | None = None


@dataclass(frozen=True)
class InventoryRequest:
    """Phiếu yêu cầu tồn kho (frontend-facing)."""
    id: str
    number: str
    kind: RequestKind
    status: RequestStatus
    location_id: str
    location_name: str
    lines: list['InventoryRequestLine']
    requested_by: str
    requested_by_name: str
    total_amount: float
    note: str | None = None
    created_at: datetime = datetime.now(UTC)
    updated_at: datetime = datetime.now(UTC)
