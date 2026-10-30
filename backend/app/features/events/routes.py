"""SSE events channel — real-time auth stream (login / logout / session revoked).

Mounted at root (`GET /events/stream`) and under `/api/v1` (`GET /api/v1/events/stream`)
by ``app/main.py``.

Authentication: Bearer token via `?token=` query param (EventSource standard) or
`Authorization: Bearer <token>` header.

Reconnection/replay: the `Last-Event-ID` header resumes delivery from the last
received event id using the bus's in-memory ring buffer.

Multi-replica: ``publish_sse_event`` publishes to Redis channel ``sse:events`` so
all worker replicas can forward real-time events to their connected SSE clients.
"""

import asyncio
import json
import logging
import os
from collections.abc import AsyncGenerator

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes.auth_utils import get_user_from_token_string
from app.database import get_db
from app.models.iam import User
from app.services.auth_events import auth_event_bus

logger = logging.getLogger(__name__)

router = APIRouter()

_AUTH_EVENTS = ("auth.login", "auth.logout", "auth.session_revoked")
_SSE_REDIS_CHANNEL = "sse:events"
_redis_client: aioredis.Redis | None = None
_redis_ready = False


def _get_redis_url() -> str | None:
    return os.environ.get("REDIS_URL")


async def _get_redis() -> aioredis.Redis | None:
    """Lazily create a Redis client for SSE pub/sub."""
    global _redis_client, _redis_ready
    if _redis_ready:
        return _redis_client
    _redis_ready = True
    url = _get_redis_url()
    if not url:
        return None
    try:
        _redis_client = aioredis.from_url(url, decode_responses=True)
        await _redis_client.ping()
        logger.info("Redis SSE pub/sub connected: %s", url)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Redis SSE unavailable (falling back to in-memory bus): %s", exc)
        _redis_client = None
    return _redis_client


async def publish_sse_event(event_type: str, payload: dict, event_id: str | None = None) -> None:
    """Publish an SSE event to Redis so all replicas can fan out to clients."""
    client = await _get_redis()
    if client is None:
        return
    message = json.dumps(
        {
            "event_type": event_type,
            "payload": payload,
            "event_id": event_id,
            "ts": __import__("datetime").datetime.now(__import__("datetime").UTC).isoformat(),
        },
        ensure_ascii=False,
    )
    try:
        await client.publish(_SSE_REDIS_CHANNEL, message)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Redis SSE publish failed: %s", exc)


async def auth_event_generator(request: Request, user: User) -> AsyncGenerator[str, None]:
    queue = await auth_event_bus.subscribe()
    try:
        last_event_id = request.headers.get("last-event-id")
        for encoded in auth_event_bus.replay_from(last_event_id):
            yield encoded

        init_payload = json.dumps(
            {"status": "connected", "username": user.username, "user_id": str(user.id)},
            ensure_ascii=False,
        )
        yield f"event: connected\ndata: {init_payload}\n\n"

        while True:
            if await request.is_disconnected():
                break
            try:
                payload = await asyncio.wait_for(queue.get(), timeout=15.0)
                yield payload
            except TimeoutError:
                yield ": keepalive ping\n\n"
    finally:
        await auth_event_bus.unsubscribe(queue)


@router.get("/stream")
async def stream_auth_events(
    request: Request,
    token: str | None = Query(None, description="JWT access token for EventSource / SSE"),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """Native Server-Sent Events (SSE) endpoint broadcasting real-time auth events.

    Events: ``auth.login``, ``auth.logout``, ``auth.session_revoked``.

    Authentication:
    Accepts JWT access token via query parameter `?token=...` (EventSource standard) or
    `Authorization: Bearer <token>` header.

    Reconnection:
    Send `Last-Event-ID: <id>` to resume replay from the last received event id.
    """
    raw_token = token
    if not raw_token:
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            raw_token = auth_header[7:].strip()

    if not raw_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication token for SSE stream",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = await get_user_from_token_string(raw_token, db)

    return StreamingResponse(
        auth_event_generator(request, user),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )

