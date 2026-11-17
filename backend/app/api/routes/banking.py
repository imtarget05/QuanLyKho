"""API ngân hàng: chuyển tiền, TCC reserve/confirm/cancel, truy vấn saga,
xác minh audit hash-chain (interview-prep 02/05, 03/02, 03/06).

Tất cả write diễn ra trong một transaction ACID duy nhất: nghiệp vụ +
general-ledger (double-entry) + outbox + audit hash-chain, khắc phục
Dual-Write Problem. Idempotency-Key (header) chặn request trùng lặp.
"""

from __future__ import annotations

import uuid
from decimal import Decimal, InvalidOperation
from uuid import NAMESPACE_URL, UUID, uuid5

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.activity import OutboxEvent
from app.models.idempotency import IdempotencyKeyRecord
from app.models.outbox import OutboxEventRecord
from app.models.saga import SagaInstance, SagaStep, SagaStepLog
from app.services.audit_chain import append_audit_event, verify_chain
from app.services.audit_service import (
    get_audit_trail,
    verify_audit_chain_integrity,
)
from app.services.audit_service import (
    record_audit_entry as record_audit_trail_entry,
)
from app.services.concurrency import (
    ConcurrencyConflict,
    InsufficientBalance,
    apply_quantity_change,
    commit_reservation,
    release_reservation,
    reserve_balance,
)
from app.services.concurrency_service import (
    InsufficientBalanceException as ConcurrencyInsufficientBalance,
)
from app.services.concurrency_service import (
    OptimisticLockException,
    execute_concurrent_transfer,
)
from app.services.idempotency_service import (
    IdempotencyConflictException,
    IdempotencyInFlightException,
    execute_idempotent_operation,
)
from app.services.outbox_service import (
    drain_outbox_events,
    emit_outbox_event,
)
from app.services.saga import SagaError, SagaOrchestrator
from app.services.saga_orchestrator import (
    SagaContext,
    create_inter_warehouse_transfer_saga,
)
from app.services.saga_orchestrator import (
    SagaOrchestrator as ModernSagaOrchestrator,
)

router = APIRouter()

_NAMESPACE = NAMESPACE_URL


def _saga_id(idempotency_key: str) -> str:
    return str(uuid5(_NAMESPACE, f"banking:transfer:{idempotency_key}"))


class TransferRequest(BaseModel):
    source_location_id: str = Field(..., description="Vị trí nguồn")
    source_item_id: str = Field(..., description="Mặt hàng nguồn")
    dest_location_id: str = Field(..., description="Vị trí đích")
    dest_item_id: str = Field(..., description="Mặt hàng đích")
    amount: str = Field(..., description="Số tiền (chuỗi decimal, ví dụ '1000.00')")
    reference: str | None = Field(None, description="Mã tham chiếu nghiệp vụ")


class TransferResponse(BaseModel):
    saga_id: str
    status: str
    message: str


@router.post("/banking/transfer", response_model=TransferResponse, status_code=202)
async def transfer(
    body: TransferRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> TransferResponse:
    if not idempotency_key:
        raise HTTPException(status_code=400, detail="Thiếu Idempotency-Key")
    try:
        amount = Decimal(body.amount)
    except (InvalidOperation, ValueError) as exc:
        raise HTTPException(status_code=422, detail="amount phải là decimal hợp lệ") from exc
    if amount <= 0:
        raise HTTPException(status_code=422, detail="amount phải lớn hơn 0")

    saga_id = _saga_id(idempotency_key)
    context = {
        "source_location_id": body.source_location_id,
        "source_item_id": body.source_item_id,
        "dest_location_id": body.dest_location_id,
        "dest_item_id": body.dest_item_id,
        "amount": str(amount),
        "reference": body.reference,
    }

    async with AsyncSessionLocal() as session:
        orchestrator = SagaOrchestrator(session)

        def make_steps():
            src_loc = body.source_location_id
            src_item = body.source_item_id
            dst_loc = body.dest_location_id
            dst_item = body.dest_item_id

            async def reserve_source(s, ctx):
                await reserve_balance(s, src_loc, src_item, amount)

            async def release_source(s, ctx):
                try:
                    await release_reservation(s, src_loc, src_item, amount)
                except InsufficientBalance:
                    pass  # bù trừ tối đa esfuerzo

            async def do_transfer(s, ctx):
                # Confirm: trừ nguồn (commit reservation) rồi cộng đích.
                await commit_reservation(s, src_loc, src_item, amount)
                await apply_quantity_change(s, dst_loc, dst_item, amount)

            async def undo_transfer(s, ctx):
                try:
                    await apply_quantity_change(s, src_loc, src_item, amount)
                except InsufficientBalance:
                    pass
                try:
                    await apply_quantity_change(s, dst_loc, dst_item, -amount)
                except InsufficientBalance:
                    pass

            return [
                {"name": "reserve_source", "action": reserve_source, "compensate": release_source},
                {"name": "transfer", "action": do_transfer, "compensate": undo_transfer},
            ]

        try:
            result = await orchestrator.execute(
                saga_id=saga_id,
                saga_type="transfer",
                steps=make_steps(),
                context=context,
            )
        except SagaError as exc:
            await session.rollback()
            raise HTTPException(
                status_code=409,
                detail=f"Saga thất bại tại bước {exc.step_name}: {exc}",
            ) from exc
        except ConcurrencyConflict as exc:
            await session.rollback()
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except InsufficientBalance as exc:
            await session.rollback()
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        # Ghi audit + outbox cùng transaction (ACID duy nhất).
        await append_audit_event(
            session,
            subject=f"transfer:{saga_id}",
            action="banking.transfer",
            request_id=idempotency_key,
            before_hash=None,
            after_hash=None,
            metadata_json={
                "saga_id": saga_id,
                "status": result["status"],
                "source": f"{body.source_location_id}:{body.source_item_id}",
                "dest": f"{body.dest_location_id}:{body.dest_item_id}",
                "amount": str(amount),
            },
        )
        session.add(
            OutboxEvent(
                event_type="banking.transfer.completed",
                aggregate_id=saga_id,
                payload_json={
                    "saga_id": saga_id,
                    "status": result["status"],
                    "amount": str(amount),
                },
            )
        )
        await session.commit()

    return TransferResponse(
        saga_id=saga_id,
        status=result["status"],
        message="Chuyển tiền đã được xử lý (saga idempotent theo Idempotency-Key)",
    )


@router.get("/banking/saga/{saga_id}")
async def get_saga(saga_id: str):
    async with AsyncSessionLocal() as session:
        saga = None
        try:
            parsed_uuid = UUID(saga_id)
            res = await session.execute(
                select(SagaInstance).where(
                    (SagaInstance.id == str(parsed_uuid)) | (SagaInstance.id == parsed_uuid)
                )
            )
            saga = res.scalars().first()
        except (ValueError, TypeError):
            pass

        if saga is None:
            res = await session.execute(
                select(SagaInstance).where(SagaInstance.id == saga_id)
            )
            saga = res.scalars().first()

        if saga is None:
            raise HTTPException(status_code=404, detail="Không tìm thấy saga")

        # Step logs (M4 schema)
        step_logs_res = await session.execute(
            select(SagaStepLog).where(SagaStepLog.saga_id == str(saga.id)).order_by(SagaStepLog.step_index.asc())
        )
        step_logs = step_logs_res.scalars().all()

        # Steps (legacy schema)
        steps_res = await session.execute(
            select(SagaStep).where(SagaStep.saga_id == str(saga.id)).order_by(SagaStep.created_at.asc())
        )
        steps = steps_res.scalars().all()

        formatted_steps = []
        if step_logs:
            for s in step_logs:
                formatted_steps.append({
                    "name": s.step_name,
                    "status": s.status,
                    "step_index": s.step_index,
                    "input_data": s.input_data,
                    "output_data": s.output_data,
                    "error_message": s.error_message,
                    "executed_at": s.executed_at.isoformat() if s.executed_at else None,
                    "compensated_at": s.compensated_at.isoformat() if s.compensated_at else None,
                })
        else:
            for s in steps:
                formatted_steps.append({
                    "name": s.step_name,
                    "status": s.status,
                    "action_json": s.action_json,
                    "compensate_json": s.compensate_json,
                    "completed_at": s.completed_at.isoformat() if s.completed_at else None,
                })

    return {
        "saga_id": str(saga.id),
        "saga_name": saga.saga_name or saga.saga_type,
        "saga_type": saga.saga_type or saga.saga_name,
        "status": saga.status,
        "current_step": saga.current_step,
        "context": saga.context_data or saga.context_json or {},
        "error_message": saga.error_message,
        "steps": formatted_steps,
        "step_logs": formatted_steps,
    }


class ConcurrentTransferRequest(BaseModel):
    source_account: str = Field(..., description="Source account code (e.g. 111, 156)")
    dest_account: str = Field(..., description="Destination account code (e.g. 112, 156)")
    amount_cents: int = Field(..., gt=0, description="Transfer amount in integer cents")
    description: str = Field(default="", description="Transfer description")
    mode: str = Field(default="pessimistic", description="Locking mode: pessimistic or optimistic")


@router.post("/banking/transfers/concurrent", status_code=200)
async def concurrent_transfer_endpoint(body: ConcurrentTransferRequest):
    """Executes account transfer with deterministic resource ordering and deadlock prevention."""
    async with AsyncSessionLocal() as session:
        try:
            result = await execute_concurrent_transfer(
                session=session,
                source_account=body.source_account,
                dest_account=body.dest_account,
                amount_cents=body.amount_cents,
                description=body.description,
                mode=body.mode,
            )
            await session.commit()
            return {"status": "SUCCESS", "data": result}
        except ConcurrencyInsufficientBalance as exc:
            await session.rollback()
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except OptimisticLockException as exc:
            await session.rollback()
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            await session.rollback()
            raise HTTPException(status_code=400, detail=str(exc)) from exc


class ExecuteSagaRequest(BaseModel):
    saga_name: str = Field(..., description="Name of the saga to execute")
    saga_id: str | None = Field(default=None, description="Optional deterministic saga ID")
    context: dict = Field(default_factory=dict, description="Initial saga context data")


@router.post("/banking/saga/execute", status_code=200)
async def execute_saga_endpoint(body: ExecuteSagaRequest):
    """Executes a distributed saga workflow with forward execution and automated compensation."""
    async with AsyncSessionLocal() as session:
        orchestrator = ModernSagaOrchestrator(session)
        if body.saga_name in ("InterWarehouseTransferSaga", "PaymentFulfillmentSaga"):
            source = body.context.get("source_account", "111")
            dest = body.context.get("dest_account", "112")
            amount = int(body.context.get("amount_cents", 1000))
            transfer_id = str(body.context.get("transfer_id", body.saga_id or uuid.uuid4()))
            steps = create_inter_warehouse_transfer_saga(source, dest, amount, transfer_id)
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported saga_name: {body.saga_name}. Available: InterWarehouseTransferSaga, PaymentFulfillmentSaga",
            )

        result = await orchestrator.execute_saga(
            saga_name=body.saga_name,
            steps=steps,
            context=SagaContext(body.context),
            saga_id=body.saga_id,
        )
        await session.commit()
        return result.to_dict()


class RecordAuditEntryRequest(BaseModel):
    actor_id: str = Field(..., description="Identifier of actor initiating action")
    action: str = Field(..., description="Action performed, e.g. TRANSFER, GL_POST, HOLD_FUNDS, SAGA_ROLLBACK")
    entity_type: str = Field(..., description="Type of target entity, e.g. ACCOUNT, JOURNAL, SAGA, OUTBOX")
    entity_id: str = Field(..., description="Identifier of target entity")
    state_payload: dict = Field(default_factory=dict, description="State delta or serialized data")


@router.post("/banking/audit/record", status_code=201)
async def record_audit_endpoint(body: RecordAuditEntryRequest):
    """Records an immutable append-only audit trail record with cryptographic hash chaining."""
    async with AsyncSessionLocal() as session:
        entry = await record_audit_trail_entry(
            session=session,
            actor_id=body.actor_id,
            action=body.action,
            entity_type=body.entity_type,
            entity_id=body.entity_id,
            state_payload=body.state_payload,
        )
        await session.commit()
        return {"status": "SUCCESS", "data": entry.to_dict()}


@router.get("/banking/audit/verify")
async def audit_verify(subject: str | None = None):
    """Scans and verifies cryptographic integrity of the audit chain."""
    async with AsyncSessionLocal() as session:
        if subject is not None:
            ok = await verify_chain(session, subject)
            return {"subject": subject, "chain_valid": ok, "valid": ok}
        result = await verify_audit_chain_integrity(session)
        return {
            "status": "SUCCESS",
            "valid": result.is_valid,
            "is_clean": result.is_valid,
            "broken_record_id": result.broken_id,
            "reason": result.reason,
        }


@router.get("/banking/audit/trail")
async def get_audit_trail_endpoint(
    limit: int = 100,
    offset: int = 0,
    entity_type: str | None = None,
    entity_id: str | None = None,
):
    """Lists audit records with sequence and cryptographic hashes."""
    async with AsyncSessionLocal() as session:
        records, total = await get_audit_trail(
            session=session,
            limit=limit,
            offset=offset,
            entity_type=entity_type,
            entity_id=entity_id,
        )
        return {
            "status": "SUCCESS",
            "total": total,
            "limit": limit,
            "offset": offset,
            "items": [r.to_dict() for r in records],
        }


@router.post("/banking/reserve")
async def reserve(body: TransferRequest, idempotency_key: str | None = Header(default=None, alias="Idempotency-Key")):
    if not idempotency_key:
        raise HTTPException(status_code=400, detail="Thiếu Idempotency-Key")
    try:
        amount = Decimal(body.amount)
    except (InvalidOperation, ValueError) as exc:
        raise HTTPException(status_code=422, detail="amount phải là decimal hợp lệ") from exc
    if amount <= 0:
        raise HTTPException(status_code=422, detail="amount phải lớn hơn 0")
    async with AsyncSessionLocal() as session:
        try:
            await reserve_balance(
                session, body.source_location_id, body.source_item_id, amount
            )
            await append_audit_event(
                session,
                subject=f"reserve:{idempotency_key}",
                action="banking.reserve",
                request_id=idempotency_key,
                metadata_json={
                    "location": body.source_location_id,
                    "item": body.source_item_id,
                    "amount": str(amount),
                },
            )
            session.add(
                OutboxEvent(
                    event_type="banking.reserve.created",
                    aggregate_id=idempotency_key,
                    payload_json={
                        "location": body.source_location_id,
                        "item": body.source_item_id,
                        "amount": str(amount),
                    },
                )
            )
            await session.commit()
        except InsufficientBalance as exc:
            await session.rollback()
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except ConcurrencyConflict as exc:
            await session.rollback()
            raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"status": "reserved", "idempotency_key": idempotency_key}


@router.post("/banking/confirm")
async def confirm(body: TransferRequest, idempotency_key: str | None = Header(default=None, alias="Idempotency-Key")):
    if not idempotency_key:
        raise HTTPException(status_code=400, detail="Thiếu Idempotency-Key")
    try:
        amount = Decimal(body.amount)
    except (InvalidOperation, ValueError) as exc:
        raise HTTPException(status_code=422, detail="amount phải là decimal hợp lệ") from exc
    async with AsyncSessionLocal() as session:
        try:
            await commit_reservation(
                session, body.source_location_id, body.source_item_id, amount
            )
            await session.commit()
        except InsufficientBalance as exc:
            await session.rollback()
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except ConcurrencyConflict as exc:
            await session.rollback()
            raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"status": "confirmed", "idempotency-key": idempotency_key}


@router.post("/banking/cancel")
async def cancel(body: TransferRequest, idempotency_key: str | None = Header(default=None, alias="Idempotency-Key")):
    if not idempotency_key:
        raise HTTPException(status_code=400, detail="Thiếu Idempotency-Key")
    try:
        amount = Decimal(body.amount)
    except (InvalidOperation, ValueError) as exc:
        raise HTTPException(status_code=422, detail="amount phải là decimal hợp lệ") from exc
    async with AsyncSessionLocal() as session:
        try:
            await release_reservation(
                session, body.source_location_id, body.source_item_id, amount
            )
            await session.commit()
        except InsufficientBalance as exc:
            await session.rollback()
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except ConcurrencyConflict as exc:
            await session.rollback()
            raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"status": "cancelled", "idempotency-key": idempotency_key}


# ============================================================================
# IDEMPOTENCY & OUTBOX ENDPOINTS (Milestone M3)
# ============================================================================

class IdempotentExecuteRequest(BaseModel):
    path: str = Field(..., description="Target request path")
    payload: dict = Field(default_factory=dict, description="Request payload")


@router.get("/banking/idempotency/{key}")
async def get_idempotency_key(key: str):
    """Retrieves durable idempotency record status and cached response."""
    async with AsyncSessionLocal() as session:
        res = await session.execute(
            select(IdempotencyKeyRecord).where(IdempotencyKeyRecord.key == key)
        )
        record = res.scalars().first()
        if not record:
            raise HTTPException(status_code=404, detail="Idempotency key not found")
        cached = None
        if record.response_body:
            import json
            try:
                cached = (
                    json.loads(record.response_body)
                    if isinstance(record.response_body, str)
                    else record.response_body
                )
            except Exception:
                cached = record.response_body
        return {
            "key": record.key,
            "status": record.status,
            "request_hash": record.request_hash,
            "status_code": record.status_code,
            "response_body": cached,
            "created_at": record.created_at.isoformat() if record.created_at else None,
            "expires_at": record.expires_at.isoformat() if record.expires_at else None,
        }


@router.post("/banking/idempotency/execute")
async def execute_idempotent_endpoint(
    body: IdempotentExecuteRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    """Executes an operation protected by the Strict Financial Idempotency Engine."""
    if not idempotency_key or not idempotency_key.strip():
        raise HTTPException(status_code=400, detail="Idempotency-Key header is mandatory and cannot be empty.")
    async with AsyncSessionLocal() as session:
        async def mock_operation():
            return (200, {"processed": True, "key": idempotency_key, "payload": body.payload})

        try:
            status_code, resp_body, is_replay = await execute_idempotent_operation(
                session=session,
                idempotency_key=idempotency_key,
                request_path=body.path,
                request_payload=body.payload,
                operation_coroutine=mock_operation,
            )
            await session.commit()
            return {"status_code": status_code, "body": resp_body, "is_replay": is_replay}
        except IdempotencyConflictException as exc:
            await session.rollback()
            raise HTTPException(status_code=409, detail=exc.message) from exc
        except IdempotencyInFlightException as exc:
            await session.rollback()
            raise HTTPException(status_code=409, detail=exc.message) from exc


class OutboxEmitRequest(BaseModel):
    topic: str
    event_type: str
    aggregate_id: str
    payload: dict = Field(default_factory=dict)
    trace_id: str | None = None


@router.post("/banking/outbox/emit", status_code=201)
async def emit_outbox_endpoint(body: OutboxEmitRequest):
    """Atomically writes an outbox event in database transaction."""
    async with AsyncSessionLocal() as session:
        try:
            ev = await emit_outbox_event(
                session=session,
                topic=body.topic,
                event_type=body.event_type,
                aggregate_id=body.aggregate_id,
                payload=body.payload,
                trace_id=body.trace_id or "",
            )
            await session.commit()
            return {
                "id": str(ev.id),
                "topic": ev.topic,
                "event_type": ev.event_type,
                "aggregate_id": ev.aggregate_id,
                "status": ev.status,
            }
        except ValueError as exc:
            await session.rollback()
            raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/banking/outbox/drain")
async def drain_outbox_endpoint(limit: int = 100):
    """Triggers the async outbox drain worker to dispatch pending events."""
    async with AsyncSessionLocal() as session:
        drained = await drain_outbox_events(session, limit=limit)
        await session.commit()
        return {
            "drained_count": len(drained),
            "events": [
                {
                    "id": str(e.id),
                    "topic": e.topic,
                    "event_type": e.event_type,
                    "aggregate_id": e.aggregate_id,
                    "status": e.status,
                    "attempts": e.attempts,
                }
                for e in drained
            ],
        }


@router.get("/banking/outbox/events")
async def list_outbox_events(
    topic: str | None = None,
    status: str | None = None,
    limit: int = 50,
):
    """Lists outbox events filtered by topic or status."""
    async with AsyncSessionLocal() as session:
        query = select(OutboxEventRecord).order_by(OutboxEventRecord.created_at.desc()).limit(limit)
        if topic:
            query = query.where(OutboxEventRecord.topic == topic)
        if status:
            query = query.where(OutboxEventRecord.status == status)
        res = await session.execute(query)
        events = res.scalars().all()
        return [
            {
                "id": str(e.id),
                "topic": e.topic,
                "event_type": e.event_type,
                "aggregate_id": e.aggregate_id,
                "status": e.status,
                "attempts": e.attempts,
                "created_at": e.created_at.isoformat() if e.created_at else None,
                "published_at": e.published_at.isoformat() if e.published_at else None,
            }
            for e in events
        ]

