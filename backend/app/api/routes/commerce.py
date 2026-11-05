"""Persisted sales, quotations, purchase orders and accounts receivable/payable."""

import uuid
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import AppError
from app.api.routes.auth_utils import (
    require_any_capability,
)
from app.api.routes.inventory import _require_location_scope
from app.database import get_db
from app.models.activity import AuditEvent, OutboxEvent
from app.models.commerce import (
    CommerceDocument,
    CommerceDocumentLine,
    CommercePayment,
    Customer,
)
from app.models.expense import Supplier
from app.models.inventory import (
    Balance,
    InventoryEntry,
    InventoryJournal,
    InventoryRequest,
    InventoryRequestLine,
    Item,
    LotBalance,
)
from app.services import idempotency
from app.services.general_ledger import post_subledger_journal

router = APIRouter(prefix="/commerce")
_READ_CAPS = ("inventory:view_balances", "inventory:create_request", "admin:user_management")
_WRITE_CAPS = ("inventory:create_request", "admin:user_management")
_CENT = Decimal("0.01")
_ZERO = Decimal("0")


def _today() -> date:
    return datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).date()


class DocumentLineInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_id: uuid.UUID
    quantity: Decimal = Field(gt=0, max_digits=20, decimal_places=3)
    unit_price: Decimal = Field(ge=0, max_digits=16, decimal_places=2)
    lot_no: str | None = Field(default=None, max_length=64)
    expiry_date: date | None = None


class DocumentInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_type: Literal["sale", "quote", "purchase"]
    location_id: uuid.UUID | None = None
    customer_id: uuid.UUID | None = None
    supplier_id: uuid.UUID | None = None
    document_date: date = Field(default_factory=_today)
    due_date: date | None = None
    discount: Decimal = Field(default=_ZERO, ge=0, max_digits=16, decimal_places=2)
    vat_percent: Decimal = Field(default=_ZERO, ge=0, le=100, max_digits=5, decimal_places=2)
    shipping: Decimal = Field(default=_ZERO, ge=0, max_digits=16, decimal_places=2)
    note: str = Field(default="", max_length=2048)
    lines: list[DocumentLineInput] = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def check_party(self):
        if self.document_type == "purchase":
            if self.supplier_id is None or self.customer_id is not None:
                raise ValueError("Phiếu mua cần nhà cung cấp và không nhận khách hàng.")
        elif self.customer_id is None or self.supplier_id is not None:
            raise ValueError("Đơn bán/báo giá cần khách hàng và không nhận nhà cung cấp.")
        if self.document_type != "quote" and self.location_id is None:
            raise ValueError("Đơn bán và phiếu mua cần chọn kho.")
        if self.due_date and self.due_date < self.document_date:
            raise ValueError("Hạn thanh toán không được trước ngày chứng từ.")
        return self


class PaymentInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    amount: Decimal = Field(gt=0, max_digits=16, decimal_places=2)
    payment_date: date = Field(default_factory=_today)
    method: Literal["cash", "bank_transfer", "card", "other"] = "cash"
    reference: str = Field(default="", max_length=128)
    note: str = Field(default="", max_length=1024)


class SupplierInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=256)
    contact_person: str | None = Field(default=None, max_length=256)
    phone: str | None = Field(default=None, max_length=32)
    email: str | None = Field(default=None, max_length=256)
    address: str | None = Field(default=None, max_length=512)


class CustomerInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=256)
    phone: str | None = Field(default=None, max_length=32)
    email: str | None = Field(default=None, max_length=256)
    address: str | None = Field(default=None, max_length=512)


class ConvertQuoteInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    location_id: uuid.UUID


def _request_key(request: Request) -> str:
    key = (request.headers.get("Idempotency-Key") or "").strip()
    if not key or len(key) > 128:
        raise AppError(422, "IDEMPOTENCY_KEY_REQUIRED", "Cần Idempotency-Key hợp lệ cho thao tác ghi.")
    return key


async def _claim_or_replay(
    db: AsyncSession, key: str, payload: dict, scope: str
) -> dict | None:
    """Claim a write key in the business transaction or replay its result.

    Claiming before any commerce mutation serializes concurrent retries at the
    database's unique key. The stored response commits or rolls back with the
    document/payment and its inventory request.
    """
    body_hash = idempotency.payload_hash(payload)

    async def replay_existing():
        record = await idempotency.find_key(db, key)
        if record is None:
            return None
        if record.request_hash != body_hash:
            raise AppError(
                409,
                "IDEMPOTENCY_KEY_REUSED",
                "Idempotency-Key đã dùng cho payload khác.",
            )
        if record.status_code is None or record.response_body is None:
            raise AppError(
                409,
                "IDEMPOTENCY_IN_PROGRESS",
                "Yêu cầu cùng khóa đang được xử lý.",
            )
        return record.response_body

    existing = await replay_existing()
    if existing is not None:
        return existing
    if await idempotency.claim_key(db, key, body_hash, scope):
        return None
    existing = await replay_existing()
    if existing is not None:
        return existing
    raise AppError(
        409,
        "IDEMPOTENCY_IN_PROGRESS",
        "Yêu cầu cùng khóa đang được xử lý.",
    )


async def _store_response(
    db: AsyncSession, key: str, payload: dict, response: dict, status: int = 201
) -> None:
    await idempotency.store_response(
        db, key, idempotency.payload_hash(payload), status, response
    )


def _money(value: Decimal) -> Decimal:
    return value.quantize(_CENT, rounding=ROUND_HALF_UP)


async def _customer(db: AsyncSession, customer_id: uuid.UUID, branch_id):
    query = select(Customer).where(Customer.id == customer_id, Customer.active.is_(True))
    if branch_id is not None:
        query = query.where(Customer.branch_id == branch_id)
    row = (await db.execute(query)).scalar_one_or_none()
    if row is None:
        raise AppError(404, "CUSTOMER_NOT_FOUND", "Không tìm thấy khách hàng.")
    return row


async def _supplier(db: AsyncSession, supplier_id: uuid.UUID, branch_id):
    query = select(Supplier).where(Supplier.id == supplier_id, Supplier.is_active.is_(True))
    if branch_id is not None:
        query = query.where(Supplier.branch_id == branch_id)
    row = (await db.execute(query)).scalar_one_or_none()
    if row is None:
        raise AppError(404, "SUPPLIER_NOT_FOUND", "Không tìm thấy nhà cung cấp.")
    return row


def _document_out(document, lines=(), payments=()):
    return {
        "id": str(document.id),
        "code": document.code,
        "document_type": document.document_type,
        "status": document.status,
        "customer_id": str(document.customer_id) if document.customer_id else None,
        "supplier_id": str(document.supplier_id) if document.supplier_id else None,
        "inventory_request_id": str(document.inventory_request_id) if document.inventory_request_id else None,
        "document_date": document.document_date.isoformat(),
        "due_date": document.due_date.isoformat() if document.due_date else None,
        "subtotal": str(document.subtotal),
        "discount": str(document.discount),
        "vat": str(document.vat),
        "shipping": str(document.shipping),
        "total": str(document.total),
        "paid": str(document.paid),
        "outstanding": str(document.total - document.paid),
        "note": document.note,
        "lines": [
            {
                "item_id": str(line.item_id),
                "sku": line.item_sku,
                "name": line.item_name,
                "unit": line.unit,
                "quantity": str(line.quantity),
                "unit_price": str(line.unit_price),
                "unit_cost": str(line.unit_cost),
                "line_total": str(line.line_total),
                "lot_no": line.lot_no,
                "expiry_date": line.expiry_date.isoformat() if line.expiry_date else None,
            }
            for line in lines
        ],
        "payments": [
            {
                "id": str(payment.id),
                "payment_type": payment.payment_type,
                "amount": str(payment.amount),
                "payment_date": payment.payment_date.isoformat(),
                "method": payment.method,
                "reference": payment.reference,
                "note": payment.note,
            }
            for payment in payments
        ],
    }


async def _audit_and_outbox(db, user, action: str, document, body: dict) -> None:
    event_id = uuid.uuid4()
    db.add(
        AuditEvent(
            id=uuid.uuid4(),
            actor_id=user.id,
            action=action,
            subject="commerce_document",
            request_id=str(event_id),
            metadata_json={"document_id": str(document.id), "code": document.code},
        )
    )
    db.add(
        OutboxEvent(
            id=event_id,
            event_type=action,
            aggregate_id=str(document.id),
            payload_json=body,
        )
    )


async def _reserve_sale_stock(db, location_id, normalized) -> None:
    quantities: dict[uuid.UUID, Decimal] = {}
    for line, item, _ in normalized:
        quantities[item.id] = quantities.get(item.id, _ZERO) + line.quantity
    balances = (
        await db.execute(
            select(Balance)
            .where(Balance.location_id == location_id, Balance.item_id.in_(quantities))
            .order_by(Balance.item_id)
            .with_for_update()
        )
    ).scalars().all()
    balance_by_item = {balance.item_id: balance for balance in balances}
    today = _today()
    for item_id, required in quantities.items():
        balance = balance_by_item.get(item_id)
        available = (
            Decimal(str(balance.quantity)) - Decimal(str(balance.reserved_quantity or _ZERO))
            if balance is not None
            else _ZERO
        )
        if available < required:
            raise AppError(409, "INSUFFICIENT_STOCK", "Không đủ tồn kho khả dụng để lập đơn bán.")
        lots = (
            await db.execute(
                select(LotBalance).where(
                    LotBalance.location_id == location_id,
                    LotBalance.item_id == item_id,
                    LotBalance.quantity > _ZERO,
                )
            )
        ).scalars().all()
        if lots:
            unexpired = sum(
                (
                    Decimal(str(lot.quantity))
                    for lot in lots
                    if lot.expiry_date is None or lot.expiry_date >= today
                ),
                _ZERO,
            )
            if unexpired < required:
                raise AppError(409, "EXPIRED_LOT_CANNOT_BE_USED", "Tồn khả dụng chỉ còn ở lô đã hết hạn.")
    for item_id, required in quantities.items():
        balance_by_item[item_id].reserved_quantity = (
            Decimal(str(balance_by_item[item_id].reserved_quantity or _ZERO)) + required
        )


@router.get("/parties")
async def list_parties(
    user=Depends(require_any_capability(*_READ_CAPS)),
    db: AsyncSession = Depends(get_db),
):
    customers_query = select(Customer).where(Customer.active.is_(True))
    suppliers_query = select(Supplier).where(Supplier.is_active.is_(True))
    branch_id = getattr(user, "branch_id", None)
    if branch_id is not None:
        customers_query = customers_query.where(Customer.branch_id == branch_id)
        suppliers_query = suppliers_query.where(Supplier.branch_id == branch_id)
    customers = (await db.execute(customers_query.order_by(Customer.name))).scalars().all()
    suppliers = (await db.execute(suppliers_query.order_by(Supplier.name))).scalars().all()
    return {
        "customers": [{"id": str(p.id), "code": p.code, "name": p.name, "phone": p.phone} for p in customers],
        "suppliers": [{"id": str(p.id), "code": p.code, "name": p.name, "phone": p.phone} for p in suppliers],
    }


@router.post("/customers", status_code=201)
async def create_customer(
    payload: CustomerInput,
    request: Request,
    user=Depends(require_any_capability(*_WRITE_CAPS)),
    db: AsyncSession = Depends(get_db),
):
    clean = payload.model_dump()
    clean["code"] = clean["code"].strip()
    clean["name"] = clean["name"].strip()
    for field in ("phone", "email", "address"):
        clean[field] = clean[field].strip() or None if clean[field] else None
    if not clean["code"] or not clean["name"]:
        raise AppError(422, "INVALID_CUSTOMER", "Mã và tên khách hàng là bắt buộc.")
    key = _request_key(request)
    replay = await _claim_or_replay(db, key, clean, "commerce.customer.create")
    if replay is not None:
        return replay
    branch_id = getattr(user, "branch_id", None)
    existing = await db.execute(
        select(Customer.id).where(
            Customer.code == clean["code"], Customer.branch_id == branch_id
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise AppError(409, "CUSTOMER_CODE_EXISTS", "Mã khách hàng đã tồn tại.")
    customer = Customer(id=uuid.uuid4(), **clean, branch_id=branch_id)
    db.add(customer)
    await db.flush()
    body = {"id": str(customer.id), **clean, "active": True}
    event_id = uuid.uuid4()
    db.add(
        AuditEvent(
            id=uuid.uuid4(),
            actor_id=user.id,
            action="commerce.customer.created",
            subject="customer",
            request_id=str(event_id),
            metadata_json={"customer_id": str(customer.id), "code": customer.code},
        )
    )
    db.add(
        OutboxEvent(
            id=event_id,
            event_type="commerce.customer.created",
            aggregate_id=str(customer.id),
            payload_json={"code": customer.code, "name": customer.name},
        )
    )
    await _store_response(db, key, clean, body)
    return body


@router.post("/suppliers", status_code=201)
async def create_supplier(
    payload: SupplierInput,
    request: Request,
    user=Depends(require_any_capability(*_WRITE_CAPS)),
    db: AsyncSession = Depends(get_db),
):
    clean = payload.model_dump()
    clean["code"] = clean["code"].strip()
    clean["name"] = clean["name"].strip()
    if not clean["code"] or not clean["name"]:
        raise AppError(422, "INVALID_SUPPLIER", "Mã và tên nhà cung cấp là bắt buộc.")
    for key in ("contact_person", "phone", "email", "address"):
        clean[key] = clean[key].strip() or None if clean[key] else None
    key = _request_key(request)
    replay = await _claim_or_replay(db, key, clean, "commerce.supplier.create")
    if replay is not None:
        return replay
    supplier = Supplier(
        id=uuid.uuid4(),
        **clean,
        branch_id=getattr(user, "branch_id", None),
    )
    db.add(supplier)
    await db.flush()
    response = {
        "id": str(supplier.id),
        "code": supplier.code,
        "name": supplier.name,
        "phone": supplier.phone,
        "active": supplier.is_active,
    }
    event_id = uuid.uuid4()
    db.add(
        AuditEvent(
            id=uuid.uuid4(),
            actor_id=user.id,
            action="commerce.supplier.created",
            subject="supplier",
            request_id=str(event_id),
            metadata_json={"supplier_id": str(supplier.id), "code": supplier.code},
        )
    )
    db.add(
        OutboxEvent(
            id=event_id,
            event_type="commerce.supplier.created",
            aggregate_id=str(supplier.id),
            payload_json={"code": supplier.code, "name": supplier.name},
        )
    )
    await _store_response(db, key, clean, response)
    return response


@router.get("/documents")
async def list_documents(
    document_type: Literal["sale", "quote", "purchase"] | None = None,
    location_id: uuid.UUID | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    user=Depends(require_any_capability(*_READ_CAPS)),
    db: AsyncSession = Depends(get_db),
):
    query = (
        select(CommerceDocument)
        .order_by(CommerceDocument.created_at.desc(), CommerceDocument.id)
        .offset(offset)
        .limit(limit)
    )
    if document_type:
        query = query.where(CommerceDocument.document_type == document_type)
    branch_id = getattr(user, "branch_id", None)
    if branch_id is not None:
        query = query.where(CommerceDocument.branch_id == branch_id)
    if location_id is not None:
        await _require_location_scope(db, user, location_id)
        matching_requests = select(InventoryRequest.id).where(
            or_(
                InventoryRequest.source_id == location_id,
                InventoryRequest.dest_id == location_id,
            )
        )
        query = query.where(
            or_(
                CommerceDocument.document_type == "quote",
                CommerceDocument.inventory_request_id.in_(matching_requests),
            )
        )
    documents = (await db.execute(query)).scalars().all()
    document_ids = [document.id for document in documents]
    lines = (
        await db.execute(
            select(CommerceDocumentLine)
            .where(CommerceDocumentLine.document_id.in_(document_ids))
            .order_by(CommerceDocumentLine.id)
        )
    ).scalars().all() if document_ids else []
    payments = (
        await db.execute(
            select(CommercePayment)
            .where(CommercePayment.document_id.in_(document_ids))
            .order_by(CommercePayment.payment_date, CommercePayment.created_at)
        )
    ).scalars().all() if document_ids else []
    lines_by_document: dict[uuid.UUID, list[CommerceDocumentLine]] = {}
    payments_by_document: dict[uuid.UUID, list[CommercePayment]] = {}
    for line in lines:
        lines_by_document.setdefault(line.document_id, []).append(line)
    for payment in payments:
        payments_by_document.setdefault(payment.document_id, []).append(payment)
    result = [
        _document_out(
            document,
            lines_by_document.get(document.id, []),
            payments_by_document.get(document.id, []),
        )
        for document in documents
    ]
    return {
        "documents": result,
        "limit": limit,
        "offset": offset,
        "next_offset": offset + limit if len(documents) == limit else None,
    }


@router.post("/documents", status_code=201)
async def create_document(
    payload: DocumentInput,
    request: Request,
    user=Depends(require_any_capability(*_WRITE_CAPS)),
    db: AsyncSession = Depends(get_db),
):
    body = payload.model_dump(mode="json")
    key = _request_key(request)
    replay = await _claim_or_replay(db, key, body, "commerce.document.create")
    if replay is not None:
        return replay

    branch_id = getattr(user, "branch_id", None)
    customer = await _customer(db, payload.customer_id, branch_id) if payload.customer_id else None
    supplier = await _supplier(db, payload.supplier_id, branch_id) if payload.supplier_id else None
    location_id = payload.location_id
    if location_id is not None:
        await _require_location_scope(db, user, location_id)

    item_ids = sorted({line.item_id for line in payload.lines}, key=str)
    items = (
        await db.execute(
            select(Item).where(Item.id.in_(item_ids), Item.active.is_(True)).with_for_update()
        )
    ).scalars().all()
    item_by_id = {item.id: item for item in items}
    if len(item_by_id) != len(item_ids):
        raise AppError(404, "ITEM_NOT_FOUND", "Có sản phẩm không tồn tại hoặc đã ngừng kinh doanh.")

    normalized = []
    subtotal = _ZERO
    for line in payload.lines:
        item = item_by_id[line.item_id]
        if payload.document_type == "purchase":
            if not line.lot_no or line.expiry_date is None:
                raise AppError(422, "LOT_REQUIRED", "Phiếu nhập cần số lô và hạn sử dụng cho từng sản phẩm.")
            if line.expiry_date < payload.document_date:
                raise AppError(422, "EXPIRED_LOT", f"Lô {line.lot_no} đã hết hạn trước ngày nhập.")
        line_total = _money(line.quantity * line.unit_price)
        subtotal += line_total
        normalized.append((line, item, line_total))
    subtotal = _money(subtotal)
    if payload.discount > subtotal:
        raise AppError(422, "DISCOUNT_EXCEEDS_SUBTOTAL", "Chiết khấu không được lớn hơn tiền hàng.")
    vat = _money((subtotal - payload.discount) * payload.vat_percent / Decimal("100"))
    total = _money(subtotal - payload.discount + vat + payload.shipping)

    document_id = uuid.uuid4()
    prefix = {"sale": "HD", "quote": "BG", "purchase": "NM"}[payload.document_type]
    code = f"{prefix}-{payload.document_date:%Y%m%d}-{document_id.hex[:8].upper()}"
    inventory_request = None
    status = "draft" if payload.document_type == "quote" else "pending_inventory"
    if payload.document_type in ("sale", "purchase"):
        inventory_request = InventoryRequest(
            id=uuid.uuid4(),
            kind="issue" if payload.document_type == "sale" else "receipt",
            status="submitted",
            maker_id=user.id,
            created_by=user.id,
            source_id=location_id if payload.document_type == "sale" else None,
            dest_id=location_id if payload.document_type == "purchase" else None,
            reason=f"Chứng từ {code}",
            supplier=supplier.name if supplier else None,
            invoice_no=code,
            sub_kind="sale" if payload.document_type == "sale" else None,
            received_at=datetime.combine(payload.document_date, datetime.min.time(), tzinfo=UTC),
            submitted_at=datetime.now(UTC),
            version=2,
        )
        db.add(inventory_request)
        await db.flush()
        if payload.document_type == "sale":
            await _reserve_sale_stock(db, location_id, normalized)
        db.add(
            AuditEvent(
                id=uuid.uuid4(),
                actor_id=user.id,
                action="inventory.request.submitted",
                subject="inventory_request",
                request_id=str(inventory_request.id),
                metadata_json={"request_id": str(inventory_request.id), "reason": f"Chứng từ {code}"},
            )
        )
        db.add(
            OutboxEvent(
                id=uuid.uuid4(),
                event_type="inventory.request.submitted",
                aggregate_id=str(inventory_request.id),
                payload_json={"request_id": str(inventory_request.id), "source": "commerce"},
            )
        )

    document = CommerceDocument(
        id=document_id,
        code=code,
        document_type=payload.document_type,
        status=status,
        customer_id=customer.id if customer else None,
        supplier_id=supplier.id if supplier else None,
        inventory_request_id=inventory_request.id if inventory_request else None,
        document_date=payload.document_date,
        due_date=payload.due_date,
        subtotal=subtotal,
        discount=payload.discount,
        vat=vat,
        shipping=payload.shipping,
        total=total,
        paid=_ZERO,
        note=payload.note.strip(),
        branch_id=branch_id,
        created_by=user.id,
    )
    db.add(document)
    await db.flush()

    for line, item, line_total in normalized:
        line_id = uuid.uuid4()
        unit_cost = Decimal(str(item.cost_price or _ZERO))
        db.add(
            CommerceDocumentLine(
                id=line_id,
                document_id=document.id,
                item_id=item.id,
                item_sku=item.sku,
                item_name=item.name,
                unit=item.unit,
                quantity=line.quantity,
                unit_price=line.unit_price,
                unit_cost=unit_cost,
                line_total=line_total,
                lot_no=line.lot_no,
                expiry_date=line.expiry_date,
            )
        )
        if inventory_request is not None:
            db.add(
                InventoryRequestLine(
                    id=line_id,
                    request_id=inventory_request.id,
                    item_id=item.id,
                    quantity=line.quantity,
                    direction="increase",
                    unit=item.unit,
                    unit_price=line.unit_price if payload.document_type == "purchase" else None,
                    lot_no=line.lot_no if payload.document_type == "purchase" else None,
                    expiry_date=line.expiry_date if payload.document_type == "purchase" else None,
                )
            )
    await db.flush()

    if inventory_request is not None and payload.document_type in ("sale", "purchase"):
        if payload.document_type == "sale":
            debit_code, credit_code = "111", "511"
        else:
            debit_code, credit_code = "156", "331"
        journal = InventoryJournal(
            id=uuid.uuid4(),
            request_id=inventory_request.id,
            posted_at=datetime.now(UTC),
            correlation_id=code,
            reversal_of=None,
        )
        db.add(journal)
        await db.flush()  # flush journal trước để có id trong inv_journals

        entries = [
            InventoryEntry(
                id=uuid.uuid4(),
                journal_id=journal.id,
                account_code=debit_code,
                debit=total,
                credit=Decimal("0"),
            ),
            InventoryEntry(
                id=uuid.uuid4(),
                journal_id=journal.id,
                account_code=credit_code,
                debit=Decimal("0"),
                credit=total,
            ),
        ]
        db.add_all(entries)
        await db.flush()  # rồi flush entries
        await post_subledger_journal(
            db,
            source_type="inventory",
            source_journal=journal,
            entries=entries,
        )

    lines = (await db.execute(select(CommerceDocumentLine).where(CommerceDocumentLine.document_id == document.id))).scalars().all()
    response = _document_out(document, lines)
    await _audit_and_outbox(db, user, "commerce.document.created", document, {"code": code, "status": status})
    await _store_response(db, key, body, response)
    return response


@router.post("/documents/{document_id}/payments", status_code=201)
async def record_payment(
    document_id: uuid.UUID,
    payload: PaymentInput,
    request: Request,
    user=Depends(require_any_capability(*_WRITE_CAPS)),
    db: AsyncSession = Depends(get_db),
):
    body = payload.model_dump(mode="json")
    key = _request_key(request)
    replay_payload = {"document_id": str(document_id), **body}
    replay = await _claim_or_replay(
        db, key, replay_payload, "commerce.payment.create"
    )
    if replay is not None:
        return replay
    query = select(CommerceDocument).where(CommerceDocument.id == document_id).with_for_update()
    branch_id = getattr(user, "branch_id", None)
    if branch_id is not None:
        query = query.where(CommerceDocument.branch_id == branch_id)
    document = (await db.execute(query)).scalar_one_or_none()
    if document is None:
        raise AppError(404, "DOCUMENT_NOT_FOUND", "Không tìm thấy chứng từ.")
    if document.document_type == "quote" or document.status != "confirmed":
        raise AppError(409, "DOCUMENT_NOT_PAYABLE", "Chỉ chứng từ đã xác nhận mới được thu hoặc trả tiền.")
    outstanding = Decimal(str(document.total)) - Decimal(str(document.paid))
    if payload.amount > outstanding:
        raise AppError(409, "PAYMENT_EXCEEDS_OUTSTANDING", "Số tiền vượt quá công nợ còn lại.")
    payment_type = "receipt" if document.document_type == "sale" else "disbursement"
    payment = CommercePayment(
        id=uuid.uuid4(),
        document_id=document.id,
        payment_type=payment_type,
        amount=payload.amount,
        payment_date=payload.payment_date,
        method=payload.method,
        reference=payload.reference.strip(),
        note=payload.note.strip(),
        created_by=user.id,
    )
    document.paid = Decimal(str(document.paid)) + payload.amount
    db.add(payment)
    await db.flush()
    response = {
        "id": str(payment.id),
        "document_id": str(document.id),
        "payment_type": payment_type,
        "amount": str(payment.amount),
        "paid": str(document.paid),
        "outstanding": str(Decimal(str(document.total)) - Decimal(str(document.paid))),
    }
    await _audit_and_outbox(db, user, "commerce.payment.recorded", document, response)
    await _store_response(db, key, replay_payload, response)
    return response


@router.post("/documents/{document_id}/convert", status_code=201)
async def convert_quote(
    document_id: uuid.UUID,
    payload: ConvertQuoteInput,
    request: Request,
    user=Depends(require_any_capability(*_WRITE_CAPS)),
    db: AsyncSession = Depends(get_db),
):
    body = {"document_id": str(document_id), **payload.model_dump(mode="json")}
    key = _request_key(request)
    replay = await _claim_or_replay(db, key, body, "commerce.quote.convert")
    if replay is not None:
        return replay
    branch_id = getattr(user, "branch_id", None)
    query = select(CommerceDocument).where(CommerceDocument.id == document_id).with_for_update()
    if branch_id is not None:
        query = query.where(CommerceDocument.branch_id == branch_id)
    quote = (await db.execute(query)).scalar_one_or_none()
    if quote is None:
        raise AppError(404, "DOCUMENT_NOT_FOUND", "Không tìm thấy báo giá.")
    if quote.document_type != "quote" or quote.status != "draft":
        raise AppError(409, "QUOTE_NOT_CONVERTIBLE", "Chỉ báo giá đang chờ mới được chuyển thành đơn bán.")
    await _require_location_scope(db, user, payload.location_id)
    quote_lines = (
        await db.execute(
            select(CommerceDocumentLine).where(
                CommerceDocumentLine.document_id == quote.id
            ).order_by(CommerceDocumentLine.id)
        )
    ).scalars().all()
    item_ids = sorted({line.item_id for line in quote_lines}, key=str)
    items = (
        await db.execute(
            select(Item).where(Item.id.in_(item_ids), Item.active.is_(True)).with_for_update()
        )
    ).scalars().all()
    item_by_id = {item.id: item for item in items}
    if len(item_by_id) != len(item_ids):
        raise AppError(409, "ITEM_UNAVAILABLE", "Sản phẩm trong báo giá không còn kinh doanh.")
    normalized = [
        (line, item_by_id[line.item_id], Decimal(str(line.line_total)))
        for line in quote_lines
    ]
    await _reserve_sale_stock(db, payload.location_id, normalized)

    order_id = uuid.uuid4()
    code = f"HD-{_today():%Y%m%d}-{order_id.hex[:8].upper()}"
    inventory_request = InventoryRequest(
        id=uuid.uuid4(),
        kind="issue",
        status="submitted",
        maker_id=user.id,
        created_by=user.id,
        source_id=payload.location_id,
        reason=f"Chuyển từ báo giá {quote.code}",
        invoice_no=code,
        sub_kind="sale",
        received_at=datetime.now(UTC),
        submitted_at=datetime.now(UTC),
        version=2,
    )
    db.add(inventory_request)
    await db.flush()
    order = CommerceDocument(
        id=order_id,
        code=code,
        document_type="sale",
        status="pending_inventory",
        customer_id=quote.customer_id,
        inventory_request_id=inventory_request.id,
        document_date=_today(),
        due_date=quote.due_date,
        subtotal=quote.subtotal,
        discount=quote.discount,
        vat=quote.vat,
        shipping=quote.shipping,
        total=quote.total,
        paid=_ZERO,
        note=quote.note,
        branch_id=quote.branch_id,
        created_by=user.id,
    )
    db.add(order)
    for old_line in quote_lines:
        new_line_id = uuid.uuid4()
        db.add(
            CommerceDocumentLine(
                id=new_line_id,
                document_id=order.id,
                item_id=old_line.item_id,
                item_sku=old_line.item_sku,
                item_name=old_line.item_name,
                unit=old_line.unit,
                quantity=old_line.quantity,
                unit_price=old_line.unit_price,
                unit_cost=old_line.unit_cost,
                line_total=old_line.line_total,
            )
        )
        db.add(
            InventoryRequestLine(
                id=new_line_id,
                request_id=inventory_request.id,
                item_id=old_line.item_id,
                quantity=old_line.quantity,
                direction="increase",
                unit=old_line.unit,
            )
        )
    quote.status = "converted"
    await db.flush()
    new_lines = (
        await db.execute(
            select(CommerceDocumentLine).where(CommerceDocumentLine.document_id == order.id)
        )
    ).scalars().all()
    response = _document_out(order, new_lines)
    await _audit_and_outbox(db, user, "commerce.quote.converted", quote, {"order_id": str(order.id), "order_code": code})
    await _audit_and_outbox(db, user, "commerce.document.created", order, {"status": order.status, "source_quote": quote.code})
    db.add(
        AuditEvent(
            id=uuid.uuid4(),
            actor_id=user.id,
            action="inventory.request.submitted",
            subject="inventory_request",
            request_id=str(inventory_request.id),
            metadata_json={"request_id": str(inventory_request.id), "source_quote": quote.code},
        )
    )
    await _store_response(db, key, body, response)
    return response
