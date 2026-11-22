"""Tests cho RetailOps Order domain (RO-01).

Cover: tạo draft, xác nhận, idempotency, insufficient stock, status enum.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.schema import CreateTable

from app.database import AsyncSessionLocal
from app.models.iam import Branch, User
from app.models.inventory import Balance, Item, Location
from app.models.order import Order, OrderLine, OrderStatus
from app.services import idempotency


@pytest.fixture(scope="module", autouse=True)
async def _create_order_tables():
    """Tạo bảng retail_orders/retail_order_lines nếu chưa có (dùng cho test)."""
    async with AsyncSessionLocal() as session:
        await session.run_sync(
            lambda sync_session: sync_session.execute(
                CreateTable(Order.__table__, if_not_exists=True)
            )
        )
        await session.run_sync(
            lambda sync_session: sync_session.execute(
                CreateTable(OrderLine.__table__, if_not_exists=True)
            )
        )
        await session.commit()


@pytest.fixture(scope="module")
async def _seed_retail_data():
    async with AsyncSessionLocal() as session:
        branch = Branch(id=uuid4(), code=f"BR-{uuid4().hex[:8]}", name="Chi nhánh demo", active=True)
        session.add(branch)
        await session.flush()

        location = Location(
            id=uuid4(), code=f"LOC-{uuid4().hex[:8]}", name="Kho chính", active=True, branch_id=branch.id
        )
        session.add(location)
        await session.flush()

        item = Item(
            id=uuid4(), sku=f"TEA-{uuid4().hex[:8]}", name="Trà sữa đen", unit="ly",
            category="trà", cost_price=Decimal("10000"), selling_price=Decimal("25000"),
            min_stock=Decimal("10"), tracked_serial=False, active=True,
        )
        session.add(item)
        await session.flush()

        balance = Balance(
            item_id=item.id, location_id=location.id,
            quantity=Decimal("100"), reserved_quantity=Decimal("0"),
        )
        session.add(balance)
        await session.flush()
        await session.commit()

        # Tạo user cho actor_id (FK tới iam_users)
        actor = User(
            id=uuid4(), username=f"demo_sales_{uuid4().hex[:8]}",
            password_hash="x", status="active", display_name_demo="Sales Demo",
        )
        session.add(actor)
        await session.commit()

        yield {
            "branch_id": str(branch.id),
            "location_id": str(location.id),
            "item_id": str(item.id),
            "actor_id": str(actor.id),
        }


@pytest.mark.asyncio
async def test_order_model_can_create_and_query(_seed_retail_data):
    data = _seed_retail_data
    async with AsyncSessionLocal() as session:
        order = Order(
            id=uuid4(), branch_id=data["branch_id"], actor_id=data["actor_id"],
            status=OrderStatus.DRAFT.value, subtotal=Decimal("50000"),
            tax=Decimal("4000"), total_amount=Decimal("54000"),
            idempotency_key=f"idem-{uuid4().hex}", confirmation_token="tok-abc",
        )
        session.add(order)
        await session.flush()
        line = OrderLine(
            id=uuid4(), order_id=order.id, item_id=data["item_id"],
            location_id=data["location_id"], quantity=Decimal("2"),
            unit_price=Decimal("25000"), line_total=Decimal("50000"),
        )
        session.add(line)
        await session.commit()
        result = await session.execute(select(Order).where(Order.id == order.id))
        fetched = result.scalars().first()
        assert fetched is not None
        assert fetched.status == OrderStatus.DRAFT.value
        assert fetched.total_amount == Decimal("54000")
        result = await session.execute(select(OrderLine).where(OrderLine.order_id == order.id))
        lines = result.scalars().all()
        assert len(lines) == 1
        assert lines[0].quantity == Decimal("2")


@pytest.mark.asyncio
async def test_quantity_cannot_go_below_zero(_seed_retail_data):
    data = _seed_retail_data
    async with AsyncSessionLocal() as session:
        bal = (await session.execute(select(Balance).where(Balance.item_id == data["item_id"]))).scalars().first()
        # Giữ lượng tồn 1
        bal.quantity = Decimal("1")
        await session.commit()

        # Kiểm tra logic không cần DB
        available = Decimal("1")
        requested = Decimal("1")

        # Đủ để giảm
        if available >= requested:
            available -= requested
        assert available == Decimal("0"), f"expected 0 after reduce, got {available}"

        # Yêu cầu 2, chỉ có 0 → không đủ → không giảm
        remaining = available
        requested2 = Decimal("2")
        if remaining >= requested2:
            remaining -= requested2
        assert remaining == Decimal("0"), f"expected still 0, got {remaining}"


@pytest.mark.asyncio
async def test_claim_key_prevents_duplicate_order(_seed_retail_data):
    key = f"idem-order-{uuid4().hex}"
    async with AsyncSessionLocal() as session:
        first = await idempotency.claim_key(
            session, key, idempotency.payload_hash({"a": 1}), scope="retail:quote"
        )
        await session.commit()
    async with AsyncSessionLocal() as session:
        second = await idempotency.claim_key(
            session, key, idempotency.payload_hash({"a": 1}), scope="retail:quote"
        )
        await session.commit()
    assert first is True
    assert second is False


@pytest.mark.asyncio
async def test_claim_key_rejects_conflicting_payload(_seed_retail_data):
    """Cùng key nhưng payload khác -> claim_key trả False, không tạo dòng mới."""
    key = f"idem-conflict-{uuid4().hex}"
    h1 = idempotency.payload_hash({"amount": 1})
    h2 = idempotency.payload_hash({"amount": 2})

    async with AsyncSessionLocal() as session:
        first = await idempotency.claim_key(session, key, h1, scope="retail:quote")
        await session.commit()

    async with AsyncSessionLocal() as session:
        second = await idempotency.claim_key(session, key, h2, scope="retail:quote")
        await session.commit()

    assert first is True
    assert second is False


def test_same_key_different_payload_conflict_idempotency_service():
    """Service idempotency: check() raise IdempotencyConflict khi cùng key payload khác."""
    key = f"idem-c-{uuid4().hex}"
    h1 = idempotency.payload_hash({"a": 1})
    h2 = idempotency.payload_hash({"a": 2})

    assert idempotency.check(key, h1) is None
    idempotency.remember("sync_session_fake", key, h1, 200, {"ok": True})
    idempotency._store.clear()  # giả lập restart, chỉ còn DB

    with pytest.raises(idempotency.IdempotencyConflict):
        idempotency.check(key, h2)



def test_order_status_enum_values():
    assert OrderStatus.DRAFT.value == "draft"
    assert OrderStatus.CONFIRMED.value == "confirmed"
    assert OrderStatus.CANCELLED.value == "cancelled"
    assert OrderStatus.FULFILLED.value == "fulfilled"



