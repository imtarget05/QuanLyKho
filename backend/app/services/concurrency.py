"""Kiểm soát đồng thời tài chính (interview-prep 02/01 §7, 02/05 §5, 03/06).

Hai lớp bảo vệ số dư / tồn kho trước xung đột truy cập cùng thời điểm:

- Pessimistic: ``SELECT ... FOR UPDATE`` trên dòng ``inv_balances`` trong
  transaction, chặn các luồng khác đọc/ghi cùng dòng cho đến khi commit.
- Optimistic: cột ``version`` trên ``inv_balances``;
  ``UPDATE ... SET quantity = ..., version = version + 1
  WHERE version = :expected_version``; nếu rowcount = 0 ném
  ``ConcurrencyConflict``.

Cùng cung cấp ``reserve_balance`` / ``commit_reservation`` /
``release_reservation`` (Reservation / Escrow pattern, 02/05 §5.2) dùng cột
``reserved_quantity`` hiện có.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from decimal import Decimal
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.inventory import Balance


class ConcurrencyConflict(Exception):
    """Phiên cũ: dòng đã được luồng khác cập nhật (optimistic lock failed)."""


class InsufficientBalance(Exception):
    """Số dư khả dụng không đủ để thực hiện thao tác."""


async def _load_balance(
    session: AsyncSession, location_id: Any, item_id: Any, *, for_update: bool
) -> Balance | None:
    stmt = select(Balance).where(
        Balance.location_id == location_id, Balance.item_id == item_id
    )
    if for_update:
        stmt = stmt.with_for_update()
    result = await session.execute(stmt)
    return result.scalars().first()


async def _ensure_balance(
    session: AsyncSession, location_id: Any, item_id: Any, *, for_update: bool
) -> Balance:
    balance = await _load_balance(session, location_id, item_id, for_update=for_update)
    if balance is None:
        balance = Balance(
            location_id=location_id,
            item_id=item_id,
            quantity=Decimal("0"),
            reserved_quantity=Decimal("0"),
            version=1,
        )
        session.add(balance)
        await session.flush()
    return balance


@asynccontextmanager
async def acquire_balance_lock(
    session: AsyncSession,
    location_id: Any,
    item_id: Any,
    *,
    mode: str = "pessimistic",
):
    """Khóa dòng tồn kho trong transaction.

    - ``pessimistic``: ``SELECT ... FOR UPDATE``.
    - ``optimistic``: đọc dòng, caller chịu trách nhiệm kiểm tra ``version`` khi
      ghi (xem ``apply_quantity_change``).

    Trả về đối tượng ``Balance`` đã được khóa (pessimistic) hoặc đọc (optimistic).
    """
    balance = await _ensure_balance(session, location_id, item_id, for_update=(mode == "pessimistic"))
    try:
        yield balance
    finally:
        pass


async def apply_quantity_change(
    session: AsyncSession,
    location_id: Any,
    item_id: Any,
    delta: Decimal,
    *,
    expected_version: int | None = None,
    mode: str = "pessimistic",
) -> Balance:
    """Thay đổi số dư (delta dương = cộng, âm = trừ) với khóa đồng thời.

    Pessimistic: lock dòng rồi cộng trực tiếp.
    Optimistic: conditional UPDATE theo version; ném ConcurrencyConflict nếu
    phiên cũ.
    """
    if mode == "pessimistic":
        async with acquire_balance_lock(
            session, location_id, item_id, mode="pessimistic"
        ) as balance:
            new_qty = (balance.quantity or Decimal("0")) + delta
            if new_qty < 0:
                raise InsufficientBalance(
                    f"Số dư không đủ: {balance.quantity} + {delta} < 0"
                )
            balance.quantity = new_qty
            balance.version = int(balance.version or 1) + 1
            await session.flush()
            return balance

    if mode == "optimistic":
        balance = await _ensure_balance(
            session, location_id, item_id, for_update=False
        )
        current_version = expected_version if expected_version is not None else int(
            balance.version or 1
        )
        new_qty = (balance.quantity or Decimal("0")) + delta
        if new_qty < 0:
            raise InsufficientBalance(
                f"Số dư không đủ: {balance.quantity} + {delta} < 0"
            )
        result = await session.execute(
            update(Balance)
            .where(
                Balance.location_id == location_id,
                Balance.item_id == item_id,
                Balance.version == current_version,
            )
            .values(quantity=new_qty, version=current_version + 1)
        )
        if result.rowcount == 0:
            raise ConcurrencyConflict(
                f"Phiên cũ: số dư loc={location_id} item={item_id} đã bị thay đổi"
            )
        await session.flush()
        updated = await _load_balance(
            session, location_id, item_id, for_update=False
        )
        return updated

    raise ValueError(f"Chế độ khóa không hỗ trợ: {mode!r}")


async def reserve_balance(
    session: AsyncSession,
    location_id: Any,
    item_id: Any,
    amount: Decimal,
) -> Balance:
    """Phong tỏa (reserve) số dư: reserved_quantity tăng, quantity không đổi.

    Dùng cho giai đoạn Try của TCC (02/05 §5.2). Số dư khả dụng
    (quantity - reserved_quantity) phải >= amount.
    """
    if amount < 0:
        raise ValueError("amount phải không âm")
    async with acquire_balance_lock(session, location_id, item_id, mode="pessimistic") as balance:
        available = (balance.quantity or Decimal("0")) - (
            balance.reserved_quantity or Decimal("0")
        )
        if available < amount:
            raise InsufficientBalance(
                f"Không đủ khả dụng để phong tỏa: available={available} amount={amount}"
            )
        balance.reserved_quantity = (balance.reserved_quantity or Decimal("0")) + amount
        balance.version = int(balance.version or 1) + 1
        await session.flush()
        return balance


async def commit_reservation(
    session: AsyncSession,
    location_id: Any,
    item_id: Any,
    amount: Decimal,
) -> Balance:
    """Xác nhận phong tôi: giảm quantity và reserved_quantity (giai đoạn Confirm)."""
    if amount < 0:
        raise ValueError("amount phải không âm")
    async with acquire_balance_lock(session, location_id, item_id, mode="pessimistic") as balance:
        if (balance.reserved_quantity or Decimal("0")) < amount:
            raise InsufficientBalance(
                f"Không đủ reservations để xác nhận: reserved={balance.reserved_quantity} amount={amount}"
            )
        if (balance.quantity or Decimal("0")) < amount:
            raise InsufficientBalance(
                f"Số dư không đủ để xác nhận: quantity={balance.quantity} amount={amount}"
            )
        balance.quantity = (balance.quantity or Decimal("0")) - amount
        balance.reserved_quantity = (balance.reserved_quantity or Decimal("0")) - amount
        balance.version = int(balance.version or 1) + 1
        await session.flush()
        return balance


async def release_reservation(
    session: AsyncSession,
    location_id: Any,
    item_id: Any,
    amount: Decimal,
) -> Balance:
    """Hủy phong tôi: giảm reserved_quantity (giai đoạn Cancel của TCC)."""
    if amount < 0:
        raise ValueError("amount phải không âm")
    async with acquire_balance_lock(session, location_id, item_id, mode="pessimistic") as balance:
        if (balance.reserved_quantity or Decimal("0")) < amount:
            raise InsufficientBalance(
                f"Không đủ reservations để hủy: reserved={balance.reserved_quantity} amount={amount}"
            )
        balance.reserved_quantity = (balance.reserved_quantity or Decimal("0")) - amount
        balance.version = int(balance.version or 1) + 1
        await session.flush()
        return balance


def available_quantity(balance: Balance) -> Decimal:
    """Số dư khả dụng = quantity - reserved_quantity."""
    return max(
        Decimal("0"), (balance.quantity or Decimal("0")) - (balance.reserved_quantity or Decimal("0"))
    )
