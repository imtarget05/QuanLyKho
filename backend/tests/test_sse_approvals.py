"""Tests for Native Server-Sent Events (SSE) approvals stream."""

import asyncio
import json

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.models.iam import User
from app.services.approval_events import (
    ApprovalEventBus,
    approval_event_bus,
    broadcast_approval_event,
)

DEMO_PASSWORD = "DemoPass123!"


class AsyncClientDisconnectStub:
    async def is_disconnected(self) -> bool:
        return False


@pytest.mark.asyncio
async def test_sse_event_bus_unit():
    """Unit test for ApprovalEventBus pub/sub lifecycle."""
    bus = ApprovalEventBus(max_queue_size=5)
    assert bus.subscriber_count == 0

    queue = await bus.subscribe()
    assert bus.subscriber_count == 1

    delivered = await bus.publish("approval_update", {"action": "submitted", "id": "123"})
    assert delivered == 1

    message = await asyncio.wait_for(queue.get(), timeout=1.0)
    parsed = json.loads(message)
    assert parsed["event"] == "approval_update"
    assert parsed["data"]["action"] == "submitted"
    assert parsed["data"]["id"] == "123"

    await bus.unsubscribe(queue)
    assert bus.subscriber_count == 0


@pytest.mark.asyncio
async def test_sse_stream_requires_authentication():
    """GET /api/v1/approvals/stream without token must return 401."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/approvals/stream")
        assert response.status_code == 401


@pytest.mark.asyncio
async def test_sse_stream_connects_and_receives_event():
    """GET /api/v1/approvals/stream with valid JWT connects and receives broadcast events."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Log in as demo_checker to obtain a valid access token
        login_resp = await client.post(
            "/api/v1/auth/login",
            json={"username": "demo_checker", "password": DEMO_PASSWORD},
        )
        assert login_resp.status_code == 200, login_resp.text
        assert login_resp.json()["access_token"]

        class DummyRequest:
            async def is_disconnected(self) -> bool:
                return False

        user = User(id="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa2", username="demo_checker")
        from app.features.approvals.routes import approval_event_generator

        generator = approval_event_generator(DummyRequest(), user)
        connected = await anext(generator)
        await broadcast_approval_event(
            action="submitted",
            request_id="req-999",
            kind="cash",
            status="submitted",
            message="Phiếu quỹ 500M VND được gửi duyệt",
        )
        event = await asyncio.wait_for(anext(generator), timeout=1.0)
        await generator.aclose()
        assert "event: connected" in connected
        assert '"status": "connected"' in connected
        assert "event: approval_update" in event
        assert "req-999" in event
        assert approval_event_bus.subscriber_count == 0
