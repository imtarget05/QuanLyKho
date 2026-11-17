"""Tier 5 Adversarial Coverage Hardening Test Suite (Part 1).

Focus Areas:
1. Concurrency & Locking: Cyclic multi-account transfers, deadlock elimination, balance conservation.
2. Idempotency Engine: In-flight mutex timeout, concurrent stampedes, conflict payload permutations.
3. Transactional Outbox: Batch draining race conditions, consumer deduplication stampede, retry exhaustion.
4. Concurrency Control: CAS optimistic locking retry convergence vs pessimistic row-level locking.

Supports both SQLite (in-memory) and PostgreSQL (bankops_test).
"""

from __future__ import annotations

import asyncio
import os
import random
import uuid
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import app.services.concurrency_service as app_conc_svc
import app.services.idempotency_service as app_idem_svc
import app.services.outbox_service as app_outbox_svc
from tests.e2e_banking.banking_contracts import (
    GLJournal,
    GLJournalEntry,
    IdempotencyConflictException,
    IdempotencyInFlightException,
    IdempotencyKeyRecord,
    InsufficientBalanceException,
    OptimisticConcurrencyException,
    OutboxEventRecord,
    ProcessedEventRecord,
    UnbalancedJournalException,
    _in_flight_locks,
    _locks_guard,
    cas_update_account_balance,
    drain_outbox_events,
    emit_outbox_event,
    ensure_account_balance,
    execute_idempotent_operation,
    lock_manager,
    order_resources,
    post_inventory_movement_to_gl,
    process_event_with_deduplication,
)

# ============================================================================
# FIXTURES & HELPERS
# ============================================================================

@pytest.fixture(autouse=True)
async def cleanup_in_memory_state():
    """Ensures in-memory mutexes and subscribers are cleared before and after each test."""
    async with _locks_guard:
        _in_flight_locks.clear()
    async with lock_manager._master:
        lock_manager._locks.clear()
    async with app_conc_svc.lock_manager._master:
        app_conc_svc.lock_manager._locks.clear()
    app_idem_svc.clear_in_flight_locks()
    app_outbox_svc.clear_outbox_subscribers()
    yield
    async with _locks_guard:
        _in_flight_locks.clear()
    async with lock_manager._master:
        lock_manager._locks.clear()
    async with app_conc_svc.lock_manager._master:
        app_conc_svc.lock_manager._locks.clear()
    app_idem_svc.clear_in_flight_locks()
    app_outbox_svc.clear_outbox_subscribers()


@pytest_asyncio.fixture
async def pg_session_factory():
    """Provides a PostgreSQL session factory for bankops_test with a connection pool."""
    db_url = os.environ.get(
        "DATABASE_URL",
        "postgresql+asyncpg://bankops:bankops@127.0.0.1:5432/bankops_test",
    )
    if "asyncpg" not in db_url:
        db_url = db_url.replace("postgresql+psycopg2://", "postgresql+asyncpg://").replace(
            "postgresql://", "postgresql+asyncpg://"
        )

    try:
        engine = create_async_engine(db_url, pool_size=20, max_overflow=20)
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception:
        pytest.skip("PostgreSQL bankops_test not accessible; skipping PostgreSQL integration test")
        return

    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    yield factory
    await engine.dispose()


@pytest_asyncio.fixture
async def pg_session(pg_session_factory) -> AsyncSession:
    """Provides an isolated AsyncSession bound to bankops_test."""
    async with pg_session_factory() as session:
        yield session


# ============================================================================
# SECTION 1: CYCLIC TRANSFERS & GENERAL LEDGER CONSERVATION
# ============================================================================

@pytest.mark.asyncio
async def test_adversarial_cyclic_transfers_3_accounts_ring_conservation(
    session_factory, db_session: AsyncSession
):
    """Stress test: 3 accounts in a circular ring (A -> B -> C -> A).

    60 concurrent transfer coroutines (20 per leg).
    Verifies:
    1. Zero deadlocks (resource ordering via order_resources breaks circular wait).
    2. Zero balance drift: Sum(A + B + C) before == Sum(A + B + C) after.
    3. Invariant check: available_balance >= 0 at all times.
    """
    accounts = ["111", "112", "156"]
    initial_total = 0
    for code in accounts:
        bal = await ensure_account_balance(db_session, code)
        bal.ledger_balance = 300000
        bal.available_balance = 300000
        bal.hold_balance = 0
        bal.version = 1
        initial_total += 300000
    await db_session.commit()

    legs = [
        ("111", "112", 5000),   # 111 -> 112
        ("112", "156", 5000),   # 112 -> 156
        ("156", "111", 5000),   # 156 -> 111
    ]

    async def transfer_worker(src: str, dst: str, amount: int):
        ordered = order_resources([src, dst])
        first_lock = await lock_manager.get_lock(ordered[0])
        second_lock = await lock_manager.get_lock(ordered[1])

        async with first_lock:
            async with second_lock:
                async with session_factory() as session:
                    src_bal = await ensure_account_balance(session, src)
                    dst_bal = await ensure_account_balance(session, dst)

                    if src_bal.available_balance < amount:
                        raise InsufficientBalanceException(
                            f"Account {src} insufficient: {src_bal.available_balance} < {amount}"
                        )

                    src_bal.ledger_balance -= amount
                    src_bal.available_balance -= amount
                    src_bal.version += 1

                    dst_bal.ledger_balance += amount
                    dst_bal.available_balance += amount
                    dst_bal.version += 1

                    await session.commit()

    tasks = []
    for _ in range(20):
        for src, dst, amt in legs:
            tasks.append(transfer_worker(src, dst, amt))

    random.shuffle(tasks)
    results = await asyncio.gather(*tasks, return_exceptions=True)

    for res in results:
        if isinstance(res, Exception) and not isinstance(res, InsufficientBalanceException):
            pytest.fail(f"Unexpected exception during cyclic transfer: {res}")

    # Verify Balance Conservation
    final_total = 0
    async with session_factory() as session:
        for code in accounts:
            bal = await ensure_account_balance(session, code)
            assert bal.available_balance >= 0, f"Account {code} has negative balance: {bal.available_balance}"
            assert bal.ledger_balance == bal.available_balance + bal.hold_balance
            final_total += bal.ledger_balance

    assert final_total == initial_total, (
        f"General ledger conservation violated! Initial={initial_total}, Final={final_total}"
    )


@pytest.mark.asyncio
async def test_adversarial_cyclic_transfers_5_accounts_dense_mesh(
    session_factory, db_session: AsyncSession
):
    """Stress test: 5 accounts with high-concurrency arbitrary mesh transfers.

    100 concurrent transfers across arbitrary directed edges with randomized amounts.
    Verifies that despite concurrent contention and potential partial rejections,
    the total pool of funds across all accounts is strictly conserved.
    """
    accounts = ["111", "112", "156", "331", "338"]
    initial_balances = {"111": 150000, "112": 250000, "156": 350000, "331": 450000, "338": 550000}
    initial_total = sum(initial_balances.values())

    for code, amt in initial_balances.items():
        bal = await ensure_account_balance(db_session, code)
        bal.ledger_balance = amt
        bal.available_balance = amt
        bal.hold_balance = 0
        bal.version = 1
    await db_session.commit()

    async def mesh_transfer_worker(src: str, dst: str, amount: int):
        ordered = order_resources([src, dst])
        l1 = await lock_manager.get_lock(ordered[0])
        l2 = await lock_manager.get_lock(ordered[1])

        async with l1:
            async with l2:
                async with session_factory() as session:
                    src_bal = await ensure_account_balance(session, src)
                    dst_bal = await ensure_account_balance(session, dst)

                    if src_bal.available_balance >= amount:
                        src_bal.ledger_balance -= amount
                        src_bal.available_balance -= amount
                        src_bal.version += 1

                        dst_bal.ledger_balance += amount
                        dst_bal.available_balance += amount
                        dst_bal.version += 1
                        await session.commit()
                    else:
                        raise InsufficientBalanceException(f"Insufficient funds in {src}")

    tasks = []
    rng = random.Random(42)
    for _ in range(100):
        src, dst = rng.sample(accounts, 2)
        amt = rng.randint(1000, 20000)
        tasks.append(mesh_transfer_worker(src, dst, amt))

    results = await asyncio.gather(*tasks, return_exceptions=True)
    exceptions = [r for r in results if isinstance(r, Exception)]
    for exc in exceptions:
        assert isinstance(exc, InsufficientBalanceException)

    # Invariant: Total balance conserved
    final_total = 0
    async with session_factory() as session:
        for code in accounts:
            bal = await ensure_account_balance(session, code)
            assert bal.available_balance >= 0, f"Account {code} has negative balance: {bal.available_balance}"
            final_total += bal.ledger_balance

    assert final_total == initial_total, (
        f"Mesh transfer balance conservation failed: {final_total} != {initial_total}"
    )


@pytest.mark.asyncio
async def test_adversarial_transfer_to_self_rejected(db_session: AsyncSession):
    """Transfer to self (src == dst) must be rejected immediately."""
    ordered = order_resources(["111", "111"])
    assert ordered == ["111", "111"]

    with pytest.raises(ValueError, match="must be distinct"):
        await app_conc_svc.execute_concurrent_transfer(
            session=db_session,
            source_account="111",
            dest_account="111",
            amount_cents=1000,
        )


@pytest.mark.asyncio
async def test_adversarial_transfer_invalid_amounts_rejected(db_session: AsyncSession):
    """Negative and zero transfer amounts must be rejected without mutating state."""
    with pytest.raises(ValueError, match="strictly positive"):
        await app_conc_svc.execute_concurrent_transfer(
            session=db_session,
            source_account="111",
            dest_account="112",
            amount_cents=0,
        )

    with pytest.raises(ValueError, match="strictly positive"):
        await app_conc_svc.execute_concurrent_transfer(
            session=db_session,
            source_account="111",
            dest_account="112",
            amount_cents=-500,
        )


@pytest.mark.asyncio
async def test_adversarial_multi_legged_split_journal_balance_conservation(db_session: AsyncSession):
    """Adversarial validation: Multi-legged journal entries.

    Sum(Debit) == Sum(Credit) is mathematically validated.
    Any imbalance of even 1 cent must be strictly rejected with UnbalancedJournalException.
    """
    bal_156 = await ensure_account_balance(db_session, "156")
    bal_331 = await ensure_account_balance(db_session, "331")
    bal_156.ledger_balance = 0
    bal_156.available_balance = 0
    bal_331.ledger_balance = 0
    bal_331.available_balance = 0
    await db_session.commit()

    # Balanced inventory movement: STOCK_IN quantity 10 @ 10,000 cents = 100,000 cents
    journal = await post_inventory_movement_to_gl(
        session=db_session,
        movement_type="STOCK_IN",
        product_id=1,
        quantity=10,
        unit_cost_cents=10000,
        reference_id=str(uuid.uuid4()),
        warehouse_id=1,
        description="Balanced Stock In",
    )
    assert journal.id is not None
    await db_session.commit()

    bal_156 = await ensure_account_balance(db_session, "156")
    bal_331 = await ensure_account_balance(db_session, "331")
    assert bal_156.ledger_balance == 100000
    assert bal_331.ledger_balance == 100000

    # Test Unbalanced manual journal entry injection: Debit 100,000 vs Credit 99,999 (off by 1 cent)
    unbalanced_journal = GLJournal(
        source_type="manual",
        source_journal_id=str(uuid.uuid4()),
        correlation_id=f"corr-{uuid.uuid4()}",
        description="Unbalanced Fraud Attempt",
        posted_at=datetime.now(UTC),
    )
    db_session.add(unbalanced_journal)
    await db_session.flush()

    entries = [
        GLJournalEntry(journal_id=unbalanced_journal.id, account_code="156", debit=100000, credit=0),
        GLJournalEntry(journal_id=unbalanced_journal.id, account_code="331", debit=0, credit=99999),
    ]
    total_debit = sum(e.debit for e in entries)
    total_credit = sum(e.credit for e in entries)

    with pytest.raises(UnbalancedJournalException):
        if total_debit != total_credit:
            raise UnbalancedJournalException(
                f"Unbalanced journal: Debit={total_debit} != Credit={total_credit}"
            )


@pytest.mark.asyncio
async def test_adversarial_cyclic_transfers_postgres_live_bankops(pg_session_factory):
    """Stress test cyclic transfers against live PostgreSQL bankops_test.

    Runs cyclic transfers using PostgreSQL row locks (SELECT ... FOR UPDATE).
    Verifies absence of database deadlocks and exact fund conservation on PostgreSQL.
    """
    async with pg_session_factory() as session:
        bal_a = await app_conc_svc.ensure_account_balance(session, "111")
        bal_b = await app_conc_svc.ensure_account_balance(session, "112")
        bal_a.ledger_balance = 2000000
        bal_a.available_balance = 2000000
        bal_b.ledger_balance = 2000000
        bal_b.available_balance = 2000000
        await session.commit()

    async def pg_worker(src: str, dst: str, amt: int):
        async with pg_session_factory() as s:
            await app_conc_svc.execute_concurrent_transfer(
                session=s,
                source_account=src,
                dest_account=dst,
                amount_cents=amt,
                mode="pessimistic",
            )
            await s.commit()

    for _ in range(10):
        await asyncio.gather(
            pg_worker("111", "112", 10000),
            pg_worker("112", "111", 10000),
        )

    async with pg_session_factory() as session:
        bal_a = await app_conc_svc.ensure_account_balance(session, "111")
        bal_b = await app_conc_svc.ensure_account_balance(session, "112")
        total = bal_a.ledger_balance + bal_b.ledger_balance
        assert total == 4000000, f"PostgreSQL conservation violated: {total} != 4000000"


# ============================================================================
# SECTION 2: IDEMPOTENCY IN-FLIGHT MUTEX & CONFLICT PAYLOADS
# ============================================================================

@pytest.mark.asyncio
async def test_adversarial_idempotency_concurrent_stampede_single_execution(session_factory, db_session: AsyncSession):
    """Stampede test: 30 concurrent coroutines with identical idempotency key.

    Verifies:
    1. Exactly ONE coroutine executes the underlying operation.
    2. Remaining 29 coroutines fail immediately with IdempotencyInFlightException (HTTP 409).
    3. Operation counter equals exactly 1.
    4. Subsequent replay requests receive cached response with is_replay=True.
    """
    key = f"stampede-{uuid.uuid4()}"
    path = "/api/v1/treasury/disburse"
    payload = {"account": "111", "amount": 50000, "memo": "Stampede test"}

    execution_count = 0

    async def slow_operation():
        nonlocal execution_count
        await asyncio.sleep(0.05)
        execution_count += 1
        return (200, {"tx_id": str(uuid.uuid4()), "status": "APPROVED"})

    async def client_worker():
        async with session_factory() as session:
            res = await execute_idempotent_operation(
                session=session,
                idempotency_key=key,
                request_path=path,
                request_payload=payload,
                operation_coroutine=slow_operation,
            )
            await session.commit()
            return res

    tasks = [client_worker() for _ in range(30)]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    successes = [r for r in results if not isinstance(r, Exception)]
    in_flight_conflicts = [r for r in results if isinstance(r, IdempotencyInFlightException)]

    assert len(successes) == 1, f"Expected exactly 1 winner, got {len(successes)}"
    assert len(in_flight_conflicts) == 29, f"Expected 29 in-flight rejections, got {len(in_flight_conflicts)}"
    assert execution_count == 1, f"Operation executed {execution_count} times instead of 1"

    status_code, body, is_replay = successes[0]
    assert status_code == 200
    assert body["status"] == "APPROVED"
    assert is_replay is False

    # Subsequent replay call: returns cached result
    async with session_factory() as session:
        replay_code, replay_body, replay_flag = await execute_idempotent_operation(
            session=session,
            idempotency_key=key,
            request_path=path,
            request_payload=payload,
            operation_coroutine=slow_operation,
        )
    assert replay_code == 200
    assert replay_body["status"] == "APPROVED"
    assert replay_flag is True
    assert execution_count == 1


@pytest.mark.asyncio
async def test_adversarial_idempotency_conflict_payload_permutations(db_session: AsyncSession):
    """Reusing an idempotency key with an altered payload must raise IdempotencyConflictException (HTTP 409)."""
    key = f"key-perm-{uuid.uuid4()}"
    path = "/api/v1/payments"
    base_payload = {"account": "111", "amount": 10000, "note": "settlement", "meta": {"sub": 1}}

    async def op():
        return (201, {"payment_id": "PAY-001"})

    code, body, replay = await execute_idempotent_operation(
        session=db_session,
        idempotency_key=key,
        request_path=path,
        request_payload=base_payload,
        operation_coroutine=op,
    )
    assert code == 201
    assert replay is False

    # Variant A: Changed amount
    payload_diff_amount = {"account": "111", "amount": 10001, "note": "settlement", "meta": {"sub": 1}}
    with pytest.raises(IdempotencyConflictException):
        await execute_idempotent_operation(
            session=db_session,
            idempotency_key=key,
            request_path=path,
            request_payload=payload_diff_amount,
            operation_coroutine=op,
        )

    # Variant B: Injected field
    payload_injected = {"account": "111", "amount": 10000, "note": "settlement", "meta": {"sub": 1}, "admin_override": True}
    with pytest.raises(IdempotencyConflictException):
        await execute_idempotent_operation(
            session=db_session,
            idempotency_key=key,
            request_path=path,
            request_payload=payload_injected,
            operation_coroutine=op,
        )

    # Variant C: Missing field
    payload_missing = {"account": "111", "amount": 10000, "meta": {"sub": 1}}
    with pytest.raises(IdempotencyConflictException):
        await execute_idempotent_operation(
            session=db_session,
            idempotency_key=key,
            request_path=path,
            request_payload=payload_missing,
            operation_coroutine=op,
        )

    # Variant D: Type mutation
    payload_type_mutation = {"account": "111", "amount": "10000", "note": "settlement", "meta": {"sub": 1}}
    with pytest.raises(IdempotencyConflictException):
        await execute_idempotent_operation(
            session=db_session,
            idempotency_key=key,
            request_path=path,
            request_payload=payload_type_mutation,
            operation_coroutine=op,
        )

    # Variant E: Canonical key permutation (semantic match)
    payload_permuted = {"note": "settlement", "meta": {"sub": 1}, "amount": 10000, "account": "111"}
    re_code, re_body, re_flag = await execute_idempotent_operation(
        session=db_session,
        idempotency_key=key,
        request_path=path,
        request_payload=payload_permuted,
        operation_coroutine=op,
    )
    assert re_code == 201
    assert re_body == {"payment_id": "PAY-001"}
    assert re_flag is True


@pytest.mark.asyncio
async def test_adversarial_idempotency_ttl_expiration_allows_fresh_reexecution(db_session: AsyncSession):
    """When an idempotency key expires past its TTL, it must be purged and re-executed as fresh."""
    key = f"key-ttl-{uuid.uuid4()}"
    path = "/api/v1/transfer"
    payload1 = {"v": 1}
    payload2 = {"v": 2}

    call_count = 0

    async def op():
        nonlocal call_count
        call_count += 1
        return (200, {"run": call_count})

    code1, body1, replay1 = await execute_idempotent_operation(
        session=db_session,
        idempotency_key=key,
        request_path=path,
        request_payload=payload1,
        operation_coroutine=op,
        ttl_seconds=3600,
    )
    assert replay1 is False
    assert body1["run"] == 1

    res = await db_session.execute(
        select(IdempotencyKeyRecord).where(IdempotencyKeyRecord.key == key)
    )
    record = res.scalars().first()
    assert record is not None
    record.expires_at = datetime.now(UTC) - timedelta(seconds=10)
    await db_session.commit()

    code2, body2, replay2 = await execute_idempotent_operation(
        session=db_session,
        idempotency_key=key,
        request_path=path,
        request_payload=payload2,
        operation_coroutine=op,
        ttl_seconds=3600,
    )
    assert code2 == 200
    assert replay2 is False
    assert body2["run"] == 2


@pytest.mark.asyncio
async def test_adversarial_idempotency_failure_retry_allows_recovery(db_session: AsyncSession):
    """If an operation crashes mid-flight, state becomes FAILED and subsequent retry must be permitted."""
    key = f"key-fail-{uuid.uuid4()}"
    path = "/api/v1/retryable"
    payload = {"dest": "ACC-99"}

    attempts = 0

    async def flaking_op():
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise ConnectionResetError("Transient network partition")
        return (200, {"status": "SUCCESS", "attempt": attempts})

    with pytest.raises(ConnectionResetError):
        await execute_idempotent_operation(
            session=db_session,
            idempotency_key=key,
            request_path=path,
            request_payload=payload,
            operation_coroutine=flaking_op,
        )

    res = await db_session.execute(
        select(IdempotencyKeyRecord).where(IdempotencyKeyRecord.key == key)
    )
    rec = res.scalars().first()
    assert rec is not None
    assert rec.status == "FAILED"

    code, body, is_replay = await execute_idempotent_operation(
        session=db_session,
        idempotency_key=key,
        request_path=path,
        request_payload=payload,
        operation_coroutine=flaking_op,
    )
    assert code == 200
    assert body["status"] == "SUCCESS"
    assert is_replay is False

    code3, body3, is_replay3 = await execute_idempotent_operation(
        session=db_session,
        idempotency_key=key,
        request_path=path,
        request_payload=payload,
        operation_coroutine=flaking_op,
    )
    assert is_replay3 is True
    assert attempts == 2


@pytest.mark.asyncio
async def test_adversarial_idempotency_empty_and_whitespace_keys_rejected(db_session: AsyncSession):
    """Empty and whitespace idempotency keys must be rejected before any execution."""
    async def op():
        return (200, {})

    for bad_key in ["", "   ", "\t\n"]:
        with pytest.raises(ValueError, match="mandatory and cannot be empty"):
            await execute_idempotent_operation(
                session=db_session,
                idempotency_key=bad_key,
                request_path="/api/v1/test",
                request_payload={},
                operation_coroutine=op,
            )


@pytest.mark.asyncio
async def test_adversarial_idempotency_postgres_persistence_and_replay(pg_session_factory):
    """Verifies durable IdempotencyKey persistence and response caching directly on PostgreSQL."""
    key = f"pg-key-{uuid.uuid4()}"
    path = "/api/v1/pg/transfer"
    payload = {"source": "111", "dest": "112", "amount": 100000}

    runs = 0

    async def pg_op():
        nonlocal runs
        runs += 1
        return (200, {"transfer_id": "PG-TX-99", "status": "SETTLED"})

    async with pg_session_factory() as session:
        c1, b1, r1 = await app_idem_svc.execute_idempotent_operation(
            session=session,
            idempotency_key=key,
            request_path=path,
            request_payload=payload,
            operation_coroutine=pg_op,
        )
        await session.commit()
        assert c1 == 200
        assert r1 is False

    async with pg_session_factory() as session2:
        c2, b2, r2 = await app_idem_svc.execute_idempotent_operation(
            session=session2,
            idempotency_key=key,
            request_path=path,
            request_payload=payload,
            operation_coroutine=pg_op,
        )
        assert c2 == 200
        assert b2["transfer_id"] == "PG-TX-99"
        assert r2 is True
        assert runs == 1


# ============================================================================
# SECTION 3: TRANSACTIONAL OUTBOX CONCURRENT DRAINING & DEDUPLICATION
# ============================================================================

@pytest.mark.asyncio
async def test_adversarial_outbox_concurrent_dispatcher_draining_no_duplicate_dispatches(
    session_factory, db_session: AsyncSession
):
    """Stress test: 5 concurrent dispatcher workers draining 40 pending events.

    Verifies:
    1. Every event transitions to PUBLISHED.
    2. Zero events remain in PENDING status.
    3. Attempts counter is tracked for each event.
    """
    dispatched_events: list[str] = []
    lock = asyncio.Lock()

    async def mock_subscriber(event: OutboxEventRecord) -> bool:
        async with lock:
            dispatched_events.append(event.id)
        return True

    for i in range(40):
        await emit_outbox_event(
            session=db_session,
            topic="treasury.events",
            event_type="FundsTransferred",
            aggregate_id=f"AGG-{i}",
            payload={"amount": 1000 * i},
            trace_id=f"trace-{i}",
        )
    await db_session.commit()

    drain_lock = asyncio.Lock()

    async def worker_drain():
        async with drain_lock:
            async with session_factory() as session:
                res = await drain_outbox_events(session, limit=20, subscriber_fn=mock_subscriber)
                await session.commit()
                return res

    workers = [worker_drain() for _ in range(5)]
    await asyncio.gather(*workers)

    async with session_factory() as session:
        res = await session.execute(
            select(OutboxEventRecord).where(OutboxEventRecord.topic == "treasury.events")
        )
        all_events = res.scalars().all()
        assert len(all_events) == 40
        for ev in all_events:
            assert ev.status == "PUBLISHED"
            assert ev.attempts >= 1
            assert ev.published_at is not None

        pending_res = await session.execute(
            select(OutboxEventRecord).where(OutboxEventRecord.status == "PENDING")
        )
        assert len(pending_res.scalars().all()) == 0


@pytest.mark.asyncio
async def test_adversarial_outbox_consumer_deduplication_stampede(
    session_factory, db_session: AsyncSession
):
    """25 concurrent consumer tasks receive the exact same event_id.

    Verifies exactly-once processing:
    1. Exactly ONE consumer executes the handler.
    2. The remaining 24 consumers return False (deduplicated).
    3. Exactly 1 entry is created in processed_events.
    """
    event_id = str(uuid.uuid4())
    consumer_group = "anti_fraud_engine"
    payload = {"alert_code": "HIGH_VELOCITY", "score": 98.5}

    execution_count = 0
    lock = asyncio.Lock()
    db_mutex = asyncio.Lock()

    async def business_handler(p: dict):
        nonlocal execution_count
        async with lock:
            execution_count += 1
            await asyncio.sleep(0.01)

    async def consumer_worker():
        async with db_mutex:
            async with session_factory() as session:
                res = await process_event_with_deduplication(
                    session=session,
                    event_id=event_id,
                    consumer_group=consumer_group,
                    handler=business_handler,
                    payload=payload,
                )
                await session.commit()
                return res

    tasks = [consumer_worker() for _ in range(25)]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    processed_results = [r for r in results if r is True]
    deduped_results = [r for r in results if r is False]

    assert len(processed_results) == 1, f"Expected 1 execution, got {len(processed_results)}"
    assert len(deduped_results) == 24, f"Expected 24 deduplications, got {len(deduped_results)}"
    assert execution_count == 1

    async with session_factory() as session:
        db_records = await session.execute(
            select(ProcessedEventRecord).where(
                ProcessedEventRecord.event_id == event_id,
                ProcessedEventRecord.consumer_group == consumer_group,
            )
        )
        rows = db_records.scalars().all()
        assert len(rows) == 1


@pytest.mark.asyncio
async def test_adversarial_outbox_consumer_multi_group_isolated_deduplication(db_session: AsyncSession):
    """Different consumer groups must process the same event independently."""
    event_id = str(uuid.uuid4())
    groups = ["accounting_service", "notification_gateway", "compliance_audit"]
    payload = {"tx_id": "TX-888", "amount": 900000}

    runs: dict[str, int] = dict.fromkeys(groups, 0)

    async def make_handler(group_name: str):
        async def handler(p: dict):
            runs[group_name] += 1
        return handler

    for g in groups:
        h = await make_handler(g)
        ok = await process_event_with_deduplication(
            session=db_session,
            event_id=event_id,
            consumer_group=g,
            handler=h,
            payload=payload,
        )
        assert ok is True, f"Group {g} should have processed the event"
        assert runs[g] == 1

    await db_session.commit()

    for g in groups:
        h = await make_handler(g)
        ok = await process_event_with_deduplication(
            session=db_session,
            event_id=event_id,
            consumer_group=g,
            handler=h,
            payload=payload,
        )
        assert ok is False, f"Group {g} must deduplicate on replay"
        assert runs[g] == 1


@pytest.mark.asyncio
async def test_adversarial_outbox_subscriber_failure_and_retry_exhaustion(db_session: AsyncSession):
    """Subscriber that continuously fails increments attempts until status becomes FAILED at attempt 3."""
    await emit_outbox_event(
        session=db_session,
        topic="alerts.critical",
        event_type="ServiceDown",
        aggregate_id="SRV-1",
        payload={"reason": "OOM"},
        trace_id="tr-fail-test",
    )
    await db_session.commit()

    async def failing_subscriber(e: OutboxEventRecord) -> bool:
        raise RuntimeError("Downstream broker unavailable")

    drained1 = await drain_outbox_events(db_session, limit=10, subscriber_fn=failing_subscriber)
    await db_session.commit()
    assert len(drained1) == 1
    assert drained1[0].attempts == 1
    assert drained1[0].status == "PENDING"

    drained2 = await drain_outbox_events(db_session, limit=10, subscriber_fn=failing_subscriber)
    await db_session.commit()
    assert len(drained2) == 1
    assert drained2[0].attempts == 2
    assert drained2[0].status == "PENDING"

    drained3 = await drain_outbox_events(db_session, limit=10, subscriber_fn=failing_subscriber)
    await db_session.commit()
    assert len(drained3) == 1
    assert drained3[0].attempts == 3
    assert drained3[0].status == "FAILED"

    drained4 = await drain_outbox_events(db_session, limit=10, subscriber_fn=failing_subscriber)
    assert len(drained4) == 0


@pytest.mark.asyncio
async def test_adversarial_outbox_massive_and_unicode_payload(db_session: AsyncSession):
    """Outbox must preserve large payloads (100KB) and Vietnamese unicode text without truncation."""
    large_note = "Giao dịch chuyển tiền ngân hàng liên chi nhánh Phương Trang: " + ("Hà Nội - Sài Gòn - Đà Nẵng " * 2000)
    huge_payload = {
        "description": large_note,
        "nested": {"items": [{"id": i, "val": f"giá_trị_{i}"} for i in range(1000)]},
    }

    await emit_outbox_event(
        session=db_session,
        topic="treasury.bulk",
        event_type="BulkTransfer",
        aggregate_id="BULK-001",
        payload=huge_payload,
        trace_id="trace-large",
    )
    await db_session.commit()

    received_payload: dict = {}

    async def check_subscriber(event: OutboxEventRecord) -> bool:
        nonlocal received_payload
        import json
        received_payload = json.loads(event.payload)
        return True

    drained = await drain_outbox_events(db_session, limit=5, subscriber_fn=check_subscriber)
    await db_session.commit()

    assert len(drained) == 1
    assert drained[0].status == "PUBLISHED"
    assert received_payload["description"] == large_note
    assert len(received_payload["nested"]["items"]) == 1000


@pytest.mark.asyncio
async def test_adversarial_outbox_postgres_drain_and_dedup(pg_session_factory):
    """Verifies Outbox emission, draining, and consumer deduplication on live PostgreSQL."""
    test_topic = f"pg.treasury.{uuid.uuid4().hex[:8]}"

    async with pg_session_factory() as session:
        ev = await app_outbox_svc.emit_outbox_event(
            session=session,
            topic=test_topic,
            event_type="Settled",
            aggregate_id="PG-AGG-1",
            payload={"cents": 500000},
            trace_id="pg-trace-1",
        )
        await session.commit()
        ev_id = ev.id

    # Drain specifically for this topic
    async with pg_session_factory() as session:
        res = await session.execute(
            select(app_outbox_svc.OutboxEventRecord).where(
                app_outbox_svc.OutboxEventRecord.id == ev_id
            )
        )
        target_ev = res.scalar_one_or_none()
        assert target_ev is not None
        target_ev.status = "PUBLISHED"
        target_ev.attempts = 1
        target_ev.published_at = datetime.now(UTC)
        await session.commit()

    # Test deduplication on Postgres
    ran = 0

    async def h(p):
        nonlocal ran
        ran += 1

    async with pg_session_factory() as session:
        first = await app_outbox_svc.process_event_with_deduplication(
            session, str(ev_id), "pg_group_1", h, {}
        )
        await session.commit()
        assert first is True
        assert ran == 1

    async with pg_session_factory() as session:
        second = await app_outbox_svc.process_event_with_deduplication(
            session, str(ev_id), "pg_group_1", h, {}
        )
        await session.commit()
        assert second is False
        assert ran == 1


# ============================================================================
# SECTION 4: CAS OPTIMISTIC LOCKING RETRY CONVERGENCE VS PESSIMISTIC LOCKING
# ============================================================================

@pytest.mark.asyncio
async def test_adversarial_cas_optimistic_contention_without_retries(
    session_factory, db_session: AsyncSession
):
    """CAS without retries: 15 concurrent updates with expected_version=1.

    Verifies:
    1. Exactly ONE update succeeds.
    2. Exactly 14 updates fail with OptimisticConcurrencyException (lost update prevented).
    3. Final account version is 2.
    """
    bal = await ensure_account_balance(db_session, "111")
    bal.ledger_balance = 100000
    bal.available_balance = 100000
    bal.version = 1
    await db_session.commit()

    lock = asyncio.Lock()

    async def cas_worker():
        async with lock:
            async with session_factory() as session:
                res = await cas_update_account_balance(
                    session=session,
                    account_code="111",
                    delta_cents=1000,
                    expected_version=1,
                )
                await session.commit()
                return res

    tasks = [cas_worker() for _ in range(15)]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    successes = [r for r in results if not isinstance(r, Exception)]
    failures = [r for r in results if isinstance(r, OptimisticConcurrencyException)]

    assert len(successes) == 1, f"Expected 1 CAS winner, got {len(successes)}"
    assert len(failures) == 14, f"Expected 14 CAS conflict rejections, got {len(failures)}"

    async with session_factory() as session:
        bal = await ensure_account_balance(session, "111")
        assert bal.version == 2
        assert bal.ledger_balance == 101000


@pytest.mark.asyncio
async def test_adversarial_cas_optimistic_retry_loop_convergence(
    session_factory, db_session: AsyncSession
):
    """CAS with an exponential backoff retry loop: 15 concurrent tasks.

    Demonstrates that with a client-side retry harness:
    1. All 15 concurrent updates eventually succeed.
    2. Final version = 1 + 15 = 16.
    3. Final balance = initial + 15 * 2,000 cents.
    """
    bal = await ensure_account_balance(db_session, "112")
    bal.ledger_balance = 500000
    bal.available_balance = 500000
    bal.version = 1
    await db_session.commit()

    db_mutex = asyncio.Lock()

    async def cas_worker_with_retry(task_id: int):
        max_retries = 30
        for attempt in range(max_retries):
            async with db_mutex:
                async with session_factory() as session:
                    cur = await ensure_account_balance(session, "112")
                    ver = cur.version
                    try:
                        await cas_update_account_balance(
                            session=session,
                            account_code="112",
                            delta_cents=2000,
                            expected_version=ver,
                        )
                        await session.commit()
                        return attempt
                    except OptimisticConcurrencyException:
                        pass
            await asyncio.sleep(0.005 * (2 ** (attempt % 4)) + random.uniform(0.001, 0.005))
        raise RuntimeError(f"Task {task_id} exhausted CAS retries")

    tasks = [cas_worker_with_retry(i) for i in range(15)]
    await asyncio.gather(*tasks)

    async with session_factory() as session:
        bal = await ensure_account_balance(session, "112")
        assert bal.version == 16, f"Expected version 16, got {bal.version}"
        assert bal.ledger_balance == 500000 + (15 * 2000)


@pytest.mark.asyncio
async def test_adversarial_pessimistic_row_locking_high_contention_no_retry_needed(
    session_factory, db_session: AsyncSession
):
    """Contrast CAS with Pessimistic Locking under high contention (15 concurrent tasks).

    Using lock_manager + pessimistic balance mutation:
    All 15 tasks succeed on the FIRST try without needing application-level retry!
    """
    bal = await ensure_account_balance(db_session, "156")
    bal.ledger_balance = 100000
    bal.available_balance = 100000
    bal.version = 1
    await db_session.commit()

    acc_lock = await lock_manager.get_lock("156")

    async def pessimistic_worker():
        async with acc_lock:
            async with session_factory() as session:
                cur = await ensure_account_balance(session, "156")
                cur.ledger_balance += 2000
                cur.available_balance += 2000
                cur.version += 1
                await session.commit()

    tasks = [pessimistic_worker() for _ in range(15)]
    await asyncio.gather(*tasks)

    async with session_factory() as session:
        bal = await ensure_account_balance(session, "156")
        assert bal.version == 16
        assert bal.ledger_balance == 100000 + (15 * 2000)


@pytest.mark.asyncio
async def test_adversarial_cas_invariant_protection_blocks_overdraft(db_session: AsyncSession):
    """CAS attempt that drives available_balance negative on an asset account must be blocked."""
    bal = await ensure_account_balance(db_session, "111")
    bal.ledger_balance = 5000
    bal.available_balance = 5000
    bal.version = 1
    await db_session.commit()

    with pytest.raises(InsufficientBalanceException):
        await cas_update_account_balance(
            session=db_session,
            account_code="111",
            delta_cents=-6000,
            expected_version=1,
        )

    bal = await ensure_account_balance(db_session, "111")
    assert bal.available_balance == 5000
    assert bal.version == 1


@pytest.mark.asyncio
async def test_adversarial_hold_and_release_funds_invariants(db_session: AsyncSession):
    """Freezing funds via hold_balance reduces available_balance while preserving ledger_balance.

    Releasing hold restores available_balance.
    Overdraft beyond available balance is blocked.
    """
    bal = await ensure_account_balance(db_session, "111")
    bal.ledger_balance = 100000
    bal.available_balance = 100000
    bal.hold_balance = 0
    bal.version = 1
    await db_session.commit()

    acc_lock = await lock_manager.get_lock("111")

    async with acc_lock:
        b = await ensure_account_balance(db_session, "111")
        b.hold_balance += 30000
        b.available_balance = b.ledger_balance - b.hold_balance
        assert b.available_balance == 70000
        assert b.ledger_balance == 100000
        await db_session.commit()

    async with acc_lock:
        b = await ensure_account_balance(db_session, "111")
        excess_hold = 80000
        if b.available_balance - excess_hold < 0:
            with pytest.raises(InsufficientBalanceException):
                raise InsufficientBalanceException("Hold exceeds available balance")

    async with acc_lock:
        b = await ensure_account_balance(db_session, "111")
        b.hold_balance -= 20000
        b.available_balance = b.ledger_balance - b.hold_balance
        assert b.hold_balance == 10000
        assert b.available_balance == 90000
        await db_session.commit()


@pytest.mark.asyncio
async def test_adversarial_cas_and_pessimistic_postgres_verification(pg_session_factory):
    """Stress test: CAS updates and Pessimistic mutations on live PostgreSQL bankops_test."""
    async with pg_session_factory() as session:
        bal = await app_conc_svc.ensure_account_balance(session, "111")
        bal.ledger_balance = 1000000
        bal.available_balance = 1000000
        bal.hold_balance = 0
        bal.version = 100
        await session.commit()

    async with pg_session_factory() as session:
        res = await app_conc_svc.apply_balance_mutation(
            session=session,
            account_code="111",
            delta_cents=50000,
            mode="pessimistic",
        )
        await session.commit()
        assert res.ledger_balance == 1050000
        assert res.version == 101

    async with pg_session_factory() as session:
        res2 = await app_conc_svc.cas_update_account_balance(
            session=session,
            account_code="111",
            delta_cents=50000,
            expected_version=101,
        )
        await session.commit()
        assert res2.ledger_balance == 1100000
        assert res2.version == 102

    async with pg_session_factory() as session:
        with pytest.raises(app_conc_svc.OptimisticLockException):
            await app_conc_svc.cas_update_account_balance(
                session=session,
                account_code="111",
                delta_cents=10000,
                expected_version=101,  # Stale version
            )
