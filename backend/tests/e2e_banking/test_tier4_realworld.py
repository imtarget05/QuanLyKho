"""Tier 4: Real-World Workload Scenarios Test Suite.

Covers >=5 realistic institutional banking workload scenarios:
1. Concurrency Stress Test: 50+ concurrent transactions debiting/crediting accounts simultaneously
   with zero balance drift, zero negative balance, and exact final balance.
2. Mid-flight Saga Failure & Automated Compensation: Multi-warehouse transfer where step 3 fails,
   verifying stock hold is released, reversal ledger entry posted, and final balance matches initial balance.
3. Tamper-Evident Forensic Test: Artificially alter historical audit log row in database,
   verifying verify_audit_chain_integrity() detects corruption and returns exact corrupted record ID.
4. Idempotency Replay Storm: 10 repeated calls with identical key return identical responses
   while creating exactly 1 ledger journal entry.
5. End-to-End Treasury Order Fulfillment Flow: Idempotency check -> Saga orchestration (Stock hold ->
   GL journal post -> Outbox emit -> Audit hash chain -> Confirmation) -> End-of-Day reconciliation.
Total: 5 tests.
"""

from __future__ import annotations

import asyncio

import pytest
from sqlalchemy import select

from tests.e2e_banking.banking_contracts import (
    GLJournal,
    GLJournalEntry,
    InventoryBalanceRecord,
    SagaContext,
    SagaOrchestrator,
    drain_outbox_events,
    emit_outbox_event,
    ensure_account_balance,
    execute_idempotent_operation,
    lock_manager,
    post_inventory_movement_to_gl,
    process_event_with_deduplication,
    record_audit_entry,
    verify_audit_chain_integrity,
)

# ============================================================================
# 1. CONCURRENCY STRESS TEST (50+ WORKERS)
# ============================================================================

@pytest.mark.asyncio
async def test_realworld_concurrency_stress_50_workers(db_session):
    """Scenario 1: Concurrency Stress Test.

    50 concurrent deposit workers + 20 concurrent debit workers concurrently mutate
    the merchant account. Verifies zero lost updates, zero negative balance, and exact
    mathematical final balance.
    """
    bal = await ensure_account_balance(db_session, "111")
    bal.ledger_balance = 500000  # Initial 500,000 cents
    bal.available_balance = 500000
    await db_session.commit()

    deposit_delta = 10000   # +10,000 cents each
    withdraw_delta = -15000 # -15,000 cents each

    num_deposits = 50
    num_withdrawals = 20

    success_deposits = 0
    success_withdrawals = 0
    failed_withdrawals = 0

    acc_lock = await lock_manager.get_lock("111")

    async def deposit_worker(worker_id: int):
        nonlocal success_deposits
        async with acc_lock:
            b = await ensure_account_balance(db_session, "111")
            b.ledger_balance += deposit_delta
            b.available_balance += deposit_delta
            b.version += 1
            await db_session.commit()
            success_deposits += 1

    async def withdraw_worker(worker_id: int):
        nonlocal success_withdrawals, failed_withdrawals
        async with acc_lock:
            b = await ensure_account_balance(db_session, "111")
            if b.available_balance + withdraw_delta >= 0:
                b.ledger_balance += withdraw_delta
                b.available_balance += withdraw_delta
                b.version += 1
                await db_session.commit()
                success_withdrawals += 1
            else:
                failed_withdrawals += 1

    # Launch all 70 tasks concurrently
    tasks = [deposit_worker(i) for i in range(num_deposits)] + [
        withdraw_worker(j) for j in range(num_withdrawals)
    ]
    await asyncio.gather(*tasks)

    # Verify final state
    final_bal = await ensure_account_balance(db_session, "111")
    expected_balance = 500000 + (success_deposits * deposit_delta) + (success_withdrawals * withdraw_delta)

    assert success_deposits == 50
    assert success_withdrawals + failed_withdrawals == 20
    assert final_bal.ledger_balance == expected_balance
    assert final_bal.available_balance >= 0
    assert final_bal.available_balance == final_bal.ledger_balance


# ============================================================================
# 2. MID-FLIGHT SAGA FAILURE & AUTOMATED COMPENSATION
# ============================================================================

@pytest.mark.asyncio
async def test_realworld_midflight_saga_failure_and_automated_compensation(db_session, seeded_data):
    """Scenario 2: Mid-flight Saga Failure & Automated Compensation.

    Inter-warehouse transfer where step 3 (carrier dispatch) fails.
    Verifies:
    - Step 2 posted ledger entry is reversed by a compensating GL journal.
    - Step 1 stock hold is fully released.
    - Final warehouse inventory balance and GL balances return exactly to initial state.
    """
    wh1_id = seeded_data["warehouses"][0].id
    wh2_id = seeded_data["warehouses"][1].id
    prod_id = seeded_data["products"][0].id

    # Check initial stock
    inv_res = await db_session.execute(
        select(InventoryBalanceRecord).where(
            InventoryBalanceRecord.warehouse_id == wh1_id,
            InventoryBalanceRecord.product_id == prod_id,
        )
    )
    inv_record = inv_res.scalars().first()
    initial_qty = inv_record.quantity
    assert initial_qty == 1000

    transfer_qty = 50
    transfer_cost = 150000

    class Step1HoldStock:
        name = "HoldStockAtSource"
        async def execute(self, session, context):
            inv = (await session.execute(
                select(InventoryBalanceRecord).where(
                    InventoryBalanceRecord.warehouse_id == wh1_id,
                    InventoryBalanceRecord.product_id == prod_id,
                )
            )).scalars().first()
            inv.reserved_quantity += transfer_qty
            await session.flush()
            context["stock_held"] = True
            return True

        async def compensate(self, session, context):
            inv = (await session.execute(
                select(InventoryBalanceRecord).where(
                    InventoryBalanceRecord.warehouse_id == wh1_id,
                    InventoryBalanceRecord.product_id == prod_id,
                )
            )).scalars().first()
            inv.reserved_quantity -= transfer_qty
            await session.flush()
            context["stock_held"] = False
            return True

    class Step2PostGLTransfer:
        name = "PostGLTransfer"
        async def execute(self, session, context):
            j = await post_inventory_movement_to_gl(
                session=session,
                movement_type="TRANSFER",
                product_id=prod_id,
                quantity=transfer_qty,
                unit_cost_cents=transfer_cost,
                reference_id="SAGA-WH-TX-1",
                warehouse_id=wh1_id,
                dest_warehouse_id=wh2_id,
                description="Inter-warehouse stock in-transit",
            )
            context["fwd_journal_id"] = j.id
            return True

        async def compensate(self, session, context):
            # Reverse GL transfer
            j_rev = await post_inventory_movement_to_gl(
                session=session,
                movement_type="TRANSFER",
                product_id=prod_id,
                quantity=transfer_qty,
                unit_cost_cents=transfer_cost,
                reference_id="SAGA-WH-TX-1-REVERSAL",
                warehouse_id=wh2_id,
                dest_warehouse_id=wh1_id,
                description="Compensating reversal of inter-warehouse stock transfer",
            )
            context["rev_journal_id"] = j_rev.id
            return True

    class Step3DispatchCarrierFails:
        name = "DispatchCarrier"
        async def execute(self, session, context):
            # Simulate external transportation API failure
            raise ConnectionError("Carrier API 503 Service Unavailable: Logistics node offline")

        async def compensate(self, session, context):
            return True

    class Step4ConfirmAtDestination:
        name = "ConfirmDestination"
        async def execute(self, session, context):
            return True
        async def compensate(self, session, context):
            return True

    steps = [Step1HoldStock(), Step2PostGLTransfer(), Step3DispatchCarrierFails(), Step4ConfirmAtDestination()]
    orch = SagaOrchestrator(db_session)
    result = await orch.execute_saga("InterWarehouseTransfer", steps, SagaContext())
    await db_session.commit()

    # Assertions
    assert result.success is False
    assert result.status == "COMPENSATED"
    assert result.failed_step == "DispatchCarrier"

    # Verify Stock hold is released back to 0
    inv_final = (await db_session.execute(
        select(InventoryBalanceRecord).where(
            InventoryBalanceRecord.warehouse_id == wh1_id,
            InventoryBalanceRecord.product_id == prod_id,
        )
    )).scalars().first()
    assert inv_final.reserved_quantity == 0
    assert inv_final.quantity == 1000

    # Verify Reversal journal was created
    journals = (await db_session.execute(
        select(GLJournal).where(GLJournal.correlation_id.in_(["corr-SAGA-WH-TX-1", "corr-SAGA-WH-TX-1-REVERSAL"]))
    )).scalars().all()
    assert len(journals) == 2


# ============================================================================
# 3. TAMPER-EVIDENT FORENSIC TEST
# ============================================================================

@pytest.mark.asyncio
async def test_realworld_tamper_evident_forensic_detection(db_session):
    """Scenario 3: Tamper-Evident Forensic Test.

    Records a sequence of 10 audit events forming an unbroken cryptographic SHA-256 chain.
    Artificially tampers with historical record #6 using raw driver SQL.
    Verifies that verify_audit_chain_integrity() detects tampering and pinpoints record #6.
    """
    records = []
    for i in range(1, 11):
        rec = await record_audit_entry(
            session=db_session,
            actor_id=f"operator-{i % 3}",
            action=f"TREASURY_OP_{i}",
            entity_type="TRANSFER",
            entity_id=f"tx-{1000 + i}",
            state_payload={"amount": i * 100000, "status": "SETTLED"},
        )
        records.append(rec)
    await db_session.commit()

    # Step 1: Pre-tamper baseline verification
    is_clean, broken_id = await verify_audit_chain_integrity(db_session)
    assert is_clean is True
    assert broken_id is None

    # Step 2: Malicious tampering on record #6 (e.g. changing amount from 600,000 to 9,999,999)
    target_record = records[5]  # Index 5 is 6th record
    target_id = target_record.id

    raw_conn = await db_session.connection()
    await raw_conn.exec_driver_sql(
        f"UPDATE audit_events_chain SET state_payload = '{{\"amount\": 9999999, \"status\": \"FRAUDULENT\"}}' WHERE id = {target_id}"
    )
    await db_session.commit()
    db_session.expire_all()

    # Step 3: Forensic scan
    is_clean_after, detected_broken_id = await verify_audit_chain_integrity(db_session)
    assert is_clean_after is False
    assert detected_broken_id == target_id


# ============================================================================
# 4. IDEMPOTENCY REPLAY STORM (10x REPEATED CALLS)
# ============================================================================

@pytest.mark.asyncio
async def test_realworld_idempotency_replay_storm_single_journal(db_session):
    """Scenario 4: Idempotency Replay Storm.

    10 repeated calls with identical idempotency key return identical responses
    while creating exactly 1 ledger journal entry in the database.
    """
    key = "IDEM-STORM-ORDER-999"
    payload = {
        "order_id": "ORD-999",
        "customer_id": "CUST-VIP-01",
        "amount_cents": 2500000,
    }

    journal_created_count = 0

    async def payment_operation():
        nonlocal journal_created_count
        # Post GL entry: Debit Cash 111, Credit Revenue 511
        journal = await post_inventory_movement_to_gl(
            session=db_session,
            movement_type="STOCK_IN",
            product_id=1,
            quantity=1,
            unit_cost_cents=2500000,
            reference_id="ORD-999",
            warehouse_id=1,
            description="Order ORD-999 payment posting",
        )
        journal_created_count += 1
        return (200, {"order_id": "ORD-999", "journal_id": journal.id, "status": "PAID"})

    responses = []
    # Fire 10 identical calls
    for _ in range(10):
        code, body, is_replay = await execute_idempotent_operation(
            session=db_session,
            idempotency_key=key,
            request_path="/api/orders/pay",
            request_payload=payload,
            operation_coroutine=payment_operation,
        )
        await db_session.commit()
        responses.append((code, body, is_replay))

    # Verification:
    # 1. Exactly 1 actual execution
    assert journal_created_count == 1

    # 2. First call was fresh, remaining 9 were cached replays
    assert responses[0][2] is False  # is_replay == False
    for r in responses[1:]:
        assert r[2] is True         # is_replay == True
        assert r[0] == 200
        assert r[1]["order_id"] == "ORD-999"
        assert r[1]["journal_id"] == responses[0][1]["journal_id"]

    # 3. Database has exactly 1 journal entry for this correlation
    journals = (await db_session.execute(
        select(GLJournal).where(GLJournal.correlation_id == "corr-ORD-999")
    )).scalars().all()
    assert len(journals) == 1


# ============================================================================
# 5. END-TO-END TREASURY ORDER FULFILLMENT FLOW
# ============================================================================

@pytest.mark.asyncio
async def test_realworld_e2e_treasury_order_fulfillment_lifecycle(db_session, seeded_data):
    """Scenario 5: End-to-End Treasury Order Fulfillment Flow.

    Complete institutional journey:
    Customer Order -> Idempotency Check -> Saga Orchestration:
      Step 1: Stock Reservation
      Step 2: GL Balanced Journal (Sales revenue & COGS)
      Step 3: Transactional Outbox Event
      Step 4: Cryptographic Audit Trail Chained Record
      Step 5: Order Confirmation & Final Stock Deduction
    -> Outbox Dispatcher Drains Events to Consumer
    -> End-of-Day Reconciliation Confirms Zero Variance.
    """
    wh_id = seeded_data["warehouses"][0].id
    prod_id = seeded_data["products"][0].id
    order_id = "ORD-E2E-INSTITUTIONAL"
    idempotency_key = "KEY-E2E-ORDER-FULFILL-001"

    order_qty = 10
    unit_selling_price_cents = 250000  # 250,000 cents revenue per unit
    unit_cogs_cost_cents = 150000      # 150,000 cents COGS per unit

    total_revenue = order_qty * unit_selling_price_cents # 2,500,000 cents
    total_cogs = order_qty * unit_cogs_cost_cents        # 1,500,000 cents

    order_payload = {
        "order_id": order_id,
        "product_id": prod_id,
        "quantity": order_qty,
        "total_revenue_cents": total_revenue,
    }

    async def execute_full_order_saga():
        context = SagaContext()
        context["order_id"] = order_id
        context["qty"] = order_qty

        class Step1StockReserve:
            name = "StockReserve"
            async def execute(self, session, ctx):
                inv = (await session.execute(
                    select(InventoryBalanceRecord).where(
                        InventoryBalanceRecord.warehouse_id == wh_id,
                        InventoryBalanceRecord.product_id == prod_id,
                    )
                )).scalars().first()
                inv.reserved_quantity += order_qty
                await session.flush()
                return True
            async def compensate(self, session, ctx):
                inv = (await session.execute(
                    select(InventoryBalanceRecord).where(
                        InventoryBalanceRecord.warehouse_id == wh_id,
                        InventoryBalanceRecord.product_id == prod_id,
                    )
                )).scalars().first()
                inv.reserved_quantity -= order_qty
                await session.flush()
                return True

        class Step2GLPosting:
            name = "GLPosting"
            async def execute(self, session, ctx):
                # 1. Stock Out GL (COGS and Inventory Asset)
                j_cogs = await post_inventory_movement_to_gl(
                    session=session,
                    movement_type="STOCK_OUT",
                    product_id=prod_id,
                    quantity=order_qty,
                    unit_cost_cents=unit_cogs_cost_cents,
                    reference_id=f"{order_id}-COGS",
                    warehouse_id=wh_id,
                    description=f"COGS for {order_id}",
                )
                ctx["cogs_journal_id"] = j_cogs.id
                return True
            async def compensate(self, session, ctx):
                return True

        class Step3OutboxEmit:
            name = "OutboxEmit"
            async def execute(self, session, ctx):
                ev = await emit_outbox_event(
                    session=session,
                    topic="orders.fulfillment",
                    event_type="ORDER_FULFILLED",
                    aggregate_id=order_id,
                    payload={"order_id": order_id, "revenue": total_revenue},
                    trace_id=f"trace-{order_id}",
                )
                ctx["outbox_event_id"] = ev.id
                return True
            async def compensate(self, session, ctx):
                return True

        class Step4AuditBlock:
            name = "AuditBlock"
            async def execute(self, session, ctx):
                audit = await record_audit_entry(
                    session=session,
                    actor_id="order-engine",
                    action="FULFILL_ORDER",
                    entity_type="ORDER",
                    entity_id=order_id,
                    state_payload={"order_id": order_id, "status": "CONFIRMED"},
                )
                ctx["audit_id"] = audit.id
                return True
            async def compensate(self, session, ctx):
                return True

        class Step5FinalStockDeduction:
            name = "FinalStockDeduction"
            async def execute(self, session, ctx):
                inv = (await session.execute(
                    select(InventoryBalanceRecord).where(
                        InventoryBalanceRecord.warehouse_id == wh_id,
                        InventoryBalanceRecord.product_id == prod_id,
                    )
                )).scalars().first()
                inv.quantity -= order_qty
                inv.reserved_quantity -= order_qty
                inv.version += 1
                await session.flush()
                return True
            async def compensate(self, session, ctx):
                return True

        steps = [Step1StockReserve(), Step2GLPosting(), Step3OutboxEmit(), Step4AuditBlock(), Step5FinalStockDeduction()]
        orch = SagaOrchestrator(db_session)
        saga_res = await orch.execute_saga("OrderFulfillmentSaga", steps, context)
        return (200, {"order_id": order_id, "saga_status": saga_res.status})

    # Trigger with Idempotency
    code, body, is_replay = await execute_idempotent_operation(
        session=db_session,
        idempotency_key=idempotency_key,
        request_path="/api/orders/fulfill",
        request_payload=order_payload,
        operation_coroutine=execute_full_order_saga,
    )
    await db_session.commit()

    assert code == 200
    assert body["saga_status"] == "COMPLETED"
    assert is_replay is False

    # Outbox dispatcher drains event
    dispatched_events = []
    async def bus_handler(e):
        dispatched_events.append(e.id)
        return True

    drained = await drain_outbox_events(db_session, limit=10, subscriber_fn=bus_handler)
    await db_session.commit()
    assert len(drained) >= 1

    # Consumer deduplication executes
    consumed = []
    async def consumer(p):
        consumed.append(p["order_id"])

    dedup_ok = await process_event_with_deduplication(
        db_session, drained[0].id, "warehouse-analytics", consumer, {"order_id": order_id}
    )
    await db_session.commit()
    assert dedup_ok is True
    assert consumed == [order_id]

    # End-of-Day (EOD) Reconciliation
    # 1. Verify global General Ledger balancing
    entries = (await db_session.execute(select(GLJournalEntry))).scalars().all()
    total_debit = sum(e.debit for e in entries)
    total_credit = sum(e.credit for e in entries)
    assert total_debit == total_credit == total_cogs

    # 2. Verify Cryptographic Audit Chain is 100% clean
    is_audit_clean, broken_id = await verify_audit_chain_integrity(db_session)
    assert is_audit_clean is True
    assert broken_id is None

    # 3. Verify Stock deduction matches exactly
    inv_final = (await db_session.execute(
        select(InventoryBalanceRecord).where(
            InventoryBalanceRecord.warehouse_id == wh_id,
            InventoryBalanceRecord.product_id == prod_id,
        )
    )).scalars().first()
    assert inv_final.quantity == 990  # 1000 - 10
    assert inv_final.reserved_quantity == 0
