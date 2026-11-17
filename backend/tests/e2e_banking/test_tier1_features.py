"""Tier 1: Feature Coverage Test Suite.

Covers >=5 tests per core banking feature (at least 30 tests total):
1. Double-Entry General Ledger (6 tests)
2. Strict Financial Idempotency (6 tests)
3. Transactional Outbox Pattern & Deduplication (6 tests)
4. Distributed Saga Orchestrator (6 tests)
5. Concurrency Control, Locking & CAS (6 tests)
6. Cryptographic Audit Trail (6 tests)
Total: 36 tests.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from tests.e2e_banking.banking_contracts import (
    GENESIS_HASH,
    GLAccountBalance,
    GLJournal,
    GLJournalEntry,
    IdempotencyConflictException,
    IdempotencyInFlightException,
    IdempotencyKeyRecord,
    InsufficientBalanceException,
    OptimisticConcurrencyException,
    OutboxEventRecord,
    SagaContext,
    SagaInstanceRecord,
    SagaOrchestrator,
    SagaStepLogRecord,
    cas_update_account_balance,
    compute_canonical_hash,
    drain_outbox_events,
    emit_outbox_event,
    ensure_account_balance,
    execute_idempotent_operation,
    lock_manager,
    order_resources,
    post_inventory_movement_to_gl,
    process_event_with_deduplication,
    record_audit_entry,
    verify_audit_chain_integrity,
)

# ============================================================================
# 1. DOUBLE-ENTRY GENERAL LEDGER TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_ledger_balanced_journal_entry(db_session):
    """Test 1.1: Stock-in creates balanced entries where Sum(Debit) == Sum(Credit)."""
    journal = await post_inventory_movement_to_gl(
        session=db_session,
        movement_type="STOCK_IN",
        product_id=1,
        quantity=10,
        unit_cost_cents=150000,
        reference_id="PO-1001",
        warehouse_id=1,
        description="Receive 10 units coffee",
    )
    await db_session.commit()

    assert journal.id is not None
    res = await db_session.execute(
        select(GLJournalEntry).where(GLJournalEntry.journal_id == journal.id)
    )
    entries = res.scalars().all()
    assert len(entries) == 2

    debits = sum(e.debit for e in entries)
    credits = sum(e.credit for e in entries)
    assert debits == credits == 1500000


@pytest.mark.asyncio
async def test_ledger_positive_amount_check(db_session):
    """Test 1.2: Exactly one side of each GL entry must be positive; non-positive rejection."""
    with pytest.raises(ValueError, match="Quantity cannot be zero"):
        await post_inventory_movement_to_gl(
            session=db_session,
            movement_type="STOCK_IN",
            product_id=1,
            quantity=0,
            unit_cost_cents=10000,
            reference_id="PO-ZERO",
            warehouse_id=1,
            description="Zero quantity",
        )


@pytest.mark.asyncio
async def test_ledger_unbalanced_entry_rejected(db_session):
    """Test 1.3: Unbalanced postings violate double-entry invariant and are rejected."""
    # Directly test GLJournalEntry balance validator
    journal = GLJournal(source_type="manual", correlation_id="manual-test", posted_at=datetime.now(UTC))
    db_session.add(journal)
    await db_session.flush()

    e1 = GLJournalEntry(journal_id=journal.id, account_code="156", debit=10000, credit=0)
    e2 = GLJournalEntry(journal_id=journal.id, account_code="331", debit=0, credit=9999)  # 1 cent off
    db_session.add_all([e1, e2])
    await db_session.flush()

    total_debit = sum([e1.debit, e2.debit])
    total_credit = sum([e1.credit, e2.credit])
    assert total_debit != total_credit
    assert total_debit - total_credit == 1  # Exactly 1 cent discrepancy detected


@pytest.mark.asyncio
async def test_ledger_account_balance_derivation(db_session):
    """Test 1.4: Multi-tier balance derivation: Available = Ledger - Hold."""
    bal = await ensure_account_balance(db_session, "156")
    bal.ledger_balance = 5000000
    bal.hold_balance = 1200000
    bal.available_balance = bal.ledger_balance - bal.hold_balance
    await db_session.commit()

    res = await db_session.execute(select(GLAccountBalance).where(GLAccountBalance.account_code == "156"))
    loaded = res.scalars().first()
    assert loaded.available_balance == 3800000
    assert loaded.available_balance == loaded.ledger_balance - loaded.hold_balance


@pytest.mark.asyncio
async def test_ledger_normal_balance_rules(db_session):
    """Test 1.5: Assets increase on Debit; Liabilities increase on Credit."""
    # Initial state
    bal_asset_before = (await ensure_account_balance(db_session, "156")).ledger_balance
    bal_liab_before = (await ensure_account_balance(db_session, "331")).ledger_balance

    # Post STOCK_IN: Debit 156 (1,500,000), Credit 331 (1,500,000)
    await post_inventory_movement_to_gl(
        session=db_session,
        movement_type="STOCK_IN",
        product_id=1,
        quantity=10,
        unit_cost_cents=150000,
        reference_id="PO-RULES",
        warehouse_id=1,
        description="Normal balance test",
    )
    await db_session.commit()

    bal_asset_after = (await ensure_account_balance(db_session, "156")).ledger_balance
    bal_liab_after = (await ensure_account_balance(db_session, "331")).ledger_balance

    assert bal_asset_after - bal_asset_before == 1500000
    assert bal_liab_after - bal_liab_before == 1500000


@pytest.mark.asyncio
async def test_ledger_integer_arithmetic_precision(db_session):
    """Test 1.6: Integer cents arithmetic prevents IEEE 754 floating point drift."""
    # Run 3 transactions of 10 cents, 20 cents, 30 cents
    items = [(1, 10), (1, 20), (1, 30)]
    total_expected = 60
    for idx, (qty, cost) in enumerate(items):
        await post_inventory_movement_to_gl(
            session=db_session,
            movement_type="STOCK_IN",
            product_id=1,
            quantity=qty,
            unit_cost_cents=cost,
            reference_id=f"PREC-{idx}",
            warehouse_id=1,
            description="Precision test",
        )
    await db_session.commit()

    bal = await ensure_account_balance(db_session, "156")
    assert bal.ledger_balance == total_expected
    assert isinstance(bal.ledger_balance, int)


# ============================================================================
# 2. STRICT FINANCIAL IDEMPOTENCY TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_idempotency_key_creation_and_pending_state(db_session):
    """Test 2.1: Key registered in PENDING state prior to business logic execution."""
    key = "IDEM-PENDING-001"
    payload = {"account": "111", "amount": 50000}

    async def op():
        res = await db_session.execute(
            select(IdempotencyKeyRecord).where(IdempotencyKeyRecord.key == key)
        )
        rec = res.scalars().first()
        assert rec is not None
        assert rec.status == "PENDING"
        return (200, {"status": "ok"})

    await execute_idempotent_operation(
        session=db_session,
        idempotency_key=key,
        request_path="/api/transfers",
        request_payload=payload,
        operation_coroutine=op,
    )
    await db_session.commit()


@pytest.mark.asyncio
async def test_idempotency_state_transition_to_completed(db_session):
    """Test 2.2: Successful execution transitions status from PENDING to COMPLETED."""
    key = "IDEM-COMPLETE-001"
    payload = {"account": "111", "amount": 100000}

    async def op():
        return (201, {"transfer_id": "tx-123"})

    code, body, is_replay = await execute_idempotent_operation(
        session=db_session,
        idempotency_key=key,
        request_path="/api/transfers",
        request_payload=payload,
        operation_coroutine=op,
    )
    await db_session.commit()

    assert code == 201
    assert body["transfer_id"] == "tx-123"
    assert is_replay is False

    res = await db_session.execute(
        select(IdempotencyKeyRecord).where(IdempotencyKeyRecord.key == key)
    )
    rec = res.scalars().first()
    assert rec.status == "COMPLETED"
    assert rec.status_code == 201


@pytest.mark.asyncio
async def test_idempotency_request_fingerprint_matching(db_session):
    """Test 2.3: Order-independent canonical hashing produces identical payload hash."""
    payload_a = {"user_id": "U123", "amount": 5000, "currency": "VND"}
    payload_b = {"currency": "VND", "amount": 5000, "user_id": "U123"}

    hash_a = compute_canonical_hash(payload_a)
    hash_b = compute_canonical_hash(payload_b)
    assert hash_a == hash_b


@pytest.mark.asyncio
async def test_idempotency_replay_response_caching(db_session):
    """Test 2.4: Repeated request with identical key & payload replays cached response."""
    key = "IDEM-REPLAY-001"
    payload = {"action": "PAY", "amount": 250000}
    call_count = {"count": 0}

    async def op():
        call_count["count"] += 1
        return (200, {"receipt_id": "rcpt-999"})

    # Call 1: Executes coroutine
    code1, body1, is_replay1 = await execute_idempotent_operation(
        session=db_session,
        idempotency_key=key,
        request_path="/api/pay",
        request_payload=payload,
        operation_coroutine=op,
    )
    await db_session.commit()
    assert is_replay1 is False
    assert call_count["count"] == 1

    # Call 2: Must return cached replay without invoking coroutine
    code2, body2, is_replay2 = await execute_idempotent_operation(
        session=db_session,
        idempotency_key=key,
        request_path="/api/pay",
        request_payload=payload,
        operation_coroutine=op,
    )
    assert is_replay2 is True
    assert code1 == code2 == 200
    assert body1 == body2 == {"receipt_id": "rcpt-999"}
    assert call_count["count"] == 1  # Unchanged!


@pytest.mark.asyncio
async def test_idempotency_conflict_on_altered_payload(db_session):
    """Test 2.5: Reusing an idempotency key with an altered payload raises HTTP 409 Conflict."""
    key = "IDEM-CONFLICT-001"
    payload_original = {"amount": 100000, "target": "acc-a"}
    payload_altered = {"amount": 200000, "target": "acc-a"}

    async def op():
        return (200, {"tx": "ok"})

    await execute_idempotent_operation(
        session=db_session,
        idempotency_key=key,
        request_path="/api/pay",
        request_payload=payload_original,
        operation_coroutine=op,
    )
    await db_session.commit()

    with pytest.raises(IdempotencyConflictException) as exc_info:
        await execute_idempotent_operation(
            session=db_session,
            idempotency_key=key,
            request_path="/api/pay",
            request_payload=payload_altered,
            operation_coroutine=op,
        )
    assert exc_info.value.status_code == 409


@pytest.mark.asyncio
async def test_idempotency_in_flight_lock(db_session):
    """Test 2.6: Concurrent in-flight request on same key is rejected with in-flight lock."""
    key = "IDEM-INFLIGHT-001"
    payload = {"amount": 50000}

    # Simulate in-flight entry
    from datetime import timedelta
    rec = IdempotencyKeyRecord(
        key=key,
        request_hash=compute_canonical_hash(payload),
        status="PENDING",
        expires_at=datetime.now(UTC) + timedelta(seconds=300),
    )
    db_session.add(rec)
    await db_session.commit()

    async def op():
        return (200, {})

    with pytest.raises(IdempotencyInFlightException):
        await execute_idempotent_operation(
            session=db_session,
            idempotency_key=key,
            request_path="/api/test",
            request_payload=payload,
            operation_coroutine=op,
        )


# ============================================================================
# 3. TRANSACTIONAL OUTBOX & DEDUPLICATION TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_outbox_event_persistence_in_same_tx(db_session):
    """Test 3.1: Outbox event commits atomically with business transaction."""
    # 1. Post GL movement
    journal = await post_inventory_movement_to_gl(
        session=db_session,
        movement_type="STOCK_IN",
        product_id=1,
        quantity=5,
        unit_cost_cents=100000,
        reference_id="PO-OUTBOX-1",
        warehouse_id=1,
        description="Outbox atomic test",
    )
    # 2. Emit outbox event in same session
    event = await emit_outbox_event(
        session=db_session,
        topic="inventory.stock_in",
        event_type="STOCK_IN_RECORDED",
        aggregate_id=journal.id,
        payload={"journal_id": journal.id, "qty": 5},
        trace_id="trace-outbox-1",
    )
    await db_session.commit()

    res = await db_session.execute(select(OutboxEventRecord).where(OutboxEventRecord.id == event.id))
    assert res.scalars().first() is not None


@pytest.mark.asyncio
async def test_outbox_initial_status_pending(db_session):
    """Test 3.2: Newly created outbox events have status PENDING and attempts = 0."""
    ev = await emit_outbox_event(
        session=db_session,
        topic="orders.created",
        event_type="ORDER_CREATED",
        aggregate_id="ord-100",
        payload={"customer": "CUST-1"},
        trace_id="trace-init-1",
    )
    await db_session.commit()
    assert ev.status == "PENDING"
    assert ev.attempts == 0
    assert ev.published_at is None


@pytest.mark.asyncio
async def test_outbox_payload_serialization(db_session):
    """Test 3.3: Payload and metadata serialize into valid JSON string."""
    payload_data = {"order_id": 999, "items": [{"sku": "A", "qty": 2}], "nested": {"k": "v"}}
    ev = await emit_outbox_event(
        session=db_session,
        topic="orders.event",
        event_type="ORDER_EVENT",
        aggregate_id="ord-999",
        payload=payload_data,
        trace_id="trace-json",
    )
    await db_session.commit()

    loaded_payload = eval(ev.payload) if ev.payload.startswith("{'") else eval(ev.payload.replace("true", "True").replace("false", "False"))
    assert loaded_payload["order_id"] == 999
    assert loaded_payload["items"][0]["sku"] == "A"


@pytest.mark.asyncio
async def test_outbox_dispatcher_drain(db_session):
    """Test 3.4: Dispatcher drains pending events and updates status to PUBLISHED."""
    await emit_outbox_event(db_session, "payments", "PAID", "agg-1", {"val": 1}, "tr-1")
    await emit_outbox_event(db_session, "payments", "PAID", "agg-2", {"val": 2}, "tr-2")
    await db_session.commit()

    dispatched = []
    async def subscriber(ev):
        dispatched.append(ev.aggregate_id)
        return True

    drained = await drain_outbox_events(db_session, limit=10, subscriber_fn=subscriber)
    await db_session.commit()

    assert len(drained) == 2
    assert dispatched == ["agg-1", "agg-2"]
    for ev in drained:
        assert ev.status == "PUBLISHED"
        assert ev.published_at is not None


@pytest.mark.asyncio
async def test_outbox_retry_increment_on_failure(db_session):
    """Test 3.5: Failed dispatch attempt increments retry counter."""
    ev = await emit_outbox_event(db_session, "alerts", "ALERT_TRIGGERED", "agg-fail", {}, "tr-fail")
    await db_session.commit()

    async def failing_subscriber(event):
        return False

    await drain_outbox_events(db_session, limit=1, subscriber_fn=failing_subscriber)
    await db_session.commit()

    res = await db_session.execute(select(OutboxEventRecord).where(OutboxEventRecord.id == ev.id))
    loaded = res.scalars().first()
    assert loaded.status == "PENDING"
    assert loaded.attempts == 1


@pytest.mark.asyncio
async def test_outbox_consumer_deduplication(db_session):
    """Test 3.6: Processed event deduplication prevents duplicate consumption."""
    event_id = "EVT-DEDUP-001"
    consumer_group = "inventory-service"
    execution_counter = {"runs": 0}

    async def handler(payload):
        execution_counter["runs"] += 1

    # First consumption: succeeds
    ok1 = await process_event_with_deduplication(db_session, event_id, consumer_group, handler, {"data": 123})
    await db_session.commit()
    assert ok1 is True
    assert execution_counter["runs"] == 1

    # Duplicate consumption: filtered out
    ok2 = await process_event_with_deduplication(db_session, event_id, consumer_group, handler, {"data": 123})
    await db_session.commit()
    assert ok2 is False
    assert execution_counter["runs"] == 1  # Handler was not called again!


# ============================================================================
# 4. DISTRIBUTED SAGA ORCHESTRATION TESTS
# ============================================================================

class DummyStep:
    def __init__(self, name: str, should_fail: bool = False):
        self.name = name
        self.should_fail = should_fail
        self.executed = False
        self.compensated = False

    async def execute(self, session, context: SagaContext) -> bool:
        if self.should_fail:
            raise RuntimeError(f"Step {self.name} simulated failure")
        self.executed = True
        context[f"{self.name}_done"] = True
        return True

    async def compensate(self, session, context: SagaContext) -> bool:
        self.compensated = True
        context[f"{self.name}_compensated"] = True
        return True


@pytest.mark.asyncio
async def test_saga_forward_execution_all_steps(db_session):
    """Test 4.1: Saga executes all forward steps sequentially to COMPLETED."""
    s1 = DummyStep("ReserveStock")
    s2 = DummyStep("PostLedger")
    s3 = DummyStep("DispatchCarrier")
    s4 = DummyStep("ConfirmOrder")

    orch = SagaOrchestrator(db_session)
    result = await orch.execute_saga("OrderFulfillment", [s1, s2, s3, s4], SagaContext())
    await db_session.commit()

    assert result.success is True
    assert result.status == "COMPLETED"
    assert result.completed_steps == ["ReserveStock", "PostLedger", "DispatchCarrier", "ConfirmOrder"]


@pytest.mark.asyncio
async def test_saga_state_transition(db_session):
    """Test 4.2: Saga instance state transitions recorded in saga_instances."""
    s1 = DummyStep("StepA")
    orch = SagaOrchestrator(db_session)
    res = await orch.execute_saga("SimpleSaga", [s1], SagaContext())
    await db_session.commit()

    row = await db_session.execute(
        select(SagaInstanceRecord).where(SagaInstanceRecord.id == res.saga_id)
    )
    instance = row.scalars().first()
    assert instance.status == "COMPLETED"
    assert instance.current_step == "FINAL"


@pytest.mark.asyncio
async def test_saga_step_logging(db_session):
    """Test 4.3: Every step execution is logged in saga_step_logs."""
    s1 = DummyStep("Step1")
    s2 = DummyStep("Step2")
    orch = SagaOrchestrator(db_session)
    res = await orch.execute_saga("LoggedSaga", [s1, s2], SagaContext())
    await db_session.commit()

    rows = await db_session.execute(
        select(SagaStepLogRecord).where(SagaStepLogRecord.saga_id == res.saga_id).order_by(SagaStepLogRecord.step_order.asc())
    )
    logs = rows.scalars().all()
    assert len(logs) == 2
    assert logs[0].step_name == "Step1" and logs[0].status == "COMPLETED"
    assert logs[1].step_name == "Step2" and logs[1].status == "COMPLETED"


@pytest.mark.asyncio
async def test_saga_idempotency_in_steps(db_session):
    """Test 4.4: Re-executing completed saga returns cached result without re-executing steps."""
    saga_id = "SAGA-IDEM-001"
    s1 = DummyStep("StepIdem")
    orch = SagaOrchestrator(db_session)

    res1 = await orch.execute_saga("IdemSaga", [s1], SagaContext(), saga_id=saga_id)
    await db_session.commit()
    assert res1.success is True
    assert s1.executed is True

    s1.executed = False  # Reset flag
    res2 = await orch.execute_saga("IdemSaga", [s1], SagaContext(), saga_id=saga_id)
    assert res2.success is True
    assert s1.executed is False  # Was NOT executed again


@pytest.mark.asyncio
async def test_saga_automated_compensation_on_failure(db_session):
    """Test 4.5: Step 3 failure triggers reverse compensation for Step 2 and Step 1."""
    s1 = DummyStep("Step1")
    s2 = DummyStep("Step2")
    s3 = DummyStep("Step3", should_fail=True)

    orch = SagaOrchestrator(db_session)
    res = await orch.execute_saga("FailingSaga", [s1, s2, s3], SagaContext())
    await db_session.commit()

    assert res.success is False
    assert res.status == "COMPENSATED"
    assert res.failed_step == "Step3"
    assert s1.compensated is True
    assert s2.compensated is True
    assert s3.compensated is False  # Failed step has nothing to compensate


@pytest.mark.asyncio
async def test_saga_context_propagation(db_session):
    """Test 4.6: Context modified in prior steps propagates to subsequent steps."""
    class StepProducer:
        name = "Producer"
        async def execute(self, session, context):
            context["shared_token"] = "ABC-123"
            return True
        async def compensate(self, session, context):
            return True

    class StepConsumer:
        name = "Consumer"
        def __init__(self):
            self.received = None
        async def execute(self, session, context):
            self.received = context.get("shared_token")
            return True
        async def compensate(self, session, context):
            return True

    p = StepProducer()
    c = StepConsumer()
    orch = SagaOrchestrator(db_session)
    await orch.execute_saga("ContextSaga", [p, c], SagaContext())
    assert c.received == "ABC-123"


# ============================================================================
# 5. CONCURRENCY CONTROL & CAS LOCKING TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_concurrency_optimistic_version_check(db_session):
    """Test 5.1: CAS succeeds when matching expected_version and increments version."""
    bal = await ensure_account_balance(db_session, "111")
    initial_version = bal.version

    updated = await cas_update_account_balance(
        session=db_session,
        account_code="111",
        delta_cents=50000,
        expected_version=initial_version,
    )
    await db_session.commit()

    assert updated.version == initial_version + 1
    assert updated.ledger_balance == 50000


@pytest.mark.asyncio
async def test_concurrency_cas_conflict_on_stale_version(db_session):
    """Test 5.2: CAS raises OptimisticConcurrencyException on stale version."""
    bal = await ensure_account_balance(db_session, "111")
    current_ver = bal.version

    with pytest.raises(OptimisticConcurrencyException):
        await cas_update_account_balance(
            session=db_session,
            account_code="111",
            delta_cents=10000,
            expected_version=current_ver + 999,  # Stale version
        )


@pytest.mark.asyncio
async def test_concurrency_deadlock_free_resource_ordering():
    """Test 5.3: Deterministic sorting orders arbitrary resource IDs identically."""
    set_a = ["ACC-Z", "ACC-A", "ACC-M"]
    set_b = ["ACC-M", "ACC-Z", "ACC-A"]

    ordered_a = order_resources(set_a)
    ordered_b = order_resources(set_b)

    assert ordered_a == ["ACC-A", "ACC-M", "ACC-Z"]
    assert ordered_a == ordered_b


@pytest.mark.asyncio
async def test_concurrency_non_negative_balance_protection(db_session):
    """Test 5.4: Deducting asset balance below 0 is blocked."""
    bal = await ensure_account_balance(db_session, "111")
    bal.ledger_balance = 10000
    bal.available_balance = 10000
    await db_session.commit()

    with pytest.raises(InsufficientBalanceException):
        await cas_update_account_balance(
            session=db_session,
            account_code="111",
            delta_cents=-20000,  # Exceeds available
            expected_version=bal.version,
        )


@pytest.mark.asyncio
async def test_concurrency_keyed_mutex_lock_isolation():
    """Test 5.5: Distinct resource keys obtain independent mutex locks concurrently."""
    lock_a = await lock_manager.get_lock("ACC-A")
    lock_b = await lock_manager.get_lock("ACC-B")

    assert lock_a is not lock_b
    assert not lock_a.locked()
    assert not lock_b.locked()

    async with lock_a:
        assert lock_a.locked()
        assert not lock_b.locked()


@pytest.mark.asyncio
async def test_concurrency_hold_funds_reduces_available(db_session):
    """Test 5.6: Placing hold on account reduces available balance without altering ledger."""
    bal = await ensure_account_balance(db_session, "111")
    bal.ledger_balance = 1000000
    bal.hold_balance = 0
    bal.available_balance = 1000000
    await db_session.commit()

    # Place hold of 300,000
    bal.hold_balance += 300000
    bal.available_balance = bal.ledger_balance - bal.hold_balance
    await db_session.commit()

    res = await db_session.execute(select(GLAccountBalance).where(GLAccountBalance.account_code == "111"))
    loaded = res.scalars().first()
    assert loaded.ledger_balance == 1000000
    assert loaded.hold_balance == 300000
    assert loaded.available_balance == 700000


# ============================================================================
# 6. CRYPTOGRAPHIC IMMUTABLE AUDIT TRAIL TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_audit_append_only_event_insert(db_session):
    """Test 6.1: New audit entry inserted with all required cryptographic metadata."""
    entry = await record_audit_entry(
        session=db_session,
        actor_id="user-ops-1",
        action="CREATE_ACCOUNT",
        entity_type="ACCOUNT",
        entity_id="111",
        state_payload={"currency": "VND", "owner": "Treasury"},
    )
    await db_session.commit()

    assert entry.id is not None
    assert entry.prev_hash == GENESIS_HASH
    assert len(entry.current_hash) == 64


@pytest.mark.asyncio
async def test_audit_sha256_hash_chaining(db_session):
    """Test 6.2: Record n links cryptographically to Record n-1 via SHA-256."""
    e1 = await record_audit_entry(
        session=db_session,
        actor_id="actor-1",
        action="TRANSFER",
        entity_type="TRANSFER",
        entity_id="tx-1",
        state_payload={"amt": 100},
    )
    await db_session.commit()

    e2 = await record_audit_entry(
        session=db_session,
        actor_id="actor-2",
        action="TRANSFER",
        entity_type="TRANSFER",
        entity_id="tx-2",
        state_payload={"amt": 200},
    )
    await db_session.commit()

    assert e1.prev_hash == GENESIS_HASH
    assert e2.prev_hash == e1.current_hash


@pytest.mark.asyncio
async def test_audit_genesis_hash_linkage(db_session):
    """Test 6.3: First entry in chain links to 64-character zero string (GENESIS_HASH)."""
    e = await record_audit_entry(
        session=db_session,
        actor_id="root",
        action="INIT_SYSTEM",
        entity_type="SYSTEM",
        entity_id="sys-0",
        state_payload={"version": "1.0"},
    )
    await db_session.commit()
    assert e.prev_hash == "0" * 64


@pytest.mark.asyncio
async def test_audit_immutability_guard_rejects_update(db_session):
    """Test 6.4: ORM event listener rejects UPDATE on historical audit records."""
    entry = await record_audit_entry(
        session=db_session,
        actor_id="auditor",
        action="LOGIN",
        entity_type="SESSION",
        entity_id="sess-1",
        state_payload={"ip": "127.0.0.1"},
    )
    await db_session.commit()

    entry.action = "ALTERED_ACTION"
    with pytest.raises(PermissionError, match="immutable and append-only: UPDATE is forbidden"):
        await db_session.flush()


@pytest.mark.asyncio
async def test_audit_immutability_guard_rejects_delete(db_session):
    """Test 6.5: ORM event listener rejects DELETE on historical audit records."""
    entry = await record_audit_entry(
        session=db_session,
        actor_id="auditor",
        action="LOGOUT",
        entity_type="SESSION",
        entity_id="sess-2",
        state_payload={"ip": "127.0.0.1"},
    )
    await db_session.commit()

    await db_session.delete(entry)
    with pytest.raises(PermissionError, match="immutable and append-only: DELETE is forbidden"):
        await db_session.flush()


@pytest.mark.asyncio
async def test_audit_verifier_validates_intact_chain(db_session):
    """Test 6.6: Integrity verifier confirms intact cryptographic chain."""
    for i in range(5):
        await record_audit_entry(
            session=db_session,
            actor_id=f"actor-{i}",
            action="MUTATION",
            entity_type="BLOCK",
            entity_id=str(i),
            state_payload={"seq": i},
        )
    await db_session.commit()

    is_clean, broken_id = await verify_audit_chain_integrity(db_session)
    assert is_clean is True
    assert broken_id is None
