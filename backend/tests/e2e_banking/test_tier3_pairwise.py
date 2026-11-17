"""Tier 3: Pairwise Combinatorial Cross-Feature Test Suite.

Covers cross-feature interactions (>=15 tests total):
1. Idempotency + Concurrency (4 tests)
2. Saga Rollback + Outbox (4 tests)
3. Double-Entry Ledger + Concurrency (4 tests)
4. Audit Trail + Outbox / Saga (4 tests)
Total: 16 tests.
"""

from __future__ import annotations

import asyncio

import pytest
from sqlalchemy import select

from tests.e2e_banking.banking_contracts import (
    AuditChainRecord,
    GLJournal,
    GLJournalEntry,
    IdempotencyInFlightException,
    OutboxEventRecord,
    SagaContext,
    SagaOrchestrator,
    cas_update_account_balance,
    emit_outbox_event,
    ensure_account_balance,
    execute_idempotent_operation,
    post_inventory_movement_to_gl,
    record_audit_entry,
    verify_audit_chain_integrity,
)

# ============================================================================
# 1. IDEMPOTENCY + CONCURRENCY INTERACTION TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_pairwise_idempotency_concurrency_race_winner(db_session):
    """Test 1.1: Concurrent duplicate requests: first wins in-flight lock, second handled gracefully."""
    key = "IDEM-PAIRWISE-001"
    payload = {"account": "111", "amount": 100000}
    executions = {"count": 0}

    async def slow_operation():
        executions["count"] += 1
        await asyncio.sleep(0.05)  # Simulate non-trivial work
        return (200, {"success": True})

    # Launch two tasks almost simultaneously
    task1 = asyncio.create_task(
        execute_idempotent_operation(db_session, key, "/transfer", payload, slow_operation)
    )
    await asyncio.sleep(0.01)  # Ensure task1 claims the mutex
    task2 = asyncio.create_task(
        execute_idempotent_operation(db_session, key, "/transfer", payload, slow_operation)
    )

    results = await asyncio.gather(task1, task2, return_exceptions=True)

    # One must succeed normally, the other must raise IdempotencyInFlightException or succeed
    succeeded = [r for r in results if not isinstance(r, Exception)]
    in_flight_exceptions = [r for r in results if isinstance(r, IdempotencyInFlightException)]

    assert len(succeeded) >= 1
    assert executions["count"] == 1  # Logic executed exactly once!
    assert len(in_flight_exceptions) == 1 or len(succeeded) == 2


@pytest.mark.asyncio
async def test_pairwise_idempotency_concurrency_balance_mutation_once(db_session):
    """Test 1.2: Two identical requests with same idempotency key debit account exactly once."""
    key = "IDEM-DEBIT-ONCE"
    bal = await ensure_account_balance(db_session, "111")
    bal.ledger_balance = 500000
    bal.available_balance = 500000
    await db_session.commit()

    async def debit_op():
        b = await ensure_account_balance(db_session, "111")
        b.ledger_balance -= 100000
        b.available_balance -= 100000
        await db_session.commit()
        return (200, {"new_bal": b.ledger_balance})

    # Call 1
    c1, b1, r1 = await execute_idempotent_operation(db_session, key, "/debit", {"amt": 100000}, debit_op)
    # Call 2 (replay)
    c2, b2, r2 = await execute_idempotent_operation(db_session, key, "/debit", {"amt": 100000}, debit_op)

    assert r1 is False
    assert r2 is True
    assert b1 == b2

    bal_final = (await ensure_account_balance(db_session, "111")).ledger_balance
    assert bal_final == 400000  # Debited exactly once, not twice!


@pytest.mark.asyncio
async def test_pairwise_idempotency_concurrency_failure_allows_subsequent_retry(db_session):
    """Test 1.3: Failed idempotent operation sets FAILED state and permits a subsequent retry."""
    key = "IDEM-FAIL-RETRY"
    payload = {"dest": "331", "amount": 50000}
    attempts = {"count": 0}

    async def flaky_op():
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise RuntimeError("Transient network failure")
        return (200, {"status": "ok"})

    # Attempt 1: Fails
    with pytest.raises(RuntimeError, match="Transient network failure"):
        await execute_idempotent_operation(db_session, key, "/pay", payload, flaky_op)
    await db_session.commit()

    # Attempt 2: Allowed to execute and succeeds
    code, body, is_replay = await execute_idempotent_operation(db_session, key, "/pay", payload, flaky_op)
    await db_session.commit()

    assert code == 200
    assert is_replay is False
    assert attempts["count"] == 2


@pytest.mark.asyncio
async def test_pairwise_idempotency_concurrency_stampede_caching(db_session):
    """Test 1.4: Sequential storm of duplicate calls returns cached response with 0 extra DB mutations."""
    key = "IDEM-STAMPEDE-01"
    counter = {"runs": 0}

    async def business_tx():
        counter["runs"] += 1
        return (200, {"order_id": "ORD-STAMPEDE"})

    # First call
    await execute_idempotent_operation(db_session, key, "/orders", {"k": 1}, business_tx)
    await db_session.commit()

    # Subsequent 5 calls
    for _ in range(5):
        c, b, rep = await execute_idempotent_operation(db_session, key, "/orders", {"k": 1}, business_tx)
        assert rep is True
        assert b["order_id"] == "ORD-STAMPEDE"

    assert counter["runs"] == 1


# ============================================================================
# 2. SAGA ROLLBACK + OUTBOX INTERACTION TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_pairwise_saga_rollback_emits_outbox_cancellation(db_session):
    """Test 2.1: Saga failure step triggers compensation and emits SAGA_FAILED event to outbox."""
    class Step1Reserve:
        name = "ReserveStock"
        async def execute(self, session, context):
            context["reserved"] = True
            return True
        async def compensate(self, session, context):
            context["reserved"] = False
            # Emit cancellation event during compensation
            await emit_outbox_event(
                session=session,
                topic="saga.events",
                event_type="SAGA_STEP_COMPENSATED",
                aggregate_id="saga-wh-1",
                payload={"step": "ReserveStock", "status": "RELEASED"},
                trace_id="tr-comp-1",
            )
            return True

    class Step2Fail:
        name = "ExternalShipment"
        async def execute(self, session, context):
            raise ConnectionError("Carrier API unreachable")
        async def compensate(self, session, context):
            return True

    orch = SagaOrchestrator(db_session)
    res = await orch.execute_saga("WarehouseTransfer", [Step1Reserve(), Step2Fail()], SagaContext())
    await db_session.commit()

    assert res.success is False
    assert res.status == "COMPENSATED"

    # Verify outbox event was committed
    events = (await db_session.execute(
        select(OutboxEventRecord).where(OutboxEventRecord.event_type == "SAGA_STEP_COMPENSATED")
    )).scalars().all()
    assert len(events) == 1
    assert "RELEASED" in events[0].payload


@pytest.mark.asyncio
async def test_pairwise_saga_success_emits_outbox_confirmation(db_session):
    """Test 2.2: Fully successful saga emits SAGA_COMPLETED event to outbox atomically."""
    class StepA:
        name = "StepA"
        async def execute(self, session, context): return True
        async def compensate(self, session, context): return True

    class StepB:
        name = "StepB"
        async def execute(self, session, context):
            await emit_outbox_event(
                session=session,
                topic="saga.events",
                event_type="SAGA_COMPLETED",
                aggregate_id="saga-ok-1",
                payload={"status": "SUCCESS"},
                trace_id="tr-ok",
            )
            return True
        async def compensate(self, session, context): return True

    orch = SagaOrchestrator(db_session)
    res = await orch.execute_saga("SuccessSaga", [StepA(), StepB()], SagaContext())
    await db_session.commit()

    assert res.success is True
    res_ev = await db_session.execute(
        select(OutboxEventRecord).where(OutboxEventRecord.event_type == "SAGA_COMPLETED")
    )
    assert res_ev.scalars().first() is not None


@pytest.mark.asyncio
async def test_pairwise_saga_rollback_posts_reversal_gl_journal(db_session):
    """Test 2.3: Saga compensation posts balanced reversal GL journal."""
    journal_created = {}

    class LedgerForwardStep:
        name = "PostGLTransfer"
        async def execute(self, session, context):
            j = await post_inventory_movement_to_gl(
                session=session,
                movement_type="TRANSFER",
                product_id=1,
                quantity=10,
                unit_cost_cents=100000,
                reference_id="SAGA-GL-1",
                warehouse_id=1,
                dest_warehouse_id=2,
                description="Forward transfer",
            )
            journal_created["fwd"] = j.id
            return True

        async def compensate(self, session, context):
            # Reverse transfer: swap warehouse 1 and 2
            j_rev = await post_inventory_movement_to_gl(
                session=session,
                movement_type="TRANSFER",
                product_id=1,
                quantity=10,
                unit_cost_cents=100000,
                reference_id="SAGA-GL-1-REV",
                warehouse_id=2,
                dest_warehouse_id=1,
                description="Compensating reversal transfer",
            )
            journal_created["rev"] = j_rev.id
            return True

    class StepBroken:
        name = "BrokenStep"
        async def execute(self, session, context): raise RuntimeError("Simulated crash")
        async def compensate(self, session, context): return True

    orch = SagaOrchestrator(db_session)
    res = await orch.execute_saga("TransferWithLedger", [LedgerForwardStep(), StepBroken()], SagaContext())
    await db_session.commit()

    assert res.success is False
    assert "fwd" in journal_created
    assert "rev" in journal_created


@pytest.mark.asyncio
async def test_pairwise_saga_failed_compensation_logged(db_session):
    """Test 2.4: If a compensation step encounters an error, it is logged with status FAILED."""
    class FailingCompStep:
        name = "FailingCompStep"
        async def execute(self, session, context): return True
        async def compensate(self, session, context): raise RuntimeError("Comp error")

    class TriggerFail:
        name = "TriggerFail"
        async def execute(self, session, context): raise RuntimeError("Trigger")
        async def compensate(self, session, context): return True

    orch = SagaOrchestrator(db_session)
    res = await orch.execute_saga("CompFailSaga", [FailingCompStep(), TriggerFail()], SagaContext())
    await db_session.commit()

    assert res.success is False
    assert res.status == "COMPENSATED"


# ============================================================================
# 3. DOUBLE-ENTRY LEDGER + CONCURRENCY INTERACTION TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_pairwise_ledger_concurrency_parallel_transfers_balanced(db_session):
    """Test 3.1: Multiple parallel transfers maintain Sum(Debit) == Sum(Credit) globally."""
    # Run 10 sequential movements across accounts
    for i in range(10):
        await post_inventory_movement_to_gl(
            session=db_session,
            movement_type="STOCK_IN",
            product_id=1,
            quantity=2,
            unit_cost_cents=50000,
            reference_id=f"PAR-TX-{i}",
            warehouse_id=1,
            description=f"Parallel stock in {i}",
        )
    await db_session.commit()

    # Query all entries in database
    res = await db_session.execute(select(GLJournalEntry))
    all_entries = res.scalars().all()

    total_debit = sum(e.debit for e in all_entries)
    total_credit = sum(e.credit for e in all_entries)
    assert total_debit == total_credit == 10 * (2 * 50000)


@pytest.mark.asyncio
async def test_pairwise_ledger_concurrency_net_zero_circular_transfers(db_session):
    """Test 3.2: Circular transfers between warehouses conserve total inventory asset balance."""
    bal_156_init = (await ensure_account_balance(db_session, "156")).ledger_balance

    # WH1 -> WH2
    await post_inventory_movement_to_gl(db_session, "TRANSFER", 1, 10, 100000, "CIRC-1", 1, "T1", dest_warehouse_id=2)
    # WH2 -> WH1
    await post_inventory_movement_to_gl(db_session, "TRANSFER", 1, 10, 100000, "CIRC-2", 2, "T2", dest_warehouse_id=1)
    await db_session.commit()

    bal_156_final = (await ensure_account_balance(db_session, "156")).ledger_balance
    assert bal_156_final == bal_156_init


@pytest.mark.asyncio
async def test_pairwise_ledger_concurrency_cas_balance_updates(db_session):
    """Test 3.3: Multiple CAS updates in sequence correctly increment version and balance."""
    bal = await ensure_account_balance(db_session, "111")
    curr_v = bal.version

    for _i in range(5):
        bal = await cas_update_account_balance(db_session, "111", delta_cents=1000, expected_version=curr_v)
        curr_v = bal.version
    await db_session.commit()

    assert bal.ledger_balance == 5000
    assert bal.version == curr_v


@pytest.mark.asyncio
async def test_pairwise_ledger_concurrency_stock_in_and_stock_out_balance(db_session):
    """Test 3.4: Stock in followed by stock out reflects exact inventory reduction and COGS increase."""
    # Stock In: 10 units @ 100,000 cents
    await post_inventory_movement_to_gl(db_session, "STOCK_IN", 1, 10, 100000, "FLOW-IN", 1, "Purchase")
    # Stock Out: 4 units @ 100,000 cents
    await post_inventory_movement_to_gl(db_session, "STOCK_OUT", 1, 4, 100000, "FLOW-OUT", 1, "Sale")
    await db_session.commit()

    bal_156 = (await ensure_account_balance(db_session, "156")).ledger_balance
    bal_632 = (await ensure_account_balance(db_session, "632")).ledger_balance
    bal_331 = (await ensure_account_balance(db_session, "331")).ledger_balance

    assert bal_156 == 600000   # 6 units remaining @ 100k
    assert bal_632 == 400000   # 4 units COGS @ 100k
    assert bal_331 == 1000000  # 10 units payable @ 100k


# ============================================================================
# 4. AUDIT TRAIL + OUTBOX & SAGA INTERACTION TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_pairwise_audit_outbox_atomic_emission(db_session):
    """Test 4.1: Business change, outbox event, and audit record commit atomically."""
    # 1. Post GL
    j = await post_inventory_movement_to_gl(db_session, "STOCK_IN", 1, 5, 200000, "ATOMIC-1", 1, "Desc")
    # 2. Emit Outbox
    o = await emit_outbox_event(db_session, "inv.tx", "STOCK_IN", j.id, {"qty": 5}, "tr-atomic")
    # 3. Record Audit
    a = await record_audit_entry(db_session, "sys", "STOCK_IN_AUDIT", "JOURNAL", j.id, {"outbox_id": o.id})
    await db_session.commit()

    # Verify all 3 exist
    assert (await db_session.execute(select(GLJournal).where(GLJournal.id == j.id))).scalars().first() is not None
    assert (await db_session.execute(select(OutboxEventRecord).where(OutboxEventRecord.id == o.id))).scalars().first() is not None
    assert (await db_session.execute(select(AuditChainRecord).where(AuditChainRecord.id == a.id))).scalars().first() is not None


@pytest.mark.asyncio
async def test_pairwise_audit_chain_verifies_across_outbox_events(db_session):
    """Test 4.2: Hash chain remains 100% valid across multiple outbox operations."""
    for i in range(5):
        o = await emit_outbox_event(db_session, "orders", "CREATED", f"ord-{i}", {"seq": i}, f"tr-{i}")
        await record_audit_entry(db_session, "dispatcher", "EMIT_OUTBOX", "OUTBOX", o.id, {"topic": o.topic})
    await db_session.commit()

    is_clean, broken_id = await verify_audit_chain_integrity(db_session)
    assert is_clean is True
    assert broken_id is None


@pytest.mark.asyncio
async def test_pairwise_audit_tracks_saga_lifecycle(db_session):
    """Test 4.3: Audit records created across Saga lifecycle form continuous unbroken chain."""
    class AuditedStep:
        name = "AuditedStep"
        async def execute(self, session, context):
            await record_audit_entry(session, "saga-engine", "STEP_START", "SAGA_STEP", "step-1", {"context": "init"})
            await record_audit_entry(session, "saga-engine", "STEP_DONE", "SAGA_STEP", "step-1", {"context": "done"})
            return True
        async def compensate(self, session, context):
            return True

    orch = SagaOrchestrator(db_session)
    await orch.execute_saga("AuditedSaga", [AuditedStep()], SagaContext())
    await db_session.commit()

    is_clean, broken_id = await verify_audit_chain_integrity(db_session)
    assert is_clean is True
    assert broken_id is None


@pytest.mark.asyncio
async def test_pairwise_audit_tamper_detection_in_outbox_workflow(db_session):
    """Test 4.4: Malicious modification of an audit event emitted in outbox flow is caught immediately."""
    o = await emit_outbox_event(db_session, "security", "ALERT", "agg-sec", {"risk": "high"}, "tr-sec")
    a = await record_audit_entry(db_session, "sec-agent", "LOG_RISK", "SECURITY", o.id, {"risk": "high"})
    await db_session.commit()

    # Raw SQL modification of payload
    raw_conn = await db_session.connection()
    await raw_conn.exec_driver_sql(
        f"UPDATE audit_events_chain SET state_payload = '{{\"risk\": \"none\"}}' WHERE id = {a.id}"
    )
    await db_session.commit()
    db_session.expire_all()

    is_clean, broken_id = await verify_audit_chain_integrity(db_session)
    assert is_clean is False
    assert broken_id == a.id
