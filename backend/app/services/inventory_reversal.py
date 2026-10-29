"""Reverse (đảo chiều) inventory movement / LotMovement.

Đảo chiều KHÔNG sửa entry cũ — tạo một movement mới có
quantity_signed ngược chiều, gắn `reversed_from` để truy vết.
Có thể phối hợp với approval pipeline nếu quyền cấp phù hợp.

Hợp đồng:
- `reverse_movement_service`: tạo movement đảo chiều (có thể gắn approval).
- Kiểm tra đầy đủ số lượng (không vượt quá tồn hiện có).
- Cập nhật `LotBalance` (hoặc `Balance`) transactionally trong cùng DB txn.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.inventory import (
    Balance,
    LotBalance,
    Movement,
)
from app.services import idempotency  # noqa: F401


class MovementReversalService:
    """Service để đảo chiều LotMovement / Movement."""

    def __init__(
        self,
        user_id: str,
        movement_id: str,
        reason: str,
        db: AsyncSession,
        approve_caps: tuple[str, ...],
    ) -> None:
        self.user_id = user_id
        self.movement_id = movement_id
        self.reason = reason
        self.db = db
        self.approve_caps = approve_caps

    async def execute(self) -> dict[str, Any]:
        """Thực hiện đảo chiều movement và trả về resultado."""
        stmt = select(Movement).where(Movement.id == self.movement_id)
        result = await self.db.execute(stmt)
        movement = result.scalar_one_or_none()
        if movement is None:
            raise ValueError(f"Movement {self.movement_id} không tồn tại.")
        if movement.posted_at is None:
            raise ValueError("Movement gốc chưa được post (không có posted_at).")

        original_qty = movement.quantity_signed
        reversed_qty = -original_qty

        balance = await self._load_balance(movement)
        available = self._compute_available(balance, movement)
        if abs(reversed_qty) > available:
            raise ValueError(
                f"Số lượng đảo chiều ({reversed_qty}) vượt quá tồn hiện có ({available})."
            )

        reversed_movement = await self._create_reversed_movement(movement, reversed_qty)
        await self._update_balance(balance, movement, reversed_movement)

        if not self._has_approval_capability():
            approval = await self._create_reversal_approval(reversed_movement)
            return {
                **dict(reversed_movement.__dict__),
                "approval_id": approval.id if approval else None,
            }

        return dict(reversed_movement.__dict__)

    async def _load_balance(self, movement: Movement) -> Any:
        if movement.lot_number:
            stmt = select(LotBalance).where(
                LotBalance.location_id == movement.location_id,
                LotBalance.item_id == movement.item_id,
                LotBalance.lot_no == movement.lot_number,
            )
            result = await self.db.execute(stmt)
            return result.scalar_one_or_none()
        from app.models.inventory import Balance

        stmt = select(Balance).where(
            Balance.location_id == movement.location_id,
            Balance.item_id == movement.item_id,
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    def _compute_available(self, balance: Any, movement: Movement) -> Decimal:
        if isinstance(balance, LotBalance):
            return balance.quantity
        if isinstance(balance, Balance):
            return balance.quantity
        return Decimal("0")


    async def _create_reversed_movement(self, movement: Movement, reversed_qty: Decimal):
        from app.models.inventory import LotMovement, LotMovementLine

        reversed_movement = LotMovement(
            id=uuid4(),
            location_id=movement.location_id,
            item_id=movement.item_id,
            request_id=movement.request_id,
            line_id=movement.line_id,
            quantity_signed=reversed_qty,
            posted_at=movement.posted_at,
        )
        self.db.add(reversed_movement)
        await self.db.flush()

        reversed_line = LotMovementLine(
            id=uuid4(),
            movement_id=reversed_movement.id,
            item_id=movement.item_id,
            quantity=abs(reversed_qty),
        )
        self.db.add(reversed_line)
        await self.db.flush()

        reversed_movement.lot_movement_line_id = reversed_line.id
        return reversed_movement

    async def _update_balance(self, balance, movement, reversed_movement):
        if isinstance(balance, LotBalance):
            balance.quantity = (
                balance.quantity + (movement.quantity_signed + reversed_movement.quantity_signed)
            )
        elif isinstance(balance, Balance):
            balance.quantity = (
                balance.quantity + (movement.quantity_signed + reversed_movement.quantity_signed)
            )

    def _has_approval_capability(self) -> bool:
        return bool(self.approve_caps)

    async def _create_reversal_approval(self, movement) -> Any:
        from app.models.approval import ApprovalDecision

        approval = ApprovalDecision(
            id=uuid4(),
            subject_type="LotMovement",
            subject_id=movement.id,
            actor_id=self.user_id,
            decision="pending",
            reason=f"Reversal của phiếu {movement.id}",
            created_at=self._utcnow(),
        )
        self.db.add(approval)
        await self.db.commit()
        return approval

    @staticmethod
    def _utcnow():
        from datetime import UTC, datetime

        return datetime.now(UTC)
