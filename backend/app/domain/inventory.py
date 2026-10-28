"""Inventory domain layer - business rules cho kho.

Pure Python, không phụ thuộc SQLAlchemy/FastAPI.
Tất cả logic: tính toán tồn, validation, MAC, FEFO, trạng thái phiếu.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum


class RequestKind(StrEnum):
    RECEIPT = "receipt"      # Nhập kho
    ISSUE = "issue"          # Xuất kho
    TRANSFER = "transfer"    # Chuyển kho
    ADJUSTMENT = "adjustment"  # Điều chỉnh tồn


class RequestStatus(StrEnum):
    DRAFT = "draft"
    PENDING = "pending"
    POSTED = "posted"
    REJECTED = "rejected"
    RETURNED = "returned"
    CANCELLED = "cancelled"


class ShiftCode(StrEnum):
    MORNING = "morning"   # 07:30–15:00
    AFTERNOON = "afternoon"  # 15:00–23:00
    SPLIT = "split"       # 07:30–18:00


class StocktakeStatus(StrEnum):
    OPEN = "open"
    SUBMITTED = "submitted"
    CLOSED = "closed"
@dataclass(frozen=True)
class ItemId:
    value: str


@dataclass(frozen=True)
class LocationId:
    value: str


@dataclass(frozen=True)
class UserId:
    value: str


@dataclass(frozen=True)
class Money:
    """Tiền tệ, luôn string với 2 chữ số thập phân."""
    amount: Decimal
    currency: str = "VND"

    def __post_init__(self) -> None:
        if self.amount < 0:
            raise ValueError("Money amount cannot be negative")

    def __add__(self, other: Money) -> Money:
        if self.currency != other.currency:
            raise ValueError("Cannot add different currencies")
        return Money(self.amount + other.amount, self.currency)

    def __sub__(self, other: Money) -> Money:
        if self.currency != other.currency:
            raise ValueError("Cannot subtract different currencies")
        result = self.amount - other.amount
        if result < 0:
            raise ValueError("Result cannot be negative")
        return Money(result, self.currency)

    def __mul__(self, multiplier: Decimal) -> Money:
        return Money(self.amount * multiplier, self.currency)

    def __str__(self) -> str:
        return f"{self.amount:.2f} {self.currency}"


@dataclass(frozen=True)
class Quantity:
    """Số lượng, luôn 3 chữ số thập phân."""

    value: Decimal

    def __post_init__(self) -> None:
        if self.value < 0:
            raise ValueError("Quantity cannot be negative")

    def __add__(self, other: Quantity) -> Quantity:
        return Quantity(self.value + other.value)

    def __sub__(self, other: Quantity) -> Quantity:
        result = self.value - other.value
        if result < 0:
            raise ValueError("Quantity cannot be negative after subtraction")
        return Quantity(result)

    def __mul__(self, multiplier: Decimal) -> Quantity:
        return Quantity(self.value * multiplier)

    def __str__(self) -> str:
        return f"{self.value:.3f}"
_ZERO_QTY = Quantity(Decimal("0"))


@dataclass
class Item:
    """Mặt hàng trong catalog."""

    id: ItemId
    sku: str
    name: str
    unit: str  # Đơn vị cơ sở (ví dụ: 'chai', 'thùng', 'kg')
    category: str | None = None
    cost_price: Money | None = None
    selling_price: Money | None = None
    min_stock: Quantity = _ZERO_QTY
    max_stock: Quantity | None = None
    tracked_serial: bool = False
    active: bool = True

    @classmethod
    def create(
        cls,
        item_id: str,
        sku: str,
        name: str,
        unit: str,
        category: str | None = None,
        cost_price: Money | None = None,
        selling_price: Money | None = None,
        min_stock: Quantity = _ZERO_QTY,
        tracked_serial: bool = False,
    ) -> Item:
        return cls(
            id=ItemId(item_id),
            sku=sku,
            name=name,
            unit=unit,
            category=category,
            cost_price=cost_price,
            selling_price=selling_price,
            min_stock=min_stock,
            tracked_serial=tracked_serial,
            active=True,
        )


@dataclass
class Location:
    """Kho / địa điểm lưu trữ."""

    id: LocationId
    code: str
    name: str
    active: bool = True

    @classmethod
    def create(cls, location_id: str, code: str, name: str) -> Location:
        return cls(id=LocationId(location_id), code=code, name=name, active=True)


@dataclass
class Balance:
    """Số lượng tồn tại một kho (derived cache, đọc từ movements)."""

    location_id: LocationId
    item_id: ItemId
    quantity: Quantity
    version: int = 1

    def add(self, qty: Quantity) -> None:
        self.quantity = self.quantity + qty
        self.version += 1

    def subtract(self, qty: Quantity) -> None:
        self.quantity = self.quantity - qty
        self.version += 1
@dataclass
class Movement:
    """Bút toán biến động tồn - bất biến, không được sửa xóa."""

    id: str
    request_id: str
    line_id: str | None
    item_id: ItemId
    location_id: LocationId
    quantity_signed: Decimal  # Dấu dương = nhập, dấu âm = xuất
    posted_at: datetime
    reversal_of: str | None = None  # ID movement bị đảo (nếu là reversal)

    @classmethod
    def create_receipt(
        cls,
        movement_id: str,
        request_id: str,
        line_id: str,
        item_id: ItemId,
        location_id: LocationId,
        quantity: Quantity,
        posted_at: datetime,
    ) -> Movement:
        return cls(
            id=movement_id,
            request_id=request_id,
            line_id=line_id,
            item_id=item_id,
            location_id=location_id,
            quantity_signed=quantity.value,
            posted_at=posted_at,
        )

    @classmethod
    def create_issue(
        cls,
        movement_id: str,
        request_id: str,
        line_id: str,
        item_id: ItemId,
        location_id: LocationId,
        quantity: Quantity,
        posted_at: datetime,
    ) -> Movement:
        return cls(
            id=movement_id,
            request_id=request_id,
            line_id=line_id,
            item_id=item_id,
            location_id=location_id,
            quantity_signed=-quantity.value,
            posted_at=posted_at,
        )

    @classmethod
    def create_reversal(
        cls,
        movement_id: str,
        request_id: str,
        line_id: str | None,
        item_id: ItemId,
        location_id: LocationId,
        quantity_signed: Decimal,
        posted_at: datetime,
        reversal_of: str,
    ) -> Movement:
        return cls(
            id=movement_id,
            request_id=request_id,
            line_id=line_id,
            item_id=item_id,
            location_id=location_id,
            quantity_signed=quantity_signed,
            posted_at=posted_at,
            reversal_of=reversal_of,
        )
@dataclass
class StocktakeLine:
    """Dòng kiểm kê trong một phiên."""

    id: str
    stocktake_id: str
    item_id: ItemId
    location_id: LocationId
    opening_qty: Quantity
    received_qty: Quantity
    used_qty: Quantity
    theoretical_qty: Quantity
    counted_qty: Quantity
    variance: Quantity

    @classmethod
    def calculate_theoretical(
        cls,
        opening: Quantity,
        received: Quantity,
        used: Quantity,
    ) -> Quantity:
        return Quantity(opening.value + received.value - used.value)

    def calculate_variance(self) -> Quantity:
        return Quantity(self.counted_qty.value - self.theoretical_qty.value)


@dataclass
class Stocktake:
    """Phiên kiểm kê - một ca làm việc tại một kho."""

    id: str
    location_id: LocationId
    business_date: date
    shift_code: ShiftCode
    status: StocktakeStatus
    maker_id: UserId
    approver_id: UserId | None = None
    version: int = 1
    note: str | None = None
    adjustment_request_id: str | None = None
    completed_at: datetime | None = None

    def can_submit(self, user_id: UserId) -> bool:
        if self.status != StocktakeStatus.OPEN:
            return False
        return self.maker_id == user_id

    def can_approve(self, user_id: UserId) -> bool:
        if self.status != StocktakeStatus.SUBMITTED:
            return False
        if self.maker_id == user_id:
            return False  # Maker không tự duyệt
        return True

    def can_edit_lines(self) -> bool:
        return self.status == StocktakeStatus.OPEN
    LOCKED = "locked"