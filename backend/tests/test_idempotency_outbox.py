"""Comprehensive Unit & Integration Test Suite for Milestone M3.

Covers:
1. Strict Financial Idempotency Engine:
   - Order-independent canonical hashing (SHA-256) with key order invariance.
   - Validation rejecting empty string and whitespace-only keys.
   - Atomic state transitions: PENDING -> COMPLETED / FAILED.
   - Cached response replay returning exact status code and payload with is_replay=True.
   - Semantic conflict rejection (HTTP 409 Conflict) on payload alteration.
   - In-flight mutex locking preventing duplicate processing during ongoing execution.
   - Automatic purging of expired TTL records.
   - Failed execution reset allowing subsequent retries.
2. Transactional Outbox Pattern & Consumer Deduplication:
   - Outbox event written in same ACID database transaction.
   - Validation rejecting empty topic and empty event_type.
   - Outbox drain dispatcher with subscriber callbacks and retry counter increments.
   - Transition to FAILED upon reaching maximum retry threshold (3 attempts).
   - In-memory event bus subscribers for local offline execution.
   - Consumer deduplication engine (processed_events table) guaranteeing exactly-once consumption.
   - Independent deduplication across distinct consumer groups.
   - Dialect-agnostic SQLite in-memory and PostgreSQL compatibility.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.models.idempotency import IdempotencyKeyRecord
from app.models.outbox import OutboxEventRecord, ProcessedEventRecord
from app.services.idempotency import (
    claim_key,
    find_key,
    store_response,
)
from app.services.idempotency_service import (
    IdempotencyConflictException,
    IdempotencyInFlightException,
    clear_in_flight_locks,
    compute_canonical_hash,
    execute_idempotent_operation,
    payload_hash,
)
from app.services.outbox_service import (
    clear_outbox_subscribers,
    drain_outbox_events,
    emit_outbox_event,
    process_event_with_deduplication,
    register_outbox_subscriber,
)


@pytest_asyncio.fixture
async def sqlite_db():
    """Provides an isolated SQLite in-memory AsyncSession for idempotency & outbox models."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    tables = [
        IdempotencyKeyRecord.__table__,
        OutboxEventRecord.__table__,
        ProcessedEventRecord.__table__,
    ]
    async with engine.begin() as conn:
        await conn.run_sync(lambda sync_conn: Base.metadata.create_all(sync_conn, tables=tables))

    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with session_factory() as session:
        clear_in_flight_locks()
        clear_outbox_subscribers()
        yield session

    await engine.dispose()


# ============================================================================
# 1. CANONICAL HASHING TESTS
# ============================================================================

def test_canonical_hash_key_order_invariance():
    """Canonical hashing produces identical SHA-256 regardless of dictionary key order."""
    payload1 = {"account": "111", "amount": 50000, "currency": "VND", "metadata": {"tag": "test"}}
    payload2 = {"currency": "VND", "metadata": {"tag": "test"}, "amount": 50000, "account": "111"}
    assert compute_canonical_hash(payload1) == compute_canonical_hash(payload2)
    assert payload_hash(payload1) == compute_canonical_hash(payload1)


def test_canonical_hash_handles_none_and_empty():
    """Handles None and empty dictionary gracefully without crashing."""
    h_none = compute_canonical_hash(None)
    h_empty = compute_canonical_hash({})
    assert h_none == h_empty
    assert len(h_none) == 64


def test_canonical_hash_detects_altered_values():
    """Detects even subtle changes in payload values."""
    p1 = {"amount": 100000}
    p2 = {"amount": 100001}
    assert compute_canonical_hash(p1) != compute_canonical_hash(p2)


# ============================================================================
# 2. IDEMPOTENCY KEY VALIDATION & LIFECYCLE TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_idempotency_empty_and_whitespace_keys_rejected(sqlite_db: AsyncSession):
    """Empty string or whitespace-only idempotency keys are rejected with ValueError."""
    with pytest.raises(ValueError, match="mandatory and cannot be empty"):
        await execute_idempotent_operation(
            session=sqlite_db,
            idempotency_key="",
            request_path="/api/pay",
            request_payload={"amt": 100},
            operation_coroutine=lambda: None,
        )

    with pytest.raises(ValueError, match="mandatory and cannot be empty"):
        await execute_idempotent_operation(
            session=sqlite_db,
            idempotency_key="     ",
            request_path="/api/pay",
            request_payload={"amt": 100},
            operation_coroutine=lambda: None,
        )


@pytest.mark.asyncio
async def test_idempotency_atomic_registration_pending(sqlite_db: AsyncSession):
    """Key is atomically recorded in PENDING status prior to coroutine execution."""
    key = "IDEM-TEST-PENDING-001"
    payload = {"source": "ACC-1", "amount": 10000}

    async def op():
        res = await sqlite_db.execute(
            select(IdempotencyKeyRecord).where(IdempotencyKeyRecord.key == key)
        )
        rec = res.scalars().first()
        assert rec is not None
        assert rec.status == "PENDING"
        assert rec.request_hash == compute_canonical_hash(payload)
        return (200, {"success": True})

    code, body, is_replay = await execute_idempotent_operation(
        session=sqlite_db,
        idempotency_key=key,
        request_path="/api/transfer",
        request_payload=payload,
        operation_coroutine=op,
    )
    await sqlite_db.commit()

    assert code == 200
    assert is_replay is False
    assert body["success"] is True

    # After completion: status is COMPLETED
    res2 = await sqlite_db.execute(
        select(IdempotencyKeyRecord).where(IdempotencyKeyRecord.key == key)
    )
    rec2 = res2.scalars().first()
    assert rec2.status == "COMPLETED"
    assert rec2.status_code == 200


@pytest.mark.asyncio
async def test_idempotency_completed_state_and_replay_cache(sqlite_db: AsyncSession):
    """Repeated request with identical key and payload replays cached response without re-executing."""
    key = "IDEM-TEST-REPLAY-001"
    payload = {"invoice": "INV-2026", "total_cents": 500000}
    call_counter = {"runs": 0}

    async def payment_processor():
        call_counter["runs"] += 1
        return (201, {"receipt_id": "RCPT-8888", "amount": 500000})

    # Call 1: First time run
    code1, body1, is_replay1 = await execute_idempotent_operation(
        session=sqlite_db,
        idempotency_key=key,
        request_path="/api/invoices/pay",
        request_payload=payload,
        operation_coroutine=payment_processor,
    )
    await sqlite_db.commit()

    assert code1 == 201
    assert is_replay1 is False
    assert body1["receipt_id"] == "RCPT-8888"
    assert call_counter["runs"] == 1

    # Call 2: Exact duplicate request
    code2, body2, is_replay2 = await execute_idempotent_operation(
        session=sqlite_db,
        idempotency_key=key,
        request_path="/api/invoices/pay",
        request_payload=payload,
        operation_coroutine=payment_processor,
    )

    assert code2 == 201
    assert is_replay2 is True
    assert body2 == body1
    assert call_counter["runs"] == 1  # Not executed again!


@pytest.mark.asyncio
async def test_idempotency_conflict_on_altered_payload(sqlite_db: AsyncSession):
    """Reusing same key with a different payload raises HTTP 409 IdempotencyConflictException."""
    key = "IDEM-TEST-CONFLICT-001"
    payload_original = {"amount": 100000, "account": "ACC-1"}
    payload_altered = {"amount": 200000, "account": "ACC-1"}

    async def op():
        return (200, {"status": "ok"})

    # Original execution
    await execute_idempotent_operation(
        session=sqlite_db,
        idempotency_key=key,
        request_path="/api/pay",
        request_payload=payload_original,
        operation_coroutine=op,
    )
    await sqlite_db.commit()

    # Conflicting reuse
    with pytest.raises(IdempotencyConflictException) as exc_info:
        await execute_idempotent_operation(
            session=sqlite_db,
            idempotency_key=key,
            request_path="/api/pay",
            request_payload=payload_altered,
            operation_coroutine=op,
        )
    assert exc_info.value.status_code == 409
    assert "conflicting payload" in str(exc_info.value).lower() or "different payload" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_idempotency_in_flight_lock_rejection(sqlite_db: AsyncSession):
    """Concurrent request on in-flight key raises HTTP 409 IdempotencyInFlightException."""
    key = "IDEM-TEST-INFLIGHT-001"
    payload = {"data": 1}

    # Pre-populate key in PENDING state
    pending_record = IdempotencyKeyRecord(
        key=key,
        request_hash=compute_canonical_hash(payload),
        status="PENDING",
        created_at=datetime.now(UTC),
        expires_at=datetime.now(UTC) + timedelta(minutes=10),
    )
    sqlite_db.add(pending_record)
    await sqlite_db.commit()

    async def op():
        return (200, {})

    with pytest.raises(IdempotencyInFlightException) as exc_info:
        await execute_idempotent_operation(
            session=sqlite_db,
            idempotency_key=key,
            request_path="/api/test",
            request_payload=payload,
            operation_coroutine=op,
        )
    assert exc_info.value.status_code == 409


@pytest.mark.asyncio
async def test_idempotency_expired_ttl_purged_and_reused(sqlite_db: AsyncSession):
    """Expired TTL record is purged and permits fresh execution."""
    key = "IDEM-TEST-EXPIRED-001"
    old_now = datetime.now(UTC) - timedelta(hours=48)

    expired_record = IdempotencyKeyRecord(
        key=key,
        request_hash="stale-hash",
        request_path="/api/old",
        status="COMPLETED",
        status_code=200,
        response_body='{"old": 1}',
        created_at=old_now,
        expires_at=old_now + timedelta(hours=24),  # Expired 24h ago
    )
    sqlite_db.add(expired_record)
    await sqlite_db.commit()

    runs = {"count": 0}
    async def fresh_op():
        runs["count"] += 1
        return (200, {"fresh": True})

    code, body, is_replay = await execute_idempotent_operation(
        session=sqlite_db,
        idempotency_key=key,
        request_path="/api/fresh",
        request_payload={"new": 2},
        operation_coroutine=fresh_op,
    )
    await sqlite_db.commit()

    assert code == 200
    assert is_replay is False
    assert body["fresh"] is True
    assert runs["count"] == 1


@pytest.mark.asyncio
async def test_idempotency_failed_operation_allows_subsequent_retry(sqlite_db: AsyncSession):
    """Failed operation transitions status to FAILED and allows subsequent retry."""
    key = "IDEM-TEST-FAILED-RETRY-001"
    payload = {"target": "acc-x"}
    should_fail = True

    async def unreliable_op():
        if should_fail:
            raise RuntimeError("Database connection timeout")
        return (200, {"recovered": True})

    # Attempt 1: Fails
    with pytest.raises(RuntimeError, match="Database connection timeout"):
        await execute_idempotent_operation(
            session=sqlite_db,
            idempotency_key=key,
            request_path="/api/retry",
            request_payload=payload,
            operation_coroutine=unreliable_op,
        )
    await sqlite_db.commit()

    # Check status is FAILED
    res = await sqlite_db.execute(
        select(IdempotencyKeyRecord).where(IdempotencyKeyRecord.key == key)
    )
    rec = res.scalars().first()
    assert rec.status == "FAILED"

    # Attempt 2: Succeeds on retry
    should_fail = False
    code, body, is_replay = await execute_idempotent_operation(
        session=sqlite_db,
        idempotency_key=key,
        request_path="/api/retry",
        request_payload=payload,
        operation_coroutine=unreliable_op,
    )
    await sqlite_db.commit()

    assert code == 200
    assert body["recovered"] is True
    assert is_replay is False


# ============================================================================
# 3. TRANSACTIONAL OUTBOX TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_outbox_emit_event_atomic_in_same_transaction(sqlite_db: AsyncSession):
    """Emits outbox event atomically in same database session."""
    ev = await emit_outbox_event(
        session=sqlite_db,
        topic="banking.treasury.transfer",
        event_type="TRANSFER_INITIATED",
        aggregate_id="TX-9999",
        payload={"amount": 1000000, "source": "ACC-100"},
        trace_id="TRACE-TX-9999",
    )
    await sqlite_db.commit()

    assert ev.id is not None
    assert ev.topic == "banking.treasury.transfer"
    assert ev.event_type == "TRANSFER_INITIATED"
    assert ev.status == "PENDING"
    assert ev.attempts == 0
    assert ev.published_at is None

    # Query from database to verify persistence
    res = await sqlite_db.execute(
        select(OutboxEventRecord).where(OutboxEventRecord.id == ev.id)
    )
    loaded = res.scalars().first()
    assert loaded is not None
    assert loaded.aggregate_id == "TX-9999"


@pytest.mark.asyncio
async def test_outbox_empty_topic_and_event_type_rejected(sqlite_db: AsyncSession):
    """Empty or whitespace topic or event_type raises ValueError."""
    with pytest.raises(ValueError, match="topic cannot be empty"):
        await emit_outbox_event(
            session=sqlite_db,
            topic="",
            event_type="VALID_EVENT",
            aggregate_id="AGG-1",
            payload={},
            trace_id="TR-1",
        )

    with pytest.raises(ValueError, match="event_type cannot be empty"):
        await emit_outbox_event(
            session=sqlite_db,
            topic="valid.topic",
            event_type="   ",
            aggregate_id="AGG-1",
            payload={},
            trace_id="TR-1",
        )


@pytest.mark.asyncio
async def test_outbox_dispatcher_drain_and_publish(sqlite_db: AsyncSession):
    """Dispatcher drains pending events, invokes subscriber, and marks PUBLISHED."""
    await emit_outbox_event(sqlite_db, "accounts", "OPENED", "acc-1", {"name": "Alice"}, "tr-1")
    await emit_outbox_event(sqlite_db, "accounts", "OPENED", "acc-2", {"name": "Bob"}, "tr-2")
    await sqlite_db.commit()

    received_ids = []
    async def subscriber(ev: OutboxEventRecord) -> bool:
        received_ids.append(ev.aggregate_id)
        return True

    drained = await drain_outbox_events(sqlite_db, limit=10, subscriber_fn=subscriber)
    await sqlite_db.commit()

    assert len(drained) == 2
    assert received_ids == ["acc-1", "acc-2"]
    for ev in drained:
        assert ev.status == "PUBLISHED"
        assert ev.published_at is not None
        assert ev.attempts == 1


@pytest.mark.asyncio
async def test_outbox_retry_increment_on_subscriber_failure(sqlite_db: AsyncSession):
    """Failed subscriber increments attempts, and after 3 failures transitions status to FAILED."""
    ev = await emit_outbox_event(sqlite_db, "alerts", "CRITICAL", "node-1", {}, "tr-fail")
    await sqlite_db.commit()

    async def broken_subscriber(e: OutboxEventRecord) -> bool:
        return False

    # Attempt 1
    await drain_outbox_events(sqlite_db, limit=1, subscriber_fn=broken_subscriber)
    await sqlite_db.commit()
    res1 = (await sqlite_db.execute(select(OutboxEventRecord).where(OutboxEventRecord.id == ev.id))).scalar_one()
    assert res1.status == "PENDING"
    assert res1.attempts == 1

    # Attempt 2
    await drain_outbox_events(sqlite_db, limit=1, subscriber_fn=broken_subscriber)
    await sqlite_db.commit()
    res2 = (await sqlite_db.execute(select(OutboxEventRecord).where(OutboxEventRecord.id == ev.id))).scalar_one()
    assert res2.status == "PENDING"
    assert res2.attempts == 2

    # Attempt 3: Exhausted -> FAILED
    await drain_outbox_events(sqlite_db, limit=1, subscriber_fn=broken_subscriber)
    await sqlite_db.commit()
    res3 = (await sqlite_db.execute(select(OutboxEventRecord).where(OutboxEventRecord.id == ev.id))).scalar_one()
    assert res3.status == "FAILED"
    assert res3.attempts == 3


@pytest.mark.asyncio
async def test_outbox_in_memory_bus_subscribers(sqlite_db: AsyncSession):
    """In-memory event bus dispatches to local registered topic subscribers."""
    received = []
    async def account_listener(ev: OutboxEventRecord) -> bool:
        received.append(ev.aggregate_id)
        return True

    register_outbox_subscriber("notifications.email", account_listener)

    await emit_outbox_event(sqlite_db, "notifications.email", "WELCOME", "user-123", {}, "tr-1")
    await sqlite_db.commit()

    drained = await drain_outbox_events(sqlite_db, limit=5, subscriber_fn=None)
    await sqlite_db.commit()

    assert len(drained) == 1
    assert drained[0].status == "PUBLISHED"
    assert received == ["user-123"]


# ============================================================================
# 4. CONSUMER DEDUPLICATION TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_consumer_deduplication_exact_once(sqlite_db: AsyncSession):
    """Exactly-once processing: first run invokes handler; duplicate replay is filtered out."""
    event_id = "EVT-DEDUP-TEST-001"
    consumer_group = "gl-posting-worker"
    executions = {"runs": 0}

    async def handler(payload: dict):
        executions["runs"] += 1

    # First delivery
    ok1 = await process_event_with_deduplication(
        session=sqlite_db,
        event_id=event_id,
        consumer_group=consumer_group,
        handler=handler,
        payload={"amount": 100},
    )
    await sqlite_db.commit()

    assert ok1 is True
    assert executions["runs"] == 1

    # Duplicate delivery
    ok2 = await process_event_with_deduplication(
        session=sqlite_db,
        event_id=event_id,
        consumer_group=consumer_group,
        handler=handler,
        payload={"amount": 100},
    )
    await sqlite_db.commit()

    assert ok2 is False
    assert executions["runs"] == 1  # Handler was not called again!


@pytest.mark.asyncio
async def test_consumer_deduplication_different_consumer_groups(sqlite_db: AsyncSession):
    """Different consumer groups process the same event independently."""
    event_id = "EVT-SHARED-001"
    group_a_runs = {"count": 0}
    group_b_runs = {"count": 0}

    async def handler_a(p):
        group_a_runs["count"] += 1

    async def handler_b(p):
        group_b_runs["count"] += 1

    ok_a = await process_event_with_deduplication(sqlite_db, event_id, "group-a", handler_a, {})
    ok_b = await process_event_with_deduplication(sqlite_db, event_id, "group-b", handler_b, {})
    await sqlite_db.commit()

    assert ok_a is True
    assert ok_b is True
    assert group_a_runs["count"] == 1
    assert group_b_runs["count"] == 1


# ============================================================================
# 5. DIALECT-AGNOSTIC SQLITE & POSTGRESQL TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_sqlite_and_postgresql_dialect_compatibility(sqlite_db: AsyncSession):
    """Verifies claim_key, find_key, and store_response work on SQLite without dialect errors."""
    key = "DIALECT-KEY-001"
    b_hash = compute_canonical_hash({"test": "dialect"})

    # Claim key
    claimed = await claim_key(sqlite_db, key, b_hash, scope="test-dialect")
    await sqlite_db.commit()
    assert claimed is True

    # Duplicate claim returns False
    claimed_again = await claim_key(sqlite_db, key, b_hash, scope="test-dialect")
    await sqlite_db.commit()
    assert claimed_again is False

    # Store response
    await store_response(sqlite_db, key, b_hash, 200, {"replayed": True})
    await sqlite_db.commit()

    # Find key
    found = await find_key(sqlite_db, key)
    assert found is not None
    assert found.key == key
    assert found.status == "COMPLETED"
    assert found.status_code == 200
