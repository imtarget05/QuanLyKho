"""Subscription resolvers for GraphQL banking & inventory domain.

Hiện tại hỗ trợ placeholder cho real-time saga status và new outbox event.
Ariadne subscription cần AsyncGenerator; triển khai đầy đủ sau khi có Event Bus.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any
from uuid import UUID


async def resolve_saga_status(
    _, info, sagaId: UUID
) -> AsyncGenerator[dict[str, Any], None]:
    """Theo dõi trạng thái saga theo ID (placeholder)."""
    yield {
        "id": str(sagaId),
        "sagaName": "",
        "sagaType": None,
        "status": "PENDING",
        "currentStep": None,
        "errorMessage": None,
        "createdAt": None,
        "updatedAt": None,
        "steps": [],
    }


async def resolve_new_outbox_event(
    _, info
) -> AsyncGenerator[dict[str, Any], None]:
    """Theo dõi sự kiện outbox mới (placeholder)."""
    yield {
        "id": "",
        "topic": "",
        "eventType": "",
        "aggregateId": "",
        "payload": "",
        "traceId": "",
        "status": "PENDING",
        "attempts": 0,
        "createdAt": None,
        "publishedAt": None,
    }


subscription_resolvers = {
    "sagaStatus": resolve_saga_status,
    "newOutboxEvent": resolve_new_outbox_event,
}