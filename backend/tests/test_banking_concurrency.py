"""Kiểm soát đồng thời: nhiều coroutine cùng cộng 1 đơn vị vào 1 balance
không làm sai lệch số dư (không lost-update, chặn race condition)."""

from __future__ import annotations

import asyncio
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.database import AsyncSessionLocal
from app.models.inventory import Balance, Item, Location
from app.services.concurrency import apply_quantity_change

WORKERS = 12
DELTA = Decimal("1")


@pytest.mark.asyncio
async def test_concurrent_balance_increment_no_lost_update():
    loc_id = uuid4()
    item_id = uuid4()

    # Tạo location/item thực để thỏa mãn foreign-key của inv_balances.
    async with AsyncSessionLocal() as session:
        session.add(
            Location(id=loc_id, code=f"LOC-{uuid4().hex[:8]}", name="Test Location", active=True)
        )
        session.add(
            Item(id=item_id, sku=f"SKU-{uuid4().hex[:8]}", name="Test Item", unit="cái", active=True)
        )
        await session.commit()

    async def worker(_n: int) -> None:
        async with AsyncSessionLocal() as session:
            # Đảm bảo balance tồn tại (idempotent) trước khi khóa/cộng.
            await session.execute(
                pg_insert(Balance)
                .values(
                    location_id=loc_id,
                    item_id=item_id,
                    quantity=Decimal("0"),
                    reserved_quantity=Decimal("0"),
                    version=1,
                )
                .on_conflict_do_nothing(index_elements=[Balance.location_id, Balance.item_id])
            )
            await session.commit()
            await apply_quantity_change(session, loc_id, item_id, DELTA, mode="pessimistic")
            await session.commit()

    await asyncio.gather(*(worker(i) for i in range(WORKERS)))

    async with AsyncSessionLocal() as session:
        row = await session.execute(
            select(Balance).where(
                Balance.location_id == loc_id, Balance.item_id == item_id
            )
        )
        bal = row.scalars().first()
        assert bal is not None
        assert bal.quantity == Decimal(WORKERS), f"lost update: {bal.quantity} != {WORKERS}"
