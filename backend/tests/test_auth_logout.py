"""POST /auth/logout — thu hoc token, sau do dung lai -> 401; khong co token -> 401."""

from __future__ import annotations

import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.database import AsyncSessionLocal

PASSWORD = "LogoutTest123!"


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
            d=f"Logout {username}",
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
