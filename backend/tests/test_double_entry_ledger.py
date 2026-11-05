"""Invariant ke toan kep (double-entry): tung phong giao dich co mot du mot co, tong bang 0."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest
from portfolio_test_helpers import first_location_and_item as _first_location_and_item
from portfolio_test_helpers import idem_headers as _idem
from portfolio_test_helpers import login_headers as _headers
from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.inventory import Balance, InventoryEntry, InventoryJournal
from app.services.general_ledger import post_subledger_journal

DEMO_PASSWORD = "DemoPass123!"
MAKER = "demo_maker"
CHECKER = "demo_checker"


async def _create_receipt(async_client, headers, dest_id: str, item_id: str, quantity: str = "5"):
    return await async_client.post(
        "/inventory/requests",
        headers=_idem(headers),
        json={
            "kind": "receipt",
            "dest_id": dest_id,
            "lines": [
                {"item_id": item_id, "quantity": quantity, "unit_price": "10000"}
            ],
            "supplier": "NCC Test",
        },
    )


async def _balance_qty(session, location_id, item_id) -> Decimal:
    row = await session.execute(
        select(Balance).where(
            Balance.location_id == location_id, Balance.item_id == item_id
        )
    )
    bal = row.scalar_one_or_none()
    if bal is None:
        return Decimal("0")
    return Decimal(str(bal.quantity))


async def _journal_entries_for_request(session, request_id):
    journal = await session.execute(
        select(InventoryJournal.id).where(InventoryJournal.request_id == request_id)
    )
    journal_id = journal.scalar_one_or_none()
    if journal_id is None:
        return []
    rows = await session.execute(
        select(
            InventoryEntry.account_code, InventoryEntry.debit, InventoryEntry.credit
        ).where(InventoryEntry.journal_id == journal_id)
    )
    return rows.all()


@pytest.mark.asyncio
async def test_receipt_approve_creates_balanced_double_entry_and_updates_balance(async_client):
    maker = await _headers(async_client, MAKER)
    checker = await _headers(async_client, CHECKER)
    dest_id, item_id = await _first_location_and_item(async_client, maker)

    r = await _create_receipt(async_client, maker, dest_id, item_id, quantity="5")
    assert r.status_code == 201, r.text
    request_id = r.json()["id"]

    async with AsyncSessionLocal() as session:
        before_qty = await _balance_qty(session, dest_id, item_id)

    r = await async_client.post(
        f"/inventory/requests/{request_id}/submit", headers=maker
    )
    assert r.status_code == 200, r.text

    r = await async_client.post(
        f"/inventory/requests/{request_id}/approve",
        headers=_idem(checker),
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "posted"

    async with AsyncSessionLocal() as session:
        # 1. Tung dong nhap kho phai dung dung mot phia (du XOR co).
        entries = await _journal_entries_for_request(session, request_id)
        assert entries, "Phai co it nhat 1 bu toan"
        for code, debit, credit in entries:
            assert (Decimal(str(debit)) > 0) != (
                Decimal(str(credit)) > 0
            ), f"Dong {code} phai dung dung mot phia"

        # 2. Tong du = tong co -> tong tat ca cac entry = 0.
        debit_total = sum((Decimal(str(d)) for _, d, _ in entries), Decimal("0"))
        credit_total = sum((Decimal(str(c)) for _, _, c in entries), Decimal("0"))
        assert debit_total == credit_total, (
            f"Khong duoi: dr={debit_total} cr={credit_total}"
        )
        assert debit_total > 0, "Phai co duong du > 0"

        # 3. Balance cap nhat thuan: ton kho dich tang bang so luong nhap.
        after_qty = await _balance_qty(session, dest_id, item_id)
        assert after_qty == before_qty + Decimal("5"), (
            f"Balance khong thuan: before={before_qty} after={after_qty}"
        )


@pytest.mark.asyncio
async def test_unbalanced_posting_is_rejected():
    async with AsyncSessionLocal() as session:
        journal = SimpleNamespace(
            id=uuid.uuid4(),
            posted_at=datetime.now(UTC),
            correlation_id="unbalanced-1",
        )
        with pytest.raises(ValueError, match="not balanced"):
            await post_subledger_journal(
                session,
                source_type="inventory",
                source_journal=journal,
                entries=[
                    SimpleNamespace(account_code="156", debit=Decimal("10"), credit=Decimal("0")),
                ],
            )


@pytest.mark.asyncio
async def test_each_entry_has_exactly_one_positive_side():
    async with AsyncSessionLocal() as session:
        journal = SimpleNamespace(
            id=uuid.uuid4(),
            posted_at=datetime.now(UTC),
            correlation_id="one-sided-1",
        )
        with pytest.raises(ValueError, match="exactly one positive side"):
            await post_subledger_journal(
                session,
                source_type="inventory",
                source_journal=journal,
                entries=[
                    SimpleNamespace(account_code="156", debit=Decimal("10"), credit=Decimal("0")),
                    SimpleNamespace(account_code="331", debit=Decimal("5"), credit=Decimal("5")),
                ],
            )
