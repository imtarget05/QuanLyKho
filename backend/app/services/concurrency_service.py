"""Concurrency Locking Engine for Banking & Treasury operations (Milestone M4).

Implements:
- Feature F13: Resource Ordering & Deadlock Prevention (order_resources)
- Feature F14: Optimistic Locking & Atomic Compare-and-Swap (CAS) on Balances
- Feature F15: Pessimistic Locking (with_for_update) & Invariant Guards (available_balance >= 0)
- In-process KeyedLockManager for coroutine-safe resource synchronization
- Dual-dialect SQLite in-memory and PostgreSQL compatibility.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ledger import ChartOfAccounts, GLAccountBalance

# ============================================================================
# EXCEPTIONS
# ============================================================================

class BankingConcurrencyException(Exception):
    """Base exception for banking concurrency control."""


class OptimisticLockException(BankingConcurrencyException):
    """Raised when atomic Compare-And-Swap (CAS) version check fails (lost update prevented)."""

    def __init__(self, message: str = "Optimistic lock version conflict", status_code: int = 409):
        super().__init__(message)
        self.status_code = status_code


# Contract alias for E2E and pairwise test parity
OptimisticConcurrencyException = OptimisticLockException


class InsufficientBalanceException(BankingConcurrencyException):
    """Raised when available balance invariant (available_balance >= 0) is violated."""

    def __init__(self, message: str = "Insufficient available balance", status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


class ResourceDeadlockException(BankingConcurrencyException):
    """Raised when an unrecoverable deadlock condition is detected."""


# ============================================================================
# FEATURE F13: RESOURCE ORDERING & DEADLOCK PREVENTION
# ============================================================================

def order_resources(resource_ids: list[Any]) -> list[Any]:
    """Sorts resource IDs deterministically to eliminate circular wait deadlocks.

    According to the Coffman conditions, a deadlock requires Mutual Exclusion,
    Hold and Wait, No Preemption, and Circular Wait. By enforcing a strict,
    deterministic total ordering across all transactions that acquire multiple
    locks, circular wait is mathematically broken.

    Supports strings, ints, UUIDs, or tuples.
    """
    if not resource_ids:
        return []
    return sorted(resource_ids, key=lambda x: str(x))


# ============================================================================
# KEYED IN-PROCESS MUTEX LOCK MANAGER
# ============================================================================

class KeyedLockManager:
    """Thread-safe and coroutine-safe in-process mutex manager per resource key."""

    def __init__(self) -> None:
        self._locks: dict[str, asyncio.Lock] = {}
        self._master = asyncio.Lock()

    async def get_lock(self, key: str) -> asyncio.Lock:
        async with self._master:
            if key not in self._locks:
                self._locks[key] = asyncio.Lock()
            return self._locks[key]


lock_manager = KeyedLockManager()


# ============================================================================
# HELPER: ENSURE GL ACCOUNT BALANCE
# ============================================================================

async def ensure_account_balance(
    session: AsyncSession, account_code: str
) -> GLAccountBalance:
    """Ensures a balance record exists for the given account code."""
    res = await session.execute(
        select(GLAccountBalance).where(GLAccountBalance.account_code == account_code)
    )
    bal = res.scalars().first()
    if bal is None:
        now = datetime.now(UTC)
        bal = GLAccountBalance(
            account_code=account_code,
            currency="VND",
            ledger_balance=0,
            available_balance=0,
            hold_balance=0,
            version=1,
            updated_at=now,
        )
        session.add(bal)
        await session.flush()
    return bal


# ============================================================================
# FEATURE F14: OPTIMISTIC LOCKING & CAS ON BALANCES
# ============================================================================

async def cas_update_account_balance(
    session: AsyncSession,
    account_code: str,
    delta_cents: int,
    expected_version: int,
    hold_delta_cents: int = 0,
) -> GLAccountBalance:
    """Executes atomic Compare-And-Swap (CAS) update on account balance.

    1. Checks expected_version against current balance version.
    2. Enforces non-negative balance invariant (available_balance >= 0).
    3. Atomically updates ledger, hold, and available balances while incrementing version.
    4. Raises OptimisticLockException on stale version or lost update.
    """
    bal = await ensure_account_balance(session, account_code)
    if bal.version != expected_version:
        raise OptimisticLockException(
            f"CAS version mismatch on account {account_code}: expected {expected_version}, found {bal.version}"
        )

    # Invariant Check: available_balance >= 0 (no overdraft on asset accounts)
    acc_res = await session.execute(
        select(ChartOfAccounts.account_type).where(ChartOfAccounts.code == account_code)
    )
    acc_type = acc_res.scalar_one_or_none() or "asset"

    new_ledger = bal.ledger_balance + delta_cents
    new_hold = bal.hold_balance + hold_delta_cents
    new_available = new_ledger - new_hold

    if new_hold < 0:
        raise InsufficientBalanceException(f"Hold balance cannot be negative: {new_hold}")

    if new_available < 0 and acc_type == "asset":
        raise InsufficientBalanceException(
            f"Negative balance protection invariant violated on {account_code}: "
            f"available balance would become {new_available} cents (< 0)"
        )

    now = datetime.now(UTC)
    # Execute atomic SQL UPDATE with CAS version predicate
    stmt = (
        update(GLAccountBalance)
        .where(
            GLAccountBalance.account_code == account_code,
            GLAccountBalance.version == expected_version,
        )
        .values(
            ledger_balance=new_ledger,
            hold_balance=new_hold,
            available_balance=new_available,
            version=expected_version + 1,
            updated_at=now,
        )
    )
    result = await session.execute(stmt)
    if result.rowcount == 0:
        raise OptimisticLockException(
            f"CAS lost update detected: account {account_code} was updated concurrently"
        )

    bal.ledger_balance = new_ledger
    bal.hold_balance = new_hold
    bal.available_balance = new_available
    bal.version = expected_version + 1
    bal.updated_at = now
    await session.flush()
    return bal


# ============================================================================
# FEATURE F15: PESSIMISTIC LOCKING & INVARIANT GUARDS
# ============================================================================

async def lock_account_balance(
    session: AsyncSession, account_code: str
) -> GLAccountBalance:
    """Acquires a row-level pessimistic exclusive lock (SELECT ... FOR UPDATE).

    Compatible with both PostgreSQL (emits FOR UPDATE) and SQLite (safe no-op query).
    """
    stmt = (
        select(GLAccountBalance)
        .where(GLAccountBalance.account_code == account_code)
        .with_for_update()
    )
    res = await session.execute(stmt)
    bal = res.scalars().first()
    if bal is None:
        bal = await ensure_account_balance(session, account_code)
    return bal


async def apply_balance_mutation(
    session: AsyncSession,
    account_code: str,
    delta_cents: int,
    hold_delta_cents: int = 0,
    *,
    mode: str = "pessimistic",
    expected_version: int | None = None,
) -> GLAccountBalance:
    """Applies a balance mutation with strict invariant guards and locking mode.

    - mode='pessimistic': SELECT ... FOR UPDATE row locking.
    - mode='optimistic': Atomic Compare-And-Swap with version check.
    """
    if mode == "optimistic":
        if expected_version is None:
            raise ValueError("expected_version is required for optimistic locking mode.")
        return await cas_update_account_balance(
            session=session,
            account_code=account_code,
            delta_cents=delta_cents,
            expected_version=expected_version,
            hold_delta_cents=hold_delta_cents,
        )

    # Pessimistic mode
    bal = await lock_account_balance(session, account_code)

    acc_res = await session.execute(
        select(ChartOfAccounts.account_type).where(ChartOfAccounts.code == account_code)
    )
    acc_type = acc_res.scalar_one_or_none() or "asset"

    new_ledger = bal.ledger_balance + delta_cents
    new_hold = bal.hold_balance + hold_delta_cents
    new_available = new_ledger - new_hold

    if new_hold < 0:
        raise InsufficientBalanceException(f"Hold balance cannot be negative: {new_hold}")

    if new_available < 0 and acc_type == "asset":
        raise InsufficientBalanceException(
            f"Negative balance protection invariant violated on {account_code}: "
            f"available balance would become {new_available} cents (< 0)"
        )

    bal.ledger_balance = new_ledger
    bal.hold_balance = new_hold
    bal.available_balance = new_available
    bal.version += 1
    bal.updated_at = datetime.now(UTC)
    await session.flush()
    return bal


async def hold_account_funds(
    session: AsyncSession,
    account_code: str,
    hold_amount_cents: int,
) -> GLAccountBalance:
    """Freezes funds by increasing hold_balance and reducing available_balance.

    Enforces available_balance >= 0.
    """
    if hold_amount_cents <= 0:
        raise ValueError("Hold amount must be strictly positive.")
    return await apply_balance_mutation(
        session=session,
        account_code=account_code,
        delta_cents=0,
        hold_delta_cents=hold_amount_cents,
        mode="pessimistic",
    )


async def release_account_hold(
    session: AsyncSession,
    account_code: str,
    release_amount_cents: int,
) -> GLAccountBalance:
    """Releases frozen funds by decreasing hold_balance and restoring available_balance."""
    if release_amount_cents <= 0:
        raise ValueError("Release amount must be strictly positive.")
    return await apply_balance_mutation(
        session=session,
        account_code=account_code,
        delta_cents=0,
        hold_delta_cents=-release_amount_cents,
        mode="pessimistic",
    )


async def execute_concurrent_transfer(
    session: AsyncSession,
    source_account: str,
    dest_account: str,
    amount_cents: int,
    description: str = "",
    *,
    mode: str = "pessimistic",
) -> dict[str, Any]:
    """Executes a transfer between two accounts with deadlock-free resource ordering.

    1. Orders accounts: order_resources([source_account, dest_account]).
    2. Locks resources in deterministic sequence, eliminating circular waits.
    3. Verifies source available balance >= amount_cents.
    4. Mutates source and destination balances atomically.
    """
    if amount_cents <= 0:
        raise ValueError("Transfer amount must be strictly positive.")
    if source_account == dest_account:
        raise ValueError("Source and destination accounts must be distinct.")

    ordered = order_resources([source_account, dest_account])

    # Acquire locks in deterministic order
    locked_balances: dict[str, GLAccountBalance] = {}
    for code in ordered:
        locked_balances[code] = await lock_account_balance(session, code)

    src_bal = locked_balances[source_account]
    dst_bal = locked_balances[dest_account]

    if src_bal.available_balance < amount_cents:
        raise InsufficientBalanceException(
            f"Source account {source_account} insufficient available balance: "
            f"{src_bal.available_balance} < {amount_cents}"
        )

    # Debit source (decreases ledger & available)
    src_bal.ledger_balance -= amount_cents
    src_bal.available_balance -= amount_cents
    src_bal.version += 1
    src_bal.updated_at = datetime.now(UTC)

    # Credit destination (increases ledger & available)
    dst_bal.ledger_balance += amount_cents
    dst_bal.available_balance += amount_cents
    dst_bal.version += 1
    dst_bal.updated_at = datetime.now(UTC)

    await session.flush()

    return {
        "source_account": source_account,
        "dest_account": dest_account,
        "amount_cents": amount_cents,
        "description": description,
        "source_balance": {
            "ledger": src_bal.ledger_balance,
            "available": src_bal.available_balance,
            "version": src_bal.version,
        },
        "dest_balance": {
            "ledger": dst_bal.ledger_balance,
            "available": dst_bal.available_balance,
            "version": dst_bal.version,
        },
    }
