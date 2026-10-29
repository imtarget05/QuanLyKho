"""AI forecasting endpoints: reorder-point optimization and anomaly detection.

Phase 2 (P2.2/P2.3) — expose the deterministic forecasting services in
`app.services.reorder_point` over authenticated HTTP so the web client can
consume reorder recommendations and demand-anomaly alerts.

Authorization: requires an inventory read capability (deny by default).
"""
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from app.api.routes.auth_utils import require_any_capability
from app.models.iam import User
from app.services.reorder_point import calculate_reorder_point, detect_anomaly

router = APIRouter(prefix="/ai")

# Người dùng cần ít nhất một trong các capability đọc tồn kho.
_VIEW_CAPS = ("inventory:view_balances", "inventory:manage_catalog")
_view_caps = require_any_capability(*_VIEW_CAPS)


class ReorderPointRequest(BaseModel):
    """Input cho bài toán tối ưu điểm đặt hàng."""

    model_config = ConfigDict(extra="forbid")

    forecast_values: list[float] = Field(
        min_length=1,
        description="Chuỗi dự báo nhu cầu (1 giá trị = 1 ngày).",
    )
    lead_time_days: float = Field(
        gt=0,
        description="Thời gian từ lúc đặt hàng đến khi nhận được hàng (ngày).",
    )
    service_level: float = Field(
        default=0.95,
        gt=0,
        lt=1,
        description="Mức phục vụ mục tiêu (0-1). Mặc định 0.95.",
    )
    current_stock: float = Field(default=0.0, ge=0)
    min_order_quantity: float = Field(default=1.0, ge=0)
    max_stock: float = Field(default=0.0, ge=0)


class ReorderPointResponse(BaseModel):
    """Kết quả tính điểm đặt hàng."""

    reorder_point: float
    safety_stock: float
    avg_daily_demand: float
    std_demand: float
    z_score: float
    lead_time_days: float
    service_level: float
    needs_order: bool
    suggested_order_quantity: float
    current_stock: float
    risk_level: str


class AnomalyRequest(BaseModel):
    """Input cho bài toán phát hiện bất thường nhu cầu."""

    model_config = ConfigDict(extra="forbid")

    actual_demand: float
    expected_demand: float
    std_demand: float = Field(ge=0)
    threshold_z: float = Field(default=2.5, gt=0)


class AnomalyResponse(BaseModel):
    """Kết quả phát hiện bất thường."""

    is_anomaly: bool
    z_score: float
    direction: str
    severity: str
    expected_demand: float
    actual_demand: float
    threshold_z: float
    reason: str


def _to_float(value: Decimal | float) -> float:
    return float(value) if isinstance(value, Decimal) else value


@router.post("/reorder-point", response_model=ReorderPointResponse)
async def post_reorder_point(
    body: ReorderPointRequest,
    _user: User = Depends(_view_caps),
) -> ReorderPointResponse:
    """Tính điểm đặt hàng tối ưu từ dự báo nhu cầu và thời gian giao hàng."""
    try:
        result = calculate_reorder_point(
            forecast_values=body.forecast_values,
            lead_time_days=body.lead_time_days,
            service_level=body.service_level,
            current_stock=body.current_stock,
            min_order_quantity=body.min_order_quantity,
            max_stock=body.max_stock,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return ReorderPointResponse(
        **{key: _to_float(value) for key, value in result.items()}
    )


@router.post("/anomaly", response_model=AnomalyResponse)
async def post_anomaly(
    body: AnomalyRequest,
    _user: User = Depends(_view_caps),
) -> AnomalyResponse:
    """Phát hiện nhu cầu bất thường bằng z-score."""
    try:
        result = detect_anomaly(
            actual_demand=body.actual_demand,
            expected_demand=body.expected_demand,
            std_demand=body.std_demand,
            threshold_z=body.threshold_z,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return AnomalyResponse(
        **{key: _to_float(value) for key, value in result.items()}
    )
