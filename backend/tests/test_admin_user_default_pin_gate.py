"""D4 — PIN mặc định khi admin tạo user KHÔNG được hardcode ngoài demo mode.

Residual (đã báo cáo ở wave inventory §2.5):
`backend/app/api/routes/admin_users.py:351` gán
`pin_hash = get_password_hash("123456")` cho **MỌI** user mới tạo qua admin,
**không** gate theo `settings.is_demo_mode`.

Hệ quả: ở production, mọi tài khoản do admin tạo đều dùng chung PIN demo
`123456` — PIN đã công khai trong repo (xem
`docs/security/secret-rotation-inventory-2026-10-20.md` §2.5).

Contract sau khi sửa (giống `backend/app/seed.py` và
`backend/app/api/routes/auth.py`):
- `settings.is_demo_mode` bật  -> `pin_hash` = hash(PIN demo).
- ngoài demo mode              -> `pin_hash IS NULL` (fail-closed: user chưa có
  PIN, admin phải tự đặt; cổng duyệt dùng PIN cấu hình `SUPERVISOR_PIN`).
"""

from __future__ import annotations

import asyncio
import uuid

import pytest
from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.iam import User

DEMO_PASSWORD = "DemoPass123!"


def _login(client, username: str, password: str = DEMO_PASSWORD) -> dict[str, str]:
    r = client.post("/auth/login", data={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _idem(headers: dict[str, str]) -> dict[str, str]:
    return {**headers, "Idempotency-Key": str(uuid.uuid4())}


def _fetch_pin_hash(username: str):
    async def _read():
        async with AsyncSessionLocal() as db:
            row = (
                await db.execute(select(User).where(User.username == username))
            ).scalar_one_or_none()
            return None if row is None else row.pin_hash

    return asyncio.run(_read())


def _settings():
    from app.config import settings

    return settings


@pytest.fixture
def non_demo_mode(monkeypatch):
    """Tắt demo mode (như môi trường production/staging)."""
    monkeypatch.setattr(
        type(_settings()), "is_demo_mode", property(lambda self: False), raising=False
    )
    yield


@pytest.fixture
def demo_mode(monkeypatch):
    """Bật demo mode tường minh."""
    monkeypatch.setattr(
        type(_settings()), "is_demo_mode", property(lambda self: True), raising=False
    )
    yield


class TestAdminCreateUserDefaultPin:
    def test_non_demo_user_has_no_default_pin(self, client, non_demo_mode):
        """Ngoài demo mode: user mới KHÔNG có PIN sẵn."""
        admin_auth = _login(client, "demo_admin")
        username = f"pin_gate_{uuid.uuid4().hex[:6]}"
        r = client.post(
            "/admin/users",
            headers=_idem(admin_auth),
            json={
                "username": username,
                "display_name": "Nguoi Dung Khong PIN",
                "roles": ["staff"],
                "onboarding_method": "temporary_password",
            },
        )
        assert r.status_code == 201, r.text

        pin_hash = _fetch_pin_hash(username)
        assert pin_hash is None, (
            "ngoài demo mode KHÔNG được gán PIN mặc định (kể cả PIN demo "
            f"'123456' đã công khai) — pin_hash={pin_hash!r}"
        )

    def test_demo_user_gets_demo_default_pin(self, client, demo_mode):
        """Demo mode: giữ hành vi cũ (PIN demo) để luồng demo chạy được."""
        admin_auth = _login(client, "demo_admin")
        username = f"pin_demo_{uuid.uuid4().hex[:6]}"
        r = client.post(
            "/admin/users",
            headers=_idem(admin_auth),
            json={
                "username": username,
                "display_name": "Nguoi Dung Demo",
                "roles": ["staff"],
                "onboarding_method": "temporary_password",
            },
        )
        assert r.status_code == 201, r.text

        pin_hash = _fetch_pin_hash(username)
        assert pin_hash is not None, "demo mode vẫn phải gán PIN mặc định"
