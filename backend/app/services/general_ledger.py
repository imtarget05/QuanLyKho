"""Transactional posting from operational sub-ledgers to the general ledger."""

import uuid
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.cash_sim import SIM_CASH_PREFIX, SIM_OFFSET_ACCOUNT
from app.models.ledger import (
    BASE_CHART_OF_ACCOUNTS,
    ChartOfAccounts,
    GeneralLedgerEntry,
    GeneralLedgerJournal,
    GLAccountBalance,
)


class UnbalancedJournalException(ValueError):
    """Raised when sum of debits does not equal sum of credits in a journal."""
    pass


async def ensure_account_balance(session: AsyncSession, account_code: str) -> GLAccountBalance:
    """Ensures balance record exists for given account code."""
    res = await session.execute(
        select(GLAccountBalance).where(GLAccountBalance.account_code == account_code)
    )
    bal = res.scalars().first()
    if bal is None:
        bal = GLAccountBalance(
            account_code=account_code,
            currency="VND",
            ledger_balance=0,
            available_balance=0,
            hold_balance=0,
            version=1,
            updated_at=datetime.now(UTC),
        )
        session.add(bal)
        await session.flush()
    return bal


async def post_inventory_movement_to_gl(
    session: AsyncSession,
    movement_type: str,
    product_id: int,
    quantity: int,
    unit_cost_cents: int,
    reference_id: str,
    warehouse_id: int,
    description: str,
    dest_warehouse_id: int | None = None,
) -> GeneralLedgerJournal:
    """Creates and commits a balanced GL journal entry for inventory movements:

    - STOCK_IN: Debit Account 156 (Inventory Asset), Credit Account 331 (Accounts Payable)
    - STOCK_OUT: Debit Account 632 (COGS Expense), Credit Account 156 (Inventory Asset)
    - TRANSFER: Debit Account 156 (Dest Warehouse), Credit Account 156 (Source Warehouse)
    - ADJUSTMENT:
        If quantity > 0: Debit Account 156, Credit Account 338 (Inventory Gain)
        If quantity < 0: Debit Account 632 (Inventory Spoilage/Loss), Credit Account 156
    Enforces Sum(Debit) == Sum(Credit) and updates gl_account_balances atomically.
    """
    if unit_cost_cents <= 0:
        raise ValueError("unit_cost_cents must be strictly positive")

    if movement_type in ("STOCK_IN", "STOCK_OUT", "TRANSFER"):
        if quantity <= 0:
            raise ValueError("quantity must be strictly positive for this movement type")
    elif movement_type == "ADJUSTMENT":
        if quantity == 0:
            raise ValueError("quantity cannot be zero for ADJUSTMENT")
    else:
        raise ValueError(f"Unsupported movement_type: {movement_type}")

    abs_qty = abs(quantity)
    total_cents = abs_qty * unit_cost_cents

    source_uuid = uuid.uuid4()
    if reference_id:
        try:
            source_uuid = uuid.UUID(str(reference_id))
        except ValueError:
            source_uuid = uuid.uuid5(uuid.NAMESPACE_DNS, str(reference_id))

    journal = GeneralLedgerJournal(
        id=uuid.uuid4(),
        source_type="inventory",
        source_journal_id=source_uuid,
        correlation_id=str(f"corr-{reference_id}")[:64],
        posted_at=datetime.now(UTC),
    )
    session.add(journal)
    await session.flush()

    entries: list[GeneralLedgerEntry] = []

    if movement_type == "STOCK_IN":
        entries.append(
            GeneralLedgerEntry(
                id=uuid.uuid4(),
                journal_id=journal.id,
                account_code="156",
                debit=total_cents,
                credit=0,
            )
        )
        entries.append(
            GeneralLedgerEntry(
                id=uuid.uuid4(),
                journal_id=journal.id,
                account_code="331",
                debit=0,
                credit=total_cents,
            )
        )
    elif movement_type == "STOCK_OUT":
        entries.append(
            GeneralLedgerEntry(
                id=uuid.uuid4(),
                journal_id=journal.id,
                account_code="632",
                debit=total_cents,
                credit=0,
            )
        )
        entries.append(
            GeneralLedgerEntry(
                id=uuid.uuid4(),
                journal_id=journal.id,
                account_code="156",
                debit=0,
                credit=total_cents,
            )
        )
    elif movement_type == "TRANSFER":
        entries.append(
            GeneralLedgerEntry(
                id=uuid.uuid4(),
                journal_id=journal.id,
                account_code="156",
                debit=total_cents,
                credit=0,
            )
        )
        entries.append(
            GeneralLedgerEntry(
                id=uuid.uuid4(),
                journal_id=journal.id,
                account_code="156",
                debit=0,
                credit=total_cents,
            )
        )
    elif movement_type == "ADJUSTMENT":
        if quantity > 0:
            entries.append(
                GeneralLedgerEntry(
                    id=uuid.uuid4(),
                    journal_id=journal.id,
                    account_code="156",
                    debit=total_cents,
                    credit=0,
                )
            )
            entries.append(
                GeneralLedgerEntry(
                    id=uuid.uuid4(),
                    journal_id=journal.id,
                    account_code="338",
                    debit=0,
                    credit=total_cents,
                )
            )
        else:
            entries.append(
                GeneralLedgerEntry(
                    id=uuid.uuid4(),
                    journal_id=journal.id,
                    account_code="632",
                    debit=total_cents,
                    credit=0,
                )
            )
            entries.append(
                GeneralLedgerEntry(
                    id=uuid.uuid4(),
                    journal_id=journal.id,
                    account_code="156",
                    debit=0,
                    credit=total_cents,
                )
            )

    # Validate Double-Entry Invariant: Sum(Debit) == Sum(Credit)
    total_debit = sum(e.debit for e in entries)
    total_credit = sum(e.credit for e in entries)
    if total_debit != total_credit:
        raise UnbalancedJournalException(
            f"Unbalanced journal: Debit={total_debit} != Credit={total_credit}"
        )

    for e in entries:
        session.add(e)
    await session.flush()

    # Atomically update gl_account_balances according to normal balance rules
    for e in entries:
        acc_res = await session.execute(
            select(ChartOfAccounts).where(ChartOfAccounts.code == e.account_code)
        )
        acc = acc_res.scalars().first()
        if not acc:
            raise ValueError(
                f"Account code {e.account_code} does not exist in Chart of Accounts."
            )

        bal = await ensure_account_balance(session, e.account_code)
        if acc.normal_balance == "debit":
            # Normal Debit: Debit increases (+), Credit decreases (-)
            delta = e.debit - e.credit
        else:
            # Normal Credit: Credit increases (+), Debit decreases (-)
            delta = e.credit - e.debit

        bal.ledger_balance += delta
        bal.available_balance = bal.ledger_balance - bal.hold_balance
        bal.version += 1
        bal.updated_at = datetime.now(UTC)

    await session.flush()
    return journal


_INVENTORY_ACCOUNTS = {account[0] for account in BASE_CHART_OF_ACCOUNTS}
_INVENTORY_ACCOUNTS.discard(SIM_OFFSET_ACCOUNT)


def _validated_amount(value: Any) -> Decimal:
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError("general-ledger amounts must be finite decimals") from exc
    if not amount.is_finite() or amount < 0:
        raise ValueError("general-ledger amounts must be finite and non-negative")
    return amount


def _validate_posting(source_type: str, entries: list[Any]) -> list[tuple[str, Decimal, Decimal]]:
    if source_type not in {"inventory", "cash_simulation"}:
        raise ValueError("unsupported general-ledger source type")

    posting = []
    debit_total = Decimal("0")
    credit_total = Decimal("0")
    for entry in entries:
        code = str(entry.account_code)
        debit = _validated_amount(entry.debit)
        credit = _validated_amount(entry.credit)
        if (debit > 0) == (credit > 0):
            raise ValueError("each general-ledger entry must have exactly one positive side")

        if source_type == "inventory":
            if code not in _INVENTORY_ACCOUNTS:
                raise ValueError(f"unsupported account for inventory posting: {code}")
        elif code == SIM_OFFSET_ACCOUNT:
            pass
        elif code.startswith(SIM_CASH_PREFIX):
            try:
                uuid.UUID(code.removeprefix(SIM_CASH_PREFIX))
            except ValueError as exc:
                raise ValueError("simulation cash account must contain a UUID") from exc
        else:
            raise ValueError(f"unsupported account for cash simulation: {code}")

        posting.append((code, debit, credit))
        debit_total += debit
        credit_total += credit

    if debit_total != credit_total:
        raise UnbalancedJournalException("general-ledger posting is not balanced")
    return posting


async def post_subledger_journal(
    db: AsyncSession,
    *,
    source_type: str,
    source_journal: Any,
    entries: list[Any],
) -> None:
    """Copy one balanced sub-ledger journal into the GL in the same transaction."""
    posting = _validate_posting(source_type, entries)
    simulation_only = source_type == "cash_simulation"
    journal_id = uuid.uuid4()

    result = await db.execute(
        pg_insert(GeneralLedgerJournal)
        .values(
            id=journal_id,
            source_type=source_type,
            source_journal_id=source_journal.id,
            posted_at=source_journal.posted_at,
            correlation_id=source_journal.correlation_id,
            simulation_only=simulation_only,
        )
        .on_conflict_do_nothing(
            index_elements=[
                GeneralLedgerJournal.source_type,
                GeneralLedgerJournal.source_journal_id,
            ]
        )
        .returning(GeneralLedgerJournal.id)
    )
    inserted_id = result.scalar_one_or_none()
    if inserted_id is None:
        return

    simulation_accounts = sorted(
        {code for code, _, _ in posting if code.startswith(SIM_CASH_PREFIX)}
    )
    if simulation_accounts:
        await db.execute(
            pg_insert(ChartOfAccounts)
            .values(
                [
                    {
                        "code": code,
                        "name": f"Simulated cashbox {code.removeprefix(SIM_CASH_PREFIX)}",
                        "account_type": "asset",
                        "normal_balance": "debit",
                        "is_active": True,
                        "simulation_only": True,
                    }
                    for code in simulation_accounts
                ]
            )
            .on_conflict_do_nothing(index_elements=[ChartOfAccounts.code])
        )

    db.add_all(
        [
            GeneralLedgerEntry(
                id=uuid.uuid4(),
                journal_id=inserted_id,
                account_code=code,
                debit=debit,
                credit=credit,
            )
            for code, debit, credit in posting
        ]
    )
    await db.flush()
