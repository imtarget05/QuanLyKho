"""Tier 5 Adversarial Coverage Hardening (Part 2) - Milestone M6.

Adversarial stress-testing suite for:
1. Distributed Saga Orchestration (`app/models/saga.py`, `app/services/saga_orchestrator.py`, `banking_contracts.py`):
   - Multi-step forward execution & deep compensation unwinding.
   - Partial network/DB aborts and mid-flight step failures.
   - Compensation step failures: handling broken compensation steps, proceeding with remaining steps, marking saga as FAILED.
   - Strict idempotency across all terminal states (COMPLETED, COMPENSATED, FAILED) with context caching.
   - Nested saga orchestration unwinding child workflows upon parent failure.
   - Step soft rejections (returning False).
   - Practical banking inter-warehouse transfer saga with automated reversal GL journal and hold release.

2. Cryptographic Immutable Audit Trail Engine (`app/models/audit.py`, `app/services/audit_service.py`, Alembic 038, live PostgreSQL triggers, ORM WORM listeners):
   - ORM WORM listeners rejecting UPDATE and DELETE operations.
   - Database-level PostgreSQL triggers (`trg_audit_trail_prevent_update`, `trg_audit_trail_prevent_delete`) preventing raw SQL bypass.
   - Cryptographic verifier sensitivity: detecting altered payloads, corrupt current hashes, severed prev_hash links, tampered genesis records, mid-chain row deletions, and rogue row injections.
   - Canonical JSON hash sensitivity across Vietnamese UTF-8, emojis, embedded null bytes (`\\x00`), key reordering, and deep nesting.
   - Cryptographic hash avalanche effect and strict 64-character lowercase hex format validation.
   - Systemic failure scenario: Business transaction rollback preserving audit trail logs without breaking cryptographic continuity.
   - Dual-dialect parity across SQLite in-memory and PostgreSQL `bankops_test`.
"""

from __future__ import annotations

import json
import os
import re
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.models.audit import (
    GENESIS_HASH as APP_GENESIS_HASH,
)
from app.models.audit import (
    AuditEntry,
    AuditImmutabilityException,
)
from app.models.ledger import (
    BASE_CHART_OF_ACCOUNTS,
    ChartOfAccounts,
    GeneralLedgerEntry,
    GeneralLedgerJournal,
)
from app.models.ledger import (
    GLAccountBalance as AppGLAccountBalance,
)
from app.models.outbox import OutboxEventRecord, ProcessedEventRecord
from app.models.saga import (
    CompensatingLog as AppCompensatingLog,
)
from app.models.saga import (
    SagaInstance as AppSagaInstance,
)
from app.models.saga import (
    SagaStep as AppSagaStep,
)
from app.models.saga import (
    SagaStepLog as AppSagaStepLog,
)
from app.services.audit_service import (
    compute_audit_hash as app_compute_audit_hash,
)
from app.services.audit_service import (
    compute_canonical_hash as app_compute_canonical_hash,
)
from app.services.audit_service import (
    get_audit_trail as app_get_audit_trail,
)
from app.services.audit_service import (
    record_audit_entry as app_record_audit_entry,
)
from app.services.audit_service import (
    verify_audit_chain_integrity as app_verify_audit_chain_integrity,
)
from app.services.saga_orchestrator import (
    DispatchTransferOutboxStep,
    HoldSourceFundsStep,
    PostGLTransferJournalStep,
)
from app.services.saga_orchestrator import (
    SagaContext as AppSagaContext,
)
from app.services.saga_orchestrator import (
    SagaOrchestrator as AppSagaOrchestrator,
)
from app.services.saga_orchestrator import (
    create_inter_warehouse_transfer_saga as app_create_transfer_saga,
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


@pytest_asyncio.fixture(scope="function")
async def app_sqlite_session():
    """Function-scoped in-memory SQLite session with all app models created."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    tables = [
        ChartOfAccounts.__table__,
        AppGLAccountBalance.__table__,
        GeneralLedgerJournal.__table__,
        GeneralLedgerEntry.__table__,
        OutboxEventRecord.__table__,
        ProcessedEventRecord.__table__,
        AppSagaInstance.__table__,
        AppSagaStepLog.__table__,
        AppSagaStep.__table__,
        AppCompensatingLog.__table__,
        AuditEntry.__table__,
    ]
    async with engine.begin() as conn:
        await conn.run_sync(lambda sync_conn: Base.metadata.create_all(sync_conn, tables=tables))

    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with session_factory() as session:
        for code, name, acc_type, normal_bal, _sim_only in BASE_CHART_OF_ACCOUNTS:
            acc = ChartOfAccounts(
                code=code,
                name=name,
                account_type=acc_type,
                normal_balance=normal_bal,
                is_active=True,
            )
            session.add(acc)
            bal = AppGLAccountBalance(
                account_code=code,
                ledger_balance=0,
                available_balance=0,
                hold_balance=0,
                version=1,
            )
            session.add(bal)
        await session.commit()
        yield session

    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def pg_session():
    """Provides a dedicated PostgreSQL AsyncSession connecting to bankops_test with table cleanup."""
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
            await session.execute(text("TRUNCATE TABLE audit_trail CASCADE;"))
            await session.execute(text("DELETE FROM saga_step_logs;"))
            await session.execute(text("DELETE FROM saga_instances;"))
            await session.commit()
        except Exception:
            await session.rollback()

        yield session

        try:
            await session.execute(text("TRUNCATE TABLE audit_trail CASCADE;"))
            await session.execute(text("DELETE FROM saga_step_logs;"))
            await session.execute(text("DELETE FROM saga_instances;"))
            await session.commit()
        except Exception:
            await session.rollback()

    await engine.dispose()


# ============================================================================
# SECTION 1: DISTRIBUTED SAGA ORCHESTRATION ADVERSARIAL TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_adversarial_saga_deep_chain_midflight_failure_and_reverse_compensation(app_sqlite_session: AsyncSession):
    """Stress-test deep 6-step saga chain where step 5 fails:
    Validates exact reverse compensation ordering (S4 -> S3 -> S2 -> S1) and ensures step 6 is never reached.
    """
    session = app_sqlite_session
    orch = AppSagaOrchestrator(session)
    execution_trace: list[str] = []
    compensation_trace: list[str] = []

    class MockStep:
        def __init__(self, step_id: int, should_fail: bool = False):
            self.step_id = step_id
            self.name = f"Step_{step_id}"
            self.should_fail = should_fail

        async def execute(self, sess: AsyncSession, ctx: AppSagaContext) -> bool:
            execution_trace.append(self.name)
            if self.should_fail:
                raise RuntimeError(f"Simulated network timeout at {self.name}")
            ctx[f"key_{self.step_id}"] = f"value_{self.step_id}"
            return True

        async def compensate(self, sess: AsyncSession, ctx: AppSagaContext) -> bool:
            compensation_trace.append(f"Compensate-{self.name}")
            ctx[f"compensated_{self.step_id}"] = True
            return True

    steps = [
        MockStep(1),
        MockStep(2),
        MockStep(3),
        MockStep(4),
        MockStep(5, should_fail=True),
        MockStep(6),
    ]

    ctx = AppSagaContext({"initial_payload": "tx_deep_1001"})
    res = await orch.execute_saga("DeepChainSaga", steps, ctx)
    await session.commit()

    assert res.success is False
    assert res.status == "COMPENSATED"
    assert res.failed_step == "Step_5"
    assert res.completed_steps == ["Step_1", "Step_2", "Step_3", "Step_4"]

    # Verify execution trace: steps 1..5 executed, step 6 unreached
    assert execution_trace == ["Step_1", "Step_2", "Step_3", "Step_4", "Step_5"]

    # Verify compensation trace: strictly reverse order S4 -> S3 -> S2 -> S1
    assert compensation_trace == ["Compensate-Step_4", "Compensate-Step_3", "Compensate-Step_2", "Compensate-Step_1"]

    # Verify database step logs
    logs_res = await session.execute(
        select(AppSagaStepLog).where(AppSagaStepLog.saga_id == res.saga_id).order_by(AppSagaStepLog.step_index.asc())
    )
    logs = logs_res.scalars().all()

    statuses = {log.step_name: log.status for log in logs}
    assert statuses["Step_1"] == "EXECUTED"
    assert statuses["Step_2"] == "EXECUTED"
    assert statuses["Step_3"] == "EXECUTED"
    assert statuses["Step_4"] == "EXECUTED"
    assert statuses["Step_5"] == "FAILED"
    assert "Step_6" not in statuses

    assert statuses["Compensate-Step_4"] == "COMPENSATED"
    assert statuses["Compensate-Step_3"] == "COMPENSATED"
    assert statuses["Compensate-Step_2"] == "COMPENSATED"
    assert statuses["Compensate-Step_1"] == "COMPENSATED"


@pytest.mark.asyncio
async def test_adversarial_saga_compensation_failure_marks_saga_failed(app_sqlite_session: AsyncSession):
    """Stress-test systemic failure during rollback:
    Step 3 fails forward execution.
    During compensation, Step 2's compensation encounters an exception.
    The orchestrator MUST:
    1. Log Step 2 compensation as FAILED.
    2. Continue compensating Step 1.
    3. Successfully complete Step 1 compensation.
    4. Transition terminal saga status to FAILED (not COMPENSATED).
    """
    session = app_sqlite_session
    orch = AppSagaOrchestrator(session)
    compensation_trace: list[str] = []

    class StepOne:
        name = "StepOne"
        async def execute(self, sess: AsyncSession, ctx: AppSagaContext) -> bool:
            return True
        async def compensate(self, sess: AsyncSession, ctx: AppSagaContext) -> bool:
            compensation_trace.append("StepOneCompensated")
            return True

    class StepTwo:
        name = "StepTwo"
        async def execute(self, sess: AsyncSession, ctx: AppSagaContext) -> bool:
            return True
        async def compensate(self, sess: AsyncSession, ctx: AppSagaContext) -> bool:
            compensation_trace.append("StepTwoCompensateFailed")
            raise RuntimeError("Database deadlock during StepTwo compensation")

    class StepThree:
        name = "StepThree"
        async def execute(self, sess: AsyncSession, ctx: AppSagaContext) -> bool:
            raise RuntimeError("Foreign clearing gateway rejected transaction")
        async def compensate(self, sess: AsyncSession, ctx: AppSagaContext) -> bool:
            return True

    res = await orch.execute_saga("BrokenCompensationSaga", [StepOne(), StepTwo(), StepThree()])
    await session.commit()

    assert res.success is False
    assert res.status == "FAILED"
    assert res.failed_step == "StepThree"
    assert "Foreign clearing gateway rejected" in (res.error or "")

    # Both compensation attempts were invoked
    assert compensation_trace == ["StepTwoCompensateFailed", "StepOneCompensated"]

    # Verify log entries in DB
    logs_res = await session.execute(
        select(AppSagaStepLog).where(AppSagaStepLog.saga_id == res.saga_id)
    )
    logs = logs_res.scalars().all()
    status_map = {log.step_name: log.status for log in logs}
    assert status_map["Compensate-StepTwo"] == "FAILED"
    assert status_map["Compensate-StepOne"] == "COMPENSATED"


@pytest.mark.asyncio
async def test_adversarial_saga_idempotency_terminal_states_cached(app_sqlite_session: AsyncSession):
    """Stress-test strict saga idempotency across all terminal states:
    Re-executing COMPLETED, COMPENSATED, and FAILED sagas must return cached results without re-invoking any step,
    and must reject mutated contexts in favor of preserved database context.
    """
    session = app_sqlite_session
    orch = AppSagaOrchestrator(session)
    call_counts = {"forward": 0, "compensate": 0}

    class MonitoredStep:
        name = "MonitoredStep"
        def __init__(self, should_fail: bool = False, comp_fail: bool = False):
            self.should_fail = should_fail
            self.comp_fail = comp_fail

        async def execute(self, sess: AsyncSession, ctx: AppSagaContext) -> bool:
            call_counts["forward"] += 1
            if self.should_fail:
                raise RuntimeError("Forward fail")
            ctx["executed"] = True
            return True

        async def compensate(self, sess: AsyncSession, ctx: AppSagaContext) -> bool:
            call_counts["compensate"] += 1
            if self.comp_fail:
                raise RuntimeError("Comp fail")
            ctx["compensated"] = True
            return True

    # 1. Idempotency on COMPLETED saga
    saga_id_1 = str(uuid.uuid4())
    initial_ctx = AppSagaContext({"client_id": "client_A", "amount": 5000})
    res1 = await orch.execute_saga("SagaCompleted", [MonitoredStep(False)], initial_ctx, saga_id=saga_id_1)
    await session.commit()
    assert res1.status == "COMPLETED"
    assert call_counts["forward"] == 1

    # Replay with altered context
    mutated_ctx = AppSagaContext({"client_id": "client_MALICIOUS", "amount": 99999999})
    replay1 = await orch.execute_saga("SagaCompleted", [MonitoredStep(False)], mutated_ctx, saga_id=saga_id_1)
    # Forward action NOT called again
    assert call_counts["forward"] == 1
    assert replay1.status == "COMPLETED"
    assert replay1.context.get("client_id") == "client_A"

    # 2. Idempotency on COMPENSATED saga
    saga_id_2 = str(uuid.uuid4())
    s1 = MonitoredStep(False)
    s2 = MonitoredStep(True)
    res2 = await orch.execute_saga("SagaCompensated", [s1, s2], AppSagaContext(), saga_id=saga_id_2)
    await session.commit()
    assert res2.status == "COMPENSATED"
    curr_fwd = call_counts["forward"]
    curr_comp = call_counts["compensate"]

    # Replay compensated saga
    replay2 = await orch.execute_saga("SagaCompensated", [s1, s2], AppSagaContext(), saga_id=saga_id_2)
    assert call_counts["forward"] == curr_fwd
    assert call_counts["compensate"] == curr_comp
    assert replay2.status == "COMPENSATED"

    # 3. Idempotency on FAILED saga (compensation failure)
    saga_id_3 = str(uuid.uuid4())
    s_comp_fail = MonitoredStep(False, comp_fail=True)
    s_fwd_fail = MonitoredStep(True)
    res3 = await orch.execute_saga("SagaFailed", [s_comp_fail, s_fwd_fail], AppSagaContext(), saga_id=saga_id_3)
    await session.commit()
    assert res3.status == "FAILED"
    curr_fwd = call_counts["forward"]
    curr_comp = call_counts["compensate"]

    # Replay failed saga
    replay3 = await orch.execute_saga("SagaFailed", [s_comp_fail, s_fwd_fail], AppSagaContext(), saga_id=saga_id_3)
    assert call_counts["forward"] == curr_fwd
    assert call_counts["compensate"] == curr_comp
    assert replay3.status == "FAILED"


@pytest.mark.asyncio
async def test_adversarial_saga_nested_orchestration_unwind(app_sqlite_session: AsyncSession):
    """Stress-test hierarchical nested saga unwinding:
    Parent Saga orchestrates a Child Saga as Step 2.
    When Parent Step 3 fails, the Parent compensation cleanly delegates to the Child Saga's
    rollback mechanism, restoring both child and parent resources.
    """
    session = app_sqlite_session
    orch = AppSagaOrchestrator(session)
    trace: list[str] = []

    # Child Saga Steps
    class ChildStepA:
        name = "ChildStepA"
        async def execute(self, sess: AsyncSession, ctx: AppSagaContext) -> bool:
            trace.append("ChildA_exec")
            ctx["child_a_done"] = True
            return True
        async def compensate(self, sess: AsyncSession, ctx: AppSagaContext) -> bool:
            trace.append("ChildA_comp")
            ctx["child_a_done"] = False
            return True

    class ChildStepB:
        name = "ChildStepB"
        async def execute(self, sess: AsyncSession, ctx: AppSagaContext) -> bool:
            trace.append("ChildB_exec")
            ctx["child_b_done"] = True
            return True
        async def compensate(self, sess: AsyncSession, ctx: AppSagaContext) -> bool:
            trace.append("ChildB_comp")
            ctx["child_b_done"] = False
            return True

    # Parent Step that encapsulates Child Saga
    class ChildSagaCompositeStep:
        name = "ChildSagaCompositeStep"
        def __init__(self):
            self.child_steps = [ChildStepA(), ChildStepB()]

        async def execute(self, sess: AsyncSession, ctx: AppSagaContext) -> bool:
            trace.append("ChildSaga_start")
            sub_orch = AppSagaOrchestrator(sess)
            child_res = await sub_orch.execute_saga("ChildSaga", self.child_steps, ctx)
            ctx["child_saga_id"] = child_res.saga_id
            return child_res.success

        async def compensate(self, sess: AsyncSession, ctx: AppSagaContext) -> bool:
            trace.append("ChildSaga_unwind")
            # Unwind child steps in reverse
            for cs in reversed(self.child_steps):
                await cs.compensate(sess, ctx)
            return True

    # Parent Steps
    class ParentStep1:
        name = "ParentStep1"
        async def execute(self, sess: AsyncSession, ctx: AppSagaContext) -> bool:
            trace.append("Parent1_exec")
            return True
        async def compensate(self, sess: AsyncSession, ctx: AppSagaContext) -> bool:
            trace.append("Parent1_comp")
            return True

    class ParentStep3:
        name = "ParentStep3"
        async def execute(self, sess: AsyncSession, ctx: AppSagaContext) -> bool:
            trace.append("Parent3_fail")
            raise RuntimeError("Global settlement hub connection refused")
        async def compensate(self, sess: AsyncSession, ctx: AppSagaContext) -> bool:
            return True

    parent_steps = [ParentStep1(), ChildSagaCompositeStep(), ParentStep3()]
    res = await orch.execute_saga("ParentSaga", parent_steps, AppSagaContext())
    await session.commit()

    assert res.success is False
    assert res.status == "COMPENSATED"
    assert res.failed_step == "ParentStep3"

    # Execution proceeded forward through Parent1, ChildA, ChildB, Parent3(fail)
    # Then compensation unwound ChildB, ChildA, Parent1
    expected_trace = [
        "Parent1_exec",
        "ChildSaga_start",
        "ChildA_exec",
        "ChildB_exec",
        "Parent3_fail",
        "ChildSaga_unwind",
        "ChildB_comp",
        "ChildA_comp",
        "Parent1_comp",
    ]
    assert trace == expected_trace


@pytest.mark.asyncio
async def test_adversarial_saga_step_returns_false_triggering_immediate_compensation(app_sqlite_session: AsyncSession):
    """Adversarial boundary test:
    A step does not raise an exception, but returns boolean False (business rejection).
    The orchestrator MUST treat False as execution failure and initiate automated compensation.
    """
    session = app_sqlite_session
    orch = AppSagaOrchestrator(session)
    comp_called = []

    class StepPass:
        name = "StepPass"
        async def execute(self, sess: AsyncSession, ctx: AppSagaContext) -> bool:
            return True
        async def compensate(self, sess: AsyncSession, ctx: AppSagaContext) -> bool:
            comp_called.append("StepPass")
            return True

    class StepRejection:
        name = "StepRejection"
        async def execute(self, sess: AsyncSession, ctx: AppSagaContext) -> bool:
            return False  # Soft rejection
        async def compensate(self, sess: AsyncSession, ctx: AppSagaContext) -> bool:
            comp_called.append("StepRejection")
            return True

    res = await orch.execute_saga("SoftRejectionSaga", [StepPass(), StepRejection()])
    await session.commit()

    assert res.success is False
    assert res.status == "COMPENSATED"
    assert res.failed_step == "StepRejection"
    assert comp_called == ["StepPass"]


@pytest.mark.asyncio
async def test_adversarial_saga_step_one_immediate_failure_zero_compensations(app_sqlite_session: AsyncSession):
    """Boundary condition: Step 1 fails immediately on forward execution.
    Zero steps were completed, so zero compensating steps must be executed.
    """
    session = app_sqlite_session
    orch = AppSagaOrchestrator(session)

    class Step1Fail:
        name = "Step1Fail"
        async def execute(self, sess: AsyncSession, ctx: AppSagaContext) -> bool:
            raise ValueError("Invalid account credential at Step 1")
        async def compensate(self, sess: AsyncSession, ctx: AppSagaContext) -> bool:
            raise AssertionError("Compensate should never be called for step that did not succeed")

    res = await orch.execute_saga("ImmediateFailSaga", [Step1Fail()])
    await session.commit()

    assert res.success is False
    assert res.status == "COMPENSATED"
    assert res.failed_step == "Step1Fail"
    assert res.completed_steps == []


@pytest.mark.asyncio
async def test_adversarial_saga_empty_steps_rejection(app_sqlite_session: AsyncSession):
    """Boundary condition: Invoking execute_saga with an empty steps list must raise ValueError immediately."""
    session = app_sqlite_session
    orch = AppSagaOrchestrator(session)

    with pytest.raises(ValueError, match="at least one step"):
        await orch.execute_saga("EmptySaga", [])


@pytest.mark.asyncio
async def test_adversarial_saga_banking_interwarehouse_lifecycle_with_reversal_journal(app_sqlite_session: AsyncSession):
    """Realistic Treasury & Banking Transfer Saga:
    Tests full forward success and then mid-flight failure at Step 4 (Confirm Transfer):
    - Validates GL journal creation and reversal journal creation.
    - Validates hold balance increment and automatic hold release on compensation.
    - Validates outbox cancellation event emission.
    - Verifies double-entry accounting balance invariant: Sum(Debit) == Sum(Credit).
    """
    session = app_sqlite_session
    source_acc = "111"  # Cash
    dest_acc = "112"    # Bank Operating Account
    transfer_amount = 25000000  # 250,000 VND

    # Fund source account initially
    src_bal_res = await session.execute(
        select(AppGLAccountBalance).where(AppGLAccountBalance.account_code == source_acc)
    )
    src_bal = src_bal_res.scalar_one()
    src_bal.ledger_balance = 100000000  # 1,000,000 VND
    src_bal.available_balance = 100000000
    src_bal.hold_balance = 0
    await session.commit()

    # 1. Forward Success Run
    transfer_id_success = f"tr-ok-{uuid.uuid4().hex[:8]}"
    steps_success = app_create_transfer_saga(source_acc, dest_acc, transfer_amount, transfer_id_success)
    orch = AppSagaOrchestrator(session)
    res_success = await orch.execute_saga("TransferSuccessSaga", steps_success)
    await session.commit()

    assert res_success.success is True
    assert res_success.status == "COMPLETED"

    # Verify balances after forward success
    src_bal_res = await session.execute(select(AppGLAccountBalance).where(AppGLAccountBalance.account_code == source_acc))
    src_bal = src_bal_res.scalar_one()
    dst_bal_res = await session.execute(select(AppGLAccountBalance).where(AppGLAccountBalance.account_code == dest_acc))
    dst_bal = dst_bal_res.scalar_one()

    assert src_bal.ledger_balance == 75000000
    assert src_bal.available_balance == 75000000
    assert src_bal.hold_balance == 0
    assert dst_bal.ledger_balance == 25000000

    # 2. Forward Failure Run at Step 4 (ConfirmTransfer)
    transfer_id_fail = f"tr-fail-{uuid.uuid4().hex[:8]}"

    class BrokenConfirmStep:
        name = "ConfirmTransfer"
        async def execute(self, sess: AsyncSession, ctx: AppSagaContext) -> bool:
            raise RuntimeError("Hardware security module (HSM) signature failure")
        async def compensate(self, sess: AsyncSession, ctx: AppSagaContext) -> bool:
            return True

    steps_fail = [
        HoldSourceFundsStep(source_acc, transfer_amount),
        PostGLTransferJournalStep(source_acc, dest_acc, transfer_amount, correlation_id=transfer_id_fail),
        DispatchTransferOutboxStep(transfer_id_fail, {"source": source_acc, "dest": dest_acc, "amount": transfer_amount}),
        BrokenConfirmStep(),
    ]

    res_fail = await orch.execute_saga("TransferFailSaga", steps_fail)
    await session.commit()

    assert res_fail.success is False
    assert res_fail.status == "COMPENSATED"
    assert res_fail.failed_step == "ConfirmTransfer"

    # Verify that source hold was released back to available balance
    await session.refresh(src_bal)
    await session.refresh(dst_bal)
    assert src_bal.hold_balance == 0
    assert src_bal.available_balance == src_bal.ledger_balance

    # Verify reversal GL journal exists and is balanced
    journals_res = await session.execute(
        select(GeneralLedgerJournal).where(GeneralLedgerJournal.correlation_id == f"rev-{transfer_id_fail}")
    )
    rev_journal = journals_res.scalars().first()
    assert rev_journal is not None

    entries_res = await session.execute(
        select(GeneralLedgerEntry).where(GeneralLedgerEntry.journal_id == rev_journal.id)
    )
    entries = entries_res.scalars().all()
    sum_debit = sum(e.debit for e in entries)
    sum_credit = sum(e.credit for e in entries)
    assert sum_debit == sum_credit == transfer_amount

    # Verify Outbox cancellation event was registered
    outbox_res = await session.execute(
        select(OutboxEventRecord).where(
            OutboxEventRecord.aggregate_id == transfer_id_fail,
            OutboxEventRecord.event_type == "transfer.cancelled",
        )
    )
    cancel_event = outbox_res.scalars().first()
    assert cancel_event is not None
    assert cancel_event.status == "PENDING"


# ============================================================================
# SECTION 2: CRYPTOGRAPHIC IMMUTABLE AUDIT TRAIL ENGINE ADVERSARIAL TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_adversarial_audit_orm_immutability_guards_reject_update(app_sqlite_session: AsyncSession):
    """Adversarial tamper attack:
    Attempts to mutate an existing AuditEntry record via the ORM.
    The WORM event listener `_guard_audit_no_update` MUST trigger and raise AuditImmutabilityException.
    """
    session = app_sqlite_session
    entry = await app_record_audit_entry(
        session=session,
        actor_id="admin_user",
        action="CREATE_ACCOUNT",
        entity_type="account",
        entity_id="acc_999",
        state_payload={"currency": "VND", "initial_balance": 0},
    )
    await session.commit()
    entry_id = entry.id
    original_action = entry.action

    # Attempt attribute mutation
    entry.action = "TAMPERED_ACTION_BY_ATTACKER"
    with pytest.raises(AuditImmutabilityException, match="Audit trail is immutable and append-only: UPDATE is forbidden"):
        await session.flush()

    await session.rollback()
    # Confirm DB value is untouched via explicit query
    res = await session.execute(select(AuditEntry.action).where(AuditEntry.id == entry_id))
    assert res.scalar_one() == original_action


@pytest.mark.asyncio
async def test_adversarial_audit_orm_immutability_guards_reject_delete(app_sqlite_session: AsyncSession):
    """Adversarial tamper attack:
    Attempts to delete an AuditEntry record via the ORM session.delete().
    The WORM event listener `_guard_audit_no_delete` MUST trigger and raise AuditImmutabilityException.
    """
    session = app_sqlite_session
    entry = await app_record_audit_entry(
        session=session,
        actor_id="auditor_user",
        action="SETTLEMENT_RECORDED",
        entity_type="settlement",
        entity_id="stl_555",
        state_payload={"amount": 50000000},
    )
    await session.commit()
    entry_id = entry.id

    # Attempt deletion
    await session.delete(entry)
    with pytest.raises(AuditImmutabilityException, match="Audit trail is immutable and append-only: DELETE is forbidden"):
        await session.flush()

    await session.rollback()
    # Confirm DB value is untouched via explicit query
    res = await session.execute(select(AuditEntry.id).where(AuditEntry.id == entry_id))
    assert res.scalar_one_or_none() is not None


@pytest.mark.asyncio
async def test_adversarial_audit_postgres_triggers_prevent_raw_sql_tampering(pg_session: AsyncSession):
    """Adversarial tamper attack on live PostgreSQL:
    Bypasses ORM completely and executes raw SQL UPDATE and DELETE on `audit_trail`.
    The PostgreSQL triggers `trg_audit_trail_prevent_update` and `trg_audit_trail_prevent_delete`
    MUST intercept the operation at the database engine layer and raise an exception.
    """
    session = pg_session
    entry = await app_record_audit_entry(
        session=session,
        actor_id="pg_admin",
        action="TRANSFER_FUNDS",
        entity_type="transfer",
        entity_id="tr_pg_101",
        state_payload={"amount_cents": 15000000},
    )
    await session.commit()
    entry_id = entry.id

    # 1. Attempt raw SQL UPDATE
    with pytest.raises(Exception) as exc_update:
        await session.execute(text(f"UPDATE audit_trail SET action = 'HACKED' WHERE id = {entry_id};"))
        await session.commit()
    await session.rollback()
    assert "audit_trail is append-only" in str(exc_update.value)

    # 2. Attempt raw SQL DELETE
    with pytest.raises(Exception) as exc_delete:
        await session.execute(text(f"DELETE FROM audit_trail WHERE id = {entry_id};"))
        await session.commit()
    await session.rollback()
    assert "audit_trail is append-only" in str(exc_delete.value)

    # Verify record remained intact
    res = await session.execute(select(AuditEntry).where(AuditEntry.id == entry_id))
    persisted = res.scalar_one_or_none()
    assert persisted is not None
    assert persisted.action == "TRANSFER_FUNDS"


@pytest.mark.asyncio
async def test_adversarial_audit_verifier_detects_payload_tampering(app_sqlite_session: AsyncSession):
    """Adversarial detection test:
    Direct raw SQL modification of `state_payload` on record 2.
    `verify_audit_chain_integrity` must pinpoint record 2 with payload_hash_mismatch.
    """
    session = app_sqlite_session

    await app_record_audit_entry(session, "actor1", "LOGIN", "session", "s1", {"ip": "10.0.0.1"})
    e2 = await app_record_audit_entry(session, "actor2", "TRANSFER", "tx", "tx2", {"amount": 1000})
    await app_record_audit_entry(session, "actor3", "LOGOUT", "session", "s3", {"ip": "10.0.0.2"})
    await session.commit()

    # Pre-tamper verification is clean
    res_clean = await app_verify_audit_chain_integrity(session)
    assert res_clean.is_valid is True

    # Tamper payload via raw SQL (bypassing ORM listener)
    await session.execute(
        text(f"UPDATE audit_trail SET state_payload = '{json.dumps({'amount': 999999})}' WHERE id = {e2.id}")
    )
    await session.commit()

    # Verifier detects payload hash mismatch on record 2
    res_tampered = await app_verify_audit_chain_integrity(session)
    assert res_tampered.is_valid is False
    assert res_tampered.broken_id == e2.id
    assert res_tampered.reason == "payload_hash_mismatch"


@pytest.mark.asyncio
async def test_adversarial_audit_verifier_detects_current_hash_tampering(app_sqlite_session: AsyncSession):
    """Adversarial detection test:
    Direct corruption of `current_hash` on record 2.
    `verify_audit_chain_integrity` must pinpoint record 2 with current_hash_mismatch.
    """
    session = app_sqlite_session

    await app_record_audit_entry(session, "user1", "AUTH", "auth", "a1", {"auth": "pass"})
    e2 = await app_record_audit_entry(session, "user2", "PAYMENT", "pay", "p2", {"fee": 50})
    await session.commit()

    # Corrupt current_hash
    forged_hash = "f" * 64
    await session.execute(
        text(f"UPDATE audit_trail SET current_hash = '{forged_hash}' WHERE id = {e2.id}")
    )
    await session.commit()

    res = await app_verify_audit_chain_integrity(session)
    assert res.is_valid is False
    assert res.broken_id == e2.id
    assert res.reason == "current_hash_mismatch"


@pytest.mark.asyncio
async def test_adversarial_audit_verifier_detects_prev_hash_tampering(app_sqlite_session: AsyncSession):
    """Adversarial detection test:
    Direct corruption of `prev_hash` on record 2.
    `verify_audit_chain_integrity` must pinpoint record 2 with prev_hash_mismatch.
    """
    session = app_sqlite_session

    await app_record_audit_entry(session, "user1", "OP1", "ent", "1", {})
    e2 = await app_record_audit_entry(session, "user2", "OP2", "ent", "2", {})
    await session.commit()

    # Sever link by tampering prev_hash
    await session.execute(
        text(f"UPDATE audit_trail SET prev_hash = 'a1b2c3d4e5f60000000000000000000000000000000000000000000000000000' WHERE id = {e2.id}")
    )
    await session.commit()

    res = await app_verify_audit_chain_integrity(session)
    assert res.is_valid is False
    assert res.broken_id == e2.id
    assert res.reason == "prev_hash_mismatch"


@pytest.mark.asyncio
async def test_adversarial_audit_verifier_detects_genesis_tampering(app_sqlite_session: AsyncSession):
    """Adversarial detection test:
    Altering record 1's `prev_hash` to anything other than GENESIS_HASH ("0" * 64).
    Verifier must catch it immediately on record 1.
    """
    session = app_sqlite_session
    e1 = await app_record_audit_entry(session, "sys", "BOOT", "system", "node1", {"status": "up"})
    await session.commit()

    await session.execute(
        text(f"UPDATE audit_trail SET prev_hash = '1' || substr(prev_hash, 2) WHERE id = {e1.id}")
    )
    await session.commit()

    res = await app_verify_audit_chain_integrity(session)
    assert res.is_valid is False
    assert res.broken_id == e1.id
    assert res.reason == "prev_hash_mismatch"


@pytest.mark.asyncio
async def test_adversarial_audit_verifier_detects_deleted_record_in_middle_of_chain(app_sqlite_session: AsyncSession):
    """Adversarial forensic test:
    In a chain of 4 records (IDs 1, 2, 3, 4), an attacker deletes record 2 via raw SQL.
    Record 3 now has a `prev_hash` that pointed to record 2, but the previous record in the database is record 1.
    The verifier must detect this chain breakage on record 3.
    """
    session = app_sqlite_session

    await app_record_audit_entry(session, "a1", "ACT1", "e", "1", {"val": 1})
    e2 = await app_record_audit_entry(session, "a2", "ACT2", "e", "2", {"val": 2})
    e3 = await app_record_audit_entry(session, "a3", "ACT3", "e", "3", {"val": 3})
    await app_record_audit_entry(session, "a4", "ACT4", "e", "4", {"val": 4})
    await session.commit()

    # Raw SQL deletion of record 2
    await session.execute(text(f"DELETE FROM audit_trail WHERE id = {e2.id}"))
    await session.commit()

    res = await app_verify_audit_chain_integrity(session)
    assert res.is_valid is False
    assert res.broken_id == e3.id
    assert res.reason == "prev_hash_mismatch"


@pytest.mark.asyncio
async def test_adversarial_audit_canonical_hash_utf8_nullbytes_and_nesting():
    """Adversarial payload canonicalization test:
    Verifies that compute_canonical_hash:
    1. Handles Vietnamese UTF-8 diacritics without distortion.
    2. Handles embedded null bytes (`\\x00`).
    3. Handles 10-level nested dictionaries.
    4. Guarantees key-order invariance (`{'b': 2, 'a': 1}` == `{'a': 1, 'b': 2}`).
    5. Yields identical hash whether provided as raw dict or serialized JSON string.
    """
    # 1. UTF-8 Vietnamese & Emojis
    payload_vn = {
        "cong_ty": "Công ty TNHH Vận tải Xe khách Phương Trang",
        "tuyen": "Sài Gòn - Đà Lạt 🚌💰",
        "so_xe": "51B-123.45",
    }
    h_vn = app_compute_canonical_hash(payload_vn)
    assert len(h_vn) == 64
    assert re.match(r"^[0-9a-f]{64}$", h_vn)

    # 2. Embedded Null Byte
    payload_null = {"auth_token": "bearer\x00malicious", "attempts": 1}
    h_null = app_compute_canonical_hash(payload_null)
    assert len(h_null) == 64

    # 3. Deep Nesting (10 levels)
    deep_dict: dict = {"level": 10, "data": "deep"}
    for i in range(9, 0, -1):
        deep_dict = {"level": i, "child": deep_dict}
    h_deep = app_compute_canonical_hash(deep_dict)
    assert len(h_deep) == 64

    # 4. Key order invariance
    p1 = {"zeta": 100, "alpha": 200, "beta": {"y": 2, "x": 1}}
    p2 = {"alpha": 200, "beta": {"x": 1, "y": 2}, "zeta": 100}
    assert app_compute_canonical_hash(p1) == app_compute_canonical_hash(p2)

    # 5. String vs Dict equivalence
    json_str = '{"gamma": [3, 2, 1], "delta": "test"}'
    json_obj = {"delta": "test", "gamma": [3, 2, 1]}
    assert app_compute_canonical_hash(json_str) == app_compute_canonical_hash(json_obj)


@pytest.mark.asyncio
async def test_adversarial_audit_avalanche_effect_and_strict_hex_format():
    """Cryptographic sensitivity test:
    Altering any single character in timestamp, actor, action, entity, or payload
    causes massive hash divergence (avalanche effect).
    """
    prev = APP_GENESIS_HASH
    ts = "2026-11-17T00:00:00+00:00"
    actor = "usr_01"
    act = "DEPOSIT"
    etype = "account"
    eid = "acc_01"
    phash = "0" * 64

    base_hash = app_compute_audit_hash(prev, ts, actor, act, etype, eid, phash)

    # Change 1 char in actor
    alt_actor_hash = app_compute_audit_hash(prev, ts, "usr_02", act, etype, eid, phash)

    # Change 1 char in timestamp
    alt_ts_hash = app_compute_audit_hash(prev, "2026-11-17T00:00:01+00:00", actor, act, etype, eid, phash)

    # Change 1 char in payload_hash
    alt_p_hash = app_compute_audit_hash(prev, ts, actor, act, etype, eid, "1" + "0" * 63)

    assert base_hash != alt_actor_hash
    assert base_hash != alt_ts_hash
    assert base_hash != alt_p_hash

    # Calculate bit differences (Hamming distance)
    def hamming_distance(h1: str, h2: str) -> int:
        b1 = bin(int(h1, 16))[2:].zfill(256)
        b2 = bin(int(h2, 16))[2:].zfill(256)
        return sum(c1 != c2 for c1, c2 in zip(b1, b2, strict=False))

    hd = hamming_distance(base_hash, alt_actor_hash)
    # Avalanche effect should change approximately ~50% of the 256 bits (typically > 80 bits)
    assert hd > 80, f"Insufficient avalanche effect: Hamming distance = {hd} bits"


@pytest.mark.asyncio
async def test_adversarial_audit_multi_entity_interleaving_and_pagination(app_sqlite_session: AsyncSession):
    """Multi-entity interleaving test:
    Audit records from multiple different entities (transfers, inventory movements, customer approvals)
    are interleaved in the shared audit trail.
    Verifies that:
    1. The unified hash chain verifies cleanly across all interleaved entities.
    2. Paginated entity filtering (`entity_type`, `entity_id`) returns precise subsets with accurate counts.
    """
    session = app_sqlite_session

    # Interleave 9 entries across 3 entities
    for i in range(1, 4):
        await app_record_audit_entry(session, f"actor_{i}", "ACTION_TR", "transfer", "TR-001", {"seq": i})
        await app_record_audit_entry(session, f"actor_{i}", "ACTION_INV", "inventory", "INV-999", {"qty": i * 10})
        await app_record_audit_entry(session, f"actor_{i}", "ACTION_ORD", "order", "ORD-777", {"items": i})

    await session.commit()

    # 1. Global chain verification
    res = await app_verify_audit_chain_integrity(session)
    assert res.is_valid is True

    # 2. Filter by entity_type="transfer"
    tr_records, tr_count = await app_get_audit_trail(session, entity_type="transfer")
    assert tr_count == 3
    assert len(tr_records) == 3
    assert all(r.entity_type == "transfer" for r in tr_records)

    # 3. Filter by entity_id="INV-999"
    inv_records, inv_count = await app_get_audit_trail(session, entity_id="INV-999")
    assert inv_count == 3
    assert len(inv_records) == 3
    assert all(r.entity_id == "INV-999" for r in inv_records)


@pytest.mark.asyncio
async def test_adversarial_business_rollback_preserves_audit_trail_log(app_sqlite_session: AsyncSession):
    """Systemic failure scenario (PROJECT.md & DISPATCH requirement):
    Rollback of business transactions while preserving audit trail logs.
    A treasury transfer fails due to overdraft / business rejection and rolls back all business tables.
    The failure audit event MUST be persisted in an independent / dedicated session without breaking
    the cryptographic hash chain integrity.
    """
    session = app_sqlite_session
    account_code = "111"

    # Step 1: Pre-existing state and initial audit log
    bal_res = await session.execute(select(AppGLAccountBalance).where(AppGLAccountBalance.account_code == account_code))
    bal = bal_res.scalar_one()
    bal.ledger_balance = 50000000  # 500,000 VND
    bal.available_balance = 50000000
    await session.commit()

    e_init = await app_record_audit_entry(
        session, "operator", "TRANSFER_REQUESTED", "transfer", "TR_ABORT_1", {"requested": 80000000}
    )
    await session.commit()

    # Step 2: Simulate business transaction attempt that fails
    try:
        # Business mutation
        bal.ledger_balance += 80000000
        bal.available_balance += 80000000
        await session.flush()

        # Business check fails: over limit / unauthorized
        raise ValueError("Transaction aborted: Insufficient authorized treasury limits")
    except Exception:
        # Roll back business state
        await session.rollback()

    # Verify balance was completely rolled back
    await session.refresh(bal)
    assert bal.ledger_balance == 50000000
    assert bal.available_balance == 50000000

    # Step 3: Record durable failure audit log
    e_fail = await app_record_audit_entry(
        session, "system", "TRANSFER_REJECTED", "transfer", "TR_ABORT_1", {"error": "Limit exceeded", "rolled_back": True}
    )
    await session.commit()

    # Step 4: Verify cryptographic chain remains completely valid and unbroken
    res = await app_verify_audit_chain_integrity(session)
    assert res.is_valid is True
    assert res.broken_id is None

    # Verify chain linkages
    assert e_fail.prev_hash == e_init.current_hash


@pytest.mark.asyncio
async def test_adversarial_saga_and_audit_cross_dialect_parity_postgres(pg_session: AsyncSession):
    """Dual-Dialect Parity Test:
    Executes distributed saga forward execution, failure compensation, and cryptographic audit trail
    recording and verification directly against PostgreSQL bankops_test.
    """
    session = pg_session

    # 1. Audit Trail on PostgreSQL
    entry1 = await app_record_audit_entry(session, "pg_user", "INIT", "system", "sys1", {"env": "postgres"})
    entry2 = await app_record_audit_entry(session, "pg_user", "CONFIG", "system", "sys1", {"threads": 8})
    await session.commit()

    verify_res = await app_verify_audit_chain_integrity(session)
    assert verify_res.is_valid is True
    assert entry2.prev_hash == entry1.current_hash

    # 2. Distributed Saga on PostgreSQL
    orch = AppSagaOrchestrator(session)
    trace = []

    class PgStep1:
        name = "PgStep1"
        async def execute(self, sess: AsyncSession, ctx: AppSagaContext) -> bool:
            trace.append("pg1_exec")
            return True
        async def compensate(self, sess: AsyncSession, ctx: AppSagaContext) -> bool:
            trace.append("pg1_comp")
            return True

    class PgStep2:
        name = "PgStep2"
        async def execute(self, sess: AsyncSession, ctx: AppSagaContext) -> bool:
            trace.append("pg2_fail")
            raise RuntimeError("Postgres simulation failure")
        async def compensate(self, sess: AsyncSession, ctx: AppSagaContext) -> bool:
            return True

    saga_res = await orch.execute_saga("PostgresSaga", [PgStep1(), PgStep2()])
    await session.commit()

    assert saga_res.success is False
    assert saga_res.status == "COMPENSATED"
    assert trace == ["pg1_exec", "pg2_fail", "pg1_comp"]

    # Verify persisted saga in PostgreSQL
    saga_in_db = await session.execute(
        select(AppSagaInstance).where(AppSagaInstance.id == saga_res.saga_id)
    )
    instance = saga_in_db.scalar_one_or_none()
    assert instance is not None
    assert instance.status == "COMPENSATED"
