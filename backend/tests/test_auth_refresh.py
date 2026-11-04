"""POST /auth/refresh — rotation, invalid/expired token, type confusion."""

from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from portfolio_test_helpers import ensure_auth_user

from app.api.routes import auth_utils

PASSWORD = "RefreshTest123!"


async def _ensure_user(username: str) -> str:
    return await ensure_auth_user(username, PASSWORD, "Refresh")


async def _login(async_client, username: str, password: str = PASSWORD):
    return await async_client.post(
        "/auth/login", json={"username": username, "password": password}
    )


async def _tokens(async_client, username: str) -> dict:
    r = await _login(async_client, username)
    assert r.status_code == 200, r.text
    return r.json()


@pytest.mark.asyncio
async def test_refresh_rotation_returns_new_access_and_refresh_token(async_client):
    username = f"refresh_rot_{uuid.uuid4().hex[:8]}"
    await _ensure_user(username)
    before = await _tokens(async_client, username)
    refresh_token = before["refresh_token"]

    r = await async_client.post("/auth/refresh", json={"refresh_token": refresh_token})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["access_token"]
    assert body["refresh_token"]
    assert body["token_type"] == "bearer"
    assert body["expires_in"] == 1800

    # Rotation: refresh token vua dung bi thu hoi, khong tai su dung lai.
    r2 = await async_client.post("/auth/refresh", json={"refresh_token": refresh_token})
    assert r2.status_code == 401, r2.text


@pytest.mark.asyncio
async def test_refresh_invalid_token_401(async_client):
    r = await async_client.post("/auth/refresh", json={"refresh_token": "khong-phai-jwt"})
    assert r.status_code == 401, r.text

    r = await async_client.post("/auth/refresh", json={"refresh_token": ""})
    assert r.status_code == 401, r.text


@pytest.mark.asyncio
async def test_refresh_expired_token_401(async_client):
    username = f"refresh_exp_{uuid.uuid4().hex[:8]}"
    user_id = await _ensure_user(username)
    expired = auth_utils.create_refresh_token(
        {"sub": user_id, "username": username}, timedelta(seconds=-1)
    )
    r = await async_client.post("/auth/refresh", json={"refresh_token": expired})
    assert r.status_code == 401, r.text


@pytest.mark.asyncio
async def test_refresh_access_token_used_as_refresh_rejected(async_client):
    """Type confusion: access token (type=access) khong duoc dung goi /auth/refresh."""
    username = f"refresh_tc_{uuid.uuid4().hex[:8]}"
    await _ensure_user(username)
    before = await _tokens(async_client, username)
    r = await async_client.post(
        "/auth/refresh", json={"refresh_token": before["access_token"]}
    )
    assert r.status_code == 401, r.text
