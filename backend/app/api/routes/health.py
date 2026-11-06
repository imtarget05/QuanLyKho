"""Health check endpoints."""
import asyncio
import logging
import os
import re
from datetime import UTC, datetime

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.api.routes.auth_utils import assert_redis_ready

logger = logging.getLogger("quanlykho.health")


class HealthResponse(BaseModel):
    status: str
    timestamp: datetime
    version: str
    services: dict


router = APIRouter()


@router.get("/version")
def version_check():
    """Expose only the deployed Git SHA for release reconciliation."""
    release_sha = os.environ.get("RENDER_GIT_COMMIT", "")
    if re.fullmatch(r"[0-9a-f]{40}", release_sha):
        return {"release_sha": release_sha}
    return {"release_sha": "unknown"}


@router.get("/live")
async def liveness_check():
    """Liveness probe - checks if service is running."""
    return {
        "status": "alive",
        "timestamp": datetime.now(UTC),
        "version": "0.1.0",
    }


@router.get("/ready")
async def readiness_check():
    """Readiness probe - checks if service can handle requests.

    docs/06: DB down -> 503 (không phải 200 degraded) để orchestrator
    loại khỏi rotation.
    """
    from app.database import engine

    db_status = "not_ready"
    try:
        from sqlalchemy import text

        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
            db_status = "ready"
    except Exception as exc:
        logger.warning("Database readiness check failed (%s)", type(exc).__name__)

    login_rate_limit_status = "not_ready"
    try:
        await asyncio.to_thread(assert_redis_ready)
        login_rate_limit_status = "ready"
    except Exception as exc:
        logger.warning("Login rate-limit readiness check failed (%s)", type(exc).__name__)

    body = {
        "status": "ready" if db_status == login_rate_limit_status == "ready" else "not_ready",
        "timestamp": datetime.now(UTC),
        "version": "0.1.0",
        "services": {
            "database": db_status,
            "login_rate_limit": login_rate_limit_status,
        },
    }
    if body["status"] != "ready":
        body["timestamp"] = body["timestamp"].isoformat()
        return JSONResponse(status_code=503, content=body)
    return body
