"""Pessimistic Concurrency Control & Overdraft Guard for GLAccountBalance.

Implements Milestone M4 Feature F15:
- SELECT FOR UPDATE pessimistic locking on account balances
- Overdraft guard: available_balance >= 0 invariant
- Atomic debit/credit with optimistic CAS version check
- Deadlock-free via deterministic resource ordering
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ledger import GLAccountBalance


class BalanceLockException(Exception):
    """Base exception for balance locking."""


class InsufficientBalanceError(BalanceLockException):
    """Raised when available balance insufficient for debit."""


class AccountNotFoundError(BalanceLockException):
    """Raised when account does not exist."""


async def _ensure_balance(
    session: AsyncSession, account_code: str, for_update: bool = False
) -> GLAccountBalance:
    """Lấy hoặc tạo GLAccountBalance cho account_code."""
    stmt = select(GLAccountBalance).where(GLAccountBalance.account_code == account_code)
    if for_update:
        stmt = stmt.with_for_update()
    res = await session.execute(stmt)
    bal = res.scalars().first()
    if bal is None:
        bal = GLAccountBalance(
            account_code=account_code,
            currency="VND",
            ledger_balance=0,
            available_balance=0,
            hold_balance=0,
            version=1,
        )
        session.add(bal)
        await session.flush()
    return bal


async def lock_account_balance(
    session: AsyncSession, account_code: str
) -> GLAccountBalance:
    """Pessimistic lock: SELECT FOR UPDATE trên balance của account."""
    return await _ensure_balance(session, account_code, for_update=True)

async def debit_balance(
    session: AsyncSession,
    account_code: str,
    amount_cents: int,
    *,
    expect_version: int | None = None,
) -> GLAccountBalance:
    """Ghi trừ số dô (debit) với overdraft guard.

    - amount_cents > 0
    - available_balance >= amount_cents (không cho phép âm)
    - Nếu expect_version được cung cấp, kiểm tra CAS trước khi ghi
    """
    if amount_cents <= 0:
        raise ValueError("Debit amount must be strictly positive.")

    bal = await lock_account_balance(session, account_code)

    # Optimistic CAS check
    if expect_version is not None and bal.version != expect_version:
        raise BalanceLockException(
            f"Optimistic lock version conflict for {account_code}: "
            f"expected {expect_version}, got {bal.version}"
        )

    if bal.available_balance < amount_cents:
        raise InsufficientBalanceError(
            f"Insufficient available balance for {account_code}: "
            f"available={bal.available_balance} < required={amount_cents}"
        )

    bal.ledger_balance -= amount_cents
    bal.available_balance -= amount_cents
    bal.version += 1
    await session.flush()
    return bal


async def credit_balance(
    session: AsyncSession,
    account_code: str,
    amount_cents: int,
    *,
    expect_version: int | None = None,
) -> GLAccountBalance:
    """Cộng số dô (credit) với CAS version check."""
    if amount_cents <= 0:
        raise ValueError("Credit amount must be strictly positive.")

    bal = await lock_account_balance(session, account_code)

    if expect_version is not None and bal.version != expect_version:
        raise BalanceLockException(
            f"Optimistic lock version conflict for {account_code}: "
            f"expected {expect_version}, got {bal.version}"
        )

    bal.ledger_balance += amount_cents
    bal.available_balance += amount_cents
    bal.version += 1
    await session.flush()
    return bal


async def transfer_with_lock(
    session: AsyncSession,
    source_account: str,
    dest_account: str,
    amount_cents: int,
    *,
    source_expect_version: int | None = None,
    dest_expect_version: int | None = None,
) -> dict[str, Any]:
    """Chuyển tiền giữa hai tài khoản với deadlock-free resource ordering.

    1. Order tài khoản theo thứ tự deterministic (tránh deadlock)
    2. SELECT FOR UPDATE từng tài khoản theo thứ tự đó
    3. Kiểm tra available_balance của source >= amount_cents
    4. Debit source + credit dest atomically
    5. CAS version check nếu được cung cấp
    """
    if amount_cents <= 0:
        raise ValueError("Transfer amount must be strictly positive.")
    if source_account == dest_account:
        raise ValueError("Source and destination accounts must be distinct.")

    ordered = sorted([source_account, dest_account], key=str)

    locked: dict[str, GLAccountBalance] = {}
    for code in ordered:
        locked[code] = await lock_account_balance(session, code)

    src = locked[source_account]
    dst = locked[dest_account]

    # CAS version checks
    if source_expect_version is not None and src.version != source_expect_version:
        raise BalanceLockException(
            f"Optimistic lock version conflict for {source_account}: "
            f"expected {source_expect_version}, got {src.version}"
        )
    if dest_expect_version is not None and dst.version != dest_expect_version:
        raise BalanceLockException(
            f"Optimistic lock version conflict for {dest_account}: "
            f"expected {dest_expect_version}, got {dst.version}"
        )

    # Overdraft guard
    if src.available_balance < amount_cents:
        raise InsufficientBalanceError(
            f"Insufficient available balance for {source_account}: "
            f"available={src.available_balance} < required={amount_cents}"
        )

    # Debit source
    src.ledger_balance -= amount_cents
    src.available_balance -= amount_cents
    src.version += 1

    # Credit destination
    dst.ledger_balance += amount_cents
    dst.available_balance += amount_cents
    dst.version += 1

    await session.flush()

    return {
        "source_account": source_account,
        "dest_account": dest_account,
        "amount_cents": amount_cents,
        "source_balance": {
            "ledger": src.ledger_balance,
            "available": src.available_balance,
            "version": src.version,
        },
        "dest_balance": {
            "ledger": dst.ledger_balance,
            "available": dst.available_balance,
            "version": dst.version,
        },
    }


__all__ = [
    "BalanceLockException",
    "InsufficientBalanceError",
    "AccountNotFoundError",
    "lock_account_balance",
    "debit_balance",
    "credit_balance",
    "transfer_with_lock",
]
