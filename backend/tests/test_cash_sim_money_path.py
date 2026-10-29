"""FIX WAVE 1 — money-path của module quỹ (cash-sim).

Bao phủ 4 lỗi G2:
- S4 (Critical): POST/PUT/DELETE /cash-sim/boxes phải đòi capability quản lý quỹ;
  client không được ghi thẳng `CashBalance.amount` (số dư chỉ đổi qua journal).
- R1 (Major, concurrency): 2 approve đồng thời trên cùng cashbox không được
  double-spend (tổng journal chi ≤ số dư trước khi approve).
- R2 (Major, idempotency): 2 POST /cash-sim/requests cùng `Idempotency-Key` chỉ
  tạo 1 phiếu, kể cả sau khi process restart (store bền vững trong DB).
"""
from __future__ import annotations

import asyncio
import uuid
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal

import pytest
from sqlalchemy import text

DEMO_PASSWORD = "DemoPass123!"
DEMO_BOX = "11111111-1111-4111-8111-111111111111"


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
class Api:
    """Giữ token theo vai trò (demo users đã seed sẵn)."""

    def __init__(self, client):
        self.c = client
        self.tokens: dict[str, str] = {}

    def login(self, username: str, password: str = DEMO_PASSWORD) -> str:
        r = self.c.post("/auth/login", data={"username": username, "password": password})
        assert r.status_code == 200, f"login({username}) -> {r.status_code}: {r.text[:300]}"
        token = r.json()["access_token"]
        self.tokens[username] = token
        return token

    def h(self, username: str) -> dict:
        if username not in self.tokens:
            self.login(username)
        return {"Authorization": f"Bearer {self.tokens[username]}"}


@pytest.fixture(scope="module")
def api(client) -> Api:
    return Api(client)


def _rows(sql: str, **params):
    """Query DB trực tiếp (độc lập HTTP response) để assert tiền thật."""
    from app.database import AsyncSessionLocal

    async def _run():
        async with AsyncSessionLocal() as session:
            result = await session.execute(text(sql), params)
            await session.commit()
            if not result.returns_rows:
                return []
            return result.fetchall()

    return asyncio.run(_run())


def _balance_of(box_id: str) -> Decimal:
    rows = _rows("SELECT amount FROM cash_balances WHERE cashbox_id = :b", b=box_id)
    assert rows, "không tìm thấy cash_balances"
    return Decimal(str(rows[0][0]))


def _posted_payment_total(box_id: str) -> Decimal:
    rows = _rows(
        "SELECT COALESCE(SUM(amount), 0) FROM cash_requests "
        "WHERE cashbox_id = :b AND kind = 'payment' AND status = 'posted'",
        b=box_id,
    )
    return Decimal(str(rows[0][0]))


def _unique_code(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10].upper()}"


# Mọi dữ liệu test tạo ra được ghi lại để dọn sau (DB test dùng chung).
_CREATED_BOXES: list[str] = []
_CREATED_KEYS: list[str] = []


@pytest.fixture(scope="module", autouse=True)
def _cleanup_cash_test_data():
    """Xoá dữ liệu module này tạo để không đẩy DB test dùng chung."""

    def _wipe():
        for box_id in _CREATED_BOXES:
            _rows(
                "DELETE FROM cash_entries WHERE journal_id IN "
                "(SELECT id FROM cash_journals WHERE request_id IN "
                "(SELECT id FROM cash_requests WHERE cashbox_id = :b))",
                b=box_id,
            )
            _rows(
                "DELETE FROM cash_journals WHERE request_id IN "
                "(SELECT id FROM cash_requests WHERE cashbox_id = :b)",
                b=box_id,
            )
            _rows("DELETE FROM cash_requests WHERE cashbox_id = :b", b=box_id)
            _rows("DELETE FROM cash_balances WHERE cashbox_id = :b", b=box_id)
            _rows("DELETE FROM cash_boxes WHERE id = :b", b=box_id)
        for key in _CREATED_KEYS:
            _rows("DELETE FROM cash_requests WHERE idempotency_key = :k", k=key)
        _CREATED_BOXES.clear()
        _CREATED_KEYS.clear()

    yield
    _wipe()


def _make_box(api: Api, owner: str, opening: str = "0.00") -> dict:
    """Tạo cashbox bằng user có capability quản lý quỹ."""
    code = _unique_code("TESTBOX")
    r = api.c.post(
        "/cash-sim/boxes",
        headers=api.h(owner),
        json={"code": code, "name": f"Test box {code}", "opening_balance": opening},
    )
    assert r.status_code == 201, f"tạo cashbox -> {r.status_code}: {r.text[:300]}"
    _CREATED_BOXES.append(r.json()["id"])
    return r.json()


def _cash_request(api: Api, maker: str, box_id: str, kind: str, amount: str, reason: str) -> str:
    r = api.c.post(
        "/cash-sim/requests",
        headers={**api.h(maker), "Idempotency-Key": str(uuid.uuid4())},
        json={"cashbox_id": box_id, "kind": kind, "amount": amount, "reason": reason},
    )
    assert r.status_code in (200, 201), f"tạo phiếu {kind} -> {r.status_code}: {r.text[:300]}"
    rid = r.json()["id"]
    sub = api.c.post(f"/cash-sim/requests/{rid}/submit", headers=api.h(maker))
    assert sub.status_code in (200, 201), f"submit -> {sub.status_code}: {sub.text[:300]}"
    return rid


def _approve(api: Api, checker: str, rid: str):
    return api.c.post(f"/cash-sim/requests/{rid}/approve", headers=api.h(checker))


# --------------------------------------------------------------------------
# S4 — capability gate cho CRUD cashbox
# --------------------------------------------------------------------------
class TestS4CashboxCapability:
    def test_staff_cannot_create_cashbox(self, api):
        api.login("demo_maker")  # role staff: chỉ cash:create_request + cash:view_balances
        r = api.c.post(
            "/cash-sim/boxes",
            headers=api.h("demo_maker"),
            json={"code": _unique_code("STAFFBOX"), "name": "staff box"},
        )
        assert r.status_code == 403, (
            f"S4: staff tạo cashbox trả {r.status_code} (mong đợi 403): {r.text[:300]}"
        )

    def test_staff_cannot_update_cashbox(self, api):
        r = api.c.put(
            f"/cash-sim/boxes/{DEMO_BOX}",
            headers=api.h("demo_maker"),
            json={"name": "staff đổi tên"},
        )
        assert r.status_code == 403, (
            f"S4: staff sửa cashbox trả {r.status_code} (mong đợi 403): {r.text[:300]}"
        )

    def test_staff_cannot_delete_cashbox(self, api):
        r = api.c.delete(f"/cash-sim/boxes/{DEMO_BOX}", headers=api.h("demo_maker"))
        assert r.status_code == 403, (
            f"S4: staff xoá cashbox trả {r.status_code} (mong đợi 403): {r.text[:300]}"
        )

    def test_auditor_cannot_create_cashbox(self, api):
        api.login("demo_auditor")
        r = api.c.post(
            "/cash-sim/boxes",
            headers=api.h("demo_auditor"),
            json={"code": _unique_code("AUDBOX"), "name": "auditor box"},
        )
        assert r.status_code == 403, (
            f"S4: auditor tạo cashbox trả {r.status_code} (mong đợi 403): {r.text[:300]}"
        )


# --------------------------------------------------------------------------
# S4 — client không được ghi thẳng CashBalance.amount
# --------------------------------------------------------------------------
class TestS4NoDirectBalanceWrite:
    def test_update_rejects_opening_balance_field(self, api):
        api.login("demo_checker")
        before = _balance_of(DEMO_BOX)
        r = api.c.put(
            f"/cash-sim/boxes/{DEMO_BOX}",
            headers=api.h("demo_checker"),
            json={"opening_balance": "999999999"},
        )
        assert r.status_code == 422, (
            f"S4: PUT opening_balance trả {r.status_code} (mong đợi 422): {r.text[:300]}"
        )
        after = _balance_of(DEMO_BOX)
        assert after == before, f"S4: số dư quỹ bị đổi từ {before} -> {after}"

    def test_update_rejects_amount_and_balance_fields(self, api):
        api.login("demo_checker")
        before = _balance_of(DEMO_BOX)
        for field in ("amount", "balance"):
            r = api.c.put(
                f"/cash-sim/boxes/{DEMO_BOX}",
                headers=api.h("demo_checker"),
                json={field: "999999999"},
            )
            assert r.status_code == 422, (
                f"S4: PUT {field} trả {r.status_code} (mong đợi 422): {r.text[:300]}"
            )
        assert _balance_of(DEMO_BOX) == before, "S4: số dư quỹ bị đổi sau khi chặn field"

    def test_update_can_still_rename_and_deactivate(self, api):
        api.login("demo_checker")
        code = _unique_code("RENBOX")
        box = _make_box(api, "demo_checker")
        r = api.c.put(
            f"/cash-sim/boxes/{box['id']}",
            headers=api.h("demo_checker"),
            json={"name": f"renamed {code}", "active": True},
        )
        assert r.status_code == 200, f"S4: rename trả {r.status_code}: {r.text[:300]}"
        assert r.json()["name"] == f"renamed {code}"

    def test_created_box_balance_is_backed_by_journal(self, api):
        """Số dư mới phải có journal hỗ trợ (không ghi tay CashBalance.amount)."""
        api.login("demo_checker")
        box = _make_box(api, "demo_checker", opening="1000000.00")
        assert Decimal(str(box["opening_balance"])) == Decimal("1000000.00")
        rows = _rows(
            "SELECT COUNT(*) FROM cash_journals j "
            "JOIN cash_requests r ON r.id = j.request_id "
            "WHERE r.cashbox_id = :b",
            b=box["id"],
        )
        assert int(rows[0][0]) >= 1, "S4: số dư mở két không có journal hỗ trợ"


# --------------------------------------------------------------------------
# R1 — approve đồng thời không được double-spend
# --------------------------------------------------------------------------
class TestR1ConcurrentApprove:
    def test_two_concurrent_approvals_do_not_double_spend(self, api, monkeypatch):
        import asyncio as _asyncio

        from app.features.cash import routes as cash_mod

        api.login("demo_checker")
        api.login("demo_approver2")
        api.login("demo_maker")

        box = _make_box(api, "demo_checker")
        box_id = box["id"]

        # Nạp quỹ qua flow chuẩn (receipt request -> approve), không ghi tay balance.
        fund_id = _cash_request(api, "demo_maker", box_id, "receipt", "100.00", "nap quy")
        funded = _approve(api, "demo_checker", fund_id)
        assert funded.status_code in (200, 201), f"nạp quỹ -> {funded.text[:300]}"
        balance_before = _balance_of(box_id)
        assert balance_before == Decimal("100.00"), f"số dư nạp = {balance_before}"

        # Mở rộng cửa sổ race: đọc số dư rồi ngủ, để 2 request cùng đọc 1 giá trị.
        original = cash_mod._balance_for_box

        async def _slow(db, cashbox_id, **kwargs):
            bal = await original(db, cashbox_id, **kwargs)
            await _asyncio.sleep(0.4)
            return bal

        monkeypatch.setattr(cash_mod, "_balance_for_box", _slow)

        rid_a = _cash_request(api, "demo_maker", box_id, "payment", "80.00", "chi A")
        rid_b = _cash_request(api, "demo_maker", box_id, "payment", "80.00", "chi B")

        with ThreadPoolExecutor(max_workers=2) as pool:
            fa = pool.submit(_approve, api, "demo_checker", rid_a)
            fb = pool.submit(_approve, api, "demo_approver2", rid_b)
            resp_a = fa.result()
            resp_b = fb.result()

        statuses = sorted([resp_a.status_code, resp_b.status_code])
        assert statuses.count(200) + statuses.count(201) == 1, (
            f"R1: cả 2 approve đều thành công {statuses} — double-spend: "
            f"{resp_a.text[:200]} | {resp_b.text[:200]}"
        )
        assert 409 in statuses, (
            f"R1: request thua kỳ vọng 409 INSUFFICIENT_SIM_CASH, thấy {statuses}: "
            f"{resp_a.text[:200]} | {resp_b.text[:200]}"
        )

        spent = _posted_payment_total(box_id)
        assert spent <= balance_before, (
            f"R1: double-spend — tổng journal chi {spent} > số dư trước {balance_before}"
        )
        assert _balance_of(box_id) == balance_before - spent, (
            "R1: số dư quỹ không khớp tổng journal đã post"
        )


# --------------------------------------------------------------------------
# R2 — idempotency bền vững
# --------------------------------------------------------------------------
class TestR2Idempotency:
    def test_same_key_creates_single_request(self, api):
        api.login("demo_maker")
        key = str(uuid.uuid4())
        _CREATED_KEYS.append(key)
        payload = {
            "cashbox_id": DEMO_BOX,
            "kind": "payment",
            "amount": "12345.00",
            "reason": "R2 idempotent",
        }
        r1 = api.c.post(
            "/cash-sim/requests",
            headers={**api.h("demo_maker"), "Idempotency-Key": key},
            json=payload,
        )
        r2 = api.c.post(
            "/cash-sim/requests",
            headers={**api.h("demo_maker"), "Idempotency-Key": key},
            json=payload,
        )
        assert r1.status_code in (200, 201), f"R2: POST 1 -> {r1.status_code}: {r1.text[:300]}"
        assert r2.status_code in (200, 201), f"R2: POST 2 -> {r2.status_code}: {r2.text[:300]}"
        assert r1.json()["id"] == r2.json()["id"], "R2: retry tạo phiếu khác"
        rows = _rows(
            "SELECT COUNT(*) FROM cash_requests WHERE idempotency_key = :k", k=key
        )
        assert int(rows[0][0]) == 1, f"R2: DB có {rows[0][0]} phiếu cho cùng key"

    def test_same_key_survives_process_restart(self, api):
        """Store in-memory bị xoá (giả lập restart) — key phải còn trong DB."""
        from app.services import idempotency as idem_mod

        api.login("demo_maker")
        key = str(uuid.uuid4())
        _CREATED_KEYS.append(key)
        payload = {
            "cashbox_id": DEMO_BOX,
            "kind": "payment",
            "amount": "22222.00",
            "reason": "R2 restart",
        }
        r1 = api.c.post(
            "/cash-sim/requests",
            headers={**api.h("demo_maker"), "Idempotency-Key": key},
            json=payload,
        )
        assert r1.status_code in (200, 201), f"R2: POST -> {r1.status_code}: {r1.text[:300]}"

        idem_mod._store.clear()  # giả lập process restart: mất store in-memory

        r2 = api.c.post(
            "/cash-sim/requests",
            headers={**api.h("demo_maker"), "Idempotency-Key": key},
            json=payload,
        )
        assert r2.status_code in (200, 201), (
            f"R2: retry sau restart trả {r2.status_code} (mong đợi replay): {r2.text[:300]}"
        )
        assert r2.json()["id"] == r1.json()["id"], "R2: sau restart retry tạo phiếu khác"
        rows = _rows(
            "SELECT COUNT(*) FROM cash_requests WHERE idempotency_key = :k", k=key
        )
        assert int(rows[0][0]) == 1, f"R2: DB có {rows[0][0]} phiếu sau restart"

    def test_same_key_different_payload_conflicts(self, api):
        api.login("demo_maker")
        key = str(uuid.uuid4())
        _CREATED_KEYS.append(key)
        r1 = api.c.post(
            "/cash-sim/requests",
            headers={**api.h("demo_maker"), "Idempotency-Key": key},
            json={
                "cashbox_id": DEMO_BOX,
                "kind": "payment",
                "amount": "33333.00",
                "reason": "R2 conflict A",
            },
        )
        assert r1.status_code in (200, 201), f"R2: POST -> {r1.status_code}: {r1.text[:300]}"
        r2 = api.c.post(
            "/cash-sim/requests",
            headers={**api.h("demo_maker"), "Idempotency-Key": key},
            json={
                "cashbox_id": DEMO_BOX,
                "kind": "payment",
                "amount": "44444.00",
                "reason": "R2 conflict B",
            },
        )
        assert r2.status_code == 409, (
            f"R2: cùng key khác payload trả {r2.status_code} (mong đợi 409): {r2.text[:300]}"
        )
        body = r2.json()
        assert body.get("error", {}).get("code") == "IDEMPOTENCY_KEY_REUSED", (
            f"R2: error code = {body.get('error', {}).get('code')}"
        )
