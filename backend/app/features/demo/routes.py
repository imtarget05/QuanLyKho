"""Demo-only endpoints cho luồng minh họa recrutier (demo flow).

Chỉ có sẵn khi `APP_ENV=demo` + `DEMO_MODE=true` (`settings.is_demo_mode`).
Mọi môi trường khác trả 404 (fail-closed, không lộ toàn bộ danh sách endpoint
trong production).
"""
from fastapi import APIRouter, Depends, HTTPException, status

from app.api.routes.auth_utils import require_capability
from app.config import settings
from app.reset_demo_db import reset_demo_database

router = APIRouter()


@router.post(
    "/demo/reset",
    summary="Reset và re-seed dữ liệu mẫu demo (chỉ môi trường demo)",
    description=(
        "Xoá toàn bộ dữ liệu giao dịch và nạp lại dữ liệu mẫu từ sample-data/, "
        "cho phép recrutier đi lại luồng: nhập hàng (có lô/HSD) → xuất FEFO → "
        "kiểm kê → chốt ca. Chỉ bật khi is_demo_mode."
    ),
)
async def demo_reset(
    _user=Depends(require_capability("admin:user_management")),
):
    """Reset lại dữ liệu demo về trạng thái sạch, sẵn sàng cho lần chạy demo tiếp theo."""
    if not settings.is_demo_mode:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Endpoint chỉ có sẵn trong môi trường demo.",
        )
    await reset_demo_database()
    return {
        "status": "reset_complete",
        "message": (
            "Đã xoá dữ liệu giao dịch cũ và re-seed mẫu cửa hàng trà sữa. "
            "Sẵn sàng chạy luồng demo: nhập hàng → xuất FEFO → kiểm kê → chốt ca."
        ),
    }
