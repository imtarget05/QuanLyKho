"""B2 — Identity/Auth: negative scope tests for cross-branch and limited-view access.

These tests do NOT rely on demo seed data for the negative path. They create
their own users and commit to the same test database used by the rest of the
suite, so a user with no (or no relevant) capabilities is always denied.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import text

from app.database import AsyncSessionLocal

PASSWORD = "Wave2Secure123!"

BRANCH_HO = "11111111-1111-4111-8111-111111111111"
BRANCH_A = "22222222-2222-4222-8222-222222222222"
BRANCH_B = "33333333-3333-4333-8333-333333333333"


async def _sql(sql: str, **params):
    """Run a short SQL statement against the test database and commit."""
    async with AsyncSessionLocal() as session:
        await session.execute(text(sql), params)
        await session.commit()


async def _rows(sql: str, **params) -> list:
    """Run a read-only SQL statement and return the fetched rows."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(text(sql), params)
        return result.fetchall()


async def _ensure_user(username: str, role_code: str, branch_id: str | None = None) -> str:
    """Insert (or re-use) a user with a fixed role and commit."""
    from app.api.routes.auth_utils import get_password_hash

    row = await _rows(
        "SELECT id FROM iam_users WHERE username = :u", u=username
    )
    user_id = row[0][0] if row else str(uuid.uuid4())
    if not row:
        await _sql(
            "INSERT INTO iam_users (id, username, password_hash, status, display_name_demo, "
            "email, branch_id) VALUES (:id, :u, :p, 'active', :d, :e, :b)",
            id=user_id,
            u=username,
            p=get_password_hash(PASSWORD),
            d=f"scope test {username}",
            e=f"{username}@bankops.internal",
            b=branch_id,
        )

    await _sql("DELETE FROM iam_user_roles WHERE user_id = :id", id=user_id)
    await _sql(
        "INSERT INTO iam_user_roles (user_id, role_code) VALUES (:id, :r)", id=user_id, r=role_code
    )
    return str(user_id)


async def _login(client, username: str, password: str = PASSWORD) -> dict:
    response = await client.post("/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


# ---------------------------------------------------------------------------
# S7 — token + capability gates on the activity/audit streams
# ---------------------------------------------------------------------------
class TestActivityAuthorization:
    async def test_activity_endpoints_require_capability(self, client):
        username = f"w2_nocap_{uuid.uuid4().hex[:8]}"
        await _ensure_user(username, "no_view_role", BRANCH_HO)
        headers = await _login(client, username)

        # Authenticated but no `activity:view`/`audit:view` capability -> 403.
        for path in (
            "/activity",
            "/activity/",
            "/activity/stream",
            "/events/stream",
            "/audit-events",
        ):
            resp = await client.get(path, headers=headers)
            assert (
                resp.status_code == 403
            ), f"{path} should require activity:view/audit:view"

    async def test_activity_endpoints_deny_anonymous_access(self, client):
        assert (await client.get("/activity")).status_code == 401
        assert (await client.get("/activity/")).status_code == 401
        assert (await client.get("/activity/stream")).status_code == 401
        assert (await client.get("/events/stream")).status_code == 401
        assert (await client.get("/audit-events")).status_code == 401

    async def test_403_for_no_capability_user(self, client):
        # S13/S11 still apply, but capability deny is checked on the auth
        # surface before any DB access.
        username = f"w2_deny_{uuid.uuid4().hex[:8]}"
        await _ensure_user(username, "no_view_role", BRANCH_HO)
        headers = await _login(client, username)

        assert (await client.get("/reports/inventory-daily", headers=headers)).status_code == 403
        assert (await client.get("/reports/cashflow-daily", headers=headers)).status_code == 403
        assert (await client.get("/reports/stagnation", headers=headers)).status_code == 403


# ---------------------------------------------------------------------------
# Scope bypass regression: `location_id` query param must NARROW scope,
# never WIDEN it. A user scoped to branch A must not read branch B data by
# passing `?location_id=<branch B location>`.
# ---------------------------------------------------------------------------
class TestReportLocationScopeNarrowing:
    @staticmethod
    async def _make_location(code: str, branch_id: str) -> str:
        loc_id = str(uuid.uuid4())
        await _sql(
            "INSERT INTO inv_locations (id, code, name, active, branch_id) "
            "VALUES (:id, :c, :n, true, :b)",
            id=loc_id,
            c=code,
            n=code,
            b=branch_id,
        )
        return loc_id

    @staticmethod
    async def _make_balance(loc_id: str, item_id: str, qty: str) -> None:
        await _sql(
            "INSERT INTO inv_balances (location_id, item_id, quantity, version, "
            "reserved_quantity) VALUES (:l, :i, :q, 1, 0)",
            l=loc_id,
            i=item_id,
            q=qty,
        )

    async def test_location_id_param_cannot_widen_scope(self, client):
        # A scoped user (branch A) with a report capability.
        username = f"w2_scope_{uuid.uuid4().hex[:8]}"
        user_id = await _ensure_user(username, "staff", BRANCH_A)
        headers = await _login(client, username)

        item_rows = await _rows(
            "SELECT id FROM inv_items WHERE active AND NOT tracked_serial LIMIT 1"
        )
        assert item_rows, "cần ít nhất một item trong danh mục để dựng balance"
        item_id = str(item_rows[0][0])

        loc_a = await self._make_location(f"SCOPE-A-{uuid.uuid4().hex[:6]}", BRANCH_A)
        loc_b = await self._make_location(f"SCOPE-B-{uuid.uuid4().hex[:6]}", BRANCH_B)
        try:
            # Balance chỉ tồn tại ở branch B — user branch A không được thấy.
            await self._make_balance(loc_b, item_id, "42")

            # 1) Không truyền `location_id`: dữ liệu branch B bị ẩn.
            unscoped = await client.get("/reports/inventory-summary", headers=headers)
            assert unscoped.status_code == 200, unscoped.text
            assert all(
                Decimal(row["closing_qty"]) == Decimal("0") for row in unscoped.json()["items"]
            ), "user branch A không được thấy tồn kho của branch B"

            # 2) Truyền `location_id` của branch B: KHÔNG được mở rộng quyền.
            #    Phải rỗng y hệt trường hợp không truyền (trước đây bug: ghi đè
            #    scope bằng `{location_id}` => lộ tồn kho branch B).
            scoped = await client.get(
                "/reports/inventory-summary", headers=headers, params={"location_id": loc_b}
            )
            assert scoped.status_code == 200, scoped.text
            assert all(
                Decimal(row["closing_qty"]) == Decimal("0") for row in scoped.json()["items"]
            ), "`location_id` ngoài scope không được lộ dữ liệu branch B"

            # 3) `location_id` thuộc scope của user: vẫn xem được (không vỡ).
            own = await client.get(
                "/reports/inventory-summary", headers=headers, params={"location_id": loc_a}
            )
            assert own.status_code == 200, own.text
        finally:
            await _sql("DELETE FROM inv_balances WHERE location_id = :l", l=loc_b)
            await _sql("DELETE FROM inv_locations WHERE id = :l", l=loc_a)
            await _sql("DELETE FROM inv_locations WHERE id = :l", l=loc_b)
            await _sql("DELETE FROM iam_user_roles WHERE user_id = :id", id=user_id)


# ---------------------------------------------------------------------------
# Reconciliation (cash scope) must respect the caller's accessible cashboxes.
# A user scoped to branch A must not see journal exceptions of branch B.
# ---------------------------------------------------------------------------
class TestReconciliationCashboxScope:
    @staticmethod
    async def _make_cashbox(code: str, branch_id: str) -> str:
        box_id = str(uuid.uuid4())
        await _sql(
            "INSERT INTO cash_boxes (id, code, name, currency, active, branch_id) "
            "VALUES (:id, :c, :n, 'VND', true, :b)",
            id=box_id,
            c=code,
            n=code,
            b=branch_id,
        )
        return box_id

    async def _plant_unbalanced_journal(self, cashbox_id: str, maker_id: str) -> str:
        """Create a cash request + journal whose entries do NOT balance."""
        req_id = str(uuid.uuid4())
        await _sql(
            "INSERT INTO cash_requests (id, cashbox_id, kind, amount, status, maker_id, "
            "created_by, version) VALUES (:id, :b, 'receipt', 100, 'posted', :m, :m, 1)",
            id=req_id,
            b=cashbox_id,
            m=maker_id,
        )
        journal_id = str(uuid.uuid4())
        await _sql(
            "INSERT INTO cash_journals (id, request_id, posted_at, correlation_id) "
            "VALUES (:id, :r, now(), :c)",
            id=journal_id,
            r=req_id,
            c=f"scope-test-{uuid.uuid4().hex[:8]}",
        )
        # debit != credit => the reconciliation reports an exception for it.
        await _sql(
            "INSERT INTO cash_entries (id, journal_id, account_code, debit, credit) "
            "VALUES (:id, :j, 'SIM_CASH:TEST', 100, 0)",
            id=str(uuid.uuid4()),
            j=journal_id,
        )
        return journal_id

    async def test_cash_reconciliation_respects_cashbox_scope(self, client):
        username = f"w2_cashscope_{uuid.uuid4().hex[:8]}"
        user_id = await _ensure_user(username, "cash_sim_operator", BRANCH_A)
        headers = await _login(client, username)

        box_b = await self._make_cashbox(f"SCOPE-BOX-B-{uuid.uuid4().hex[:6]}", BRANCH_B)
        journal_b = None
        try:
            journal_b = await self._plant_unbalanced_journal(box_b, user_id)

            resp = await client.post(
                "/reconciliations",
                headers={**headers, "Idempotency-Key": str(uuid.uuid4())},
                json={"scope": "cash"},
            )
            assert resp.status_code == 201, resp.text
            subjects = [e["subject"] for e in resp.json()["exceptions"]]
            assert f"journal:{journal_b}" not in subjects, (
                "journal của két ngoài scope không được lộ qua reconciliation"
            )
        finally:
            if journal_b:
                request_rows = await _rows(
                    "SELECT request_id FROM cash_journals WHERE id = :j", j=journal_b
                )
                await _sql("DELETE FROM cash_entries WHERE journal_id = :j", j=journal_b)
                await _sql("DELETE FROM cash_journals WHERE id = :j", j=journal_b)
                if request_rows:
                    await _sql(
                        "DELETE FROM cash_requests WHERE id = :r",
                        r=str(request_rows[0][0]),
                    )
            await _sql("DELETE FROM cash_boxes WHERE id = :b", b=box_b)
            await _sql("DELETE FROM iam_user_roles WHERE user_id = :id", id=user_id)


# ---------------------------------------------------------------------------
# Reconciliation exception counters must respect the caller's accessible scope.
# ---------------------------------------------------------------------------
class TestReconciliationExceptionCounterScope:
    @staticmethod
    async def _make_cashbox(code: str, branch_id: str) -> str:
        box_id = str(uuid.uuid4())
        await _sql(
            "INSERT INTO cash_boxes (id, code, name, currency, active, branch_id) "
            "VALUES (:id, :c, :n, 'VND', true, :b)",
            id=box_id, c=code, n=code, b=branch_id,
        )
        return box_id

    async def _plant_unbalanced_journal(self, cashbox_id: str, maker_id: str) -> str:
        req_id = str(uuid.uuid4())
        await _sql(
            "INSERT INTO cash_requests (id, cashbox_id, kind, amount, status, maker_id, "
            "created_by, version) VALUES (:id, :b, 'receipt', 100, 'posted', :m, :m, 1)",
            id=req_id, b=cashbox_id, m=maker_id,
        )
        journal_id = str(uuid.uuid4())
        await _sql(
            "INSERT INTO cash_journals (id, request_id, posted_at, correlation_id) "
            "VALUES (:id, :r, now(), :c)",
            id=journal_id, r=req_id,
            c=f"scope-test-{uuid.uuid4().hex[:8]}",
        )
        await _sql(
            "INSERT INTO cash_entries (id, journal_id, account_code, debit, credit) "
            "VALUES (:id, :j, 'SIM_CASH:TEST', 100, 0)",
            id=str(uuid.uuid4()), j=journal_id,
        )
        return journal_id

    async def test_dashboard_exception_counters_respect_cashbox_scope(self, client):
        username = f"w2_exc_cash_{uuid.uuid4().hex[:8]}"
        user_id = await _ensure_user(username, "cash_sim_operator", BRANCH_A)
        headers = await _login(client, username)

        box_b = await self._make_cashbox(f"EXC-BOX-B-{uuid.uuid4().hex[:6]}", BRANCH_B)
        journal_b = None
        try:
            journal_b = await self._plant_unbalanced_journal(box_b, user_id)

            resp = await client.post(
                "/reconciliations",
                headers={**headers, "Idempotency-Key": str(uuid.uuid4())},
                json={"scope": "cash"},
            )
            assert resp.status_code == 201, resp.text
            assert f"journal:{journal_b}" not in [
                e["subject"] for e in resp.json()["exceptions"]
            ], "branch-B journal exception must not appear for branch-A user"

            dash = await client.get("/dashboard/summary", headers=headers)
            assert dash.status_code == 200, dash.text
            counters = dash.json()["reconciliation_counters"]
            assert counters["total_exceptions"] == 0, (
                f"branch-A user must see 0 total exceptions, got {counters['total_exceptions']}"
            )
            assert counters["cash_exceptions"] == 0
            assert counters["open_exceptions"] == 0
        finally:
            if journal_b:
                request_rows = await _rows(
                    "SELECT request_id FROM cash_journals WHERE id = :j", j=journal_b
                )
                await _sql("DELETE FROM cash_entries WHERE journal_id = :j", j=journal_b)
                await _sql("DELETE FROM cash_journals WHERE id = :j", j=journal_b)
                if request_rows:
                    await _sql(
                        "DELETE FROM cash_requests WHERE id = :r",
                        r=str(request_rows[0][0]),
                    )
            await _sql("DELETE FROM cash_boxes WHERE id = :b", b=box_b)
            await _sql("DELETE FROM iam_user_roles WHERE user_id = :id", id=user_id)

    async def test_dashboard_exception_counters_admin_sees_all(self, client):
        admin_username = f"w2_exc_admin_{uuid.uuid4().hex[:8]}"
        admin_id = await _ensure_user(admin_username, "admin", BRANCH_HO)
        await _sql("INSERT INTO iam_user_roles (user_id, role_code) VALUES (:id, 'cash_sim_operator')", id=admin_id)
        admin_headers = await _login(client, admin_username)

        box_b = await self._make_cashbox(f"EXC-ADMIN-B-{uuid.uuid4().hex[:6]}", BRANCH_B)
        journal_b = None
        try:
            journal_b = await self._plant_unbalanced_journal(box_b, admin_id)

            resp = await client.post(
                "/reconciliations",
                headers={**admin_headers, "Idempotency-Key": str(uuid.uuid4())},
                json={"scope": "cash"},
            )
            assert resp.status_code == 201, resp.text
            subjects = [e["subject"] for e in resp.json()["exceptions"]]
            assert f"journal:{journal_b}" in subjects, (
                "admin must see branch-B journal exception"
            )

            dash = await client.get("/dashboard/summary", headers=admin_headers)
            assert dash.status_code == 200, dash.text
            counters = dash.json()["reconciliation_counters"]
            assert counters["total_exceptions"] >= 1, (
                f"admin must see >= 1 total exceptions, got {counters['total_exceptions']}"
            )
            assert counters["cash_exceptions"] >= 1
            assert counters["open_exceptions"] >= 1
        finally:
            if journal_b:
                request_rows = await _rows(
                    "SELECT request_id FROM cash_journals WHERE id = :j", j=journal_b
                )
                await _sql("DELETE FROM cash_entries WHERE journal_id = :j", j=journal_b)
                await _sql("DELETE FROM cash_journals WHERE id = :j", j=journal_b)
                if request_rows:
                    await _sql(
                        "DELETE FROM cash_requests WHERE id = :r",
                        r=str(request_rows[0][0]),
                    )
            await _sql("DELETE FROM cash_boxes WHERE id = :b", b=box_b)
            await _sql("DELETE FROM iam_user_roles WHERE user_id = :id", id=admin_id)
