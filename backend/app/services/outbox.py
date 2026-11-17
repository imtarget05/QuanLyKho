"""Alias shim for outbox_service matching naming convention."""

from app.services.outbox_service import (
    clear_outbox_subscribers,
    dispatch_to_local_subscribers,
    drain_outbox_events,
    emit_outbox_event,
    process_event_with_deduplication,
    register_outbox_subscriber,
)

__all__ = [
    "clear_outbox_subscribers",
    "dispatch_to_local_subscribers",
    "drain_outbox_events",
    "emit_outbox_event",
    "process_event_with_deduplication",
    "register_outbox_subscriber",
]
