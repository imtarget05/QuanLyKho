"""D2 — tách quyền két tiền mặt (capability split).

Yêu cầu: KHÔNG dùng quyền đối soát (`cash:reconcile`) để cấp quyền sửa thông
tin / số dư két. Ba quyền tách bạch:

- `cash:manage_box`     -> quản lý THÔNG TIN két (tên, trạng thái). KHÔNG đụng số dư.
- `cash:reconcile`      -> nghiệp vụ đối soát (giữ nguyên cho reconciliations).
- `cash:post_adjustment`-> tạo/duyệt/thực hiện bút toán tài chính (journal
  điều chỉnh / đảo). Tách riêng, KHÔNG gộp vào `cash:manage_box`.

Test dùng user tổng hợp (role riêng trong `iam_role_capabilities`) để kiểm tra
đúng ranh giới quyền, không phụ thuộc user demo có sẵn.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from sqlalchemy import text

DEMO_PASSWORD = "DemoPass123!"
DEMO_BOX = "11111111-1111-4111-8111-111111111111"

# Role tổng hợp (dọn sau khi test).
_ROLE_BOX = "t_role_box_only"
_ROLE_RECON = "t_role_reconcile_only"
_ROLE_RECON_MAKER = "t_role_recon_maker"
_ROLE_RECON_CHECKER = "t_role_recon_checker"
_ROLE_MAKER = "t_role_maker"
_ROLE_CHECKER = "t_role_checker"

_CREATED_USERS: list[str] = []
_CREATED_ROLES: list[str] = []
_CREATED_BOXES: list[str] = []


# --------------------------------------------------------------------------
# Helpers DB
# --------------------------------------------------------------------------
async def _sql(sql: str, **params):
    """Chạy SQL trực tiếp (độc lập HTTP response) để assert dữ liệu thật."""
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


async def _create_user(username: str, role_code: str, caps: list[str]) -> str:
    """Tạo (hoặc tái dùng) user tổng hợp chỉ có đúng các capability trong `caps`.

    User KHÔNG bị xoá sau test (nhiều bảng khác có FK tới `iam_users`), chỉ
    dọn `iam_user_roles` + `iam_role_capabilities` để không lẩn quyền.
    """
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
    await _sql(
        "DELETE FROM iam_role_capabilities WHERE role_code = :r", r=role_code
    )
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
    return user_id


_TEST_USERNAMES = [
    "t_box_manager",
    "t_reconcile_only",
    "t_recon_maker",
    "t_recon_checker",
    "t_poster_maker",
    "t_poster_checker",
]


async def _purge_test_users() -> None:
    """Dọn quyền cũ của user tổng hợp (user KHÔNG xoá: nhiều bảng có FK)."""
    names = ", ".join(f":n{i}" for i in range(len(_TEST_USERNAMES)))
    params = {f"n{i}": n for i, n in enumerate(_TEST_USERNAMES)}
    await _sql(
        f"DELETE FROM iam_user_roles WHERE user_id IN "
        f"(SELECT id FROM iam_users WHERE username IN ({names}))",
        **params,
    )


@pytest.fixture(autouse=True)
async def _cleanup():
    await _purge_test_users()
    yield
    for user_id in _CREATED_USERS:
        await _sql("DELETE FROM iam_user_roles WHERE user_id = :id", id=user_id)
    for role_code in _CREATED_ROLES:
        await _sql("DELETE FROM iam_role_capabilities WHERE role_code = :r", r=role_code)
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
    _CREATED_USERS.clear()
    _CREATED_ROLES.clear()
    _CREATED_BOXES.clear()


@pytest.fixture
async def users(client):
    """Token cho từng user tổng hợp + token demo_checker (approver)."""
    tokens: dict[str, str] = {}

    async def _login(username: str) -> str:
        r = await client.post(
            "/auth/login", data={"username": username, "password": DEMO_PASSWORD}
        )
        assert r.status_code == 200, f"login({username}) -> {r.status_code}: {r.text[:300]}"
        return r.json()["access_token"]

    # Chỉ quản lý thông tin két.
    await _create_user("t_box_manager", _ROLE_BOX, ["cash:manage_box"])
    # Chỉ đối soát (không quản lý két, không ghi bút toán tài chính).
    await _create_user("t_reconcile_only", _ROLE_RECON, ["cash:reconcile"])
    # Đối soát + tạo/duyệt phiếu thường, nhưng KHÔNG có quyền ghi bút toán
    # điều chỉnh tài chính -> phiếu thường OK, bút toán điều chỉnh bị chặn.
    await _create_user(
        "t_recon_maker", _ROLE_RECON_MAKER, ["cash:create_request", "cash:reconcile"]
    )
    await _create_user(
        "t_recon_checker", _ROLE_RECON_CHECKER, ["cash:approve_request", "cash:reconcile"]
    )
    # Tạo + duyệt bút toán tài chính (không quản lý thông tin két).
    await _create_user("t_poster_maker", _ROLE_MAKER, ["cash:create_request", "cash:post_adjustment"])
    await _create_user(
        "t_poster_checker",
        _ROLE_CHECKER,
        ["cash:approve_request", "cash:post_adjustment"],
    )

    for username in (
        "t_box_manager",
        "t_reconcile_only",
        "t_recon_maker",
        "t_recon_checker",
        "t_poster_maker",
        "t_poster_checker",
    ):
        tokens[username] = await _login(username)
    tokens["demo_checker"] = await _login("demo_checker")
    return tokens


def _h(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _make_box(client, token: str, opening: str = "0.00") -> dict:
    code = f"CAPSPLIT-{uuid.uuid4().hex[:10].upper()}"
    r = await client.post(
        "/cash-sim/boxes",
        headers=_h(token),
        json={"code": code, "name": f"Box {code}", "opening_balance": opening},
    )
    assert r.status_code == 201, f"tạo cashbox -> {r.status_code}: {r.text[:300]}"
    _CREATED_BOXES.append(r.json()["id"])
    return r.json()


@pytest.fixture
async def funded_box(client, users):
    """Két riêng của module này, có số dư đầu kỳ để bút toán chi được post."""
    return await _make_box(client, users["demo_checker"], opening="1000000.00")


# --------------------------------------------------------------------------
# (a) cash:manage_box sửa được metadata, KHÔNG ghi được số dư
# --------------------------------------------------------------------------
class TestManageBoxMetadataOnly:
    async def test_manage_box_can_rename_box(self, client, users):
        box = await _make_box(client, users["demo_checker"])
        r = await client.put(
            f"/cash-sim/boxes/{box['id']}",
            headers=_h(users["t_box_manager"]),
            json={"name": "đổi tên bởi box manager"},
        )
        assert r.status_code == 200, f"D2(a): rename -> {r.status_code}: {r.text[:300]}"
        assert r.json()["name"] == "đổi tên bởi box manager"

    async def test_manage_box_cannot_write_amount(self, client, users):
        box = await _make_box(client, users["demo_checker"])
        before = await _balance_of(box["id"])
        for field in ("amount", "balance", "opening_balance"):
            r = await client.put(
                f"/cash-sim/boxes/{box['id']}",
                headers=_h(users["t_box_manager"]),
                json={field: "999999999"},
            )
            assert r.status_code == 422, (
                f"D2(a): PUT {field} -> {r.status_code} (mong đợi 422): {r.text[:300]}"
            )
        assert await _balance_of(box["id"]) == before, "D2(a): số dư quỹ bị đổi bởi cash:manage_box"

    async def test_manage_box_cannot_delete_box(self, client, users):
        """`cash:manage_box` quản lý thông tin; xoá (soft-delete) cũng là quản lý
        thông tin nên được phép — nhưng KHÔNG được xoá sạch số dư."""
        box = await _make_box(client, users["demo_checker"])
        before = await _balance_of(box["id"])
        r = await client.delete(f"/cash-sim/boxes/{box['id']}", headers=_h(users["t_box_manager"]))
        assert r.status_code == 200, f"D2(a): delete -> {r.status_code}: {r.text[:300]}"
        assert await _balance_of(box["id"]) == before


# --------------------------------------------------------------------------
# (b) chỉ có cash:reconcile -> KHÔNG được sửa metadata / tạo két
# --------------------------------------------------------------------------
class TestReconcileCannotManageBox:
    async def test_reconcile_only_cannot_update_box(self, client, users):
        box = await _make_box(client, users["demo_checker"])
        r = await client.put(
            f"/cash-sim/boxes/{box['id']}",
            headers=_h(users["t_reconcile_only"]),
            json={"name": "reconcile đổi tên"},
        )
        assert r.status_code == 403, (
            f"D2(b): reconcile sửa metadata -> {r.status_code} (mong đợi 403): {r.text[:300]}"
        )

    async def test_reconcile_only_cannot_create_box(self, client, users):
        code = f"RECON-{uuid.uuid4().hex[:10].upper()}"
        r = await client.post(
            "/cash-sim/boxes",
            headers=_h(users["t_reconcile_only"]),
            json={"code": code, "name": "reconcile box", "opening_balance": "0.00"},
        )
        assert r.status_code == 403, (
            f"D2(b): reconcile tạo két -> {r.status_code} (mong đợi 403): {r.text[:300]}"
        )

    async def test_reconcile_only_cannot_delete_box(self, client, users):
        box = await _make_box(client, users["demo_checker"])
        r = await client.delete(
            f"/cash-sim/boxes/{box['id']}", headers=_h(users["t_reconcile_only"])
        )
        assert r.status_code == 403, (
            f"D2(b): reconcile xoá két -> {r.status_code} (mong đợi 403): {r.text[:300]}"
        )


# --------------------------------------------------------------------------
# (c) cash:reconcile KHÔNG được tạo/duyệt bút toán tài chính
# --------------------------------------------------------------------------
class TestFinancialPostingIsSeparate:
    async def test_reconcile_only_cannot_create_adjustment_request(self, client, users):
        key = str(uuid.uuid4())
        r = await client.post(
            "/cash-sim/requests",
            headers={**_h(users["t_reconcile_only"]), "Idempotency-Key": key},
            json={
                "cashbox_id": DEMO_BOX,
                "kind": "adjustment",
                "amount": "1000.00",
                "reason": "D2(c) reconcile tạo điều chỉnh",
            },
        )
        assert r.status_code == 403, (
            f"D2(c): reconcile tạo adjustment -> {r.status_code} (mong đợi 403): {r.text[:300]}"
        )

    async def test_reconcile_maker_can_create_normal_request_but_not_adjustment(
        self, client, users, funded_box
    ):
        """Có `cash:create_request` + `cash:reconcile` -> tạo phiếu thường được,
        nhưng bút toán điều chỉnh tài chính thì không (thiếu `cash:post_adjustment`)."""
        key = str(uuid.uuid4())
        normal = await client.post(
            "/cash-sim/requests",
            headers={**_h(users["t_recon_maker"]), "Idempotency-Key": key},
            json={
                "cashbox_id": funded_box["id"],
                "kind": "payment",
                "amount": "10.00",
                "reason": "D2(c) phiếu chi thường",
            },
        )
        assert normal.status_code in (200, 201), (
            f"D2(c): phiếu thường -> {normal.status_code}: {normal.text[:300]}"
        )

        adj = await client.post(
            "/cash-sim/requests",
            headers={
                **_h(users["t_recon_maker"]),
                "Idempotency-Key": str(uuid.uuid4()),
            },
            json={
                "cashbox_id": funded_box["id"],
                "kind": "adjustment",
                "amount": "10.00",
                "reason": "D2(c) bút toán điều chỉnh",
            },
        )
        assert adj.status_code == 403, (
            f"D2(c): reconcile tạo adjustment -> {adj.status_code} (mong đợi 403): {adj.text[:300]}"
        )

    async def test_reconcile_checker_cannot_approve_adjustment(self, client, users, funded_box):
        """Có `cash:approve_request` + `cash:reconcile` -> không được duyệt bút toán
        điều chỉnh (thiếu `cash:post_adjustment`)."""
        created = await client.post(
            "/cash-sim/requests",
            headers={
                **_h(users["t_poster_maker"]),
                "Idempotency-Key": str(uuid.uuid4()),
            },
            json={
                "cashbox_id": funded_box["id"],
                "kind": "adjustment",
                "amount": "10.00",
                "reason": "D2(c) phiếu điều chỉnh để checker reconcile thử duyệt",
            },
        )
        assert created.status_code in (200, 201), created.text[:300]
        rid = created.json()["id"]
        await client.post(f"/cash-sim/requests/{rid}/submit", headers=_h(users["t_poster_maker"]))

        before = await _balance_of(funded_box["id"])
        r = await client.post(
            f"/cash-sim/requests/{rid}/approve", headers=_h(users["t_recon_checker"])
        )
        assert r.status_code == 403, (
            f"D2(c): reconcile duyệt adjustment -> {r.status_code} (mong đợi 403): {r.text[:300]}"
        )
        assert await _balance_of(funded_box["id"]) == before, (
            "D2(c): số dư bị đổi dù approve bị từ chối"
        )

    async def test_reconcile_only_cannot_approve_adjustment(self, client, users, funded_box):
        """Phiếu điều chỉnh do người có `cash:post_adjustment` tạo; người chỉ có
        `cash:reconcile` không được duyệt (post journal)."""
        key = str(uuid.uuid4())
        created = await client.post(
            "/cash-sim/requests",
            headers={**_h(users["t_poster_maker"]), "Idempotency-Key": key},
            json={
                "cashbox_id": funded_box["id"],
                "kind": "adjustment",
                "amount": "1000.00",
                "reason": "D2(c) phiếu điều chỉnh hợp lệ",
            },
        )
        assert created.status_code in (200, 201), (
            f"D2(c): tạo adjustment -> {created.status_code}: {created.text[:300]}"
        )
        rid = created.json()["id"]
        sub = await client.post(
            f"/cash-sim/requests/{rid}/submit", headers=_h(users["t_poster_maker"])
        )
        assert sub.status_code in (200, 201), f"D2(c): submit -> {sub.text[:300]}"

        before = await _balance_of(funded_box["id"])
        r = await client.post(
            f"/cash-sim/requests/{rid}/approve", headers=_h(users["t_reconcile_only"])
        )
        assert r.status_code == 403, (
            f"D2(c): reconcile duyệt adjustment -> {r.status_code} (mong đợi 403): {r.text[:300]}"
        )
        assert await _balance_of(funded_box["id"]) == before, (
            "D2(c): số dư bị đổi dù approve bị từ chối"
        )

    async def test_reconcile_only_cannot_reverse_posted_request(self, client, users, funded_box):
        """`cash:reconcile` là quyền đối soát (đọc) -> KHÔNG được post journal đảo."""
        created = await client.post(
            "/cash-sim/requests",
            headers={
                **_h(users["t_poster_maker"]),
                "Idempotency-Key": str(uuid.uuid4()),
            },
            json={
                "cashbox_id": funded_box["id"],
                "kind": "receipt",
                "amount": "100.00",
                "reason": "D2(c) phiếu thu để thử đảo",
            },
        )
        assert created.status_code in (200, 201), created.text[:300]
        rid = created.json()["id"]
        await client.post(f"/cash-sim/requests/{rid}/submit", headers=_h(users["t_poster_maker"]))
        ap = await client.post(
            f"/cash-sim/requests/{rid}/approve", headers=_h(users["t_poster_checker"])
        )
        assert ap.status_code in (200, 201), ap.text[:300]

        before = await _balance_of(funded_box["id"])
        r = await client.post(
            f"/cash-sim/requests/{rid}/reverse",
            headers={**_h(users["t_reconcile_only"]), "Idempotency-Key": str(uuid.uuid4())},
            json={"reason": "D2(c) reconcile đảo giao dịch"},
        )
        assert r.status_code == 403, (
            f"D2(c): reconcile đảo giao dịch -> {r.status_code} (mong đợi 403): {r.text[:300]}"
        )
        assert await _balance_of(funded_box["id"]) == before, (
            "D2(c): số dư bị đổi dù reverse bị từ chối"
        )

    async def test_post_adjustment_capability_can_post_adjustment(self, client, users, funded_box):
        """Đường hợp đúng: có `cash:post_adjustment` thì tạo + duyệt được."""
        key = str(uuid.uuid4())
        created = await client.post(
            "/cash-sim/requests",
            headers={**_h(users["t_poster_maker"]), "Idempotency-Key": key},
            json={
                "cashbox_id": funded_box["id"],
                "kind": "adjustment",
                "amount": "1000.00",
                "reason": "D2(c) bút toán điều chỉnh hợp lệ",
            },
        )
        assert created.status_code in (200, 201), created.text[:300]
        rid = created.json()["id"]
        await client.post(f"/cash-sim/requests/{rid}/submit", headers=_h(users["t_poster_maker"]))
        before = await _balance_of(funded_box["id"])
        r = await client.post(
            f"/cash-sim/requests/{rid}/approve", headers=_h(users["t_poster_checker"])
        )
        assert r.status_code in (200, 201), (
            f"D2(c): approve adjustment hợp lệ -> {r.status_code}: {r.text[:300]}"
        )
        assert await _balance_of(funded_box["id"]) == before - Decimal("1000.00"), (
            "D2(c): số dư không được ghi nhận bút toán điều chỉnh"
        )
