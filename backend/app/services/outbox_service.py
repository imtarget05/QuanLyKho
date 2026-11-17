"""Transactional Outbox Pattern & Consumer Deduplication Service (Milestone M3).

Implements PROJECT.md § Interface Contracts:
1. `emit_outbox_event`: Atomically persists OutboxEventRecord in the exact same DB transaction as business changes.
2. `drain_outbox_events`: Asynchronous drain worker polling pending events and dispatching to subscribers with retry threshold.
3. `process_event_with_deduplication`: Exactly-once consumer guarantee tracking processed events by consumer group.
4. Local in-memory pub/sub event bus supporting 100% offline self-contained local execution (R3).
"""

from __future__ import annotations

import json
import logging
import uuid
from collections.abc import Callable, Coroutine
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.outbox import OutboxEventRecord, ProcessedEventRecord

logger = logging.getLogger(__name__)

__all__ = [
    "clear_outbox_subscribers",
    "dispatch_to_local_subscribers",
    "drain_outbox_events",
    "emit_outbox_event",
    "process_event_with_deduplication",
    "register_outbox_subscriber",
]


# ============================================================================
# 1. LOCAL IN-MEMORY EVENT BUS (Offline/Local First)
# ============================================================================

_local_subscribers: dict[str, list[Callable[[OutboxEventRecord], Coroutine[Any, Any, bool]]]] = {}


def register_outbox_subscriber(
    topic: str,
    subscriber: Callable[[OutboxEventRecord], Coroutine[Any, Any, bool]],
) -> None:
    """Registers an async subscriber callback for a specific outbox topic (or '*' for all)."""
    if topic not in _local_subscribers:
        _local_subscribers[topic] = []
    _local_subscribers[topic].append(subscriber)


def clear_outbox_subscribers() -> None:
    """Clears all in-memory outbox subscribers."""
    _local_subscribers.clear()


async def dispatch_to_local_subscribers(event: OutboxEventRecord) -> bool:
    """Dispatches an event to all subscribers matching topic or wildcard '*'.

    Returns True if all subscribers succeeded, False if any failed.
    """
    subs = _local_subscribers.get(event.topic, []) + _local_subscribers.get("*", [])
    if not subs:
        return True  # No subscribers registered; marked published successfully

    all_ok = True
    for sub in subs:
        try:
            ok = await sub(event)
            if not ok:
                all_ok = False
        except Exception as exc:
            logger.warning("Subscriber for topic '%s' raised error: %s", event.topic, exc)
            all_ok = False
    return all_ok


# ============================================================================
# 2. ATOMIC OUTBOX EVENT EMISSION
# ============================================================================

async def emit_outbox_event(
    session: AsyncSession,
    topic: str,
    event_type: str,
    aggregate_id: str,
    payload: dict,
    trace_id: str,
) -> OutboxEventRecord:
    """Atomically writes an outbox event in the same DB transaction as business logic."""
    if not topic or not topic.strip():
        raise ValueError("Outbox topic cannot be empty.")
    if not event_type or not event_type.strip():
        raise ValueError("Outbox event_type cannot be empty.")

    payload_dict = payload if isinstance(payload, dict) else {}
    payload_str = json.dumps(payload, default=str) if isinstance(payload, (dict, list)) else str(payload)

    event_record = OutboxEventRecord(
        id=str(uuid.uuid4()),
        topic=topic.strip(),
        event_type=event_type.strip(),
        aggregate_id=str(aggregate_id),
        payload=payload_str,
        payload_json=payload_dict,
        trace_id=str(trace_id or uuid.uuid4()),
        status="PENDING",
        attempts=0,
        created_at=datetime.now(UTC),
    )
    session.add(event_record)
    await session.flush()
    return event_record


# ============================================================================
# 3. ASYNC OUTBOX DISPATCHER / DRAIN WORKER
# ============================================================================

async def drain_outbox_events(
    session: AsyncSession,
    limit: int = 100,
    subscriber_fn: Callable[[OutboxEventRecord], Coroutine[Any, Any, bool]] | None = None,
) -> list[OutboxEventRecord]:
    """Polls pending outbox events, invokes subscribers, and updates status accordingly."""
    res = await session.execute(
        select(OutboxEventRecord)
        .where(OutboxEventRecord.status == "PENDING")
        .order_by(OutboxEventRecord.created_at.asc())
        .limit(limit)
    )
    events = res.scalars().all()
    processed: list[OutboxEventRecord] = []

    for ev in events:
        ev.attempts += 1
        success = True
        if subscriber_fn:
            try:
                success = bool(await subscriber_fn(ev))
            except Exception as exc:
                logger.warning("Outbox subscriber failed on event %s: %s", ev.id, exc)
                success = False
        else:
            success = await dispatch_to_local_subscribers(ev)

        if success:
            ev.status = "PUBLISHED"
            ev.published_at = datetime.now(UTC)
        else:
            if ev.attempts >= 3:
                ev.status = "FAILED"
        processed.append(ev)

    await session.flush()
    return processed


# ============================================================================
# 4. CONSUMER DEDUPLICATION ENGINE (EXACTLY-ONCE)
# ============================================================================

async def process_event_with_deduplication(
    session: AsyncSession,
    event_id: str,
    consumer_group: str,
    handler: Callable[[dict], Coroutine[Any, Any, None]],
    payload: dict,
) -> bool:
    """Consumer deduplication: checks processed_events table before running handler.

    Returns True if event was newly processed, False if it was deduplicated (already processed).
    """
    res = await session.execute(
        select(ProcessedEventRecord).where(
            ProcessedEventRecord.event_id == str(event_id),
            ProcessedEventRecord.consumer_group == str(consumer_group),
        )
    )
    if res.scalars().first() is not None:
        return False  # Already processed (deduplicated)

    await handler(payload)

    proc_record = ProcessedEventRecord(
        event_id=str(event_id),
        consumer_group=str(consumer_group),
        processed_at=datetime.now(UTC),
    )
    session.add(proc_record)
    await session.flush()
    return True
