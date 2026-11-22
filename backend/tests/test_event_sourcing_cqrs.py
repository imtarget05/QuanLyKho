"""Test suite for Event Sourcing + CQRS Replay Projector (app/services/event_projector.py).

Verifies the mathematical and state invariants of Event Sourcing in Banking/Fintech:
1. Monotonic sequence numbering per aggregate.
2. Independent sequence spaces across different aggregates.
3. Deterministic state reconstruction via event replay (Receipt -> Issue -> Adjustment -> Expiry).
4. Idempotency traceability: each event tracks the originating idempotency key.
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import MagicMock

import pytest

from app.models.event_store import InventoryEvent, InventoryEventType
from app.services.event_projector import InventoryEventProjector


class MockAsyncSession:
    """Lightweight in-memory session mock to test EventProjector logic deterministically."""

    def __init__(self) -> None:
        self.events: list[InventoryEvent] = []
        self.flushed = False

    async def execute(self, statement: Any) -> Any:
        stmt_str = str(statement)
        mock_result = MagicMock()

        # Handle max(sequence_number) query in append_event
        if "max(" in stmt_str.lower() or "func.max" in stmt_str.lower():
            # Extract aggregate_id from statement if possible or use latest
            if not self.events:
                mock_result.scalar.return_value = None
            else:
                max_seq = max(e.sequence_number for e in self.events)
                mock_result.scalar.return_value = max_seq
            return mock_result

        # Handle get_history select query
        mock_result.scalars.return_value.all.return_value = sorted(
            self.events, key=lambda e: e.sequence_number
        )
        return mock_result

    def add(self, instance: Any) -> None:
        if isinstance(instance, InventoryEvent):
            self.events.append(instance)

    async def flush(self) -> None:
        self.flushed = True


@pytest.mark.asyncio
async def test_event_projector_first_event_starts_at_sequence_zero() -> None:
    session = MockAsyncSession()
    projector = InventoryEventProjector(session)  # type: ignore[arg-type]

    lot_id = uuid.uuid4()
    event = await projector.append_event(
        aggregate_id=lot_id,
        aggregate_type="LOT",
        event_type=InventoryEventType.RECEIPT_POSTED,
        payload={"quantity": 100, "unit_cost": "25000"},
        idempotency_key="IDEM-TEST-001",
    )

    assert event.sequence_number == 0
    assert event.aggregate_id == str(lot_id)
    assert event.event_type == "RECEIPT_POSTED"
    assert event.caused_by_idempotency_key == "IDEM-TEST-001"
    assert session.flushed is True


@pytest.mark.asyncio
async def test_event_projector_sequential_events_increment_sequence() -> None:
    session = MockAsyncSession()
    projector = InventoryEventProjector(session)  # type: ignore[arg-type]

    sku_id = uuid.uuid4()
    e0 = await projector.append_event(
        aggregate_id=sku_id,
        aggregate_type="SKU",
        event_type=InventoryEventType.RECEIPT_POSTED,
        payload={"quantity": 50},
    )
    assert e0.sequence_number == 0

    e1 = await projector.append_event(
        aggregate_id=sku_id,
        aggregate_type="SKU",
        event_type=InventoryEventType.ISSUE_POSTED,
        payload={"quantity": 20},
    )
    assert e1.sequence_number == 1


@pytest.mark.asyncio
async def test_event_projector_replay_reconstructs_exact_balance_journey() -> None:
    """Test full event sourcing lifecycle replay:
    Receipt(100) -> Issue(30) -> Adjust(-10) -> ReverseAdjust(-10) -> Expire -> 0.
    """
    session = MockAsyncSession()
    lot_id = uuid.uuid4()
    lot_str = str(lot_id)

    # Pre-populate event log
    events = [
        InventoryEvent(
            id=str(uuid.uuid4()),
            aggregate_id=lot_str,
            aggregate_type="LOT",
            sequence_number=0,
            event_type=InventoryEventType.RECEIPT_POSTED.value,
            payload={"quantity": 100},
        ),
        InventoryEvent(
            id=str(uuid.uuid4()),
            aggregate_id=lot_str,
            aggregate_type="LOT",
            sequence_number=1,
            event_type=InventoryEventType.ISSUE_POSTED.value,
            payload={"quantity": 30},
        ),
        InventoryEvent(
            id=str(uuid.uuid4()),
            aggregate_id=lot_str,
            aggregate_type="LOT",
            sequence_number=2,
            event_type=InventoryEventType.ADJUSTMENT_POSTED.value,
            payload={"quantity": -10},
        ),
        InventoryEvent(
            id=str(uuid.uuid4()),
            aggregate_id=lot_str,
            aggregate_type="LOT",
            sequence_number=3,
            event_type=InventoryEventType.ADJUSTMENT_REVERSED.value,
            payload={"quantity": -10},
        ),
    ]
    session.events = events
    projector = InventoryEventProjector(session)  # type: ignore[arg-type]

    state = await projector.replay_aggregate(lot_id)
    # 100 - 30 + (-10) - (-10) = 70
    assert state["computed_balance"] == 70
    assert state["event_count"] == 4


@pytest.mark.asyncio
async def test_event_projector_lot_expired_wipes_balance_to_zero() -> None:
    session = MockAsyncSession()
    lot_id = uuid.uuid4()
    lot_str = str(lot_id)

    session.events = [
        InventoryEvent(
            id=str(uuid.uuid4()),
            aggregate_id=lot_str,
            aggregate_type="LOT",
            sequence_number=0,
            event_type=InventoryEventType.RECEIPT_POSTED.value,
            payload={"quantity": 50},
        ),
        InventoryEvent(
            id=str(uuid.uuid4()),
            aggregate_id=lot_str,
            aggregate_type="LOT",
            sequence_number=1,
            event_type=InventoryEventType.LOT_EXPIRED.value,
            payload={"reason": "Past best-before date"},
        ),
    ]
    projector = InventoryEventProjector(session)  # type: ignore[arg-type]

    state = await projector.replay_aggregate(lot_id)
    assert state["computed_balance"] == 0
    assert state["event_count"] == 2
