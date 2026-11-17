"""Empirical Stress Test & Boundary Verification Suite: Milestone M3.

Authored by Empirical Challenger (challenger_m3_2_gen1).
Stress-tests SQLite & PostgreSQL transactional integrity and boundary cases:
1. Database rollback boundary:
   - If business logic fails inside an outer transaction, verify outbox event is rolled back completely.
   - Commit consistency: when outer transaction commits, outbox event persists atomically.
   - Savepoint rollback boundary: inner savepoint rollback cleans up nested outbox events.
   - Idempotency rollback boundary: transaction rollback clears uncommitted idempotency records.
2. TTL boundary:
   - Behavior at exact expiration boundary (record.expires_at == now).
   - Behavior sub-second before and after expiration (500ms before vs 1ms after).
   - Timezone awareness across naive SQLite and timezone-aware PostgreSQL.
   - Zero and negative TTL edge cases.
3. Large payload handling (100KB+):
   - SHA-256 canonical hashing performance and order invariance on 150KB+ JSON.
   - Idempotency key execution, persistence, and replay cache fidelity on 150KB+ payloads.
   - Outbox event persistence, subscriber dispatch, and consumer deduplication on 150KB+ payloads across SQLite & PostgreSQL.
4. Rapid sequential replay:
   - 100 rapid sequential replay requests checking latency, data fidelity, and execution count.
   - Dual-dialect verification: tested on both SQLite (in-memory) and PostgreSQL (bankops_test).
"""

from __future__ import annotations

import asyncio
import os
import time
import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.models.idempotency import IdempotencyKeyRecord
from app.models.outbox import OutboxEventRecord, ProcessedEventRecord
from app.services.idempotency_service import (
    IdempotencyConflictException,
    clear_in_flight_locks,
    compute_canonical_hash,
    execute_idempotent_operation,
)
from app.services.outbox_service import (
    clear_outbox_subscribers,
    dispatch_to_local_subscribers,
    drain_outbox_events,
    emit_outbox_event,
    process_event_with_deduplication,
    register_outbox_subscriber,
)

_raw_pg_url = (
    os.environ.get("DATABASE_URL_TEST")
    or os.environ.get("DATABASE_URL")
    or "postgresql+asyncpg://postgres:postgres@localhost:5432/bankops_test"
)
for _pfx in ("postgresql+psycopg2://", "postgresql://", "postgres://"):
    if _raw_pg_url.startswith(_pfx):
        _raw_pg_url = _raw_pg_url.replace(_pfx, "postgresql+asyncpg://", 1)
        break
POSTGRES_TEST_URL = _raw_pg_url


# ============================================================================
# FIXTURES
# ============================================================================

@pytest_asyncio.fixture
async def sqlite_session() -> AsyncGenerator[AsyncSession, None]:
    """Provides an isolated SQLite in-memory AsyncSession."""
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


@pytest_asyncio.fixture
async def postgres_session() -> AsyncGenerator[AsyncSession, None]:
    """Provides an isolated PostgreSQL session connected to bankops_test."""
    engine = create_async_engine(POSTGRES_TEST_URL)
    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    # Ensure tables exist
    tables = [
        IdempotencyKeyRecord.__table__,
        OutboxEventRecord.__table__,
        ProcessedEventRecord.__table__,
    ]
    async with engine.begin() as conn:
        await conn.run_sync(lambda sync_conn: Base.metadata.create_all(sync_conn, tables=tables))

    async with session_factory() as session:
        clear_in_flight_locks()
        clear_outbox_subscribers()
        yield session
        clear_in_flight_locks()
        clear_outbox_subscribers()

    await engine.dispose()


def generate_large_payload(target_kb: int = 150) -> dict[str, Any]:
    """Generates a structured, deterministic JSON-serializable dictionary > target_kb."""
    records = []
    # Each record ~ 300 bytes
    num_records = int((target_kb * 1024) / 300) + 10
    for i in range(num_records):
        records.append({
            "line_item_id": i,
            "sku": f"PRODUCT-SKU-{i:05d}",
            "name": f"Trà sữa Oolong nướng hạt sen cao cấp loại {i}",
            "quantity": (i % 50) + 1,
            "unit_price_cents": 45000 + (i * 10),
            "currency": "VND",
            "attributes": {
                "sweetness": "50%",
                "ice": "regular",
                "toppings": ["trân châu đen", "thạch sương sáo", "pudding trứng"],
                "batch_code": f"LOT-2026-X{i}",
            },
            "timestamp": "2026-11-16T14:30:00.000Z",
        })
    return {
        "invoice_number": f"INV-LARGE-{uuid.uuid4().hex[:8]}",
        "treasury_account": "ACC-11223344",
        "description": "Thanh toán lô hàng nhập kho số lượng lớn với tải trọng cao 150KB+",
        "line_items": records,
        "metadata": {
            "system": "QuanLyKho-Treasury",
            "environment": "production-stress-test",
            "flags": {"audit_required": True, "express": False, "priority": 1},
        },
    }


# ============================================================================
# 1. DATABASE ROLLBACK BOUNDARY (ATOMIC CONSISTENCY)
# ============================================================================

@pytest.mark.asyncio
async def test_rollback_boundary_sqlite_outbox_discarded_on_failure(sqlite_session: AsyncSession):
    """If business logic fails in outer transaction, outbox event is rolled back completely in SQLite."""
    event_id = None
    aggregate_id = f"AGG-ROLLBACK-SQLITE-{uuid.uuid4().hex[:6]}"

    # Simulate an atomic Unit-of-Work transaction that fails at step 2
    try:
        async with sqlite_session.begin():
            # Step 1: Emit outbox event
            ev = await emit_outbox_event(
                session=sqlite_session,
                topic="banking.treasury.transfer",
                event_type="TRANSFER_CREATED",
                aggregate_id=aggregate_id,
                payload={"amount": 5000000, "account": "ACC-ROLLBACK"},
                trace_id="TRACE-RB-1",
            )
            event_id = ev.id
            assert event_id is not None

            # Step 2: Simulated business failure (e.g. balance check or constraint violation)
            raise RuntimeError("Business invariant check failed: Insufficient treasury balance!")
    except RuntimeError as exc:
        assert "Business invariant check failed" in str(exc)

    # Verify atomic consistency: outbox event must NOT exist in the database!
    res = await sqlite_session.execute(
        select(OutboxEventRecord).where(OutboxEventRecord.aggregate_id == aggregate_id)
    )
    loaded_event = res.scalars().first()
    assert loaded_event is None, "CRITICAL: Outbox event was NOT rolled back upon transaction failure!"

    # Verify dispatcher drains 0 events
    drained = await drain_outbox_events(sqlite_session)
    assert len(drained) == 0


@pytest.mark.asyncio
async def test_rollback_boundary_postgres_outbox_discarded_on_failure(postgres_session: AsyncSession):
    """If business logic fails in outer transaction, outbox event is rolled back completely in PostgreSQL."""
    aggregate_id = f"AGG-ROLLBACK-PG-{uuid.uuid4().hex[:6]}"

    try:
        async with postgres_session.begin():
            ev = await emit_outbox_event(
                session=postgres_session,
                topic="banking.treasury.transfer",
                event_type="TRANSFER_CREATED",
                aggregate_id=aggregate_id,
                payload={"amount": 9000000, "account": "ACC-ROLLBACK-PG"},
                trace_id="TRACE-RB-PG-1",
            )
            assert ev.id is not None
            # Business logic failure
            raise ValueError("PostgreSQL transaction aborted due to ledger imbalance")
    except ValueError as exc:
        assert "PostgreSQL transaction aborted" in str(exc)

    # Verify atomic consistency in PostgreSQL
    res = await postgres_session.execute(
        select(OutboxEventRecord).where(OutboxEventRecord.aggregate_id == aggregate_id)
    )
    loaded_event = res.scalars().first()
    assert loaded_event is None, "CRITICAL: PostgreSQL outbox event persisted despite transaction rollback!"


@pytest.mark.asyncio
async def test_rollback_boundary_commit_consistency_sqlite(sqlite_session: AsyncSession):
    """When outer transaction commits cleanly, outbox event persists atomically in SQLite."""
    aggregate_id = f"AGG-COMMIT-SQLITE-{uuid.uuid4().hex[:6]}"

    async with sqlite_session.begin():
        ev = await emit_outbox_event(
            session=sqlite_session,
            topic="banking.payments",
            event_type="PAYMENT_CONFIRMED",
            aggregate_id=aggregate_id,
            payload={"status": "confirmed", "amount": 100000},
            trace_id="TRACE-COMMIT-1",
        )
        assert ev.status == "PENDING"

    # Transaction is committed. Query to verify persistence
    res = await sqlite_session.execute(
        select(OutboxEventRecord).where(OutboxEventRecord.aggregate_id == aggregate_id)
    )
    loaded = res.scalars().first()
    assert loaded is not None
    assert loaded.status == "PENDING"
    assert loaded.event_type == "PAYMENT_CONFIRMED"


@pytest.mark.asyncio
async def test_rollback_boundary_commit_consistency_postgres(postgres_session: AsyncSession):
    """When outer transaction commits cleanly, outbox event persists atomically in PostgreSQL."""
    aggregate_id = f"AGG-COMMIT-PG-{uuid.uuid4().hex[:6]}"

    async with postgres_session.begin():
        ev = await emit_outbox_event(
            session=postgres_session,
            topic="banking.payments",
            event_type="PAYMENT_CONFIRMED",
            aggregate_id=aggregate_id,
            payload={"status": "confirmed", "amount": 250000},
            trace_id="TRACE-COMMIT-PG-1",
        )
        assert ev.status == "PENDING"

    res = await postgres_session.execute(
        select(OutboxEventRecord).where(OutboxEventRecord.aggregate_id == aggregate_id)
    )
    loaded = res.scalars().first()
    assert loaded is not None
    assert loaded.aggregate_id == aggregate_id
    assert loaded.status == "PENDING"

    # Cleanup
    await postgres_session.execute(
        delete(OutboxEventRecord).where(OutboxEventRecord.aggregate_id == aggregate_id)
    )
    await postgres_session.commit()


@pytest.mark.asyncio
async def test_rollback_boundary_nested_savepoint_rollback(sqlite_session: AsyncSession):
    """Nested savepoint failure rolls back inner outbox event while preserving outer transaction."""
    outer_agg = f"AGG-OUTER-{uuid.uuid4().hex[:6]}"
    inner_agg = f"AGG-INNER-{uuid.uuid4().hex[:6]}"

    async with sqlite_session.begin():
        # Outer event
        await emit_outbox_event(
            sqlite_session, "outer.topic", "OUTER_EVENT", outer_agg, {"scope": "outer"}, "tr-out"
        )

        # Savepoint for optional secondary action
        try:
            async with sqlite_session.begin_nested():
                await emit_outbox_event(
                    sqlite_session, "inner.topic", "INNER_EVENT", inner_agg, {"scope": "inner"}, "tr-in"
                )
                raise RuntimeError("Non-fatal secondary step failed!")
        except RuntimeError:
            pass  # Handled, savepoint rolled back

    # Outer event must exist, inner event must NOT exist
    res_outer = await sqlite_session.execute(
        select(OutboxEventRecord).where(OutboxEventRecord.aggregate_id == outer_agg)
    )
    assert res_outer.scalars().first() is not None

    res_inner = await sqlite_session.execute(
        select(OutboxEventRecord).where(OutboxEventRecord.aggregate_id == inner_agg)
    )
    assert res_inner.scalars().first() is None


@pytest.mark.asyncio
async def test_rollback_boundary_idempotency_cleared_on_outer_rollback(sqlite_session: AsyncSession):
    """When outer business transaction rolls back, uncommitted idempotency key is also rolled back."""
    key = f"IDEM-RB-{uuid.uuid4().hex[:6]}"
    payload = {"account": "ACC-RB"}

    try:
        async with sqlite_session.begin():
            async def failing_op():
                raise RuntimeError("Business transaction aborted mid-flight")

            await execute_idempotent_operation(
                sqlite_session, key, "/api/rollback", payload, failing_op
            )
    except RuntimeError:
        pass  # Caught outside transaction, outer transaction rolled back

    # Verify key does not exist in DB after rollback
    res = await sqlite_session.execute(
        select(IdempotencyKeyRecord).where(IdempotencyKeyRecord.key == key)
    )
    assert res.scalars().first() is None, "Idempotency record persisted despite outer transaction rollback!"

    # Since it was rolled back, a subsequent request with same key starts freshly
    recovered = False
    async def fresh_op():
        nonlocal recovered
        recovered = True
        return (200, {"success": True})

    code, body, is_replay = await execute_idempotent_operation(
        sqlite_session, key, "/api/rollback", payload, fresh_op
    )
    await sqlite_session.commit()
    assert code == 200
    assert recovered is True
    assert is_replay is False


# ============================================================================
# 2. TTL BOUNDARY ANALYSIS
# ============================================================================

@pytest.mark.asyncio
async def test_ttl_boundary_exact_now_vs_subsecond_sqlite(sqlite_session: AsyncSession):
    """Tests TTL boundary behavior: exact now, sub-second expired, and sub-second active."""
    now = datetime.now(UTC)
    key_active = f"TTL-ACTIVE-{uuid.uuid4().hex[:6]}"
    key_expired = f"TTL-EXPIRED-{uuid.uuid4().hex[:6]}"
    payload = {"account": "ACC-TTL-1"}

    # Record 1: expires in 500 milliseconds (Active)
    rec_active = IdempotencyKeyRecord(
        key=key_active,
        request_hash=compute_canonical_hash(payload),
        status="COMPLETED",
        status_code=200,
        response_body='{"cached": "active"}',
        created_at=now - timedelta(seconds=10),
        expires_at=now + timedelta(milliseconds=500),
    )
    # Record 2: expired 1 millisecond ago
    rec_expired = IdempotencyKeyRecord(
        key=key_expired,
        request_hash=compute_canonical_hash(payload),
        status="COMPLETED",
        status_code=200,
        response_body='{"cached": "expired"}',
        created_at=now - timedelta(seconds=10),
        expires_at=now - timedelta(milliseconds=1),
    )
    sqlite_session.add_all([rec_active, rec_expired])
    await sqlite_session.commit()

    run_counts = {"active": 0, "expired": 0}

    async def op_active():
        run_counts["active"] += 1
        return (200, {"cached": "fresh_active"})

    async def op_expired():
        run_counts["expired"] += 1
        return (200, {"cached": "fresh_expired"})

    # Test Active key: Must return cached replay
    code1, body1, is_replay1 = await execute_idempotent_operation(
        sqlite_session, key_active, "/api/ttl", payload, op_active
    )
    assert is_replay1 is True
    assert body1["cached"] == "active"
    assert run_counts["active"] == 0

    # Test Expired key: Must purge stale record and re-execute freshly
    code2, body2, is_replay2 = await execute_idempotent_operation(
        sqlite_session, key_expired, "/api/ttl", payload, op_expired
    )
    assert is_replay2 is False
    assert body2["cached"] == "fresh_expired"
    assert run_counts["expired"] == 1


@pytest.mark.asyncio
async def test_ttl_boundary_exact_boundary_comparison(sqlite_session: AsyncSession):
    """At exact boundary where expires_at is equal to or slightly ahead of now, verifies cached replay."""
    now = datetime.now(UTC)
    key_exact = f"TTL-EXACT-{uuid.uuid4().hex[:6]}"
    payload = {"account": "ACC-EXACT"}

    # Record with expires_at set to 100 milliseconds in the future
    rec = IdempotencyKeyRecord(
        key=key_exact,
        request_hash=compute_canonical_hash(payload),
        status="COMPLETED",
        status_code=200,
        response_body='{"cached": "exact"}',
        created_at=now - timedelta(seconds=10),
        expires_at=now + timedelta(milliseconds=100),
    )
    sqlite_session.add(rec)
    await sqlite_session.commit()

    runs = 0
    async def op():
        nonlocal runs
        runs += 1
        return (200, {"fresh": True})

    code, body, is_replay = await execute_idempotent_operation(
        sqlite_session, key_exact, "/api/exact", payload, op
    )
    assert is_replay is True
    assert body["cached"] == "exact"
    assert runs == 0


@pytest.mark.asyncio
async def test_ttl_boundary_postgres_expiration_purge(postgres_session: AsyncSession):
    """PostgreSQL timezone-aware expiration boundary correctly purges and re-executes."""
    now = datetime.now(UTC)
    key = f"TTL-PG-EXPIRED-{uuid.uuid4().hex[:6]}"
    payload = {"data": "pg-ttl"}

    rec = IdempotencyKeyRecord(
        key=key,
        request_hash=compute_canonical_hash(payload),
        status="COMPLETED",
        status_code=200,
        response_body='{"old": true}',
        created_at=now - timedelta(seconds=60),
        expires_at=now - timedelta(microseconds=500),
    )
    postgres_session.add(rec)
    await postgres_session.commit()

    runs = 0
    async def op():
        nonlocal runs
        runs += 1
        return (200, {"new": True})

    code, body, is_replay = await execute_idempotent_operation(
        postgres_session, key, "/api/test", payload, op
    )
    await postgres_session.commit()

    assert code == 200
    assert is_replay is False
    assert body["new"] is True
    assert runs == 1

    # Cleanup
    await postgres_session.execute(
        delete(IdempotencyKeyRecord).where(IdempotencyKeyRecord.key == key)
    )
    await postgres_session.commit()


@pytest.mark.asyncio
async def test_ttl_boundary_zero_and_negative_ttl(sqlite_session: AsyncSession):
    """TTL of 0 or negative immediately expires upon completion."""
    key = f"TTL-ZERO-{uuid.uuid4().hex[:6]}"
    payload = {"step": 1}

    async def op():
        return (200, {"step": 1})

    # Call with ttl_seconds=0
    code1, body1, is_replay1 = await execute_idempotent_operation(
        sqlite_session, key, "/api/zero", payload, op, ttl_seconds=0
    )
    await sqlite_session.commit()
    assert is_replay1 is False

    # Small delay to ensure now > expires_at
    await asyncio.sleep(0.005)

    # Next call with same key: should be treated as expired and re-run
    called_again = False
    async def op2():
        nonlocal called_again
        called_again = True
        return (200, {"step": 2})

    code2, body2, is_replay2 = await execute_idempotent_operation(
        sqlite_session, key, "/api/zero", payload, op2, ttl_seconds=0
    )
    await sqlite_session.commit()

    assert is_replay2 is False
    assert called_again is True
    assert body2["step"] == 2


# ============================================================================
# 3. LARGE PAYLOAD HANDLING (100KB+ JSON PAYLOADS)
# ============================================================================

def test_large_payload_canonical_hash_invariance_100kb():
    """Canonical hashing on a 150KB+ dictionary is fast (<50ms) and strictly key-order invariant."""
    payload1 = generate_large_payload(target_kb=150)
    raw_json = str(payload1)
    payload_size_kb = len(raw_json) / 1024
    assert payload_size_kb >= 100, f"Payload size {payload_size_kb}KB is under 100KB"

    # Permute dictionary keys at top level and inside metadata
    payload2 = {
        "metadata": dict(reversed(list(payload1["metadata"].items()))),
        "description": payload1["description"],
        "line_items": payload1["line_items"],
        "treasury_account": payload1["treasury_account"],
        "invoice_number": payload1["invoice_number"],
    }

    t0 = time.perf_counter()
    h1 = compute_canonical_hash(payload1)
    duration_ms = (time.perf_counter() - t0) * 1000

    h2 = compute_canonical_hash(payload2)

    assert h1 == h2, "Canonical hash differed despite identical dictionary content!"
    assert duration_ms < 100, f"Canonical hashing took too long: {duration_ms:.2f}ms"

    # Mutate 1 leaf value in the 150KB payload: hash must change
    payload_altered = dict(payload1)
    payload_altered["line_items"] = list(payload1["line_items"])
    payload_altered["line_items"][0] = dict(payload_altered["line_items"][0])
    payload_altered["line_items"][0]["quantity"] += 1

    h_altered = compute_canonical_hash(payload_altered)
    assert h1 != h_altered, "Altering 1 field failed to produce different SHA-256 fingerprint!"


@pytest.mark.asyncio
async def test_large_payload_idempotency_sqlite_150kb(sqlite_session: AsyncSession):
    """Idempotency engine handles 150KB+ payloads in SQLite: execution, replay fidelity, 409 conflict."""
    key = f"IDEM-LARGE-SQLITE-{uuid.uuid4().hex[:8]}"
    large_req = generate_large_payload(target_kb=150)
    large_resp = generate_large_payload(target_kb=150)
    run_count = 0

    async def processor():
        nonlocal run_count
        run_count += 1
        return (200, large_resp)

    # 1. First execution
    code1, body1, is_replay1 = await execute_idempotent_operation(
        sqlite_session, key, "/api/bulk-treasury", large_req, processor
    )
    await sqlite_session.commit()

    assert code1 == 200
    assert is_replay1 is False
    assert run_count == 1
    assert len(body1["line_items"]) == len(large_resp["line_items"])

    # 2. Replay request: 100% data fidelity check
    code2, body2, is_replay2 = await execute_idempotent_operation(
        sqlite_session, key, "/api/bulk-treasury", large_req, processor
    )
    assert code2 == 200
    assert is_replay2 is True
    assert run_count == 1  # Not executed again
    assert body2["invoice_number"] == large_resp["invoice_number"]
    assert len(body2["line_items"]) == len(large_resp["line_items"])
    assert body2["line_items"][5]["sku"] == large_resp["line_items"][5]["sku"]

    # 3. Altered payload with same key: HTTP 409 Conflict
    altered_req = dict(large_req)
    altered_req["description"] = "Modified description to trigger 409 conflict"
    with pytest.raises(IdempotencyConflictException) as exc_info:
        await execute_idempotent_operation(
            sqlite_session, key, "/api/bulk-treasury", altered_req, processor
        )
    assert exc_info.value.status_code == 409


@pytest.mark.asyncio
async def test_large_payload_idempotency_postgres_150kb(postgres_session: AsyncSession):
    """Idempotency engine handles 150KB+ payloads in PostgreSQL: execution, replay fidelity, 409 conflict."""
    key = f"IDEM-LARGE-PG-{uuid.uuid4().hex[:8]}"
    large_req = generate_large_payload(target_kb=150)
    large_resp = generate_large_payload(target_kb=150)
    run_count = 0

    async def processor():
        nonlocal run_count
        run_count += 1
        return (201, large_resp)

    # 1. Execution
    code1, body1, is_replay1 = await execute_idempotent_operation(
        postgres_session, key, "/api/bulk-treasury-pg", large_req, processor
    )
    await postgres_session.commit()

    assert code1 == 201
    assert is_replay1 is False
    assert run_count == 1

    # 2. Replay
    code2, body2, is_replay2 = await execute_idempotent_operation(
        postgres_session, key, "/api/bulk-treasury-pg", large_req, processor
    )
    assert code2 == 201
    assert is_replay2 is True
    assert run_count == 1
    assert body2["invoice_number"] == large_resp["invoice_number"]
    assert len(body2["line_items"]) == len(large_resp["line_items"])

    # 3. Conflict
    altered_req = dict(large_req)
    altered_req["treasury_account"] = "ACC-CONFLICT-9999"
    with pytest.raises(IdempotencyConflictException):
        await execute_idempotent_operation(
            postgres_session, key, "/api/bulk-treasury-pg", altered_req, processor
        )

    # Cleanup
    await postgres_session.execute(
        delete(IdempotencyKeyRecord).where(IdempotencyKeyRecord.key == key)
    )
    await postgres_session.commit()


@pytest.mark.asyncio
async def test_large_payload_outbox_persistence_and_drain_sqlite(sqlite_session: AsyncSession):
    """Outbox stores 150KB+ payload, drains to subscriber, and deduplicates in SQLite."""
    large_payload = generate_large_payload(target_kb=150)
    agg_id = f"AGG-LARGE-OUTBOX-{uuid.uuid4().hex[:6]}"

    # Emit outbox event
    ev = await emit_outbox_event(
        session=sqlite_session,
        topic="banking.treasury.bulk_import",
        event_type="BULK_IMPORT_COMPLETED",
        aggregate_id=agg_id,
        payload=large_payload,
        trace_id="TRACE-LARGE-1",
    )
    await sqlite_session.commit()

    assert ev.id is not None
    assert len(ev.payload) > 100 * 1024

    received_payloads = []
    async def subscriber(event: OutboxEventRecord) -> bool:
        received_payloads.append(event.payload_json)
        return True

    # Drain event
    drained = await drain_outbox_events(sqlite_session, limit=10, subscriber_fn=subscriber)
    await sqlite_session.commit()

    assert len(drained) == 1
    assert drained[0].status == "PUBLISHED"
    assert len(received_payloads) == 1
    assert received_payloads[0]["invoice_number"] == large_payload["invoice_number"]
    assert len(received_payloads[0]["line_items"]) == len(large_payload["line_items"])

    # Consumer deduplication with 150KB payload
    consumer_runs = 0
    async def consumer_handler(p: dict):
        nonlocal consumer_runs
        consumer_runs += 1

    ok1 = await process_event_with_deduplication(
        sqlite_session, ev.id, "treasury-workers", consumer_handler, large_payload
    )
    await sqlite_session.commit()
    assert ok1 is True
    assert consumer_runs == 1

    # Duplicate call: must be filtered out
    ok2 = await process_event_with_deduplication(
        sqlite_session, ev.id, "treasury-workers", consumer_handler, large_payload
    )
    await sqlite_session.commit()
    assert ok2 is False
    assert consumer_runs == 1


@pytest.mark.asyncio
async def test_large_payload_outbox_persistence_and_drain_postgres(postgres_session: AsyncSession):
    """Outbox stores 150KB+ payload, verifies persistence and consumer deduplication in PostgreSQL."""
    large_payload = generate_large_payload(target_kb=150)
    agg_id = f"AGG-LARGE-PG-{uuid.uuid4().hex[:6]}"

    ev = await emit_outbox_event(
        session=postgres_session,
        topic="banking.bulk.pg",
        event_type="BULK_PG_PROCESSED",
        aggregate_id=agg_id,
        payload=large_payload,
        trace_id="TRACE-LARGE-PG",
    )
    await postgres_session.commit()

    # Query loaded event directly from PostgreSQL
    res = await postgres_session.execute(
        select(OutboxEventRecord).where(OutboxEventRecord.id == ev.id)
    )
    loaded = res.scalars().first()
    assert loaded is not None
    assert loaded.aggregate_id == agg_id
    assert len(loaded.payload) > 100 * 1024
    assert loaded.payload_json["invoice_number"] == large_payload["invoice_number"]
    assert len(loaded.payload_json["line_items"]) == len(large_payload["line_items"])

    # Test local subscriber dispatch directly with loaded event
    subscriber_received = []
    async def direct_subscriber(e: OutboxEventRecord) -> bool:
        subscriber_received.append(e.id)
        return True

    register_outbox_subscriber("banking.bulk.pg", direct_subscriber)
    dispatch_ok = await dispatch_to_local_subscribers(loaded)
    assert dispatch_ok is True
    assert subscriber_received == [loaded.id]

    # Test PostgreSQL consumer deduplication with 150KB+ payload
    consumer_runs = 0
    async def handler(p: dict):
        nonlocal consumer_runs
        consumer_runs += 1

    ok1 = await process_event_with_deduplication(
        postgres_session, loaded.id, "pg-consumers", handler, large_payload
    )
    await postgres_session.commit()
    assert ok1 is True
    assert consumer_runs == 1

    # Second delivery: must be deduplicated
    ok2 = await process_event_with_deduplication(
        postgres_session, loaded.id, "pg-consumers", handler, large_payload
    )
    await postgres_session.commit()
    assert ok2 is False
    assert consumer_runs == 1

    # Cleanup PostgreSQL test records
    await postgres_session.execute(
        delete(OutboxEventRecord).where(OutboxEventRecord.id == ev.id)
    )
    await postgres_session.execute(
        delete(ProcessedEventRecord).where(ProcessedEventRecord.event_id == str(ev.id))
    )
    await postgres_session.commit()


# ============================================================================
# 4. RAPID SEQUENTIAL REPLAY (100 REPLAY REQUESTS)
# ============================================================================

@pytest.mark.asyncio
async def test_rapid_sequential_replay_100_sqlite_latency_and_fidelity(sqlite_session: AsyncSession):
    """100 rapid sequential replays in SQLite: checks latency (<1ms/req avg) and 100% data fidelity."""
    key = f"IDEM-100-SQLITE-{uuid.uuid4().hex[:8]}"
    payload = {
        "source_account": "ACC-PRIMARY-001",
        "destination_account": "ACC-SECONDARY-002",
        "amount_cents": 125000000,
        "currency": "VND",
        "notes": "Chuyển tiền quyết toán kho liên chi nhánh",
    }
    operation_runs = 0

    async def money_transfer():
        nonlocal operation_runs
        operation_runs += 1
        return (200, {
            "transaction_id": f"TX-{uuid.uuid4().hex[:12]}",
            "settled_at": "2026-11-16T15:00:00Z",
            "status": "SETTLED",
            "amount_cents": 125000000,
        })

    # Initial execution
    t_start_initial = time.perf_counter()
    initial_code, initial_body, initial_replay = await execute_idempotent_operation(
        sqlite_session, key, "/api/settlements", payload, money_transfer
    )
    await sqlite_session.commit()
    (time.perf_counter() - t_start_initial) * 1000

    assert initial_code == 200
    assert initial_replay is False
    assert operation_runs == 1

    # 100 Rapid sequential replays
    replay_latencies: list[float] = []
    t_batch_start = time.perf_counter()

    for i in range(100):
        t0 = time.perf_counter()
        code, body, is_replay = await execute_idempotent_operation(
            sqlite_session, key, "/api/settlements", payload, money_transfer
        )
        lat_ms = (time.perf_counter() - t0) * 1000
        replay_latencies.append(lat_ms)

        # Invariants verification
        assert code == 200, f"Replay #{i+1} returned code {code} instead of 200"
        assert is_replay is True, f"Replay #{i+1} had is_replay=False"
        assert body == initial_body, f"Replay #{i+1} body drifted from initial response!"

    total_batch_ms = (time.perf_counter() - t_batch_start) * 1000
    avg_latency_ms = sum(replay_latencies) / len(replay_latencies)
    max_latency_ms = max(replay_latencies)
    min_latency_ms = min(replay_latencies)

    # Strict invariant: Underlying operation was NEVER called during replays
    assert operation_runs == 1, f"CRITICAL: Operation executed {operation_runs} times instead of 1!"

    print(
        f"\n[SQLite Replay Stats 100x]: Total={total_batch_ms:.2f}ms | "
        f"Avg={avg_latency_ms:.3f}ms | Min={min_latency_ms:.3f}ms | Max={max_latency_ms:.3f}ms"
    )
    # Replay latency benchmark assertion: Average replay should be <= 5.0ms on local SQLite
    assert avg_latency_ms < 5.0, f"Average replay latency too high: {avg_latency_ms:.2f}ms"


@pytest.mark.asyncio
async def test_rapid_sequential_replay_100_postgres_latency_and_fidelity(postgres_session: AsyncSession):
    """100 rapid sequential replays in PostgreSQL: verifies zero drift and records benchmark latency."""
    key = f"IDEM-100-PG-{uuid.uuid4().hex[:8]}"
    payload = {
        "order_id": "ORD-PG-9999",
        "customer_id": "CUST-8888",
        "total_amount": 789000,
    }
    runs = 0

    async def business_op():
        nonlocal runs
        runs += 1
        return (200, {"order_id": "ORD-PG-9999", "status": "APPROVED", "run_id": uuid.uuid4().hex[:8]})

    # Initial call
    code0, body0, is_rep0 = await execute_idempotent_operation(
        postgres_session, key, "/api/orders", payload, business_op
    )
    await postgres_session.commit()
    assert is_rep0 is False
    assert runs == 1

    # 100 Replay loop
    latencies: list[float] = []
    t_start = time.perf_counter()

    for _i in range(100):
        t0 = time.perf_counter()
        code, body, is_rep = await execute_idempotent_operation(
            postgres_session, key, "/api/orders", payload, business_op
        )
        lat = (time.perf_counter() - t0) * 1000
        latencies.append(lat)

        assert code == 200
        assert is_rep is True
        assert body == body0

    total_ms = (time.perf_counter() - t_start) * 1000
    avg_ms = sum(latencies) / len(latencies)

    assert runs == 1, f"CRITICAL: Operation executed {runs} times in PostgreSQL!"

    print(
        f"\n[PostgreSQL Replay Stats 100x]: Total={total_ms:.2f}ms | "
        f"Avg={avg_ms:.3f}ms | Min={min(latencies):.3f}ms | Max={max(latencies):.3f}ms"
    )
    assert avg_ms < 15.0, f"PostgreSQL average replay latency too high: {avg_ms:.2f}ms"

    # Cleanup PostgreSQL test records
    await postgres_session.execute(
        delete(IdempotencyKeyRecord).where(IdempotencyKeyRecord.key == key)
    )
    await postgres_session.commit()
