"""Wave 2 — Worker A: SECURITY & IDENTITY.

Bao phu cac finding G2 da verify bang doc code:

- A (S5)  IDOR: xoá phiếu nháp của người khác (inventory + cash-sim).
- B (S6)  Tenant/branch isolation: balances/boxes, dashboard summary, stocktakes.
- C (S7)  `/events/stream` phai yeu cau token + capability.
- D (S9)  Google login khong tu cap role cho user da ton tai.
- E (R3/R4) Session revocation: `auth_version` trong refresh token + tang khi doi/reset mat khau.
- F (S13) `must_change_password` phai duoc enforce.
- G (S11) Rate limit login theo username + IP, tra `Retry-After`.
- H (R9)  Soft delete item KHONG duoc lam mat ton kho.
- I (S8)  Client khong duoc tu ghi `opening_qty`/`received_qty` cua phieu kiem ke.

Moi test tao du lieu rieng (user / location / cashbox co tien to), nen khong
dung chung du lieu voi cac test khac.
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import date, timedelta

from sqlalchemy import text

PASSWORD = "Wave2Secure123!"

BRANCH_HO = "11111111-1111-4111-8111-111111111111"
BRANCH_A = "22222222-2222-4222-8222-222222222222"
BRANCH_B = "33333333-3333-4333-8333-333333333333"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
async def _sql(sql: str, **params):
    """Chay SQL truc tiep (doc/ghi DB) de setup du lieu can thiet cho test."""
    from app.database import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        result = await session.execute(text(sql), params)
        await session.commit()
        if not result.returns_rows:
            return []
        return result.fetchall()


async def _ensure_user(username: str, role_code: str, branch_id: str | None = None) -> str:
    """Tao (hoac tai dung) user co role + branch xac dinh. Tra user_id."""
    from app.api.routes.auth_utils import get_password_hash

    rows = await _sql("SELECT id FROM iam_users WHERE username = :u", u=username)
    if rows:
        user_id = str(rows[0][0])
        await _sql(
            "UPDATE iam_users SET password_hash = :p, status = 'active', branch_id = :b "
            "WHERE id = :id",
            p=get_password_hash(PASSWORD),
            b=branch_id,
            id=user_id,
        )
    else:
        user_id = str(uuid.uuid4())
        await _sql(
            "INSERT INTO iam_users (id, username, password_hash, status, display_name_demo, "
            "email, branch_id) VALUES (:id, :u, :p, 'active', :d, :e, :b)",
            id=user_id,
            u=username,
            p=get_password_hash(PASSWORD),
            d=f"Wave2 {username}",
            e=f"{username}@bankops.internal",
            b=branch_id,
        )
    await _sql("DELETE FROM iam_user_roles WHERE user_id = :id", id=user_id)
    await _sql(
        "INSERT INTO iam_user_roles (user_id, role_code) VALUES (:id, :r)",
        id=user_id,
        r=role_code,
    )
    return user_id


async def _tokens(client, username: str, password: str = PASSWORD) -> dict:
    r = await client.post(
        "/auth/login",
        json={"username": username, "password": password},
    )
    assert r.status_code == 200, r.text
    return r.json()


async def _login(client, username: str, password: str = PASSWORD) -> dict:
    body = await _tokens(client, username, password)
    return {"Authorization": f"Bearer {body['access_token']}"}


def _idem(headers: dict) -> dict:
    return {**headers, "Idempotency-Key": str(uuid.uuid4())}


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


async def _make_cashbox(code: str, branch_id: str, amount: str = "1000") -> str:
    box_id = str(uuid.uuid4())
    await _sql(
        "INSERT INTO cash_boxes (id, code, name, currency, active, branch_id) "
        "VALUES (:id, :c, :n, 'VND', true, :b)",
        id=box_id,
        c=code,
        n=code,
        b=branch_id,
    )
    await _sql(
        "INSERT INTO cash_balances (cashbox_id, amount, version) VALUES (:id, :a, 1)",
        id=box_id,
        a=amount,
    )
    return box_id


async def _cleanup_location(loc_id: str) -> None:
    try:
        await _sql("DELETE FROM inv_stocktake_lines WHERE stocktake_id IN "
                   "(SELECT id FROM inv_stocktakes WHERE location_id = :l)", l=loc_id)
        await _sql("DELETE FROM inv_stocktakes WHERE location_id = :l", l=loc_id)
        await _sql("DELETE FROM inv_balances WHERE location_id = :l", l=loc_id)
        await _sql("DELETE FROM inv_stock_levels WHERE location_id = :l", l=loc_id)
        await _sql("DELETE FROM inv_locations WHERE id = :l", l=loc_id)
    except Exception:
        pass


async def _cleanup_cashbox(box_id: str) -> None:
    try:
        await _sql("DELETE FROM cash_balances WHERE cashbox_id = :b", b=box_id)
        await _sql("DELETE FROM cash_boxes WHERE id = :b", b=box_id)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# A (S5) — IDOR: chi chu so huu duoc xoa phieu draft
# ---------------------------------------------------------------------------
async def test_delete_inventory_draft_request_only_by_owner(client):
    maker = f"w2_inv_a_{uuid.uuid4().hex[:8]}"
    other = f"w2_inv_b_{uuid.uuid4().hex[:8]}"
    await _ensure_user(maker, "staff", BRANCH_HO)
    await _ensure_user(other, "staff", BRANCH_HO)
    h_maker = await _login(client, maker)
    h_other = await _login(client, other)

    locs = (await client.get("/inventory/locations", headers=h_maker)).json()["locations"]
    items = (await client.get("/inventory/items", headers=h_maker)).json()["items"]
    assert locs and items

    created = await client.post(
        "/inventory/requests",
        headers=_idem(h_maker),
        json={
            "kind": "receipt",
            "dest_id": locs[0]["id"],
            "reason": "wave2 idor",
            "lines": [{"item_id": items[0]["id"], "quantity": "1"}],
        },
    )
    assert created.status_code in (200, 201), created.text
    req_id = created.json()["id"]

    # Nguoi khac KHONG duoc xoa phieu draft cua nguoi ta
    denied = await client.delete(f"/inventory/requests/{req_id}", headers=h_other)
    assert denied.status_code == 403, denied.text

    # Phieu van con nguyen sau khi bi tu choi
    still = await client.get(f"/inventory/requests/{req_id}", headers=h_maker)
    assert still.status_code == 200, still.text

    # Chu so huu xoa duoc
    ok = await client.delete(f"/inventory/requests/{req_id}", headers=h_maker)
    assert ok.status_code == 200, ok.text
    assert (await client.get(f"/inventory/requests/{req_id}", headers=h_maker)).status_code == 404


async def test_delete_cash_draft_request_only_by_owner(client):
    maker = f"w2_cash_a_{uuid.uuid4().hex[:8]}"
    other = f"w2_cash_b_{uuid.uuid4().hex[:8]}"
    await _ensure_user(maker, "staff", BRANCH_HO)
    await _ensure_user(other, "staff", BRANCH_HO)
    h_maker = await _login(client, maker)
    h_other = await _login(client, other)

    boxes = (await client.get("/cash-sim/boxes", headers=h_maker)).json()["boxes"]
    assert boxes

    created = await client.post(
        "/cash-sim/requests",
        headers=_idem(h_maker),
        json={
            "kind": "payment",
            "amount": "1000",
            "cashbox_id": boxes[0]["id"],
            "reason": "wave2 idor cash",
        },
    )
    assert created.status_code in (200, 201), created.text
    req_id = created.json()["id"]

    denied = await client.delete(f"/cash-sim/requests/{req_id}", headers=h_other)
    assert denied.status_code == 403, denied.text

    ok = await client.delete(f"/cash-sim/requests/{req_id}", headers=h_maker)
    assert ok.status_code == 200, ok.text


# ---------------------------------------------------------------------------
# B (S6) — Branch isolation
# ---------------------------------------------------------------------------
async def test_stocktakes_are_scoped_to_user_branch(client):
    suffix = uuid.uuid4().hex[:8]
    loc_a = await _make_location(f"W2-STK-A-{suffix}", BRANCH_A)
    loc_b = await _make_location(f"W2-STK-B-{suffix}", BRANCH_B)
    try:
        user_a = f"w2_stk_a_{suffix}"
        user_b = f"w2_stk_b_{suffix}"
        uid_a = await _ensure_user(user_a, "staff", BRANCH_A)
        uid_b = await _ensure_user(user_b, "staff", BRANCH_B)
        h_b = await _login(client, user_b)

        st_a = str(uuid.uuid4())
        st_b = str(uuid.uuid4())
        await _sql(
            "INSERT INTO inv_stocktakes (id, location_id, status, maker_id, note) "
            "VALUES (:id, :loc, 'open', :mk, 'wave2')",
            id=st_a,
            loc=loc_a,
            mk=uid_a,
        )
        await _sql(
            "INSERT INTO inv_stocktakes (id, location_id, status, maker_id, note) "
            "VALUES (:id, :loc, 'open', :mk, 'wave2')",
            id=st_b,
            loc=loc_b,
            mk=uid_b,
        )

        listed = await client.get("/inventory/stocktakes", headers=h_b)
        assert listed.status_code == 200, listed.text
        ids = {s["id"] for s in listed.json()["stocktakes"]}
        assert st_b in ids, "user branch B phai thay kiem ke cua minh"
        assert st_a not in ids, "user branch B KHONG duoc thay kiem ke branch A"

        # Doc chi tiet cua kiem ke branch A cung phai bi tu choi
        assert (await client.get(f"/inventory/stocktakes/{st_a}", headers=h_b)).status_code == 404
    finally:
        await _cleanup_location(loc_a)
        await _cleanup_location(loc_b)


async def test_cash_boxes_and_balances_are_scoped_to_user_branch(client):
    suffix = uuid.uuid4().hex[:8]
    box_a = await _make_cashbox(f"W2-BOX-A-{suffix}", BRANCH_A, "111")
    box_b = await _make_cashbox(f"W2-BOX-B-{suffix}", BRANCH_B, "222")
    try:
        user_a = f"w2_box_a_{suffix}"
        user_b = f"w2_box_b_{suffix}"
        await _ensure_user(user_a, "staff", BRANCH_A)
        await _ensure_user(user_b, "staff", BRANCH_B)
        h_a = await _login(client, user_a)
        h_b = await _login(client, user_b)

        boxes_b = (await client.get("/cash-sim/boxes", headers=h_b)).json()["boxes"]
        box_ids_b = {b["id"] for b in boxes_b}
        assert box_b in box_ids_b
        assert box_a not in box_ids_b, "user branch B KHONG duoc thay ket branch A"

        bal_b = (await client.get("/cash-sim/balances", headers=h_b)).json()["balances"]
        bal_ids_b = {b["cashbox_id"] for b in bal_b}
        assert box_b in bal_ids_b
        assert box_a not in bal_ids_b, "user branch B KHONG duoc thay so du branch A"

        # Khoa chay nguoc: user branch A thay het
        boxes_a = (await client.get("/cash-sim/boxes", headers=h_a)).json()["boxes"]
        assert box_a in {b["id"] for b in boxes_a}
        assert box_b not in {b["id"] for b in boxes_a}
    finally:
        await _cleanup_cashbox(box_a)
        await _cleanup_cashbox(box_b)


async def test_dashboard_summary_is_scoped_to_user_branch(client):
    suffix = uuid.uuid4().hex[:8]
    loc_a = await _make_location(f"W2-DB-A-{suffix}", BRANCH_A)
    loc_b = await _make_location(f"W2-DB-B-{suffix}", BRANCH_B)
    box_a = await _make_cashbox(f"W2-DBX-A-{suffix}", BRANCH_A, "5")
    try:
        user_a = f"w2_dash_a_{suffix}"
        user_b = f"w2_dash_b_{suffix}"
        await _ensure_user(user_a, "staff", BRANCH_A)
        await _ensure_user(user_b, "staff", BRANCH_B)
        h_b = await _login(client, user_b)

        # Balances cho ca hai branch (de dashboard co du lieu de loai)
        rows = await _sql("SELECT id FROM inv_items WHERE active = true LIMIT 1")
        assert rows
        item_id = str(rows[0][0])
        for loc in (loc_a, loc_b):
            await _sql(
                "INSERT INTO inv_balances (location_id, item_id, quantity, reserved_quantity, version) "
                "VALUES (:l, :i, 7, 0, 1)",
                l=loc,
                i=item_id,
            )

        data = (await client.get("/dashboard/summary", headers=h_b)).json()
        loc_ids = {loc["id"] for loc in data["locations"]}
        assert loc_b in loc_ids, "dashboard phai thay kho cua user"
        assert loc_a not in loc_ids, "dashboard KHONG duoc lo kho branch A"

        bal_locs = {b["location_id"] for b in data["balances"]}
        assert loc_b in bal_locs
        assert loc_a not in bal_locs, "dashboard KHONG duoc lo ton branch A"

        box_ids = {b["id"] for b in data["cashboxes"]}
        assert box_a not in box_ids, "dashboard KHONG duoc lo ket branch A"
    finally:
        await _cleanup_location(loc_a)
        await _cleanup_location(loc_b)
        await _cleanup_cashbox(box_a)


# ---------------------------------------------------------------------------
# C (S7) — Event stream phai co auth
# ---------------------------------------------------------------------------
async def test_events_stream_requires_authentication(client):
    anon = await client.get("/events/stream")
    assert anon.status_code == 401, anon.text


async def test_events_stream_requires_capability(client):
    # Role `checker` chi co etl:review -> khong co activity:view/audit:view
    username = f"w2_stream_{uuid.uuid4().hex[:8]}"
    await _ensure_user(username, "checker", BRANCH_HO)
    headers = await _login(client, username)
    r = await client.get("/events/stream", headers=headers)
    assert r.status_code == 403, r.text


async def test_events_stream_allowed_with_activity_capability(client):
    username = f"w2_stream_ok_{uuid.uuid4().hex[:8]}"
    await _ensure_user(username, "staff", BRANCH_HO)
    headers = await _login(client, username)
    r = await client.get("/events/stream", headers=headers)
    assert r.status_code == 200, r.text


# ---------------------------------------------------------------------------
# D (S9) — Google login khong cap role cho user da ton tai
# ---------------------------------------------------------------------------
async def test_google_login_existing_user_does_not_change_roles(client, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "demo_mode", True)
    email = f"w2_google_{uuid.uuid4().hex[:8]}@bankops.internal"
    await _ensure_user(email, "staff", BRANCH_HO)

    before = await _sql(
        "SELECT role_code FROM iam_user_roles ur JOIN iam_users u ON u.id = ur.user_id "
        "WHERE u.username = :u ORDER BY role_code",
        u=email,
    )
    assert [r[0] for r in before] == ["staff"]

    r = await client.post(
        "/auth/google",
        json={"id_token": f"mock-google-token:{email}:Wave2 Google User"},
    )
    assert r.status_code == 200, r.text
    roles = r.json()["user"]["roles"]
    assert "inventory_manager" not in roles, "khong duoc tu cap role khi user da ton tai"
    assert roles == ["staff"]

    after = await _sql(
        "SELECT role_code FROM iam_user_roles ur JOIN iam_users u ON u.id = ur.user_id "
        "WHERE u.username = :u ORDER BY role_code",
        u=email,
    )
    assert [r[0] for r in after] == ["staff"]


# ---------------------------------------------------------------------------
# E (R3/R4) — Session revocation
# ---------------------------------------------------------------------------
async def test_admin_bump_auth_version_revokes_tokens(client):
    username = f"w2_rev_{uuid.uuid4().hex[:8]}"
    uid = await _ensure_user(username, "staff", BRANCH_HO)
    h = await _login(client, username)
    refresh_token = (await _tokens(client, username))["refresh_token"]

    # Admin thu hoi phien: tang auth_version qua endpoint chinh thuc
    admin_h = await _login(client, "demo_admin", "DemoPass123!")
    revoked = await client.post(
        f"/admin/users/{uid}/sessions/revoke",
        headers=_idem(admin_h),
    )
    assert revoked.status_code == 200, revoked.text

    # Access token cu bi tu choi
    assert (await client.get("/auth/me", headers=h)).status_code == 401
    # Refresh token cu bi tu choi
    r = await client.post("/auth/refresh", json={"refresh_token": refresh_token})
    assert r.status_code == 401, r.text


async def test_change_password_revokes_existing_sessions(client):
    username = f"w2_chpw_{uuid.uuid4().hex[:8]}"
    await _ensure_user(username, "staff", BRANCH_HO)
    h = await _login(client, username)
    refresh_token = (await _tokens(client, username))["refresh_token"]

    r = await client.post(
        "/auth/change-password",
        headers=h,
        json={"old_password": PASSWORD, "new_password": "Wave2Changed456!"},
    )
    assert r.status_code == 200, r.text

    assert (await client.get("/auth/me", headers=h)).status_code == 401
    rr = await client.post("/auth/refresh", json={"refresh_token": refresh_token})
    assert rr.status_code == 401, rr.text

    # Mat khau moi dung -> dang nhap lai duoc
    again = await client.post(
        "/auth/login", json={"username": username, "password": "Wave2Changed456!"}
    )
    assert again.status_code == 200, again.text


async def test_reset_password_revokes_existing_sessions(client, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "demo_mode", True)
    username = f"w2_reset_{uuid.uuid4().hex[:8]}"
    await _ensure_user(username, "staff", BRANCH_HO)
    h = await _login(client, username)
    refresh_token = (await _tokens(client, username))["refresh_token"]

    forgot = await client.post("/auth/forgot-password", json={"username": username})
    assert forgot.status_code == 200, forgot.text
    otp = forgot.json().get("otp_demo")
    assert otp, "demo mode phai tra OTP de test"

    reset = await client.post(
        "/auth/reset-password",
        json={"username": username, "otp": otp, "new_password": "Wave2Reset456!"},
    )
    assert reset.status_code == 200, reset.text

    assert (await client.get("/auth/me", headers=h)).status_code == 401
    rr = await client.post("/auth/refresh", json={"refresh_token": refresh_token})
    assert rr.status_code == 401, rr.text


# ---------------------------------------------------------------------------
# F (S13) — must_change_password phai duoc enforce
# ---------------------------------------------------------------------------
async def test_must_change_password_blocks_business_endpoints(client):
    username = f"w2_mustchg_{uuid.uuid4().hex[:8]}"
    uid = await _ensure_user(username, "staff", BRANCH_HO)
    await _sql("UPDATE iam_users SET must_change_password = true WHERE id = :id", id=uid)
    h = await _login(client, username)

    denied = await client.get("/inventory/items", headers=h)
    assert denied.status_code == 403, denied.text
    body = denied.json()
    assert body["error"]["code"] == "PASSWORD_CHANGE_REQUIRED", body

    # /auth/me van cho phep (can thiet cho client biet trang thai)
    assert (await client.get("/auth/me", headers=h)).status_code == 200

    # Doi mat khau lan dau van cho phep
    changed = await client.post(
        "/auth/change-initial-password",
        headers=h,
        json={"current_password": PASSWORD, "new_password": "Wave2Initial789!"},
    )
    assert changed.status_code == 200, changed.text

    # Sau khi doi -> tru cap nghiep vu duoc (phai dang nhap lai: doi mat khau
    # cung thu hoi phien cu -> token cu bi 401)
    h2 = await _login(client, username, "Wave2Initial789!")
    assert (await client.get("/inventory/items", headers=h2)).status_code == 200


# ---------------------------------------------------------------------------
# G (S11) — Login rate limit theo username + IP
# ---------------------------------------------------------------------------
async def test_login_rate_limit_returns_429_with_retry_after(client):
    username = f"w2_rl_{uuid.uuid4().hex[:8]}"
    await _ensure_user(username, "staff", BRANCH_HO)
    for _ in range(6):
        r = await client.post(
            "/auth/login", json={"username": username, "password": "WrongPassword!"}
        )
    assert r.status_code == 429, r.text
    assert "Retry-After" in r.headers, r.headers


async def test_login_rate_limit_is_scoped_per_ip(app, client):
    """Sai mat khau tu IP khac khong khoa tai khoan cua IP goc (chong DoS)."""
    from httpx import ASGITransport, AsyncClient

    username = f"w2_rlip_{uuid.uuid4().hex[:8]}"
    await _ensure_user(username, "staff", BRANCH_HO)

    async with AsyncClient(transport=ASGITransport(app=app, client=("9.9.9.9", 50000)), base_url="http://testserver") as attacker:
        for _ in range(6):
            await attacker.post(
                "/auth/login", json={"username": username, "password": "WrongPassword!"}
            )
        locked = await attacker.post(
            "/auth/login", json={"username": username, "password": PASSWORD}
        )
        assert locked.status_code == 429, locked.text

    # IP khac -> van dang nhap duoc voi mat khau dung
    ok = await client.post("/auth/login", json={"username": username, "password": PASSWORD})
    assert ok.status_code == 200, ok.text


class _FakeRedis:
    """Bộ giả lập tối thiểu cho `redis.Redis` (INCR/EXPIRE/GET/TTL/DEL)."""

    def __init__(self):
        self.values: dict[str, int] = {}
        self.ttls: dict[str, int] = {}

    def get(self, key):
        return self.values.get(key)

    def incr(self, key):
        self.values[key] = self.values.get(key, 0) + 1
        return self.values[key]

    def expire(self, key, seconds):
        self.ttls[key] = seconds

    def ttl(self, key):
        if key not in self.values:
            return -2
        return self.ttls.get(key, -1)

    def delete(self, key):
        self.values.pop(key, None)
        self.ttls.pop(key, None)


async def test_rate_limiter_uses_redis_backend_when_configured(monkeypatch):
    """Khi có Redis client, bộ đếm phải dùng Redis (dùng chung nhiều replica)."""
    from app.api.routes import auth_utils

    fake = _FakeRedis()
    monkeypatch.setattr(auth_utils, "_redis_client", fake)
    monkeypatch.setattr(auth_utils, "_redis_resolved", True)

    user = f"w2_redis_{uuid.uuid4().hex[:8]}"
    ip = "10.0.0.5"
    assert auth_utils.login_rate_limited(user, ip) is False
    for _ in range(3):
        auth_utils.record_login_failure(user, ip)
    assert auth_utils.login_rate_limited(user, ip) is False  # 3 < 5
    for _ in range(2):
        auth_utils.record_login_failure(user, ip)
    assert auth_utils.login_rate_limited(user, ip) is True  # 5 >= 5
    # IP khac -> khong bi khoa
    assert auth_utils.login_rate_limited(user, "10.0.0.6") is False
    # TTL (Retry-After) do Redis cung cap
    assert auth_utils.login_retry_after_seconds(user, ip) > 0
    # Xoa so do -> khoa duoc goi
    auth_utils.reset_login_failures(user, ip)
    assert auth_utils.login_rate_limited(user, ip) is False


async def test_rate_limiter_falls_back_to_memory_when_redis_fails(monkeypatch):
    """Redis lỗi -> phải fallback về bộ đếm trong RAM (không mở cửa brute force)."""
    from app.api.routes import auth_utils

    class _BrokenRedis:
        def get(self, key):
            raise RuntimeError("redis down")

        def incr(self, key):
            raise RuntimeError("redis down")

        def expire(self, key, seconds):
            raise RuntimeError("redis down")

        def ttl(self, key):
            raise RuntimeError("redis down")

        def delete(self, key):
            raise RuntimeError("redis down")

    monkeypatch.setattr(auth_utils, "_redis_client", _BrokenRedis())
    monkeypatch.setattr(auth_utils, "_redis_resolved", True)

    user = f"w2_redisdown_{uuid.uuid4().hex[:8]}"
    ip = "10.0.0.7"
    for _ in range(5):
        auth_utils.record_login_failure(user, ip)
    assert auth_utils.login_rate_limited(user, ip) is True
    assert auth_utils.login_retry_after_seconds(user, ip) > 0


# ---------------------------------------------------------------------------
# H (R9) — Soft delete item khong lam mat ton kho
# ---------------------------------------------------------------------------
async def test_soft_delete_item_keeps_balance(client):
    suffix = uuid.uuid4().hex[:8]
    username = f"w2_delmgr_{suffix}"
    await _ensure_user(username, "inventory_manager", BRANCH_HO)
    h = await _login(client, username)

    sku = f"W2-DEL-{suffix}"
    item = await client.post(
        "/inventory/items",
        headers=h,
        json={"sku": sku, "name": "Món xoá mềm", "unit": "kg"},
    )
    assert item.status_code in (200, 201), item.text
    item_id = item.json()["id"]

    locs = (await client.get("/inventory/locations", headers=h)).json()["locations"]
    loc_id = locs[0]["id"]

    # Tao phieu nhap (ton tai -> nhanh soft delete) + ton kho
    req = await client.post(
        "/inventory/requests",
        headers=_idem(h),
        json={
            "kind": "receipt",
            "dest_id": loc_id,
            "reason": "wave2 soft delete",
            "lines": [{"item_id": item_id, "quantity": "10"}],
        },
    )
    assert req.status_code in (200, 201), req.text
    req_id = req.json()["id"]
    await client.post(f"/inventory/requests/{req_id}/submit", headers=h)

    checker = f"w2_delchk_{suffix}"
    await _ensure_user(checker, "approver", BRANCH_HO)
    hc = await _login(client, checker)
    approved = await client.post(
        f"/inventory/requests/{req_id}/approve",
        headers={**hc, "Idempotency-Key": str(uuid.uuid4())},
    )
    assert approved.status_code == 200, approved.text

    bal_before = await _sql(
        "SELECT quantity FROM inv_balances WHERE item_id = :i AND location_id = :l",
        i=item_id,
        l=loc_id,
    )
    assert bal_before, "phai co ton kho truoc khi xoa"

    deleted = await client.delete(f"/inventory/items/{item_id}", headers=h)
    assert deleted.status_code == 200, deleted.text
    assert deleted.json()["mode"] == "soft_deleted", deleted.text

    # Ton kho phai con nguyen sau soft delete
    bal_after = await _sql(
        "SELECT quantity FROM inv_balances WHERE item_id = :i AND location_id = :l",
        i=item_id,
        l=loc_id,
    )
    assert bal_after, "soft delete KHONG duoc xoa ton kho"

    # Khong co lech (tong movement == ton)
    moved = await _sql(
        "SELECT COALESCE(SUM(quantity_signed), 0) FROM inv_movements "
        "WHERE item_id = :i AND location_id = :l",
        i=item_id,
        l=loc_id,
    )
    assert float(moved[0][0]) == float(bal_after[0][0]), "soft delete tao lech ton kho"


async def test_hard_delete_item_removes_balance(client):
    suffix = uuid.uuid4().hex[:8]
    username = f"w2_delmgr2_{suffix}"
    await _ensure_user(username, "inventory_manager", BRANCH_HO)
    h = await _login(client, username)

    sku = f"W2-HARD-{suffix}"
    item = await client.post(
        "/inventory/items",
        headers=h,
        json={"sku": sku, "name": "Món xoá cứng", "unit": "kg"},
    )
    assert item.status_code in (200, 201), item.text
    item_id = item.json()["id"]

    locs = (await client.get("/inventory/locations", headers=h)).json()["locations"]
    loc_id = locs[0]["id"]
    await _sql(
        "INSERT INTO inv_balances (location_id, item_id, quantity, reserved_quantity, version) "
        "VALUES (:l, :i, 3, 0, 1)",
        l=loc_id,
        i=item_id,
    )

    deleted = await client.delete(f"/inventory/items/{item_id}", headers=h)
    assert deleted.status_code == 200, deleted.text
    assert deleted.json()["mode"] == "hard_deleted", deleted.text

    bal_after = await _sql(
        "SELECT quantity FROM inv_balances WHERE item_id = :i", i=item_id
    )
    assert not bal_after, "hard delete phai xoa ton kho"


# ---------------------------------------------------------------------------
# I (S8) — Client khong duoc tu ghi opening_qty / received_qty
# ---------------------------------------------------------------------------
async def test_stocktake_client_cannot_mass_assign_opening_qty(client):
    suffix = uuid.uuid4().hex[:8]
    username = f"w2_stk_{suffix}"
    await _ensure_user(username, "staff", BRANCH_HO)
    h = await _login(client, username)

    loc_id = await _make_location(f"W2-OPEN-{suffix}", BRANCH_HO)
    try:
        rows = await _sql("SELECT id FROM inv_items WHERE active = true LIMIT 1")
        item_id = str(rows[0][0])
        await _sql(
            "INSERT INTO inv_balances (location_id, item_id, quantity, reserved_quantity, version) "
            "VALUES (:l, :i, 50, 0, 1)",
            l=loc_id,
            i=item_id,
        )

        business = date.today() + timedelta(days=int(suffix[:2], 16) % 300 + 1)
        created = await client.post(
            "/inventory/stocktakes",
            headers=_idem(h),
            json={
                "location_id": loc_id,
                "shift_code": "morning",
                "business_date": business.isoformat(),
                "note": "wave2 mass assignment",
            },
        )
        assert created.status_code in (200, 201), created.text
        st_id = created.json()["id"]

        # Maker tu gia: opening = counted, received = counted -> variance = 0
        updated = await client.put(
            f"/inventory/stocktakes/{st_id}/lines",
            headers=h,
            json={
                "lines": [
                    {
                        "item_id": item_id,
                        "counted_qty": "200",
                        "opening_qty": "100",
                        "received_qty": "100",
                        "used_qty": "0",
                    }
                ]
            },
        )
        assert updated.status_code == 200, updated.text
        line = next(x for x in updated.json()["lines"] if x["item_id"] == item_id)

        # Server phai bo qua gia tri client gui cho opening/received
        assert float(line["opening_qty"]) == 50.0, line
        assert float(line["received_qty"]) == 0.0, line
        # ... va variance phai do server tinh (khong phai 0)
        assert float(line["variance"]) != 0.0, line
        assert float(line["variance"]) == 150.0, line
    finally:
        await _cleanup_location(loc_id)
