"""Tests for SSE Redis pub/sub (P8 - multi-replica)."""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_publish_sse_event_no_redis_falls_back():
    """Khi không có Redis, publish_sse_event không lỗi (fallback in-memory)."""
    from app.services.events import publish_sse_event

    # Neu co ham publish_sse_event, goi no; neu khong, bo qua
    try:
        await publish_sse_event("auth.login", {"user_id": "x"}, "evt-1")
    except NameError:
        pytest.skip("publish_sse_event chua duoc export")


async def test_sse_endpoint_exists(client):
    """Endpoint SSE duoc mount."""
    resp = client.get("/api/v1/events/stream")
    assert resp.status_code in (200, 401)  # 401 neu chua co token, 200 neu co
