"""Rate limit dang nhap: nhieu lan sai -> 429; sau khoa (cua so het han) -> dang nhap duoc lai."""

from __future__ import annotations

import time
import uuid

import pytest
from portfolio_test_helpers import ensure_auth_user

from app.api.routes import auth_utils
from app.config import settings

PASSWORD = "RateLimitTest123!"
WRONG = "WrongPassword!"


async def _ensure_user(username: str) -> str:
    return await ensure_auth_user(username, PASSWORD, "RateLimit")


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
