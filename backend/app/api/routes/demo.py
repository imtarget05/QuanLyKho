"""Demo-only endpoints cho luồng minh họa recrutier (demo flow).

Chỉ có sẵn khi `APP_ENV=demo` + `DEMO_MODE=true` (`settings.is_demo_mode`).
Mọi môi trường khác trả 404 (fail-closed, không lộ toàn bộ danh sách endpoint
trong production).
"""
from fastapi import APIRouter, Depends, HTTPException, status

from app.api.routes.auth_utils import require_capability
from app.config import settings

router = APIRouter()


@router.post(
    "/demo/reset",
    summary="Reset phiên demo RAM (chỉ môi trường demo)",
    description="Demo không lưu DB; tải lại ứng dụng để bắt đầu phiên trống.",
)
async def demo_reset(
    _user=Depends(require_capability("admin:user_management")),
):
    """DB reset is intentionally disabled; RAM demo is reset by reloading the UI."""
    if not settings.is_demo_mode:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Endpoint chỉ có sẵn trong môi trường demo.",
        )
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail="Demo không lưu trong DB. Tải lại ứng dụng để bắt đầu phiên trống.",
    )
