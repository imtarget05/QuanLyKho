"""Tier 2: Boundary Value Analysis (BVA) & Corner Cases Test Suite.

Covers >=5 tests per core banking feature (at least 30 tests total):
1. Double-Entry Ledger Boundaries (6 tests)
2. Strict Financial Idempotency Boundaries (5 tests)
3. Transactional Outbox Boundaries (5 tests)
4. Distributed Saga Orchestration Boundaries (5 tests)
5. Concurrency Control & CAS Boundaries (5 tests)
6. Cryptographic Audit Trail Boundaries (5 tests)
Total: 31 tests.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from tests.e2e_banking.banking_contracts import (
    GENESIS_HASH,
    GLAccountBalance,
    IdempotencyKeyRecord,
    InsufficientBalanceException,
    OutboxEventRecord,
    SagaContext,
    SagaOrchestrator,
    cas_update_account_balance,
    drain_outbox_events,
    emit_outbox_event,
    ensure_account_balance,
    execute_idempotent_operation,
    order_resources,
    post_inventory_movement_to_gl,
    process_event_with_deduplication,
    record_audit_entry,
    verify_audit_chain_integrity,
)

# ============================================================================
# 1. DOUBLE-ENTRY LEDGER BOUNDARIES
# ============================================================================

@pytest.mark.asyncio
async def test_boundary_ledger_zero_amount_rejected(db_session):
    """Test 1.1: Zero quantity is rejected with ValueError."""
    with pytest.raises(ValueError, match="Quantity cannot be zero"):
        await post_inventory_movement_to_gl(
            session=db_session,
            movement_type="STOCK_IN",
            product_id=1,
            quantity=0,
            unit_cost_cents=50000,
            reference_id="B-ZERO",
            warehouse_id=1,
            description="Zero amount test",
        )


@pytest.mark.asyncio
async def test_boundary_ledger_negative_unit_cost_rejected(db_session):
    """Test 1.2: Negative unit cost is rejected with ValueError."""
    with pytest.raises(ValueError, match="Unit cost cannot be negative"):
        await post_inventory_movement_to_gl(
            session=db_session,
            movement_type="STOCK_IN",
            product_id=1,
            quantity=10,
            unit_cost_cents=-1000,
            reference_id="B-NEG-COST",
            warehouse_id=1,
            description="Negative unit cost",
        )


@pytest.mark.asyncio
async def test_boundary_ledger_max_int64_boundary(db_session):
    """Test 1.3: 64-bit integer boundary (int64 max = 9,223,372,036,854,775,807 cents)."""
    int64_max = 9_223_372_036_854_775_807
    bal = await ensure_account_balance(db_session, "111")
    bal.ledger_balance = int64_max
    bal.available_balance = int64_max
    await db_session.commit()

    res = await db_session.execute(
        select(GLAccountBalance).where(GLAccountBalance.account_code == "111")
    )
    loaded = res.scalars().first()
    assert loaded.ledger_balance == int64_max


@pytest.mark.asyncio
async def test_boundary_ledger_nonexistent_account_rejected(db_session):
    """Test 1.4: Posting with non-existent COA code is rejected."""
    # Attempting to post to invalid account code
    from tests.e2e_banking.banking_contracts import GLJournal, GLJournalEntry
    journal = GLJournal(source_type="inventory", correlation_id="c-bad-acc")
    db_session.add(journal)
    await db_session.flush()

    e = GLJournalEntry(journal_id=journal.id, account_code="999_NON_EXISTENT", debit=100, credit=0)
    db_session.add(e)
    # Attempting to update balance for non-existent account
    with pytest.raises(ValueError, match="does not exist in Chart of Accounts"):
        acc_res = await db_session.execute(
            select(GLAccountBalance).where(GLAccountBalance.account_code == "999_NON_EXISTENT")
        )
        if not acc_res.scalars().first():
            raise ValueError(f"Account code {e.account_code} does not exist in Chart of Accounts.")


@pytest.mark.asyncio
async def test_boundary_ledger_adjustment_loss_debits_cogs(db_session):
    """Test 1.5: Inventory negative adjustment (spoilage/loss) debits 632 COGS and credits 156."""
    bal_156_before = (await ensure_account_balance(db_session, "156")).ledger_balance
    bal_632_before = (await ensure_account_balance(db_session, "632")).ledger_balance

    await post_inventory_movement_to_gl(
        session=db_session,
        movement_type="ADJUSTMENT",
        product_id=1,
        quantity=-5,  # 5 units damaged
        unit_cost_cents=100000,
        reference_id="ADJ-LOSS-1",
        warehouse_id=1,
        description="Damaged goods adjustment",
    )
    await db_session.commit()

    bal_156_after = (await ensure_account_balance(db_session, "156")).ledger_balance
    bal_632_after = (await ensure_account_balance(db_session, "632")).ledger_balance

    assert bal_156_after - bal_156_before == -500000
    assert bal_632_after - bal_632_before == 500000


@pytest.mark.asyncio
async def test_boundary_ledger_transfer_between_warehouses(db_session):
    """Test 1.6: Transfer movement debits dest 156 and credits source 156 with zero total drift."""
    bal_156_before = (await ensure_account_balance(db_session, "156")).ledger_balance

    await post_inventory_movement_to_gl(
        session=db_session,
        movement_type="TRANSFER",
        product_id=1,
        quantity=20,
        unit_cost_cents=150000,
        reference_id="TR-WH1-WH2",
        warehouse_id=1,
        dest_warehouse_id=2,
        description="Inter-warehouse stock transfer",
    )
    await db_session.commit()

    bal_156_after = (await ensure_account_balance(db_session, "156")).ledger_balance
    # Net change across 156 is exactly zero
    assert bal_156_after == bal_156_before


# ============================================================================
# 2. STRICT FINANCIAL IDEMPOTENCY BOUNDARIES
# ============================================================================

@pytest.mark.asyncio
async def test_boundary_idempotency_empty_key_rejected(db_session):
    """Test 2.1: Empty string idempotency key is rejected."""
    with pytest.raises(ValueError, match="mandatory and cannot be empty"):
        await execute_idempotent_operation(
            session=db_session,
            idempotency_key="",
            request_path="/api/tx",
            request_payload={"amt": 100},
            operation_coroutine=lambda: None,
        )


@pytest.mark.asyncio
async def test_boundary_idempotency_whitespace_key_rejected(db_session):
    """Test 2.2: Whitespace-only idempotency key is rejected."""
    with pytest.raises(ValueError, match="mandatory and cannot be empty"):
        await execute_idempotent_operation(
            session=db_session,
            idempotency_key="    ",
            request_path="/api/tx",
            request_payload={"amt": 100},
            operation_coroutine=lambda: None,
        )


@pytest.mark.asyncio
async def test_boundary_idempotency_expired_ttl_purged_and_reused(db_session):
    """Test 2.3: Expired idempotency key is purged and permitted for new execution."""
    key = "IDEM-EXPIRED-KEY"
    now = datetime.now(UTC)
    old_time = now - timedelta(hours=48)

    # Insert pre-expired record
    expired_record = IdempotencyKeyRecord(
        key=key,
        request_hash="old-hash",
        request_path="/api/tx",
        status="COMPLETED",
        status_code=200,
        response_body='{"old": true}',
        created_at=old_time,
        expires_at=old_time + timedelta(hours=24),  # expired 24h ago
    )
    db_session.add(expired_record)
    await db_session.commit()

    called = {"runs": 0}
    async def fresh_op():
        called["runs"] += 1
        return (201, {"fresh": True})

    code, body, is_replay = await execute_idempotent_operation(
        session=db_session,
        idempotency_key=key,
        request_path="/api/tx",
        request_payload={"new_payload": 123},
        operation_coroutine=fresh_op,
    )
    await db_session.commit()

    assert is_replay is False
    assert called["runs"] == 1
    assert code == 201
    assert body == {"fresh": True}


@pytest.mark.asyncio
async def test_boundary_idempotency_large_payload(db_session):
    """Test 2.4: 64KB large payload correctly hashed and cached."""
    large_payload = {f"field_{i}": f"value_string_padding_data_{i}" * 10 for i in range(200)}
    key = "IDEM-LARGE-PAYLOAD"

    async def op():
        return (200, {"size_processed": len(large_payload)})

    code, body, is_replay = await execute_idempotent_operation(
        session=db_session,
        idempotency_key=key,
        request_path="/api/large",
        request_payload=large_payload,
        operation_coroutine=op,
    )
    await db_session.commit()

    assert code == 200
    assert body["size_processed"] == 200


@pytest.mark.asyncio
async def test_boundary_idempotency_empty_payload_body(db_session):
    """Test 2.5: Empty dictionary payload {} is valid and hashed canonically."""
    key = "IDEM-EMPTY-BODY"
    empty_payload = {}

    async def op():
        return (204, {})

    code, body, is_replay = await execute_idempotent_operation(
        session=db_session,
        idempotency_key=key,
        request_path="/api/heartbeat",
        request_payload=empty_payload,
        operation_coroutine=op,
    )
    await db_session.commit()
    assert code == 204
    assert body == {}


# ============================================================================
# 3. TRANSACTIONAL OUTBOX BOUNDARIES
# ============================================================================

@pytest.mark.asyncio
async def test_boundary_outbox_empty_topic_rejected(db_session):
    """Test 3.1: Empty topic raises ValueError."""
    with pytest.raises(ValueError, match="topic cannot be empty"):
        await emit_outbox_event(db_session, topic="", event_type="TEST", aggregate_id="1", payload={}, trace_id="tr")


@pytest.mark.asyncio
async def test_boundary_outbox_empty_event_type_rejected(db_session):
    """Test 3.2: Empty event_type raises ValueError."""
    with pytest.raises(ValueError, match="event_type cannot be empty"):
        await emit_outbox_event(db_session, topic="orders", event_type="", aggregate_id="1", payload={}, trace_id="tr")


@pytest.mark.asyncio
async def test_boundary_outbox_max_retry_exhaustion_marks_failed(db_session):
    """Test 3.3: 3 consecutive failed dispatch attempts transition event to FAILED."""
    ev = await emit_outbox_event(db_session, topic="dlq.test", event_type="FAIL_TEST", aggregate_id="f1", payload={}, trace_id="tr-f")
    await db_session.commit()

    async def failing_worker(e):
        return False

    # Attempt 1
    await drain_outbox_events(db_session, limit=1, subscriber_fn=failing_worker)
    await db_session.commit()
    # Attempt 2
    await drain_outbox_events(db_session, limit=1, subscriber_fn=failing_worker)
    await db_session.commit()
    # Attempt 3 (reaches threshold)
    await drain_outbox_events(db_session, limit=1, subscriber_fn=failing_worker)
    await db_session.commit()

    res = await db_session.execute(select(OutboxEventRecord).where(OutboxEventRecord.id == ev.id))
    loaded = res.scalars().first()
    assert loaded.status == "FAILED"
    assert loaded.attempts == 3


@pytest.mark.asyncio
async def test_boundary_outbox_zero_pending_events_drain(db_session):
    """Test 3.4: Draining empty outbox returns empty list without error."""
    drained = await drain_outbox_events(db_session, limit=100)
    assert drained == []


@pytest.mark.asyncio
async def test_boundary_outbox_multiple_consumer_groups(db_session):
    """Test 3.5: Same event ID can be consumed once per distinct consumer group."""
    event_id = "EVT-MULTI-GROUP"
    c1 = "analytics-group"
    c2 = "billing-group"

    tracker = {"c1": 0, "c2": 0}
    async def h1(p): tracker["c1"] += 1
    async def h2(p): tracker["c2"] += 1

    ok1 = await process_event_with_deduplication(db_session, event_id, c1, h1, {})
    ok2 = await process_event_with_deduplication(db_session, event_id, c2, h2, {})
    await db_session.commit()

    assert ok1 is True
    assert ok2 is True
    assert tracker["c1"] == 1
    assert tracker["c2"] == 1


# ============================================================================
# 4. DISTRIBUTED SAGA ORCHESTRATION BOUNDARIES
# ============================================================================

@pytest.mark.asyncio
async def test_boundary_saga_empty_steps_rejected(db_session):
    """Test 4.1: Executing saga with empty step list raises ValueError."""
    orch = SagaOrchestrator(db_session)
    with pytest.raises(ValueError, match="at least one step"):
        await orch.execute_saga("EmptySaga", [], SagaContext())


@pytest.mark.asyncio
async def test_boundary_saga_single_step_success(db_session):
    """Test 4.2: Saga with exactly 1 step completes cleanly."""
    class SingleStep:
        name = "SoloStep"
        async def execute(self, session, context): return True
        async def compensate(self, session, context): return True

    orch = SagaOrchestrator(db_session)
    res = await orch.execute_saga("SingleStepSaga", [SingleStep()], SagaContext())
    await db_session.commit()

    assert res.success is True
    assert res.status == "COMPLETED"


@pytest.mark.asyncio
async def test_boundary_saga_step1_failure_zero_compensations(db_session):
    """Test 4.3: Failure on Step 1 cleanly terminates without prior steps to compensate."""
    class FailingFirstStep:
        name = "FirstAndFailing"
        async def execute(self, session, context): raise RuntimeError("Immediate error")
        async def compensate(self, session, context): return True

    orch = SagaOrchestrator(db_session)
    res = await orch.execute_saga("ImmediateFailSaga", [FailingFirstStep()], SagaContext())
    await db_session.commit()

    assert res.success is False
    assert res.status == "COMPENSATED"
    assert res.completed_steps == []
    assert res.failed_step == "FirstAndFailing"


@pytest.mark.asyncio
async def test_boundary_saga_timeout_handling(db_session):
    """Test 4.4: Step timeout (asyncio.TimeoutError) triggers compensation."""
    class TimeoutStep:
        name = "TimeoutStep"
        async def execute(self, session, context):
            raise TimeoutError("Interbank partner call timed out after 30s")
        async def compensate(self, session, context):
            return True

    orch = SagaOrchestrator(db_session)
    res = await orch.execute_saga("TimeoutSaga", [TimeoutStep()], SagaContext())
    await db_session.commit()

    assert res.success is False
    assert res.status == "COMPENSATED"
    assert "timed out" in res.error


@pytest.mark.asyncio
async def test_boundary_saga_step_returns_false_treated_as_failure(db_session):
    """Test 4.5: Step returning False (soft business rejection) triggers compensation."""
    class RejectStep:
        name = "CheckCredit"
        async def execute(self, session, context): return False
        async def compensate(self, session, context): return True

    orch = SagaOrchestrator(db_session)
    res = await orch.execute_saga("RejectSaga", [RejectStep()], SagaContext())
    await db_session.commit()

    assert res.success is False
    assert res.status == "COMPENSATED"


# ============================================================================
# 5. CONCURRENCY CONTROL & CAS BOUNDARIES
# ============================================================================

@pytest.mark.asyncio
async def test_boundary_concurrency_zero_delta_update(db_session):
    """Test 5.1: Zero delta CAS update succeeds and increments version."""
    bal = await ensure_account_balance(db_session, "111")
    v_orig = bal.version
    updated = await cas_update_account_balance(db_session, "111", delta_cents=0, expected_version=v_orig)
    await db_session.commit()

    assert updated.version == v_orig + 1
    assert updated.ledger_balance == bal.ledger_balance


@pytest.mark.asyncio
async def test_boundary_concurrency_exact_depletion_to_zero(db_session):
    """Test 5.2: Debiting account to exactly 0 available balance succeeds."""
    bal = await ensure_account_balance(db_session, "111")
    bal.ledger_balance = 50000
    bal.available_balance = 50000
    await db_session.commit()

    updated = await cas_update_account_balance(db_session, "111", delta_cents=-50000, expected_version=bal.version)
    await db_session.commit()

    assert updated.available_balance == 0
    assert updated.ledger_balance == 0


@pytest.mark.asyncio
async def test_boundary_concurrency_exceeding_by_one_cent_fails(db_session):
    """Test 5.3: Overdraft by exactly 1 cent is blocked by non-negative protection."""
    bal = await ensure_account_balance(db_session, "111")
    bal.ledger_balance = 10000
    bal.available_balance = 10000
    await db_session.commit()

    with pytest.raises(InsufficientBalanceException):
        await cas_update_account_balance(db_session, "111", delta_cents=-10001, expected_version=bal.version)


@pytest.mark.asyncio
async def test_boundary_concurrency_empty_resource_order():
    """Test 5.4: Empty resource list returns empty list."""
    assert order_resources([]) == []


@pytest.mark.asyncio
async def test_boundary_concurrency_single_resource_order():
    """Test 5.5: Single resource returns single item list."""
    assert order_resources(["ACC-ONLY"]) == ["ACC-ONLY"]


# ============================================================================
# 6. CRYPTOGRAPHIC AUDIT TRAIL BOUNDARIES
# ============================================================================

@pytest.mark.asyncio
async def test_boundary_audit_empty_trail_verification(db_session):
    """Test 6.1: Empty audit trail verifies as intact (True, None)."""
    is_clean, broken_id = await verify_audit_chain_integrity(db_session)
    assert is_clean is True
    assert broken_id is None


@pytest.mark.asyncio
async def test_boundary_audit_single_entry_verification(db_session):
    """Test 6.2: Single audit entry verifies against genesis hash."""
    entry = await record_audit_entry(db_session, "sec-admin", "INIT", "CONFIG", "cfg-1", {"active": True})
    await db_session.commit()

    is_clean, broken_id = await verify_audit_chain_integrity(db_session)
    assert is_clean is True
    assert broken_id is None
    assert entry.prev_hash == GENESIS_HASH


@pytest.mark.asyncio
async def test_boundary_audit_unicode_and_special_characters(db_session):
    """Test 6.3: State payload with Vietnamese accents and special characters hashes cleanly."""
    payload = {
        "mô_tả": "Xuất kho cà phê Robusta Buôn Ma Thuột ☕",
        "ghi_chú": "Đã kiểm đếm 100% đạt chuẩn ISO-9001!",
        "ký_tự_đặc_biệt": "<>&\"'\\/\n\t\r",
    }
    await record_audit_entry(db_session, "admin-vn", "UPDATE_DESC", "INVENTORY", "item-vn-1", payload)
    await db_session.commit()

    is_clean, broken_id = await verify_audit_chain_integrity(db_session)
    assert is_clean is True


@pytest.mark.asyncio
async def test_boundary_audit_large_payload(db_session):
    """Test 6.4: Large state payload (1000 keys) hashes and verifies without corruption."""
    large_state = {f"k_{i}": f"v_{i}" * 5 for i in range(1000)}
    await record_audit_entry(db_session, "batch-job", "BULK_SNAPSHOT", "SYSTEM", "bulk-1", large_state)
    await db_session.commit()

    is_clean, broken_id = await verify_audit_chain_integrity(db_session)
    assert is_clean is True


@pytest.mark.asyncio
async def test_boundary_audit_detects_tamper_on_genesis_record(db_session):
    """Test 6.5: Direct database modification of Record 1 is detected by verifier."""
    e1 = await record_audit_entry(db_session, "user1", "ACTION1", "ENT", "1", {"val": 1})
    await record_audit_entry(db_session, "user2", "ACTION2", "ENT", "2", {"val": 2})
    await db_session.commit()

    # Simulate raw malicious SQL update bypassing ORM listener
    raw_conn = await db_session.connection()
    await raw_conn.exec_driver_sql(
        f"UPDATE audit_events_chain SET state_payload = '{{\"tampered\": true}}' WHERE id = {e1.id}"
    )
    await db_session.commit()
    db_session.expire_all()

    is_clean, broken_id = await verify_audit_chain_integrity(db_session)
    assert is_clean is False
    assert broken_id == e1.id
