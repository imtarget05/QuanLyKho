"""Unit tests for the stocktake assessment agent (deterministic, no database)."""
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.ai.stocktake_agent import (
    AssessmentVerdict,
    StocktakeAssessmentOptions,
    StocktakeAssessmentWorkflow,
)
from app.models.iam import User
from app.models.inventory import (
    InventoryRequest,
    InventoryRequestLine,
    Stocktake,
    StocktakeLine,
)

FORBIDDEN_WORDS = ("approved", "posted", "mutated")


class _FakeScalars:
    def __init__(self, rows):
        self._rows = list(rows)

    def first(self):
        return self._rows[0] if self._rows else None

    def all(self):
        return list(self._rows)


class _FakeResult:
    def __init__(self, rows=(), scalar=None):
        self._rows = list(rows)
        self._scalar = scalar

    def scalars(self):
        return _FakeScalars(self._rows)

    def scalar(self):
        return self._scalar

    def all(self):
        return list(self._rows)


class _FakeSession:
    def __init__(self, handler):
        self.handler = handler

    async def execute(self, query):
        return await self.handler(query)


def _eq_value(query, column_name):
    from sqlalchemy.sql.elements import BindParameter

    for criterion in getattr(query, "_where_criteria", []) or []:
        for column_side, value_side in ((criterion.left, criterion.right), (criterion.right, criterion.left)):
            if isinstance(value_side, BindParameter) and getattr(column_side, "name", None) == column_name:
                return value_side.value
    return None


def _table_of(query):
    q = str(query)
    if "inv_stocktake_lines" in q:
        return "stocktake_lines"
    if "inv_request_lines" in q:
        return "request_lines"
    if "inv_stocktakes" in q:
        return "stocktakes"
    if "inv_requests" in q:
        return "requests"
    if "iam_scope_grants" in q:
        return "scope_grants"
    if "inv_locations" in q:
        return "locations"
    if "iam_user_roles" in q:
        return "user_roles"
    if "iam_users" in q:
        return "users"
    return None


def make_handler(store):
    async def handler(query):
        table = _table_of(query)
        q = str(query)
        if table == "users":
            username = _eq_value(query, "username")
            user = next((u for u in store["users"] if u.username == username), None)
            return _FakeResult(rows=[user] if user is not None else [], scalar=user)
        if table == "user_roles":
            user_id = _eq_value(query, "user_id")
            return _FakeResult(rows=[(r,) for r in store["role_map"].get(str(user_id), [])])
        if table == "locations":
            branch_id = _eq_value(query, "branch_id")
            rows = [row.id for row in store["locations"] if str(row.id) == str(branch_id)] if branch_id else []
            return _FakeResult(rows=rows)
        if table == "scope_grants":
            user_id = _eq_value(query, "user_id")
            return _FakeResult(rows=store["grants_map"].get(str(user_id), []))
        if table == "requests":
            rid = _eq_value(query, "id")
            obj = store["requests_map"].get(str(rid))
            return _FakeResult(rows=[obj] if obj is not None else [], scalar=obj)
        if table == "stocktakes":
            rid = _eq_value(query, "id")
            obj = store["stocktakes_map"].get(str(rid))
            return _FakeResult(rows=[obj] if obj is not None else [], scalar=obj)
        if table == "request_lines":
            rid = _eq_value(query, "request_id")
            rows = [line for line in store["request_lines"] if str(line.request_id) == str(rid)]
            if "sum" in q:
                return _FakeResult(scalar=sum(float(line.quantity) for line in rows))
            return _FakeResult(scalar=len(rows))
        if table == "stocktake_lines":
            stid = _eq_value(query, "stocktake_id")
            rows = [line for line in store["stocktake_lines"] if str(line.stocktake_id) == str(stid)]
            if "sum" in q:
                return _FakeResult(scalar=sum(abs(float(line.variance)) for line in rows))
            return _FakeResult(scalar=len(rows))
        return _FakeResult()

    return handler


def _normal_store():
    maker_id = uuid4()
    assessor_id = uuid4()
    loc_a = uuid4()
    loc_b = uuid4()
    item_id = uuid4()
    req_id = uuid4()
    now = datetime.now(UTC)
    maker_user = User(id=maker_id, username="maker_one", password_hash="x", status="active")
    assessor_user = User(id=assessor_id, username="assessor_one", password_hash="x", status="active")
    req = InventoryRequest(
        id=req_id,
        kind="adjustment",
        status="submitted",
        maker_id=maker_id,
        source_id=loc_a,
        dest_id=None,
        reason="Ca sang leth ca phe, mat 2 lon sua.",
        version=1,
        created_by=maker_id,
        updated_at=now,
    )
    line = InventoryRequestLine(
        id=uuid4(), request_id=req_id, item_id=item_id, quantity=Decimal("5"), direction="increase"
    )
    store = {
        "users": [maker_user, assessor_user],
        "role_map": {str(maker_id): [], str(assessor_id): []},
        "grants_map": {
            str(maker_id): [SimpleNamespace(location_id=loc_a, branch_id=None)],
            str(assessor_id): [SimpleNamespace(location_id=loc_a, branch_id=None)],
        },
        "locations": [],
        "requests_map": {str(req_id): req},
        "stocktakes_map": {},
        "request_lines": [line],
        "stocktake_lines": [],
    }
    return store, req_id, maker_id, assessor_id, loc_a, loc_b


async def _assess(store, request_id, assessed_by="assessor_one"):
    session = _FakeSession(make_handler(store))
    return await StocktakeAssessmentWorkflow(
        StocktakeAssessmentOptions(enabled=True, staleness_minutes=60)
    ).assess_async(request_id, assessed_by, session)


def test_options_defaults():
    options = StocktakeAssessmentOptions()
    assert options.enabled is False
    assert options.staleness_minutes == 60
    assert options.source_sha == ""


def test_verdict_values():
    assert AssessmentVerdict.NORMAL == "normal"
    assert AssessmentVerdict.HIGH_RISK == "high_risk"
    assert AssessmentVerdict.STALE_VERSION == "stale_version"
    assert AssessmentVerdict.MISSING_EVIDENCE == "missing_evidence"
    assert AssessmentVerdict.SCOPE_VIOLATION == "scope_violation"
    assert AssessmentVerdict.POLICY_VIOLATION == "policy_violation"


@pytest.mark.asyncio
async def test_triage_normal():
    store, req_id, _maker_id, assessor_id, loc_a, _loc_b = _normal_store()
    result = await _assess(store, req_id, "assessor_one")
    assert result.verdict == AssessmentVerdict.NORMAL
    assert result.triaged.can_proceed is True
    assert result.is_read_only is True
    assert result.critiqued.actions_blocked is False
    assert result.critiqued.version_fresh is True
    assert result.critiqued.evidence_validated is True


@pytest.mark.asyncio
async def test_triage_high_risk():
    store, req_id, _maker_id, _assessor_id, loc_a, _loc_b = _normal_store()
    store["request_lines"][0].quantity = Decimal("12")
    result = await _assess(store, req_id, "assessor_one")
    assert result.verdict == AssessmentVerdict.HIGH_RISK
    assert result.triaged.can_proceed is True
    assert result.critiqued.actions_blocked is True


@pytest.mark.asyncio
async def test_triage_high_risk_stocktake_path():
    store, req_id, _maker_id, _assessor_id, loc_a, _loc_b = _normal_store()
    store["requests_map"] = {}
    st_id = uuid4()
    st = Stocktake(
        id=st_id,
        location_id=loc_a,
        status="open",
        maker_id=uuid4(),
        note="Ca sang dem so luong.",
        version=1,
        updated_at=datetime.now(UTC),
    )
    store["stocktakes_map"][str(st_id)] = st
    store["stocktake_lines"] = [
        StocktakeLine(id=uuid4(), stocktake_id=st_id, item_id=uuid4(), variance=Decimal("12"))
    ]
    result = await _assess(store, st_id, "assessor_one")
    assert result.verdict == AssessmentVerdict.HIGH_RISK
    assert result.triaged.can_proceed is True


@pytest.mark.asyncio
async def test_triage_stale_version():
    store, req_id, _maker_id, _assessor_id, loc_a, _loc_b = _normal_store()
    store["requests_map"][str(req_id)].updated_at = datetime.now(UTC) - timedelta(hours=5)
    result = await _assess(store, req_id, "assessor_one")
    assert result.verdict == AssessmentVerdict.STALE_VERSION
    assert result.triaged.can_proceed is False
    assert result.critiqued.actions_blocked is True
    assert result.critiqued.version_fresh is False


@pytest.mark.asyncio
async def test_triage_missing_evidence_no_reason():
    store, req_id, _maker_id, _assessor_id, loc_a, _loc_b = _normal_store()
    store["requests_map"][str(req_id)].reason = ""
    result = await _assess(store, req_id, "assessor_one")
    assert result.verdict == AssessmentVerdict.MISSING_EVIDENCE
    assert result.triaged.can_proceed is False


@pytest.mark.asyncio
async def test_triage_missing_evidence_no_lines():
    store, req_id, _maker_id, _assessor_id, loc_a, _loc_b = _normal_store()
    store["request_lines"] = []
    result = await _assess(store, req_id, "assessor_one")
    assert result.verdict == AssessmentVerdict.MISSING_EVIDENCE
    assert result.triaged.can_proceed is False


@pytest.mark.asyncio
async def test_triage_scope_violation():
    store, req_id, _maker_id, _assessor_id, _loc_a, loc_b = _normal_store()
    store["requests_map"][str(req_id)].source_id = loc_b
    result = await _assess(store, req_id, "assessor_one")
    assert result.verdict == AssessmentVerdict.SCOPE_VIOLATION
    assert result.triaged.can_proceed is False


@pytest.mark.asyncio
async def test_triage_policy_violation_maker_self_approval():
    store, req_id, maker_id, _assessor_id, _loc_a, _loc_b = _normal_store()
    result = await _assess(store, req_id, "maker_one")
    assert result.verdict == AssessmentVerdict.POLICY_VIOLATION
    assert result.triaged.can_proceed is False


@pytest.mark.asyncio
async def test_request_not_found():
    store, _req_id, _maker_id, _assessor_id, _loc_a, _loc_b = _normal_store()
    result = await _assess(store, uuid4(), "assessor_one")
    assert result.verdict == AssessmentVerdict.MISSING_EVIDENCE
    assert result.triaged.can_proceed is False


@pytest.mark.asyncio
async def test_disabled_flag_off():
    store, req_id, _maker_id, _assessor_id, _loc_a, _loc_b = _normal_store()
    session = _FakeSession(make_handler(store))
    result = await StocktakeAssessmentWorkflow().assess_async(req_id, "assessor_one", session)
    assert result.verdict == AssessmentVerdict.NORMAL
    assert result.triaged.can_proceed is False
    assert result.is_read_only is True
    assert "disabled" in result.triaged.reasoning.lower()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "setup",
    [
        ("normal", {}),
        ("high_risk", {"qty": Decimal("12")}),
        ("stale", {"updated_at": datetime.now(UTC) - timedelta(hours=5)}),
        ("missing_evidence", {"reason": ""}),
        ("scope_violation", {"source_id_override": True}),
        ("policy_violation", {"assessed_by": "maker_one"}),
    ],
)
async def test_is_read_only_and_no_forbidden_words(setup):
    name, overrides = setup
    store, req_id, maker_id, _assessor_id, loc_a, loc_b = _normal_store()
    req = store["requests_map"][str(req_id)]
    if "qty" in overrides:
        store["request_lines"][0].quantity = overrides["qty"]
    if "updated_at" in overrides:
        req.updated_at = overrides["updated_at"]
    if "reason" in overrides:
        req.reason = overrides["reason"]
    if overrides.get("source_id_override"):
        req.source_id = loc_b
    assessed_by = overrides.get("assessed_by", "assessor_one")
    result = await _assess(store, req_id, assessed_by)
    assert result.is_read_only is True
    lowered = result.recommendation.lower()
    for word in FORBIDDEN_WORDS:
        assert word not in lowered, f"forbidden word {word!r} in recommendation: {result.recommendation}"


@pytest.mark.asyncio
async def test_critic_cannot_lower_deterministic_risk():
    store, req_id, maker_id, _assessor_id, loc_a, _loc_b = _normal_store()
    store["request_lines"][0].quantity = Decimal("12")
    result = await _assess(store, req_id, "assessor_one")
    assert result.verdict == AssessmentVerdict.HIGH_RISK
    assert result.analyzed.cannot_lower_deterministic_risk is True
    assert result.triaged.verdict == result.verdict
    assert result.critiqued.actions_blocked is True

    store2, req_id2, _m2, _a2, _la2, _lb2 = _normal_store()
    result2 = await _assess(store2, req_id2, "assessor_one")
    assert result2.verdict == AssessmentVerdict.NORMAL
    assert result2.analyzed.cannot_lower_deterministic_risk is True
    assert result2.critiqued.actions_blocked is False
