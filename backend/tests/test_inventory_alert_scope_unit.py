"""Branch scope guards for stock thresholds and alert queries."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from starlette.requests import Request

from app.api.errors import AppError
from app.features.inventory import routes as inventory

ALLOWED_LOCATION = uuid.UUID("22222222-2222-4222-8222-222222222222")
OTHER_LOCATION = uuid.UUID("33333333-3333-4333-8333-333333333333")


def _db():
    db = MagicMock()
    db.execute = AsyncMock(return_value=MagicMock())
    db.execute.return_value.all.return_value = []
    db.execute.return_value.scalars.return_value.all.return_value = []
    return db


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("route", "kwargs"),
    [
        (inventory.low_stock_alerts, {"location_id": None}),
        (inventory.expiry_alerts, {"days": 7}),
        (inventory.list_stock_levels, {"location_id": None, "item_id": None}),
        (inventory.list_low_stock, {"location_id": None}),
    ],
)
async def test_inventory_alert_queries_filter_to_branch(monkeypatch, route, kwargs):
    monkeypatch.setattr(
        inventory, "get_accessible_location_ids", AsyncMock(return_value={ALLOWED_LOCATION})
    )
    db = _db()
    await route(**kwargs, db=db, **({"current_user": object()} if "current_user" in route.__code__.co_varnames else {"user": object()}))

    statement = db.execute.call_args.args[0]
    sql = str(statement.compile(compile_kwargs={"literal_binds": True}))
    assert ALLOWED_LOCATION.hex in sql


@pytest.mark.asyncio
async def test_stock_threshold_write_rejects_other_branch(monkeypatch):
    monkeypatch.setattr(
        inventory, "get_accessible_location_ids", AsyncMock(return_value={ALLOWED_LOCATION})
    )
    db = _db()
    request = Request(
        {
            "type": "http",
            "method": "PUT",
            "path": "/inventory/stock-levels",
            "headers": [(b"idempotency-key", b"prior-response")],
        }
    )
    replay = MagicMock(return_value={"id": "old-cached-record"})
    monkeypatch.setattr(inventory, "_replay", replay)
    with pytest.raises(AppError) as exc:
        await inventory.put_stock_level(
            {"location_id": str(OTHER_LOCATION), "item_id": str(uuid.uuid4()), "min_qty": "5"},
            request=request,
            user=object(),
            db=db,
        )
    assert exc.value.http_status == 404
    replay.assert_not_called()
    db.execute.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("route", "kwargs"),
    [
        (inventory.low_stock_alerts, {"location_id": str(OTHER_LOCATION)}),
        (inventory.list_stock_levels, {"location_id": str(OTHER_LOCATION), "item_id": None}),
        (inventory.list_low_stock, {"location_id": str(OTHER_LOCATION)}),
    ],
)
async def test_location_filter_cannot_widen_branch_scope(monkeypatch, route, kwargs):
    monkeypatch.setattr(
        inventory, "get_accessible_location_ids", AsyncMock(return_value={ALLOWED_LOCATION})
    )
    db = _db()
    user_arg = {"current_user": object()} if "current_user" in route.__code__.co_varnames else {"user": object()}
    await route(**kwargs, db=db, **user_arg)

    statement = db.execute.call_args.args[0]
    sql = str(statement.compile(compile_kwargs={"literal_binds": True}))
    where_clause = sql.split("WHERE", 1)[1]
    assert ALLOWED_LOCATION.hex in where_clause
    assert OTHER_LOCATION.hex in where_clause
    assert " AND " in where_clause


@pytest.mark.asyncio
async def test_expiry_alert_reads_current_positive_lot_balance(monkeypatch):
    monkeypatch.setattr(
        inventory, "get_accessible_location_ids", AsyncMock(return_value={ALLOWED_LOCATION})
    )
    db = _db()
    await inventory.expiry_alerts(days=7, current_user=object(), db=db)
    sql = str(db.execute.call_args.args[0].compile(compile_kwargs={"literal_binds": True}))
    assert "FROM inv_lot_balances" in sql
    assert "inv_lot_balances.quantity > 0" in sql
    assert ALLOWED_LOCATION.hex in sql
