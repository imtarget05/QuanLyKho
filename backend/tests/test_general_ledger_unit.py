import uuid
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app.api.routes import inventory as inventory_routes
from app.api.routes import reports
from app.models.ledger import BASE_CHART_OF_ACCOUNTS
from app.services.general_ledger import post_subledger_journal


def _entry(account_code: str, debit: str, credit: str):
    return SimpleNamespace(
        account_code=account_code,
        debit=Decimal(debit),
        credit=Decimal(credit),
    )


def _database():
    db = Mock()
    db.execute = AsyncMock()
    db.flush = AsyncMock()
    result = Mock()
    result.scalar_one_or_none.return_value = uuid.uuid4()
    db.execute.return_value = result
    return db


def test_base_chart_has_required_accounts_and_simulation_offset():
    accounts = {
        code: (account_type, normal_balance, simulation_only)
        for code, _, account_type, normal_balance, simulation_only
        in BASE_CHART_OF_ACCOUNTS
    }

    assert {"111", "112", "152", "156", "331", "511", "632"} <= accounts.keys()
    assert accounts["SIM_OFFSET:DEMO"][2] is True
    assert accounts["156"][2] is False


@pytest.mark.asyncio
async def test_inventory_subledger_is_copied_to_general_ledger():
    db = _database()
    journal = SimpleNamespace(
        id=uuid.uuid4(),
        posted_at=datetime.now(UTC),
        correlation_id="inventory-123",
    )
    entries = [
        _entry("156", "125.00", "0"),
        _entry("331", "0", "125.00"),
    ]

    await post_subledger_journal(
        db, source_type="inventory", source_journal=journal, entries=entries
    )

    db.execute.assert_awaited_once()
    db.flush.assert_awaited_once()
    gl_entries = db.add_all.call_args.args[0]
    assert [(entry.account_code, entry.debit, entry.credit) for entry in gl_entries] == [
        ("156", Decimal("125.00"), Decimal("0")),
        ("331", Decimal("0"), Decimal("125.00")),
    ]


@pytest.mark.asyncio
async def test_cash_subledger_marks_general_ledger_as_simulation_only():
    db = _database()
    journal = SimpleNamespace(
        id=uuid.uuid4(),
        posted_at=datetime.now(UTC),
        correlation_id="cash-123",
    )
    entries = [
        _entry(f"SIM_CASH:{uuid.uuid4()}", "25.00", "0"),
        _entry("SIM_OFFSET:DEMO", "0", "25.00"),
    ]

    await post_subledger_journal(
        db, source_type="cash_simulation", source_journal=journal, entries=entries
    )

    assert db.execute.await_count == 2
    gl_entries = db.add_all.call_args.args[0]
    assert {entry.account_code for entry in gl_entries} == {
        entries[0].account_code,
        "SIM_OFFSET:DEMO",
    }


@pytest.mark.asyncio
async def test_unbalanced_or_unknown_inventory_postings_are_rejected():
    db = _database()
    journal = SimpleNamespace(
        id=uuid.uuid4(),
        posted_at=datetime.now(UTC),
        correlation_id="bad-123",
    )

    with pytest.raises(ValueError, match="not balanced"):
        await post_subledger_journal(
            db,
            source_type="inventory",
            source_journal=journal,
            entries=[_entry("156", "10.00", "0")],
        )

    with pytest.raises(ValueError, match="unsupported account"):
        await post_subledger_journal(
            db,
            source_type="inventory",
            source_journal=journal,
            entries=[
                _entry("999", "10.00", "0"),
                _entry("331", "0", "10.00"),
            ],
        )

    db.execute.assert_not_awaited()


@pytest.mark.parametrize(
    ("direction", "expected"),
    [
        ("increase", [("156", Decimal("2"), Decimal("0")), ("632", Decimal("0"), Decimal("2"))]),
        ("decrease", [("156", Decimal("0"), Decimal("2")), ("632", Decimal("2"), Decimal("0"))]),
    ],
)
@pytest.mark.asyncio
async def test_inventory_adjustments_balance_the_offsetting_account(
    monkeypatch, direction, expected
):
    posting = AsyncMock()
    monkeypatch.setattr(inventory_routes, "post_subledger_journal", posting)
    db = Mock()
    db.flush = AsyncMock()
    request = SimpleNamespace(id=uuid.uuid4(), kind="adjustment")
    line = SimpleNamespace(
        quantity=Decimal("2"),
        unit_price=None,
        direction=direction,
    )

    await inventory_routes._post_inventory_journal(
        db, request, [line], datetime.now(UTC), "adjustment-123"
    )

    posted_entries = posting.await_args.kwargs["entries"]
    assert [
        (entry.account_code, entry.debit, entry.credit)
        for entry in posted_entries
    ] == expected


@pytest.mark.asyncio
async def test_general_ledger_report_is_scoped_and_labels_simulation(
    monkeypatch,
):
    location_id = uuid.uuid4()
    cashbox_id = uuid.uuid4()
    monkeypatch.setattr(
        reports,
        "get_accessible_location_ids",
        AsyncMock(return_value={location_id}),
    )
    monkeypatch.setattr(
        reports,
        "get_accessible_cashbox_ids",
        AsyncMock(return_value={cashbox_id}),
    )
    monkeypatch.setattr(
        reports,
        "get_user_capabilities",
        AsyncMock(
            return_value=["inventory:view_balances", "cash:view_balances"]
        ),
    )
    db = Mock()
    result = Mock()
    result.all.return_value = [
        ("156", "Merchandise inventory", Decimal("125.00"), Decimal("0"), False),
        (
            "SIM_OFFSET:DEMO",
            "Simulation opening and offset account",
            Decimal("0"),
            Decimal("25.00"),
            True,
        ),
    ]
    db.execute = AsyncMock(return_value=result)

    response = await reports.general_ledger(
        current_user=SimpleNamespace(id=uuid.uuid4()),
        db=db,
        date_from=None,
        date_to=None,
        include_simulation=True,
        limit=100,
        offset=0,
    )

    assert response["currency"] == "VND"
    assert response["includes_simulation"] is True
    assert response["accounts"][0]["debit_total"] == "125.00"
    assert response["accounts"][1]["simulation_only"] is True
    statement = str(db.execute.await_args.args[0])
    assert "inv_requests.source_id" in statement
    assert "inv_requests.dest_id" in statement
    assert "cash_requests.cashbox_id" in statement


@pytest.mark.asyncio
async def test_inventory_only_report_excludes_cash_and_simulation_by_default(
    monkeypatch,
):
    monkeypatch.setattr(
        reports,
        "get_accessible_location_ids",
        AsyncMock(return_value={uuid.uuid4()}),
    )
    cash_scope = AsyncMock(return_value={uuid.uuid4()})
    monkeypatch.setattr(reports, "get_accessible_cashbox_ids", cash_scope)
    monkeypatch.setattr(
        reports,
        "get_user_capabilities",
        AsyncMock(return_value=["inventory:view_balances"]),
    )
    db = Mock()
    result = Mock()
    result.all.return_value = []
    db.execute = AsyncMock(return_value=result)

    await reports.general_ledger(
        current_user=SimpleNamespace(id=uuid.uuid4()),
        db=db,
        date_from=None,
        date_to=None,
        include_simulation=False,
        limit=100,
        offset=0,
    )

    cash_scope.assert_not_awaited()
    statement = str(db.execute.await_args.args[0])
    assert "cash_requests" not in statement
    assert "gl_journals.simulation_only IS false" in statement
