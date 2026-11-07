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
from app.config import settings

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

    # Production yêu cầu Redis (fail closed -> 503 khi down); demo/không
    # production stays up và báo degraded khi Redis xuống (fail open) để login
    # vẫn chạy qua rate limiting trong RAM.
    redis_required = (
        settings.app_env.strip().lower() == "production" and not settings.is_demo_mode
    )

    login_rate_limit_status = "not_ready"
    try:
        await asyncio.to_thread(assert_redis_ready)
        if redis_required:
            login_rate_limit_status = "ready"
        else:
            # Chế độ demo/không production: assert_redis_ready bỏ qua, nên ta
            # cần tự kiểm tra chính xác Redis trước khi báo "ready". Nếu không
            # thể kết nối -> báo "degraded" (fail-open, login vẫn qua RAM) thay
            # vì giả sẵn sẵn.
            from app.api.routes.auth_utils import _get_redis_client

            client = _get_redis_client()
            if client is None:
                login_rate_limit_status = "degraded"
            else:
                try:
                    client.ping()
                    login_rate_limit_status = "ready"
                except Exception as exc:  # noqa: BLE001 - Redis labil trong demo
                    login_rate_limit_status = "degraded"
                    logger.warning(
                        "Redis unavailable in demo mode; login rate limit "
                        "degrades to in-memory (%s)",
                        type(exc).__name__,
                    )
    except Exception as exc:
        if redis_required:
            # Production: Redis bắt buộc -> fail closed, orchestrator loại pod.
            login_rate_limit_status = "not_ready"
            logger.error("Required Redis readiness check failed (%s)", type(exc).__name__)
        else:
            # Demo: Redis không bắt buộc -> fail open, báo degraded thay vì 503.
            login_rate_limit_status = "degraded"
            logger.warning(
                "Redis unavailable in demo mode; login rate limit "
                "degrades to RAM (%s)", type(exc).__name__
            )

    # CSDL luôn bắt buộc. Chỉ login_rate_limit được phép degraded ở demo mode.
    db_down = db_status == "not_ready"
    redis_hard_down = login_rate_limit_status == "not_ready"
    redis_degraded = login_rate_limit_status == "degraded"

    not_ready = db_down or redis_hard_down
    degraded = (not not_ready) and redis_degraded
    ready = not not_ready and not degraded

    status = "ready" if ready else ("degraded" if degraded else "not_ready")

    body = {
        "status": status,
        "timestamp": datetime.now(UTC),
        "version": "0.1.0",
        "services": {
            "database": db_status,
            "login_rate_limit": login_rate_limit_status,
        },
    }
    if not ready:
        body["timestamp"] = body["timestamp"].isoformat()
        code = 503 if not_ready else 200
        return JSONResponse(status_code=code, content=body)
    return body
