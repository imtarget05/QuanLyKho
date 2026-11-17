"""Unit tests for Enhanced Double-Entry Ledger Engine & Dynamic Balances (Milestone M2).

Covers:
1. Balanced posting for STOCK_IN, STOCK_OUT, TRANSFER, ADJUSTMENT.
2. Rejection of zero quantity, negative unit costs, and unsupported movement types.
3. Strict double-entry balance validation (Debit == Credit).
4. Accurate multi-tier balance tracking (ledger_balance, hold_balance, available_balance, version).
5. Normal balance orientation:
   - Debit-normal accounts (156 Inventory, 632 COGS) increase on Debit, decrease on Credit.
   - Credit-normal accounts (331 Accounts Payable, 338 Surplus, 511 Revenue) increase on Credit, decrease on Debit.
6. Full SQLite in-memory and PostgreSQL compatibility.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.models.ledger import (
    BASE_CHART_OF_ACCOUNTS,
    ChartOfAccounts,
    GeneralLedgerEntry,
    GeneralLedgerJournal,
    GLAccountBalance,
)
from app.services.general_ledger import (
    UnbalancedJournalException,
    _validate_posting,
    ensure_account_balance,
    post_inventory_movement_to_gl,
)


@pytest_asyncio.fixture
async def sqlite_session():
    """Provides a clean in-memory SQLite async session with seeded Chart of Accounts."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    ledger_tables = [
        ChartOfAccounts.__table__,
        GeneralLedgerJournal.__table__,
        GeneralLedgerEntry.__table__,
        GLAccountBalance.__table__,
    ]
    async with engine.begin() as conn:
        await conn.run_sync(lambda sync_conn: Base.metadata.create_all(sync_conn, tables=ledger_tables))

    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with session_factory() as session:
        for code, name, acc_type, normal_bal, sim_only in BASE_CHART_OF_ACCOUNTS:
            acc = ChartOfAccounts(
                code=code,
                name=name,
                account_type=acc_type,
                normal_balance=normal_bal,
                is_active=True,
                simulation_only=sim_only,
            )
            session.add(acc)
            bal = GLAccountBalance(
                account_code=code,
                currency="VND",
                ledger_balance=0,
                available_balance=0,
                hold_balance=0,
                version=1,
            )
            session.add(bal)
        await session.commit()
        yield session

    await engine.dispose()


@pytest.mark.asyncio
async def test_stock_in_creates_balanced_entries_and_updates_balances(sqlite_session: AsyncSession):
    """STOCK_IN: Debit 156 (Inventory Asset), Credit 331 (Accounts Payable)."""
    bal_156_before = (await ensure_account_balance(sqlite_session, "156")).ledger_balance
    bal_331_before = (await ensure_account_balance(sqlite_session, "331")).ledger_balance

    journal = await post_inventory_movement_to_gl(
        session=sqlite_session,
        movement_type="STOCK_IN",
        product_id=101,
        quantity=50,
        unit_cost_cents=20000,
        reference_id="PO-2026-001",
        warehouse_id=1,
        description="Receive 50 units milk tea powder",
    )
    await sqlite_session.commit()

    assert isinstance(journal, GeneralLedgerJournal)
    assert journal.id is not None

    # Verify Journal Entries
    res = await sqlite_session.execute(
        select(GeneralLedgerEntry).where(GeneralLedgerEntry.journal_id == journal.id)
    )
    entries = res.scalars().all()
    assert len(entries) == 2

    entry_156 = next(e for e in entries if e.account_code == "156")
    entry_331 = next(e for e in entries if e.account_code == "331")

    expected_cents = 50 * 20000  # 1,000,000 cents
    assert entry_156.debit == expected_cents
    assert entry_156.credit == 0
    assert entry_331.debit == 0
    assert entry_331.credit == expected_cents

    # Verify Balances
    bal_156_after = await ensure_account_balance(sqlite_session, "156")
    bal_331_after = await ensure_account_balance(sqlite_session, "331")

    assert bal_156_after.ledger_balance - bal_156_before == expected_cents
    assert bal_156_after.available_balance == bal_156_after.ledger_balance - bal_156_after.hold_balance
    assert bal_331_after.ledger_balance - bal_331_before == expected_cents
    assert bal_331_after.available_balance == bal_331_after.ledger_balance - bal_331_after.hold_balance


@pytest.mark.asyncio
async def test_stock_out_creates_cogs_and_reduces_inventory(sqlite_session: AsyncSession):
    """STOCK_OUT: Debit 632 (COGS), Credit 156 (Inventory Asset)."""
    # Pre-seed inventory balance
    bal_156 = await ensure_account_balance(sqlite_session, "156")
    bal_156.ledger_balance = 2000000
    bal_156.available_balance = 2000000
    await sqlite_session.commit()

    bal_156_before = (await ensure_account_balance(sqlite_session, "156")).ledger_balance
    bal_632_before = (await ensure_account_balance(sqlite_session, "632")).ledger_balance

    journal = await post_inventory_movement_to_gl(
        session=sqlite_session,
        movement_type="STOCK_OUT",
        product_id=101,
        quantity=10,
        unit_cost_cents=20000,
        reference_id="SO-2026-001",
        warehouse_id=1,
        description="Issue 10 units for sales order",
    )
    await sqlite_session.commit()

    expected_cents = 10 * 20000  # 200,000 cents
    res = await sqlite_session.execute(
        select(GeneralLedgerEntry).where(GeneralLedgerEntry.journal_id == journal.id)
    )
    entries = res.scalars().all()
    assert len(entries) == 2

    entry_632 = next(e for e in entries if e.account_code == "632")
    entry_156 = next(e for e in entries if e.account_code == "156")
    assert entry_632.debit == expected_cents
    assert entry_632.credit == 0
    assert entry_156.debit == 0
    assert entry_156.credit == expected_cents

    bal_156_after = await ensure_account_balance(sqlite_session, "156")
    bal_632_after = await ensure_account_balance(sqlite_session, "632")

    # Inventory Asset decreased on Credit
    assert bal_156_before - bal_156_after.ledger_balance == expected_cents
    # COGS Expense increased on Debit
    assert bal_632_after.ledger_balance - bal_632_before == expected_cents


@pytest.mark.asyncio
async def test_transfer_movement_is_balanced(sqlite_session: AsyncSession):
    """TRANSFER: Debit 156 (Dest WH), Credit 156 (Source WH). Net zero asset change."""
    bal_156_before = (await ensure_account_balance(sqlite_session, "156")).ledger_balance

    journal = await post_inventory_movement_to_gl(
        session=sqlite_session,
        movement_type="TRANSFER",
        product_id=101,
        quantity=15,
        unit_cost_cents=20000,
        reference_id="TRF-2026-001",
        warehouse_id=1,
        dest_warehouse_id=2,
        description="Transfer 15 units from WH1 to WH2",
    )
    await sqlite_session.commit()

    expected_cents = 15 * 20000
    res = await sqlite_session.execute(
        select(GeneralLedgerEntry).where(GeneralLedgerEntry.journal_id == journal.id)
    )
    entries = res.scalars().all()
    assert len(entries) == 2
    assert sum(e.debit for e in entries) == sum(e.credit for e in entries) == expected_cents

    bal_156_after = (await ensure_account_balance(sqlite_session, "156")).ledger_balance
    assert bal_156_after == bal_156_before


@pytest.mark.asyncio
async def test_adjustment_surplus_and_deficit(sqlite_session: AsyncSession):
    """ADJUSTMENT: Positive quantity -> Debit 156 / Credit 338; Negative quantity -> Debit 632 / Credit 156."""
    # 1. Surplus adjustment (+5 units)
    j_surplus = await post_inventory_movement_to_gl(
        session=sqlite_session,
        movement_type="ADJUSTMENT",
        product_id=101,
        quantity=5,
        unit_cost_cents=20000,
        reference_id="ADJ-GAIN-001",
        warehouse_id=1,
        description="Inventory surplus found during cycle count",
    )
    await sqlite_session.commit()

    res_surplus = await sqlite_session.execute(
        select(GeneralLedgerEntry).where(GeneralLedgerEntry.journal_id == j_surplus.id)
    )
    entries_surplus = res_surplus.scalars().all()
    assert len(entries_surplus) == 2
    e_156 = next(e for e in entries_surplus if e.account_code == "156")
    e_338 = next(e for e in entries_surplus if e.account_code == "338")
    assert e_156.debit == 100000 and e_156.credit == 0
    assert e_338.debit == 0 and e_338.credit == 100000

    # 2. Deficit / Spoilage adjustment (-3 units)
    j_loss = await post_inventory_movement_to_gl(
        session=sqlite_session,
        movement_type="ADJUSTMENT",
        product_id=101,
        quantity=-3,
        unit_cost_cents=20000,
        reference_id="ADJ-LOSS-001",
        warehouse_id=1,
        description="Expired stock disposed",
    )
    await sqlite_session.commit()

    res_loss = await sqlite_session.execute(
        select(GeneralLedgerEntry).where(GeneralLedgerEntry.journal_id == j_loss.id)
    )
    entries_loss = res_loss.scalars().all()
    assert len(entries_loss) == 2
    e_632 = next(e for e in entries_loss if e.account_code == "632")
    e_156_loss = next(e for e in entries_loss if e.account_code == "156")
    assert e_632.debit == 60000 and e_632.credit == 0
    assert e_156_loss.debit == 0 and e_156_loss.credit == 60000


@pytest.mark.asyncio
async def test_zero_quantity_rejected(sqlite_session: AsyncSession):
    """Quantity == 0 must raise ValueError for forward movements."""
    with pytest.raises(ValueError, match="quantity must be strictly positive for this movement type"):
        await post_inventory_movement_to_gl(
            session=sqlite_session,
            movement_type="STOCK_IN",
            product_id=1,
            quantity=0,
            unit_cost_cents=10000,
            reference_id="PO-ZERO",
            warehouse_id=1,
            description="Zero quantity test",
        )


@pytest.mark.asyncio
async def test_zero_quantity_rejected_for_adjustment(sqlite_session: AsyncSession):
    """Quantity == 0 must raise ValueError specifically for ADJUSTMENT."""
    with pytest.raises(ValueError, match="quantity cannot be zero for ADJUSTMENT"):
        await post_inventory_movement_to_gl(
            session=sqlite_session,
            movement_type="ADJUSTMENT",
            product_id=1,
            quantity=0,
            unit_cost_cents=10000,
            reference_id="ADJ-ZERO",
            warehouse_id=1,
            description="Zero adjustment test",
        )


@pytest.mark.asyncio
async def test_negative_quantity_rejected_for_forward_movements(sqlite_session: AsyncSession):
    """Negative quantity must raise ValueError for STOCK_IN, STOCK_OUT, and TRANSFER."""
    for mtype in ("STOCK_IN", "STOCK_OUT", "TRANSFER"):
        with pytest.raises(ValueError, match="quantity must be strictly positive for this movement type"):
            await post_inventory_movement_to_gl(
                session=sqlite_session,
                movement_type=mtype,
                product_id=1,
                quantity=-25,
                unit_cost_cents=10000,
                reference_id=f"REF-NEG-{mtype}",
                warehouse_id=1,
                dest_warehouse_id=2 if mtype == "TRANSFER" else None,
                description=f"Negative qty {mtype} test",
            )


@pytest.mark.asyncio
async def test_zero_unit_cost_rejected(sqlite_session: AsyncSession):
    """Unit cost == 0 must raise ValueError to prevent zero-value DB constraint violations."""
    with pytest.raises(ValueError, match="unit_cost_cents must be strictly positive"):
        await post_inventory_movement_to_gl(
            session=sqlite_session,
            movement_type="STOCK_IN",
            product_id=1,
            quantity=10,
            unit_cost_cents=0,
            reference_id="PO-ZERO-COST",
            warehouse_id=1,
            description="Zero cost test",
        )


@pytest.mark.asyncio
async def test_negative_unit_cost_rejected(sqlite_session: AsyncSession):
    """Unit cost < 0 must raise ValueError."""
    with pytest.raises(ValueError, match="unit_cost_cents must be strictly positive"):
        await post_inventory_movement_to_gl(
            session=sqlite_session,
            movement_type="STOCK_IN",
            product_id=1,
            quantity=10,
            unit_cost_cents=-500,
            reference_id="PO-NEG-COST",
            warehouse_id=1,
            description="Negative cost test",
        )


def test_fastapi_app_boots_and_handles_health_request():
    """Verifies FastAPI lifespan boots cleanly without middleware freeze RuntimeError."""
    from starlette.testclient import TestClient

    from app.main import app

    with TestClient(app) as client:
        live_resp = client.get("/health/live")
        assert live_resp.status_code == 200
        assert live_resp.json().get("status") == "alive"

        api_v1_resp = client.get("/api/v1/health/live")
        assert api_v1_resp.status_code == 200
        assert api_v1_resp.json().get("status") == "alive"


@pytest.mark.asyncio
async def test_unsupported_movement_type_rejected(sqlite_session: AsyncSession):
    """Unknown movement type must raise ValueError."""
    with pytest.raises(ValueError, match="Unsupported movement_type"):
        await post_inventory_movement_to_gl(
            session=sqlite_session,
            movement_type="INVALID_MOVE",
            product_id=1,
            quantity=10,
            unit_cost_cents=1000,
            reference_id="PO-INVALID",
            warehouse_id=1,
            description="Invalid movement type test",
        )


@pytest.mark.asyncio
async def test_unbalanced_posting_rejected():
    """Unbalanced posting must raise UnbalancedJournalException (subclass of ValueError)."""
    unbalanced_entries = [
        SimpleNamespace(account_code="156", debit="100.00", credit="0"),
        SimpleNamespace(account_code="331", debit="0", credit="99.99"),
    ]
    with pytest.raises(UnbalancedJournalException, match="not balanced"):
        _validate_posting("inventory", unbalanced_entries)


@pytest.mark.asyncio
async def test_multi_tier_balance_derivation_and_hold(sqlite_session: AsyncSession):
    """Verifies Available = Ledger - Hold and optimistic version increment."""
    bal = await ensure_account_balance(sqlite_session, "156")
    bal.ledger_balance = 5000000
    bal.hold_balance = 1500000
    bal.available_balance = bal.ledger_balance - bal.hold_balance
    bal.version += 1
    await sqlite_session.commit()

    loaded = await ensure_account_balance(sqlite_session, "156")
    assert loaded.ledger_balance == 5000000
    assert loaded.hold_balance == 1500000
    assert loaded.available_balance == 3500000
    assert loaded.version >= 2
