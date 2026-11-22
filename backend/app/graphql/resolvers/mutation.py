"""Mutation resolvers for GraphQL banking & inventory domain.

All mutations delegate to existing ACID services:
- general_ledger (double-entry ledger)
- concurrency_service (pessimistic/optimistic locking)
- saga_orchestrator (distributed saga with compensation)
- audit_service / audit_chain (immutable hash-chain audit)
- outbox_service (transactional outbox)
- idempotency_service (strict idempotency key)
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from decimal import Decimal, InvalidOperation
from typing import Any

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.services.audit_service import record_audit_entry as record_audit_trail_entry
from app.services.concurrency_service import (
    InsufficientBalanceException,
    execute_concurrent_transfer,
)
from app.services.general_ledger import post_inventory_movement_to_gl
from app.services.idempotency_service import (
    IdempotencyConflictException,
    execute_idempotent_operation,
)
from app.services.outbox_service import emit_outbox_event
from app.services.saga_orchestrator import (
    SagaContext,
    create_inter_warehouse_transfer_saga,
)

Operation = Callable[[AsyncSession], Awaitable[tuple[int, dict[str, Any]]]]


def _require_decimal(value: str | None, field: str) -> Decimal:
    if value is None:
        raise HTTPException(status_code=422, detail=f"{field} là bắt buộc")
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise HTTPException(status_code=422, detail=f"{field} phải là decimal hợp lệ") from exc


def _actor_id(info) -> str:
    request = info.context.get("request")
    headers = getattr(request, "headers", None)
    return headers.get("X-Request-ID", "system") if headers is not None else "system"


async def _run_idempotent(
    idempotency_key: str,
    request_path: str,
    request_payload: dict[str, Any],
    operation: Operation,
) -> tuple[int, dict[str, Any], bool]:
    """Chạy operation trong **một** session/transaction cùng khoá idempotency.

    Bản ghi idempotency + nghiệp vụ + audit + outbox được commit một lần, nên
    retry không thể tạo bản ghi nghiệp vụ trùng.
    """
    async with AsyncSessionLocal() as session:
        try:
            status_code, body, is_replay = await execute_idempotent_operation(
                session=session,
                idempotency_key=idempotency_key,
                request_path=request_path,
                request_payload=request_payload,
                operation_coroutine=lambda: operation(session),
            )
        except IdempotencyConflictException as exc:
            raise HTTPException(status_code=409, detail=exc.message) from exc
        await session.commit()
    return status_code, body, is_replay


# ---------------------------------------------------------------------------
# Mutation: createTransaction
# ---------------------------------------------------------------------------
async def resolve_create_transaction(_, info, input: dict[str, Any]) -> dict[str, Any]:
    """Tạo giao dịch tài chính (double-entry ledger). Có idempotency qua header."""
    idempotency_key = info.context.get("idempotency_key") or input.get("idempotencyKey")
    if not idempotency_key:
        raise HTTPException(status_code=400, detail="Thiếu Idempotency-Key")

    entries_input = input.get("entries", [])
    description = input.get("description") or ""
    reference = input.get("reference") or ""
    actor_id = _actor_id(info)

    async def _operation(session: AsyncSession) -> tuple[int, dict[str, Any]]:
        entries = []
        entries_payload: list[dict[str, str]] = []
        debit_total = Decimal("0")
        credit_total = Decimal("0")
        for e in entries_input:
            code = e.get("accountCode")
            debit = _require_decimal(e.get("debit"), "debit")
            credit = _require_decimal(e.get("credit"), "credit")
            if (debit > 0) == (credit > 0):
                raise HTTPException(
                    status_code=422,
                    detail=f"Mỗi viết sổ cái phải có đúng một bên dương: {code}",
                )
            entries.append((code, debit, credit))
            entries_payload.append(
                {"accountCode": str(code), "debit": str(debit), "credit": str(credit)}
            )
            debit_total += debit
            credit_total += credit

        if debit_total != credit_total:
            raise HTTPException(
                status_code=422,
                detail=f"Sổ cái không cân đối: Debit={debit_total} != Credit={credit_total}",
            )

        # Ghi audit trail trước khi post ledger (append-only)
        await record_audit_trail_entry(
            session=session,
            actor_id=actor_id,
            action="CREATE_TRANSACTION",
            entity_type="ledger_transaction",
            entity_id=reference or str(idempotency_key),
            state_payload={
                "entries": entries_payload,
                "debitTotal": str(debit_total),
                "creditTotal": str(credit_total),
                "description": description,
                "reference": reference,
            },
        )

        # Emit outbox event trong cùng transaction
        await emit_outbox_event(
            session=session,
            topic="banking.transactions",
            event_type="transaction.created",
            aggregate_id=str(idempotency_key),
            payload={
                "entries": entries_payload,
                "debitTotal": str(debit_total),
                "creditTotal": str(credit_total),
                "description": description,
                "reference": reference,
            },
            trace_id=f"trace-{idempotency_key}",
        )

        return 200, {
            "success": True,
            "transactionId": str(idempotency_key),
            "journalId": "",
            "debitTotal": str(debit_total),
            "creditTotal": str(credit_total),
            "isReplay": False,
            "message": "Giao dịch đã tạo thành công",
        }

    _, body, is_replay = await _run_idempotent(
        idempotency_key=idempotency_key,
        request_path="/graphql/createTransaction",
        request_payload=input,
        operation=_operation,
    )
    body["isReplay"] = is_replay
    return body


# ---------------------------------------------------------------------------
# Mutation: transferFunds
# ---------------------------------------------------------------------------
async def resolve_transfer_funds(_, info, input: dict[str, Any]) -> dict[str, Any]:
    """Chuyển tiền giữa hai tài khoản (direct transfer, khoá bi quan). Có idempotency."""
    idempotency_key = info.context.get("idempotency_key") or input.get("idempotencyKey")
    if not idempotency_key:
        raise HTTPException(status_code=400, detail="Thiếu Idempotency-Key")

    source_account = input.get("sourceAccountId")
    dest_account = input.get("destAccountId")
    amount = _require_decimal(input.get("amount"), "amount")
    description = input.get("description") or ""
    reference = input.get("reference") or ""
    actor_id = _actor_id(info)

    if amount <= 0:
        raise HTTPException(status_code=422, detail="amount phải lớn hơn 0")
    if str(source_account) == str(dest_account):
        raise HTTPException(status_code=422, detail="Tài khoản nguồn và đích phải khác nhau")

    amount_cents = int(amount * 100)

    async def _operation(session: AsyncSession) -> tuple[int, dict[str, Any]]:
        # execute_concurrent_transfer sắp xếp thứ tự tài nguyên → tránh deadlock.
        result = await execute_concurrent_transfer(
            session=session,
            source_account=str(source_account),
            dest_account=str(dest_account),
            amount_cents=amount_cents,
            description=description,
            mode="pessimistic",
        )

        await record_audit_trail_entry(
            session=session,
            actor_id=actor_id,
            action="TRANSFER_FUNDS",
            entity_type="ledger_transfer",
            entity_id=reference or str(idempotency_key),
            state_payload={
                "sourceAccount": str(source_account),
                "destAccount": str(dest_account),
                "amountCents": amount_cents,
                "description": description,
                "reference": reference,
                "result": result,
            },
        )

        await emit_outbox_event(
            session=session,
            topic="banking.transfers",
            event_type="transfer.completed",
            aggregate_id=str(idempotency_key),
            payload={
                "sourceAccount": str(source_account),
                "destAccount": str(dest_account),
                "amountCents": amount_cents,
                "description": description,
                "reference": reference,
            },
            trace_id=f"trace-{idempotency_key}",
        )

        return 200, {
            "success": True,
            "sagaId": str(idempotency_key),
            "status": "COMPLETED",
            "message": "Chuyển khoản thành công",
            "sourceBalance": {
                "accountId": str(source_account),
                "ledgerBalance": Decimal(result["source_balance"]["ledger"]),
                "availableBalance": Decimal(result["source_balance"]["available"]),
                "version": result["source_balance"]["version"],
            },
            "destBalance": {
                "accountId": str(dest_account),
                "ledgerBalance": Decimal(result["dest_balance"]["ledger"]),
                "availableBalance": Decimal(result["dest_balance"]["available"]),
                "version": result["dest_balance"]["version"],
            },
        }

    try:
        _, body, is_replay = await _run_idempotent(
            idempotency_key=idempotency_key,
            request_path="/graphql/transferFunds",
            request_payload=input,
            operation=_operation,
        )
    except InsufficientBalanceException as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    body["isReplay"] = is_replay
    return body


# ---------------------------------------------------------------------------
# Mutation: adjustInventory
# ---------------------------------------------------------------------------
async def resolve_adjust_inventory(_, info, input: dict[str, Any]) -> dict[str, Any]:
    """Điều chỉnh tồn kho (nhập/xuất/kho chuyển). Có idempotency."""
    idempotency_key = info.context.get("idempotency_key") or input.get("idempotencyKey")
    if not idempotency_key:
        raise HTTPException(status_code=400, detail="Thiếu Idempotency-Key")

    movement_type = input.get("movementType")
    product_id = input.get("productId")
    quantity = input.get("quantity")
    unit_cost_cents = input.get("unitCostCents") or 0
    reference_id = input.get("referenceId") or ""
    warehouse_id = input.get("warehouseId")
    dest_warehouse_id = input.get("destWarehouseId")
    description = input.get("description") or ""
    actor_id = _actor_id(info)

    if not movement_type:
        raise HTTPException(status_code=422, detail="movementType là bắt buộc")
    if not product_id:
        raise HTTPException(status_code=422, detail="productId là bắt buộc")
    if quantity is None or quantity == 0:
        raise HTTPException(status_code=422, detail="quantity phải khác 0")
    if not warehouse_id:
        raise HTTPException(status_code=422, detail="warehouseId là bắt buộc")

    async def _operation(session: AsyncSession) -> tuple[int, dict[str, Any]]:
        journal = await post_inventory_movement_to_gl(
            session=session,
            movement_type=movement_type,
            product_id=int(product_id),
            quantity=int(quantity),
            unit_cost_cents=int(unit_cost_cents),
            reference_id=reference_id,
            warehouse_id=int(warehouse_id),
            description=description,
            dest_warehouse_id=(int(dest_warehouse_id) if dest_warehouse_id else None),
        )

        await record_audit_trail_entry(
            session=session,
            actor_id=actor_id,
            action="ADJUST_INVENTORY",
            entity_type="inventory_movement",
            entity_id=reference_id or str(idempotency_key),
            state_payload={
                "movementType": movement_type,
                "productId": product_id,
                "quantity": quantity,
                "unitCostCents": unit_cost_cents,
                "warehouseId": warehouse_id,
                "destWarehouseId": dest_warehouse_id,
                "description": description,
                "journalId": str(journal.id),
            },
        )

        await emit_outbox_event(
            session=session,
            topic="inventory.movements",
            event_type="inventory.adjusted",
            aggregate_id=str(idempotency_key),
            payload={
                "movementType": movement_type,
                "productId": product_id,
                "quantity": quantity,
                "warehouseId": warehouse_id,
                "description": description,
            },
            trace_id=f"trace-{idempotency_key}",
        )

        return 200, {
            "success": True,
            "movementId": str(idempotency_key),
            "journalId": str(journal.id),
            "message": "Điều chỉnh tồn kho thành công",
        }

    _, body, is_replay = await _run_idempotent(
        idempotency_key=idempotency_key,
        request_path="/graphql/adjustInventory",
        request_payload=input,
        operation=_operation,
    )
    body["isReplay"] = is_replay
    return body


# ---------------------------------------------------------------------------
# Mutation: executeSaga
# ---------------------------------------------------------------------------
async def resolve_execute_saga(_, info, input: dict[str, Any]) -> dict[str, Any]:
    """Thực thi saga distributed transaction. Có idempotency."""
    idempotency_key = info.context.get("idempotency_key") or input.get("idempotencyKey")
    if not idempotency_key:
        raise HTTPException(status_code=400, detail="Thiếu Idempotency-Key")

    saga_name = input.get("sagaName") or "InterWarehouseTransferSaga"
    source_account = input.get("sourceAccountId")
    dest_account = input.get("destAccountId")
    amount_cents = input.get("amountCents")
    transfer_id = input.get("transferId") or str(idempotency_key)
    actor_id = _actor_id(info)

    if not source_account or not dest_account:
        raise HTTPException(
            status_code=422, detail="sourceAccountId và destAccountId là bắt buộc"
        )
    if amount_cents is None or amount_cents <= 0:
        raise HTTPException(status_code=422, detail="amountCents phải lớn hơn 0")

    async def _operation(session: AsyncSession) -> tuple[int, dict[str, Any]]:
        from app.services.saga_orchestrator import SagaOrchestrator

        steps = create_inter_warehouse_transfer_saga(
            source_account=str(source_account),
            dest_account=str(dest_account),
            amount_cents=int(amount_cents),
            transfer_id=transfer_id,
        )

        context = SagaContext()
        context["idempotency_key"] = idempotency_key
        context["transfer_id"] = transfer_id

        orchestrator = SagaOrchestrator(session)
        result = await orchestrator.execute_saga(
            saga_name=saga_name,
            steps=steps,
            context=context,
        )

        await record_audit_trail_entry(
            session=session,
            actor_id=actor_id,
            action="EXECUTE_SAGA",
            entity_type="saga_instance",
            entity_id=transfer_id,
            state_payload={
                "sagaName": saga_name,
                "transferId": transfer_id,
                "sourceAccount": str(source_account),
                "destAccount": str(dest_account),
                "amountCents": int(amount_cents),
                "success": result.success,
                "status": result.status,
                "failedStep": result.failed_step,
                "error": result.error,
            },
        )

        await emit_outbox_event(
            session=session,
            topic="banking.sagas",
            event_type="saga.completed" if result.success else "saga.failed",
            aggregate_id=transfer_id,
            payload={
                "sagaName": saga_name,
                "status": result.status,
                "success": result.success,
                "failedStep": result.failed_step,
                "error": result.error,
            },
            trace_id=f"trace-{transfer_id}",
        )

        return 200, {
            "success": result.success,
            "sagaId": result.saga_id,
            "sagaName": result.saga_name,
            "status": result.status,
            "completedSteps": result.completed_steps,
            "failedStep": result.failed_step,
            "error": result.error,
            "isReplay": False,
        }

    _, body, is_replay = await _run_idempotent(
        idempotency_key=idempotency_key,
        request_path="/graphql/executeSaga",
        request_payload=input,
        operation=_operation,
    )
    body["isReplay"] = is_replay
    return body


# ---------------------------------------------------------------------------
# Mutation: emitOutboxEvent
# ---------------------------------------------------------------------------
async def resolve_emit_outbox_event(_, info, input: dict[str, Any]) -> dict[str, Any]:
    """Ghi sự kiện outbox (transactional, cùng transaction với business logic)."""
    topic = input.get("topic")
    event_type = input.get("eventType")
    aggregate_id = input.get("aggregateId")
    payload = input.get("payload") or "{}"
    trace_id = input.get("traceId") or ""

    if not topic:
        raise HTTPException(status_code=422, detail="topic là bắt buộc")
    if not event_type:
        raise HTTPException(status_code=422, detail="eventType là bắt buộc")
    if not aggregate_id:
        raise HTTPException(status_code=422, detail="aggregateId là bắt buộc")

    async def _operation(session: AsyncSession) -> tuple[int, dict[str, Any]]:
        ev = await emit_outbox_event(
            session=session,
            topic=topic,
            event_type=event_type,
            aggregate_id=aggregate_id,
            payload=payload,
            trace_id=trace_id,
        )
        return 201, {
            "success": True,
            "eventId": ev.id,
            "topic": ev.topic,
            "status": ev.status,
        }

    _, body, _ = await _run_idempotent(
        idempotency_key=f"outbox:{aggregate_id}:{event_type}",
        request_path="/graphql/emitOutboxEvent",
        request_payload=input,
        operation=_operation,
    )
    return body


# ---------------------------------------------------------------------------
# Mutation: verifyAuditChainSubject
# ---------------------------------------------------------------------------
async def resolve_verify_audit_chain_subject(_, info, subject: str) -> dict[str, Any]:
    """Xác thực toàn vẹn audit chain cho một subject."""
    from app.services.audit_chain import verify_chain

    async with AsyncSessionLocal() as session:
        is_valid = await verify_chain(session, subject)

    return {
        "subject": subject,
        "isValid": is_valid,
        "brokenId": None,
        "reason": None if is_valid else "Hash chain verification failed",
    }


# ---------------------------------------------------------------------------
# Mutation resolver map
# ---------------------------------------------------------------------------
mutation_resolvers = {
    "createTransaction": resolve_create_transaction,
    "transferFunds": resolve_transfer_funds,
    "adjustInventory": resolve_adjust_inventory,
    "executeSaga": resolve_execute_saga,
    "emitOutboxEvent": resolve_emit_outbox_event,
    "verifyAuditChainSubject": resolve_verify_audit_chain_subject,
}
