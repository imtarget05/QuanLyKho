"""Inventory domain services - business logic rules.

Thuộc domain layer, không phụ thuộc vào SQLAlchemy/FastAPI.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from .inventory import (
    Money,
    Quantity,
    RequestStatus,
    Stocktake,
    StocktakeStatus,
)


@dataclass(frozen=True)
class MacResult:
    """Kết quả tính giá vốn bình quân gia quyền (MAC)."""

    old_qty: Quantity
    old_cost: Money
    in_qty: Quantity
    in_cost: Money
    new_qty: Quantity
    new_cost: Money


class InventoryDomainService:
    """Nghiệp vụ kho: tính toán MAC, validate movement, trạng thái phiếu."""

    @staticmethod
    def calculate_mac(
        old_qty: Quantity,
        old_cost: Money,
        in_qty: Quantity,
        in_cost: Money,
    ) -> MacResult:
        """
        Tính giá vốn bình quân gia quyền (Weighted Average Cost - WACC).

        Công thức:
          C_new = (Q_old × C_old + Q_in × C_in) / (Q_old + Q_in)

        Nếu tổng số lượng = 0, trả về giá nhập.
        """
        old_qty_val = old_qty.value
        in_qty_val = in_qty.value
        total_qty_val = old_qty_val + in_qty_val

        if total_qty_val == 0:
            # Không có tồn, giá vốn = giá nhập
            return MacResult(
                old_qty=Quantity(Decimal("0")),
                old_cost=Money(Decimal("0")),
                in_qty=in_qty,
                in_cost=in_cost,
                new_qty=in_qty,
                new_cost=in_cost,
            )

        old_cost_val = old_cost.amount if old_cost else Decimal("0")
        in_cost_val = in_cost.amount

        new_cost_amount = (
            old_cost_val * old_qty_val + in_cost_val * in_qty_val
        ) / total_qty_val
        # Làm tròn đến 2 chữ số
        new_cost_amount = new_cost_amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        return MacResult(
            old_qty=old_qty,
            old_cost=old_cost or Money(Decimal("0")),
            in_qty=in_qty,
            in_cost=in_cost,
            new_qty=Quantity(total_qty_val),
            new_cost=Money(new_cost_amount),
        )

    @staticmethod
    def can_issue(
        available_qty: Quantity,
        requested_qty: Quantity,
    ) -> None:
        """Kiểm tra xem có thể xuất số lượng yêu cầu không."""
        if requested_qty.value > available_qty.value:
            from .exceptions import InsufficientStockError
            raise InsufficientStockError(
                item_id="unknown",
                location_id="unknown",
                requested=requested_qty.value,
                available=available_qty.value,
            )

    @staticmethod
    def can_transition_status(
        current: RequestStatus,
        target: RequestStatus,
    ) -> bool:
        """Kiểm tra xem chuyển trạng thái phiếu có hợp lệ không."""
        valid_transitions = {
            RequestStatus.DRAFT: {RequestStatus.PENDING, RequestStatus.CANCELLED},
            RequestStatus.PENDING: {
                RequestStatus.POSTED,
                RequestStatus.REJECTED,
                RequestStatus.RETURNED,
            },
            RequestStatus.RETURNED: {RequestStatus.PENDING},
            RequestStatus.POSTED: set(),
            RequestStatus.REJECTED: set(),
            RequestStatus.CANCELLED: set(),
        }
        return target in valid_transitions.get(current, set())

    @staticmethod
    def can_approve_stocktake(
        stocktake: Stocktake,
        user_id: str,
    ) -> bool:
        """Kiểm tra user có thể duyệt ca kiểm kê không."""
        if stocktake.status != StocktakeStatus.SUBMITTED:
            return False
        if stocktake.maker_id.value == user_id:
            return False  # Maker không tự duyệt
        return True

    @staticmethod
    def calculate_mac_for_receipt(
        current_balance_qty: Quantity,
        current_cost: Money | None,
        in_qty: Quantity,
        in_cost: Money,
    ) -> Money:
        """Tính MAC mới sau khi nhập hàng."""
        old_cost = current_cost or Money(Decimal("0"))
        result = InventoryDomainService.calculate_mac(
            old_qty=current_balance_qty,
            old_cost=old_cost,
            in_qty=in_qty,
            in_cost=in_cost,
        )
        return result.new_cost