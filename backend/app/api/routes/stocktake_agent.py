"""Stocktake assessment agent routes (read-only, feature flag gated)."""
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.stocktake_agent import (
    AssessmentResult,
    StocktakeAssessmentOptions,
    StocktakeAssessmentWorkflow,
)
from app.api.routes.auth_utils import get_current_user
from app.config import settings
from app.database import get_db
from app.models.iam import User

router = APIRouter(prefix="/ai/stocktake")


class AssessStocktakeBody(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    assessed_by: str | None = None


@router.post("/assess/{request_id}")
async def assess_stocktake(
    request_id: str,
    body: AssessStocktakeBody | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AssessmentResult:
    if user.status != "active":
        raise HTTPException(403, "Tài khoản không hoạt động.")
    if not settings.ai_agent_enabled:
        raise HTTPException(403, "Stocktake assessment agent is disabled.")
    assessed_by = body.assessed_by if body and body.assessed_by else user.username
    workflow = StocktakeAssessmentWorkflow(
        options=StocktakeAssessmentOptions(
            enabled=True, staleness_minutes=60, source_sha=""
        )
    )
    return await workflow.assess_async(request_id, assessed_by, db)


@router.get("/health")
async def stocktake_agent_health() -> dict[str, Any]:
    return {
        "agent": "stocktake_assessment",
        "enabled": bool(settings.ai_agent_enabled),
        "provider": "deterministic",
        "read_only": True,
    }
