"""Integration test for the stocktake assessment agent against a real Postgres.

Skipped unless DATABASE_URL points at a dedicated test database (name contains
"_test") whose schema has been migrated (alembic upgrade head).  The assessment
workflow is read-only: this test asserts no inventory/ledger rows are mutated.
"""
import os
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import text

from app.ai.stocktake_agent import (
    AssessmentVerdict,
    StocktakeAssessmentOptions,
    StocktakeAssessmentWorkflow,
)
from app.database import AsyncSessionLocal
from app.models.iam import ScopeGrant, User
from app.models.inventory import Item, Location, Stocktake, StocktakeLine


def _dsn_is_test() -> bool:
    return "_test" in os.environ.get("DATABASE_URL", "").lower()


pytestmark = pytest.mark.skipif(
    not _dsn_is_test(),
    reason="requires a dedicated test Postgres (DATABASE_URL database name contains _test)",
)

_COUNT_TABLES = (
    "inv_balances",
    "inv_movements",
    "inv_stocktake_lines",
    "inv_stocktakes",
    "inv_requests",
    "inv_request_lines",
)


async def _require_schema(session):
    res = await session.execute(text("SELECT to_regclass('inv_stocktakes')"))
    if res.scalar() is None:
        pytest.skip("inv_stocktakes table missing; run `alembic upgrade head` against the test DB first")


async def _counts(session):
    totals = {}
    for table in _COUNT_TABLES:
        res = await session.execute(text(f"SELECT count(*) FROM {table}"))
        totals[table] = res.scalar()
    return totals


@pytest.fixture
async def db_session():
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
            await _require_schema(session)
            yield session
    except Exception as exc:  # noqa: BLE001 - skip when no test Postgres available
        pytest.skip(f"cannot reach test Postgres: {type(exc).__name__}: {exc}")


async def _seed_stocktake(session, st_id, maker_id, checker_id, loc_id, item_id, variance, note, maker_user, checker_user):
    now = datetime.now(UTC)
    session.add(User(id=maker_id, username=maker_user, password_hash="x", status="active", display_name_demo="E2E Maker"))
    session.add(User(id=checker_id, username=checker_user, password_hash="x", status="active", display_name_demo="E2E Checker"))
    session.add(Location(id=loc_id, code=f"LOC-E2E-{uuid4().hex[:8]}", name="E2e kho", active=True))
    session.add(
        Item(id=item_id, sku=f"SKU-E2E-{uuid4().hex[:8]}", name="Tra den", unit="lon", selling_price=Decimal("10000"))
    )
    await session.flush()
    session.add(ScopeGrant(id=uuid4(), user_id=checker_id, location_id=loc_id))
    session.add(
        Stocktake(
            id=st_id,
            location_id=loc_id,
            status="open",
            maker_id=maker_id,
            note=note,
            version=1,
            updated_at=now,
        )
    )
    session.add(
        StocktakeLine(
            id=uuid4(),
            stocktake_id=st_id,
            item_id=item_id,
            book_qty=Decimal("10"),
            counted_qty=Decimal("10") + variance,
            variance=variance,
        )
    )
    await session.commit()


@pytest.mark.asyncio
async def test_stocktake_assessment_is_read_only_normal(db_session):
    st_id = uuid4()
    maker_id = uuid4()
    checker_id = uuid4()
    loc_id = uuid4()
    item_id = uuid4()

    maker_user = f"e2e_maker_{uuid4().hex[:8]}"
    checker_user = f"e2e_checker_{uuid4().hex[:8]}"
    await _seed_stocktake(
        db_session, st_id, maker_id, checker_id, loc_id, item_id, Decimal("-2"), "Ca sang dem so luong, mat 2 lon.", maker_user, checker_user
    )

    before = await _counts(db_session)
    result = await StocktakeAssessmentWorkflow(
        StocktakeAssessmentOptions(enabled=True, staleness_minutes=60)
    ).assess_async(str(st_id), checker_user, db_session)
    after = await _counts(db_session)

    assert result.is_read_only is True
    assert result.verdict == AssessmentVerdict.NORMAL
    assert result.triaged.can_proceed is True
    assert result.critiqued.actions_blocked is False
    lowered = result.recommendation.lower()
    for word in ("approved", "posted", "mutated"):
        assert word not in lowered
    assert before == after, "read-only assessment must not mutate inventory or ledger rows"


@pytest.mark.asyncio
async def test_stocktake_assessment_high_risk_read_only(db_session):
    st_id = uuid4()
    maker_id = uuid4()
    checker_id = uuid4()
    loc_id = uuid4()
    item_id = uuid4()

    maker_user = f"e2e_maker_{uuid4().hex[:8]}"
    checker_user = f"e2e_checker_{uuid4().hex[:8]}"
    await _seed_stocktake(
        db_session, st_id, maker_id, checker_id, loc_id, item_id, Decimal("12"), "Lech so luong lon ca chieu.", maker_user, checker_user
    )

    before = await _counts(db_session)
    result = await StocktakeAssessmentWorkflow(
        StocktakeAssessmentOptions(enabled=True, staleness_minutes=60)
    ).assess_async(str(st_id), checker_user, db_session)
    after = await _counts(db_session)

    assert result.is_read_only is True
    assert result.verdict == AssessmentVerdict.HIGH_RISK
    assert result.triaged.can_proceed is True
    assert result.critiqued.actions_blocked is True
    assert "Recommend Checker review via Maker/Checker approval flow" in result.recommendation
    assert "Agent cannot approve/post/change inventory" in result.recommendation
    assert before == after, "read-only assessment must not mutate inventory or ledger rows"
