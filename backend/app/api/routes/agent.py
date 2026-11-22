"""SOP agent API (Track D — D1/D2/D4).

    POST /agent/ask                       — hỏi đáp SOP + GraphQL read-only tools
    GET  /agent/hitl/{request_id}         — xem yêu cầu ghi đang chờ duyệt
    POST /agent/hitl/{request_id}/decision — duyệt/từ chối (maker-checker)

Nguyên tắc (ADR 0002):
- Agent chỉ tư vấn. Hành động ghi không bao giờ tự thực thi — luôn đi qua HITL.
- Tool GraphQL là read-only (xem `app.services.agent_tools`), mutation bị chặn
  ở AST guard trước khi executor chạy.
- `/agent/hitl/*` yêu cầu capability duyệt phiếu, không chỉ đăng nhập.
"""

from __future__ import annotations

import time
from typing import Literal

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from app.api.routes.auth_utils import (
    get_current_user,
    require_any_capability,
)
from app.config import settings
from app.models.iam import User
from app.services.ai_agent import (
    decide_write_action,
    get_pending_write_action,
    run_sop_agent,
)

router = APIRouter(prefix="/agent", tags=["agent"])

_windows: dict[str, tuple[float, int]] = {}

_APPROVER_CAPS = (
    "inventory:approve_request",
    "cash:approve_request",
    "approval:view_inbox",
)


class AgentAskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    message: str = Field(min_length=1, max_length=2000)
    provider: str | None = Field(
        default=None,
        description="Provider LLM tuỳ chọn (cloudflare/ollama/...). Mặc định: grounded local.",
    )
    enable_tools: bool = Field(
        default=True,
        description="Bật GraphQL tool read-only (số dư, saga, outbox, audit, health).",
    )


class HitlDecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: Literal["approved", "rejected"]
    note: str | None = Field(default=None, max_length=500)


def _enforce_agent_rate_limit(user: User) -> None:
    """Rate limit per-process theo user (demo deployment)."""
    now = time.monotonic()
    key = str(user.id)
    start, count = _windows.get(key, (now, 0))
    if now - start >= 60:
        start, count = now, 0
    limit = getattr(settings, "ai_requests_per_minute", 30) or 30
    if count >= limit:
        raise HTTPException(
            429,
            "Bạn đã vượt giới hạn trợ lý AI. Thử lại sau một phút.",
            headers={"Retry-After": "60"},
        )
    _windows[key] = (start, count + 1)


@router.post("/ask")
async def ask(body: AgentAskRequest, user: User = Depends(get_current_user)):
    if getattr(user, "status", "active") != "active":
        raise HTTPException(403, "Tài khoản không hoạt động.")
    _enforce_agent_rate_limit(user)

    async with httpx.AsyncClient(timeout=settings.ai_timeout_seconds) as client:
        result = await run_sop_agent(
            body.message,
            settings,
            client,
            provider=body.provider,
            enable_tools=body.enable_tools,
        )
    return result


@router.get("/hitl/{request_id}")
async def get_hitl_request(
    request_id: str,
    user: User = Depends(require_any_capability(*_APPROVER_CAPS)),
):
    record = get_pending_write_action(request_id)
    if record is None:
        raise HTTPException(404, "Không tìm thấy yêu cầu duyệt.")
    return record


@router.post("/hitl/{request_id}/decision")
async def decide_hitl_request(
    request_id: str,
    body: HitlDecisionRequest,
    user: User = Depends(require_any_capability(*_APPROVER_CAPS)),
):
    approver = getattr(user, "email", None) or getattr(user, "username", None) or str(user.id)
    updated = decide_write_action(request_id, body.decision, approver)
    if updated is None:
        raise HTTPException(
            409,
            "Yêu cầu không tồn tại hoặc đã được xử lý trước đó.",
        )
    if body.note:
        updated["note"] = body.note
    # Lưu ý: đây CHỈ ghi nhận quyết định. Việc thực thi mutation thật vẫn phải
    # đi qua luồng nghiệp vụ có PIN/maker-checker tương ứng — agent không ghi.
    return {
        "request_id": updated["request_id"],
        "status": updated["status"],
        "action_type": updated["action_type"],
        "approver": updated["approver"],
        "note": updated.get("note"),
        "executed": False,
    }
