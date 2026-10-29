"""Cash simulation routes - real double-entry ledger (docs/04, B08)."""
import uuid
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import AppError
from app.api.observability import record_approval_decision
from app.api.routes.auth_utils import (
    get_accessible_cashbox_ids,
    get_current_user,
    require_any_capability,
)
from app.config import settings
from app.database import get_db
from app.models import (
    schema_parity as _schema_parity,  # noqa: F401 - map cash_boxes.branch_id
)
from app.models.activity import AuditEvent, OutboxEvent
from app.models.cash_sim import (
    CashBalance,
    CashBox,
    CashEntry,
    CashJournal,
    CashRequest,
)
from app.services import idempotency
from app.services.approval_controls import verify_supervisor_pin
from app.services.approval_events import broadcast_approval_event

router = APIRouter()

_ZERO = Decimal("0")

class ApprovalInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    supervisor_pin: str | None = Field(default=None, min_length=1, max_length=128)


_SIM_CASH_PREFIX = "SIM_CASH:"
_SIM_OFFSET = "SIM_OFFSET:DEMO"
_SUBJECT = "cash_request"
_SUBJECT_BOX = "cash_box"

# Tách quyền két tiền mặt (D2) — ba quyền độc lập, không gộp:
# - `cash:manage_box`      -> quản lý THÔNG TIN két (tạo/sửa tên, trạng thái).
#                            KHÔNG đụng tới số dư.
# - `cash:reconcile`       -> nghiệp vụ đối soát (giữ nguyên cho API đối soát).
# - `cash:post_adjustment` -> tạo/duyệt/thực hiện bút toán TÀI CHÍNH
#                            (journal điều chỉnh / đảo giao dịch). Tách riêng,
#                            KHÔNG nằm trong `cash:manage_box`.
_CASHBOX_CAPS = ("cash:manage_box",)
_ADJUSTMENT_CAPS = ("cash:post_adjustment",)
# Kind của phiếu quỹ là bút toán điều chỉnh tài chính (không phải thu/chi thường).
_ADJUSTMENT_KINDS = ("adjustment",)
# Bút toán điều chỉnh theo chiều TĂNG quỹ (dòng tiền VÀO). Tách riêng khỏi
# `receipt` vì `receipt` là nghiệp vụ thu tiền thường của cashier (nạp quỹ),
# còn `adjustment_in` là **bút toán điều chỉnh số dư** -> bắt buộc có
# `cash:post_adjustment` ngay từ lúc tạo phiếu.
_ADJUSTMENT_IN_KINDS = ("adjustment_in",)
# Các kind làm SỐ DƯ QUỸ **TĂNG** khi được post. Mọi chiều tăng đều là bút toán
# tài chính -> người thực hiện phải có `cash:post_adjustment` (D2).
_MONEY_IN_KINDS = ("receipt",) + _ADJUSTMENT_IN_KINDS
# Mọi kind là bút toán điều chỉnh tài chính (cả 2 chiều) -> cần
# `cash:post_adjustment` để TẠO phiếu.
_FINANCIAL_ADJUSTMENT_KINDS = _ADJUSTMENT_KINDS + _ADJUSTMENT_IN_KINDS

# Field client gửi lên để "ghi tay" số dư quỹ. Số dư chỉ được đổi qua
# journal (phiếu thu/chi/đảo), không ghi trực tiếp từ input client.
_DIRECT_BALANCE_FIELDS = ("amount", "balance", "opening_balance")

# Độ dài tối đa của `Idempotency-Key` (khớp cột `cash_requests.idempotency_key`).
_IDEMPOTENCY_KEY_MAX_LEN = 128


def _now() -> datetime:
    return datetime.now(UTC)


async def _visible_cashbox_ids(db: AsyncSession, user) -> set[uuid.UUID] | None:
    """Wrapper cục bộ -> helper dùng chung trong `auth_utils`."""
    return await get_accessible_cashbox_ids(db, user)


def _cashbox_id(payload: dict[str, Any]) -> uuid.UUID | None:
    if payload.get("cashbox_id"):
        try:
            return uuid.UUID(str(payload["cashbox_id"]))
        except (ValueError, AttributeError, TypeError):
            pass
    return None


async def _balance_for_box(
    db: AsyncSession, cashbox_id: uuid.UUID, *, for_update: bool = False
):
    """Đọc số dư quỹ.

    `for_update=True` khoá row (SELECT ... FOR UPDATE) để 2 approve song song
    không cùng đọc một số dư rồi cùng ghi (double-spend, R1) — pattern đã dùng
    ở `inventory.py::_get_balance`.
    """
    stmt = select(CashBalance).where(CashBalance.cashbox_id == cashbox_id)
    if for_update:
        stmt = stmt.with_for_update()
    rows = (await db.execute(stmt)).scalars().all()
    return rows[0] if rows else None


def _uuid(val: str, field: str = "id") -> uuid.UUID:
    try:
        return uuid.UUID(str(val))
    except (ValueError, TypeError):
        raise AppError(422, "INVALID_UUID", f"{field} không hợp lệ") from None


async def _load_request(
    db: AsyncSession, request_id: uuid.UUID, *, for_update: bool = False
):
    stmt = select(CashRequest).where(CashRequest.id == request_id)
    if for_update:
        stmt = stmt.with_for_update()
    return (await db.execute(stmt)).scalar_one_or_none()


async def _user_capabilities(db: AsyncSession, user_id: str) -> set[str]:
    from app.models.iam import RoleCapability, UserRole

    rows = (
        await db.execute(
            select(RoleCapability.capability_code)
            .join(UserRole, UserRole.role_code == RoleCapability.role_code)
            .where(UserRole.user_id == user_id)
        )
    ).scalars().all()
    return set(rows) if rows else set()


def _is_money_in_kind(kind: Any) -> bool:
    """True nếu `kind` làm SỐ DƯ QUỸ TĂNG khi được post.

    `receipt` (thu tiền) và `adjustment_in` (bút toán điều chỉnh tăng quỹ) là
    hai chiều TIỀN VÀO két -> đều là bút toán tài chính, phải có
    `cash:post_adjustment` (xem `_ADJUSTMENT_CAPS`).
    """
    return str(kind).strip().lower() in _MONEY_IN_KINDS


def _check_if_match(request: Request, expected_version: int) -> None:
    raw = request.headers.get("if-match")
    if raw is None:
        return
    expected = raw.strip().strip('"')
    if expected.isdigit() and int(expected) != expected_version:
        raise AppError(
            409,
            "VERSION_CONFLICT",
            f"If-Match={expected} but version is {expected_version}",
            {"current_version": expected_version},
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


def _cash_entry(
    journal_id: uuid.UUID, account: str, debit: Decimal, credit: Decimal
) -> CashEntry:
    return CashEntry(
        id=uuid.uuid4(),
        journal_id=journal_id,
        account_code=account,
        debit=debit,
        credit=credit,
    )


# --------------------------------------------------------------------------
# Reads
# --------------------------------------------------------------------------

@router.get("/cash-sim/boxes")
async def list_cashboxes(
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Danh sách cash boxes (read-only, lọc theo chi nhánh)."""
    stmt = select(CashBox)
    visible = await _visible_cashbox_ids(db, current_user)
    if visible is not None:
        stmt = stmt.where(CashBox.id.in_(visible))
    boxes = (await db.execute(stmt)).scalars().all()
    return {
        "simulation": True,
        "currency": "VND",
        "boxes": [
            {
                "id": str(b.id),
                "code": b.code,
                "name": b.name,
                "currency": b.currency,
                "active": b.active,
            }
            for b in boxes
        ],
    }


def _reject_direct_balance_write(payload: dict) -> None:
    """Chặn client ghi tay số dư quỹ (S4).

    Số dư chỉ đổi qua journal chuẩn (phiếu thu/chi/đảo đã approve). Nếu client
    gửi field số dư vào PUT két thì trả 422 thay vì âm thầm ghi đè.
    """
    offending = [f for f in _DIRECT_BALANCE_FIELDS if f in payload]
    if offending:
        raise AppError(
            422,
            "DIRECT_BALANCE_WRITE_FORBIDDEN",
            "Số dư quỹ chỉ đổi qua phiếu (journal), không ghi trực tiếp từ API két. "
            f"Field bị từ chối: {', '.join(sorted(offending))}",
            {"rejected_fields": sorted(offending)},
        )


def _decimal(raw: Any, field: str) -> Decimal:
    try:
        return Decimal(str(raw).strip())
    except (InvalidOperation, ValueError, TypeError):
        raise AppError(422, "INVALID_AMOUNT", f"{field} không hợp lệ") from None


@router.post("/cash-sim/boxes", status_code=201)
async def create_cashbox(
    payload: dict,
    user=Depends(require_any_capability(*_CASHBOX_CAPS)),
    db: AsyncSession = Depends(get_db),
):
    """Mở két tiền mặt.

    Yêu cầu capability quản lý THÔNG TIN két (`cash:manage_box`). Nếu mở két
    kèm số dư đầu kỳ thì còn phải có `cash:post_adjustment` vì đó là bút toán
    tài chính (mở két). Số dư mở két KHÔNG ghi thẳng vào `CashBalance.amount`:
    nó được post thành một bút toán mở két (journal cân debit/credit) để ledger
    và read model không lệch nhau.
    """
    _reject_direct_balance_write({k: v for k, v in payload.items() if k != "opening_balance"})
    code = str(payload.get("code", "")).strip().upper()
    name = str(payload.get("name", "")).strip()
    currency = str(payload.get("currency", "VND")).strip().upper() or "VND"
    opening_balance = str(payload.get("opening_balance", "0.00")).strip() or "0.00"
    if not code:
        raise AppError(422, "MISSING_CODE", "Mã két không được để trống")
    if not name:
        raise AppError(422, "MISSING_NAME", "Tên két không được để trống")
    opening = _decimal(opening_balance, "opening_balance")
    if opening < _ZERO:
        raise AppError(422, "INVALID_AMOUNT", f"opening_balance phải >= 0, nhận {opening}")
    if opening > _ZERO:
        # Mở két có số dư đầu kỳ = bút toán tài chính -> cần quyền riêng.
        caps = await _user_capabilities(db, user.id)
        if not any(c in caps for c in _ADJUSTMENT_CAPS):
            raise AppError(
                403,
                "FORBIDDEN",
                "Mở két kèm số dư đầu kỳ cần quyền ghi bút toán tài chính "
                f"({', '.join(_ADJUSTMENT_CAPS)}).",
            )
    existing = (await db.execute(select(CashBox).where(CashBox.code == code))).scalars().first()
    if existing:
        raise AppError(409, "DUPLICATE_CODE", f"Mã két {code} đã tồn tại")
    box = CashBox(
        id=uuid.uuid4(),
        code=code,
        name=name,
        currency=currency,
        active=True,
    )
    db.add(box)
    await db.flush()
    # S6 — két mới gắn với chi nhánh của người mở két để số dư quỹ không bị
    # lọt sang chi nhánh khác (`cash_boxes.branch_id` do schema_parity map).
    if getattr(user, "branch_id", None):
        await db.execute(
            update(CashBox.__table__)
            .where(CashBox.__table__.c.id == box.id)
            .values(branch_id=user.branch_id)
        )
    balance = CashBalance(
        cashbox_id=box.id,
        amount=_ZERO,
        version=1,
    )
    db.add(balance)
    await db.flush()

    if opening > _ZERO:
        # Bút toán mở két: debit SIM_CASH (quỹ tăng), credit SIM_OFFSET.
        opening_req = CashRequest(
            id=uuid.uuid4(),
            cashbox_id=box.id,
            kind="opening",
            amount=opening,
            status="posted",
            maker_id=user.id,
            approver_id=user.id,
            reason=f"Mở két {code}",
            version=1,
            created_by=user.id,
        )
        db.add(opening_req)
        await db.flush()
        journal = CashJournal(
            id=uuid.uuid4(),
            request_id=opening_req.id,
            posted_at=_now(),
            correlation_id=uuid.uuid4().hex[:12],
            reversal_of=None,
        )
        db.add(journal)
        await db.flush()
        db.add(_cash_entry(journal.id, f"{_SIM_CASH_PREFIX}{box.id}", opening, _ZERO))
        db.add(_cash_entry(journal.id, _SIM_OFFSET, _ZERO, opening))
        balance.amount = opening
        balance.version += 1

    await _audit_box(db, user.id, "create", box, {"opening_balance": str(opening)})
    await _outbox_box(db, "cash_box.created", box, {"opening_balance": str(opening)})
    await db.commit()
    await db.refresh(box)
    return {
        "id": str(box.id),
        "code": box.code,
        "name": box.name,
        "currency": box.currency,
        "opening_balance": str(balance.amount),
        "active": box.active,
    }


@router.put("/cash-sim/boxes/{cashbox_id}")
async def update_cashbox(
    cashbox_id: str,
    payload: dict,
    user=Depends(require_any_capability(*_CASHBOX_CAPS)),
    db: AsyncSession = Depends(get_db),
):
    """Sửa thông tin két (tên / trạng thái) — cần `cash:manage_box`.

    KHÔNG sửa được số dư quỹ (S4): mọi field số dư bị chặn 422
    `DIRECT_BALANCE_WRITE_FORBIDDEN`."""
    _reject_direct_balance_write(payload)
    cid = _uuid(cashbox_id, "cashbox_id")
    box = (await db.execute(select(CashBox).where(CashBox.id == cid))).scalars().first()
    if not box:
        raise AppError(404, "CASHBOX_NOT_FOUND", "Không tìm thấy két sắt")
    before = {"name": box.name, "active": box.active}
    if "name" in payload and payload["name"]:
        box.name = str(payload["name"]).strip()
    if "active" in payload:
        box.active = bool(payload["active"])

    await _audit_box(
        db,
        user.id,
        "update",
        box,
        {"before": before, "after": {"name": box.name, "active": box.active}},
    )
    await _outbox_box(
        db, "cash_box.updated", box, {"before": before, "after": {"name": box.name, "active": box.active}}
    )
    await db.commit()
    await db.refresh(box)
    cur_bal = (await db.execute(select(CashBalance).where(CashBalance.cashbox_id == cid))).scalars().first()
    return {
        "id": str(box.id),
        "code": box.code,
        "name": box.name,
        "currency": box.currency,
        "active": box.active,
        "balance": str(cur_bal.amount) if cur_bal else "0.00",
    }


@router.delete("/cash-sim/boxes/{cashbox_id}")
async def delete_cashbox(
    cashbox_id: str,
    user=Depends(require_any_capability(*_CASHBOX_CAPS)),
    db: AsyncSession = Depends(get_db),
):
    cid = _uuid(cashbox_id, "cashbox_id")
    box = (await db.execute(select(CashBox).where(CashBox.id == cid))).scalars().first()
    if not box:
        raise AppError(404, "CASHBOX_NOT_FOUND", "Không tìm thấy két sắt")
    box.active = False
    await _audit_box(db, user.id, "delete", box, {"active": False})
    await _outbox_box(db, "cash_box.deleted", box, {"active": False})
    await db.commit()
    return {"status": "deleted", "id": str(box.id)}


@router.get("/cash-sim/balances")
async def list_cash_balances(
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Tồn quỹ của từng cash box - read model, nguồn sự thật là journals."""
    stmt = select(CashBalance)
    visible = await _visible_cashbox_ids(db, current_user)
    if visible is not None:
        stmt = stmt.where(CashBalance.cashbox_id.in_(visible))
    rows = (await db.execute(stmt)).scalars().all()
    return {
        "simulation": True,
        "currency": "VND",
        "balances": [
            {
                "cashbox_id": str(b.cashbox_id),
                "amount": str(b.amount),
                "version": b.version,
                "currency": "VND",
                "simulation": True,
            }
            for b in rows
        ],
    }


@router.get("/cash-sim/journals")
async def list_journals(
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    request_id: str | None = None,
    limit: int = 100,
    offset: int = 0,
):
    stmt = select(CashJournal).order_by(CashJournal.posted_at.desc())
    visible = await _visible_cashbox_ids(db, current_user)
    if visible is not None:
        stmt = stmt.where(CashJournal.request_id.in_(
            select(CashRequest.id).where(CashRequest.cashbox_id.in_(visible))
        ))
    if request_id:
        stmt = stmt.where(CashJournal.request_id == uuid.UUID(request_id))
    total = (
        await db.execute(select(func.count()).select_from(stmt.subquery()))
    ).scalar_one()
    rows = (await db.execute(stmt.limit(limit).offset(offset))).scalars().all()
    req_map = {
        r.id: r
        for r in (
            await db.execute(
                select(CashRequest)
                .where(
                    CashRequest.cashbox_id.in_(visible)
                    if visible is not None
                    else CashRequest.id.is_not(None)
                )
            )
        ).scalars().all()
    }
    return {
        "simulation": True,
        "currency": "VND",
        "journals": [
            {
                "id": str(j.id),
                "request_id": str(j.request_id),
                "cashbox_id": str(req_map[j.request_id].cashbox_id)
                if j.request_id in req_map
                else "",
                "kind": req_map[j.request_id].kind
                if j.request_id in req_map
                else "receipt",
                "amount": str(req_map[j.request_id].amount)
                if j.request_id in req_map
                else "0",
                "currency": "VND",
                "reason": (req_map[j.request_id].reason or j.correlation_id)
                if j.request_id in req_map
                else j.correlation_id,
                "posted_at": j.posted_at.isoformat() if j.posted_at else None,
                "reversal_of": str(j.reversal_of) if j.reversal_of else None,
                "correlation_id": j.correlation_id,
                "entries": [
                    {
                        "id": str(e.id),
                        "account_code": e.account_code,
                        "debit": str(e.debit),
                        "credit": str(e.credit),
                    }
                    for e in (
                        await db.execute(
                            select(CashEntry).where(CashEntry.journal_id == j.id)
                        )
                    )
                    .scalars()
                    .all()
                ],
            }
            for j in rows
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


def _same_cash_payload(req: CashRequest, payload: dict[str, Any]) -> bool:
    """Cùng idempotency-key + cùng payload nội dung -> được replay (A3)."""
    try:
        amount = Decimal(str(payload.get("amount", "0")).strip())
    except (InvalidOperation, ValueError, TypeError):
        return False
    box_id = _cashbox_id(payload)
    if box_id is None:
        return False
    return (
        Decimal(str(req.amount)) == amount
        and str(req.kind) == str(payload.get("kind", "payment"))
        and str(req.cashbox_id) == str(box_id)
        and (req.reason or None) == (payload.get("reason") or None)
    )


def _replay_cash_request(req: CashRequest, payload: dict[str, Any], user) -> dict:
    """Trả lại phiếu đã tạo cho key này; payload khác -> 409 (A4).

    Phiếu của user khác không bao giờ được trả ra -> 409 luôn.
    """
    if str(req.maker_id) != str(getattr(user, "id", user)):
        raise idempotency.IdempotencyConflict(201, {"id": str(req.id)})
    if not _same_cash_payload(req, payload):
        raise idempotency.IdempotencyConflict(201, _cash_req_out(req))
    return _cash_req_out(req)


def _cash_req_out(r: CashRequest, extra: dict | None = None) -> dict:
    body = {
        "id": str(r.id),
        "cashbox_id": str(r.cashbox_id),
        "kind": r.kind,
        "amount": str(r.amount),
        "status": r.status,
        "version": r.version,
        "maker_id": str(r.maker_id),
        "approver_id": str(r.approver_id) if r.approver_id else None,
        "reason": r.reason,
        "return_reason": getattr(r, "return_reason", None),
        "created_at": r.created_at.isoformat() if r.created_at else None,
        "simulation": True,
        "currency": "VND",
    }
    if extra:
        body.update(extra)
    return body


@router.get("/cash-sim/requests")
async def list_cash_requests(
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    limit: int = 100,
):
    stmt = select(CashRequest).order_by(CashRequest.created_at.desc())
    visible = await _visible_cashbox_ids(db, current_user)
    if visible is not None:
        stmt = stmt.where(CashRequest.cashbox_id.in_(visible))
    rows = (
        await db.execute(stmt.limit(max(1, min(limit, 100))))
    ).scalars().all()
    return {
        "simulation": True,
        "currency": "VND",
        "requests": [_cash_req_out(r) for r in rows],
    }


@router.delete("/cash-sim/requests/{request_id}")
async def delete_cash_request(
    request_id: str,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    rid = _uuid(request_id, "request_id")
    req = (await db.execute(select(CashRequest).where(CashRequest.id == rid))).scalars().first()
    if not req:
        raise AppError(404, "REQUEST_NOT_FOUND", "Không tìm thấy phiếu quỹ")
    # S5 (IDOR) — chỉ chủ sở hữu phiếu mới được xoá phiếu nháp.
    if str(req.maker_id) != str(user.id):
        raise AppError(403, "FORBIDDEN", "Chỉ người lập phiếu mới được xoá phiếu này.")
    if req.status != "draft":
        raise AppError(409, "CANNOT_DELETE_NON_DRAFT", "Chỉ có thể xoá phiếu ở trạng thái nháp (draft)")
    await db.delete(req)
    await db.commit()
    return {"status": "deleted", "id": str(rid)}


# --------------------------------------------------------------------------
# Creates (draft)
# --------------------------------------------------------------------------

@router.post("/cash-sim/requests", status_code=201)
async def create_cash_request(
    payload: dict[str, Any],
    request: Request,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Tạo phiếu cash draft - maker phải có capability cash:create_request (docs/06)."""
    key = _require_key(request)
    if len(key) > _IDEMPOTENCY_KEY_MAX_LEN:
        raise AppError(
            422,
            "IDEMPOTENCY_KEY_TOO_LONG",
            f"Idempotency-Key tối đa {_IDEMPOTENCY_KEY_MAX_LEN} ký tự",
        )
    caps = await _user_capabilities(db, user.id)
    if "cash:create_request" not in caps:
        raise AppError(403, "FORBIDDEN", "Bạn không có quyền tạo phiếu quỹ.")

    kind = str(payload.get("kind", "payment")).strip().lower()
    # Bút toán điều chỉnh tài chính (cả chiều RA `adjustment` lẫn chiều VÀO
    # `adjustment_in`) -> bắt buộc có `cash:post_adjustment` để TẠO phiếu.
    if kind in _FINANCIAL_ADJUSTMENT_KINDS and not any(
        c in caps for c in _ADJUSTMENT_CAPS
    ):
        raise AppError(
            403,
            "FORBIDDEN",
            "Bạn không có quyền tạo bút toán điều chỉnh tài chính "
            f"({', '.join(_ADJUSTMENT_CAPS)}).",
        )

    try:
        amount = Decimal(str(payload.get("amount", "0")))
    except (InvalidOperation, ValueError):
        raise AppError(422, "INVALID_AMOUNT", "amount không hợp lệ") from None

    cashbox_id = _cashbox_id(payload)
    if amount <= _ZERO:
        raise AppError(422, "INVALID_AMOUNT", f"amount phải > 0, nhận {amount}")
    if cashbox_id is None:
        raise AppError(422, "CASHBOX_NOT_FOUND", "Két quỹ không tồn tại.")

    # Key đã dùng trước đó và còn sống trong DB (bền vững qua restart, R2):
    # replay phiếu cũ, không tạo phiếu trùng. Tra trước store in-memory để
    # không bao giờ trả phiếu của user khác cho user này.
    existing = await idempotency.lookup_persisted(db, key, CashRequest)
    if existing is not None:
        return _replay_cash_request(existing, payload, user)

    replay = idempotency.check(key, idempotency.payload_hash(payload))
    if replay is not None:
        return replay[1]

    req = CashRequest(
        id=uuid.uuid4(),
        cashbox_id=cashbox_id,
        kind=kind,
        amount=amount,
        status="draft",
        maker_id=user.id,
        reason=payload.get("reason"),
        version=1,
        created_by=user.id,
        idempotency_key=key,
    )
    db.add(req)
    try:
        await db.commit()
    except IntegrityError:
        # Tranh chấp unique idempotency_key (2 request cùng key chạy song song):
        # request thua rollback rồi replay phiếu của request thắng.
        await db.rollback()
        existing = await idempotency.lookup_persisted(db, key, CashRequest)
        if existing is None:
            raise AppError(
                409,
                "IDEMPOTENCY_KEY_REUSED",
                "Idempotency-Key đã được dùng cho một payload khác",
            ) from None
        return _replay_cash_request(existing, payload, user)
    await db.refresh(req)
    body = _cash_req_out(req)
    idempotency.remember(db, key, idempotency.payload_hash(payload), 201, body)
    return body


# --------------------------------------------------------------------------
# Submit
# --------------------------------------------------------------------------

@router.post("/cash-sim/requests/{request_id}/submit")
async def submit_cash_request(
    request_id: str,
    request: Request,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    req = await _load_request(db, uuid.UUID(request_id))
    if req is None:
        raise AppError(404, "NOT_FOUND", "Phiếu không tồn tại")
    if str(req.maker_id) != str(user.id):
        raise AppError(403, "FORBIDDEN", "Chỉ người lập phiếu mới được gửi đi duyệt.")
    if req.status not in ("draft", "returned"):
        raise AppError(409, "STATE_CONFLICT", f"Không thể gửi phiếu khi đang ở trạng thái {req.status}.")
    _check_if_match(request, req.version)

    req.status = "submitted"
    req.version += 1
    req.submitted_at = _now()
    await db.commit()
    await db.refresh(req)
    await broadcast_approval_event(
        action="submitted",
        request_id=str(req.id),
        kind="cash",
        status="submitted",
        message=f"Phiếu quỹ {req.kind} ({req.id}) đã được gửi duyệt",
        meta={"sub_kind": req.kind, "maker_id": str(user.id), "amount": str(req.amount)},
    )
    return _cash_req_out(req)


# --------------------------------------------------------------------------
# Approve
# --------------------------------------------------------------------------

@router.post("/cash-sim/requests/{request_id}/approve")
async def approve_cash_request(
    request_id: str,
    request: Request,
    payload: ApprovalInput | None = None,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Force post: check quỹ thực, post journal cân, audit + outbox trong tx (docs/06, B08)."""
    # Khoá dòng phiếu: 2 approve đồng thời cùng 1 phiếu thì request thứ 2 phải
    # chờ và thấy trạng thái đã đổi (409) thay vì post 2 journal.
    req = await _load_request(db, uuid.UUID(request_id), for_update=True)
    if req is None:
        raise AppError(404, "NOT_FOUND", "Phiếu không tồn tại")
    if str(req.maker_id) == str(user.id):
        raise AppError(403, "SELF_APPROVAL_FORBIDDEN", "Bạn không được tự duyệt phiếu của chính mình.")
    caps = await _user_capabilities(db, user.id)
    if "cash:approve_request" not in caps:
        raise AppError(403, "FORBIDDEN", "Bạn không có quyền duyệt phiếu quỹ.")
    # Bút toán điều chỉnh tài chính (chiều RA) -> cần `cash:post_adjustment`.
    if str(req.kind) in _ADJUSTMENT_KINDS and not any(
        c in caps for c in _ADJUSTMENT_CAPS
    ):
        raise AppError(
            403,
            "FORBIDDEN",
            "Bạn không có quyền duyệt bút toán điều chỉnh tài chính "
            f"({', '.join(_ADJUSTMENT_CAPS)}).",
        )
    # Chiều TĂNG quỹ (`receipt` / `adjustment_in`) cũng là bút toán tài chính:
    # người DUYỆT là người làm số dư tăng -> phải có `cash:post_adjustment`.
    # Không có quyền này thì user chỉ có `cash:create_request` /
    # `cash:approve_request` vẫn có thể làm số dư quỹ TĂNG -> lỗ hổng phân
    # quyền chiều tăng (D2).
    if _is_money_in_kind(req.kind) and not any(c in caps for c in _ADJUSTMENT_CAPS):
        raise AppError(
            403,
            "FORBIDDEN",
            "Duyệt phiếu làm TĂNG số dư quỹ cần quyền ghi bút toán tài chính "
            f"({', '.join(_ADJUSTMENT_CAPS)}).",
        )
    if req.status != "submitted":
        raise AppError(409, "STATE_CONFLICT", f"Không thể duyệt phiếu khi đang ở trạng thái {req.status}.")
    _check_if_match(request, req.version)

    # Khoá dòng số dư (SELECT ... FOR UPDATE) trước khi kiểm tra & ghi: hai
    # checker approve đồng thời không được cùng đọc một số dư rồi cùng ghi
    # (double-spend, R1).
    box = await _balance_for_box(db, req.cashbox_id, for_update=True)
    if box is None:
        raise AppError(404, "CASHBOX_NOT_FOUND", "Két quỹ không tồn tại.")
    amount = Decimal(str(req.amount))
    is_receipt = req.kind == "receipt"
    # Chiều TĂNG quỹ = tiền VÀO két (`receipt`, `adjustment_in`); chiều còn
    # lại = tiền RA két (`payment`, `adjustment`).
    money_in = is_receipt or _is_money_in_kind(req.kind)
    # Chi (payment/adjustment) mới cần quỹ đủ; thu (receipt) là tiền VÀO quỹ.
    if not money_in and Decimal(str(box.amount)) < amount:
        raise AppError(
            409, "INSUFFICIENT_SIM_CASH", "quỹ trong box không đủ để hoàn tất",
            {"current_amount": str(box.amount), "requested": str(amount)},
        )

    from app.ai.assessment import assess_request_heuristic

    risk = assess_request_heuristic({
        "request_id": str(req.id),
        "kind": "cash",
        "amount_or_qty": str(req.amount),
        "maker": str(req.maker_id),
        "reason": req.reason or "",
    })
    verify_supervisor_pin(
        payload.supervisor_pin if payload else None,
        settings,
        required=risk["risk_level"] == "high",
        user=user,
    )



    cid = uuid.uuid4().hex[:12]
    now = _now()
    journal = CashJournal(
        id=uuid.uuid4(),
        request_id=req.id,
        posted_at=now,
        correlation_id=cid,
        reversal_of=None,
    )
    db.add(journal)
    await db.flush()

    if money_in:
        # Thu: debit SIM_CASH (quỹ tăng), credit SIM_OFFSET (nguồn đối ứng).
        debit = _cash_entry(journal.id, f"{_SIM_CASH_PREFIX}{req.cashbox_id}", amount, _ZERO)
        credit = _cash_entry(journal.id, _SIM_OFFSET, _ZERO, amount)
    else:
        # Chi: debit SIM_OFFSET, credit SIM_CASH (quỹ giảm).
        debit = _cash_entry(journal.id, _SIM_OFFSET, amount, _ZERO)
        credit = _cash_entry(journal.id, f"{_SIM_CASH_PREFIX}{req.cashbox_id}", _ZERO, amount)

    db.add(debit)
    db.add(credit)

    box.amount = (
        Decimal(str(box.amount)) + amount
        if money_in
        else Decimal(str(box.amount)) - amount
    )
    box.version += 1
    req.status = "posted"
    req.version += 1
    req.approver_id = user.id
    await _audit(db, user.id, "approve", req)
    await _outbox(db, "cash_request.approved", req, {"correlation_id": cid})

    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise AppError(409, "VERSION_CONFLICT", "Phiếu đã bị thay đổi giữa các concurrent approve (A2)") from None

    record_approval_decision("cash", "approved", req.submitted_at)
    await db.refresh(req)
    await broadcast_approval_event(
        action="approved",
        request_id=str(req.id),
        kind="cash",
        status="posted",
        message=f"Phiếu quỹ {req.kind} ({req.id}) đã được phê duyệt",
        meta={"sub_kind": req.kind, "approver_id": str(user.id), "amount": str(req.amount)},
    )
    return _cash_req_out(req, {"journal_id": str(journal.id)})


# --------------------------------------------------------------------------
# Reject
# --------------------------------------------------------------------------

@router.post("/cash-sim/requests/{request_id}/reject")
async def reject_cash_request(
    request_id: str,
    request: Request,
    payload: dict[str, Any] | None = None,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    req = await _load_request(db, uuid.UUID(request_id))
    if req is None:
        raise AppError(404, "NOT_FOUND", "Phiếu không tồn tại")
    if str(req.maker_id) == str(user.id):
        raise AppError(403, "SELF_APPROVAL_FORBIDDEN", "Bạn không được tự từ chối phiếu của chính mình.")
    caps = await _user_capabilities(db, user.id)
    if "cash:approve_request" not in caps:
        raise AppError(403, "FORBIDDEN", "Bạn không có quyền duyệt phiếu quỹ.")
    if req.status != "submitted":
        raise AppError(409, "STATE_CONFLICT", f"Không thể từ chối phiếu khi đang ở trạng thái {req.status}.")
    _check_if_match(request, req.version)

    if payload and payload.get("reason"):
        req.reason = str(payload["reason"])
    req.status = "rejected"
    req.version += 1
    req.approver_id = user.id
    await db.commit()
    record_approval_decision("cash", "rejected", req.submitted_at)
    await db.refresh(req)
    await broadcast_approval_event(
        action="rejected",
        request_id=str(req.id),
        kind="cash",
        status="rejected",
        message=f"Phiếu quỹ {req.kind} ({req.id}) đã bị từ chối",
        meta={"sub_kind": req.kind, "approver_id": str(user.id), "reason": req.reason},
    )
    return _cash_req_out(req)


@router.post("/cash-sim/requests/{request_id}/return")
async def return_cash_request(
    request_id: str,
    request: Request,
    payload: dict[str, Any] | None = None,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    req = await _load_request(db, uuid.UUID(request_id))
    if req is None:
        raise AppError(404, "NOT_FOUND", "Phiếu không tồn tại")
    if str(req.maker_id) == str(user.id):
        raise AppError(403, "SELF_APPROVAL_FORBIDDEN", "Bạn không được tự trả về phiếu của chính mình.")
    caps = await _user_capabilities(db, user.id)
    if "cash:approve_request" not in caps:
        raise AppError(403, "FORBIDDEN", "Bạn không có quyền duyệt phiếu quỹ.")
    if req.status != "submitted":
        raise AppError(409, "STATE_CONFLICT", f"Không thể trả lại phiếu khi đang ở trạng thái {req.status}.")
    _check_if_match(request, req.version)

    reason = str(payload.get("reason", "")).strip() if payload else ""
    if len(reason) < 3:
        raise AppError(422, "MISSING_REASON", "Lý do trả về yêu cầu chỉnh sửa phải có ít nhất 3 ký tự")

    req.status = "returned"
    req.return_reason = reason
    req.version += 1
    req.approver_id = user.id
    await db.commit()
    await db.refresh(req)
    await broadcast_approval_event(
        action="returned",
        request_id=str(req.id),
        kind="cash",
        status="returned",
        message=f"Phiếu quỹ {req.kind} ({req.id}) đã được trả về để chỉnh sửa",
        meta={"sub_kind": req.kind, "approver_id": str(user.id), "reason": reason},
    )
    return _cash_req_out(req)


# --------------------------------------------------------------------------
# Reverse
# --------------------------------------------------------------------------

@router.post("/cash-sim/requests/{request_id}/reverse")
async def reverse_cash_request(
    request_id: str,
    request: Request,
    payload: dict[str, Any] | None = None,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Reversal = journal mới, debit/credit ngược lại, original nguyên vẹn (C3, docs/05)."""
    key = _require_key(request)
    req = await _load_request(db, uuid.UUID(request_id))
    if req is None:
        raise AppError(404, "NOT_FOUND", "Phiếu không tồn tại")
    caps = await _user_capabilities(db, user.id)
    # Đảo giao dịch = post journal -> KHÔNG được bằng quyền đối soát
    # (`cash:reconcile` chỉ đọc/đối soát, không ghi ledger).
    if not ({"cash:create_request", "cash:approve_request"} | set(_ADJUSTMENT_CAPS)) & caps:
        raise AppError(
            403,
            "FORBIDDEN",
            "Bạn không có quyền đảo giao dịch quỹ "
            "(cần cash:create_request / cash:approve_request).",
        )
    if str(req.kind) in _ADJUSTMENT_KINDS and not any(
        c in caps for c in _ADJUSTMENT_CAPS
    ):
        raise AppError(
            403,
            "FORBIDDEN",
            "Bạn không có quyền đảo bút toán điều chỉnh tài chính "
            f"({', '.join(_ADJUSTMENT_CAPS)}).",
        )
    # Đảo phiếu làm TĂNG quỹ (gốc là phiếu chi `payment`/`adjustment`) ->
    # người đảo là người làm số dư tăng -> cần `cash:post_adjustment`.
    original_money_in = _is_money_in_kind(req.kind)
    if not original_money_in and not any(c in caps for c in _ADJUSTMENT_CAPS):
        raise AppError(
            403,
            "FORBIDDEN",
            "Đảo phiếu làm TĂNG số dư quỹ cần quyền ghi bút toán tài chính "
            f"({', '.join(_ADJUSTMENT_CAPS)}).",
        )
    if req.status != "posted":
        raise AppError(409, "STATE_CONFLICT", f"Không thể đảo giao dịch khi đang ở trạng thái {req.status}.")
    _check_if_match(request, req.version)

    orig_j = (
        await db.execute(select(CashJournal).where(CashJournal.request_id == req.id))
    ).scalar_one_or_none()
    if orig_j is None:
        raise AppError(404, "JOURNAL_NOT_FOUND", "Không tìm thấy journal gốc")

    box = await _balance_for_box(db, req.cashbox_id, for_update=True)
    if box is None:
        raise AppError(404, "CASHBOX_NOT_FOUND", "Két quỹ không tồn tại.")
    amount = Decimal(str(req.amount))
    # Đảo phiếu gốc làm TĂNG quỹ (`receipt`, `adjustment_in`) -> đảo lại làm
    # GIẢM quỹ (cần đủ tiền trong két). Ngược lại, đảo phiếu chi làm TĂNG quỹ.
    if original_money_in and Decimal(str(box.amount)) < amount:
        raise AppError(409, "INSUFFICIENT_SIM_CASH", "Quỹ không đủ để đảo bút toán thu.")

    now = _now()
    base = req.id.hex[:8]
    rev_req = CashRequest(
        id=uuid.uuid4(),
        cashbox_id=req.cashbox_id,
        kind="reversal",
        amount=amount,
        status="posted",
        maker_id=user.id,
        approver_id=req.approver_id or user.id,
        reason=(payload or {}).get("reason") or f"Reversal of {req.id}",
        version=1,
        created_by=user.id,
    )
    db.add(rev_req)
    await db.flush()

    rev_j = CashJournal(
        id=uuid.uuid4(),
        request_id=rev_req.id,
        posted_at=now,
        correlation_id=base,
        reversal_of=orig_j.id,
    )
    db.add(rev_j)
    await db.flush()

    if original_money_in:
        # Đảo phiếu thu: debit SIM_OFFSET, credit SIM_CASH (quỹ giảm lại).
        debit = _cash_entry(rev_j.id, _SIM_OFFSET, amount, _ZERO)
        credit = _cash_entry(rev_j.id, f"{_SIM_CASH_PREFIX}{req.cashbox_id}", _ZERO, amount)
        box.amount = Decimal(str(box.amount)) - amount
    else:
        # Đảo phiếu chi: debit SIM_CASH, credit SIM_OFFSET (quỹ hoàn lại).
        debit = _cash_entry(rev_j.id, f"{_SIM_CASH_PREFIX}{req.cashbox_id}", amount, _ZERO)
        credit = _cash_entry(rev_j.id, _SIM_OFFSET, _ZERO, amount)
        box.amount = Decimal(str(box.amount)) + amount

    db.add_all([debit, credit])
    box.version += 1
    await _audit(db, user.id, "reverse", rev_req)
    await _outbox(db, "cash_request.reversed", rev_req, {"reversal_of": str(orig_j.id)})

    try:
        await db.commit()
        await db.refresh(rev_j)
    except IntegrityError:
        await db.rollback()
        raise AppError(409, "VERSION_CONFLICT", "Phiếu đã bị thay đổi giữa giao dịch đảo (A2)") from None

    body = {
        "id": str(rev_j.id),
        "request_id": str(req.id),
        "reversal_of": str(orig_j.id),
        "status": "posted",
        "posted_at": rev_j.posted_at.isoformat() if rev_j.posted_at else None,
        "simulation": True,
        "currency": "VND",
    }
    idempotency.remember(db, key, idempotency.payload_hash(payload or {}), 200, body)
    return body


# --------------------------------------------------------------------------
# Audit + Outbox helpers (giữ tính nhất quán với inventory routes)
# --------------------------------------------------------------------------

async def _audit(db: AsyncSession, actor_id, action: str, req: CashRequest) -> None:
    db.add(
        AuditEvent(
            id=uuid.uuid4(),
            actor_id=actor_id,
            action=action,
            subject=f"{_SUBJECT}:{req.id}",
            before_hash=idempotency.payload_hash({"status": req.status}),
            after_hash=idempotency.payload_hash({"status": req.status}),
            occurred_at=datetime.now(UTC),
            metadata_json={"kind": req.kind, "status": req.status},
        )
    )


async def _outbox(db: AsyncSession, event_type: str, req: CashRequest, extra: dict) -> None:
    """Outbox cùng transaction -> worker publish at-least-once (docs/04, B09)."""
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
                "amount": str(req.amount),
                **extra,
            },
            created_at=datetime.now(UTC),
        )
    )


async def _audit_box(
    db: AsyncSession, actor_id, action: str, box: CashBox, extra: dict | None = None
) -> None:
    """Audit thay đổi cấu hình két (S4: mọi ghi vào két đều có dấu vết)."""
    db.add(
        AuditEvent(
            id=uuid.uuid4(),
            actor_id=actor_id,
            action=f"cash_box.{action}",
            subject=f"{_SUBJECT_BOX}:{box.id}",
            before_hash=idempotency.payload_hash(extra or {}),
            after_hash=idempotency.payload_hash(extra or {}),
            occurred_at=datetime.now(UTC),
            metadata_json={"code": box.code, **(extra or {})},
        )
    )


async def _outbox_box(
    db: AsyncSession, event_type: str, box: CashBox, extra: dict | None = None
) -> None:
    db.add(
        OutboxEvent(
            id=uuid.uuid4(),
            event_type=event_type,
            aggregate_id=str(box.id),
            payload_json={
                "subject_type": _SUBJECT_BOX,
                "subject_id": str(box.id),
                "code": box.code,
                "name": box.name,
                "active": box.active,
                **(extra or {}),
            },
            created_at=datetime.now(UTC),
        )
    )
