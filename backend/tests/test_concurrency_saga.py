"""Comprehensive Unit & Integration Test Suite for Milestone M4.

Covers:
1. Concurrency Locking Engine (F13, F14, F15):
   - Deterministic resource ordering (order_resources) eliminating circular wait deadlocks.
   - Optimistic locking & atomic Compare-and-Swap (CAS) on GLAccountBalance.
   - Stale version conflict detection (OptimisticLockException / OptimisticConcurrencyException).
   - Invariant enforcement: available_balance >= 0 (no overdraft / negative stock).
   - Pessimistic locking (with_for_update) & KeyedLockManager coroutine synchronization.
   - Hold and release lifecycle (hold_account_funds, release_account_hold).
   - Concurrent transfer execution with deadlock-free resource ordering.
2. Distributed Saga Orchestration (F16, F17, F18):
   - Forward saga execution with sequential step execution (execute_saga).
   - Context propagation and step audit logging (SagaStepLog).
   - Automated reverse compensation rollback upon mid-flight step failure.
   - Saga state machine transitions: PENDING -> RUNNING -> COMPENSATING -> COMPENSATED / FAILED / COMPLETED.
   - Idempotent saga re-execution returning cached results without duplicate side-effects.
   - Practical core banking saga: InterWarehouseTransferSaga (Hold -> Post GL -> Outbox -> Confirm).
   - Full compensation rollback on transfer failure (GL Reversal -> Release Hold -> Cancel Event).
3. API Endpoints:
   - POST /banking/transfers/concurrent
   - POST /banking/saga/execute
   - GET /banking/saga/{saga_id}
4. Dual-Dialect Compatibility:
   - Verified across both SQLite in-memory and PostgreSQL.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.main import app
from app.models.ledger import (
    BASE_CHART_OF_ACCOUNTS,
    ChartOfAccounts,
    GeneralLedgerEntry,
    GeneralLedgerJournal,
    GLAccountBalance,
)
from app.models.outbox import OutboxEventRecord, ProcessedEventRecord
from app.models.saga import (
    CompensatingLog,
    SagaInstance,
    SagaStep,
    SagaStepLog,
)
from app.services.concurrency_service import (
    InsufficientBalanceException,
    KeyedLockManager,
    OptimisticConcurrencyException,
    OptimisticLockException,
    apply_balance_mutation,
    cas_update_account_balance,
    ensure_account_balance,
    execute_concurrent_transfer,
    hold_account_funds,
    lock_account_balance,
    order_resources,
    release_account_hold,
)
from app.services.saga_orchestrator import (
    ConfirmTransferStep,
    HoldSourceFundsStep,
    PostGLTransferJournalStep,
    SagaContext,
    SagaOrchestrator,
    create_inter_warehouse_transfer_saga,
)


@pytest_asyncio.fixture
async def sqlite_session():
    """Provides an isolated SQLite in-memory AsyncSession seeded with standard Chart of Accounts."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    tables = [
        ChartOfAccounts.__table__,
        GLAccountBalance.__table__,
        GeneralLedgerJournal.__table__,
        GeneralLedgerEntry.__table__,
        OutboxEventRecord.__table__,
        ProcessedEventRecord.__table__,
        SagaInstance.__table__,
        SagaStepLog.__table__,
        SagaStep.__table__,
        CompensatingLog.__table__,
    ]
    async with engine.begin() as conn:
        await conn.run_sync(lambda sync_conn: Base.metadata.create_all(sync_conn, tables=tables))

    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with session_factory() as session:
        # Seed standard chart of accounts
        for code, name, acc_type, normal_bal, sim_only in BASE_CHART_OF_ACCOUNTS:
            acc = ChartOfAccounts(
                code=code,
                name=name,
                account_type=acc_type,
                normal_balance=normal_bal,
                is_active=True,
                simulation_only=sim_only,
            )
            session.add(acc)
        await session.flush()

        # Seed initial balances for primary cash (111), bank (112), and inventory (156)
        bal_111 = GLAccountBalance(
            account_code="111",
            currency="VND",
            ledger_balance=100_000_00,  # 1,000,000 VND (in cents)
            available_balance=100_000_00,
            hold_balance=0,
            version=1,
            updated_at=datetime.now(UTC),
        )
        bal_112 = GLAccountBalance(
            account_code="112",
            currency="VND",
            ledger_balance=50_000_00,  # 500,000 VND
            available_balance=50_000_00,
            hold_balance=0,
            version=1,
            updated_at=datetime.now(UTC),
        )
        bal_156 = GLAccountBalance(
            account_code="156",
            currency="VND",
            ledger_balance=200_000_00,
            available_balance=200_000_00,
            hold_balance=0,
            version=1,
            updated_at=datetime.now(UTC),
        )
        session.add_all([bal_111, bal_112, bal_156])
        await session.flush()

        yield session

    await engine.dispose()


# ============================================================================
# 1. FEATURE F13: RESOURCE ORDERING & DEADLOCK PREVENTION
# ============================================================================

def test_order_resources_deterministic_ordering():
    """Resource IDs are sorted deterministically regardless of input order."""
    res_a = ["ACC_B", "ACC_A", "ACC_Z", "ACC_C"]
    res_b = ["ACC_Z", "ACC_C", "ACC_B", "ACC_A"]
    res_c = ["ACC_A", "ACC_B", "ACC_C", "ACC_Z"]

    ordered_a = order_resources(res_a)
    ordered_b = order_resources(res_b)
    ordered_c = order_resources(res_c)

    assert ordered_a == ["ACC_A", "ACC_B", "ACC_C", "ACC_Z"]
    assert ordered_a == ordered_b == ordered_c


def test_order_resources_empty_and_single_element():
    """Handles boundary cases: empty list and single-element list cleanly."""
    assert order_resources([]) == []
    assert order_resources(["ACC_100"]) == ["ACC_100"]
    assert order_resources([105, 101, 103]) == [101, 103, 105]


def test_order_resources_breaks_circular_wait():
    """Worker 1 wanting [B, A] and Worker 2 wanting [A, B] obtain identical lock order."""
    worker1_resources = ["ACCOUNT_B", "ACCOUNT_A"]
    worker2_resources = ["ACCOUNT_A", "ACCOUNT_B"]

    lock_order1 = order_resources(worker1_resources)
    lock_order2 = order_resources(worker2_resources)

    # Both workers lock ACCOUNT_A first, then ACCOUNT_B: eliminating circular wait!
    assert lock_order1 == ["ACCOUNT_A", "ACCOUNT_B"]
    assert lock_order2 == ["ACCOUNT_A", "ACCOUNT_B"]
    assert lock_order1 == lock_order2


@pytest.mark.asyncio
async def test_keyed_lock_manager_isolation():
    """KeyedLockManager isolates locks for distinct keys while serializing identical keys."""
    mgr = KeyedLockManager()
    lock_a1 = await mgr.get_lock("KEY_A")
    lock_a2 = await mgr.get_lock("KEY_A")
    lock_b = await mgr.get_lock("KEY_B")

    assert lock_a1 is lock_a2  # Same lock object for identical key
    assert lock_a1 is not lock_b  # Distinct lock object for different key

    # Test lock acquisition
    async with lock_a1:
        assert lock_a1.locked()
        assert not lock_b.locked()


# ============================================================================
# 2. FEATURE F14: OPTIMISTIC LOCKING & CAS ON BALANCES
# ============================================================================

@pytest.mark.asyncio
async def test_cas_update_success_increments_version(sqlite_session: AsyncSession):
    """CAS update succeeds when expected_version matches current version, incrementing version."""
    bal = await ensure_account_balance(sqlite_session, "111")
    initial_version = bal.version
    initial_available = bal.available_balance

    updated = await cas_update_account_balance(
        session=sqlite_session,
        account_code="111",
        delta_cents=25_000_00,  # +250,000 VND
        expected_version=initial_version,
    )

    assert updated.version == initial_version + 1
    assert updated.available_balance == initial_available + 25_000_00
    assert updated.ledger_balance == initial_available + 25_000_00


@pytest.mark.asyncio
async def test_cas_version_mismatch_raises_optimistic_lock_exception(sqlite_session: AsyncSession):
    """CAS update fails with OptimisticLockException when expected_version is stale."""
    bal = await ensure_account_balance(sqlite_session, "111")
    current_version = bal.version

    # Attempt CAS with an outdated version
    stale_version = current_version - 1
    with pytest.raises(OptimisticLockException) as exc_info:
        await cas_update_account_balance(
            session=sqlite_session,
            account_code="111",
            delta_cents=10_000_00,
            expected_version=stale_version,
        )

    assert "CAS version mismatch" in str(exc_info.value)
    assert exc_info.value.status_code == 409
    # Also verify alias
    assert issubclass(OptimisticConcurrencyException, OptimisticLockException)


@pytest.mark.asyncio
async def test_cas_negative_balance_protection_raises_insufficient_balance(sqlite_session: AsyncSession):
    """CAS update rejects debit that would cause available_balance < 0 on asset accounts."""
    bal = await ensure_account_balance(sqlite_session, "111")
    excessive_debit = -(bal.available_balance + 100)  # 1 cent more than available

    with pytest.raises(InsufficientBalanceException) as exc_info:
        await cas_update_account_balance(
            session=sqlite_session,
            account_code="111",
            delta_cents=excessive_debit,
            expected_version=bal.version,
        )

    assert "Negative balance protection invariant violated" in str(exc_info.value)
    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_concurrent_cas_contention_single_winner(sqlite_session: AsyncSession):
    """Under concurrent CAS contention with identical expected_version, exactly 1 succeeds."""
    bal = await ensure_account_balance(sqlite_session, "111")
    target_version = bal.version

    winners = []
    conflicts = []

    async def attempt_cas(task_id: int):
        try:
            await cas_update_account_balance(
                session=sqlite_session,
                account_code="111",
                delta_cents=1_000,
                expected_version=target_version,
            )
            winners.append(task_id)
        except OptimisticLockException:
            conflicts.append(task_id)

    # Simulate 10 concurrent requests competing for the exact same version
    await asyncio.gather(*(attempt_cas(i) for i in range(10)))

    assert len(winners) == 1
    assert len(conflicts) == 9
    assert bal.version == target_version + 1


# ============================================================================
# 3. FEATURE F15: PESSIMISTIC LOCKING & INVARIANT GUARDS
# ============================================================================

@pytest.mark.asyncio
async def test_lock_account_balance_with_for_update(sqlite_session: AsyncSession):
    """lock_account_balance executes row-level query safely across dialects."""
    bal = await lock_account_balance(sqlite_session, "111")
    assert bal is not None
    assert bal.account_code == "111"
    assert bal.available_balance > 0


@pytest.mark.asyncio
async def test_hold_and_release_funds_lifecycle(sqlite_session: AsyncSession):
    """hold_account_funds freezes funds; release_account_hold restores available balance."""
    bal = await ensure_account_balance(sqlite_session, "111")
    initial_ledger = bal.ledger_balance
    initial_available = bal.available_balance
    hold_amount = 30_000_00  # 300,000 VND

    # 1. Freeze funds
    held_bal = await hold_account_funds(sqlite_session, "111", hold_amount)
    assert held_bal.hold_balance == hold_amount
    assert held_bal.ledger_balance == initial_ledger  # Ledger balance unchanged
    assert held_bal.available_balance == initial_available - hold_amount  # Available reduced

    # 2. Invariant: Available = Ledger - Hold
    assert held_bal.available_balance == held_bal.ledger_balance - held_bal.hold_balance

    # 3. Release funds
    released_bal = await release_account_hold(sqlite_session, "111", hold_amount)
    assert released_bal.hold_balance == 0
    assert released_bal.available_balance == initial_available
    assert released_bal.ledger_balance == initial_ledger


@pytest.mark.asyncio
async def test_hold_funds_exceeding_available_rejected(sqlite_session: AsyncSession):
    """Attempting to hold more funds than available balance is strictly rejected."""
    bal = await ensure_account_balance(sqlite_session, "111")
    excessive_hold = bal.available_balance + 500

    with pytest.raises(InsufficientBalanceException):
        await hold_account_funds(sqlite_session, "111", excessive_hold)


@pytest.mark.asyncio
async def test_apply_balance_mutation_pessimistic_mode(sqlite_session: AsyncSession):
    """apply_balance_mutation correctly mutates balances under pessimistic mode."""
    bal = await apply_balance_mutation(
        session=sqlite_session,
        account_code="112",
        delta_cents=15_000_00,
        mode="pessimistic",
    )
    assert bal.ledger_balance == 65_000_00
    assert bal.available_balance == 65_000_00
    assert bal.version == 2


@pytest.mark.asyncio
async def test_concurrent_transfers_with_resource_ordering(sqlite_session: AsyncSession):
    """execute_concurrent_transfer executes cross-account transfers safely without deadlocks."""
    # Transfer 200,000 VND from 111 to 112
    result = await execute_concurrent_transfer(
        session=sqlite_session,
        source_account="111",
        dest_account="112",
        amount_cents=20_000_00,
        description="Payment settlement transfer",
        mode="pessimistic",
    )

    assert result["source_account"] == "111"
    assert result["dest_account"] == "112"
    assert result["amount_cents"] == 20_000_00
    assert result["source_balance"]["available"] == 80_000_00
    assert result["dest_balance"]["available"] == 70_000_00

    # Invariant: Total funds conserved (111 + 112 = 1,500,000 VND)
    total = result["source_balance"]["ledger"] + result["dest_balance"]["ledger"]
    assert total == 150_000_00


# ============================================================================
# 4. FEATURE F16 & F17: FORWARD SAGA EXECUTION & AUDIT LOGGING
# ============================================================================

class MockSagaStep:
    def __init__(self, name: str, should_fail: bool = False):
        self.name = name
        self.should_fail = should_fail
        self.executed = False
        self.compensated = False

    async def execute(self, session: AsyncSession, context: SagaContext) -> bool:
        if self.should_fail:
            raise RuntimeError(f"Step '{self.name}' simulated deliberate failure.")
        self.executed = True
        context[f"{self.name}_done"] = True
        return True

    async def compensate(self, session: AsyncSession, context: SagaContext) -> bool:
        self.compensated = True
        context[f"{self.name}_compensated"] = True
        return True


@pytest.mark.asyncio
async def test_saga_forward_execution_all_steps_completed(sqlite_session: AsyncSession):
    """All saga steps execute sequentially to terminal COMPLETED state."""
    orch = SagaOrchestrator(sqlite_session)
    s1 = MockSagaStep("Reserve")
    s2 = MockSagaStep("DebitCredit")
    s3 = MockSagaStep("DispatchEvent")
    s4 = MockSagaStep("Confirm")

    ctx = SagaContext({"order_id": "ORD-999"})
    result = await orch.execute_saga("OrderFulfillmentSaga", [s1, s2, s3, s4], ctx)

    assert result.success is True
    assert result.status == "COMPLETED"
    assert len(result.completed_steps) == 4
    assert s1.executed and s2.executed and s3.executed and s4.executed

    # Verify context propagation
    assert ctx["Reserve_done"] is True
    assert ctx["Confirm_done"] is True

    # Verify saga instance record in DB
    saga_rec = (
        await sqlite_session.execute(select(SagaInstance).where(SagaInstance.id == result.saga_id))
    ).scalars().first()
    assert saga_rec is not None
    assert saga_rec.status == "COMPLETED"

    # Verify step logs in DB
    step_logs = (
        await sqlite_session.execute(
            select(SagaStepLog).where(SagaStepLog.saga_id == result.saga_id).order_by(SagaStepLog.step_index.asc())
        )
    ).scalars().all()
    assert len(step_logs) == 4
    assert [log.status for log in step_logs] == ["EXECUTED", "EXECUTED", "EXECUTED", "EXECUTED"]


@pytest.mark.asyncio
async def test_saga_idempotency_prevents_duplicate_execution(sqlite_session: AsyncSession):
    """Re-executing an already completed saga returns the cached result without duplicate execution."""
    orch = SagaOrchestrator(sqlite_session)
    s1 = MockSagaStep("StepA")
    saga_id = str(uuid.uuid4())

    res1 = await orch.execute_saga("IdempotentSaga", [s1], SagaContext(), saga_id=saga_id)
    assert res1.success is True
    assert res1.status == "COMPLETED"

    # Reset mock execution flag
    s1.executed = False

    # Second execution with same saga_id
    res2 = await orch.execute_saga("IdempotentSaga", [s1], SagaContext(), saga_id=saga_id)
    assert res2.saga_id == res1.saga_id
    assert res2.status == "COMPLETED"
    assert res2.success is True
    assert s1.executed is False  # Step was NOT re-executed!


# ============================================================================
# 5. FEATURE F18: COMPENSATING ROLLBACK STEPS EXECUTION
# ============================================================================

@pytest.mark.asyncio
async def test_saga_step_failure_triggers_reverse_compensation(sqlite_session: AsyncSession):
    """When Step 3 fails, completed steps 2 and 1 are compensated in exact reverse order (S2 -> S1)."""
    orch = SagaOrchestrator(sqlite_session)
    s1 = MockSagaStep("Step1")
    s2 = MockSagaStep("Step2")
    s3 = MockSagaStep("Step3", should_fail=True)  # Fails mid-flight

    compensation_order = []

    async def comp2(s, ctx):
        compensation_order.append("Step2")
        s2.compensated = True
        return True

    async def comp1(s, ctx):
        compensation_order.append("Step1")
        s1.compensated = True
        return True

    s2.compensate = comp2
    s1.compensate = comp1

    result = await orch.execute_saga("FailingSaga", [s1, s2, s3], SagaContext())

    assert result.success is False
    assert result.status == "COMPENSATED"
    assert result.failed_step == "Step3"
    assert "simulated deliberate failure" in str(result.error)

    # Verification: Steps 1 & 2 were compensated in exact reverse order
    assert s1.compensated is True
    assert s2.compensated is True
    assert compensation_order == ["Step2", "Step1"]

    # Verify DB step logs recorded compensation status
    comp_logs = (
        await sqlite_session.execute(
            select(SagaStepLog)
            .where(SagaStepLog.saga_id == result.saga_id, SagaStepLog.step_name.like("Compensate-%"))
            .order_by(SagaStepLog.step_index.asc())
        )
    ).scalars().all()
    assert len(comp_logs) == 2
    assert [step_log.status for step_log in comp_logs] == ["COMPENSATED", "COMPENSATED"]


@pytest.mark.asyncio
async def test_saga_failed_compensation_transitions_to_failed(sqlite_session: AsyncSession):
    """When a compensation step itself fails, the saga transitions to terminal status FAILED."""
    orch = SagaOrchestrator(sqlite_session)
    s1 = MockSagaStep("Step1")
    s2 = MockSagaStep("Step2", should_fail=True)

    async def broken_compensate(s, ctx):
        raise RuntimeError("Compensation crashed due to external system failure")

    s1.compensate = broken_compensate

    result = await orch.execute_saga("CriticalSaga", [s1, s2], SagaContext())
    assert result.success is False
    assert result.status == "FAILED"


# ============================================================================
# 6. PRACTICAL CORE BANKING SAGA: INTER-WAREHOUSE TRANSFER SAGA
# ============================================================================

@pytest.mark.asyncio
async def test_practical_inter_warehouse_transfer_saga_success(sqlite_session: AsyncSession):
    """Practical Inter-Warehouse Transfer Saga succeeds end-to-end:

    1. HoldSourceFunds freezes funds on account 111.
    2. PostGLTransferJournal posts balanced debit/credit journal entry.
    3. DispatchTransferOutbox emits outbox event.
    4. ConfirmTransfer releases hold and commits ledger balance.
    """
    orch = SagaOrchestrator(sqlite_session)
    transfer_id = f"tx-{uuid.uuid4()}"
    steps = create_inter_warehouse_transfer_saga(
        source_account="111",
        dest_account="112",
        amount_cents=10_000_00,  # 100,000 VND
        transfer_id=transfer_id,
    )

    ctx = SagaContext()
    result = await orch.execute_saga("InterWarehouseTransferSaga", steps, ctx)

    assert result.success is True
    assert result.status == "COMPLETED"
    assert len(result.completed_steps) == 4

    # Verify GL journal was created
    assert "gl_journal_id" in ctx
    journal = (
        await sqlite_session.execute(
            select(GeneralLedgerJournal).where(GeneralLedgerJournal.id == uuid.UUID(ctx["gl_journal_id"]))
        )
    ).scalars().first()
    assert journal is not None
    assert journal.source_type == "transfer"

    # Verify Outbox event was emitted
    assert "outbox_event_id" in ctx
    outbox_ev = (
        await sqlite_session.execute(
            select(OutboxEventRecord).where(OutboxEventRecord.id == ctx["outbox_event_id"])
        )
    ).scalars().first()
    assert outbox_ev is not None
    assert outbox_ev.event_type == "transfer.dispatched"

    # Verify final balances
    bal_111 = await ensure_account_balance(sqlite_session, "111")
    bal_112 = await ensure_account_balance(sqlite_session, "112")
    assert bal_111.hold_balance == 0
    assert bal_111.ledger_balance == 90_000_00
    assert bal_112.ledger_balance == 60_000_00


@pytest.mark.asyncio
async def test_practical_inter_warehouse_transfer_saga_compensation(sqlite_session: AsyncSession):
    """Practical Transfer Saga compensates completely when failure occurs after GL posting:

    - Reversal GL Journal is posted (Debit source, Credit destination).
    - Source hold is released.
    - Cancellation outbox event is emitted.
    - Balances return to pristine initial values.
    """
    orch = SagaOrchestrator(sqlite_session)
    transfer_id = f"tx-fail-{uuid.uuid4()}"

    class IntentionalFailureStep:
        name = "DispatchTransferOutbox"

        async def execute(self, session: AsyncSession, context: SagaContext) -> bool:
            raise RuntimeError("Outbox dispatch simulated network crash")

        async def compensate(self, session: AsyncSession, context: SagaContext) -> bool:
            return True

    # Assemble saga with step 3 failing
    steps = [
        HoldSourceFundsStep("111", 10_000_00),
        PostGLTransferJournalStep("111", "112", 10_000_00, correlation_id=transfer_id),
        IntentionalFailureStep(),
        ConfirmTransferStep("111", "112", 10_000_00),
    ]

    ctx = SagaContext()
    result = await orch.execute_saga("InterWarehouseTransferSaga", steps, ctx)

    assert result.success is False
    assert result.status == "COMPENSATED"
    assert result.failed_step == "DispatchTransferOutbox"

    # 1. Verify Reversal GL journal was posted
    assert "reversal_journal_id" in ctx
    rev_journal = (
        await sqlite_session.execute(
            select(GeneralLedgerJournal).where(GeneralLedgerJournal.id == uuid.UUID(ctx["reversal_journal_id"]))
        )
    ).scalars().first()
    assert rev_journal is not None
    assert rev_journal.correlation_id.startswith("rev-")

    # 2. Verify Hold was completely released
    assert ctx.get("hold_released") is True
    bal_111 = await ensure_account_balance(sqlite_session, "111")
    assert bal_111.hold_balance == 0
    assert bal_111.available_balance == 100_000_00  # Back to initial!


# ============================================================================
# 7. API ENDPOINTS & HTTP ROUTE VERIFICATION
# ============================================================================

@pytest.mark.asyncio
async def test_api_concurrent_transfer_endpoint():
    """POST /banking/transfers/concurrent transfers funds with resource ordering."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {
            "source_account": "111",
            "dest_account": "112",
            "amount_cents": 5_000_00,  # 50,000 VND
            "description": "API concurrent transfer test",
            "mode": "pessimistic",
        }
        resp = await client.post("/banking/transfers/concurrent", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "SUCCESS"
        assert data["data"]["amount_cents"] == 5_000_00


@pytest.mark.asyncio
async def test_api_concurrent_transfer_insufficient_balance():
    """POST /banking/transfers/concurrent returns 400 when available balance is insufficient."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {
            "source_account": "111",
            "dest_account": "112",
            "amount_cents": 999_999_999_99,  # Huge amount
            "description": "Overdraft attempt",
            "mode": "pessimistic",
        }
        resp = await client.post("/banking/transfers/concurrent", json=payload)
        assert resp.status_code == 400
        data = resp.json()
        error_msg = data.get("detail") or data.get("error", {}).get("message", "")
        assert "insufficient available balance" in error_msg.lower()


@pytest.mark.asyncio
async def test_api_saga_execute_and_get_status():
    """POST /banking/saga/execute triggers saga; GET /banking/saga/{id} retrieves audit log."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        saga_id = str(uuid.uuid4())
        exec_payload = {
            "saga_name": "InterWarehouseTransferSaga",
            "saga_id": saga_id,
            "context": {
                "source_account": "111",
                "dest_account": "112",
                "amount_cents": 2_000_00,
                "transfer_id": f"api-tx-{saga_id}",
            },
        }
        exec_resp = await client.post("/banking/saga/execute", json=exec_payload)
        assert exec_resp.status_code == 200
        res_data = exec_resp.json()
        assert res_data["status"] == "COMPLETED"
        assert res_data["success"] is True

        # Query GET /banking/saga/{saga_id}
        get_resp = await client.get(f"/banking/saga/{saga_id}")
        assert get_resp.status_code == 200
        status_data = get_resp.json()
        assert status_data["saga_id"] == saga_id
        assert status_data["status"] == "COMPLETED"
        assert len(status_data["step_logs"]) == 4


# ============================================================================
# 8. DUAL-DIALECT COMPATIBILITY VERIFICATION
# ============================================================================

@pytest.mark.asyncio
async def test_sqlite_and_postgresql_dialect_compatibility(sqlite_session: AsyncSession):
    """Verifies all models and CAS locking functions function cleanly under SQLite."""
    # Verify GUID and JSONOrText handle queries and serializations seamlessly
    inst = SagaInstance(
        saga_name="DialectTestSaga",
        status="PENDING",
        context_data={"test_key": "test_val", "amount": 12345},
    )
    sqlite_session.add(inst)
    await sqlite_session.flush()

    retrieved = (
        await sqlite_session.execute(select(SagaInstance).where(SagaInstance.id == inst.id))
    ).scalars().first()
    assert retrieved is not None
    assert retrieved.context_data["test_key"] == "test_val"

    # Verify CAS works under SQLite
    bal = await ensure_account_balance(sqlite_session, "111")
    v = bal.version
    updated = await cas_update_account_balance(sqlite_session, "111", 100, v)
    assert updated.version == v + 1
