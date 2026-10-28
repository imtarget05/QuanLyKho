"""Stocktake service - nghiệp vụ kiểm kê kho."""

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal

from app.domain.approval import ApprovalWorkflow
from app.domain.exceptions import (
    DomainError,
    InvalidStateTransitionError,
    NotFoundError,
)
from app.domain.inventory import (
    ItemId,
    Movement,
    Quantity,
    Stocktake,
    StocktakeLine,
    StocktakeStatus,
    UserId,
)
from app.repositories.inventory_repository import (
    BalanceRepository,
    ItemRepository,
    MovementRepository,
    StocktakeLineRepository,
    StocktakeRepository,
)
from app.repositories.location_repository import LocationRepository
from app.repositories.user_repository import UserRepository


@dataclass(frozen=True)
class StocktakeLineResponse:
    """Dòng kiểm kê - frontend response."""
    id: str
    item_id: str
    item_name: str
    item_sku: str
    opening_qty: float
    received_qty: float
    used_qty: float
    counted_qty: float
    variance: float


@dataclass(frozen=True)
class StocktakeResponse:
    """Phiên kiểm kê - frontend response."""
    id: str
    number: str
    location_id: str
    location_name: str
    business_date: str
    shift_code: str
    status: str
    maker_id: str
    maker_name: str
    approver_id: str | None
    approver_name: str | None
    note: str | None
    lines: list[StocktakeLineResponse]
    total_counted_qty: float
    total_opening_qty: float
    total_variance: float
    created_at: str
    completed_at: str | None


class StocktakeService:
    """
    Nghiệp vụ kiểm kê kho (stocktake).
    """

    def __init__(
        self,
        stocktake_repo: StocktakeRepository,
        line_repo: StocktakeLineRepository,
        item_repo: ItemRepository,
        balance_repo: BalanceRepository,
        movement_repo: MovementRepository,
        location_repo: LocationRepository,
        user_repo: UserRepository,
    ):
        self.stocktake_repo = stocktake_repo
        self.line_repo = line_repo
        self.item_repo = item_repo
        self.balance_repo = balance_repo
        self.movement_repo = movement_repo
        self.location_repo = location_repo
        self.user_repo = user_repo

    def _get_user_name(self, user_id: str) -> str:
        user = self.user_repo.get(user_id)
        return user.name if user else "?"

    def _to_response(self, stocktake: Stocktake, location_id: str) -> StocktakeResponse:
        """Chuyển đổi sang frontend response."""
        location = self.location_repo.get(location_id)
        location_name = location.name if location else "?"

        lines = self.line_repo.list_by_stocktake(stocktake.id)

        total_counted_qty = 0
        total_opening_qty = 0
        total_variance = 0

        lines_response = []
        for line in lines:
            total_counted_qty += float(line.counted_qty.value)
            total_opening_qty += float(line.opening_qty.value)
            total_variance += float(line.variance.value)

            lines_response.append(StocktakeLineResponse(
                id=line.id,
                item_id=line.item_id.value,
                item_name=line.item_id.value,
                item_sku=line.item_id.value,
                opening_qty=float(line.opening_qty.value),
                received_qty=float(line.received_qty.value),
                used_qty=float(line.used_qty.value),
                counted_qty=float(line.counted_qty.value),
                variance=float(line.variance.value),
        ))

        return StocktakeResponse(
            id=stocktake.id,
            number=stocktake.id,
            location_id=stocktake.location_id.value,
            location_name=location_name,
            business_date=str(stocktake.business_date),
            shift_code=stocktake.shift_code.value,
            status=stocktake.status.value,
            maker_id=stocktake.maker_id.value,
            maker_name=self._get_user_name(stocktake.maker_id.value),
            approver_id=stocktake.approver_id.value if stocktake.approver_id else None,
            approver_name=stocktake.approver_id.value and self._get_user_name(stocktake.approver_id.value) if stocktake.approver_id else None,
            note=stocktake.note,
            lines=lines_response,
            total_counted_qty=total_counted_qty,
            total_opening_qty=total_opening_qty,
            total_variance=total_variance,
            created_at=stocktake.created_at.isoformat() if stocktake.created_at else "",
            completed_at=stocktake.completed_at.isoformat() if stocktake.completed_at else None,
        )


    def create_stocktake(
        self,
        user_id: str,
        location_id: str,
        business_date: date,
        shift_code: str,
        note: str | None = None,
    ) -> StocktakeResponse:
        """
        Tạo phiên kiểm kê mới.
        """
        # Check open stocktake already exists
        existing = self.stocktake_repo.get_open_by_location_shift(
            location_id, business_date, shift_code
        )
        if existing:
            raise DomainError("STOCKTAKE_EXISTS", "Đã có phiên kiểm kê mở tại kho này")

        # Tạo stocktake domain
        stocktake_id = f"st_{uuid.uuid4().hex[:12]}"

        stocktake = Stocktake.create(
            id=stocktake_id,
            location_id=location_id,
            business_date=business_date,
            shift_code=shift_code,
            status=StocktakeStatus.OPEN,
            maker_id=user_id,
            note=note,
            version=1,
        )

        # Lưu
        saved = self.stocktake_repo.add(stocktake)

        return self._to_response(saved, location_id)

    def submit_stocktake(
        self,
        stocktake_id: str,
        user_id: str,
        lines: list[dict],
    ) -> StocktakeResponse:
        """
        Gửi phiếu kiểm kê sau khi hoàn thành.
        """
        stocktake = self.stocktake_repo.get(stocktake_id)
        if stocktake is None:
            raise NotFoundError("Phiên kiểm kê", stocktake_id)

        if not stocktake.can_submit(user_id):
            raise InvalidStateTransitionError(
                subject="stocktake", from_status=stocktake.status.value, to_status="submitted"
            )

        # Lưu dòng
        for line_data in lines:
            item_id = line_data["item_id"]
            # Tìm item
            item = self.item_repo.get(item_id)
            if item is None:
                raise NotFoundError("Mặt hàng", item_id)

            # Tính lý thuyết
            theoretical_qty = Quantity(
                line_data.get("opening", 0) +
                line_data.get("received", 0) -
                line_data.get("used", 0)
            )

            line = StocktakeLine(
                id=uuid.uuid4().hex[:12],
                stocktake_id=stocktake_id,
                item_id=ItemId(item_id),
                location_id=stocktake.location_id,
                opening_qty=Quantity(line_data.get("opening", 0)),
                received_qty=Quantity(line_data.get("received", 0)),
                used_qty=Quantity(line_data.get("used", 0)),
                theoretical_qty=theoretical_qty,
                counted_qty=Quantity(line_data.get("counted", 0)),
                variance=Quantity(0),
            )

            self.line_repo.add(line)

        # Cập nhật status
        stocktake.status = StocktakeStatus.SUBMITTED
        stocktake.version += 1
        self.stocktake_repo.update(stocktake)

        return self._to_response(stocktake, stocktake.location_id.value)
    def approve_stocktake(
        self,
        stocktake_id: str,
        approver_id: str,
        reason: str | None = None,
    ) -> StocktakeResponse:
        """
        Duyệt phiên kiểm kê - áp dụng biến động tồn.
        """
        stocktake = self.stocktake_repo.get(stocktake_id)
        if stocktake is None:
            raise NotFoundError("Phiên kiểm kê", stocktake_id)

        if not stocktake.can_approve(approver_id):
            raise InvalidStateTransitionError(
                subject="stocktake", from_status=stocktake.status.value, to_status="approved"
            )

        # Tạo approval workflow
        approval = ApprovalWorkflow(
            subject_type="stocktake",
            subject_id=stocktake_id,
            maker_id=stocktake.maker_id.value,
            approver_id=approver_id,
            status="approved",
        )
        approval.approve(approver_id, reason)

        # Lấy danh sách dòng
        lines = self.line_repo.list_by_stocktake(stocktake_id)
        for line in lines:
            # Tính số lượng áp dụng
            applied_qty = Decimal(str(line.counted_qty.value)) - Decimal(str(line.opening_qty.value))

            if applied_qty > 0:
                # Nhập: increasing stock
                movement = Movement.create_receipt(
                    movement_id=f"mv_{uuid.uuid4().hex[:12]}",
                    request_id=stocktake_id,
                    line_id=line.id,
                    item_id=line.item_id,
                    location_id=stocktake.location_id,
                    quantity=Quantity(applied_qty),
                    posted_at=datetime.now(UTC),
                )
                self.movement_repo.add(movement)
            elif applied_qty < 0:
                # Xuất
                movement = Movement.create_issue(
                    movement_id=f"mv_{uuid.uuid4().hex[:12]}",
                    request_id=stocktake_id,
                    line_id=line.id,
                    item_id=line.item_id,
                    location_id=stocktake.location_id,
                    quantity=Quantity(-applied_qty),
                    posted_at=datetime.now(UTC),
                )
                self.movement_repo.add(movement)

            # Cập nhật balance
            balance = self.balance_repo.get_by_location_item(
                stocktake.location_id.value,
                line.item_id.value,
            )
            if balance:
                new_qty = balance.quantity.value + applied_qty
                balance.quantity = Quantity(new_qty)
                balance.version += 1
                self.balance_repo.upsert(
                    stocktake.location_id.value,
                    line.item_id.value,
                    float(new_qty),
                )

        # Cập nhật stocktake
        stocktake.status = StocktakeStatus.CLOSED
        stocktake.approver_id = UserId(approver_id)
        stocktake.completed_at = datetime.now(UTC)
        stocktake.version += 1
        self.stocktake_repo.update(stocktake)

        return self._to_response(stocktake, stocktake.location_id.value)

    def get(self, stocktake_id: str) -> StocktakeResponse:
        """Lấy thông tin phiên kiểm kê."""
        stocktake = self.stocktake_repo.get(stocktake_id)
        if stocktake is None:
            raise NotFoundError("Phiên kiểm kê", stocktake_id)

        return self._to_response(stocktake, stocktake.location_id.value)

    def list(
        self,
        skip: int = 0,
        limit: int = 50,
        location_id: str | None = None,
        status: str | None = None,
    ) -> list[StocktakeResponse]:
        """Danh sách phiên kiểm kê."""
        stocktakes = self.stocktake_repo.list(
            skip=skip,
            limit=limit,
            location_id=location_id,
            status=status,
        )
        return [
            self._to_response(st, st.location_id.value)
            for st in stocktakes
        ]
