"""Distributed Saga Orchestration Engine (Milestone M4, interview-prep 02/05 §4).

Implements:
- Feature F16 & F17: Forward Saga Execution (SagaOrchestrator.execute_saga)
- Feature F18: Automated Reverse Compensating Steps Execution on failure
- Idempotent execution: existing terminal saga returns cached result
- Comprehensive step audit logging in saga_step_logs table
- Practical Banking Sagas: InterWarehouseTransferSaga & PaymentFulfillmentSaga
"""

from __future__ import annotations

import inspect
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ledger import GeneralLedgerEntry, GeneralLedgerJournal
from app.models.saga import SagaInstance, SagaStepLog
from app.services.concurrency_service import (
    ensure_account_balance,
    hold_account_funds,
    release_account_hold,
)
from app.services.outbox_service import emit_outbox_event

# ============================================================================
# PROTOCOLS & DATA STRUCTURES
# ============================================================================

class SagaContext(dict):
    """Context dictionary passed across saga steps containing shared state."""
    pass


class SagaStep(Protocol):
    name: str

    async def execute(self, session: AsyncSession, context: SagaContext) -> bool:
        ...

    async def compensate(self, session: AsyncSession, context: SagaContext) -> bool:
        ...


class SagaResult:
    """Standardized result returned upon completion or compensation of a Saga."""

    def __init__(
        self,
        saga_id: str,
        saga_name: str,
        success: bool,
        status: str,
        completed_steps: list[str],
        failed_step: str | None = None,
        error: str | None = None,
        context: dict[str, Any] | None = None,
    ):
        self.saga_id = saga_id
        self.saga_name = saga_name
        self.success = success
        self.status = status
        self.completed_steps = completed_steps
        self.failed_step = failed_step
        self.error = error
        self.context = context or {}

    def to_dict(self) -> dict[str, Any]:
        return {
            "saga_id": self.saga_id,
            "saga_name": self.saga_name,
            "success": self.success,
            "status": self.status,
            "completed_steps": self.completed_steps,
            "failed_step": self.failed_step,
            "error": self.error,
        }

    def __repr__(self) -> str:
        return (
            f"<SagaResult {self.saga_name} (id={self.saga_id}) "
            f"success={self.success} status={self.status} failed={self.failed_step}>"
        )


async def _invoke_step(method: Callable, session: AsyncSession, context: SagaContext) -> Any:
    """Invokes step method supporting both (session, context) and (context) signatures."""
    sig = inspect.signature(method)
    params = list(sig.parameters.values())
    if len(params) <= 1:
        return await method(context)
    return await method(session, context)


# ============================================================================
# SAGA ORCHESTRATOR
# ============================================================================

class SagaOrchestrator:
    """State machine coordinator for distributed transactions with automated rollback."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def execute_saga(
        self,
        saga_name: str,
        steps: list[Any],
        context: SagaContext | None = None,
        saga_id: str | None = None,
    ) -> SagaResult:
        """Executes saga steps sequentially with automated compensation rollback upon failure.

        1. Idempotency Check: if saga_id is provided and already terminal (COMPLETED,
           COMPENSATED, FAILED), returns cached result without re-executing steps.
        2. Sequential Forward Execution: executes each step, persists step audit log,
           and records output in context.
        3. Automated Compensation Rollback: on step failure, catches exception,
           transitions status to COMPENSATING, and executes compensate() in exact
           reverse order for all completed steps.
        4. State Persistence: records every state transition and step outcome
           in saga_instances and saga_step_logs tables.
        """
        if not steps:
            raise ValueError("Saga must contain at least one step.")

        ctx = context if context is not None else SagaContext()
        sid = str(saga_id or uuid.uuid4())

        # 1. Idempotency check against database
        res = await self.session.execute(
            select(SagaInstance).where(SagaInstance.id == sid)
        )
        existing = res.scalars().first()

        if existing and existing.status in ("COMPLETED", "COMPENSATED", "FAILED", "completed", "failed"):
            # Return cached terminal result
            completed_step_names = [
                log.step_name
                for log in (existing.step_logs or [])
                if log.status in ("EXECUTED", "COMPLETED", "done")
            ]
            is_success = existing.status in ("COMPLETED", "completed")
            return SagaResult(
                saga_id=str(existing.id),
                saga_name=existing.saga_name or saga_name,
                success=is_success,
                status=existing.status.upper(),
                completed_steps=completed_step_names,
                error=existing.error_message,
                context=existing.context or dict(ctx),
            )

        now = datetime.now(UTC)
        if not existing:
            saga_rec = SagaInstance(
                id=sid,
                saga_name=saga_name,
                saga_type=saga_name,
                status="RUNNING",
                current_step=getattr(steps[0], "name", "Step1"),
                context_data=dict(ctx),
                context_json=dict(ctx),
                created_at=now,
                updated_at=now,
            )
            self.session.add(saga_rec)
        else:
            saga_rec = existing
            saga_rec.status = "RUNNING"
            saga_rec.updated_at = now
        await self.session.flush()

        completed_steps: list[Any] = []

        # 2. Sequential Forward Step Execution
        for idx, step in enumerate(steps, start=1):
            step_name = getattr(step, "name", f"Step_{idx}")
            saga_rec.current_step = step_name
            saga_rec.updated_at = datetime.now(UTC)

            step_log = SagaStepLog(
                saga_id=saga_rec.id,
                step_name=step_name,
                step_index=idx,
                status="PENDING",
                input_data=dict(ctx),
                created_at=datetime.now(UTC),
            )
            self.session.add(step_log)
            await self.session.flush()

            try:
                # Forward execution
                exec_fn = getattr(step, "execute", None)
                if exec_fn is None:
                    raise AttributeError(f"Step '{step_name}' has no execute method.")

                ok = await _invoke_step(exec_fn, self.session, ctx)
                if ok is False:
                    raise RuntimeError(f"Step '{step_name}' returned False (execution rejected).")

                # Step Succeeded
                step_log.status = "EXECUTED"
                step_log.output_data = {"result": ok, "context_snapshot": dict(ctx)}
                step_log.executed_at = datetime.now(UTC)
                completed_steps.append(step)
                saga_rec.context_data = dict(ctx)
                await self.session.flush()

            except Exception as exc:
                # 3. Step Failed: Initiate Automated Compensating Rollback
                step_log.status = "FAILED"
                step_log.error_message = str(exc)
                step_log.executed_at = datetime.now(UTC)
                saga_rec.status = "COMPENSATING"
                saga_rec.error_message = str(exc)
                saga_rec.updated_at = datetime.now(UTC)
                await self.session.flush()

                compensation_failed = False
                comp_idx = idx + 100

                # Compensate completed steps in exact reverse order
                for comp_step in reversed(completed_steps):
                    comp_name = getattr(comp_step, "name", "UnknownStep")
                    comp_log = SagaStepLog(
                        saga_id=saga_rec.id,
                        step_name=f"Compensate-{comp_name}",
                        step_index=comp_idx,
                        status="PENDING",
                        input_data=dict(ctx),
                        created_at=datetime.now(UTC),
                    )
                    self.session.add(comp_log)
                    await self.session.flush()
                    comp_idx += 1

                    try:
                        comp_fn = getattr(comp_step, "compensate", None)
                        if comp_fn is not None:
                            await _invoke_step(comp_fn, self.session, ctx)
                        comp_log.status = "COMPENSATED"
                        comp_log.compensated_at = datetime.now(UTC)
                        comp_log.output_data = {"compensated": True}
                    except Exception as comp_err:
                        compensation_failed = True
                        comp_log.status = "FAILED"
                        comp_log.error_message = str(comp_err)

                    await self.session.flush()

                # Transition terminal status
                final_status = "FAILED" if compensation_failed else "COMPENSATED"
                saga_rec.status = final_status
                saga_rec.updated_at = datetime.now(UTC)
                await self.session.flush()

                return SagaResult(
                    saga_id=str(saga_rec.id),
                    saga_name=saga_name,
                    success=False,
                    status=final_status,
                    completed_steps=[getattr(s, "name", "step") for s in completed_steps],
                    failed_step=step_name,
                    error=str(exc),
                    context=dict(ctx),
                )

        # 4. All Steps Completed Successfully
        saga_rec.status = "COMPLETED"
        saga_rec.current_step = "FINAL"
        saga_rec.updated_at = datetime.now(UTC)
        saga_rec.context_data = dict(ctx)
        await self.session.flush()

        return SagaResult(
            saga_id=str(saga_rec.id),
            saga_name=saga_name,
            success=True,
            status="COMPLETED",
            completed_steps=[getattr(s, "name", "step") for s in completed_steps],
            context=dict(ctx),
        )

    async def execute(
        self,
        *,
        saga_id: str,
        saga_type: str,
        steps: list[dict[str, Any]],
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Backwards compatibility adapter for legacy dictionary-based steps."""
        ctx = SagaContext(context or {})

        class DictStepAdapter:
            def __init__(self, step_dict: dict[str, Any]):
                self.name = step_dict["name"]
                self._action = step_dict["action"]
                self._compensate = step_dict.get("compensate")

            async def execute(self, session: AsyncSession, context: SagaContext) -> bool:
                res = await self._action(session, context)
                return True if res is None else bool(res)

            async def compensate(self, session: AsyncSession, context: SagaContext) -> bool:
                if self._compensate:
                    await self._compensate(session, context)
                return True

        adapted_steps = [DictStepAdapter(sd) for sd in steps]
        res = await self.execute_saga(
            saga_name=saga_type,
            steps=adapted_steps,
            context=ctx,
            saga_id=saga_id,
        )
        return {
            "saga_id": res.saga_id,
            "saga_type": res.saga_name,
            "status": res.status.lower(),
            "current_step": res.failed_step or "FINAL",
            "context": res.context,
            "success": res.success,
        }


# ============================================================================
# PRACTICAL CORE BANKING SAGA IMPLEMENTATION: INTER-WAREHOUSE TRANSFER SAGA
# ============================================================================

class HoldSourceFundsStep:
    """Step 1: Freezes funds/inventory at the source warehouse."""

    def __init__(self, source_account: str, amount_cents: int):
        self.name = "HoldSourceFunds"
        self.source_account = source_account
        self.amount_cents = amount_cents

    async def execute(self, session: AsyncSession, context: SagaContext) -> bool:
        await hold_account_funds(session, self.source_account, self.amount_cents)
        context["funds_held"] = True
        context["held_account"] = self.source_account
        context["held_amount"] = self.amount_cents
        return True

    async def compensate(self, session: AsyncSession, context: SagaContext) -> bool:
        if context.get("funds_held"):
            await release_account_hold(session, self.source_account, self.amount_cents)
            context["funds_held"] = False
            context["hold_released"] = True
        return True


class PostGLTransferJournalStep:
    """Step 2: Posts balanced General Ledger double-entry journal (Debit Dest, Credit Source)."""

    def __init__(self, source_account: str, dest_account: str, amount_cents: int, correlation_id: str):
        self.name = "PostGLTransferJournal"
        self.source_account = source_account
        self.dest_account = dest_account
        self.amount_cents = amount_cents
        self.correlation_id = correlation_id

    async def execute(self, session: AsyncSession, context: SagaContext) -> bool:
        journal = GeneralLedgerJournal(
            source_type="transfer",
            source_journal_id=uuid.uuid4(),
            correlation_id=self.correlation_id,
            posted_at=datetime.now(UTC),
        )
        session.add(journal)
        await session.flush()

        # Debit destination, Credit source
        e_debit = GeneralLedgerEntry(
            journal_id=journal.id,
            account_code=self.dest_account,
            debit=self.amount_cents,
            credit=0,
        )
        e_credit = GeneralLedgerEntry(
            journal_id=journal.id,
            account_code=self.source_account,
            debit=0,
            credit=self.amount_cents,
        )
        session.add(e_debit)
        session.add(e_credit)
        await session.flush()

        context["gl_journal_id"] = str(journal.id)
        return True

    async def compensate(self, session: AsyncSession, context: SagaContext) -> bool:
        if context.get("gl_journal_id"):
            # Post reversal journal: Debit source, Credit dest
            rev_journal = GeneralLedgerJournal(
                source_type="transfer",
                source_journal_id=uuid.uuid4(),
                correlation_id=f"rev-{self.correlation_id}",
                posted_at=datetime.now(UTC),
            )
            session.add(rev_journal)
            await session.flush()

            e_rev_debit = GeneralLedgerEntry(
                journal_id=rev_journal.id,
                account_code=self.source_account,
                debit=self.amount_cents,
                credit=0,
            )
            e_rev_credit = GeneralLedgerEntry(
                journal_id=rev_journal.id,
                account_code=self.dest_account,
                debit=0,
                credit=self.amount_cents,
            )
            session.add(e_rev_debit)
            session.add(e_rev_credit)
            await session.flush()

            context["reversal_journal_id"] = str(rev_journal.id)
        return True


class DispatchTransferOutboxStep:
    """Step 3: Atomically registers transactional outbox event for async messaging."""

    def __init__(self, transfer_id: str, payload: dict[str, Any]):
        self.name = "DispatchTransferOutbox"
        self.transfer_id = transfer_id
        self.payload = payload

    async def execute(self, session: AsyncSession, context: SagaContext) -> bool:
        ev = await emit_outbox_event(
            session=session,
            topic="banking.transfers",
            event_type="transfer.dispatched",
            aggregate_id=self.transfer_id,
            payload=self.payload,
            trace_id=f"trace-{self.transfer_id}",
        )
        context["outbox_event_id"] = str(ev.id)
        return True

    async def compensate(self, session: AsyncSession, context: SagaContext) -> bool:
        cancel_ev = await emit_outbox_event(
            session=session,
            topic="banking.transfers",
            event_type="transfer.cancelled",
            aggregate_id=self.transfer_id,
            payload={"reason": "Saga compensation", "original_payload": self.payload},
            trace_id=f"trace-cancel-{self.transfer_id}",
        )
        context["cancel_outbox_event_id"] = str(cancel_ev.id)
        return True


class ConfirmTransferStep:
    """Step 4: Releases source hold and applies net ledger deduction."""

    def __init__(self, source_account: str, dest_account: str, amount_cents: int):
        self.name = "ConfirmTransfer"
        self.source_account = source_account
        self.dest_account = dest_account
        self.amount_cents = amount_cents

    async def execute(self, session: AsyncSession, context: SagaContext) -> bool:
        # Release hold and adjust ledger
        src_bal = await ensure_account_balance(session, self.source_account)
        src_bal.hold_balance -= self.amount_cents
        src_bal.ledger_balance -= self.amount_cents
        src_bal.available_balance = src_bal.ledger_balance - src_bal.hold_balance
        src_bal.version += 1
        src_bal.updated_at = datetime.now(UTC)

        dst_bal = await ensure_account_balance(session, self.dest_account)
        dst_bal.ledger_balance += self.amount_cents
        dst_bal.available_balance = dst_bal.ledger_balance - dst_bal.hold_balance
        dst_bal.version += 1
        dst_bal.updated_at = datetime.now(UTC)

        await session.flush()
        context["confirmed"] = True
        return True

    async def compensate(self, session: AsyncSession, context: SagaContext) -> bool:
        # Final step compensation is no-op if executed after complete
        return True


def create_inter_warehouse_transfer_saga(
    source_account: str,
    dest_account: str,
    amount_cents: int,
    transfer_id: str,
) -> list[Any]:
    """Factory creating the steps for an Inter-Warehouse / Multi-Account Transfer Saga."""
    payload = {
        "transfer_id": transfer_id,
        "source_account": source_account,
        "dest_account": dest_account,
        "amount_cents": amount_cents,
    }
    return [
        HoldSourceFundsStep(source_account, amount_cents),
        PostGLTransferJournalStep(source_account, dest_account, amount_cents, correlation_id=transfer_id),
        DispatchTransferOutboxStep(transfer_id, payload),
        ConfirmTransferStep(source_account, dest_account, amount_cents),
    ]


# Alias for PaymentFulfillmentSaga
create_payment_fulfillment_saga = create_inter_warehouse_transfer_saga
InterWarehouseTransferSaga = create_inter_warehouse_transfer_saga
PaymentFulfillmentSaga = create_payment_fulfillment_saga
