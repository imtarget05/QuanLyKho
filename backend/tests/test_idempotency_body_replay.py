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
