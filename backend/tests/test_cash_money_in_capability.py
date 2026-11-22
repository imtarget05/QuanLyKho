"""STEP 5 — chiều TĂNG quỹ cũng phải có `cash:post_adjustment` (D2).

Lỗ hổng (residual): mọi kind khác `receipt` bị coi là dòng tiền RA, còn
`receipt` (chiều TĂNG) chỉ cần `cash:create_request` -> user KHÔNG có
`cash:post_adjustment` vẫn làm số dư quỹ TĂNG. Bút toán tài chính (cả 2
chiều) phải do người có `cash:post_adjustment` thực hiện.

Bảo đảm sau khi sửa:
- Tạo phiếu điều chỉnh tăng quỹ (`adjustment_in`) mà không có
  `cash:post_adjustment` -> **403** (có đủ quyền -> 201).
- Duyệt phiếu làm TĂNG số dư (`receipt`, `adjustment_in`) mà người duyệt không
  có `cash:post_adjustment` -> **403** và số dư KHÔNG đổi.
- Đảo phiếu chi (làm TĂNG số dư) mà không có `cash:post_adjustment` -> **403**
  và số dư KHÔNG đổi.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from sqlalchemy import text

DEMO_PASSWORD = "DemoPass123!"

# Role tổng hợp (dọn sau test) — không phụ thuộc user demo có sẵn.
_ROLE_MAKER = "t_s5_maker"
_ROLE_CHECKER = "t_s5_checker"
_ROLE_CHECKER_ADJ = "t_s5_checker_adj"
_ROLE_POSTER = "t_s5_poster"

_CREATED_USERS: list[str] = []
_CREATED_ROLES: list[str] = []
_CREATED_BOXES: list[str] = []

_TEST_USERNAMES = [
    "t_s5_maker",
    "t_s5_checker",
    "t_s5_checker_adj",
    "t_s5_poster",
]


async def _sql(sql: str, **params):
    """Chạy SQL trực tiếp để assert dữ liệu thật (không qua HTTP response)."""
    from app.database import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        result = await session.execute(text(sql), params)
        await session.commit()
        if not result.returns_rows:
            return []
        return result.fetchall()


async def _balance_of(box_id: str) -> Decimal:
    rows = await _sql("SELECT amount FROM cash_balances WHERE cashbox_id = :b", b=box_id)
    assert rows, "không tìm thấy cash_balances"
    return Decimal(str(rows[0][0]))


async def _create_user(username: str, role_code: str, caps: list[str]) -> None:
    """Tạo user tổng hợp chỉ có đúng các capability trong `caps`."""
    from app.api.routes.auth_utils import get_password_hash

    rows = await _sql("SELECT id FROM iam_users WHERE username = :u", u=username)
    if rows:
        user_id = str(rows[0][0])
        await _sql(
            "UPDATE iam_users SET password_hash = :p WHERE id = :id",
            id=user_id,
            p=get_password_hash(DEMO_PASSWORD),
        )
        await _sql("DELETE FROM iam_user_roles WHERE user_id = :id", id=user_id)
    else:
        user_id = str(uuid.uuid4())
        await _sql(
            "INSERT INTO iam_users (id, username, password_hash, status, display_name_demo) "
            "VALUES (:id, :u, :p, 'active', :d)",
            id=user_id,
            u=username,
            p=get_password_hash(DEMO_PASSWORD),
            d=f"Test {username}",
        )
    await _sql(
        "INSERT INTO iam_user_roles (user_id, role_code) VALUES (:id, :r)",
        id=user_id,
        r=role_code,
    )
    await _sql("DELETE FROM iam_role_capabilities WHERE role_code = :r", r=role_code)
    for cap in caps:
        await _sql(
            "INSERT INTO iam_role_capabilities (role_code, capability_code) "
            "VALUES (:r, :c) ON CONFLICT DO NOTHING",
            r=role_code,
            c=cap,
        )
    _CREATED_USERS.append(user_id)
    if role_code not in _CREATED_ROLES:
        _CREATED_ROLES.append(role_code)


@pytest.fixture(autouse=True)
async def _cleanup():
    yield
    for box_id in _CREATED_BOXES:
        await _sql(
            "DELETE FROM cash_entries WHERE journal_id IN "
            "(SELECT id FROM cash_journals WHERE request_id IN "
            "(SELECT id FROM cash_requests WHERE cashbox_id = :b))",
            b=box_id,
        )
        await _sql(
            "DELETE FROM cash_journals WHERE request_id IN "
            "(SELECT id FROM cash_requests WHERE cashbox_id = :b)",
            b=box_id,
        )
        await _sql("DELETE FROM cash_requests WHERE cashbox_id = :b", b=box_id)
        await _sql("DELETE FROM cash_balances WHERE cashbox_id = :b", b=box_id)
        await _sql("DELETE FROM cash_boxes WHERE id = :b", b=box_id)
    for user_id in _CREATED_USERS:
        await _sql("DELETE FROM iam_user_roles WHERE user_id = :id", id=user_id)
    for role_code in _CREATED_ROLES:
        await _sql("DELETE FROM iam_role_capabilities WHERE role_code = :r", r=role_code)
    _CREATED_USERS.clear()
    _CREATED_ROLES.clear()
    _CREATED_BOXES.clear()


@pytest.fixture
async def tokens(client):
    """Token cho user tổng hợp (quyền tối thiểu) + demo_checker (mở két)."""

    async def _login(username: str) -> str:
        r = await client.post(
            "/auth/login", data={"username": username, "password": DEMO_PASSWORD}
        )
        assert r.status_code == 200, f"login({username}) -> {r.status_code}: {r.text[:300]}"
        return r.json()["access_token"]

    # Maker: CHỈ có `cash:create_request` (KHÔNG có `cash:post_adjustment`).
    await _create_user("t_s5_maker", _ROLE_MAKER, ["cash:create_request"])
    # Checker: CHỈ có `cash:approve_request` (KHÔNG có `cash:post_adjustment`).
    await _create_user("t_s5_checker", _ROLE_CHECKER, ["cash:approve_request"])
    # Checker đủ quyền ghi bút toán tài chính.
    await _create_user(
        "t_s5_checker_adj",
        _ROLE_CHECKER_ADJ,
        ["cash:approve_request", "cash:post_adjustment"],
    )
    # Maker đủ quyền ghi bút toán tài chính.
    await _create_user(
        "t_s5_poster",
        _ROLE_POSTER,
        ["cash:create_request", "cash:post_adjustment"],
    )

    out = {}
    for u in _TEST_USERNAMES:
        out[u] = await _login(u)
    out["demo_checker"] = await _login("demo_checker")
    return out


def _h(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def box(client, tokens):
    """Két riêng của module, có số dư đầu kỳ (mở két cần quyền bút toán)."""
    code = f"S5MONEY-{uuid.uuid4().hex[:10].upper()}"
    r = await client.post(
        "/cash-sim/boxes",
        headers=_h(tokens["demo_checker"]),
        json={"code": code, "name": f"Box {code}", "opening_balance": "1000000.00"},
    )
    assert r.status_code == 201, f"mở két -> {r.status_code}: {r.text[:300]}"
    _CREATED_BOXES.append(r.json()["id"])
    return r.json()


async def _create_request(client, token: str, box_id: str, kind: str, amount: str, reason: str):
    return await client.post(
        "/cash-sim/requests",
        headers={**_h(token), "Idempotency-Key": str(uuid.uuid4())},
        json={
            "cashbox_id": box_id,
            "kind": kind,
            "amount": amount,
            "reason": reason,
        },
    )


async def _submit(client, token: str, rid: str):
    return await client.post(f"/cash-sim/requests/{rid}/submit", headers=_h(token))


# --------------------------------------------------------------------------
# (a) Tạo phiếu điều chỉnh TĂNG quỹ -> cần `cash:post_adjustment`
# --------------------------------------------------------------------------
class TestMoneyInAdjustmentRequiresPostAdjustment:
    async def test_create_money_in_adjustment_without_capability_is_403(self, client, tokens, box):
        """User có `cash:create_request` nhưng KHÔNG có `cash:post_adjustment`
        -> tạo phiếu tăng quỹ (`adjustment_in`) phải bị 403."""
        r = await _create_request(
            client, tokens["t_s5_maker"], box["id"], "adjustment_in", "1000.00", "S5 tăng quỹ"
        )
        assert r.status_code == 403, (
            f"S5(a): tạo phiếu tăng quỹ không có quyền -> {r.status_code} "
            f"(mong đợi 403): {r.text[:300]}"
        )

    async def test_create_money_in_adjustment_with_capability_is_allowed(
        self, client, tokens, box
    ):
        """Đủ quyền -> tạo được phiếu tăng quỹ."""
        r = await _create_request(
            client, tokens["t_s5_poster"], box["id"], "adjustment_in", "1000.00", "S5 tăng quỹ hợp lệ"
        )
        assert r.status_code in (200, 201), (
            f"S5(a): tạo phiếu tăng quỹ hợp lệ -> {r.status_code}: {r.text[:300]}"
        )


# --------------------------------------------------------------------------
# (b) Duyệt phiếu làm TĂNG số dư (`receipt`) -> cần `cash:post_adjustment`
# --------------------------------------------------------------------------
class TestReceiptApprovalRequiresPostAdjustment:
    async def test_approve_receipt_without_capability_is_403_and_balance_unchanged(
        self, client, tokens, box
    ):
        created = await _create_request(
            client, tokens["t_s5_maker"], box["id"], "receipt", "500.00", "S5 thu quỹ"
        )
        assert created.status_code in (200, 201), created.text[:300]
        rid = created.json()["id"]
        sub = await _submit(client, tokens["t_s5_maker"], rid)
        assert sub.status_code in (200, 201)

        before = await _balance_of(box["id"])
        r = await client.post(f"/cash-sim/requests/{rid}/approve", headers=_h(tokens["t_s5_checker"]))
        assert r.status_code == 403, (
            f"S5(b): duyệt phiếu thu bằng checker không có cash:post_adjustment -> "
            f"{r.status_code} (mong đợi 403): {r.text[:300]}"
        )
        assert await _balance_of(box["id"]) == before, (
            "S5(b): số dư quỹ TĂNG dù approve bị từ chối (lỗ hổng chiều tăng)"
        )

    async def test_approve_receipt_with_capability_increases_balance(
        self, client, tokens, box
    ):
        created = await _create_request(
            client, tokens["t_s5_maker"], box["id"], "receipt", "500.00", "S5 thu quỹ hợp lệ"
        )
        assert created.status_code in (200, 201), created.text[:300]
        rid = created.json()["id"]
        sub = await _submit(client, tokens["t_s5_maker"], rid)
        assert sub.status_code in (200, 201)

        before = await _balance_of(box["id"])
        r = await client.post(
            f"/cash-sim/requests/{rid}/approve", headers=_h(tokens["t_s5_checker_adj"])
        )
        assert r.status_code in (200, 201), (
            f"S5(b): duyệt phiếu thu hợp lệ -> {r.status_code}: {r.text[:300]}"
        )
        assert await _balance_of(box["id"]) == before + Decimal("500.00"), (
            "S5(b): phiếu thu hợp lệ phải làm số dư quỹ tăng đúng số tiền"
        )


# --------------------------------------------------------------------------
# (c) Đảo phiếu chi (chiều TĂNG) -> cần `cash:post_adjustment`
# --------------------------------------------------------------------------
class TestReversalMoneyInRequiresPostAdjustment:
    async def test_reverse_payment_without_capability_is_403_and_balance_unchanged(
        self, client, tokens, box
    ):
        created = await _create_request(
            client, tokens["t_s5_maker"], box["id"], "payment", "100.00", "S5 chi quỹ"
        )
        assert created.status_code in (200, 201), created.text[:300]
        rid = created.json()["id"]
        sub = await _submit(client, tokens["t_s5_maker"], rid)
        assert sub.status_code in (200, 201)
        ap = await client.post(f"/cash-sim/requests/{rid}/approve", headers=_h(tokens["t_s5_checker"]))
        assert ap.status_code in (200, 201), f"post phiếu chi -> {ap.text[:300]}"

        before = await _balance_of(box["id"])
        rev = await client.post(
            f"/cash-sim/requests/{rid}/reverse",
            headers={**_h(tokens["t_s5_maker"]), "Idempotency-Key": str(uuid.uuid4())},
            json={"reason": "S5 đảo phiếu chi"},
        )
        assert rev.status_code == 403, (
            f"S5(c): đảo phiếu chi (làm TĂNG quỹ) bằng user không có "
            f"cash:post_adjustment -> {rev.status_code} (mong đợi 403): {rev.text[:300]}"
        )
        assert await _balance_of(box["id"]) == before, (
            "S5(c): số dư quỹ TĂNG dù reverse bị từ chối"
        )
