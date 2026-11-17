"""Pytest fixtures for standalone E2E Banking test suite.

Features:
- Standalone async SQLite in-memory engine and sessionmaker (`sqlite+aiosqlite:///:memory:`)
- Automatically registers and creates all tables:
  coa_accounts, gl_journals, gl_journal_entries, gl_account_balances,
  idempotency_keys, outbox_events, processed_events, saga_instances,
  saga_step_logs, audit_events_chain, warehouses, products, inventory_balances.
- Fixtures for test client, sample accounts (111 Cash, 156 Inventory, 331 AP, 511 Revenue, 632 COGS),
  warehouses, and products.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import Any

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

# Re-export root conftest fixtures/utilities to prevent shadowing when tests import `from conftest import ...`
try:
    from tests.conftest import (  # noqa: F401
        APP_DIR,
        BACKEND_DIR,
        REPO_DIR,
        _import_or_fail,
        fetch_all_balances,
        open_shift,
        run,
    )
except ImportError:
    pass

from tests.e2e_banking.banking_contracts import (
    BankingBase,
    COAAccount,
    GLAccountBalance,
    InventoryBalanceRecord,
    ProductRecord,
    WarehouseRecord,
)

STANDARD_COA = [
    ("111", "Cash on Hand", "asset", "debit"),
    ("112", "Bank Operating Account", "asset", "debit"),
    ("156", "Merchandise Inventory", "asset", "debit"),
    ("331", "Accounts Payable (Suppliers)", "liability", "credit"),
    ("338", "Other Payables & Inventory Surplus", "liability", "credit"),
    ("511", "Sales Revenue", "revenue", "credit"),
    ("632", "Cost of Goods Sold (COGS)", "expense", "debit"),
]


@pytest_asyncio.fixture(scope="function")
async def async_engine():
    """Function-scoped in-memory SQLite async engine."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(BankingBase.metadata.create_all)

    yield engine

    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def session_factory(async_engine):
    """Session factory bound to the function-scoped async engine."""
    return async_sessionmaker(async_engine, expire_on_commit=False, class_=AsyncSession)


@pytest_asyncio.fixture(scope="function")
async def db_session(session_factory) -> AsyncGenerator[AsyncSession, None]:
    """Provides an isolated AsyncSession with pre-seeded Chart of Accounts."""
    async with session_factory() as session:
        # Pre-seed standard Chart of Accounts
        for code, name, acc_type, normal_bal in STANDARD_COA:
            account = COAAccount(
                code=code,
                name=name,
                account_type=acc_type,
                normal_balance=normal_bal,
                is_active=True,
                created_at=datetime.now(UTC),
            )
            session.add(account)
            bal = GLAccountBalance(
                account_code=code,
                ledger_balance=0,
                available_balance=0,
                hold_balance=0,
                version=1,
                updated_at=datetime.now(UTC),
            )
            session.add(bal)
        await session.commit()
        yield session


@pytest_asyncio.fixture(scope="function")
async def seeded_data(db_session: AsyncSession) -> dict[str, Any]:
    """Seeds sample warehouses, products, and initial inventory balances."""
    # Warehouses
    wh1 = WarehouseRecord(code="WH-MAIN", name="Hanoi Central Hub", is_active=True)
    wh2 = WarehouseRecord(code="WH-SOUTH", name="Saigon Regional Hub", is_active=True)
    db_session.add_all([wh1, wh2])
    await db_session.flush()

    # Products
    p1 = ProductRecord(sku="SKU-COFFEE-01", name="Robusta Coffee Beans 1kg", unit_cost_cents=150000)
    p2 = ProductRecord(sku="SKU-TEA-01", name="Oolong Premium Tea 500g", unit_cost_cents=200000)
    db_session.add_all([p1, p2])
    await db_session.flush()

    # Inventory balances
    inv1 = InventoryBalanceRecord(warehouse_id=wh1.id, product_id=p1.id, quantity=1000, reserved_quantity=0, version=1)
    inv2 = InventoryBalanceRecord(warehouse_id=wh2.id, product_id=p2.id, quantity=500, reserved_quantity=0, version=1)
    db_session.add_all([inv1, inv2])
    await db_session.commit()

    return {
        "warehouses": [wh1, wh2],
        "products": [p1, p2],
        "balances": [inv1, inv2],
    }
