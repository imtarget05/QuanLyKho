"""Shared HTTP and database setup for portfolio integration tests."""

from __future__ import annotations

import uuid

from sqlalchemy import text

from app.database import AsyncSessionLocal


async def async_sql(sql: str, **params):
    async with AsyncSessionLocal() as session:
        result = await session.execute(text(sql), params)
        await session.commit()
        return result.fetchall() if result.returns_rows else []


async def ensure_auth_user(username: str, password: str, display_prefix: str) -> str:
    from app.api.routes.auth_utils import get_password_hash

    rows = await async_sql("SELECT id FROM iam_users WHERE username = :u", u=username)
    password_hash = get_password_hash(password)
    if rows:
        user_id = str(rows[0][0])
        await async_sql(
            "UPDATE iam_users SET password_hash = :p, status = 'active' WHERE id = :id",
            p=password_hash,
            id=user_id,
        )
    else:
        user_id = str(uuid.uuid4())
        await async_sql(
            "INSERT INTO iam_users (id, username, password_hash, status, display_name_demo, email) "
            "VALUES (:id, :u, :p, 'active', :d, :e)",
            id=user_id,
            u=username,
            p=password_hash,
            d=f"{display_prefix} {username}",
            e=f"{username}@bankops.internal",
        )
    return user_id


async def login_headers(client, username: str, password: str = "DemoPass123!") -> dict:
    response = await client.post("/auth/login", data={"username": username, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def first_location_and_item(client, headers: dict) -> tuple:
    locations = (await client.get("/inventory/locations", headers=headers)).json()["locations"]
    assert locations, "Can it kho"
    items = (await client.get("/inventory/items", headers=headers)).json()["items"]
    assert items, "Can it hang"
    return locations[0]["id"], items[0]["id"]


def idem_headers(headers: dict) -> dict:
    return {**headers, "Idempotency-Key": str(uuid.uuid4())}
