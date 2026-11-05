"""Transactional posting from operational sub-ledgers to the general ledger."""

import uuid
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.cash_sim import SIM_CASH_PREFIX, SIM_OFFSET_ACCOUNT
from app.models.ledger import (
    BASE_CHART_OF_ACCOUNTS,
    ChartOfAccounts,
    GeneralLedgerEntry,
    GeneralLedgerJournal,
)

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
        raise ValueError("general-ledger posting is not balanced")
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
