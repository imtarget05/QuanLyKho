"""Request bodies consumed by the idempotency layer must reach the API handler."""

from __future__ import annotations

import asyncio
import uuid

import pytest
from fastapi import FastAPI, Request
from httpx import ASGITransport, AsyncClient

from app.api.middleware.idempotency import IdempotencyMiddleware
from app.services import idempotency


@pytest.mark.asyncio
async def test_json_body_reaches_handler_after_idempotency_hash(monkeypatch):
    monkeypatch.setattr(idempotency, "check", lambda key, digest: None)
    monkeypatch.setattr(idempotency, "remember", lambda *args: None)

    app = FastAPI()

    @app.post("/echo")
    async def echo(request: Request):
        return await request.json()

    app.add_middleware(IdempotencyMiddleware)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await asyncio.wait_for(
            client.post(
                "/echo",
                headers={"Idempotency-Key": str(uuid.uuid4())},
                json={"quantity": 5},
            ),
            timeout=2,
        )

    assert response.status_code == 200
    assert response.json() == {"quantity": 5}


@pytest.mark.asyncio
async def test_http_replay_does_not_cross_authentication_context(monkeypatch):
    stored = {}

    def check(key, digest):
        return stored.get(key)

    def remember(_db, key, digest, status, body):
        stored[key] = (status, body)

    monkeypatch.setattr(idempotency, "check", check)
    monkeypatch.setattr(idempotency, "remember", remember)

    app = FastAPI()

    @app.post("/actor")
    async def actor(request: Request):
        return {"actor": request.headers["authorization"]}

    app.add_middleware(IdempotencyMiddleware)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        first = await client.post(
            "/actor", headers={"Idempotency-Key": "same", "Authorization": "Bearer maker"}, json={}
        )
        second = await client.post(
            "/actor", headers={"Idempotency-Key": "same", "Authorization": "Bearer checker"}, json={}
        )

    assert first.json() == {"actor": "Bearer maker"}
    assert second.json() == {"actor": "Bearer checker"}
