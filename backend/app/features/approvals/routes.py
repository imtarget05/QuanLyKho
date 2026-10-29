import asyncio
import json
from collections.abc import AsyncGenerator
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes.auth_utils import (
    get_accessible_cashbox_ids,
    get_accessible_location_ids,
    get_user_capabilities,
    get_user_from_token_string,
    require_capability,
)
from app.database import get_db
from app.models.cash_sim import CashRequest
from app.models.iam import User
from app.models.inventory import (
    InventoryRequest,
    InventoryRequestLine,
    Location,
    Stocktake,
    StocktakeLine,
)
from app.services.approval_events import approval_event_bus

router = APIRouter()


@router.get("/inbox")
async def get_approval_inbox(
    current_user=Depends(require_capability("approval:view_inbox")),
    db: AsyncSession = Depends(get_db),
):
    """Get pending approvals for current user (cần capability approve — docs/06)."""
    users = {
        str(u.id): (u.display_name_demo or u.username)
        for u in (await db.execute(select(User))).scalars().all()
    }
    allowed_location_ids = await get_accessible_location_ids(db, current_user)

    inv_stmt = select(InventoryRequest).where(InventoryRequest.status == "submitted")
    if allowed_location_ids is not None:
        inv_stmt = inv_stmt.where(
            or_(
                InventoryRequest.source_id.in_(allowed_location_ids),
                InventoryRequest.dest_id.in_(allowed_location_ids),
            )
        )
    inv_rows = (await db.execute(inv_stmt.order_by(InventoryRequest.submitted_at.asc()))).scalars().all()

    allowed_cashbox_ids = await get_accessible_cashbox_ids(db, current_user)
    cash_stmt = select(CashRequest).where(CashRequest.status == "submitted")
    if allowed_cashbox_ids is not None:
        cash_stmt = cash_stmt.where(CashRequest.cashbox_id.in_(allowed_cashbox_ids))
    cash_rows = (await db.execute(cash_stmt.order_by(CashRequest.submitted_at.asc()))).scalars().all()

    inv_ids = [r.id for r in inv_rows]
    qty_by_req: dict = {}
    if inv_ids:
        sums = (
            await db.execute(
                select(
                    InventoryRequestLine.request_id,
                    func.coalesce(func.sum(InventoryRequestLine.quantity), 0),
                )
                .where(InventoryRequestLine.request_id.in_(inv_ids))
                .group_by(InventoryRequestLine.request_id)
            )
        ).all()
        qty_by_req = {str(row[0]): row[1] for row in sums}

    approvals = []
    for r in inv_rows:
        if str(r.maker_id) == str(current_user.id):
            continue
        line_count = qty_by_req.get(str(r.id), 0)
        maker_id = str(r.maker_id)

        approvals.append(
            {
                "id": str(r.id),
                "kind": "inventory",
                "sub_kind": r.kind,
                "status": r.status,
                "maker_id": maker_id,
                "maker": users.get(maker_id, maker_id),
                "impact": f"Kho ({r.kind}) · {line_count} đơn vị",
                "approval_detail": {"kind": r.kind, "total_quantity": str(line_count)},
                "detail": r.reason or f"Phiếu kho {r.kind}",
            }
        )

    for r in cash_rows:
        if str(r.maker_id) == str(current_user.id):
            continue
        maker_id = str(r.maker_id)
        approvals.append(
            {
                "id": str(r.id),
                "kind": "cash",
                "sub_kind": r.kind,
                "status": r.status,
                "maker_id": maker_id,
                "maker": users.get(maker_id, maker_id),
                "impact": f"Quỹ ({r.kind}) · {r.amount} VND",
                "detail": r.reason or f"Phiếu quỹ {r.kind}",
            }
        )

    # Ca kiểm kê theo ca đang chờ duyệt (SRS §3.3)
    st_stmt = select(Stocktake).where(Stocktake.status == "submitted")
    if allowed_location_ids is not None:
        st_stmt = st_stmt.where(Stocktake.location_id.in_(allowed_location_ids))
    stocktake_rows = (await db.execute(st_stmt.order_by(Stocktake.created_at.asc()))).scalars().all()

    for st in stocktake_rows:
        if str(st.maker_id) == str(current_user.id):
            continue
        maker_id = str(st.maker_id)
        loc = (
            await db.execute(select(Location).where(Location.id == st.location_id))
        ).scalars().first()
        loc_name = loc.name if loc else "Quầy quầy/kho"
        st_lines = (
            await db.execute(
                select(StocktakeLine).where(StocktakeLine.stocktake_id == st.id)
            )
        ).scalars().all()
        var_count = sum(1 for ln in st_lines if Decimal(str(ln.variance)) != Decimal("0"))
        shift_names = {
            "morning": "Ca Sáng",
            "afternoon": "Ca Chiều",
            "split": "Ca Lỡ ngày",
        }
        shift_title = shift_names.get(st.shift_code or "", "Kiểm kê ca")
        approvals.append(
            {
                "id": str(st.id),
                "kind": "stocktake",
                "sub_kind": st.shift_code or "stocktake",
                "status": st.status,
                "maker_id": maker_id,
                "maker": users.get(maker_id, maker_id),
                "impact": f"{shift_title} ({loc_name}) · {var_count} món lệch",
                "approval_detail": {
                    "kind": "stocktake",
                    "shift_code": st.shift_code,
                    "location_id": str(st.location_id),
                    "variance_count": var_count,
                    "location_name": loc_name,
                },
                "detail": st.note or f"Kiểm kê {shift_title} ngày {st.business_date or ''}",
            }
        )

    return {"approvals": approvals}


async def approval_event_generator(request: Request, user: User) -> AsyncGenerator[str, None]:
    queue = await approval_event_bus.subscribe()
    try:
        init_payload = json.dumps(
            {"status": "connected", "username": user.username, "user_id": str(user.id)},
            ensure_ascii=False,
        )
        yield f"event: connected\ndata: {init_payload}\n\n"
        while True:
            if await request.is_disconnected():
                break
            try:
                payload = await asyncio.wait_for(queue.get(), timeout=15.0)
                yield f"event: approval_update\ndata: {payload}\n\n"
            except TimeoutError:
                yield ": keepalive ping\n\n"
    finally:
        await approval_event_bus.unsubscribe(queue)


@router.get("/stream")
async def stream_approval_events(
    request: Request,
    token: str | None = Query(None, description="JWT access token for EventSource / SSE"),
    db: AsyncSession = Depends(get_db),
):
    """Native Server-Sent Events (SSE) endpoint broadcasting real-time Maker-Checker approvals.

    Allows browser tabs and clients to receive push notifications on approval state changes
    instantly without polling.

    Authentication:
    Accepts JWT access token via query parameter `?token=...` (EventSource standard) or
    `Authorization: Bearer <token>` header.
    """
    raw_token = token
    if not raw_token:
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            raw_token = auth_header[7:].strip()

    if not raw_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication token for SSE stream",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = await get_user_from_token_string(raw_token, db)
    caps = await get_user_capabilities(db, user.id)
    allowed_caps = {"approval:view_inbox", "inventory:view_requests", "cash:view_requests"}
    if not any(c in caps for c in allowed_caps):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User does not have permission to subscribe to approval stream",
        )

    return StreamingResponse(
        approval_event_generator(request, user),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
