"""Exports Routes — Kết xuất và Đồng bộ dữ liệu ra Excel (.xlsx), CSV, Google Sheets.

Cung cấp:
  - GET /exports/catalog: Xuất danh mục hàng hóa (Excel / CSV)
  - GET /exports/balances: Xuất số dư tồn kho theo kho/vị trí (Excel / CSV)
  - GET /exports/movements: Xuất sổ biến động kho / ledger (Excel / CSV)
  - GET /exports/cash-journal: Xuất sổ nhật ký thu chi tiền mặt (Excel / CSV)
  - GET /exports/inventory-summary: Xuất bảng tổng hợp nhập xuất tồn (Excel / CSV)
  - POST /exports/sync-google-sheets: Đẩy dữ liệu bất kỳ trực tiếp lên Google Sheets
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import AppError
from app.api.routes.auth_utils import (
    get_accessible_location_ids,
    get_current_user_with_capabilities,
)
from app.database import get_db
from app.models.cash_sim import CashJournal, CashRequest
from app.models.iam import User
from app.models.inventory import Balance, Item, Location, Movement
from app.services import export_engine, google_sheets_service

router = APIRouter(prefix="/exports", tags=["exports"])

_READ_CAPS = {
    "inventory:view_balances",
    "inventory:manage_catalog",
    "cash:view_balances",
    "cash:reconcile",
    "audit:view",
    "approval:view_inbox",
    "admin:user_management",
    "etl:admin",
    "etl:run",
}


def _verify_export_permission(caps: list[str]) -> None:
    if not any(c in _READ_CAPS for c in caps):
        raise AppError(403, "FORBIDDEN", "Bạn không có quyền kết xuất dữ liệu.")


def _parse_iso_date(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt
    except ValueError:
        raise AppError(422, "INVALID_DATE", f"Ngày {raw!r} không đúng chuẩn ISO-8601") from None


def _format_response(
    rows: list[dict[str, Any]],
    headers: list[tuple[str, str]],
    title: str,
    filename_prefix: str,
    export_format: str,
) -> Response:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base_name = f"{filename_prefix}_{timestamp}"

    if export_format == "csv":
        csv_content = export_engine.generate_csv(rows, headers)
        encoded = csv_content.encode("utf-8-sig")
        return Response(
            content=encoded,
            media_type="text/csv; charset=utf-8",
            headers={
                "Content-Disposition": f"attachment; filename=\"{base_name}.csv\"; filename*=UTF-8''{quote(base_name)}.csv"
            },
        )

    # Excel (.xlsx)
    xlsx_bytes = export_engine.generate_xlsx(rows, headers, title=title)
    return Response(
        content=xlsx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f"attachment; filename=\"{base_name}.xlsx\"; filename*=UTF-8''{quote(base_name)}.xlsx"
        },
    )


# --------------------------------------------------------------------------
# 1. Export Catalog (Danh mục hàng hóa)
# --------------------------------------------------------------------------
@router.get("/catalog")
async def export_catalog(
    format: str = Query("xlsx", pattern="^(xlsx|csv)$"),
    user_caps: tuple[User, list[str]] = Depends(get_current_user_with_capabilities),
    db: AsyncSession = Depends(get_db),
):
    _, caps = user_caps
    _verify_export_permission(caps)

    stmt = select(Item).order_by(Item.sku)
    items = (await db.execute(stmt)).scalars().all()

    headers, rows = export_engine.serialize_catalog_dataset(items)
    return _format_response(rows, headers, "Danh Mục Hàng Hoá & Nguyên Liệu", "DanhMuc_HangHoa", format)


# --------------------------------------------------------------------------
# 2. Export Balances (Tồn kho theo vị trí)
# --------------------------------------------------------------------------
@router.get("/balances")
async def export_balances(
    format: str = Query("xlsx", pattern="^(xlsx|csv)$"),
    location_id: str | None = None,
    user_caps: tuple[User, list[str]] = Depends(get_current_user_with_capabilities),
    db: AsyncSession = Depends(get_db),
):
    user, caps = user_caps
    _verify_export_permission(caps)

    allowed_locations = await get_accessible_location_ids(db, user.id, caps)

    stmt = (
        select(Balance, Item, Location)
        .join(Item, Balance.item_id == Item.id)
        .join(Location, Balance.location_id == Location.id)
        .order_by(Location.name, Item.sku)
    )

    if location_id:
        loc_uuid = uuid.UUID(location_id)
        if allowed_locations is not None and loc_uuid not in allowed_locations:
            raise AppError(403, "SCOPE_FORBIDDEN", "Không có quyền xem kho này.")
        stmt = stmt.where(Balance.location_id == loc_uuid)
    elif allowed_locations is not None:
        stmt = stmt.where(Balance.location_id.in_(allowed_locations))

    records = (await db.execute(stmt)).all()
    headers, rows = export_engine.serialize_balances_dataset(records)
    return _format_response(rows, headers, "Báo Cáo Tồn Kho Thực Tế", "TonKho_ChiTiet", format)


# --------------------------------------------------------------------------
# 3. Export Movements (Sổ biến động kho)
# --------------------------------------------------------------------------
@router.get("/movements")
async def export_movements(
    format: str = Query("xlsx", pattern="^(xlsx|csv)$"),
    location_id: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
    user_caps: tuple[User, list[str]] = Depends(get_current_user_with_capabilities),
    db: AsyncSession = Depends(get_db),
):
    user, caps = user_caps
    _verify_export_permission(caps)

    allowed_locations = await get_accessible_location_ids(db, user.id, caps)

    stmt = (
        select(Movement, Item, Location)
        .join(Item, Movement.item_id == Item.id)
        .join(Location, Movement.location_id == Location.id)
        .order_by(desc(Movement.posted_at))
    )

    if location_id:
        loc_uuid = uuid.UUID(location_id)
        if allowed_locations is not None and loc_uuid not in allowed_locations:
            raise AppError(403, "SCOPE_FORBIDDEN", "Không có quyền xem kho này.")
        stmt = stmt.where(Movement.location_id == loc_uuid)
    elif allowed_locations is not None:
        stmt = stmt.where(Movement.location_id.in_(allowed_locations))

    dt_from = _parse_iso_date(from_date)
    dt_to = _parse_iso_date(to_date)
    if dt_from:
        stmt = stmt.where(Movement.posted_at >= dt_from)
    if dt_to:
        stmt = stmt.where(Movement.posted_at <= dt_to)

    records = (await db.execute(stmt)).all()
    headers, rows = export_engine.serialize_movements_dataset(records)
    return _format_response(rows, headers, "Sổ Nhật Ký Biến Động Kho", "BienDong_Kho", format)


# --------------------------------------------------------------------------
# 4. Export Cash Journal (Sổ quỹ & Thu chi)
# --------------------------------------------------------------------------
@router.get("/cash-journal")
async def export_cash_journal(
    format: str = Query("xlsx", pattern="^(xlsx|csv)$"),
    from_date: str | None = None,
    to_date: str | None = None,
    user_caps: tuple[User, list[str]] = Depends(get_current_user_with_capabilities),
    db: AsyncSession = Depends(get_db),
):
    _, caps = user_caps
    _verify_export_permission(caps)

    stmt = (
        select(CashJournal, CashRequest)
        .outerjoin(CashRequest, CashJournal.request_id == CashRequest.id)
        .order_by(desc(CashJournal.posted_at))
    )

    dt_from = _parse_iso_date(from_date)
    dt_to = _parse_iso_date(to_date)
    if dt_from:
        stmt = stmt.where(CashJournal.posted_at >= dt_from)
    if dt_to:
        stmt = stmt.where(CashJournal.posted_at <= dt_to)

    records = (await db.execute(stmt)).all()
    headers, rows = export_engine.serialize_cash_journal_dataset(records)
    return _format_response(rows, headers, "Sổ Quỹ Tiền Mặt & Nhật Ký Giao Dịch", "SoQuy_TienMat", format)


# --------------------------------------------------------------------------
# 5. Export Inventory Summary (Tổng hợp Nhập - Xuất - Tồn)
# --------------------------------------------------------------------------
@router.get("/inventory-summary")
async def export_inventory_summary(
    format: str = Query("xlsx", pattern="^(xlsx|csv)$"),
    location_id: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
    user_caps: tuple[User, list[str]] = Depends(get_current_user_with_capabilities),
    db: AsyncSession = Depends(get_db),
):
    user, caps = user_caps
    _verify_export_permission(caps)

    # Đọc danh sách movements để tổng hợp
    stmt = select(Movement).order_by(Movement.posted_at)
    if location_id:
        stmt = stmt.where(Movement.location_id == uuid.UUID(location_id))
    dt_from = _parse_iso_date(from_date)
    dt_to = _parse_iso_date(to_date)
    if dt_from:
        stmt = stmt.where(Movement.posted_at >= dt_from)
    if dt_to:
        stmt = stmt.where(Movement.posted_at <= dt_to)

    movements = (await db.execute(stmt)).scalars().all()

    # Nhóm theo ngày (bucket)
    buckets: dict[str, dict[str, Any]] = {}
    for mv in movements:
        day_str = (mv.posted_at or mv.created_at).strftime("%Y-%m-%d")
        if day_str not in buckets:
            buckets[day_str] = {
                "bucket": day_str,
                "inbound_qty": 0.0,
                "outbound_qty": 0.0,
                "net_qty": 0.0,
                "receipt_count": 0,
                "issue_count": 0,
            }
        b = buckets[day_str]
        qty = float(mv.quantity_signed or 0)
        if qty > 0:
            b["inbound_qty"] += qty
            b["receipt_count"] += 1
        else:
            b["outbound_qty"] += abs(qty)
            b["issue_count"] += 1
        b["net_qty"] += qty

    summary_list = list(buckets.values())
    headers, rows = export_engine.serialize_inventory_summary_dataset(summary_list)
    return _format_response(rows, headers, "Báo Cáo Tổng Hợp Nhập Xuất Tồn", "TongHop_NhapXuatTon", format)


# --------------------------------------------------------------------------
# 6. Sync Out to Google Sheets
# --------------------------------------------------------------------------
class SyncGoogleSheetsInput(BaseModel):
    dataset: str = Field(..., pattern="^(catalog|balances|movements|cash_journal|inventory_summary)$")
    sheet_url_or_id: str = Field(..., min_length=1)
    tab: str = Field(default="Sheet1")
    location_id: str | None = None
    from_date: str | None = None
    to_date: str | None = None
    webhook_url: str | None = None


@router.post("/sync-google-sheets")
async def sync_to_google_sheets(
    payload: SyncGoogleSheetsInput,
    user_caps: tuple[User, list[str]] = Depends(get_current_user_with_capabilities),
    db: AsyncSession = Depends(get_db),
):
    user, caps = user_caps
    _verify_export_permission(caps)

    headers: list[tuple[str, str]] = []
    rows: list[dict[str, Any]] = []

    if payload.dataset == "catalog":
        items = (await db.execute(select(Item).order_by(Item.sku))).scalars().all()
        headers, rows = export_engine.serialize_catalog_dataset(items)
    elif payload.dataset == "balances":
        stmt = select(Balance, Item, Location).join(Item, Balance.item_id == Item.id).join(Location, Balance.location_id == Location.id)
        if payload.location_id:
            stmt = stmt.where(Balance.location_id == uuid.UUID(payload.location_id))
        records = (await db.execute(stmt)).all()
        headers, rows = export_engine.serialize_balances_dataset(records)
    elif payload.dataset == "movements":
        stmt = select(Movement, Item, Location).join(Item, Movement.item_id == Item.id).join(Location, Movement.location_id == Location.id).order_by(desc(Movement.posted_at))
        if payload.location_id:
            stmt = stmt.where(Movement.location_id == uuid.UUID(payload.location_id))
        records = (await db.execute(stmt)).all()
        headers, rows = export_engine.serialize_movements_dataset(records)
    elif payload.dataset == "cash_journal":
        records = (await db.execute(select(CashJournal, CashRequest).outerjoin(CashRequest, CashJournal.request_id == CashRequest.id).order_by(desc(CashJournal.posted_at)))).all()
        headers, rows = export_engine.serialize_cash_journal_dataset(records)
    elif payload.dataset == "inventory_summary":
        movements = (await db.execute(select(Movement))).scalars().all()
        buckets: dict[str, dict[str, Any]] = {}
        for mv in movements:
            day_str = (mv.posted_at or mv.created_at).strftime("%Y-%m-%d")
            if day_str not in buckets:
                buckets[day_str] = {"bucket": day_str, "inbound_qty": 0.0, "outbound_qty": 0.0, "net_qty": 0.0, "receipt_count": 0, "issue_count": 0}
            b = buckets[day_str]
            qty = float(mv.quantity_signed or 0)
            if qty > 0:
                b["inbound_qty"] += qty
                b["receipt_count"] += 1
            else:
                b["outbound_qty"] += abs(qty)
                b["issue_count"] += 1
            b["net_qty"] += qty
        headers, rows = export_engine.serialize_inventory_summary_dataset(list(buckets.values()))

    result = await google_sheets_service.sync_out_to_google_sheet(
        url_or_id=payload.sheet_url_or_id,
        tab=payload.tab,
        headers=headers,
        rows=rows,
        webhook_url=payload.webhook_url,
    )
    return result
