"""RetailOps order routes (MVP).

Transaction-safe order lifecycle:
  POST   /orders/quote        -> draft order (read/draft, no stock commit)
  POST   /orders/confirm      -> confirm + atomic stock decrement (commit)
  POST   /orders/cancel       -> cancel (may need manager approval)
  GET    /orders/{order_id}   -> read order (tenant-scoped)
  GET    /orders/operations/{operation_id}  -> tra cứu trạng thái thao tác (timeout recovery)

ADR-002: Single source of truth = QuanLyKho inventory + order.
ADR-003: Agent proposes; backend decides price/stock/permission/commit.
ADR-004: User confirmation required before commit; manager approval for cancel.
ADR-009: Contract giữ prefix thực tế /orders (không đổi sang /api/retail).
ADR-010: Idempotency dùng engine đơn lẻ app.services.idempotency_service.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import AppError
from app.api.routes.auth_utils import (
    get_accessible_location_ids,
    get_user_capabilities,
    require_any_capability,
)
from app.database import get_db
from app.models.approval import ApprovalDecision
from app.models.iam import User
from app.models.idempotency import IdempotencyKey
from app.models.inventory import (
    Balance,
    InventoryEntry,
    InventoryJournal,
    InventoryRequest,
    Item,
    Location,
)
from app.models.order import Order, OrderLine, OrderStatus
from app.services.audit_service import record_audit_entry
from app.services.idempotency_service import (
    IdempotencyConflictException,
    IdempotencyInFlightException,
    compute_canonical_hash,
    execute_idempotent_operation,
)

router = APIRouter(prefix="/orders", tags=["retail-orders"])

_WRITE_CAP = "retail:order:write"
_READ_CAP = "retail:order:read"
_CANCEL_CAP = "retail:order:cancel"
_APPROVE_CANCEL_CAP = "retail:order:approve_cancel"

_DEFAULT_TTL_MINUTES = 30
_TAX_RATE = Decimal("0.08")  # 8% VAT — backend decides, not LLM


# ---------------------------------------------------------------------------
# Schemas (inline to avoid circular import; keep aligned with app/schemas/order.py)
# ---------------------------------------------------------------------------
class OrderLineIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_id: str
    location_id: str
    quantity: str  # decimal as string to avoid float precision issues


class QuoteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    branch_id: str
    lines: list[OrderLineIn]
    customer_ref: str | None = Field(default=None, max_length=128)
    idempotency_key: str | None = Field(default=None, max_length=128)


class QuoteResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    draft_id: str
    confirmation_token: str
    expires_at: str
    lines: list[dict]
    subtotal: str
    tax: str
    total_amount: str
    currency: str = "VND"
    stock_ok: bool
    insufficient_items: list[dict] = Field(default_factory=list)


class ConfirmRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    draft_id: str
    confirmation_token: str
    idempotency_key: str | None = Field(default=None, max_length=128)


class CancelRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    order_id: str
    reason: str | None = Field(default=None, max_length=1024)
    idempotency_key: str | None = Field(default=None, max_length=128)


class CancelDecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: str = Field(pattern="^(approved|rejected)$")
    note: str | None = Field(default=None, max_length=500)
    idempotency_key: str = Field(min_length=1, max_length=128)


class OperationStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operation_id: str
    status: str  # committed | rejected | unknown
    raw_status: str
    request_path: str | None = None
    scope: str | None = None
    result: dict | None = None
    created_at: str | None = None
    updated_at: str | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _uuid(value: str, field_name: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except (ValueError, AttributeError) as exc:
        raise AppError(400, f"INVALID_{field_name.upper()}", f"{field_name} không hợp lệ") from exc


def _decimal(value: str, field_name: str) -> Decimal:
    try:
        return Decimal(value)
    except (InvalidOperation, ValueError) as exc:
        raise AppError(400, f"INVALID_{field_name.upper()}", f"{field_name} không phải số hợp lệ") from exc


async def _get_accessible_locations(db: AsyncSession, user: User) -> set[uuid.UUID] | None:
    allowed = await get_accessible_location_ids(db, user)
    if allowed is None:
        return None
    return {uuid.UUID(str(lid)) for lid in allowed}


def _status_label(raw: str) -> str:
    return {"COMPLETED": "committed", "FAILED": "rejected"}.get(raw, "unknown")


# ---------------------------------------------------------------------------
# POST /orders/quote  — draft order (no stock commit)
# ---------------------------------------------------------------------------
@router.post("/quote")
async def quote_order(
    body: QuoteRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_any_capability(_WRITE_CAP)),
):
    """Tạo đơn hàng nháp (draft). Backend tính giá, kiểm tra tồn kho, chưa trừ tồn kho.

    Idempotency: cùng key + cùng payload -> trả lại quote cũ; khác payload -> 409.
    """
    payload = {
        "actor_id": str(current_user.id),
        "branch_id": body.branch_id,
        "lines": [
            {"item_id": line.item_id, "location_id": line.location_id, "quantity": line.quantity}
            for line in body.lines
        ],
        "customer_ref": body.customer_ref,
    }
    key = body.idempotency_key or f"quote-{uuid.uuid4().hex}"

    async def operation() -> tuple[int, dict]:
        accessible = await _get_accessible_locations(db, current_user)
        lines_out: list[dict] = []
        insufficient_items: list[dict] = []
        subtotal = Decimal("0")
        tax = Decimal("0")
        stock_ok = True
        for line in body.lines:
            item_id = _uuid(line.item_id, "item_id")
            location_id = _uuid(line.location_id, "location_id")
            quantity = _decimal(line.quantity, "quantity")

            if accessible is not None and location_id not in accessible:
                raise AppError(403, "FORBIDDEN", f"Không có quyền truy cập kho {location_id}")

            item = (await db.execute(select(Item).where(Item.id == item_id))).scalars().first()
            if not item or not item.active:
                raise AppError(404, "ITEM_NOT_FOUND", f"Sản phẩm {item_id} không tồn tại hoặc đã ngừng kinh doanh")

            location = (await db.execute(select(Location).where(Location.id == location_id))).scalars().first()
            if not location or not location.active:
                raise AppError(404, "LOCATION_NOT_FOUND", f"Kho {location_id} không tồn tại hoặc đã ngừng hoạt động")
            if location.branch_id != _uuid(body.branch_id, "branch_id"):
                raise AppError(400, "BRANCH_LOCATION_MISMATCH", "Kho không thuộc chi nhánh của đơn hàng")

            balance = (
                await db.execute(select(Balance).where(Balance.item_id == item_id, Balance.location_id == location_id))
            ).scalars().first()
            available = balance.available_quantity if balance else Decimal("0")

            if available < quantity:
                stock_ok = False
                insufficient_items.append({
                    "item_id": str(item_id),
                    "item_name": item.name,
                    "sku": item.sku,
                    "location_id": str(location_id),
                    "requested": str(quantity),
                    "available": str(available),
                })

            unit_price = item.selling_price or Decimal("0")
            line_total = quantity * unit_price
            subtotal += line_total
            lines_out.append({
                "item_id": str(item_id),
                "item_name": item.name,
                "sku": item.sku,
                "location_id": str(location_id),
                "quantity": str(quantity),
                "unit_price": str(unit_price),
                "line_total": str(line_total),
            })

            tax += line_total * _TAX_RATE

        branch_id = _uuid(body.branch_id, "branch_id")
        actor_id = current_user.id

        total_amount = subtotal + tax
        now = datetime.now(UTC)
        expires_at = now + timedelta(minutes=_DEFAULT_TTL_MINUTES)

        draft = Order(
            id=uuid.uuid4(),
            branch_id=branch_id,
            actor_id=actor_id,
            customer_ref=body.customer_ref,
            status=OrderStatus.DRAFT.value,
            subtotal=subtotal,
            tax=tax,
            total_amount=total_amount,
            idempotency_key=key,
            idempotency_payload_hash=compute_canonical_hash(payload),
            confirmation_token=uuid.uuid4().hex,
            expires_at=expires_at,
        )
        db.add(draft)

        for line_data in lines_out:
            db.add(OrderLine(
                id=uuid.uuid4(),
                order_id=draft.id,
                item_id=uuid.UUID(line_data["item_id"]),
                location_id=uuid.UUID(line_data["location_id"]),
                quantity=Decimal(line_data["quantity"]),
                unit_price=Decimal(line_data["unit_price"]),
                line_total=Decimal(line_data["line_total"]),
            ))

        await record_audit_entry(
            session=db,
            actor_id=str(actor_id),
            action="retail.order.quote",
            entity_type="retail_order",
            entity_id=str(draft.id),
            state_payload={
                "branch_id": str(branch_id),
                "total_amount": str(total_amount),
                "stock_ok": stock_ok,
                "idempotency_key": key,
            },
        )

        return 200, {
            "draft_id": str(draft.id),
            "confirmation_token": draft.confirmation_token,
            "expires_at": expires_at.isoformat(),
            "lines": lines_out,
            "subtotal": str(subtotal),
            "tax": str(tax),
            "total_amount": str(total_amount),
            "currency": "VND",
            "stock_ok": stock_ok,
            "insufficient_items": insufficient_items,
        }

    try:
        _status_code, response_body, _is_replay = await execute_idempotent_operation(
            db, key, "/orders/quote", payload, operation
        )
    except IdempotencyConflictException as exc:
        raise AppError(409, "IDEMPOTENCY_CONFLICT", "Khóa idempotency đã dùng cho payload khác") from exc
    except IdempotencyInFlightException as exc:
        raise AppError(409, "IDEMPOTENCY_CONFLICT", "Yêu cầu cùng khóa đang được xử lý, vui lòng thử lại") from exc
    return response_body


# ---------------------------------------------------------------------------
# POST /orders/confirm  — commit order (atomic stock decrement)
# ---------------------------------------------------------------------------
@router.post("/confirm")
async def confirm_order(
    body: ConfirmRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_any_capability(_WRITE_CAP)),
):
    """Xác nhận đơn nháp -> kiểm tra lại tồn kho/gía trị/quyền -> trừ tồn kho atomic -> commit.

    Xác nhận phải xảy ra trước khi tạo đơn commit. Backend re-validate mọi thứ.
    Commit/rollback được get_db thực hiện atomic cùng bản ghi idempotency.
    """
    draft_id = _uuid(body.draft_id, "draft_id")
    actor_id = current_user.id

    payload = {
        "draft_id": body.draft_id, "confirmation_token": body.confirmation_token,
        "actor_id": str(current_user.id),
    }
    key = body.idempotency_key or f"confirm-{uuid.uuid4().hex}"

    async def operation() -> tuple[int, dict]:
        result = await db.execute(
            select(Order).where(Order.id == draft_id).with_for_update(nowait=True)
        )
        draft = result.scalars().first()
        if not draft:
            raise AppError(404, "ORDER_NOT_FOUND", "Đơn nháp không tồn tại")

        if draft.actor_id != actor_id:
            caps = await get_user_capabilities(db, current_user.id)
            if "retail:order:manage_all" not in caps:
                raise AppError(403, "FORBIDDEN", "Không phải chủ sở hữu đơn hàng này")

        if draft.status != OrderStatus.DRAFT.value:
            raise AppError(409, "INVALID_TRANSITION", f"Đơn đã ở trạng thái {draft.status}, không thể xác nhận")

        if draft.expires_at and draft.expires_at < datetime.now(UTC):
            raise AppError(410, "DRAFT_EXPIRED", "Đơn nháp đã hết hạn, vui lòng báo giá lại")

        if draft.confirmation_token != body.confirmation_token:
            raise AppError(403, "INVALID_TOKEN", "Mã xác nhận không khớp")

        lines = (
            await db.execute(select(OrderLine).where(OrderLine.order_id == draft_id))
        ).scalars().all()
        if not lines:
            raise AppError(400, "EMPTY_ORDER", "Đơn không có dòng hàng")
        accessible = await _get_accessible_locations(db, current_user)
        if accessible is not None and any(line.location_id not in accessible for line in lines):
            raise AppError(403, "FORBIDDEN", "Không có quyền truy cập kho của đơn hàng")

        insufficient: list[dict] = []
        for line in lines:
            stmt = (
                update(Balance)
                .where(
                    Balance.item_id == line.item_id,
                    Balance.location_id == line.location_id,
                    (Balance.quantity - Balance.reserved_quantity) >= line.quantity,
                )
                .values(quantity=Balance.quantity - line.quantity)
                .execution_options(synchronize_session=False)
            )
            res = await db.execute(stmt)
            if res.rowcount == 0:
                balance = (
                    await db.execute(select(Balance).where(
                        Balance.item_id == line.item_id,
                        Balance.location_id == line.location_id,
                    ))
                ).scalars().first()
                item = (await db.execute(select(Item).where(Item.id == line.item_id))).scalars().first()
                avail = (balance.quantity or Decimal("0")) - (balance.reserved_quantity or Decimal("0"))
                insufficient.append({
                    "item_id": str(line.item_id),
                    "item_name": item.name if item else "?",
                    "sku": item.sku if item else "?",
                    "location_id": str(line.location_id),
                    "requested": str(line.quantity),
                    "available": str(avail),
                })

        if insufficient:
            raise AppError(409, "INSUFFICIENT_STOCK", "Không đủ tồn kho cho một số mặt hàng", details=insufficient)

        draft.status = OrderStatus.CONFIRMED.value
        draft.confirmation_at = datetime.now(UTC)
        draft.confirmed_by = actor_id

        inventory_request = InventoryRequest(
            id=draft.id,
            kind="issue",
            status="confirmed",
            maker_id=actor_id,
            created_by=actor_id,
        )
        db.add(inventory_request)
        await db.flush()
        journal = InventoryJournal(
            id=uuid.uuid4(),
            request_id=draft.id,
            posted_at=datetime.now(UTC),
            correlation_id=str(draft.id),
        )
        db.add(journal)
        await db.flush()
        entries: list[InventoryEntry] = []
        for line in lines:
            entries.append(
                InventoryEntry(
                    id=uuid.uuid4(),
                    journal_id=journal.id,
                    account_code=f"INV.{line.item_id}",
                    debit=Decimal("0"),
                    credit=line.line_total,
                )
            )
            entries.append(
                InventoryEntry(
                    id=uuid.uuid4(),
                    journal_id=journal.id,
                    account_code=f"COGS.{line.item_id}",
                    debit=line.line_total,
                    credit=Decimal("0"),
                )
            )
        db.add_all(entries)

        await record_audit_entry(
            session=db,
            actor_id=str(actor_id),
            action="retail.order.confirm",
            entity_type="retail_order",
            entity_id=str(draft_id),
            state_payload={
                "branch_id": str(draft.branch_id),
                "total_amount": str(draft.total_amount),
                "line_count": len(lines),
            },
        )

        return 200, {
            "order_id": str(draft.id),
            "status": draft.status,
            "total_amount": str(draft.total_amount),
            "currency": draft.currency,
            "confirmed_at": draft.confirmation_at.isoformat() if draft.confirmation_at else None,
            "confirmed_by": str(draft.confirmed_by) if draft.confirmed_by else None,
        }

    try:
        _status_code, response_body, _is_replay = await execute_idempotent_operation(
            db, key, "/orders/confirm", payload, operation
        )
    except IdempotencyConflictException as exc:
        raise AppError(409, "IDEMPOTENCY_CONFLICT", "Khóa idempotency đã dùng cho payload khác") from exc
    except IdempotencyInFlightException as exc:
        raise AppError(409, "IDEMPOTENCY_CONFLICT", "Yêu cầu cùng khóa đang được xử lý, vui lòng thử lại") from exc
    return response_body


# ---------------------------------------------------------------------------
# POST /orders/cancel  — cancel order (may need manager approval)
# ---------------------------------------------------------------------------
@router.post("/cancel")
async def cancel_order(
    body: CancelRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_any_capability(_CANCEL_CAP)),
):
    """Yêu cầu hủy đơn hàng.

    Nếu policy yêu cầu phê duyệt quản lý -> trả APPROVAL_REQUIRED.
    Nếu không -> hủy ngay, hoàn tồn kho (idempotent).
    """
    order_id = _uuid(body.order_id, "order_id")
    actor_id = current_user.id

    payload = {"order_id": body.order_id, "reason": body.reason, "actor_id": str(current_user.id)}
    key = body.idempotency_key or f"cancel-{uuid.uuid4().hex}"

    async def operation() -> tuple[int, dict]:
        result = await db.execute(
            select(Order).where(Order.id == order_id).with_for_update(nowait=True)
        )
        order = result.scalars().first()
        if not order:
            raise AppError(404, "ORDER_NOT_FOUND", "Đơn hàng không tồn tại")

        if order.status != OrderStatus.CONFIRMED.value:
            raise AppError(409, "INVALID_TRANSITION", f"Chỉ hủy được đơn đã xác nhận (hiện tại: {order.status})")

        if order.actor_id != actor_id:
            caps = await get_user_capabilities(db, current_user.id)
            if "retail:order:manage_all" not in caps:
                raise AppError(403, "FORBIDDEN", "Không phải chủ sở hữu đơn hàng này")

        order_lines = (await db.execute(select(OrderLine).where(OrderLine.order_id == order_id))).scalars().all()
        accessible = await _get_accessible_locations(db, current_user)
        if accessible is not None and any(line.location_id not in accessible for line in order_lines):
            raise AppError(403, "FORBIDDEN", "Không có quyền truy cập kho của đơn hàng")

        needs_approval = order.total_amount >= Decimal("5000000")

        if needs_approval:
            if order.approval_decision_id is not None:
                raise AppError(409, "ALREADY_DECIDED", "Yêu cầu hủy đã có quyết định")
            order.approval_required = True
            order.cancel_reason = body.reason
            await record_audit_entry(
                session=db, actor_id=str(actor_id), action="retail.order.cancel_requested",
                entity_type="retail_order", entity_id=str(order_id),
                state_payload={"reason": body.reason, "requires_manager": True},
            )
            return 202, {"order_id": str(order_id), "status": "pending_approval", "approval_required": True}

        order.status = OrderStatus.CANCELLED.value
        order.cancel_reason = body.reason

        lines = (
            await db.execute(select(OrderLine).where(OrderLine.order_id == order_id))
        ).scalars().all()
        for line in lines:
            stmt = (
                update(Balance)
                .where(
                    Balance.item_id == line.item_id,
                    Balance.location_id == line.location_id,
                )
                .values(quantity=Balance.quantity + line.quantity)
                .execution_options(synchronize_session=False)
            )
            await db.execute(stmt)

        await record_audit_entry(
            session=db,
            actor_id=str(actor_id),
            action="retail.order.cancel",
            entity_type="retail_order",
            entity_id=str(order_id),
            state_payload={"reason": body.reason, "needs_approval": False},
        )

        return 200, {
            "order_id": str(order_id),
            "status": order.status,
            "message": "Đơn hàng đã hủy và tồn kho đã được hoàn trả",
        }

    try:
        _status_code, response_body, _is_replay = await execute_idempotent_operation(
            db, key, "/orders/cancel", payload, operation
        )
    except IdempotencyConflictException as exc:
        raise AppError(409, "IDEMPOTENCY_CONFLICT", "Khóa idempotency đã dùng cho payload khác") from exc
    except IdempotencyInFlightException as exc:
        raise AppError(409, "IDEMPOTENCY_CONFLICT", "Yêu cầu cùng khóa đang được xử lý, vui lòng thử lại") from exc
    return response_body


# ---------------------------------------------------------------------------
# POST /orders/{order_id}/cancel-decision  — manager checker
# ---------------------------------------------------------------------------
@router.post("/{order_id}/cancel-decision")
async def decide_cancel_order(
    order_id: str,
    body: CancelDecisionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_any_capability(_APPROVE_CANCEL_CAP)),
):
    """Manager checker decides a pending high-value cancellation."""
    oid = _uuid(order_id, "order_id")
    payload = {
        "order_id": order_id, "decision": body.decision, "note": body.note,
        "actor_id": str(current_user.id),
    }

    async def operation() -> tuple[int, dict]:
        order = (
            await db.execute(select(Order).where(Order.id == oid).with_for_update(nowait=True))
        ).scalars().first()
        if order is None:
            raise AppError(404, "ORDER_NOT_FOUND", "Đơn hàng không tồn tại")
        if order.actor_id == current_user.id:
            raise AppError(403, "MAKER_CHECKER", "Người tạo đơn không thể tự duyệt hủy")
        if order.status != OrderStatus.CONFIRMED.value or not order.approval_required or order.approval_decision_id:
            raise AppError(409, "INVALID_TRANSITION", "Không có yêu cầu hủy đang chờ duyệt")
        lines = (await db.execute(select(OrderLine).where(OrderLine.order_id == oid))).scalars().all()
        accessible = await _get_accessible_locations(db, current_user)
        if accessible is not None and any(line.location_id not in accessible for line in lines):
            raise AppError(403, "FORBIDDEN", "Không có quyền truy cập kho của đơn hàng")
        decision = ApprovalDecision(
            id=uuid.uuid4(), subject_type="retail_order_cancel", subject_id=oid,
            actor_id=current_user.id, decision=body.decision, reason=body.note,
            request_payload_hash=compute_canonical_hash(payload),
        )
        db.add(decision)
        await db.flush()
        order.approval_decision_id = decision.id
        order.approval_required = False
        if body.decision == "approved":
            for line in lines:
                await db.execute(
                    update(Balance)
                    .where(Balance.item_id == line.item_id, Balance.location_id == line.location_id)
                    .values(quantity=Balance.quantity + line.quantity)
                    .execution_options(synchronize_session=False)
                )
            order.status = OrderStatus.CANCELLED.value
        await record_audit_entry(
            session=db, actor_id=str(current_user.id), action="retail.order.cancel_decision",
            entity_type="retail_order", entity_id=str(oid),
            state_payload={"decision": body.decision, "order_status": order.status},
        )
        return 200, {
            "order_id": str(oid), "decision_id": str(decision.id),
            "decision": body.decision, "status": order.status,
        }

    try:
        _status_code, response_body, _is_replay = await execute_idempotent_operation(
            db, body.idempotency_key, "/orders/cancel-decision", payload, operation
        )
    except IdempotencyConflictException as exc:
        raise AppError(409, "IDEMPOTENCY_CONFLICT", "Khóa idempotency đã dùng cho payload khác") from exc
    except IdempotencyInFlightException as exc:
        raise AppError(409, "IDEMPOTENCY_CONFLICT", "Yêu cầu cùng khóa đang được xử lý, vui lòng thử lại") from exc
    return response_body


# ---------------------------------------------------------------------------
# GET /orders/{order_id}  — read order (tenant-scoped)
# ---------------------------------------------------------------------------
@router.get("/{order_id}")
async def get_order(
    order_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_any_capability(_READ_CAP)),
):
    """Tra cứu đơn hàng (chỉ người có quyền trong scope branch)."""
    oid = _uuid(order_id, "order_id")

    result = await db.execute(select(Order).where(Order.id == oid))
    order = result.scalars().first()
    if not order:
        raise AppError(404, "ORDER_NOT_FOUND", "Đơn hàng không tồn tại")

    lines = (
        await db.execute(select(OrderLine).where(OrderLine.order_id == oid))
    ).scalars().all()
    accessible = await _get_accessible_locations(db, current_user)
    if accessible is not None and any(line.location_id not in accessible for line in lines):
        raise AppError(403, "FORBIDDEN", "Không có quyền xem đơn hàng này")
    if order.actor_id != current_user.id:
        caps = await get_user_capabilities(db, current_user.id)
        if "retail:order:manage_all" not in caps:
            raise AppError(403, "FORBIDDEN", "Không có quyền xem đơn hàng này")

    return {
        "order_id": str(order.id),
        "branch_id": str(order.branch_id),
        "actor_id": str(order.actor_id),
        "customer_ref": order.customer_ref,
        "status": order.status,
        "subtotal": str(order.subtotal),
        "tax": str(order.tax),
        "total_amount": str(order.total_amount),
        "currency": order.currency,
        "confirmation_at": order.confirmation_at.isoformat() if order.confirmation_at else None,
        "confirmed_by": str(order.confirmed_by) if order.confirmed_by else None,
        "expires_at": order.expires_at.isoformat() if order.expires_at else None,
        "cancel_reason": order.cancel_reason,
        "approval_required": order.approval_required,
        "approval_decision_id": str(order.approval_decision_id) if order.approval_decision_id else None,
        "created_at": order.created_at.isoformat() if order.created_at else None,
        "updated_at": order.updated_at.isoformat() if order.updated_at else None,
        "lines": [
            {
                "item_id": str(line.item_id),
                "location_id": str(line.location_id),
                "quantity": str(line.quantity),
                "unit_price": str(line.unit_price),
                "line_total": str(line.line_total),
            }
            for line in lines
        ],
    }


# ---------------------------------------------------------------------------
# GET /orders/operations/{operation_id}  — tra cứu trạng thái thao tác (timeout recovery)
# ---------------------------------------------------------------------------
@router.get("/operations/{operation_id}")
async def get_operation_status(
    operation_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_any_capability(_READ_CAP)),
):
    """Tra cứu kết quả một thao tác ghi qua idempotency key (operation ID).

    Dùng khi client bị timeout sau commit và cần đối soát: committed / rejected / unknown.
    """
    result = await db.execute(select(IdempotencyKey).where(IdempotencyKey.key == operation_id))
    record = result.scalars().first()
    if not record:
        raise AppError(404, "OPERATION_NOT_FOUND", "Không tìm thấy thao tác với mã này")

    body: dict | None = None
    if record.response_body:
        try:
            body = json.loads(record.response_body) if isinstance(record.response_body, str) else record.response_body  # type: ignore[arg-type]
        except Exception:  # noqa: BLE001
            body = {"raw": record.response_body}

    # The idempotency table is shared across API domains. Never reveal a cached
    # response merely because a caller knows its key.
    if record.request_path not in {"/orders/quote", "/orders/confirm", "/orders/cancel"}:
        raise AppError(404, "OPERATION_NOT_FOUND", "Không tìm thấy thao tác với mã này")
    order_id = (body or {}).get("order_id") or (body or {}).get("draft_id")
    if not order_id:
        raise AppError(404, "OPERATION_NOT_FOUND", "Không tìm thấy thao tác với mã này")
    order = (await db.execute(select(Order).where(Order.id == _uuid(order_id, "order_id")))).scalars().first()
    if order is None:
        raise AppError(404, "OPERATION_NOT_FOUND", "Không tìm thấy thao tác với mã này")
    if order.actor_id != current_user.id:
        caps = await get_user_capabilities(db, current_user.id)
        if "retail:order:manage_all" not in caps:
            raise AppError(404, "OPERATION_NOT_FOUND", "Không tìm thấy thao tác với mã này")
    lines = (await db.execute(select(OrderLine).where(OrderLine.order_id == order.id))).scalars().all()
    accessible = await _get_accessible_locations(db, current_user)
    if accessible is not None and any(line.location_id not in accessible for line in lines):
        raise AppError(404, "OPERATION_NOT_FOUND", "Không tìm thấy thao tác với mã này")

    return OperationStatus(
        operation_id=operation_id,
        status=_status_label(record.status),
        raw_status=record.status,
        request_path=record.request_path,
        scope=record.scope,
        result=body,
        created_at=record.created_at.isoformat() if record.created_at else None,
        updated_at=record.updated_at.isoformat() if record.updated_at else None,
    ).model_dump()
