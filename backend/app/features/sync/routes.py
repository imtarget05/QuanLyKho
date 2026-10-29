"""Maker/checker endpoint for requests to synchronize a store's source data."""
import json
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes.auth_utils import require_capability
from app.database import get_db
from app.models.iam import User
from app.models.sync_request import SyncRequest

router = APIRouter(prefix="/sync", tags=["Source synchronization"])
_SCOPES = {"catalog", "stock_snapshot", "store_master"}


class CreateSyncRequest(BaseModel):
    scope: str
    payload: dict = Field(default_factory=dict)


class DecideSyncRequest(BaseModel):
    note: str | None = Field(default=None, max_length=1000)


def _row(row: SyncRequest) -> dict:
    return {"id": str(row.id), "scope": row.scope, "payload": row.payload,
            "status": row.status, "requested_at": row.created_at.isoformat(),
            "reviewed_at": row.reviewed_at.isoformat() if row.reviewed_at else None,
            "decision_note": row.decision_note}


@router.post("/requests", status_code=status.HTTP_201_CREATED)
async def create_request(body: CreateSyncRequest, user: User = Depends(require_capability("sync:request")), db: AsyncSession = Depends(get_db)):
    if body.scope not in _SCOPES:
        raise HTTPException(422, "Phạm vi đồng bộ không hợp lệ.")
    if len(json.dumps(body.payload, ensure_ascii=False).encode()) > 64_000:
        raise HTTPException(422, "Dữ liệu yêu cầu đồng bộ vượt quá 64 KB.")
    row = SyncRequest(requester_id=user.id, scope=body.scope, payload=body.payload, status="submitted")
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return _row(row)


@router.get("/requests/mine")
async def my_requests(user: User = Depends(require_capability("sync:request")), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(SyncRequest).where(SyncRequest.requester_id == user.id).order_by(SyncRequest.created_at.desc()))).scalars().all()
    return {"requests": [_row(r) for r in rows]}


@router.get("/inbox")
async def approval_inbox(user: User = Depends(require_capability("sync:approve_root")), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(SyncRequest).where(SyncRequest.status == "submitted").order_by(SyncRequest.created_at))).scalars().all()
    return {"requests": [_row(r) for r in rows]}


@router.post("/requests/{request_id}/approve")
async def approve_request(request_id: str, body: DecideSyncRequest, user: User = Depends(require_capability("sync:approve_root")), db: AsyncSession = Depends(get_db)):
    row = await db.get(SyncRequest, request_id)
    if row is None:
        raise HTTPException(404, "Không tìm thấy yêu cầu đồng bộ.")
    if row.requester_id == user.id:
        raise HTTPException(403, "Root không thể tự duyệt yêu cầu do chính mình tạo.")
    if row.status != "submitted":
        raise HTTPException(409, "Yêu cầu đã được xử lý.")
    row.status, row.reviewed_by, row.reviewed_at, row.decision_note = "approved", user.id, datetime.now(UTC), body.note
    await db.commit()
    return _row(row)
