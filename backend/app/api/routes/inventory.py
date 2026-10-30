"""Inventory routes (docs/05, B05-B07).

Bất biến docs/00:
1. maker != checker, kể cả admin (A1).
2. đúng một lần post mỗi phiếu — optimistic lock + unique constraint (A2).
3. retry cùng Idempotency-Key + cùng payload replay; khác payload 409 (A3/A4).
4. xuất/chuyển quá tồn -> 409, balance giữ nguyên (I1).
5. mọi write đều audit + outbox trong cùng transaction.
"""
import hashlib
import os
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import AppError
from app.api.observability import record_approval_decision
from app.api.pagination import (
    KeysetSpec,
    apply_keyset,
    build_cursor_payload,
    clamp_limit,
    coerce_timestamp,
    decode_cursor,
    encode_cursor,
)
from app.api.request_context import request_id_var
from app.api.routes.auth_utils import (
    get_accessible_location_ids,
    get_current_user,
    get_user_capabilities,
    get_user_roles,
    require_any_capability,
)
from app.config import settings
from app.database import get_db
from app.models.activity import AuditEvent, OutboxEvent
from app.models.approval import ApprovalDecision
from app.models.iam import User
from app.models.inventory import (
    Asset,
    AssetLog,
    Balance,
    InventoryRequest,
    InventoryRequestLine,
    Item,
    Location,
    LotBalance,
    LotMovement,
    Movement,
    StockLevel,
    Stocktake,
    StocktakeLine,
)
from app.services import idempotency
from app.services.approval_controls import verify_supervisor_pin
from app.services.approval_events import broadcast_approval_event

router = APIRouter()

_VIEW_CATALOG = (
    "admin:user_management",
    "inventory:manage_catalog",
    "inventory:view_balances",
    "inventory:create_request",
    "inventory:approve_request",
)
_VIEW_ASSETS = (
    "admin:user_management",
    "inventory:manage_catalog",
    "inventory:view_balances",
    "inventory:create_request",
    "inventory:approve_request",
    "audit:view",
)
_KINDS = ("receipt", "issue", "transfer", "adjustment")
_SUB_KINDS = ("sale", "spoilage", "internal", "transfer")

class ApprovalInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    supervisor_pin: str | None = Field(default=None, min_length=1, max_length=128)


_SUBJECT = "inventory_request"
_APPROVE_CAPS = ("inventory:create_request", "inventory:approve_request")
_REQUEST_READ_CAPS = ("inventory:create_request", "inventory:approve_request", "inventory:review")
# Ghi lại quyết định của agent để reviewer đối chiếu (không dùng để đọc response).
_write_caps = require_any_capability("inventory:create_request")
_ZERO = Decimal("0")

# The web client currently presents the first four statuses.  The additional
# values preserve the documented custody vocabulary for security stationery.
_ASSET_STATUSES = frozenset(
    {
        "available",
        "in_vault",
        "assigned",
        "in_use",
        "issued",
        "maintenance",
        "damaged",
        "lost",
        "disposed",
        "retired",
    }
)
_ASSET_STATUS_TRANSITIONS = {
    "available": _ASSET_STATUSES - {"retired"},
    "in_vault": _ASSET_STATUSES - {"issued", "retired"},
    "assigned": _ASSET_STATUSES - {"issued", "retired"},
    "in_use": _ASSET_STATUSES - {"issued", "retired"},
    "maintenance": {"maintenance", "available", "in_vault", "damaged", "lost", "disposed"},
    "damaged": {"damaged", "maintenance", "disposed"},
    "lost": {"lost"},
    "issued": {"issued"},
    "disposed": {"disposed"},
    "retired": {"retired"},
}
_MOVABLE_ASSET_STATUSES = frozenset({"available", "in_vault"})


def _now() -> datetime:
    return datetime.now(UTC)


def _uuid(value: str, field: str) -> uuid.UUID:
    try:
        return uuid.UUID(str(value))
    except (ValueError, AttributeError, TypeError):
        raise AppError(422, "INVALID_UUID", f"{field} không phải UUID hợp lệ") from None


def _qty(raw) -> Decimal:
    try:
        return Decimal(str(raw))
    except (InvalidOperation, ValueError, TypeError):
        raise AppError(422, "INVALID_QUANTITY", f"quantity không hợp lệ: {raw!r}") from None


def _format_qty(val) -> str | None:
    if val is None:
        return None
    try:
        d = Decimal(str(val))
    except (InvalidOperation, ValueError, TypeError):
        return str(val)
    if d == d.to_integral():
        return str(int(d))
    s = str(d)
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return s


# Khung giờ 3 ca quầy trà sữa (SRS §3.3): Sáng 07:30–15:00,
# Chiều 15:00–23:00, Lỡ ngày 07:30–18:00. Ca Lỡ ghi nhận độc lập,
# không thay thế chuỗi bàn giao Sáng → Chiều.
_SHIFT_WINDOWS = {
    "morning": ("Ca Sáng", "07:30", "15:00"),
    "afternoon": ("Ca Chiều", "15:00", "23:00"),
    "split": ("Ca Lỡ ngày", "07:30", "18:00"),
}
_SHIFT_ORDER = {"morning": 0, "split": 1, "afternoon": 2}


def _hanoi_today() -> date:
    try:
        from zoneinfo import ZoneInfo

        return datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).date()
    except Exception:
        return datetime.now(UTC).date()


def _parse_datetime(raw, field: str = "received_at") -> datetime | None:
    if raw in (None, ""):
        return None
    try:
        dt = datetime.fromisoformat(str(raw))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt
    except ValueError:
        try:
            d = date.fromisoformat(str(raw))
            return datetime(d.year, d.month, d.day, tzinfo=UTC)
        except ValueError:
            raise AppError(422, "INVALID_DATETIME", f"{field} phải theo định dạng ISO hoặc YYYY-MM-DD") from None


_parse_date = _parse_datetime


def _parse_day(raw, field: str = "business_date") -> date | None:
    if raw in (None, ""):
        return None
    try:
        return date.fromisoformat(str(raw))
    except ValueError:
        raise AppError(422, "INVALID_DATE", f"{field} phải theo định dạng YYYY-MM-DD") from None


def _parse_expiry(raw) -> date | None:
    if raw in (None, ""):
        return None
    try:
        return date.fromisoformat(str(raw))
    except ValueError:
        raise AppError(422, "INVALID_EXPIRY", "expiry_date phải theo định dạng YYYY-MM-DD") from None


def _parse_money(raw, field: str = "unit_price") -> Decimal | None:
    if raw in (None, ""):
        return None
    try:
        val = Decimal(str(raw))
    except (InvalidOperation, ValueError, TypeError):
        raise AppError(422, "INVALID_PRICE", f"{field} không hợp lệ: {raw!r}") from None
    if val < 0:
        raise AppError(422, "NEGATIVE_PRICE", f"{field} không được âm")
    return val


def _line_total(qty: Decimal, price: Decimal | None) -> str | None:
    if price is None:
        return None
    total = (qty * price).quantize(Decimal("0.01"))
    return str(total)


def _item_out(item: Item, is_admin: bool = True) -> dict:
    """Return the ingredient catalog representation used by all item APIs.
    
    Chỉ Admin/Manager mới thấy cost_price & selling_price; nhân viên khác nhận None.
    """
    has_cost = is_admin and getattr(item, "cost_price", None) is not None
    has_selling = is_admin and getattr(item, "selling_price", None) is not None
    return {
        "id": str(item.id),
        "sku": item.sku,
        "name": item.name,
        "unit": item.unit,
        "category": item.category,
        "packaging": item.packaging,
        "cost_price": float(item.cost_price) if has_cost else None,
        "selling_price": float(item.selling_price) if has_selling else None,
        "min_stock": float(item.min_stock) if getattr(item, "min_stock", None) is not None else None,
        "tracked_serial": item.tracked_serial,
        "active": item.active,
    }


def _stocktake_line_out(line: StocktakeLine) -> dict:
    return {
        "id": str(line.id),
        "item_id": str(line.item_id),
        "book_qty": _format_qty(line.book_qty),
        "opening_qty": _format_qty(line.opening_qty),
        "received_qty": _format_qty(line.received_qty),
        "used_qty": _format_qty(line.used_qty),
        "theoretical_qty": _format_qty(line.theoretical_qty),
        "counted_qty": _format_qty(line.counted_qty),
        "variance": _format_qty(line.variance),
        "reason": line.reason,
    }


def _check_if_match(request: Request, version: int) -> None:
    raw = request.headers.get("if-match")
    if raw is None:
        return
    expected = raw.strip().strip('"')
    if expected.isdigit() and int(expected) != version:
        raise AppError(
            409,
            "VERSION_CONFLICT",
            f"If-Match={expected} nhưng version hiện tại là {version}",
            {"current_version": version},
        )


def _req_out(req: InventoryRequest, lines: list | None = None) -> dict:
    body: dict = {
        "id": str(req.id),
        "kind": req.kind,
        "status": req.status,
        "version": req.version,
        "maker_id": str(req.maker_id),
        "approver_id": str(req.approver_id) if req.approver_id else None,
        "reason": req.reason,
        "created_at": req.created_at.isoformat() if getattr(req, "created_at", None) else None,
        "simulation": True,
    }
    if req.source_id:
        body["source_id"] = str(req.source_id)
    if req.dest_id:
        body["dest_id"] = str(req.dest_id)
    if getattr(req, "return_reason", None):
        body["return_reason"] = req.return_reason
    if getattr(req, "supplier", None):
        body["supplier"] = req.supplier
    if getattr(req, "invoice_no", None):
        body["invoice_no"] = req.invoice_no
    if getattr(req, "sub_kind", None):
        body["sub_kind"] = req.sub_kind
    if getattr(req, "received_at", None):
        body["received_at"] = req.received_at.isoformat()
    if lines is not None:
        body["lines"] = lines
        tot_amt = Decimal("0")
        for ln in lines:
            lt = ln.get("line_total")
            if lt is not None:
                tot_amt += Decimal(str(lt))
        body["total_amount"] = str(tot_amt)
    return body


async def _load_lines(db: AsyncSession, request_id) -> list:
    rows = (
        await db.execute(
            select(InventoryRequestLine).where(
                InventoryRequestLine.request_id == request_id
            )
        )
    ).scalars().all()
    return [
        {
            "id": str(r.id),
            "item_id": str(r.item_id),
            "quantity": str(r.quantity),
            "direction": getattr(r, "direction", "increase"),
            "serial": r.serial,
            "unit": getattr(r, "unit", None),
            "conversion_rate": str(r.conversion_rate) if getattr(r, "conversion_rate", None) is not None else None,
            "unit_price": str(r.unit_price) if r.unit_price is not None else None,
            "line_total": _line_total(r.quantity, r.unit_price),
            "lot_no": getattr(r, "lot_no", None),
            "expiry_date": r.expiry_date.isoformat() if getattr(r, "expiry_date", None) else None,
        }
        for r in rows
    ]


async def _load_request(db: AsyncSession, request_id: str) -> InventoryRequest:
    req = (
        await db.execute(
            select(InventoryRequest).where(
                InventoryRequest.id == _uuid(request_id, "request_id")
            )
        )
    ).scalar_one_or_none()
    if req is None:
        raise AppError(404, "NOT_FOUND", "Phiếu không tồn tại")
    return req


async def _load_request_for_read(db, request_id: str, user) -> InventoryRequest:
    """Maker reads own requests; approvers and reviewers may read within scope."""
    req = await _load_request(db, request_id)
    if str(req.maker_id) == str(user.id):
        return req
    caps = await get_user_capabilities(db, user.id)
    if "inventory:approve_request" not in caps and "inventory:review" not in caps:
        raise AppError(404, "NOT_FOUND", "Phiếu không tồn tại hoặc ngoài phạm vi của bạn")
    accessible_locations = await get_accessible_location_ids(db, user)
    if accessible_locations is not None and not (
        (req.source_id is not None and req.source_id in accessible_locations)
        or (req.dest_id is not None and req.dest_id in accessible_locations)
    ):
        raise AppError(404, "NOT_FOUND", "Phiếu không tồn tại hoặc ngoài phạm vi của bạn")
    return req


async def _resolve_item_id(db: AsyncSession, line: dict):
    if line.get("item_id"):
        iid = _uuid(line["item_id"], "item_id")
        if (await db.execute(select(Item.id).where(Item.id == iid))).scalar_one_or_none() is None:
            raise AppError(422, "ITEM_NOT_FOUND", f"item_id {line['item_id']} không tồn tại")
        return iid
    if line.get("sku"):
        row = (await db.execute(select(Item).where(Item.sku == line["sku"]))).scalar_one_or_none()
        if row is not None:
            return row.id
    raise AppError(422, "ITEM_NOT_FOUND", f"Không xác định được item từ {line!r}")


async def _require_location_scope(
    db: AsyncSession, user: User, location_id: uuid.UUID
) -> None:
    """Fail closed without confirming whether an out-of-scope location exists."""
    allowed_location_ids = await get_accessible_location_ids(db, user)
    if allowed_location_ids is not None and location_id not in allowed_location_ids:
        raise AppError(404, "LOCATION_NOT_FOUND", "Không tìm thấy kho trong phạm vi được cấp.")


def _validate_transition(req: InventoryRequest, kind: str, src, dst) -> None:
    """issue/transfer bắt buộc source; receipt/adjustment bắt buộc target."""
    if req.kind in ("issue", "transfer") and src is None:
        raise AppError(422, "SOURCE_REQUIRED", f"kind={kind} yêu cầu source_id")
    if req.kind in ("receipt", "adjustment") and src is None and dst is None:
        raise AppError(
            422, "DESTINATION_REQUIRED", f"kind={kind} yêu cầu dest_id (hoặc source_id)"
        )
    if req.kind == "transfer" and (src is None or dst is None):
        raise AppError(422, "DESTINATION_REQUIRED", "transfer yêu cầu cả source_id và dest_id")


async def _get_balance(
    db: AsyncSession, location_id, item_id, *, for_update: bool = False
) -> Balance | None:
    stmt = select(Balance).where(
        Balance.location_id == location_id, Balance.item_id == item_id
    )
    if for_update:
        stmt = stmt.with_for_update()
    return (await db.execute(stmt)).scalar_one_or_none()


async def _lock_balances(
    db: AsyncSession, balance_keys: set[tuple[object, object]]
) -> dict[tuple[object, object], Balance]:
    """Lock every existing balance in one stable order before a posting writes.

    Request approval can touch both sides of a transfer.  Taking every lock in
    the same `(location_id, item_id)` order prevents a transfer A→B and B→A
    from deadlocking while preserving a single serialisable balance update.
    """
    locked: dict[tuple[object, object], Balance] = {}
    for location_id, item_id in sorted(balance_keys, key=lambda key: (str(key[0]), str(key[1]))):
        balance = await _get_balance(db, location_id, item_id, for_update=True)
        if balance is not None:
            locked[(location_id, item_id)] = balance
    return locked


def _affected_balance_keys(
    req: InventoryRequest, lines: list[InventoryRequestLine]
) -> set[tuple[object, object]]:
    keys: set[tuple[object, object]] = set()
    for line in lines:
        if req.kind == "transfer" and req.source_id is not None and req.dest_id is not None:
            keys.add((req.source_id, line.item_id))
            keys.add((req.dest_id, line.item_id))
        elif req.kind == "issue" and req.source_id is not None:
            keys.add((req.source_id, line.item_id))
        else:
            target = req.dest_id or req.source_id
            if target is not None:
                keys.add((target, line.item_id))
    return keys


async def _lock_and_validate_serial_assets(
    db: AsyncSession, req: InventoryRequest, lines: list[InventoryRequestLine]
) -> dict[str, Asset]:
    """Lock serial assets and validate custody before stock is ever posted."""
    serial_lines = [line for line in lines if line.serial and line.serial.strip()]
    if not serial_lines:
        return {}

    serials = [line.serial.strip() for line in serial_lines]
    if len(serials) != len(set(serials)):
        raise AppError(422, "DUPLICATE_SERIAL_LINE", "Một serial chỉ được xuất hiện một lần trong phiếu")

    rows = (
        await db.execute(
            select(Asset)
            .where(Asset.serial.in_(sorted(serials)))
            .order_by(Asset.serial)
            .with_for_update()
        )
    ).scalars().all()
    assets = {asset.serial: asset for asset in rows}

    for line in serial_lines:
        serial = line.serial.strip()
        asset = assets.get(serial)
        if asset is None:
            raise AppError(422, "SERIAL_ASSET_NOT_FOUND", f"Không tìm thấy serial {serial!r}")
        if str(asset.item_id) != str(line.item_id):
            raise AppError(422, "SERIAL_ITEM_MISMATCH", "Serial không thuộc mặt hàng trên dòng phiếu")
        if req.kind in ("issue", "transfer"):
            if str(asset.location_id) != str(req.source_id):
                raise AppError(422, "SERIAL_SOURCE_MISMATCH", "Serial không nằm tại kho nguồn của phiếu")
            if asset.status not in _MOVABLE_ASSET_STATUSES:
                raise AppError(
                    422,
                    "SERIAL_STATUS_INVALID",
                    f"Serial {serial!r} không ở trạng thái có thể xuất/chuyển",
                )
    return assets


async def _audit(db, actor_id, action: str, req: InventoryRequest, before: dict) -> None:
    http_request_id = request_id_var.get()
    audit_request_id = (
        http_request_id
        if len(http_request_id) <= 64
        else hashlib.sha256(http_request_id.encode("utf-8")).hexdigest()
    )
    db.add(
        AuditEvent(
            id=uuid.uuid4(),
            actor_id=actor_id,
            action=action,
            subject=f"{_SUBJECT}:{req.id}",
            before_hash=idempotency.payload_hash(before),
            after_hash=idempotency.payload_hash(
                {"status": req.status, "version": req.version}
            ),
            request_id=audit_request_id,
            occurred_at=_now(),
            metadata_json={"kind": req.kind, "status": req.status},
        )
    )


async def _outbox(db, event_type: str, req: InventoryRequest, extra: dict) -> None:
    db.add(
        OutboxEvent(
            id=uuid.uuid4(),
            event_type=event_type,
            aggregate_id=str(req.id),
            payload_json={
                "subject_type": _SUBJECT,
                "subject_id": str(req.id),
                "kind": req.kind,
                "status": req.status,
                "version": req.version,
                **extra,
            },
            created_at=_now(),
        )
    )


async def _audit_stocktake(
    db: AsyncSession, actor_id, action: str, stocktake: Stocktake, before: dict
) -> None:
    db.add(
        AuditEvent(
            id=uuid.uuid4(),
            actor_id=actor_id,
            action=action,
            subject=f"inventory_stocktake:{stocktake.id}",
            before_hash=idempotency.payload_hash(before),
            after_hash=idempotency.payload_hash(
                {
                    "status": stocktake.status,
                    "adjustment_request_id": str(stocktake.adjustment_request_id)
                    if stocktake.adjustment_request_id
                    else None,
                }
            ),
            occurred_at=_now(),
            metadata_json={
                "location_id": str(stocktake.location_id),
                "status": stocktake.status,
                "adjustment_request_id": str(stocktake.adjustment_request_id)
                if stocktake.adjustment_request_id
                else None,
            },
        )
    )


async def _outbox_stocktake(
    db: AsyncSession, event_type: str, stocktake: Stocktake
) -> None:
    db.add(
        OutboxEvent(
            id=uuid.uuid4(),
            event_type=event_type,
            aggregate_id=str(stocktake.id),
            payload_json={
                "subject_type": "inventory_stocktake",
                "subject_id": str(stocktake.id),
                "location_id": str(stocktake.location_id),
                "status": stocktake.status,
                "adjustment_request_id": str(stocktake.adjustment_request_id)
                if stocktake.adjustment_request_id
                else None,
            },
            created_at=_now(),
        )
    )


def _require_key(request: Request) -> str:
    key = request.headers.get("idempotency-key")
    if not key or not key.strip():
        raise AppError(
            400,
            "IDEMPOTENCY_KEY_REQUIRED",
            "Header Idempotency-Key là bắt buộc với mọi thao tác ghi (docs/06)",
        )
    return key.strip()


def _replay(key: str, payload) -> dict | None:
    replay = idempotency.check(key, idempotency.payload_hash(payload))
    if replay is None:
        return None
    _status, body = replay
    return body


async def _stocktake_replay(db: AsyncSession, key: str | None, operation: dict) -> dict | None:
    """Read the durable response before repeating a stocktake write."""
    if not key:
        return None
    record = await idempotency.find_key(db, key)
    if record is None:
        return None
    if record.request_hash != idempotency.payload_hash(operation):
        raise AppError(409, "IDEMPOTENCY_KEY_REUSED", "Idempotency-Key đã dùng cho payload khác")
    return record.response_body if record.status_code is not None else None

# --------------------------------------------------------------------------
# --------------------------------------------------------------------------
# Catalog reads
# --------------------------------------------------------------------------
@router.get("/inventory/items")
async def list_items(
    current_user=Depends(require_any_capability(*_VIEW_CATALOG)),
    db: AsyncSession = Depends(get_db),
):
    items = (await db.execute(select(Item).where(Item.active.is_(True)))).scalars().all()
    roles = await get_user_roles(db, current_user.id)
    is_admin = any(r in ("admin", "superadmin", "manager") for r in roles)
    if not is_admin:
        caps = await get_user_capabilities(db, current_user.id)
        is_admin = "admin:user_management" in caps or "admin" in caps or getattr(current_user, "is_superuser", False)
    return {
        "items": [_item_out(i, is_admin=is_admin) for i in items]
    }


@router.get("/inventory/items/{item_id}")
async def get_item(
    item_id: str,
    current_user=Depends(require_any_capability(*_VIEW_CATALOG)),
    db: AsyncSession = Depends(get_db),
):
    item = await db.get(Item, _uuid(item_id, "item_id"))
    if not item or not item.active:
        raise AppError(404, "ITEM_NOT_FOUND", "Không tìm thấy nguyên liệu")
    roles = await get_user_roles(db, current_user.id)
    is_admin = any(r in ("admin", "superadmin", "manager") for r in roles)
    if not is_admin:
        caps = await get_user_capabilities(db, current_user.id)
        is_admin = "admin:user_management" in caps or "admin" in caps or getattr(current_user, "is_superuser", False)
    return _item_out(item, is_admin=is_admin)


@router.post("/inventory/items", status_code=201)
async def create_item(
    payload: dict,
    current_user=Depends(require_any_capability("inventory:manage_catalog", "admin:user_management")),
    db: AsyncSession = Depends(get_db),
):
    sku = str(payload.get("sku", "")).strip().upper()
    name = str(payload.get("name", "")).strip()
    unit = str(payload.get("unit", "")).strip() or "đơn vị"
    category = str(payload.get("category", "")).strip() or None
    packaging = str(payload.get("packaging", "")).strip() or None
    tracked_serial = bool(payload.get("tracked_serial", False))
    cost_price = Decimal(str(payload["cost_price"])) if payload.get("cost_price") is not None else None
    selling_price = Decimal(str(payload["selling_price"])) if payload.get("selling_price") is not None else None
    min_stock = Decimal(str(payload["min_stock"])) if payload.get("min_stock") is not None else None
    if not sku:
        raise AppError(422, "MISSING_SKU", "SKU không được để trống")
    if not name:
        raise AppError(422, "MISSING_NAME", "Tên nguyên liệu không được để trống")
    existing = (await db.execute(select(Item).where(Item.sku == sku))).scalars().first()
    if existing:
        if not existing.active:
            existing.active = True
            existing.name = name
            existing.unit = unit
            existing.category = category
            existing.packaging = packaging
            existing.tracked_serial = tracked_serial
            existing.cost_price = cost_price
            existing.selling_price = selling_price
            existing.min_stock = min_stock
            await db.commit()
            await db.refresh(existing)
            return _item_out(existing)
        raise AppError(409, "DUPLICATE_SKU", f"SKU {sku} đã tồn tại")
    item = Item(
        id=uuid.uuid4(),
        sku=sku,
        name=name,
        unit=unit,
        category=category,
        packaging=packaging,
        cost_price=cost_price,
        selling_price=selling_price,
        min_stock=min_stock,
        tracked_serial=tracked_serial,
        active=True,
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return _item_out(item)


MAX_BATCH_ITEMS = 100
MAX_OPEN_DRAFTS_PER_USER = int(os.environ.get("MAX_OPEN_DRAFTS_PER_USER", "0"))


@router.post("/inventory/items/batch", status_code=201)
async def create_items_batch(
    payload: dict,
    current_user=Depends(require_any_capability("inventory:manage_catalog", "admin:user_management")),
    db: AsyncSession = Depends(get_db),
):
    raw_items = payload.get("items", [])
    if not isinstance(raw_items, list) or not raw_items:
        raise AppError(422, "EMPTY_BATCH", "Danh sách mặt hàng không được để trống")
    if len(raw_items) > MAX_BATCH_ITEMS:
        raise AppError(
            422,
            "BATCH_TOO_LARGE",
            f"Mỗi lô tải lên tối đa {MAX_BATCH_ITEMS} mặt hàng để đảm bảo an toàn hệ thống.",
        )

    skus = [str(r.get("sku", "")).strip().upper() for r in raw_items if r.get("sku")]
    existing_items_res = await db.execute(select(Item).where(Item.sku.in_(skus)))
    existing_map = {item.sku: item for item in existing_items_res.scalars().all()}

    created_items = []
    skipped_count = 0
    seen_in_batch = set()

    for r in raw_items:
        sku = str(r.get("sku", "")).strip().upper()
        name = str(r.get("name", "")).strip()
        unit = str(r.get("unit", "")).strip() or "đơn vị"
        category = str(r.get("category", "")).strip() or None
        packaging = str(r.get("packaging", "")).strip() or None

        if not sku or not name:
            skipped_count += 1
            continue
        if sku in seen_in_batch:
            skipped_count += 1
            continue

        existing_item = existing_map.get(sku)
        if existing_item:
            if not existing_item.active:
                existing_item.active = True
                existing_item.name = name
                existing_item.unit = unit
                existing_item.category = category
                existing_item.packaging = packaging
                seen_in_batch.add(sku)
                created_items.append(existing_item)
                continue
            else:
                skipped_count += 1
                continue

        seen_in_batch.add(sku)
        item = Item(
            id=uuid.uuid4(),
            sku=sku,
            name=name,
            unit=unit,
            category=category,
            packaging=packaging,
            tracked_serial=False,
            active=True,
        )
        db.add(item)
        created_items.append(item)

    await db.commit()
    for item in created_items:
        await db.refresh(item)

    return {
        "created_count": len(created_items),
        "skipped_count": skipped_count,
        "items": [_item_out(i) for i in created_items],
    }


@router.put("/inventory/items/{item_id}")
async def update_item(
    item_id: str,
    payload: dict,
    current_user=Depends(require_any_capability("inventory:manage_catalog", "admin:user_management")),
    db: AsyncSession = Depends(get_db),
):
    iid = _uuid(item_id, "item_id")
    item = (await db.execute(select(Item).where(Item.id == iid))).scalars().first()
    if not item:
        raise AppError(404, "ITEM_NOT_FOUND", "Không tìm thấy vật tư")
    if "name" in payload and payload["name"]:
        item.name = str(payload["name"]).strip()
    if "unit" in payload and payload["unit"]:
        item.unit = str(payload["unit"]).strip()
    if "category" in payload:
        item.category = str(payload["category"] or "").strip() or None
    if "packaging" in payload:
        item.packaging = str(payload["packaging"] or "").strip() or None
    if "cost_price" in payload:
        item.cost_price = Decimal(str(payload["cost_price"])) if payload["cost_price"] is not None else None
    if "selling_price" in payload:
        item.selling_price = Decimal(str(payload["selling_price"])) if payload["selling_price"] is not None else None
    if "min_stock" in payload:
        item.min_stock = Decimal(str(payload["min_stock"])) if payload["min_stock"] is not None else None
    if "tracked_serial" in payload:
        item.tracked_serial = bool(payload["tracked_serial"])
    if "active" in payload:
        item.active = bool(payload["active"])
    await db.commit()
    await db.refresh(item)
    return _item_out(item)


async def _perform_delete_item(db: AsyncSession, item: Item) -> dict:
    iid = item.id
    # Check if item has historical ledger or operational references
    has_movements = (await db.execute(select(Movement.id).where(Movement.item_id == iid).limit(1))).scalars().first()
    has_requests = (await db.execute(select(InventoryRequestLine.id).where(InventoryRequestLine.item_id == iid).limit(1))).scalars().first()
    has_stocktakes = (await db.execute(select(StocktakeLine.id).where(StocktakeLine.item_id == iid).limit(1))).scalars().first()

    if not has_movements and not has_requests and not has_stocktakes:
        # Hard delete: vật tư chưa từng phát sinh giao dịch -> xoá sạch cả
        # tồn kho và ngưỡng tồn kho (không còn dữ liệu tham chiếu).
        await db.execute(delete(Balance).where(Balance.item_id == iid))
        await db.execute(delete(StockLevel).where(StockLevel.item_id == iid))
        # Safe to hard delete completely, along with any unused assets
        await db.execute(delete(Asset).where(Asset.item_id == iid))
        await db.delete(item)
        mode = "hard_deleted"
    else:
        # R9 — soft delete: chỉ NGỪNG hoạt động vật tư, GIỮ NGUYÊN tồn kho
        # (`Balance`) và ngưỡng tồn kho (`StockLevel`). Xoá tồn ở nhánh này sẽ
        # làm mất tồn trong khi movement vẫn còn -> đối soát lệch vĩnh viễn.
        # Muốn giảm tồn thì phải lập Phiếu điều chỉnh (adjustment) qua luồng
        # maker -> checker, không xoá thẳng trong API xoá vật tư.
        item.active = False
        mode = "soft_deleted"

    return {"status": "deleted", "id": str(iid), "mode": mode}


@router.delete("/inventory/items/{item_id}")
async def delete_item(
    item_id: str,
    current_user=Depends(require_any_capability("inventory:manage_catalog", "admin:user_management")),
    db: AsyncSession = Depends(get_db),
):
    iid = _uuid(item_id, "item_id")
    item = (await db.execute(select(Item).where(Item.id == iid))).scalars().first()
    if not item:
        raise AppError(404, "ITEM_NOT_FOUND", "Không tìm thấy vật tư")
    res = await _perform_delete_item(db, item)
    await db.commit()
    return res


@router.post("/inventory/items/batch-delete")
async def batch_delete_items(
    payload: dict,
    current_user=Depends(require_any_capability("inventory:manage_catalog", "admin:user_management")),
    db: AsyncSession = Depends(get_db),
):
    raw_ids = payload.get("item_ids", [])
    if not isinstance(raw_ids, list) or not raw_ids:
        raise AppError(422, "EMPTY_BATCH", "Danh sách mã mặt hàng không được để trống")

    iids = [_uuid(i, "item_ids") for i in raw_ids]
    items = (await db.execute(select(Item).where(Item.id.in_(iids)))).scalars().all()
    found_map = {item.id: item for item in items}

    deleted_ids = []
    skipped_items = []

    for iid in iids:
        item = found_map.get(iid)
        if not item:
            skipped_items.append({"id": str(iid), "reason": "ITEM_NOT_FOUND"})
            continue
        try:
            await _perform_delete_item(db, item)
            deleted_ids.append(str(iid))
        except AppError as e:
            skipped_items.append({"id": str(iid), "reason": e.code, "message": e.message})

    await db.commit()
    return {
        "deleted_count": len(deleted_ids),
        "skipped_count": len(skipped_items),
        "deleted_ids": deleted_ids,
        "skipped_items": skipped_items,
    }


@router.get("/inventory/locations")
async def list_locations(
    current_user=Depends(require_any_capability(*_VIEW_CATALOG)),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Location)
    allowed_location_ids = await get_accessible_location_ids(db, current_user)
    if allowed_location_ids is not None:
        stmt = stmt.where(Location.id.in_(allowed_location_ids))
    locations = (await db.execute(stmt)).scalars().all()
    return {
        "locations": [
            {"id": str(loc.id), "code": loc.code, "name": loc.name, "active": loc.active}
            for loc in locations
        ]
    }


@router.post("/inventory/locations", status_code=201)
async def create_location(
    payload: dict,
    current_user=Depends(require_any_capability("inventory:manage_catalog", "admin:user_management")),
    db: AsyncSession = Depends(get_db),
):
    code = str(payload.get("code", "")).strip().upper()
    name = str(payload.get("name", "")).strip()
    if not code:
        raise AppError(422, "MISSING_CODE", "Mã kho không được để trống")
    if not name:
        raise AppError(422, "MISSING_NAME", "Tên kho không được để trống")
    existing = (await db.execute(select(Location).where(Location.code == code))).scalars().first()
    if existing:
        raise AppError(409, "DUPLICATE_CODE", f"Mã kho {code} đã tồn tại")
    loc = Location(
        id=uuid.uuid4(),
        code=code,
        name=name,
        active=True,
    )
    db.add(loc)
    await db.commit()
    await db.refresh(loc)
    return {"id": str(loc.id), "code": loc.code, "name": loc.name, "active": loc.active}


@router.put("/inventory/locations/{location_id}")
async def update_location(
    location_id: str,
    payload: dict,
    current_user=Depends(require_any_capability("inventory:manage_catalog", "admin:user_management")),
    db: AsyncSession = Depends(get_db),
):
    lid = _uuid(location_id, "location_id")
    loc = (await db.execute(select(Location).where(Location.id == lid))).scalars().first()
    if not loc:
        raise AppError(404, "LOCATION_NOT_FOUND", "Không tìm thấy kho")
    if "name" in payload and payload["name"]:
        loc.name = str(payload["name"]).strip()
    if "active" in payload:
        loc.active = bool(payload["active"])
    await db.commit()
    await db.refresh(loc)
    return {"id": str(loc.id), "code": loc.code, "name": loc.name, "active": loc.active}


@router.delete("/inventory/locations/{location_id}")
async def delete_location(
    location_id: str,
    current_user=Depends(require_any_capability("inventory:manage_catalog", "admin:user_management")),
    db: AsyncSession = Depends(get_db),
):
    lid = _uuid(location_id, "location_id")
    loc = (await db.execute(select(Location).where(Location.id == lid))).scalars().first()
    if not loc:
        raise AppError(404, "LOCATION_NOT_FOUND", "Không tìm thấy kho")
    loc.active = False
    await db.commit()
    return {"status": "deleted", "id": str(loc.id)}


@router.get("/inventory/balances")
async def list_balances(
    current_user=Depends(require_any_capability(*_VIEW_CATALOG)),
    db: AsyncSession = Depends(get_db),
    location_id: str | None = None,
    item_id: str | None = None,
    limit: int = 100,
    cursor: str | None = None,
):
    """Tồn kho theo (location, item). Paginate bằng limit + opaque cursor."""
    import uuid as _uuid_mod

    limit = clamp_limit(limit, default=100)

    def _coerce_uuid(raw: object) -> uuid.UUID:
        return _uuid_mod.UUID(str(raw))

    spec = KeysetSpec(
        columns=(Balance.location_id, Balance.item_id),
        descending=(False, False),
        keys=("location_id", "item_id"),
        attrs=("location_id", "item_id"),
        coerce=(_coerce_uuid, _coerce_uuid),
    )
    stmt = select(Balance).order_by(Balance.location_id, Balance.item_id)
    allowed_location_ids = await get_accessible_location_ids(db, current_user)
    if allowed_location_ids is not None:
        stmt = stmt.where(Balance.location_id.in_(allowed_location_ids))
    if location_id:
        stmt = stmt.where(Balance.location_id == _uuid(location_id, "location_id"))
    if item_id:
        stmt = stmt.where(Balance.item_id == _uuid(item_id, "item_id"))
    stmt = apply_keyset(stmt, spec, decode_cursor(cursor))
    rows = (await db.execute(stmt.limit(limit + 1))).scalars().all()
    page, next_cursor = rows[:limit], None
    if len(rows) > limit:
        next_cursor = encode_cursor(build_cursor_payload(spec, page[-1]))
    return {
        "balances": [
            {
                "location_id": str(b.location_id),
                "item_id": str(b.item_id),
                "quantity": str(b.quantity),
                "reserved_quantity": str(getattr(b, "reserved_quantity", 0) or 0),
                "available_quantity": str(b.available_quantity),
                "version": b.version,
            }
            for b in page
        ],
        "next_cursor": next_cursor,
        "limit": limit,
    }


@router.get("/inventory/assets")
async def list_assets(
    current_user=Depends(require_any_capability(*_VIEW_ASSETS)),
    db: AsyncSession = Depends(get_db),
    serial: str | None = None,
    location_id: str | None = None,
    limit: int = 100,
    cursor: str | None = None,
):
    limit = clamp_limit(limit, default=100)

    spec = KeysetSpec(
        columns=(Asset.serial, Asset.id),
        descending=(False, False),
        keys=("serial", "id"),
        attrs=("serial", "id"),
        coerce=(str, lambda raw: _uuid(raw, "cursor.id")),
    )
    stmt = select(Asset).order_by(Asset.serial, Asset.id)
    allowed_location_ids = await get_accessible_location_ids(db, current_user)
    if allowed_location_ids is not None:
        stmt = stmt.where(Asset.location_id.in_(allowed_location_ids))
    if serial:
        stmt = stmt.where(Asset.serial == serial)
    if location_id:
        stmt = stmt.where(Asset.location_id == _uuid(location_id, "location_id"))
    stmt = apply_keyset(stmt, spec, decode_cursor(cursor))
    rows = (await db.execute(stmt.limit(limit + 1))).scalars().all()
    page, next_cursor = rows[:limit], None
    if len(rows) > limit:
        next_cursor = encode_cursor(build_cursor_payload(spec, page[-1]))
    return {
        "assets": [
            {
                "id": str(a.id),
                "item_id": str(a.item_id),
                "serial": a.serial,
                "location_id": str(a.location_id),
                "assignee_demo": a.assignee_demo,
                "status": a.status,
            }
            for a in page
        ],
        "next_cursor": next_cursor,
        "limit": limit,
    }


@router.get("/inventory/movements")
async def list_movements(
    current_user=Depends(require_any_capability(*_VIEW_CATALOG)),
    db: AsyncSession = Depends(get_db),
    request_id: str | None = None,
    location_id: str | None = None,
    limit: int = 100,
    cursor: str | None = None,
):
    limit = clamp_limit(limit, default=100)

    spec = KeysetSpec(
        columns=(Movement.posted_at, Movement.id),
        descending=(True, False),
        keys=("posted_at", "id"),
        attrs=("posted_at", "id"),
        coerce=(coerce_timestamp, lambda raw: _uuid(raw, "cursor.id")),
    )
    stmt = select(Movement).order_by(Movement.posted_at.desc(), Movement.id)
    # IDOR: chỉ cho thấy movement trong các location user có quyền truy cập.
    allowed_location_ids = await get_accessible_location_ids(db, current_user)
    if allowed_location_ids is not None:
        stmt = stmt.where(Movement.location_id.in_(allowed_location_ids))
    if request_id:
        stmt = stmt.where(Movement.request_id == _uuid(request_id, "request_id"))
    if location_id:
        stmt = stmt.where(Movement.location_id == _uuid(location_id, "location_id"))
    stmt = apply_keyset(stmt, spec, decode_cursor(cursor))
    rows = (await db.execute(stmt.limit(limit + 1))).scalars().all()
    page, next_cursor = rows[:limit], None
    if len(rows) > limit:
        next_cursor = encode_cursor(build_cursor_payload(spec, page[-1]))
    return {
        "movements": [
            {
                "id": str(m.id),
                "request_id": str(m.request_id),
                "line_id": str(m.line_id),
                "item_id": str(m.item_id),
                "location_id": str(m.location_id),
                "quantity_signed": str(m.quantity_signed),
                "posted_at": m.posted_at.isoformat() if m.posted_at else None,
            }
            for m in page
        ],
        "next_cursor": next_cursor,
        "limit": limit,
    }



@router.post("/inventory/movements/{movement_id}/reverse", status_code=201)
async def reverse_movement(
    movement_id: str,
    body: MovementReverseInput,
    current_user=Depends(require_any_capability("inventory:approve_request", "inventory:manage_catalog")),
    db: AsyncSession = Depends(get_db),
):
    """Đảo chiều một LotMovement (không sửa entry cũ — tạo movement mới).

    Tạo một LotMovement mới với quantity_signed ngược chiều, phản ánh
    sự kiện reversed_from của movement gốc.
    """
    from app.services.inventory_reversal import reverse_movement_service

    result = await reverse_movement_service(
        user_id=current_user.id,
        movement_id=movement_id,
        reason=body.reason,
        db=db,
        approve_caps=_APPROVE_CAPS,
    )
    await _audit(db, current_user.id, "reverse", result, {"reversed_from": movement_id})
    await _outbox(db, "inventory.movement.reversed", result, {"reversed_from": movement_id})
    return result




@router.get("/inventory/requests")
async def list_requests(
    current_user=Depends(require_any_capability(*_REQUEST_READ_CAPS)),
    db: AsyncSession = Depends(get_db),
    status: str | None = None,
    mine: bool = False,
    limit: int = 100,
    cursor: str | None = None,
):
    limit = clamp_limit(limit, default=100)

    spec = KeysetSpec(
        columns=(InventoryRequest.created_at, InventoryRequest.id),
        descending=(True, False),
        keys=("created_at", "id"),
        attrs=("created_at", "id"),
        coerce=(coerce_timestamp, lambda raw: _uuid(raw, "cursor.id")),
    )
    stmt = select(InventoryRequest).order_by(
        InventoryRequest.created_at.desc(), InventoryRequest.id
    )
    if status:
        stmt = stmt.where(InventoryRequest.status == status)
    caps = await get_user_capabilities(db, current_user.id)
    # Auditors have inventory:review, not approval. They may list read-only
    # requests inside their location scope, just as GET by id permits.
    if mine or not ({"inventory:approve_request", "inventory:review"} & set(caps)):
        stmt = stmt.where(InventoryRequest.maker_id == current_user.id)
    else:
        accessible_locations = await get_accessible_location_ids(db, current_user)
        if accessible_locations is not None:
            stmt = stmt.where(
                or_(
                    InventoryRequest.source_id.in_(accessible_locations),
                    InventoryRequest.dest_id.in_(accessible_locations),
                )
            )
    stmt = apply_keyset(stmt, spec, decode_cursor(cursor))
    rows = (await db.execute(stmt.limit(limit + 1))).scalars().all()
    page, next_cursor = rows[:limit], None
    if len(rows) > limit:
        next_cursor = encode_cursor(build_cursor_payload(spec, page[-1]))

    req_ids = [r.id for r in page]
    lines_by_req: dict[uuid.UUID, list[dict]] = {r.id: [] for r in page}
    if req_ids:
        line_rows = (
            await db.execute(
                select(InventoryRequestLine).where(
                    InventoryRequestLine.request_id.in_(req_ids)
                )
            )
        ).scalars().all()
        for lr in line_rows:
            lines_by_req[lr.request_id].append({
                "item_id": str(lr.item_id),
                "quantity": str(lr.quantity),
                "direction": getattr(lr, "direction", "increase"),
                "serial": lr.serial,
                "unit_price": str(lr.unit_price) if lr.unit_price is not None else None,
                "line_total": _line_total(lr.quantity, lr.unit_price),
                "lot_no": getattr(lr, "lot_no", None),
                "expiry_date": lr.expiry_date.isoformat() if getattr(lr, "expiry_date", None) else None,
            })

    return {
        "requests": [_req_out(r, lines_by_req.get(r.id, [])) for r in page],
        "next_cursor": next_cursor,
        "limit": limit,
    }


@router.get("/inventory/requests/{request_id}")
async def get_request(
    request_id: str,
    current_user=Depends(require_any_capability(*_REQUEST_READ_CAPS)),
    db: AsyncSession = Depends(get_db),
):
    req = await _load_request_for_read(db, request_id, current_user)
    return _req_out(req, await _load_lines(db, req.id))


@router.delete("/inventory/requests/{request_id}")
async def delete_request(
    request_id: str,
    user=Depends(require_any_capability("inventory:create_request")),
    db: AsyncSession = Depends(get_db),
):
    rid = _uuid(request_id, "request_id")
    req = (await db.execute(select(InventoryRequest).where(InventoryRequest.id == rid))).scalars().first()
    if not req:
        raise AppError(404, "REQUEST_NOT_FOUND", "Không tìm thấy phiếu yêu cầu")
    # S5 (IDOR) — chỉ chủ sở hữu phiếu mới được xoá; user khác dù có quyền
    # `inventory:create_request` cũng không được xoá phiếu nháp của người ta.
    if str(req.maker_id) != str(user.id):
        raise AppError(403, "FORBIDDEN", "Chỉ người lập phiếu mới được xoá phiếu này.")
    if req.status != "draft":
        raise AppError(409, "CANNOT_DELETE_NON_DRAFT", "Chỉ có thể xoá phiếu ở trạng thái nháp (draft)")
    lines = (await db.execute(select(InventoryRequestLine).where(InventoryRequestLine.request_id == rid))).scalars().all()
    for line in lines:
        await db.delete(line)
    await db.delete(req)
    await db.commit()
    return {"status": "deleted", "id": str(rid)}



# --------------------------------------------------------------------------
# Writes — create / submit
# --------------------------------------------------------------------------
@router.post("/inventory/requests", status_code=201)
async def create_request(
    payload: dict,
    request: Request,
    user=Depends(require_any_capability("inventory:create_request")),
    db: AsyncSession = Depends(get_db),
):
    key = _require_key(request)
    kind = str(payload.get("kind", "")).lower()
    if kind not in _KINDS:
        raise AppError(422, "INVALID_KIND", f"kind phải thuộc {_KINDS}, nhận {kind!r}")
    cached = _replay(key, payload)
    if cached is not None:
        return cached

    src = _uuid(payload["source_id"], "source_id") if payload.get("source_id") else None
    dst = _uuid(payload["dest_id"], "dest_id") if payload.get("dest_id") else None
    if kind == "transfer" and (src is None or dst is None):
        raise AppError(422, "DESTINATION_REQUIRED", "transfer yêu cầu source_id và dest_id")

    # A maker may only create a request that touches locations in their branch
    # scope.  Checking both sides of a transfer prevents using a permitted
    # source location as a bridge into an unauthorized branch.
    if src is not None:
        await _require_location_scope(db, user, src)
    if dst is not None:
        await _require_location_scope(db, user, dst)

    # Chống spam mở hàng loạt phiếu nháp làm rác DB: tối đa MAX_OPEN_DRAFTS_PER_USER phiếu draft/maker (nếu được kích hoạt)
    if MAX_OPEN_DRAFTS_PER_USER > 0:
        open_drafts_count = (
            await db.execute(
                select(func.count(InventoryRequest.id)).where(
                    InventoryRequest.maker_id == user.id,
                    InventoryRequest.status == "draft",
                )
            )
        ).scalar() or 0
        if open_drafts_count >= MAX_OPEN_DRAFTS_PER_USER:
            raise AppError(
                422,
                "DRAFT_QUOTA_EXCEEDED",
                f"Bạn đã đạt giới hạn tối đa {MAX_OPEN_DRAFTS_PER_USER} phiếu nháp chưa hoàn tất. Vui lòng nộp duyệt hoặc xóa bớt phiếu cũ.",
            )

    invoice_no = str(payload.get("invoice_no", "")).strip() or None
    raw_sub_kind = str(payload.get("sub_kind", "")).strip().lower() or None
    reason = str(payload.get("reason", "")).strip() or None
    if kind == "issue":
        sub_kind = raw_sub_kind or "sale"
        if sub_kind not in _SUB_KINDS:
            raise AppError(422, "INVALID_SUB_KIND", f"sub_kind phải thuộc {_SUB_KINDS}, nhận {sub_kind!r}")
        if sub_kind in ("spoilage", "internal") and not reason:
            raise AppError(422, "MISSING_REASON", f"Xuất kho loại '{sub_kind}' bắt buộc phải có lý do (reason)")
        if sub_kind == "transfer" and (src is None or dst is None):
            raise AppError(422, "DESTINATION_REQUIRED", "Xuất chuyển kho yêu cầu source_id và dest_id")
    elif kind == "transfer":
        sub_kind = raw_sub_kind or "transfer"
    else:
        sub_kind = raw_sub_kind

    received_at_in = payload.get("received_at") or payload.get("received_date")
    received_at = _parse_date(received_at_in, "received_at") if received_at_in else _now()

    req = InventoryRequest(
        id=uuid.uuid4(),
        kind=kind,
        status="draft",
        maker_id=user.id,
        created_by=user.id,
        source_id=src,
        dest_id=dst,
        reason=reason,
        supplier=str(payload.get("supplier", "")).strip() or None,
        invoice_no=invoice_no,
        sub_kind=sub_kind,
        received_at=received_at,
        version=1,
    )
    db.add(req)
    await db.flush()

    lines_in = payload.get("lines") or []
    if not isinstance(lines_in, list):
        raise AppError(422, "INVALID_LINES", "lines phải là danh sách")
    receipt_day = _hanoi_today()
    for ln in lines_in:
        if not isinstance(ln, dict):
            raise AppError(422, "INVALID_LINES", f"line không hợp lệ: {ln!r}")
        item_id = await _resolve_item_id(db, ln)
        qty = _qty(ln.get("quantity", "0"))
        if qty <= _ZERO:
            raise AppError(
                422, "INVALID_QUANTITY", f"quantity phải > 0, nhận {ln.get('quantity')!r}"
            )
        direction = str(ln.get("direction", "increase")).lower()
        if direction not in {"increase", "decrease"}:
            raise AppError(
                422,
                "INVALID_ADJUSTMENT_DIRECTION",
                "direction phải là increase hoặc decrease",
            )
        if kind != "adjustment" and direction != "increase":
            raise AppError(
                422,
                "INVALID_ADJUSTMENT_DIRECTION",
                "Chỉ phiếu adjustment mới có direction=decrease",
            )
        serial = str(ln["serial"]).strip() if ln.get("serial") else None
        # Phiếu nhập trà sữa (SRS §3.2): NCC, đơn giá/thành tiền,
        # số lô và HSD. HSD không được trước ngày nhận.
        unit = str(ln.get("unit", "")).strip() or None
        conv_val = ln.get("conversion_rate")
        conversion_rate = Decimal(str(conv_val)) if conv_val is not None else None
        if conversion_rate is not None and conversion_rate <= _ZERO:
            raise AppError(422, "INVALID_CONVERSION_RATE", "Hệ số quy đổi conversion_rate phải > 0")

        unit_price = _parse_money(ln.get("unit_price")) if kind == "receipt" else None
        lot_no = str(ln.get("lot_no", "")).strip() or None
        expiry = _parse_expiry(ln.get("expiry_date")) if kind == "receipt" else None
        if kind == "receipt" and expiry is not None and expiry < receipt_day:
            raise AppError(422, "EXPIRED_LOT", f"Lô {lot_no or ''} đã hết hạn ngày {expiry.isoformat()}")
        db.add(
            InventoryRequestLine(
                id=uuid.uuid4(), request_id=req.id, item_id=item_id,
                quantity=qty, direction=direction, serial=serial,
                unit=unit, conversion_rate=conversion_rate,
                unit_price=unit_price, lot_no=lot_no, expiry_date=expiry,
            )
        )
    await _audit(db, user.id, "inventory.request.created", req, {"status": None})
    await _outbox(db, "inventory.request.created", req, {})
    await db.commit()
    await db.refresh(req)
    body = _req_out(req, await _load_lines(db, req.id))
    idempotency.remember(db, key, idempotency.payload_hash(payload), 201, body)
    return body


@router.post("/inventory/requests/{request_id}/submit")
async def submit_request(
    request_id: str,
    request: Request,
    user=Depends(require_any_capability("inventory:create_request")),
    db: AsyncSession = Depends(get_db),
):
    req = await _load_request(db, request_id)
    if str(req.maker_id) != str(user.id):
        raise AppError(403, "FORBIDDEN", "Chỉ maker mới được submit phiếu của mình")
    if req.status not in ("draft", "returned"):
        raise AppError(409, "STATE_CONFLICT", f"Không thể gửi phiếu khi đang ở trạng thái {req.status}.")
    _check_if_match(request, req.version)

    # Lock the request before reserving stock, so a duplicate concurrent submit
    # cannot reserve the same draft twice.  The source balances are locked below.
    if req.kind in ("issue", "transfer") and req.source_id is not None:
        req = (
            await db.execute(
                select(InventoryRequest)
                .where(InventoryRequest.id == req.id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        ).scalar_one()
        if req.status not in ("draft", "returned"):
            raise AppError(409, "STATE_CONFLICT", f"Không thể gửi phiếu khi đang ở trạng thái {req.status}.")

    lines = (
        await db.execute(
            select(InventoryRequestLine).where(InventoryRequestLine.request_id == req.id)
        )
    ).scalars().all()

    # Reserve inventory for issue / transfer
    if req.kind in ("issue", "transfer") and req.source_id is not None:
        need: dict = {}
        for ln in lines:
            need[ln.item_id] = need.get(ln.item_id, _ZERO) + Decimal(str(ln.quantity))

        # Validate the entire reservation while every source row is locked.
        # Reserving a subset would let an unfulfillable request enter the
        # checker queue and would make its later release/approval ambiguous.
        source_balances = await _lock_balances(
            db, {(req.source_id, item_id) for item_id in need}
        )
        for item_id in sorted(need, key=str):
            qty = need[item_id]
            bal = source_balances.get((req.source_id, item_id))
            available = (
                max(
                    _ZERO,
                    Decimal(str(bal.quantity))
                    - Decimal(str(getattr(bal, "reserved_quantity", 0) or 0)),
                )
                if bal is not None
                else _ZERO
            )
            if available < qty:
                raise AppError(
                    409,
                    "INSUFFICIENT_STOCK",
                    "không đủ tồn khả dụng tại kho nguồn để đặt trước toàn bộ phiếu",
                )

        # Kiểm tra hàng quá hạn đối với loại xuất sale / internal
        if req.kind == "issue" and getattr(req, "sub_kind", None) in ("sale", "internal"):
            today = _hanoi_today()
            for item_id in sorted(need, key=str):
                qty = need[item_id]
                lots_rows = (
                    await db.execute(
                        select(LotBalance).where(
                            LotBalance.location_id == req.source_id,
                            LotBalance.item_id == item_id,
                            LotBalance.quantity > _ZERO,
                        )
                    )
                ).scalars().all()
                if lots_rows:
                    non_expired = sum(
                        (Decimal(str(lot.quantity)) for lot in lots_rows if lot.expiry_date is None or lot.expiry_date >= today),
                        Decimal("0"),
                    )
                    if non_expired < qty:
                        item_obj = await db.get(Item, item_id)
                        name = item_obj.name if item_obj else str(item_id)
                        raise AppError(
                            422,
                            "EXPIRED_LOT_CANNOT_BE_USED",
                            f"Nguyên liệu '{name}' chỉ còn lô đã hết hạn sử dụng. Không thể xuất loại '{req.sub_kind}', vui lòng lập phiếu xuất hủy (spoilage).",
                        )

        for item_id in sorted(need, key=str):
            bal = source_balances[(req.source_id, item_id)]
            bal.reserved_quantity = (
                Decimal(str(getattr(bal, "reserved_quantity", 0) or 0)) + need[item_id]
            )

    before = {"status": req.status, "version": req.version}
    req.status = "submitted"
    req.version += 1
    req.submitted_at = _now()
    await _audit(db, user.id, "inventory.request.submitted", req, before)
    await _outbox(db, "inventory.request.submitted", req, {})
    await db.commit()
    await db.refresh(req)
    await broadcast_approval_event(
        action="submitted",
        request_id=str(req.id),
        kind="inventory",
        status="submitted",
        message=f"Phiếu kho {req.kind} ({req.id}) đã được gửi duyệt",
        meta={"sub_kind": req.kind, "maker_id": str(user.id)},
    )
    return _req_out(req, await _load_lines(db, req.id))


async def _sync_inbound_items_to_open_stocktakes(
    db: AsyncSession,
    location_id: uuid.UUID | None,
    item_totals: dict[uuid.UUID, Decimal],
) -> None:
    """Tự động đồng bộ số lượng hàng nhập đa dòng vào ca kiểm kê đang mở (SRS §3.3)."""
    if location_id is None or not item_totals:
        return
    open_stocktakes = (
        await db.execute(
            select(Stocktake).where(
                Stocktake.location_id == location_id,
                Stocktake.status == "open",
            )
        )
    ).scalars().all()
    for ost in open_stocktakes:
        for item_id, quantity in item_totals.items():
            if quantity <= _ZERO:
                continue
            st_line = (
                await db.execute(
                    select(StocktakeLine).where(
                        StocktakeLine.stocktake_id == ost.id,
                        StocktakeLine.item_id == item_id,
                    )
                )
            ).scalars().first()
            if st_line:
                st_line.received_qty = Decimal(str(st_line.received_qty or 0)) + quantity
                st_line.theoretical_qty = (
                    Decimal(str(st_line.opening_qty or 0))
                    + st_line.received_qty
                    - Decimal(str(st_line.used_qty or 0))
                )
                if ost.shift_code:
                    st_line.book_qty = st_line.theoretical_qty
                st_line.variance = Decimal(str(st_line.counted_qty or 0)) - st_line.book_qty
            else:
                db.add(
                    StocktakeLine(
                        id=uuid.uuid4(),
                        stocktake_id=ost.id,
                        item_id=item_id,
                        book_qty=quantity if ost.shift_code else _ZERO,
                        opening_qty=_ZERO,
                        received_qty=quantity,
                        used_qty=_ZERO,
                        theoretical_qty=quantity,
                        counted_qty=_ZERO,
                        variance=-quantity if ost.shift_code else _ZERO,
                    )
                )
        await db.flush()


async def _sync_inbound_to_open_stocktakes(
    db: AsyncSession,
    location_id: uuid.UUID | None,
    item_id: uuid.UUID,
    quantity: Decimal,
) -> None:
    """Đồng bộ một nguyên liệu vào ca kiểm kê đang mở."""
    await _sync_inbound_items_to_open_stocktakes(db, location_id, {item_id: quantity})


async def _sync_outbound_items_to_open_stocktakes(
    db: AsyncSession,
    location_id: uuid.UUID | None,
    item_totals: dict[uuid.UUID, Decimal],
) -> None:
    """Tự động đồng bộ số lượng hàng xuất vào ca kiểm kê đang mở (SRS §3.3).
    
    Cộng dồn vào used_qty, tính lại theoretical_qty và variance.
    """
    if location_id is None or not item_totals:
        return
    open_stocktakes = (
        await db.execute(
            select(Stocktake).where(
                Stocktake.location_id == location_id,
                Stocktake.status == "open",
            )
        )
    ).scalars().all()
    for ost in open_stocktakes:
        for item_id, quantity in item_totals.items():
            if quantity <= _ZERO:
                continue
            st_line = (
                await db.execute(
                    select(StocktakeLine).where(
                        StocktakeLine.stocktake_id == ost.id,
                        StocktakeLine.item_id == item_id,
                    )
                )
            ).scalars().first()
            if st_line:
                st_line.used_qty = Decimal(str(st_line.used_qty or 0)) + quantity
                st_line.theoretical_qty = (
                    Decimal(str(st_line.opening_qty or 0))
                    + Decimal(str(st_line.received_qty or 0))
                    - st_line.used_qty
                )
                if ost.shift_code:
                    st_line.book_qty = st_line.theoretical_qty
                st_line.variance = Decimal(str(st_line.counted_qty or 0)) - st_line.book_qty
            else:
                db.add(
                    StocktakeLine(
                        id=uuid.uuid4(),
                        stocktake_id=ost.id,
                        item_id=item_id,
                        book_qty=-quantity if ost.shift_code else _ZERO,
                        opening_qty=_ZERO,
                        received_qty=_ZERO,
                        used_qty=quantity,
                        theoretical_qty=-quantity,
                        counted_qty=_ZERO,
                        variance=quantity if ost.shift_code else _ZERO,
                    )
                )
        await db.flush()


async def _deduct_stock_fefo(
    db: AsyncSession,
    location_id: uuid.UUID,
    item: Item,
    need_qty: Decimal,
    sub_kind: str,
    today: date,
) -> list[tuple[LotBalance, Decimal, Decimal]]:
    """Trừ tồn kho theo thuật toán FEFO (HSD sớm trước, NULL cuối cùng).
    
    Khóa dòng LotBalance bằng with_for_update().
    Chặn xuất lô hết hạn nếu sub_kind != 'spoilage'.
    Tự động seed lô TON-DAU-KY nếu tồn Balance > 0 nhưng chưa có LotBalance.
    Trả về danh sách các lượt trừ: (lot_obj, take_qty, unit_cost).
    """
    stmt = (
        select(LotBalance)
        .where(
            LotBalance.location_id == location_id,
            LotBalance.item_id == item.id,
            LotBalance.quantity > _ZERO,
        )
        .order_by(
            LotBalance.expiry_date.asc().nulls_last(),
            LotBalance.created_at.asc(),
        )
        .with_for_update()
    )
    lots = list((await db.execute(stmt)).scalars().all())

    # Fallback cho dữ liệu cũ: nếu chưa có LotBalance nhưng Balance > 0
    if not lots:
        bal = (
            await db.execute(
                select(Balance)
                .where(Balance.location_id == location_id, Balance.item_id == item.id)
                .with_for_update()
            )
        ).scalar_one_or_none()
        if bal and Decimal(str(bal.quantity)) > _ZERO:
            fallback_lot = LotBalance(
                id=uuid.uuid4(),
                location_id=location_id,
                item_id=item.id,
                lot_no="TON-DAU-KY-CHUA-KIEM-DINH",
                expiry_date=None,  # F&B policy: không gắn hạn 2099 ảo; xếp nulls_last để ưu tiên xuất lô có HSD rõ ràng
                quantity=Decimal(str(bal.quantity)),
                unit_cost=Decimal(str(item.cost_price or 0)),
            )
            db.add(fallback_lot)
            await db.flush()
            lots = [fallback_lot]

    valid_lots: list[LotBalance] = []
    expired_qty = Decimal("0")
    for lot in lots:
        is_expired = lot.expiry_date is not None and lot.expiry_date < today
        if is_expired:
            if sub_kind == "spoilage":
                valid_lots.append(lot)
            else:
                expired_qty += Decimal(str(lot.quantity))
        else:
            valid_lots.append(lot)

    available_qty = sum((Decimal(str(lot.quantity)) for lot in valid_lots), Decimal("0"))
    if available_qty < need_qty:
        item_name = item.name or item.sku
        msg = f"Không đủ tồn kho khả dụng cho nguyên liệu '{item_name}': cần {need_qty}, còn {available_qty}."
        if expired_qty > _ZERO and sub_kind != "spoilage":
            msg += f" (Có {expired_qty} đã hết hạn sử dụng, vui lòng xuất bằng loại 'spoilage' - xuất hủy)."
        raise AppError(422, "INSUFFICIENT_STOCK", msg)

    deductions: list[tuple[LotBalance, Decimal, Decimal]] = []
    remaining = need_qty
    for lot in valid_lots:
        if remaining <= _ZERO:
            break
        lot_qty = Decimal(str(lot.quantity))
        take = min(lot_qty, remaining)
        lot.quantity = lot_qty - take
        lot_cost = Decimal(str(lot.unit_cost if lot.unit_cost is not None else (item.cost_price or 0)))
        deductions.append((lot, take, lot_cost))
        remaining -= take

    return deductions


@router.post("/inventory/requests/{request_id}/approve")
async def approve_request(
    request_id: str,
    request: Request,
    payload: ApprovalInput | None = None,
    # Authenticate before checking the maker/checker invariant.  Requiring an
    # approval capability here would reject a maker before we could report the
    # domain error that explains why self-approval is forbidden.
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Duyệt + post trong một transaction (docs/06 cấm 202 cho approve)."""
    key = _require_key(request)
    req = await _load_request(db, request_id)
    # Branch-scope guard: checker must have access to source/dest locations.
    if req.source_id is not None:
        await _require_location_scope(db, user, req.source_id)
    if req.dest_id is not None:
        await _require_location_scope(db, user, req.dest_id)
    cached = _replay(key, {"approve": str(req.id)})
    if cached is not None:
        return cached

    # A maker receives the domain-specific A1 result even if their normal
    # role has no approval capability.  The final state is still rechecked
    # under the row lock below before any posting can occur.
    if str(req.maker_id) == str(user.id):
        raise AppError(403, "SELF_APPROVAL_FORBIDDEN", "Bạn không được tự duyệt phiếu của chính mình.")

    caps = await get_user_capabilities(db, user.id)
    if "inventory:approve_request" not in caps:
        raise AppError(403, "FORBIDDEN", "Bạn không có quyền phê duyệt phiếu kho.")

    # Every final decision takes the same row lock.  Reject/return use this
    # exact pattern, so a losing action observes the final state and cannot
    # release reservations after an approve has posted movements.
    req = (
        await db.execute(
            select(InventoryRequest)
            .where(InventoryRequest.id == req.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()
    if req is None:
        raise AppError(404, "NOT_FOUND", "Phiếu không tồn tại")
    # Invariant 1 — maker không tự duyệt, kể cả admin. Recheck after the
    # final-decision lock to keep the invariant adjacent to the mutation.
    if str(req.maker_id) == str(user.id):
        raise AppError(403, "SELF_APPROVAL_FORBIDDEN", "Bạn không được tự duyệt phiếu của chính mình.")
    if req.status != "submitted":
        raise AppError(409, "STATE_CONFLICT", f"Không thể duyệt phiếu khi đang ở trạng thái {req.status}.")
    _check_if_match(request, req.version)

    lines = (
        await db.execute(
            select(InventoryRequestLine).where(InventoryRequestLine.request_id == req.id)
        )
    ).scalars().all()

    # Validate and lock custody records before creating a single movement.
    serial_assets = await _lock_and_validate_serial_assets(db, req, lines)
    balances = await _lock_balances(db, _affected_balance_keys(req, lines))

    # I1: kiểm tra đủ tồn TRƯỚC khi ghi movement nào.
    if req.kind in ("issue", "transfer") and req.source_id is not None:
        need: dict = {}
        for ln in lines:
            need[ln.item_id] = need.get(ln.item_id, _ZERO) + Decimal(str(ln.quantity))
        for item_id in sorted(need, key=str):
            qty = need[item_id]
            bal = balances.get((req.source_id, item_id))
            have = Decimal(str(bal.quantity)) if bal else _ZERO
            if have < qty:
                raise AppError(409, "INSUFFICIENT_STOCK", "Không đủ tồn kho ở kho nguồn.")
            reserved = (
                Decimal(str(getattr(bal, "reserved_quantity", 0) or 0))
                if bal is not None
                else _ZERO
            )
            if reserved < qty:
                raise AppError(
                    409,
                    "RESERVATION_MISMATCH",
                    "phiếu không còn đủ tồn đặt trước để được phê duyệt",
                )

    # A negative stocktake adjustment is stored as a positive quantity plus an
    # explicit direction.  Confirm every reducing line can be posted before
    # any movement is written, preserving all-or-nothing semantics.
    if req.kind == "adjustment":
        for ln in lines:
            if getattr(ln, "direction", "increase") != "decrease":
                continue
            target = req.dest_id or req.source_id
            bal = balances.get((target, ln.item_id)) if target is not None else None
            if bal is None or Decimal(str(bal.quantity)) < Decimal(str(ln.quantity)):
                raise AppError(409, "INSUFFICIENT_STOCK", "Phiếu điều chỉnh giảm vượt quá tồn kho hiện có.")

    amount = sum(
        Decimal(str(line.quantity)) for line in lines
    )
    verify_supervisor_pin(
        payload.supervisor_pin if payload else None,
        settings,
        required=req.kind in ("issue", "transfer") and amount >= Decimal("50"),
        user=user,
    )



    now = _now()
    today = _hanoi_today()
    item_cache: dict[uuid.UUID, Item] = {}

    async def _get_item_obj(iid: uuid.UUID) -> Item:
        if iid not in item_cache:
            it = await db.get(Item, iid)
            if not it:
                raise AppError(422, "ITEM_NOT_FOUND", f"Không tìm thấy item {iid}")
            item_cache[iid] = it
        return item_cache[iid]

    transfer_dest_items: dict[uuid.UUID, Decimal] = {}
    outbound_sync_items: dict[uuid.UUID, Decimal] = {}

    for ln in lines:
        qty = Decimal(str(ln.quantity))
        item_obj = await _get_item_obj(ln.item_id)
        if req.kind == "transfer" and req.source_id is not None and req.dest_id is not None:
            sub_k = req.sub_kind or "transfer"
            deductions = await _deduct_stock_fefo(db, req.source_id, item_obj, qty, sub_k, today)
            src_mv_id = uuid.uuid4()
            dst_mv_id = uuid.uuid4()
            total_cost = sum(((take_qty * unit_cost).quantize(Decimal("0.01")) for _, take_qty, unit_cost in deductions), Decimal("0"))
            avg_unit_cost = (total_cost / qty).quantize(Decimal("0.01")) if qty > _ZERO else Decimal("0")

            src_mv = Movement(
                id=src_mv_id, request_id=req.id, line_id=ln.id,
                item_id=ln.item_id, location_id=req.source_id,
                quantity_signed=-qty, posted_at=now,
                sub_kind="transfer", unit_cost=avg_unit_cost, cost_amount=total_cost,
            )
            dst_mv = Movement(
                id=dst_mv_id, request_id=req.id, line_id=ln.id,
                item_id=ln.item_id, location_id=req.dest_id,
                quantity_signed=qty, posted_at=now,
                sub_kind="transfer", unit_cost=avg_unit_cost, cost_amount=total_cost,
            )
            db.add(src_mv)
            db.add(dst_mv)
            await db.flush()

            for lot, take_qty, unit_cost in deductions:
                cost_amt = (take_qty * unit_cost).quantize(Decimal("0.01"))
                # Ghi nhận LotMovement kho nguồn
                db.add(
                    LotMovement(
                        id=uuid.uuid4(),
                        movement_id=src_mv_id,
                        request_id=req.id,
                        line_id=ln.id,
                        item_id=ln.item_id,
                        location_id=req.source_id,
                        lot_no=lot.lot_no,
                        expiry_date=lot.expiry_date,
                        quantity_signed=-take_qty,
                        unit_cost=unit_cost,
                        cost_amount=cost_amt,
                        sub_kind="transfer",
                    )
                )

                # Cộng LotBalance kho đích với cùng số lô và HSD
                dst_lot = (
                    await db.execute(
                        select(LotBalance).where(
                            LotBalance.location_id == req.dest_id,
                            LotBalance.item_id == ln.item_id,
                            LotBalance.lot_no == lot.lot_no,
                            LotBalance.expiry_date == lot.expiry_date,
                        ).with_for_update()
                    )
                ).scalar_one_or_none()
                if dst_lot:
                    dst_lot.quantity = Decimal(str(dst_lot.quantity)) + take_qty
                    if unit_cost > Decimal("0"):
                        dst_lot.unit_cost = unit_cost
                    dst_lot.updated_at = now
                else:
                    db.add(
                        LotBalance(
                            id=uuid.uuid4(),
                            location_id=req.dest_id,
                            item_id=ln.item_id,
                            lot_no=lot.lot_no,
                            expiry_date=lot.expiry_date,
                            quantity=take_qty,
                            unit_cost=unit_cost,
                            created_at=now,
                            updated_at=now,
                        )
                    )

                # Ghi nhận LotMovement kho đích
                db.add(
                    LotMovement(
                        id=uuid.uuid4(),
                        movement_id=dst_mv_id,
                        request_id=req.id,
                        line_id=ln.id,
                        item_id=ln.item_id,
                        location_id=req.dest_id,
                        lot_no=lot.lot_no,
                        expiry_date=lot.expiry_date,
                        quantity_signed=take_qty,
                        unit_cost=unit_cost,
                        cost_amount=cost_amt,
                        sub_kind="transfer",
                    )
                )

            src = balances.get((req.source_id, ln.item_id))
            if src:
                src.quantity = Decimal(str(src.quantity)) - qty
                src.reserved_quantity = (
                    Decimal(str(getattr(src, "reserved_quantity", 0) or 0)) - qty
                )
            dst = balances.get((req.dest_id, ln.item_id))
            if dst:
                dst.quantity = Decimal(str(dst.quantity)) + qty
            else:
                dst = Balance(
                    location_id=req.dest_id,
                    item_id=ln.item_id,
                    quantity=qty,
                    reserved_quantity=Decimal(0),
                    version=1,
                )
                db.add(dst)
                balances[(req.dest_id, ln.item_id)] = dst
            transfer_dest_items[ln.item_id] = transfer_dest_items.get(ln.item_id, _ZERO) + qty

        elif req.kind == "issue" and req.source_id is not None:
            sub_k = req.sub_kind or "sale"
            deductions = await _deduct_stock_fefo(db, req.source_id, item_obj, qty, sub_k, today)
            src_mv_id = uuid.uuid4()
            total_cost = sum(((take_qty * unit_cost).quantize(Decimal("0.01")) for _, take_qty, unit_cost in deductions), Decimal("0"))
            avg_unit_cost = (total_cost / qty).quantize(Decimal("0.01")) if qty > _ZERO else Decimal("0")

            src_mv = Movement(
                id=src_mv_id, request_id=req.id, line_id=ln.id,
                item_id=ln.item_id, location_id=req.source_id,
                quantity_signed=-qty, posted_at=now,
                sub_kind=sub_k, unit_cost=avg_unit_cost, cost_amount=total_cost,
            )
            db.add(src_mv)
            await db.flush()

            for lot, take_qty, unit_cost in deductions:
                cost_amt = (take_qty * unit_cost).quantize(Decimal("0.01"))
                db.add(
                    LotMovement(
                        id=uuid.uuid4(),
                        movement_id=src_mv_id,
                        request_id=req.id,
                        line_id=ln.id,
                        item_id=ln.item_id,
                        location_id=req.source_id,
                        lot_no=lot.lot_no,
                        expiry_date=lot.expiry_date,
                        quantity_signed=-take_qty,
                        unit_cost=unit_cost,
                        cost_amount=cost_amt,
                        sub_kind=sub_k,
                    )
                )

            src = balances.get((req.source_id, ln.item_id))
            if src:
                src.quantity = Decimal(str(src.quantity)) - qty
                src.reserved_quantity = (
                    Decimal(str(getattr(src, "reserved_quantity", 0) or 0)) - qty
                )

            # Nếu là chuyển kho (issue sub_kind=transfer), tạo Movement inbound cho kho đích
            # và cập nhật Balance + LotBalance kho đích.
            if sub_k == "transfer" and req.dest_id is not None:
                dst_mv_id = uuid.uuid4()
                dst_mv = Movement(
                    id=dst_mv_id, request_id=req.id, line_id=ln.id,
                    item_id=ln.item_id, location_id=req.dest_id,
                    quantity_signed=qty, posted_at=now,
                    sub_kind="transfer", unit_cost=avg_unit_cost, cost_amount=total_cost,
                )
                db.add(dst_mv)
                await db.flush()

                # LotMovement cho kho đích (lô di chuyển theo hàng)
                for lot, take_qty, unit_cost in deductions:
                    cost_amt = (take_qty * unit_cost).quantize(Decimal("0.01"))
                    db.add(
                        LotMovement(
                            id=uuid.uuid4(),
                            movement_id=dst_mv_id,
                            request_id=req.id,
                            line_id=ln.id,
                            item_id=ln.item_id,
                            location_id=req.dest_id,
                            lot_no=lot.lot_no,
                            expiry_date=lot.expiry_date,
                            quantity_signed=take_qty,
                            unit_cost=unit_cost,
                            cost_amount=cost_amt,
                            sub_kind="transfer",
                        )
                    )
                    # Cập nhật LotBalance kho đích
                    stmt_dst_lot = (
                        select(LotBalance)
                        .where(
                            LotBalance.location_id == req.dest_id,
                            LotBalance.item_id == ln.item_id,
                            LotBalance.lot_no == lot.lot_no,
                        )
                        .with_for_update()
                    )
                    dst_lot_bal = (await db.execute(stmt_dst_lot)).scalar_one_or_none()
                    if dst_lot_bal:
                        dst_lot_bal.quantity = Decimal(str(dst_lot_bal.quantity)) + take_qty
                    else:
                        db.add(LotBalance(
                            id=uuid.uuid4(),
                            location_id=req.dest_id,
                            item_id=ln.item_id,
                            lot_no=lot.lot_no,
                            expiry_date=lot.expiry_date,
                            quantity=take_qty,
                            unit_cost=unit_cost,
                        ))

                # Cập nhật Balance kho đích
                dst_bal = balances.get((req.dest_id, ln.item_id))
                if dst_bal:
                    dst_bal.quantity = Decimal(str(dst_bal.quantity)) + qty
                else:
                    dst_bal = Balance(
                        location_id=req.dest_id,
                        item_id=ln.item_id,
                        quantity=qty,
                        reserved_quantity=Decimal(0),
                        version=1,
                    )
                    db.add(dst_bal)
                    balances[(req.dest_id, ln.item_id)] = dst_bal

                transfer_dest_items[ln.item_id] = transfer_dest_items.get(ln.item_id, _ZERO) + qty
            elif sub_k in ("sale", "spoilage", "internal"):
                outbound_sync_items[ln.item_id] = outbound_sync_items.get(ln.item_id, _ZERO) + qty


        else:
            target = req.dest_id or req.source_id
            if target is None:
                continue
            direction = getattr(ln, "direction", "increase")
            conv_rate = Decimal(str(getattr(ln, "conversion_rate", None) or 1))
            qty_base = qty * conv_rate
            quantity_signed = -qty_base if req.kind == "adjustment" and direction == "decrease" else qty_base
            mv_id = uuid.uuid4()
            unit_price = Decimal(str(getattr(ln, "unit_price", None) or 0)) if req.kind == "receipt" else None
            unit_cost_base = (unit_price / conv_rate) if unit_price is not None and unit_price > Decimal("0") else None
            cost_amt = (qty_base * unit_cost_base).quantize(Decimal("0.01")) if unit_cost_base else None

            mv = Movement(
                id=mv_id, request_id=req.id, line_id=ln.id,
                item_id=ln.item_id, location_id=target,
                quantity_signed=quantity_signed, posted_at=now,
                sub_kind="receipt" if req.kind == "receipt" else req.kind,
                unit_cost=unit_cost_base,
                cost_amount=cost_amt,
            )
            db.add(mv)
            await db.flush()

            bal = balances.get((target, ln.item_id))
            if bal:
                bal.quantity = Decimal(str(bal.quantity)) + quantity_signed
            else:
                bal = Balance(
                    location_id=target,
                    item_id=ln.item_id,
                    quantity=quantity_signed,
                    reserved_quantity=Decimal(0),
                    version=1,
                )
                db.add(bal)
                balances[(target, ln.item_id)] = bal

            if req.kind == "receipt":
                lot_no = getattr(ln, "lot_no", None) or "DEFAULT"
                exp = getattr(ln, "expiry_date", None)
                existing_lot = (
                    await db.execute(
                        select(LotBalance).where(
                            LotBalance.location_id == target,
                            LotBalance.item_id == ln.item_id,
                            LotBalance.lot_no == lot_no,
                            LotBalance.expiry_date == exp,
                        ).with_for_update()
                    )
                ).scalar_one_or_none()
                if existing_lot:
                    existing_lot.quantity = Decimal(str(existing_lot.quantity)) + qty_base
                    if unit_cost_base is not None:
                        existing_lot.unit_cost = unit_cost_base
                    existing_lot.updated_at = now
                else:
                    db.add(
                        LotBalance(
                            id=uuid.uuid4(),
                            location_id=target,
                            item_id=ln.item_id,
                            lot_no=lot_no,
                            expiry_date=exp,
                            quantity=qty_base,
                            unit_cost=unit_cost_base,
                            created_at=now,
                            updated_at=now,
                        )
                    )
                db.add(
                    LotMovement(
                        id=uuid.uuid4(),
                        movement_id=mv_id,
                        request_id=req.id,
                        line_id=ln.id,
                        item_id=ln.item_id,
                        location_id=target,
                        lot_no=lot_no,
                        expiry_date=exp,
                        quantity_signed=qty_base,
                        unit_cost=unit_cost_base,
                        cost_amount=cost_amt,
                        sub_kind="receipt",
                    )
                )

        if ln.serial:
            asset = serial_assets[ln.serial.strip()]
            status_before = asset.status
            if req.kind == "transfer" and req.dest_id:
                asset.location_id = req.dest_id
                db.add(
                    AssetLog(
                        id=uuid.uuid4(),
                        asset_id=asset.id,
                        serial=asset.serial,
                        from_location_id=req.source_id,
                        to_location_id=req.dest_id,
                        status_before=status_before,
                        status_after=asset.status,
                        request_id=req.id,
                        actor_id=user.id,
                        notes=f"Chuyển kho theo phiếu {req.id}",
                    )
                )
            elif req.kind == "issue":
                asset.status = "issued"
                db.add(
                    AssetLog(
                        id=uuid.uuid4(),
                        asset_id=asset.id,
                        serial=asset.serial,
                        from_location_id=req.source_id,
                        to_location_id=None,
                        status_before=status_before,
                        status_after="issued",
                        request_id=req.id,
                        actor_id=user.id,
                        notes=f"Xuất kho theo phiếu {req.id}",
                    )
                )

    if transfer_dest_items and req.dest_id:
        await _sync_inbound_items_to_open_stocktakes(db, req.dest_id, transfer_dest_items)
    if outbound_sync_items and req.source_id:
        await _sync_outbound_items_to_open_stocktakes(db, req.source_id, outbound_sync_items)

    if req.kind == "receipt" and req.dest_id:
        target = req.dest_id
        # 1. Đồng bộ các dòng nhập vào ca kiểm kê đang mở (xử lý đúng phiếu nhiều dòng)
        item_totals: dict[uuid.UUID, Decimal] = {}
        item_cost_totals: dict[uuid.UUID, Decimal] = {}
        for ln in lines:
            conv_rate = Decimal(str(getattr(ln, "conversion_rate", None) or 1))
            ln_qty_base = Decimal(str(ln.quantity)) * conv_rate
            item_totals[ln.item_id] = item_totals.get(ln.item_id, Decimal("0")) + ln_qty_base
            ln_price = Decimal(str(getattr(ln, "unit_price", None) or 0))
            item_cost_totals[ln.item_id] = item_cost_totals.get(ln.item_id, Decimal("0")) + (Decimal(str(ln.quantity)) * ln_price)

        await _sync_inbound_items_to_open_stocktakes(db, target, item_totals)

        # 2. Tính lại Giá vốn bình quân gia quyền (Weighted Average Unit Cost)
        for item_id, total_inbound_base in item_totals.items():
            inbound_cost = item_cost_totals.get(item_id, Decimal("0"))
            if total_inbound_base <= _ZERO or inbound_cost <= _ZERO:
                continue
            item_obj = (
                await db.execute(select(Item).where(Item.id == item_id).with_for_update())
            ).scalar_one_or_none()
            if not item_obj:
                continue
            all_bals = (await db.execute(select(Balance).where(Balance.item_id == item_id))).scalars().all()
            current_total_qty = sum((Decimal(str(b.quantity)) for b in all_bals), Decimal("0"))
            old_qty = max(Decimal("0"), current_total_qty - total_inbound_base)
            old_cost = Decimal(str(item_obj.cost_price or 0))
            if old_qty + total_inbound_base > Decimal("0"):
                new_cost = ((old_qty * old_cost) + inbound_cost) / (old_qty + total_inbound_base)
                item_obj.cost_price = Decimal(str(round(new_cost, 2)))

    before = {"status": "submitted", "version": req.version}
    req.status = "posted"
    req.version += 1
    req.approver_id = user.id
    db.add(
        ApprovalDecision(
            id=uuid.uuid4(), subject_type="inventory_request", subject_id=req.id,
            actor_id=user.id, decision="approved",
        )
    )
    await _audit(db, user.id, "inventory.request.approved", req, before)
    await _outbox(db, "inventory.request.approved", req, {})
    await db.commit()
    record_approval_decision("inventory", "approved", req.submitted_at)
    await db.refresh(req)
    await broadcast_approval_event(
        action="approved",
        request_id=str(req.id),
        kind="inventory",
        status="posted",
        message=f"Phiếu kho {req.kind} ({req.id}) đã được phê duyệt",
        meta={"sub_kind": req.kind, "approver_id": str(user.id)},
    )
    body = _req_out(req)
    idempotency.remember(db, key, idempotency.payload_hash({"approve": str(req.id)}), 200, body)
    return body


@router.post("/inventory/requests/{request_id}/reject")
async def reject_request(
    request_id: str,
    request: Request,
    payload: dict | None = None,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    req = await _load_request(db, request_id)
    # Branch-scope guard: checker must have access to source/dest locations.
    if req.source_id is not None:
        await _require_location_scope(db, user, req.source_id)
    if req.dest_id is not None:
        await _require_location_scope(db, user, req.dest_id)
    caps = await get_user_capabilities(db, user.id)
    if "inventory:approve_request" not in caps:
        raise AppError(403, "FORBIDDEN", "Bạn không có quyền phê duyệt phiếu kho.")
    req = (
        await db.execute(
            select(InventoryRequest)
            .where(InventoryRequest.id == req.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()
    if req is None:
        raise AppError(404, "NOT_FOUND", "Phiếu không tồn tại")
    if str(req.maker_id) == str(user.id):
        raise AppError(403, "SELF_APPROVAL_FORBIDDEN", "Bạn không được tự duyệt phiếu của chính mình.")
    if req.status != "submitted":
        raise AppError(409, "STATE_CONFLICT", f"Không thể từ chối phiếu khi đang ở trạng thái {req.status}.")
    _check_if_match(request, req.version)

    lines = (
        await db.execute(
            select(InventoryRequestLine).where(InventoryRequestLine.request_id == req.id)
        )
    ).scalars().all()
    balances = await _lock_balances(db, _affected_balance_keys(req, lines))

    before = {"status": req.status, "version": req.version}
    if payload and payload.get("reason"):
        req.reason = str(payload["reason"])
    req.status = "rejected"
    req.version += 1
    req.approver_id = user.id

    if req.kind in ("issue", "transfer") and req.source_id is not None:
        for ln in lines:
            src = balances.get((req.source_id, ln.item_id))
            if src:
                src.reserved_quantity = max(
                    Decimal(0),
                    Decimal(str(getattr(src, "reserved_quantity", 0) or 0)) - Decimal(str(ln.quantity))
                )

    await _audit(db, user.id, "inventory.request.rejected", req, before)
    await _outbox(db, "inventory.request.rejected", req, {})
    await db.commit()
    record_approval_decision("inventory", "rejected", req.submitted_at)
    await db.refresh(req)
    await broadcast_approval_event(
        action="rejected",
        request_id=str(req.id),
        kind="inventory",
        status="rejected",
        message=f"Phiếu kho {req.kind} ({req.id}) đã bị từ chối",
        meta={"sub_kind": req.kind, "approver_id": str(user.id), "reason": req.reason},
    )
    return _req_out(req)


@router.post("/inventory/requests/{request_id}/return")
async def return_request(
    request_id: str,
    request: Request,
    payload: dict | None = None,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    req = await _load_request(db, request_id)
    # Branch-scope guard: checker must have access to source/dest locations.
    if req.source_id is not None:
        await _require_location_scope(db, user, req.source_id)
    if req.dest_id is not None:
        await _require_location_scope(db, user, req.dest_id)
    caps = await get_user_capabilities(db, user.id)
    if "inventory:approve_request" not in caps:
        raise AppError(403, "FORBIDDEN", "Bạn không có quyền phê duyệt phiếu kho.")
    req = (
        await db.execute(
            select(InventoryRequest)
            .where(InventoryRequest.id == req.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()
    if req is None:
        raise AppError(404, "NOT_FOUND", "Phiếu không tồn tại")
    if str(req.maker_id) == str(user.id):
        raise AppError(403, "SELF_APPROVAL_FORBIDDEN", "Bạn không được tự trả về phiếu của chính mình.")
    if req.status != "submitted":
        raise AppError(409, "STATE_CONFLICT", f"Không thể trả lại phiếu khi đang ở trạng thái {req.status}.")
    _check_if_match(request, req.version)

    reason = str(payload.get("reason", "")).strip() if payload else ""
    if len(reason) < 3:
        raise AppError(422, "MISSING_REASON", "Lý do trả về yêu cầu chỉnh sửa phải có ít nhất 3 ký tự")

    lines = (
        await db.execute(
            select(InventoryRequestLine).where(InventoryRequestLine.request_id == req.id)
        )
    ).scalars().all()
    balances = await _lock_balances(db, _affected_balance_keys(req, lines))

    before = {"status": req.status, "version": req.version}
    req.status = "returned"
    req.return_reason = reason
    req.version += 1
    req.approver_id = user.id

    if req.kind in ("issue", "transfer") and req.source_id is not None:
        for ln in lines:
            src = balances.get((req.source_id, ln.item_id))
            if src:
                src.reserved_quantity = max(
                    Decimal(0),
                    Decimal(str(getattr(src, "reserved_quantity", 0) or 0)) - Decimal(str(ln.quantity))
                )

    await _audit(db, user.id, "inventory.request.returned", req, before)
    await _outbox(db, "inventory.request.returned", req, {"return_reason": reason})
    await db.commit()
    await db.refresh(req)
    await broadcast_approval_event(
        action="returned",
        request_id=str(req.id),
        kind="inventory",
        status="returned",
        message=f"Phiếu kho {req.kind} ({req.id}) đã được trả về để chỉnh sửa",
        meta={"sub_kind": req.kind, "approver_id": str(user.id), "reason": reason},
    )
    return _req_out(req)



@router.post("/inventory/requests/{request_id}/reverse", status_code=201)
async def reverse_request(
    request_id: str,
    request: Request,
    payload: dict | None = None,
    user=Depends(require_any_capability("inventory:approve_request")),
    db: AsyncSession = Depends(get_db),
):
    """Đảo phiếu đã post: tạo phiếu draft mới (reduction) liên kết từ phiếu gốc."""
    key = _require_key(request)
    req = await _load_request(db, request_id)
    if req.status != "posted":
        raise AppError(409, "STATE_CONFLICT", f"Không thể đảo phiếu khi đang ở trạng thái {req.status}.")
    if str(req.maker_id) == str(user.id):
        raise AppError(403, "SELF_APPROVAL_FORBIDDEN", "Bạn không được tự đảo phiếu của chính mình.")

    cached = _replay(key, {"reverse": str(req.id)})
    if cached is not None:
        return cached

    lines = (
        await db.execute(
            select(InventoryRequestLine).where(InventoryRequestLine.request_id == req.id)
        )
    ).scalars().all()

    reason = (payload or {}).get("reason", "") or "Đảo phiếu"
    reversal_req = InventoryRequest(
        id=uuid.uuid4(),
        kind="adjustment",
        status="draft",
        maker_id=user.id,
        source_id=req.dest_id or req.source_id,
        dest_id=req.source_id or req.dest_id,
        reason=f"Đảo phiếu {req.id}: {reason}",
        created_by=user.id,
        version=1,
    )
    db.add(reversal_req)
    await db.flush()

    for ln in lines:
        db.add(
            InventoryRequestLine(
                id=uuid.uuid4(),
                request_id=reversal_req.id,
                item_id=ln.item_id,
                quantity=ln.quantity,
                direction="decrease" if getattr(ln, "direction", "increase") == "increase" else "increase",
                unit=getattr(ln, "unit", None),
            )
        )

    await _audit(db, user.id, "inventory.request.reversed", reversal_req, {"original_request_id": str(req.id)})
    await _outbox(db, "inventory.request.reversed", reversal_req, {"original_request_id": str(req.id)})
    await db.commit()
    await db.refresh(reversal_req)

    body = {
        "id": str(reversal_req.id),
        "original_request_id": str(req.id),
        "reversed_from": str(req.id),
        "status": reversal_req.status,
        "kind": reversal_req.kind,
    }
    idempotency.remember(db, key, idempotency.payload_hash({"reverse": str(req.id)}), 201, body)
    return body


@router.post("/inventory/assets", status_code=201)
async def create_asset(
    payload: dict,
    request: Request,
    user=Depends(require_any_capability("inventory:create_request")),
    db: AsyncSession = Depends(get_db),
):
    """Tạo tài sản theo serial — serial trùng -> 409 DUPLICATE_SERIAL (I3)."""
    from sqlalchemy.exc import IntegrityError

    key = _require_key(request)
    serial = str(payload.get("serial", "")).strip()
    if not serial:
        raise AppError(422, "SERIAL_REQUIRED", "serial là bắt buộc")
    status = str(payload.get("status", "available")).strip().lower()
    if status not in _ASSET_STATUSES:
        raise AppError(422, "INVALID_ASSET_STATUS", "Trạng thái ấn chỉ không hợp lệ")
    cached = _replay(key, payload)
    if cached is not None:
        return cached
    item_id = await _resolve_item_id(db, payload)
    location_id = (
        _uuid(payload["location_id"], "location_id") if payload.get("location_id") else None
    )
    if location_id is None:
        raise AppError(422, "LOCATION_REQUIRED", "location_id là bắt buộc")
    await _require_location_scope(db, user, location_id)
    dup = (
        await db.execute(select(Asset).where(Asset.serial == serial))
    ).scalar_one_or_none()
    if dup is not None:
        raise AppError(409, "DUPLICATE_SERIAL", f"serial {serial!r} đã tồn tại")
    asset = Asset(
        id=uuid.uuid4(), item_id=item_id, serial=serial,
        location_id=location_id, status=status,
    )
    db.add(asset)
    log = AssetLog(
        id=uuid.uuid4(),
        asset_id=asset.id,
        serial=asset.serial,
        from_location_id=None,
        to_location_id=location_id,
        status_before=None,
        status_after=asset.status,
        actor_id=user.id,
        notes="Khởi tạo số serial ấn chỉ vào hệ thống",
    )
    db.add(log)
    try:
        await db.commit()
        await db.refresh(asset)
    except IntegrityError:
        await db.rollback()
        raise AppError(409, "DUPLICATE_SERIAL", f"serial {serial!r} đã tồn tại") from None
    body = {
        "id": str(asset.id),
        "item_id": str(asset.item_id),
        "serial": asset.serial,
        "location_id": str(asset.location_id),
        "assignee_demo": asset.assignee_demo,
        "status": asset.status,
    }
    idempotency.remember(db, key, idempotency.payload_hash(payload), 201, body)
    return body


@router.get("/inventory/assets/{asset_id}/history")
async def get_asset_history(
    asset_id: str,
    current_user=Depends(require_any_capability(*_VIEW_ASSETS)),
    db: AsyncSession = Depends(get_db),
):
    try:
        aid = uuid.UUID(asset_id)
        asset = (await db.execute(select(Asset).where(Asset.id == aid))).scalars().first()
    except (ValueError, AttributeError):
        asset = (await db.execute(select(Asset).where(Asset.serial == str(asset_id)))).scalars().first()
    if not asset:
        raise AppError(404, "ASSET_NOT_FOUND", "Không tìm thấy nguyên liệu")
    aid = asset.id

    logs = (
        await db.execute(
            select(AssetLog)
            .where(AssetLog.asset_id == aid)
            .order_by(AssetLog.created_at.desc())
        )
    ).scalars().all()

    locations = {
        str(loc.id): loc.name
        for loc in (await db.execute(select(Location))).scalars().all()
    }
    users = {
        str(u.id): (u.display_name_demo or u.username)
        for u in (await db.execute(select(User))).scalars().all()
    }

    return {
        "asset": {
            "id": str(asset.id),
            "serial": asset.serial,
            "status": asset.status,
            "location_id": str(asset.location_id),
            "location_name": locations.get(str(asset.location_id), ""),
            "assignee": asset.assignee_demo,
        },
        "history": [
            {
                "id": str(log.id),
                "serial": log.serial,
                "from_location_id": str(log.from_location_id) if log.from_location_id else None,
                "from_location_name": locations.get(str(log.from_location_id)) if log.from_location_id else None,
                "to_location_id": str(log.to_location_id) if log.to_location_id else None,
                "to_location_name": locations.get(str(log.to_location_id)) if log.to_location_id else None,
                "from_assignee": log.from_assignee,
                "to_assignee": log.to_assignee,
                "status_before": log.status_before,
                "status_after": log.status_after,
                "actor_id": str(log.actor_id) if log.actor_id else None,
                "actor_name": users.get(str(log.actor_id)) if log.actor_id else None,
                "request_id": str(log.request_id) if log.request_id else None,
                "notes": log.notes,
                "created_at": log.created_at.isoformat() if log.created_at else None,
            }
            for log in logs
        ],
    }


@router.post("/inventory/assets/{asset_id}/handover")
async def handover_asset(
    asset_id: str,
    payload: dict,
    request: Request,
    user=Depends(require_any_capability("inventory:manage_catalog", "admin:user_management")),
    db: AsyncSession = Depends(get_db),
):
    key = _require_key(request)
    operation = {"asset_id": asset_id, "payload": payload}
    cached = _replay(key, operation)
    if cached is not None:
        return cached

    try:
        aid = uuid.UUID(asset_id)
        asset_stmt = select(Asset).where(Asset.id == aid)
    except (ValueError, AttributeError):
        asset_stmt = select(Asset).where(Asset.serial == str(asset_id).strip())
    asset = (await db.execute(asset_stmt.with_for_update())).scalars().first()
    if not asset:
        raise AppError(404, "ASSET_NOT_FOUND", "Không tìm thấy nguyên liệu")

    to_location_id = (
        _uuid(payload["to_location_id"], "to_location_id")
        if payload.get("to_location_id")
        else None
    )
    if to_location_id is not None:
        destination = (
            await db.execute(select(Location).where(Location.id == to_location_id))
        ).scalar_one_or_none()
        if destination is None:
            raise AppError(404, "LOCATION_NOT_FOUND", "Không tìm thấy kho nhận bàn giao")
        if not destination.active:
            raise AppError(409, "LOCATION_INACTIVE", "Không thể bàn giao đến kho đã ngừng hoạt động")

    raw_assignee = payload.get("to_assignee")
    if raw_assignee is not None and not isinstance(raw_assignee, str):
        raise AppError(422, "INVALID_ASSIGNEE", "to_assignee phải là chuỗi")
    to_assignee = raw_assignee.strip() if isinstance(raw_assignee, str) else None
    if to_assignee is not None and len(to_assignee) > 128:
        raise AppError(422, "INVALID_ASSIGNEE", "to_assignee không được quá 128 ký tự")

    new_status = str(payload.get("status") or asset.status).strip().lower()
    if new_status not in _ASSET_STATUSES:
        raise AppError(422, "INVALID_ASSET_STATUS", "Trạng thái ấn chỉ không hợp lệ")
    allowed = _ASSET_STATUS_TRANSITIONS.get(asset.status, set())
    if new_status not in allowed:
        raise AppError(
            409,
            "INVALID_ASSET_TRANSITION",
            f"Không thể chuyển ấn chỉ từ {asset.status} sang {new_status}",
        )

    raw_notes = payload.get("notes")
    if raw_notes is not None and not isinstance(raw_notes, str):
        raise AppError(422, "INVALID_NOTES", "notes phải là chuỗi")
    notes = raw_notes.strip() if isinstance(raw_notes, str) else "Bàn giao nguyên liệu nội bộ"
    if len(notes) > 1024:
        raise AppError(422, "INVALID_NOTES", "notes không được quá 1024 ký tự")

    status_before = asset.status
    from_loc = asset.location_id
    from_assignee = asset.assignee_demo

    if to_location_id:
        asset.location_id = to_location_id
    if to_assignee is not None:
        asset.assignee_demo = to_assignee
    asset.status = new_status

    log = AssetLog(
        id=uuid.uuid4(),
        asset_id=asset.id,
        serial=asset.serial,
        from_location_id=from_loc,
        to_location_id=asset.location_id,
        from_assignee=from_assignee,
        to_assignee=asset.assignee_demo,
        status_before=status_before,
        status_after=new_status,
        actor_id=user.id,
        notes=notes,
    )
    db.add(log)
    await db.commit()
    await db.refresh(asset)
    body = {
        "id": str(asset.id),
        "serial": asset.serial,
        "status": asset.status,
        "location_id": str(asset.location_id),
        "assignee": asset.assignee_demo,
        "log_id": str(log.id),
    }
    idempotency.remember(db, key, idempotency.payload_hash(operation), 200, body)
    return body


# --------------------------------------------------------------------------
# Stock Levels & Low Stock Alerts
# --------------------------------------------------------------------------
@router.get("/inventory/low-stock-alerts")
async def low_stock_alerts(
    location_id: str | None = None,
    current_user=Depends(require_any_capability("inventory:view_balances", "inventory:manage_catalog")),
    db: AsyncSession = Depends(get_db),
):
    """Cảnh báo tồn thấp trà sữa (SRS §3.4): tồn cuối <= Min → đỏ, cần đặt hàng."""
    allowed_location_ids = await get_accessible_location_ids(db, current_user)
    stmt = (
        select(Balance, StockLevel, Item, Location)
        .join(StockLevel, (StockLevel.location_id == Balance.location_id) & (StockLevel.item_id == Balance.item_id))
        .join(Item, Item.id == Balance.item_id)
        .join(Location, Location.id == Balance.location_id)
    )
    if allowed_location_ids is not None:
        stmt = stmt.where(StockLevel.location_id.in_(allowed_location_ids))
    if location_id:
        lid = _uuid(location_id, "location_id")
        stmt = stmt.where(StockLevel.location_id == lid)
    rows = (await db.execute(stmt)).all()
    alerts = []
    for bal, lvl, item, loc in rows:
        qty, minimum = Decimal(str(bal.quantity)), Decimal(str(lvl.min_qty))
        if qty <= minimum:
            alerts.append(
                {
                    "location_id": str(loc.id),
                    "location_code": loc.code,
                    "location_name": loc.name,
                    "item_id": str(item.id),
                    "sku": item.sku,
                    "item_name": item.name,
                    "unit": item.unit,
                    "quantity": _format_qty(bal.quantity),
                    "min_qty": _format_qty(lvl.min_qty),
                    "severity": "critical",
                    "message": f"{item.name} tại {loc.name} còn {_format_qty(bal.quantity)} {item.unit} (Min {_format_qty(lvl.min_qty)}) — cần đặt hàng",
                }
            )
    alerts.sort(key=lambda a: (a["location_code"], a["sku"]))
    return {"alerts": alerts, "count": len(alerts), "rule": "quantity <= min_qty"}


@router.get("/inventory/expiry-alerts")
@router.get("/inventory/alerts/expiry")
async def expiry_alerts(
    days: int = 7,
    current_user=Depends(require_any_capability("inventory:view_balances", "inventory:manage_catalog")),
    db: AsyncSession = Depends(get_db),
):
    """Cảnh báo cận date (SRS §3.4): vàng khi sắp hết HSD, đỏ khi hết trong ngày/quá hạn."""
    if days < 0 or days > 365:
        raise AppError(422, "INVALID_DAYS", "days phải trong 0..365")
    today = _hanoi_today()
    allowed_location_ids = await get_accessible_location_ids(db, current_user)
    # Đọc tồn hiện hành từ lot-balance (MỖI lô HSD) thay vì đường receipt posted
    # cũ — đảm bảo số lượng phản chiếu tồn kho hiện tại, không phải lịch sử nhập.
    stmt = (
        select(LotBalance, Item)
        .join(Item, Item.id == LotBalance.item_id)
        .where(
            LotBalance.quantity > 0,
            LotBalance.expiry_date.is_not(None),
        )
    )
    if allowed_location_ids is not None:
        stmt = stmt.where(LotBalance.location_id.in_(allowed_location_ids))
    rows = (await db.execute(stmt)).all()
    alerts = []
    for lot, item in rows:
        delta = (lot.expiry_date - today).days
        if delta <= days:
            alerts.append(
                {
                    "item_id": str(item.id),
                    "sku": item.sku,
                    "item_name": item.name,
                    "unit": item.unit,
                    "lot_no": lot.lot_no,
                    "expiry_date": lot.expiry_date.isoformat(),
                    "days_left": delta,
                    "quantity": _format_qty(lot.quantity),
                    "severity": "critical" if delta <= 0 else ("watch" if delta > 3 else "warning"),
                    "message": f"Lô {lot.lot_no or '?'} {item.name} HSD {lot.expiry_date.isoformat()} (còn {delta} ngày)",
                }
            )
    alerts.sort(key=lambda a: (a["days_left"], a["sku"]))
    return {"alerts": alerts, "count": len(alerts), "today": today.isoformat(), "window_days": days}


@router.put("/inventory/stock-levels")
async def put_stock_level(
    payload: dict,
    request: Request,
    user=Depends(require_any_capability("inventory:manage_catalog", "admin:user_management")),
    db: AsyncSession = Depends(get_db),
):
    """Thiết lập định mức tồn kho (min_qty, max_qty) theo (location_id, item_id)."""
    location_id = _uuid(payload.get("location_id"), "location_id")
    # Scope check là dòng chặn đầu tiên: 404 phải xảy ra TRƯỚC mọi side-effect,
    # kể cả idempotency replay (replay không được bypass phạm vi chi nhánh).
    await _require_location_scope(db, user, location_id)

    key = request.headers.get("Idempotency-Key")
    if key:
        cached = _replay(key, payload)
        if cached is not None:
            return cached

    item_id = _uuid(payload.get("item_id"), "item_id")

    if "min_qty" not in payload:
        raise AppError(422, "MISSING_MIN_QTY", "min_qty là bắt buộc")
    min_qty = _qty(payload["min_qty"])
    if min_qty < Decimal("0"):
        raise AppError(422, "INVALID_MIN_QTY", "min_qty không được âm")

    max_qty = None
    if payload.get("max_qty") is not None:
        max_qty = _qty(payload["max_qty"])
        if max_qty < min_qty:
            raise AppError(422, "INVALID_STOCK_LEVEL", "max_qty phải lớn hơn hoặc bằng min_qty")

    loc = (await db.execute(select(Location).where(Location.id == location_id))).scalars().first()
    if not loc:
        raise AppError(404, "LOCATION_NOT_FOUND", "Không tìm thấy kho")
    it = (await db.execute(select(Item).where(Item.id == item_id))).scalars().first()
    if not it:
        raise AppError(404, "ITEM_NOT_FOUND", "Không tìm thấy mặt hàng")

    existing = (
        await db.execute(
            select(StockLevel).where(
                StockLevel.location_id == location_id,
                StockLevel.item_id == item_id,
            )
        )
    ).scalars().first()

    if existing:
        existing.min_qty = min_qty
        existing.max_qty = max_qty
        level = existing
    else:
        level = StockLevel(
            id=uuid.uuid4(),
            location_id=location_id,
            item_id=item_id,
            min_qty=min_qty,
            max_qty=max_qty,
        )
        db.add(level)

    await db.commit()
    await db.refresh(level)

    body = {
        "id": str(level.id),
        "location_id": str(level.location_id),
        "item_id": str(level.item_id),
        "min_qty": _format_qty(level.min_qty),
        "max_qty": _format_qty(level.max_qty) if level.max_qty is not None else None,
    }
    if key:
        idempotency.remember(db, key, idempotency.payload_hash(payload), 200, body)
    return body


@router.get("/inventory/stock-levels")
async def list_stock_levels(
    location_id: str | None = None,
    item_id: str | None = None,
    user=Depends(require_any_capability(*_VIEW_CATALOG)),
    db: AsyncSession = Depends(get_db),
):
    """Lấy danh sách các định mức tồn kho đã cấu hình."""
    allowed_location_ids = await get_accessible_location_ids(db, user)
    stmt = select(StockLevel)
    if allowed_location_ids is not None:
        stmt = stmt.where(StockLevel.location_id.in_(allowed_location_ids))
    if location_id:
        stmt = stmt.where(StockLevel.location_id == _uuid(location_id, "location_id"))
    if item_id:
        stmt = stmt.where(StockLevel.item_id == _uuid(item_id, "item_id"))
    levels = (await db.execute(stmt)).scalars().all()
    return {
        "stock_levels": [
            {
                "id": str(level.id),
                "location_id": str(level.location_id),
                "item_id": str(level.item_id),
                "min_qty": _format_qty(level.min_qty),
                "max_qty": _format_qty(level.max_qty) if level.max_qty is not None else None,
            }
            for level in levels
        ]
    }


@router.get("/inventory/low-stock")
@router.get("/inventory/alerts/low-stock")
async def list_low_stock(
    location_id: str | None = None,
    user=Depends(require_any_capability(*_VIEW_CATALOG)),
    db: AsyncSession = Depends(get_db),
):
    """So sánh số dư thực tế với định mức min_qty và trả về danh sách cảnh báo thiếu."""
    allowed_location_ids = await get_accessible_location_ids(db, user)
    stmt = (
        select(StockLevel, Balance, Item, Location)
        .outerjoin(
            Balance,
            (Balance.location_id == StockLevel.location_id)
            & (Balance.item_id == StockLevel.item_id),
        )
        .join(Item, Item.id == StockLevel.item_id)
        .join(Location, Location.id == StockLevel.location_id)
    )
    if allowed_location_ids is not None:
        stmt = stmt.where(StockLevel.location_id.in_(allowed_location_ids))
    if location_id:
        stmt = stmt.where(StockLevel.location_id == _uuid(location_id, "location_id"))
    rows = (await db.execute(stmt)).all()

    items_out = []
    for level, bal, it, loc in rows:
        current_qty = Decimal(str(bal.quantity)) if bal and bal.quantity is not None else Decimal("0")
        min_qty = Decimal(str(level.min_qty))

        if current_qty < min_qty:
            deficit = min_qty - current_qty
            status = "empty" if current_qty <= Decimal("0") else "low"
            unit = it.unit if it else "đơn vị"
            deficit_str = _format_qty(deficit)
            suggested_action = (
                f"Đề xuất lập phiếu nhập kho hoặc chuyển kho bổ sung tối thiểu {deficit_str} {unit}"
            )
            items_out.append({
                "location_id": str(level.location_id),
                "location_code": loc.code if loc else "N/A",
                "location_name": loc.name if loc else "N/A",
                "item_id": str(level.item_id),
                "sku": it.sku if it else "N/A",
                "item_name": it.name if it else "N/A",
                "unit": unit,
                "current_qty": _format_qty(current_qty),
                "min_qty": _format_qty(level.min_qty),
                "max_qty": _format_qty(level.max_qty) if level.max_qty is not None else None,
                "status": status,
                "deficit": deficit_str,
                "suggested_action": suggested_action,
            })

    return {"items": items_out}



# --------------------------------------------------------------------------
# Stocktakes (Kiểm kê định kỳ & đối soát chênh lệch)
# --------------------------------------------------------------------------
@router.post("/inventory/stocktakes", status_code=201)
async def create_stocktake(
    payload: dict,
    request: Request,
    user=Depends(require_any_capability("inventory:create_request", "inventory:manage_catalog", "admin:user_management")),
    db: AsyncSession = Depends(get_db),
):
    """Tạo đợt kiểm kê kho mới (trạng thái ban đầu = open)."""
    key = request.headers.get("Idempotency-Key")
    location_id = _uuid(payload.get("location_id"), "location_id")
    await _require_location_scope(db, user, location_id)
    loc = (await db.execute(select(Location).where(Location.id == location_id))).scalars().first()
    if not loc:
        raise AppError(404, "LOCATION_NOT_FOUND", "Không tìm thấy kho kiểm kê")
    cached = await _stocktake_replay(db, key, payload)
    if cached is not None:
        return cached
    if key and not await idempotency.claim_key(db, key, idempotency.payload_hash(payload), "stocktake:create"):
        cached = await _stocktake_replay(db, key, payload)
        if cached is not None:
            return cached
        raise AppError(409, "IDEMPOTENCY_IN_PROGRESS", "Yêu cầu mở ca đang được xử lý")

    note = str(payload.get("note") or payload.get("title") or "Kiểm kê theo ca").strip()
    shift_code = str(payload.get("shift_code") or "").strip().lower() or None
    if shift_code not in (None, "morning", "afternoon", "split"):
        raise AppError(422, "INVALID_SHIFT", "shift_code phải là morning, afternoon hoặc split")
    business_date = _parse_day(payload.get("business_date")) or _hanoi_today()
    # Chống mở trùng ca đang mở (SRS §3.3): 1 ca/location/ngày.
    existing_open = (
        await db.execute(
            select(Stocktake.id).where(
                Stocktake.location_id == location_id,
                Stocktake.business_date == business_date,
                Stocktake.shift_code == shift_code,
                Stocktake.status == "open",
            )
        )
    ).scalar_one_or_none()
    if existing_open is not None:
        raise AppError(409, "SHIFT_ALREADY_OPEN", "Ca này đã mở, không được mở trùng")
    st = Stocktake(
        id=uuid.uuid4(),
        location_id=location_id,
        status="open",
        maker_id=user.id,
        note=note,
        shift_code=shift_code,
        business_date=business_date,
    )
    db.add(st)
    await db.flush()
    # Tồn đầu ca kế thừa số thực tế đã chốt của ca bàn giao trước:
    # Sáng ← tồn cuối ngày hôm trước; Chiều ← Sáng cùng ngày; Lỡ ← độc lập
    # nhưng vẫn khởi tạo từ tồn gần nhất để giảm nhập tay.
    items = (await db.execute(select(Item).where(Item.active == True))).scalars().all()  # noqa: E712
    prev_counted: dict[str, Decimal] = {}
    if shift_code in ("morning", "afternoon"):
        prev_stmt = select(Stocktake).where(
            Stocktake.location_id == location_id,
            Stocktake.status.in_(["submitted", "closed"]),
        )
        if shift_code == "morning":
            prev_stmt = prev_stmt.where(Stocktake.business_date < business_date)
        else:
            prev_stmt = prev_stmt.where(
                Stocktake.business_date == business_date,
                Stocktake.shift_code == "morning",
            )
        prev = (
            await db.execute(
                prev_stmt.order_by(Stocktake.business_date.desc(), Stocktake.created_at.desc()).limit(1)
            )
        ).scalars().first()
        if prev is not None:
            prev_lines = (
                await db.execute(select(StocktakeLine).where(StocktakeLine.stocktake_id == prev.id))
            ).scalars().all()
            prev_counted = {str(pl.item_id): Decimal(str(pl.counted_qty)) for pl in prev_lines}
    balances = (
        await db.execute(select(Balance).where(Balance.location_id == location_id))
    ).scalars().all()
    bal_map = {str(b.item_id): Decimal(str(b.quantity)) for b in balances}
    for item in items:
        opening = prev_counted.get(str(item.id), bal_map.get(str(item.id), _ZERO))
        db.add(
            StocktakeLine(
                id=uuid.uuid4(), stocktake_id=st.id, item_id=item.id,
                book_qty=opening, opening_qty=opening,
                received_qty=_ZERO, used_qty=_ZERO,
                theoretical_qty=opening, counted_qty=opening,
                variance=_ZERO,
            )
        )
    await db.flush()

    shift_label = _SHIFT_WINDOWS.get(shift_code, ("Kiểm kê", "", ""))[0] if shift_code else "Kiểm kê"
    body = {
        "id": str(st.id),
        "location_id": str(st.location_id),
        "status": st.status,
        "version": st.version,
        "note": st.note,
        "maker_id": str(st.maker_id),
        "shift_code": st.shift_code,
        "shift_label": shift_label,
        "business_date": st.business_date.isoformat() if st.business_date else None,
        "created_at": st.created_at.isoformat() if st.created_at else None,
    }
    if key:
        await idempotency.store_response(db, key, idempotency.payload_hash(payload), 201, body)
    await db.commit()
    return body


@router.get("/inventory/stocktakes")
async def list_stocktakes(
    location_id: str | None = None,
    status: str | None = None,
    user=Depends(require_any_capability(*_VIEW_CATALOG)),
    db: AsyncSession = Depends(get_db),
):
    """Danh sách các đợt kiểm kê (lọc theo phạm vi chi nhánh của user)."""
    stmt = select(Stocktake).order_by(Stocktake.created_at.desc())
    # S6 — kiểm kê là dữ liệu tồn kho theo chi nhánh: user branch B không
    # được thấy đợt kiểm kê của branch A (cùng cơ chế scope như
    # `list_balances` / `list_locations`).
    allowed_location_ids = await get_accessible_location_ids(db, user)
    if allowed_location_ids is not None:
        stmt = stmt.where(Stocktake.location_id.in_(allowed_location_ids))
    if location_id:
        stmt = stmt.where(Stocktake.location_id == _uuid(location_id, "location_id"))
    if status:
        stmt = stmt.where(Stocktake.status == status)
    rows = (await db.execute(stmt)).scalars().all()
    return {
        "stocktakes": [
            {
                "id": str(r.id),
                "location_id": str(r.location_id),
                "status": r.status,
                "version": r.version,
                "note": r.note,
                "maker_id": str(r.maker_id),
                "shift_code": r.shift_code,
                "business_date": r.business_date.isoformat() if r.business_date else None,
                "approver_id": str(r.approver_id) if r.approver_id else None,
                "adjustment_request_id": str(r.adjustment_request_id) if r.adjustment_request_id else None,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "completed_at": r.completed_at.isoformat() if r.completed_at else None,
            }
            for r in rows
        ]
    }


@router.get("/inventory/stocktakes/{stocktake_id}")
async def get_stocktake(
    stocktake_id: str,
    user=Depends(require_any_capability(*_VIEW_CATALOG)),
    db: AsyncSession = Depends(get_db),
):
    """Chi tiết đợt kiểm kê kèm các dòng đếm thực tế và chênh lệch."""
    sid = _uuid(stocktake_id, "stocktake_id")
    st = (await db.execute(select(Stocktake).where(Stocktake.id == sid))).scalars().first()
    if not st:
        raise AppError(404, "STOCKTAKE_NOT_FOUND", "Không tìm thấy đợt kiểm kê")
    # S6 — ngoài phạm vi chi nhánh thì coi như không tồn tại (404).
    allowed_location_ids = await get_accessible_location_ids(db, user)
    if (
        allowed_location_ids is not None
        and str(st.location_id) not in {str(i) for i in allowed_location_ids}
    ):
        raise AppError(404, "STOCKTAKE_NOT_FOUND", "Không tìm thấy đợt kiểm kê")
    lines = (
        await db.execute(select(StocktakeLine).where(StocktakeLine.stocktake_id == sid))
    ).scalars().all()
    return {
        "id": str(st.id),
        "location_id": str(st.location_id),
        "status": st.status,
        "version": st.version,
        "note": st.note,
        "maker_id": str(st.maker_id),
        "shift_code": st.shift_code,
        "business_date": st.business_date.isoformat() if st.business_date else None,
        "approver_id": str(st.approver_id) if st.approver_id else None,
        "adjustment_request_id": str(st.adjustment_request_id) if st.adjustment_request_id else None,
        "created_at": st.created_at.isoformat() if st.created_at else None,
        "completed_at": st.completed_at.isoformat() if st.completed_at else None,
        "lines": [_stocktake_line_out(line) for line in lines],
    }


@router.put("/inventory/stocktakes/{stocktake_id}/lines")
async def update_stocktake_lines(
    stocktake_id: str,
    payload: dict,
    request: Request,
    user=Depends(require_any_capability("inventory:create_request", "inventory:manage_catalog", "admin:user_management")),
    db: AsyncSession = Depends(get_db),
):
    """Cập nhật các dòng kiểm đếm thực tế, tự tính chênh lệch so với sổ cái."""
    sid = _uuid(stocktake_id, "stocktake_id")
    key = request.headers.get("Idempotency-Key")
    operation = {"update_stocktake_lines": str(sid), "payload": payload}
    st = (
        await db.execute(
            select(Stocktake)
            .where(Stocktake.id == sid)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()
    if not st:
        raise AppError(404, "STOCKTAKE_NOT_FOUND", "Không tìm thấy đợt kiểm kê")
    await _require_location_scope(db, user, st.location_id)
    if str(st.maker_id) != str(user.id):
        raise AppError(403, "FORBIDDEN", "Chỉ maker mới được cập nhật dòng kiểm kê của mình")
    cached = await _stocktake_replay(db, key, operation)
    if cached is not None:
        return cached
    _check_if_match(request, st.version)
    if st.status != "open":
        raise AppError(409, "STOCKTAKE_LOCKED", f"Ca đã {st.status}, không được sửa — phải tạo Phiếu điều chỉnh kiểm kê")

    raw_lines = payload.get("lines", [])
    for row in raw_lines:
        item_id = _uuid(row.get("item_id"), "item_id")
        counted_qty = _qty(row.get("counted_qty", 0))

        # Đọc tồn sổ sách tại thời điểm kiểm kê
        bal = (
            await db.execute(
                select(Balance).where(
                    Balance.location_id == st.location_id,
                    Balance.item_id == item_id,
                )
            )
        ).scalars().first()
        book_qty = Decimal(str(bal.quantity)) if bal else Decimal("0")

        existing_line = (
            await db.execute(
                select(StocktakeLine).where(
                    StocktakeLine.stocktake_id == sid,
                    StocktakeLine.item_id == item_id,
                )
            )
        ).scalars().first()

        if existing_line:
            # SRS §3.3 + S8: nhân viên chỉ nhập Sử dụng + Kiểm thực tế;
            # Tồn đầu/Nhập do HỆ THỐNG giữ, Còn lại + Lệch tự tính.
            # S8 — client KHÔNG được tự ghi đè `opening_qty`/`received_qty`:
            # nếu client tự chỉnh được số tồn đầu/nhập thì chênh lệch kiểm kê
            # luôn = 0 và người làm đối soát bị "tự rửa" sai lệch. Server luôn
            # tính `theoretical_qty` từ số liệu hệ thống; giá trị client gửi
            # lên bị BỎ QUA (không phải lỗi 422 để client cũ không vỡ).
            opening_qty = Decimal(str(existing_line.opening_qty))
            received_qty = Decimal(str(existing_line.received_qty))
            used_qty = _qty(row.get("used_qty", existing_line.used_qty))
            if used_qty < 0:
                raise AppError(422, "NEGATIVE_USED", "Sử dụng trong ca không được âm")
            theoretical_qty = opening_qty + received_qty - used_qty
            existing_line.book_qty = theoretical_qty if st.shift_code else book_qty
            existing_line.opening_qty = opening_qty
            existing_line.received_qty = received_qty
            existing_line.used_qty = used_qty
            existing_line.theoretical_qty = theoretical_qty
            existing_line.counted_qty = counted_qty
            existing_line.variance = counted_qty - existing_line.book_qty
            if "reason" in row:
                existing_line.reason = str(row["reason"])
        else:
            # Dòng mới: tồn đầu lấy từ sổ cái (Balance) của server, nhập = 0.
            opening_qty = book_qty
            received_qty = _ZERO
            used_qty = _qty(row.get("used_qty", 0))
            if used_qty < 0:
                raise AppError(422, "NEGATIVE_USED", "Sử dụng trong ca không được âm")
            theoretical_qty = opening_qty + received_qty - used_qty
            expected_qty = theoretical_qty if st.shift_code else book_qty
            db.add(
                StocktakeLine(
                    id=uuid.uuid4(),
                    stocktake_id=sid,
                    item_id=item_id,
                    book_qty=expected_qty,
                    opening_qty=opening_qty,
                    received_qty=received_qty,
                    used_qty=used_qty,
                    theoretical_qty=theoretical_qty,
                    counted_qty=counted_qty,
                    variance=counted_qty - expected_qty,
                    reason=str(row.get("reason", "")),
                )
            )

    st.version += 1
    await db.flush()
    lines = (
        await db.execute(select(StocktakeLine).where(StocktakeLine.stocktake_id == sid))
    ).scalars().all()
    body = {
        "id": str(st.id),
        "location_id": str(st.location_id),
        "status": st.status,
        "version": st.version,
        "note": st.note,
        "lines": [_stocktake_line_out(line) for line in lines],
    }
    if key:
        await idempotency.store_response(db, key, idempotency.payload_hash(operation), 200, body)
    await db.commit()
    return body


@router.post("/inventory/stocktakes/{stocktake_id}/submit")
async def submit_stocktake(
    stocktake_id: str,
    request: Request,
    user=Depends(require_any_capability("inventory:create_request", "inventory:manage_catalog", "admin:user_management")),
    db: AsyncSession = Depends(get_db),
):
    """Đệ trình đợt kiểm kê sang trạng thái submitted chờ phê duyệt."""
    sid = _uuid(stocktake_id, "stocktake_id")
    key = request.headers.get("Idempotency-Key")
    operation = {"submit_stocktake": str(sid)}
    st = (
        await db.execute(
            select(Stocktake)
            .where(Stocktake.id == sid)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()
    if not st:
        raise AppError(404, "STOCKTAKE_NOT_FOUND", "Không tìm thấy đợt kiểm kê")
    await _require_location_scope(db, user, st.location_id)
    if str(st.maker_id) != str(user.id):
        raise AppError(403, "FORBIDDEN", "Chỉ maker mới được submit đợt kiểm kê của mình")
    cached = await _stocktake_replay(db, key, operation)
    if cached is not None:
        return cached
    _check_if_match(request, st.version)
    if st.status != "open":
        raise AppError(409, "STATE_CONFLICT", f"Không thể submit từ trạng thái {st.status}")

    st.status = "submitted"
    st.version += 1
    body = {
        "id": str(st.id),
        "location_id": str(st.location_id),
        "status": st.status,
        "version": st.version,
        "note": st.note,
    }
    if key:
        await idempotency.store_response(db, key, idempotency.payload_hash(operation), 200, body)
    await db.commit()
    await broadcast_approval_event(
        action="submitted",
        request_id=str(st.id),
        kind="stocktake",
        status="submitted",
        message=f"Đợt kiểm kê {str(st.id)[:8]} đã được gửi phê duyệt",
        meta={"location_id": str(st.location_id), "maker_id": str(user.id)},
    )
    return body



@router.post("/inventory/stocktakes/{stocktake_id}/approve")
async def approve_stocktake(
    stocktake_id: str,
    request: Request,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Phê duyệt đợt kiểm kê (Maker != Checker). Tự sinh phiếu adjustment nếu có chênh lệch."""
    sid = _uuid(stocktake_id, "stocktake_id")
    key = _require_key(request)
    operation = {"approve_stocktake": str(sid)}
    cached = _replay(key, operation)
    if cached is not None:
        return cached

    caps = await get_user_capabilities(db, user.id)
    if "inventory:approve_request" not in caps:
        raise AppError(403, "FORBIDDEN", "Bạn không có quyền phê duyệt kiểm kê.")

    # Single-winner state transition: the second checker waits and then sees
    # `closed`, so it cannot emit a second adjustment draft.
    st = (
        await db.execute(select(Stocktake).where(Stocktake.id == sid).with_for_update())
    ).scalar_one_or_none()
    if not st:
        raise AppError(404, "STOCKTAKE_NOT_FOUND", "Không tìm thấy đợt kiểm kê")
    await _require_location_scope(db, user, st.location_id)
    cached = _replay(key, operation)
    if cached is not None:
        return cached

    # Invariant A1: Maker không tự duyệt đợt kiểm kê của chính mình
    if str(st.maker_id) == str(user.id):
        raise AppError(403, "SELF_APPROVAL_FORBIDDEN", "Bạn không được tự duyệt đợt kiểm kê của chính mình.")

    if st.status != "submitted":
        raise AppError(409, "STATE_CONFLICT", f"Không thể approve từ trạng thái {st.status}")

    lines = (
        await db.execute(select(StocktakeLine).where(StocktakeLine.stocktake_id == sid))
    ).scalars().all()

    variance_lines = [line for line in lines if Decimal(str(line.variance)) != Decimal("0")]
    adj_id: str | None = None

    # Nếu có chênh lệch, tự động sinh phiếu điều chỉnh kho (kind=adjustment)
    if variance_lines:
        adj_req = InventoryRequest(
            id=uuid.uuid4(),
            kind="adjustment",
            status="submitted",
            maker_id=st.maker_id,
            source_id=st.location_id,
            dest_id=st.location_id,
            reason=f"Điều chỉnh tự động từ đợt kiểm kê {str(st.id)[:8]}: {st.note or ''}",
            created_by=st.maker_id,
            version=1,
            submitted_at=_now(),
        )
        db.add(adj_req)

        for vl in variance_lines:
            db.add(
                InventoryRequestLine(
                    id=uuid.uuid4(),
                    request_id=adj_req.id,
                    item_id=vl.item_id,
                    # A shortage has a negative variance and must reduce the
                    # ledger when the separately approved adjustment is posted.
                    # The quantity remains positive to satisfy qty_positive;
                    # direction is the explicit accounting effect.
                    quantity=abs(Decimal(str(vl.variance))),
                    direction="increase" if Decimal(str(vl.variance)) > _ZERO else "decrease",
                )
            )

        st.adjustment_request_id = adj_req.id
        adj_id = str(adj_req.id)

    st.status = "closed"
    st.version += 1
    st.approver_id = user.id
    st.completed_at = _now()
    db.add(
        ApprovalDecision(
            id=uuid.uuid4(),
            subject_type="inventory_stocktake",
            subject_id=st.id,
            actor_id=user.id,
            decision="approved",
        )
    )
    await _audit_stocktake(
        db,
        user.id,
        "inventory.stocktake.approved",
        st,
        {"status": "submitted", "adjustment_request_id": None},
    )
    await _outbox_stocktake(db, "inventory.stocktake.approved", st)

    await db.commit()
    record_approval_decision("stocktake", "approved", st.created_at)
    await db.refresh(st)

    await broadcast_approval_event(
        action="approved",
        request_id=str(st.id),
        kind="stocktake",
        status="closed",
        message=f"Đợt kiểm kê {str(st.id)[:8]} đã được phê duyệt",
        meta={
            "location_id": str(st.location_id),
            "maker_id": str(st.maker_id),
            "approver_id": str(st.approver_id),
            "adjustment_request_id": adj_id,
        },
    )

    body = {
        "id": str(st.id),
        "status": "closed",
        "version": st.version,
        "location_id": str(st.location_id),
        "maker_id": str(st.maker_id),
        "approver_id": str(st.approver_id),
        "adjustment_request_id": adj_id,
    }
    idempotency.remember(db, key, idempotency.payload_hash(operation), 200, body)
    return body


@router.post("/inventory/stocktakes/{stocktake_id}/reject")
async def reject_stocktake(
    stocktake_id: str,
    request: Request,
    payload: dict | None = None,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Từ chối đợt kiểm kê, hoàn lại trạng thái open để nhân viên đếm lại."""
    sid = _uuid(stocktake_id, "stocktake_id")
    caps = await get_user_capabilities(db, user.id)
    if "inventory:approve_request" not in caps:
        raise AppError(403, "FORBIDDEN", "Bạn không có quyền phê duyệt/từ chối kiểm kê.")
    st = (
        await db.execute(select(Stocktake).where(Stocktake.id == sid).with_for_update())
    ).scalar_one_or_none()
    if not st:
        raise AppError(404, "STOCKTAKE_NOT_FOUND", "Không tìm thấy đợt kiểm kê")
    await _require_location_scope(db, user, st.location_id)
    if st.status != "submitted":
        raise AppError(409, "STATE_CONFLICT", f"Không thể từ chối từ trạng thái {st.status}")
    if str(st.maker_id) == str(user.id):
        raise AppError(403, "SELF_APPROVAL_FORBIDDEN", "Bạn không được tự từ chối đợt kiểm kê của chính mình.")

    reason = (payload or {}).get("reason") or "Yêu cầu kiểm đếm lại số liệu"
    st.status = "open"
    st.version += 1
    st.note = f"{st.note or ''} [Từ chối: {reason}]".strip()
    await db.commit()
    record_approval_decision("stocktake", "rejected", st.created_at)
    await broadcast_approval_event(
        action="rejected",
        request_id=str(st.id),
        kind="stocktake",
        status="open",
        message=f"Đợt kiểm kê {str(st.id)[:8]} bị từ chối: {reason}",
        meta={"stocktake_id": str(st.id), "reason": reason},
    )
    return {"id": str(st.id), "status": "open", "version": st.version, "note": st.note}

