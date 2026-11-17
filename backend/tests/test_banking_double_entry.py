"""Kiểm tra sổ cái kế toán kép (double-entry) cho giao dịch ngân hàng.

Mọi bút toán post phải cân đối: ∑Debit = ∑Credit; bút toán lệch bị từ chối.
"""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.ledger import GeneralLedgerEntry, GeneralLedgerJournal
from app.services.general_ledger import post_subledger_journal


@pytest.mark.asyncio
async def test_transfer_creates_balanced_double_entry_journal():
    """Chuyển tiền giữa 2 tài khoản tạo journal cân đối (∑dr = ∑cr)."""
    journal_id = uuid4()
    correlation_id = f"transfer-{uuid4()}"
    source_journal = SimpleNamespace(
        id=journal_id,
        posted_at=__import__("datetime").datetime.now(__import__("datetime").UTC),
        correlation_id=correlation_id,
    )

    async with AsyncSessionLocal() as session:
        await post_subledger_journal(
            session,
            source_type="inventory",
            source_journal=source_journal,
            entries=[
                SimpleNamespace(account_code="156", debit=Decimal("1000.00"), credit=Decimal("0")),  # kho nguồn giảm
                SimpleNamespace(account_code="331", debit=Decimal("0"), credit=Decimal("1000.00")),  # nợ người nhận tăng
            ],
        )
        await session.commit()

        rows = await session.execute(
            select(
                GeneralLedgerEntry.account_code,
                GeneralLedgerEntry.debit,
                GeneralLedgerEntry.credit,
            )
            .join(GeneralLedgerJournal, GeneralLedgerJournal.id == GeneralLedgerEntry.journal_id)
            .where(GeneralLedgerJournal.correlation_id == correlation_id)
        )
        entries = rows.all()
        assert len(entries) == 2

        debit_total = sum((Decimal(str(d)) for _, d, _ in entries), Decimal("0"))
        credit_total = sum((Decimal(str(c)) for _, _, c in entries), Decimal("0"))
        assert debit_total == credit_total == Decimal("1000.00")

        for _code, debit, credit in entries:
            assert (Decimal(str(debit)) > 0) != (Decimal(str(credit)) > 0)


@pytest.mark.asyncio
async def test_unbalanced_double_entry_is_rejected():
    """Bút toán không cân đối (∑dr != ∑cr) phải bị từ chối."""
    journal_id = uuid4()
    correlation_id = f"unbalanced-{uuid4()}"
    source_journal = SimpleNamespace(
        id=journal_id,
        posted_at=__import__("datetime").datetime.now(__import__("datetime").UTC),
        correlation_id=correlation_id,
    )
    async with AsyncSessionLocal() as session:
        with pytest.raises(ValueError, match="not balanced"):
            await post_subledger_journal(
                session,
                source_type="inventory",
                source_journal=source_journal,
                entries=[
                    SimpleNamespace(account_code="156", debit=Decimal("1000.00"), credit=Decimal("0")),
                ],
            )
