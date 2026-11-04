"""POST /auth/refresh — rotation, invalid/expired token, type confusion."""

from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.api.routes import auth_utils
from app.database import AsyncSessionLocal

PASSWORD = "RefreshTest123!"


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
            d=f"Refresh {username}",
            e=f"{username}@bankops.internal",
        )
    return user_id


@pytest.fixture
async def async_client(app):
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        yield client


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
