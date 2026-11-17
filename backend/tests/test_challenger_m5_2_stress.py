"""Adversarial Stress Test Suite for Milestone M5: Immutability Bypasses & Concurrency Stress.

Challenger 2 (`challenger_m5_2_gen1`) - Banking & FinTech Architecture Hardening.

Covers:
1. Raw SQL Bypass Attempts:
   - Direct SQL UPDATE bypass blocked by PostgreSQL trigger `prevent_audit_trail_mutation`.
   - Direct SQL DELETE bypass blocked by PostgreSQL trigger `prevent_audit_trail_mutation`.
   - Batch SQL UPDATE bypass blocked by PostgreSQL trigger.
   - Raw SQL TRUNCATE bypass analysis and permission boundary.
2. Truncation & Transaction Rollback Isolation:
   - Rollback at genesis leaves zero dangling records and preserves GENESIS_HASH reference.
   - Rollback mid-chain leaves zero unlinked records and preserves chain continuity despite sequence ID gaps.
   - Nested savepoint rollback cleanly purges intermediate entries without chain corruption.
3. Concurrency Stress (50+ Concurrent Coroutines):
   - 50 concurrent coroutines with serialized coordination: validates monotonic chain, zero duplicate IDs,
     and pristine `verify_audit_chain_integrity` result.
   - 50 concurrent coroutines unsynchronized: empirically demonstrates race condition on `prev_hash`
     (chain forking) and verifies forensic detection by `verify_audit_chain_integrity`.
   - Concurrent readers & verifiers during active appends: validates read snapshot isolation under PostgreSQL.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.models.audit import GENESIS_HASH, AuditEntry
from app.services.audit_service import (
    get_audit_trail,
    record_audit_entry,
    verify_audit_chain_integrity,
)

# ============================================================================
# FIXTURES
# ============================================================================

def _get_pg_url() -> str:
    db_url = os.environ.get(
        "DATABASE_URL",
        "postgresql+asyncpg://bankops:bankops@127.0.0.1:5432/bankops_test",
    )
    if "asyncpg" not in db_url:
        db_url = (
            db_url.replace("postgresql+psycopg2://", "postgresql+asyncpg://")
            .replace("postgresql://", "postgresql+asyncpg://")
        )
    return db_url


@pytest_asyncio.fixture
async def pg_session():
    """Provides a dedicated PostgreSQL AsyncSession connecting to bankops_test."""
    db_url = _get_pg_url()
    try:
        engine = create_async_engine(db_url, poolclass=StaticPool)
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception:
        pytest.skip("PostgreSQL bankops_test not accessible; skipping PostgreSQL integration test")
        return

    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with session_factory() as session:
        try:
            await session.execute(text("TRUNCATE TABLE audit_trail;"))
            await session.commit()
        except Exception:
            await session.rollback()
        yield session

        try:
            await session.execute(text("TRUNCATE TABLE audit_trail;"))
            await session.commit()
        except Exception:
            await session.rollback()

    await engine.dispose()


@pytest_asyncio.fixture
async def pg_session_factory():
    """Provides an AsyncSession factory with an expanded connection pool (pool_size=60)
    to support 50+ concurrent coroutines without connection starvation."""
    db_url = _get_pg_url()
    try:
        engine = create_async_engine(db_url, pool_size=60, max_overflow=20)
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception:
        pytest.skip("PostgreSQL bankops_test not accessible; skipping PostgreSQL integration test")
        return

    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    # Initial table cleanup
    async with session_factory() as session:
        try:
            await session.execute(text("TRUNCATE TABLE audit_trail;"))
            await session.commit()
        except Exception:
            await session.rollback()

    yield session_factory

    # Post-test cleanup
    async with session_factory() as session:
        try:
            await session.execute(text("TRUNCATE TABLE audit_trail;"))
            await session.commit()
        except Exception:
            await session.rollback()

    await engine.dispose()


# ============================================================================
# 1. RAW SQL BYPASS ATTEMPTS
# ============================================================================

@pytest.mark.asyncio
async def test_raw_sql_update_bypass_prevented_by_trigger(pg_session: AsyncSession):
    """Verify that raw SQL UPDATE directly targeting audit_trail is unconditionally rejected
    by the PostgreSQL trigger prevent_audit_trail_mutation."""
    entry = await record_audit_entry(
        session=pg_session,
        actor_id="sec-admin",
        action="TRANSFER_POSTED",
        entity_type="JOURNAL",
        entity_id="J-1001",
        state_payload={"amount_cents": 500000, "dr": "111", "cr": "112"},
    )
    await pg_session.commit()

    entry_id = entry.id
    original_action = entry.action

    # Attempt malicious raw SQL UPDATE
    with pytest.raises(Exception) as exc_info:
        await pg_session.execute(
            text(f"UPDATE audit_trail SET action = 'MALICIOUS_TAMPER' WHERE id = {entry_id}")
        )
        await pg_session.commit()

    await pg_session.rollback()

    err_msg = str(exc_info.value)
    assert "audit_trail is append-only: UPDATE operations are prohibited" in err_msg

    # Verify original record remains pristine
    res = await pg_session.execute(select(AuditEntry).where(AuditEntry.id == entry_id))
    persisted = res.scalars().first()
    assert persisted is not None
    assert persisted.action == original_action


@pytest.mark.asyncio
async def test_raw_sql_delete_bypass_prevented_by_trigger(pg_session: AsyncSession):
    """Verify that raw SQL DELETE directly targeting audit_trail is unconditionally rejected
    by the PostgreSQL trigger prevent_audit_trail_mutation."""
    entry = await record_audit_entry(
        session=pg_session,
        actor_id="sec-admin",
        action="COMPLIANCE_HOLD",
        entity_type="ACCOUNT",
        entity_id="ACC-9999",
        state_payload={"reason": "AML_FLAG"},
    )
    await pg_session.commit()

    entry_id = entry.id

    # Attempt malicious raw SQL DELETE
    with pytest.raises(Exception) as exc_info:
        await pg_session.execute(
            text(f"DELETE FROM audit_trail WHERE id = {entry_id}")
        )
        await pg_session.commit()

    await pg_session.rollback()

    err_msg = str(exc_info.value)
    assert "audit_trail is append-only: DELETE operations are prohibited" in err_msg

    # Verify record was not deleted
    res = await pg_session.execute(select(AuditEntry).where(AuditEntry.id == entry_id))
    persisted = res.scalars().first()
    assert persisted is not None
    assert persisted.id == entry_id


@pytest.mark.asyncio
async def test_raw_sql_batch_update_prevented_by_trigger(pg_session: AsyncSession):
    """Verify that a batch/blanket raw SQL UPDATE without WHERE clause is also rejected."""
    for i in range(5):
        await record_audit_entry(
            session=pg_session,
            actor_id=f"actor-{i}",
            action=f"ACTION_{i}",
            entity_type="SETTING",
            entity_id=str(i),
            state_payload={"val": i},
        )
    await pg_session.commit()

    # Attempt blanket UPDATE on entire table
    with pytest.raises(Exception) as exc_info:
        await pg_session.execute(
            text("UPDATE audit_trail SET actor_id = 'adversary'")
        )
        await pg_session.commit()

    await pg_session.rollback()
    assert "audit_trail is append-only: UPDATE operations are prohibited" in str(exc_info.value)


@pytest.mark.asyncio
async def test_raw_sql_truncate_bypass_analysis(pg_session: AsyncSession):
    """Empirical analysis of TRUNCATE vulnerability:

    Row-level triggers (BEFORE DELETE FOR EACH ROW) do NOT intercept TRUNCATE statements
    in PostgreSQL unless a statement-level trigger (BEFORE TRUNCATE) is defined or TRUNCATE
    privileges are revoked.
    """
    await record_audit_entry(
        session=pg_session,
        actor_id="system",
        action="INIT",
        entity_type="SYSTEM",
        entity_id="sys",
        state_payload={"boot": True},
    )
    await pg_session.commit()

    # Verify row exists
    res = await pg_session.execute(select(func.count(AuditEntry.id)))
    assert res.scalar() == 1

    # TRUNCATE bypasses row-level triggers unless explicitly guarded
    try:
        await pg_session.execute(text("TRUNCATE TABLE audit_trail;"))
        await pg_session.commit()
        truncated = True
    except Exception:
        await pg_session.rollback()
        truncated = False

    # Document empirical reality: TRUNCATE is permitted by DB unless statement trigger exists
    assert truncated is True, "TRUNCATE bypassed row-level triggers (architectural finding)"


# ============================================================================
# 2. TRUNCATION & TRANSACTION ROLLBACK ISOLATION
# ============================================================================

@pytest.mark.asyncio
async def test_rollback_at_genesis_leaves_zero_dangling_records(pg_session: AsyncSession):
    """Verify that an aborted transaction at genesis leaves zero unlinked records,
    and subsequent transaction links cleanly to GENESIS_HASH."""
    # 1. Transaction aborts at genesis
    await record_audit_entry(
        session=pg_session,
        actor_id="failing-agent",
        action="ABORTED_OPERATION",
        entity_type="ACCOUNT",
        entity_id="ACC-001",
        state_payload={"draft": True},
    )
    # Rollback aborts before commit
    await pg_session.rollback()

    # 2. Verify table is completely empty
    res = await pg_session.execute(select(func.count(AuditEntry.id)))
    assert res.scalar() == 0

    # 3. Chain verification on empty table is clean
    v_clean = await verify_audit_chain_integrity(pg_session)
    assert v_clean.is_valid is True
    assert v_clean.broken_id is None

    # 4. Subsequent transaction links cleanly to GENESIS_HASH
    first_committed = await record_audit_entry(
        session=pg_session,
        actor_id="valid-agent",
        action="FIRST_COMMITTED",
        entity_type="ACCOUNT",
        entity_id="ACC-001",
        state_payload={"draft": False},
    )
    await pg_session.commit()

    assert first_committed.prev_hash == GENESIS_HASH
    v_after = await verify_audit_chain_integrity(pg_session)
    assert v_after.is_valid is True


@pytest.mark.asyncio
async def test_rollback_mid_chain_preserves_monotonic_linkage_despite_id_gaps(
    pg_session: AsyncSession,
):
    """Verify that transaction rollback in mid-chain leaves no dangling entries,
    and the subsequent transaction correctly references the preceding committed record
    despite PostgreSQL autoincrement sequence ID gaps."""
    # 1. Commit Record 1
    r1 = await record_audit_entry(
        session=pg_session,
        actor_id="actor-1",
        action="STEP_1",
        entity_type="TRANSFER",
        entity_id="T-100",
        state_payload={"step": 1},
    )
    await pg_session.commit()
    r1_id = r1.id
    r1_hash = r1.current_hash

    # 2. Transaction 2 fails mid-flight and rolls back
    r_aborted = await record_audit_entry(
        session=pg_session,
        actor_id="actor-2",
        action="STEP_2_FAILED",
        entity_type="TRANSFER",
        entity_id="T-100",
        state_payload={"step": 2, "error": "InsufficientFunds"},
    )
    aborted_id = r_aborted.id
    await pg_session.rollback()

    # 3. Commit Record 3
    r3 = await record_audit_entry(
        session=pg_session,
        actor_id="actor-3",
        action="STEP_3_RECOVERY",
        entity_type="TRANSFER",
        entity_id="T-100",
        state_payload={"step": 3, "status": "RECOVERED"},
    )
    await pg_session.commit()
    r3_id = r3.id

    # Sequence ID verification: ID gap occurred due to aborted transaction
    assert r3_id > aborted_id > r1_id

    # Verify Record 3 prev_hash references Record 1 current_hash
    assert r3.prev_hash == r1_hash

    # Verify aborted record does NOT exist in DB
    check_res = await pg_session.execute(
        select(AuditEntry).where(AuditEntry.id == aborted_id)
    )
    assert check_res.scalars().first() is None

    # Full chain integrity verification succeeds cleanly despite sequence gaps
    v_res = await verify_audit_chain_integrity(pg_session)
    assert v_res.is_valid is True
    assert v_res.broken_id is None
    assert v_res.reason is None


@pytest.mark.asyncio
async def test_nested_savepoint_rollback_isolation(pg_session: AsyncSession):
    """Verify that nested savepoint rollbacks cleanly discard speculative audit events
    while keeping the outer transaction and final chain intact."""
    # Outer record
    r1 = await record_audit_entry(
        session=pg_session,
        actor_id="orchestrator",
        action="SAGA_START",
        entity_type="SAGA",
        entity_id="S-1",
        state_payload={"status": "STARTED"},
    )
    await pg_session.flush()

    # Nested savepoint
    async with pg_session.begin_nested() as savepoint:
        await record_audit_entry(
            session=pg_session,
            actor_id="sub-task",
            action="SPECULATIVE_STEP",
            entity_type="SAGA",
            entity_id="S-1",
            state_payload={"status": "TENTATIVE"},
        )
        await pg_session.flush()
        # Rollback savepoint
        await savepoint.rollback()

    # Final step in outer transaction
    r3 = await record_audit_entry(
        session=pg_session,
        actor_id="orchestrator",
        action="SAGA_CONFIRM",
        entity_type="SAGA",
        entity_id="S-1",
        state_payload={"status": "CONFIRMED"},
    )
    await pg_session.commit()

    # Verify chain links r3 to r1
    assert r3.prev_hash == r1.current_hash

    # Verify only 2 records exist in database
    records, total = await get_audit_trail(pg_session, limit=10)
    assert total == 2
    assert [r.action for r in records] == ["SAGA_CONFIRM", "SAGA_START"]

    # Verify chain integrity
    v_res = await verify_audit_chain_integrity(pg_session)
    assert v_res.is_valid is True


# ============================================================================
# 3. CONCURRENCY STRESS TESTING (50+ CONCURRENT COROUTINES)
# ============================================================================

@pytest.mark.asyncio
async def test_concurrency_stress_50_coroutines_synchronized_clean_chain(
    pg_session_factory: async_sessionmaker[AsyncSession],
):
    """Concurrency Stress Test (50+ Coroutines) with Serialization Coordination:

    When concurrent appenders coordinate via an in-process serialization lock
    (simulating an async queue worker or sequenced outbox processor):
    1. All 50 coroutines complete successfully.
    2. Zero duplicate sequence IDs are generated.
    3. Every record links monotonically to its predecessor (H_n = SHA256(H_{n-1} ...)).
    4. verify_audit_chain_integrity confirms the entire 50-record chain is 100% valid.
    """
    total_coroutines = 55
    append_lock = asyncio.Lock()

    async def worker(idx: int) -> int:
        async with append_lock:
            async with pg_session_factory() as session:
                entry = await record_audit_entry(
                    session=session,
                    actor_id=f"concurrent-worker-{idx}",
                    action="CONCURRENT_TRANSFER",
                    entity_type="ACCOUNT",
                    entity_id=f"ACC-{1000 + idx}",
                    state_payload={
                        "iteration": idx,
                        "amount_cents": 100000 + idx * 50,
                        "uuid": str(uuid.uuid4()),
                    },
                )
                await session.commit()
                return entry.id

    # Launch 55 concurrent coroutines simultaneously
    tasks = [worker(i) for i in range(total_coroutines)]
    entry_ids = await asyncio.gather(*tasks)

    # 1. Verify all 55 completed
    assert len(entry_ids) == total_coroutines

    # 2. Verify all generated IDs are strictly unique
    assert len(set(entry_ids)) == total_coroutines

    # 3. Verify monotonic continuity in DB
    async with pg_session_factory() as verify_session:
        res = await verify_session.execute(
            select(AuditEntry).order_by(AuditEntry.id.asc())
        )
        records = list(res.scalars().all())
        assert len(records) == total_coroutines

        # Validate cryptographic link step by step
        expected_prev = GENESIS_HASH
        for i, rec in enumerate(records):
            assert rec.prev_hash == expected_prev, f"Chain broken at record index {i} (id={rec.id})"
            expected_prev = rec.current_hash

        # 4. Verify using the service verifier
        v_res = await verify_audit_chain_integrity(verify_session)
        assert v_res.is_valid is True
        assert v_res.broken_id is None
        assert v_res.reason is None


@pytest.mark.asyncio
async def test_concurrency_stress_50_coroutines_unsynchronized_reveals_race_condition(
    pg_session_factory: async_sessionmaker[AsyncSession],
):
    """Empirical Vulnerability Exposure: Unsynchronized Concurrent Appends:

    When 50+ concurrent coroutines call record_audit_entry across separate DB transactions
    without synchronization:
    - Multiple coroutines read the exact same last committed record concurrently.
    - They compute curr_hash based on the same prev_hash, creating sibling blocks (chain fork).
    - Upon commit, PostgreSQL assigns sequential IDs, but the prev_hash values collide.
    - verify_audit_chain_integrity detects the corruption and pinpoints 'prev_hash_mismatch'.

    This test empirically documents the finding and validates the verifier's tamper detection.
    """
    total_coroutines = 50

    async def unsynchronized_worker(idx: int) -> dict[str, Any]:
        async with pg_session_factory() as session:
            entry = await record_audit_entry(
                session=session,
                actor_id=f"race-worker-{idx}",
                action="RACE_OPERATION",
                entity_type="ASSET",
                entity_id=f"ITEM-{idx}",
                state_payload={"idx": idx},
            )
            await session.commit()
            return {"id": entry.id, "prev_hash": entry.prev_hash, "curr_hash": entry.current_hash}

    # Dispatch 50 concurrent unsynchronized coroutines
    tasks = [unsynchronized_worker(i) for i in range(total_coroutines)]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # All transactions succeed at the DB level (no SQL constraint errors)
    successful_results = [r for r in results if isinstance(r, dict)]
    assert len(successful_results) == total_coroutines

    # Inspect chain in DB
    async with pg_session_factory() as session:
        records_res = await session.execute(
            select(AuditEntry).order_by(AuditEntry.id.asc())
        )
        records = list(records_res.scalars().all())
        assert len(records) == total_coroutines

        # Count occurrences of prev_hashes: in an unsynchronized race, duplicate prev_hashes occur
        prev_hashes = [r.prev_hash for r in records]
        unique_prev_hashes = set(prev_hashes)
        has_duplicate_prev_hashes = len(unique_prev_hashes) < len(prev_hashes)

        # Run integrity verifier
        v_res = await verify_audit_chain_integrity(session)

        # Empirically verify that the concurrency race condition is detected
        if has_duplicate_prev_hashes:
            assert v_res.is_valid is False
            assert v_res.reason == "prev_hash_mismatch"
            assert v_res.broken_id is not None
        else:
            # In rare low-concurrency environments if sequential execution occurred
            assert v_res.is_valid is True


@pytest.mark.asyncio
async def test_concurrent_readers_during_high_volume_appends(
    pg_session_factory: async_sessionmaker[AsyncSession],
):
    """Verify that multiple concurrent readers (verification & trail queries) can run
    simultaneously alongside active appenders without database deadlocks or lock timeouts."""
    num_writers = 25
    num_readers = 25
    append_lock = asyncio.Lock()

    async def writer_task(idx: int):
        async with append_lock:
            async with pg_session_factory() as session:
                await record_audit_entry(
                    session=session,
                    actor_id=f"writer-{idx}",
                    action="CONCURRENT_WRITE",
                    entity_type="BENCHMARK",
                    entity_id=str(idx),
                    state_payload={"w": idx},
                )
                await session.commit()

    async def reader_task(idx: int) -> bool:
        # Small delay to interleave with writers
        await asyncio.sleep(0.01 * (idx % 5))
        async with pg_session_factory() as session:
            # Readers query audit trail and run verification
            _items, total = await get_audit_trail(session, limit=20)
            res = await verify_audit_chain_integrity(session)
            return res.is_valid

    # Run 25 writers and 25 readers concurrently
    writer_coros = [writer_task(i) for i in range(num_writers)]
    reader_coros = [reader_task(i) for i in range(num_readers)]
    all_coros = writer_coros + reader_coros

    results = await asyncio.gather(*all_coros, return_exceptions=True)

    # Check zero exceptions occurred across all 50 concurrent tasks
    exceptions = [r for r in results if isinstance(r, Exception)]
    assert len(exceptions) == 0, f"Concurrent reader/writer tasks failed with exceptions: {exceptions}"

    # Final state check
    async with pg_session_factory() as session:
        v_final = await verify_audit_chain_integrity(session)
        assert v_final.is_valid is True
        _records, total_count = await get_audit_trail(session, limit=100)
        assert total_count == num_writers
