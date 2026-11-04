"""Rate limit dang nhap: nhieu lan sai -> 429; sau khoa (cua so het han) -> dang nhap duoc lai."""

from __future__ import annotations

import time
import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.api.routes import auth_utils
from app.config import settings
from app.database import AsyncSessionLocal

PASSWORD = "RateLimitTest123!"
WRONG = "WrongPassword!"


async def _sql(sql: str, **params):
    async with AsyncSessionLocal() as session:
        result = await session.execute(text(sql), params)
        await session.commit()
        if not result.returns_rows:
            return []
        return result.fetchall()


async def _ensure_user(username: str) -> str:
    from app.api.routes.auth_utils import get_password_hash

    rows = await _sql("SELECT id FROM iam_users WHERE username = :u", u=username)
    if rows:
        user_id = str(rows[0][0])
        await _sql(
            "UPDATE iam_users SET password_hash = :p, status = 'active' WHERE id = :id",
            p=get_password_hash(PASSWORD),
            id=user_id,
        )
    else:
        user_id = str(uuid.uuid4())
        await _sql(
            "INSERT INTO iam_users (id, username, password_hash, status, display_name_demo, email) "
            "VALUES (:id, :u, :p, 'active', :d, :e)",
            id=user_id,
            u=username,
            p=get_password_hash(PASSWORD),
            d=f"RateLimit {username}",
            e=f"{username}@bankops.internal",
        )
    return user_id


@pytest.fixture
async def async_client(app):
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        yield client


async def _login_json(async_client, username: str, password: str):
    return await async_client.post(
        "/auth/login", json={"username": username, "password": password}
    )


@pytest.mark.asyncio
async def test_multiple_failed_login_attempts_rate_limited(async_client):
    username = f"rl_fail_{uuid.uuid4().hex[:8]}"
    await _ensure_user(username)

    max_attempts = settings.rate_limit_login_attempts
    for _ in range(max_attempts):
        r = await _login_json(async_client, username, WRONG)
        assert r.status_code == 401, r.text

    # Lan thu tiep theo bi khoa -> 429 kèm header Retry-After.
    r = await _login_json(async_client, username, WRONG)
    assert r.status_code == 429, r.text
    assert "Retry-After" in r.headers, r.headers


@pytest.mark.asyncio
async def test_after_lockout_window_login_works_again(async_client, monkeypatch):
    """Giai ma kho het han, mat khau chinh lai van dang nhap duoc (an giua bo dem thoi gian)."""
    username = f"rl_recover_{uuid.uuid4().hex[:8]}"
    await _ensure_user(username)

    now = [time.time()]
    monkeypatch.setattr(auth_utils.time, "time", lambda: now[0])

    max_attempts = settings.rate_limit_login_attempts
    for _ in range(max_attempts):
        r = await _login_json(async_client, username, WRONG)
        assert r.status_code == 401, r.text

    r = await _login_json(async_client, username, WRONG)
    assert r.status_code == 429, r.text

    # Thoi gian chay qua cua so khoa (window + 1 giay).
    now[0] += settings.rate_limit_login_window_minutes * 60 + 1

    r = await _login_json(async_client, username, PASSWORD)
    assert r.status_code == 200, r.text
