"""SSE events channel — real-time auth stream (login / logout / session revoked).

Mounted at root (`GET /events/stream`) and under `/api/v1` (`GET /api/v1/events/stream`)
by ``app/main.py``.

Authentication: Bearer token via `?token=` query param (EventSource standard) or
`Authorization: Bearer <token>` header.

Reconnection/replay: the `Last-Event-ID` header resumes delivery from the last
received event id using the bus's in-memory ring buffer.
"""

import asyncio
import json
from collections.abc import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes.auth_utils import get_user_from_token_string
from app.database import get_db
from app.models.iam import User
from app.services.auth_events import auth_event_bus

router = APIRouter()

_AUTH_EVENTS = ("auth.login", "auth.logout", "auth.session_revoked")


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

