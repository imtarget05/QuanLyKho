"""POST /auth/logout — thu hoc token, sau do dung lai -> 401; khong co token -> 401."""

from __future__ import annotations

import uuid

import pytest
from portfolio_test_helpers import ensure_auth_user

PASSWORD = "LogoutTest123!"


async def _ensure_user(username: str) -> str:
    return await ensure_auth_user(username, PASSWORD, "Logout")


async def _login(async_client, username: str, password: str = PASSWORD):
    return await async_client.post(
        "/auth/login", json={"username": username, "password": password}
    )


async def _bearer(async_client, username: str) -> dict:
    r = await _login(async_client, username)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.mark.asyncio
async def test_logout_revokes_access_token(async_client):
    username = f"logout_ok_{uuid.uuid4().hex[:8]}"
    await _ensure_user(username)
    headers = await _bearer(async_client, username)

    r = await async_client.post("/auth/logout", headers=headers, json={})
    assert r.status_code == 200, r.text
    assert r.json()["message"] == "Logged out successfully"

    # Token da thu hoi khong su dung duoc nua.
    r = await async_client.get("/auth/me", headers=headers)
    assert r.status_code == 401, r.text


@pytest.mark.asyncio
async def test_logout_no_token_401(async_client):
    r = await async_client.post("/auth/logout", json={})
    assert r.status_code == 401, r.text
