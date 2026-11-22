"""Event Projector service: append + replay for Inventory Event Sourcing.

CQRS write-side: append_event (command)
CQRS read-side:  replay_aggregate, get_history (query)

Thread-safety: append_event uses SELECT MAX(...) FOR UPDATE to serialise
concurrent writers on the same aggregate within a PostgreSQL transaction.
In SQLite (test mode) the FOR UPDATE hint is silently ignored; SQLite's
file-level locking and StaticPool provide adequate isolation for unit tests.
"""

from __future__ import annotations

import uuid
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.event_store import InventoryEvent, InventoryEventType


class InventoryEventProjector:
    """Append events to and replay state from the inventory event store."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ------------------------------------------------------------------
    # Write side (Command)
    # ------------------------------------------------------------------

    async def append_event(
        self,
        aggregate_id: UUID | str,
        aggregate_type: str,
        event_type: str | InventoryEventType,
        payload: dict,
        idempotency_key: str | None = None,
    ) -> InventoryEvent:
        """Append a new event for the given aggregate.

        Acquires a row-level lock (FOR UPDATE) on the MAX sequence query to
        prevent duplicate sequence numbers under concurrent writers.

        Returns the newly created InventoryEvent (flushed but not committed).
        """
        aggregate_id_str = str(aggregate_id)
        event_type_str = str(event_type.value if isinstance(event_type, InventoryEventType) else event_type)

        # SELECT MAX(sequence_number) FOR UPDATE — serialises concurrent inserts
        # Note: FOR UPDATE is a no-op in SQLite but harmless.
        result = await self._session.execute(
            select(func.max(InventoryEvent.sequence_number))
            .where(InventoryEvent.aggregate_id == aggregate_id_str)
            .with_for_update()
        )
        current_max = result.scalar()  # None if no events yet
        next_seq = 0 if current_max is None else current_max + 1

        event = InventoryEvent(
            id=str(uuid.uuid4()),
            aggregate_id=aggregate_id_str,
            aggregate_type=aggregate_type,
            sequence_number=next_seq,
            event_type=event_type_str,
            payload=payload,
            caused_by_idempotency_key=idempotency_key,
        )
        self._session.add(event)
        await self._session.flush()
        return event

    # ------------------------------------------------------------------
    # Read side (Query)
    # ------------------------------------------------------------------

    async def get_history(self, aggregate_id: UUID | str) -> list[InventoryEvent]:
        """Return all events for an aggregate, ordered by sequence_number."""
        aggregate_id_str = str(aggregate_id)
        result = await self._session.execute(
            select(InventoryEvent)
            .where(InventoryEvent.aggregate_id == aggregate_id_str)
            .order_by(InventoryEvent.sequence_number)
        )
        return list(result.scalars().all())

    async def replay_aggregate(self, aggregate_id: UUID | str) -> dict:
        """Replay all events to compute the current balance for an aggregate.

        Balance rules:
          - RECEIPT_POSTED:     balance += payload["quantity"]
          - ISSUE_POSTED:       balance -= payload["quantity"]
          - ADJUSTMENT_POSTED:  balance += payload["quantity"]  (signed delta)
          - ADJUSTMENT_REVERSED: balance -= payload["quantity"]
          - LOT_EXPIRED:        balance = 0  (lot is wiped)

        Returns:
            {
                "aggregate_id": str,
                "computed_balance": int,
                "event_count": int,
            }
        """
        events = await self.get_history(aggregate_id)
        balance = 0
        for event in events:
            qty = int(event.payload.get("quantity", 0))
            et = event.event_type
            if et == InventoryEventType.RECEIPT_POSTED or et == InventoryEventType.RECEIPT_POSTED.value:
                balance += qty
            elif et == InventoryEventType.ISSUE_POSTED or et == InventoryEventType.ISSUE_POSTED.value:
                balance -= qty
            elif et == InventoryEventType.ADJUSTMENT_POSTED or et == InventoryEventType.ADJUSTMENT_POSTED.value:
                balance += qty
            elif et == InventoryEventType.ADJUSTMENT_REVERSED or et == InventoryEventType.ADJUSTMENT_REVERSED.value:
                balance -= qty
            elif et == InventoryEventType.LOT_EXPIRED or et == InventoryEventType.LOT_EXPIRED.value:
                balance = 0

        return {
            "aggregate_id": str(aggregate_id),
            "computed_balance": balance,
            "event_count": len(events),
        }
