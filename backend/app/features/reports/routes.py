"""Reports routes — aggregation readonly cho biểu đồ ngày/tháng (Track A).

Mọi endpoint là read-only trên ledger/movement đã post: không tạo write,
không đổi số dư. Decimal giữ dạng string tới client để không mất chính xác.
"""
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes.auth_utils import (
    get_accessible_cashbox_ids,
    get_accessible_location_ids,
    require_any_capability,
)
from app.database import get_db
from app.models.cash_sim import CashEntry, CashJournal, CashRequest
from app.models.inventory import Balance, InventoryRequest, Item, Movement

router = APIRouter()

_READ_CAPS = (
    "inventory:view_balances",
    "inventory:manage_catalog",
    "cash:view_balances",
    "cash:reconcile",
    "audit:view",
    "approval:view_inbox",
)

_WATCH_DEFAULT = 30
_STAGNANT_DEFAULT = 60
_CRITICAL_DEFAULT = 90


def _parse_date(raw: str | None, field: str) -> datetime | None:
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError:
        from app.api.errors import AppError

        raise AppError(422, "INVALID_DATE", f"{field} phải ISO-8601, nhận {raw!r}") from None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt


def _narrow_to_location(
    allowed_location_ids: set[uuid.UUID] | None, location_id: str
) -> set[uuid.UUID] | None:
    """Thu hẹp phạm vi location theo tham số truy vấn, KHÔNG bao giờ mở rộng.

    - Admin (``allowed_location_ids is None``) xem được mọi location, nên
      tham số ``location_id`` chỉ lọc kết quả.
    - User thường bị giới hạn bởi scope: ``location_id`` phải nằm trong scope,
      nếu không thì phạm vi rỗng => không thấy dữ liệu nào.
    """
    try:
        requested = uuid.UUID(str(location_id))
    except (ValueError, AttributeError, TypeError):
        # `location_id` sai định dạng: coi như không khớp location nào.
        return set()

    if allowed_location_ids is None:
        return {requested}
    return allowed_location_ids & {requested}


def _severity(days: int | None, watch: int, stagnant: int, critical: int) -> str:
    if days is None:
        return "critical"
    if days >= critical:
        return "critical"
    if days >= stagnant:
        return "stagnant"
    if days >= watch:
        return "watch"
    return "normal"

@router.get("/inventory-daily")
async def inventory_daily(
    current_user=Depends(require_any_capability(*_READ_CAPS)),
    db: AsyncSession = Depends(get_db),
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
):
    """Nhập/xuất/tồn theo ngày từ Movement đã post (nguồn sự thật)."""
    from datetime import date
    from decimal import Decimal

    df, dt = _parse_date(date_from, "date_from"), _parse_date(date_to, "date_to")
    stmt = select(Movement)
    if df:
        stmt = stmt.where(Movement.posted_at >= df)
    if dt:
        stmt = stmt.where(Movement.posted_at <= dt)
    allowed_location_ids = await get_accessible_location_ids(db, current_user)
    if allowed_location_ids is not None:
        stmt = stmt.where(Movement.location_id.in_(allowed_location_ids))
    moves = (await db.execute(stmt)).scalars().all()
    buckets: dict[str, dict] = {}
    for m in moves:
        day = (m.posted_at.date() if m.posted_at else date.today()).isoformat()
        b = buckets.setdefault(
            day,
            {
                "inbound": Decimal("0"),
                "inbound_cost": Decimal("0"),
                "outbound": Decimal("0"),
                "outbound_cost": Decimal("0"),
                "outbound_sale_qty": Decimal("0"),
                "outbound_sale_cost": Decimal("0"),
                "outbound_spoilage_qty": Decimal("0"),
                "outbound_spoilage_cost": Decimal("0"),
                "outbound_internal_qty": Decimal("0"),
                "outbound_internal_cost": Decimal("0"),
                "outbound_transfer_qty": Decimal("0"),
                "outbound_transfer_cost": Decimal("0"),
                "net": Decimal("0"),
            },
        )
        qty = Decimal(str(m.quantity_signed))
        cost = Decimal(str(getattr(m, "cost_amount", None) or 0))
        if qty >= 0:
            b["inbound"] += qty
            b["inbound_cost"] += cost
        else:
            out_qty = -qty
            b["outbound"] += out_qty
            b["outbound_cost"] += cost
            sub = str(getattr(m, "sub_kind", None) or "sale").lower()
            if sub == "spoilage":
                b["outbound_spoilage_qty"] += out_qty
                b["outbound_spoilage_cost"] += cost
            elif sub == "internal":
                b["outbound_internal_qty"] += out_qty
                b["outbound_internal_cost"] += cost
            elif sub == "transfer":
                b["outbound_transfer_qty"] += out_qty
                b["outbound_transfer_cost"] += cost
            else:
                b["outbound_sale_qty"] += out_qty
                b["outbound_sale_cost"] += cost
        b["net"] += qty
    # Đếm phiếu theo ngày tạo để đối chiếu với movement.
    req_stmt = select(InventoryRequest)
    if df:
        req_stmt = req_stmt.where(InventoryRequest.created_at >= df)
    if dt:
        req_stmt = req_stmt.where(InventoryRequest.created_at <= dt)
    reqs = (await db.execute(req_stmt)).scalars().all()
    counts: dict[str, dict] = {}
    for r in reqs:
        day = (r.created_at.date() if r.created_at else date.today()).isoformat()
        c = counts.setdefault(day, {"receipt": 0, "issue": 0})
        if r.kind == "receipt":
            c["receipt"] += 1
        elif r.kind == "issue":
            c["issue"] += 1
    out = []
    for day in sorted(set(buckets) | set(counts)):
        b = buckets.get(
            day,
            {
                "inbound": Decimal("0"),
                "inbound_cost": Decimal("0"),
                "outbound": Decimal("0"),
                "outbound_cost": Decimal("0"),
                "outbound_sale_qty": Decimal("0"),
                "outbound_sale_cost": Decimal("0"),
                "outbound_spoilage_qty": Decimal("0"),
                "outbound_spoilage_cost": Decimal("0"),
                "outbound_internal_qty": Decimal("0"),
                "outbound_internal_cost": Decimal("0"),
                "outbound_transfer_qty": Decimal("0"),
                "outbound_transfer_cost": Decimal("0"),
                "net": Decimal("0"),
            },
        )
        c = counts.get(day, {"receipt": 0, "issue": 0})
        out.append(
            {
                "bucket": day,
                "inbound_qty": str(b["inbound"]),
                "inbound_cost": str(b["inbound_cost"].quantize(Decimal("0.01"))),
                "outbound_qty": str(b["outbound"]),
                "outbound_cost": str(b["outbound_cost"].quantize(Decimal("0.01"))),
                "outbound_sale_qty": str(b["outbound_sale_qty"]),
                "outbound_sale_cost": str(b["outbound_sale_cost"].quantize(Decimal("0.01"))),
                "outbound_spoilage_qty": str(b["outbound_spoilage_qty"]),
                "outbound_spoilage_cost": str(b["outbound_spoilage_cost"].quantize(Decimal("0.01"))),
                "outbound_internal_qty": str(b["outbound_internal_qty"]),
                "outbound_internal_cost": str(b["outbound_internal_cost"].quantize(Decimal("0.01"))),
                "outbound_transfer_qty": str(b["outbound_transfer_qty"]),
                "outbound_transfer_cost": str(b["outbound_transfer_cost"].quantize(Decimal("0.01"))),
                "net_qty": str(b["net"]),
                "receipt_count": c["receipt"],
                "issue_count": c["issue"],
            }
        )
    return {"buckets": out, "unit": "quantity", "simulation": True}


@router.get("/inventory-monthly")
async def inventory_monthly(
    current_user=Depends(require_any_capability(*_READ_CAPS)),
    db: AsyncSession = Depends(get_db),
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
):
    """Gộp buckets ngày thành tháng (YYYY-MM) kèm phân rã loại xuất."""
    daily = await inventory_daily(current_user, db, date_from, date_to)
    months: dict[str, dict] = {}
    from decimal import Decimal

    for b in daily["buckets"]:
        key = b["bucket"][:7]
        m = months.setdefault(
            key,
            {
                "inbound": Decimal("0"),
                "inbound_cost": Decimal("0"),
                "outbound": Decimal("0"),
                "outbound_cost": Decimal("0"),
                "outbound_sale_qty": Decimal("0"),
                "outbound_sale_cost": Decimal("0"),
                "outbound_spoilage_qty": Decimal("0"),
                "outbound_spoilage_cost": Decimal("0"),
                "outbound_internal_qty": Decimal("0"),
                "outbound_internal_cost": Decimal("0"),
                "outbound_transfer_qty": Decimal("0"),
                "outbound_transfer_cost": Decimal("0"),
                "net": Decimal("0"),
                "receipt": 0,
                "issue": 0,
            },
        )
        m["inbound"] += Decimal(b["inbound_qty"])
        m["inbound_cost"] += Decimal(b["inbound_cost"])
        m["outbound"] += Decimal(b["outbound_qty"])
        m["outbound_cost"] += Decimal(b["outbound_cost"])
        m["outbound_sale_qty"] += Decimal(b["outbound_sale_qty"])
        m["outbound_sale_cost"] += Decimal(b["outbound_sale_cost"])
        m["outbound_spoilage_qty"] += Decimal(b["outbound_spoilage_qty"])
        m["outbound_spoilage_cost"] += Decimal(b["outbound_spoilage_cost"])
        m["outbound_internal_qty"] += Decimal(b["outbound_internal_qty"])
        m["outbound_internal_cost"] += Decimal(b["outbound_internal_cost"])
        m["outbound_transfer_qty"] += Decimal(b["outbound_transfer_qty"])
        m["outbound_transfer_cost"] += Decimal(b["outbound_transfer_cost"])
        m["net"] += Decimal(b["net_qty"])
        m["receipt"] += b["receipt_count"]
        m["issue"] += b["issue_count"]
    return {
        "buckets": [
            {
                "bucket": k,
                "inbound_qty": str(v["inbound"]),
                "inbound_cost": str(v["inbound_cost"].quantize(Decimal("0.01"))),
                "outbound_qty": str(v["outbound"]),
                "outbound_cost": str(v["outbound_cost"].quantize(Decimal("0.01"))),
                "outbound_sale_qty": str(v["outbound_sale_qty"]),
                "outbound_sale_cost": str(v["outbound_sale_cost"].quantize(Decimal("0.01"))),
                "outbound_spoilage_qty": str(v["outbound_spoilage_qty"]),
                "outbound_spoilage_cost": str(v["outbound_spoilage_cost"].quantize(Decimal("0.01"))),
                "outbound_internal_qty": str(v["outbound_internal_qty"]),
                "outbound_internal_cost": str(v["outbound_internal_cost"].quantize(Decimal("0.01"))),
                "outbound_transfer_qty": str(v["outbound_transfer_qty"]),
                "outbound_transfer_cost": str(v["outbound_transfer_cost"].quantize(Decimal("0.01"))),
                "net_qty": str(v["net"]),
                "receipt_count": v["receipt"],
                "issue_count": v["issue"],
            }
            for k, v in sorted(months.items())
        ],
        "unit": "quantity",
        "simulation": True,
    }


@router.get("/inventory-summary")
async def inventory_summary(
    current_user=Depends(require_any_capability(*_READ_CAPS)),
    db: AsyncSession = Depends(get_db),
    location_id: str | None = Query(default=None),
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
):
    """Báo cáo Nhập-Xuất-Tồn chi tiết theo từng nguyên liệu và phân loại xuất kho."""
    from collections import defaultdict
    from decimal import Decimal

    from app.models.inventory import Balance, Item, Movement

    df, dt = _parse_date(date_from, "date_from"), _parse_date(date_to, "date_to")
    items = {str(i.id): i for i in (await db.execute(select(Item).where(Item.active.is_(True)))).scalars().all()}

    stmt = select(Movement)
    allowed_location_ids = await get_accessible_location_ids(db, current_user)
    if location_id is not None:
        # `location_id` chỉ THU HẸP phạm vi, không được MỞ RỘNG quyền: user
        # chỉ xem được location nằm trong scope của mình.
        allowed_location_ids = _narrow_to_location(allowed_location_ids, location_id)
    if allowed_location_ids is not None:
        stmt = stmt.where(Movement.location_id.in_(allowed_location_ids))
    if df:
        stmt = stmt.where(Movement.posted_at >= df)
    if dt:
        stmt = stmt.where(Movement.posted_at <= dt)
    moves = (await db.execute(stmt)).scalars().all()

    stats = defaultdict(lambda: {
        "inbound_qty": Decimal("0"), "inbound_cost": Decimal("0"),
        "inbound_receipt_qty": Decimal("0"), "inbound_receipt_cost": Decimal("0"),
        "inbound_transfer_qty": Decimal("0"), "inbound_transfer_cost": Decimal("0"),
        "sale_qty": Decimal("0"), "sale_cost": Decimal("0"),
        "spoilage_qty": Decimal("0"), "spoilage_cost": Decimal("0"),
        "internal_qty": Decimal("0"), "internal_cost": Decimal("0"),
        "transfer_qty": Decimal("0"), "transfer_cost": Decimal("0"),
        "total_out_qty": Decimal("0"), "total_out_cost": Decimal("0"),
    })

    for m in moves:
        iid = str(m.item_id)
        qty = Decimal(str(m.quantity_signed))
        cost = Decimal(str(getattr(m, "cost_amount", None) or 0))
        st = stats[iid]
        sub = str(getattr(m, "sub_kind", None) or "receipt").lower()
        if qty >= 0:
            st["inbound_qty"] += qty
            st["inbound_cost"] += cost
            # Phân biệt: nhập từ NCC vs nhập từ chuyển kho
            if sub == "transfer":
                st["inbound_transfer_qty"] += qty
                st["inbound_transfer_cost"] += cost
            else:
                st["inbound_receipt_qty"] += qty
                st["inbound_receipt_cost"] += cost
        else:
            out_qty = -qty
            st["total_out_qty"] += out_qty
            st["total_out_cost"] += cost
            if sub == "spoilage":
                st["spoilage_qty"] += out_qty
                st["spoilage_cost"] += cost
            elif sub == "internal":
                st["internal_qty"] += out_qty
                st["internal_cost"] += cost
            elif sub == "transfer":
                st["transfer_qty"] += out_qty
                st["transfer_cost"] += cost
            else:
                st["sale_qty"] += out_qty
                st["sale_cost"] += cost

    bal_stmt = select(Balance)
    if location_id is not None:
        allowed_location_ids = _narrow_to_location(allowed_location_ids, location_id)
    if allowed_location_ids is not None:
        bal_stmt = bal_stmt.where(Balance.location_id.in_(allowed_location_ids))
    bals = (await db.execute(bal_stmt)).scalars().all()
    closing_map = defaultdict(lambda: Decimal("0"))
    for b in bals:
        closing_map[str(b.item_id)] += Decimal(str(b.quantity or 0))

    rows = []
    for iid, item in sorted(items.items(), key=lambda kv: kv[1].sku):
        st = stats[iid]
        closing_qty = closing_map[iid]
        item_cost = Decimal(str(item.cost_price or 0))
        closing_cost = closing_qty * item_cost
        opening_qty = closing_qty - st["inbound_qty"] + st["total_out_qty"]
        opening_cost = opening_qty * item_cost
        rows.append({
            "item_id": iid,
            "sku": item.sku,
            "item_name": item.name,
            "unit": item.unit,
            "category": item.category,
            "cost_price": str(item_cost),
            "opening_qty": str(opening_qty),
            "opening_cost": str(opening_cost.quantize(Decimal("0.01"))),
            # Tổng nhập (tương thích ngược)
            "inbound_qty": str(st["inbound_qty"]),
            "inbound_cost": str(st["inbound_cost"].quantize(Decimal("0.01"))),
            # Phân loại nhập: mua NCC vs nhận từ chuyển kho
            "inbound_receipt_qty": str(st["inbound_receipt_qty"]),
            "inbound_receipt_cost": str(st["inbound_receipt_cost"].quantize(Decimal("0.01"))),
            "inbound_transfer_qty": str(st["inbound_transfer_qty"]),
            "inbound_transfer_cost": str(st["inbound_transfer_cost"].quantize(Decimal("0.01"))),
            "outbound_sale_qty": str(st["sale_qty"]),
            "outbound_sale_cost": str(st["sale_cost"].quantize(Decimal("0.01"))),
            "outbound_spoilage_qty": str(st["spoilage_qty"]),
            "outbound_spoilage_cost": str(st["spoilage_cost"].quantize(Decimal("0.01"))),
            "outbound_internal_qty": str(st["internal_qty"]),
            "outbound_internal_cost": str(st["internal_cost"].quantize(Decimal("0.01"))),
            "outbound_transfer_qty": str(st["transfer_qty"]),
            "outbound_transfer_cost": str(st["transfer_cost"].quantize(Decimal("0.01"))),
            "total_outbound_qty": str(st["total_out_qty"]),
            "total_outbound_cost": str(st["total_out_cost"].quantize(Decimal("0.01"))),
            "closing_qty": str(closing_qty),
            "closing_cost": str(closing_cost.quantize(Decimal("0.01"))),
        })

    return {"items": rows, "count": len(rows), "simulation": True}


@router.get("/consumption-top")
async def consumption_top(
    current_user=Depends(require_any_capability(*_READ_CAPS)),
    db: AsyncSession = Depends(get_db),
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
    limit: int = Query(default=10, ge=1, le=100),
):
    """Top nguyên liệu tiêu hao (SRS §3.5): tổng Sử dụng theo ca + Movement xuất."""
    from collections import defaultdict
    from decimal import Decimal

    from app.models.inventory import Stocktake, StocktakeLine

    df, dt = _parse_date(date_from, "date_from"), _parse_date(date_to, "date_to")
    used: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    st_stmt = select(Stocktake)
    allowed_location_ids = await get_accessible_location_ids(db, current_user)
    if allowed_location_ids is not None:
        st_stmt = st_stmt.where(Stocktake.location_id.in_(allowed_location_ids))
    if df:
        st_stmt = st_stmt.where(Stocktake.created_at >= df)
    if dt:
        st_stmt = st_stmt.where(Stocktake.created_at <= dt)
    st_ids = [str(s.id) for s in (await db.execute(st_stmt)).scalars().all()]
    if st_ids:
        from sqlalchemy import func as _func

        lines = (
            await db.execute(
                select(StocktakeLine.item_id, _func.sum(StocktakeLine.used_qty)).where(
                    StocktakeLine.stocktake_id.in_(st_ids)
                ).group_by(StocktakeLine.item_id)
            )
        ).all()
        for item_id, total in lines:
            used[str(item_id)] += Decimal(str(total or 0))
    move_stmt = select(Movement).where(Movement.quantity_signed < 0)
    allowed_location_ids = await get_accessible_location_ids(db, current_user)
    if allowed_location_ids is not None:
        move_stmt = move_stmt.where(Movement.location_id.in_(allowed_location_ids))
    if df:
        move_stmt = move_stmt.where(Movement.posted_at >= df)
    if dt:
        move_stmt = move_stmt.where(Movement.posted_at <= dt)
    for m in (await db.execute(move_stmt)).scalars().all():
        used[str(m.item_id)] += -Decimal(str(m.quantity_signed))
    items = {str(i.id): i for i in (await db.execute(select(Item))).scalars().all()}
    ranked = sorted(used.items(), key=lambda kv: kv[1], reverse=True)[:limit]
    return {
        "items": [
            {
                "item_id": item_id,
                "sku": items[item_id].sku if item_id in items else item_id,
                "name": items[item_id].name if item_id in items else item_id,
                "unit": items[item_id].unit if item_id in items else None,
                "category": items[item_id].category if item_id in items else None,
                "used_qty": str(qty),
            }
            for item_id, qty in ranked
        ],
        "simulation": True,
    }


@router.get("/shift-history")
async def shift_history(
    current_user=Depends(require_any_capability(*_READ_CAPS)),
    db: AsyncSession = Depends(get_db),
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
    shift_code: str | None = Query(default=None),
):
    """Lịch sử chốt ca (SRS §3.5): chi tiết từng ca + nhân viên chốt."""
    from decimal import Decimal

    from app.models.iam import User
    from app.models.inventory import Stocktake, StocktakeLine

    df, dt = _parse_date(date_from, "date_from"), _parse_date(date_to, "date_to")
    stmt = select(Stocktake)
    if df:
        stmt = stmt.where(Stocktake.created_at >= df)
    if dt:
        stmt = stmt.where(Stocktake.created_at <= dt)
    allowed_location_ids = await get_accessible_location_ids(db, current_user)
    if allowed_location_ids is not None:
        stmt = stmt.where(Stocktake.location_id.in_(allowed_location_ids))
    if shift_code:
        stmt = stmt.where(Stocktake.shift_code == shift_code)
    shifts = (await db.execute(stmt.order_by(Stocktake.business_date.desc(), Stocktake.created_at.desc()))).scalars().all()
    users = {str(u.id): u for u in (await db.execute(select(User))).scalars().all()}
    out = []
    for s in shifts:
        lines = (
            await db.execute(select(StocktakeLine).where(StocktakeLine.stocktake_id == s.id))
        ).scalars().all()
        total_var = sum((abs(Decimal(str(ln.variance))) for ln in lines), Decimal("0"))
        maker = users.get(str(s.maker_id))
        out.append(
            {
                "id": str(s.id),
                "business_date": s.business_date.isoformat() if s.business_date else None,
                "shift_code": s.shift_code,
                "location_id": str(s.location_id),
                "status": s.status,
                "maker": maker.display_name_demo if maker else str(s.maker_id),
                "line_count": len(lines),
                "variance_lines": sum(1 for ln in lines if Decimal(str(ln.variance)) != 0),
                "total_abs_variance": str(total_var),
                "completed_at": s.completed_at.isoformat() if s.completed_at else None,
            }
        )
    return {"shifts": out, "count": len(out), "simulation": True}


@router.get("/cashflow-daily")
async def cashflow_daily(
    current_user=Depends(require_any_capability(*_READ_CAPS)),
    db: AsyncSession = Depends(get_db),
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
):
    """Thu/chi theo ngày từ journal đã post + entries (double-entry)."""
    from datetime import date
    from decimal import Decimal

    df, dt = _parse_date(date_from, "date_from"), _parse_date(date_to, "date_to")
    stmt = select(CashJournal)
    if df:
        stmt = stmt.where(CashJournal.posted_at >= df)
    if dt:
        stmt = stmt.where(CashJournal.posted_at <= dt)
    allowed_cashbox_ids = await get_accessible_cashbox_ids(db, current_user)
    if allowed_cashbox_ids is not None:
        allowed_requests = (
            await db.execute(
                select(CashRequest.id).where(CashRequest.cashbox_id.in_(allowed_cashbox_ids))
            )
        ).scalars().all()
        stmt = stmt.where(CashJournal.request_id.in_(allowed_requests))
    journals = (await db.execute(stmt)).scalars().all()
    buckets: dict[str, dict] = {}
    for j in journals:
        day = (j.posted_at.date() if j.posted_at else date.today()).isoformat()
        entries = (
            await db.execute(select(CashEntry).where(CashEntry.journal_id == j.id))
        ).scalars().all()
        b = buckets.setdefault(
            day, {"in_": Decimal("0"), "out": Decimal("0"), "n": 0, "is_receipt": 0}
        )
        for e in entries:
            # SIM_CASH debit = tiền vào quỹ; SIM_CASH credit = tiền ra quỹ.
            if e.account_code.startswith("SIM_CASH:"):
                b["in_"] += Decimal(str(e.debit))
                b["out"] += Decimal(str(e.credit))
        b["n"] += 1
    out = []
    for day in sorted(buckets):
        b = buckets[day]
        out.append(
            {
                "bucket": day,
                "total_in": str(b["in_"]),
                "total_out": str(b["out"]),
                "net": str(b["in_"] - b["out"]),
                "journal_count": b["n"],
            }
        )
    return {"buckets": out, "currency": "VND", "simulation": True}


@router.get("/cashflow-monthly")
async def cashflow_monthly(
    current_user=Depends(require_any_capability(*_READ_CAPS)),
    db: AsyncSession = Depends(get_db),
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
):
    """Gộp cashflow ngày thành tháng."""
    daily = await cashflow_daily(current_user, db, date_from, date_to)
    months: dict[str, dict] = {}
    from decimal import Decimal

    for b in daily["buckets"]:
        key = b["bucket"][:7]
        m = months.setdefault(
            key, {"in_": Decimal("0"), "out": Decimal("0"), "n": 0}
        )
        m["in_"] += Decimal(b["total_in"])
        m["out"] += Decimal(b["total_out"])
        m["n"] += b["journal_count"]
    return {
        "buckets": [
            {
                "bucket": k,
                "total_in": str(v["in_"]),
                "total_out": str(v["out"]),
                "net": str(v["in_"] - v["out"]),
                "journal_count": v["n"],
            }
            for k, v in sorted(months.items())
        ],
        "currency": "VND",
        "simulation": True,
    }


@router.get("/stagnation")
async def stagnation(
    current_user=Depends(require_any_capability(*_READ_CAPS)),
    db: AsyncSession = Depends(get_db),
    watch_days: int = Query(default=_WATCH_DEFAULT),
    stagnant_days: int = Query(default=_STAGNANT_DEFAULT),
    critical_days: int = Query(default=_CRITICAL_DEFAULT),
):
    """Hàng tồn đọng: balance>0 + số ngày từ lần issue gần nhất."""
    from datetime import date
    from decimal import Decimal

    allowed_location_ids = await get_accessible_location_ids(db, current_user)
    balances = (await db.execute(select(Balance))).scalars().all()
    if allowed_location_ids is not None:
        balances = [b for b in balances if b.location_id in allowed_location_ids]
    items = {
        str(i.id): i for i in (await db.execute(select(Item))).scalars().all()
    }
    # Lần issue gần nhất theo (item): max posted_at của movement âm.
    last_issue: dict[str, date] = {}
    moves_stmt = select(Movement).where(Movement.quantity_signed < 0)
    if allowed_location_ids is not None:
        moves_stmt = moves_stmt.where(Movement.location_id.in_(allowed_location_ids))
    moves = (await db.execute(moves_stmt)).scalars().all()
    for m in moves:
        if not m.posted_at:
            continue
        key = str(m.item_id)
        day = m.posted_at.date()
        if key not in last_issue or day > last_issue[key]:
            last_issue[key] = day
    today = date.today()
    out = []
    for b in balances:
        qty = Decimal(str(b.quantity))
        if qty <= 0:
            continue
        key = str(b.item_id)
        item = items.get(key)
        last = last_issue.get(key)
        days = (today - last).days if last else None
        out.append(
            {
                "item_id": key,
                "sku": item.sku if item else key,
                "name": item.name if item else key,
                "quantity": str(qty),
                "days_since_last_issue": days,
                "severity": _severity(days, watch_days, stagnant_days, critical_days),
            }
        )
    out.sort(
        key=lambda r: (r["days_since_last_issue"] is not None, r["days_since_last_issue"] or 0),
        reverse=True,
    )
    return {
        "items": out,
        "thresholds": {"watch": watch_days, "stagnant": stagnant_days, "critical": critical_days},
        "simulation": True,
    }
