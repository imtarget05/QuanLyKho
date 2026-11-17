"""Saga API routes (interview-prep 02/05 §4, 04/02 Q15)."""

from typing import Any

from fastapi import APIRouter, Depends

from app.db.database import get_async_session
from app.services.saga import SagaOrchestrator

router = APIRouter(prefix="/saga", tags=["saga"])


@router.post("/orchestrate", summary="Thực thi Saga distributed transaction")
async def orchestrate_saga(
    saga_id: str,
    saga_type: str,
    steps: list[dict[str, Any]],
    context: dict[str, Any] | None = None,
    session = Depends(get_async_session),
):
    """Thực thi saga distributed transaction.

    Args:
        saga_id: Unique identifier for this saga (also acts as idempotency key)
        saga_type: Type of saga (e.g., "fund_transfer", "batch_settlement")
        steps: List of step defs {"name": str, "action": callable, "compensate": callable}
        context: Optional context dict shared across steps

    Returns:
        Saga execution status

    Raises:
        HTTPException: If saga is already completed/failed (idempotent) or on error
    """

    orchestrator = SagaOrchestrator(session=session)
    result = await orchestrator.execute(
        saga_id=saga_id,
        saga_type=saga_type,
        steps=steps,
        context=context,
    )
    return result