"""Model serving endpoints (Phase M — C4).

Wrapper xung quanh `app.services.model_serving` cho dự báo nhu cầu từ model
đã Promotion sang Production trong MLflow Model Registry.

    POST /api/v1/ml/forecast  — dự báo multi-period (model Production).

Thiết kế:
- Tái dùng `DemandForecastRequest` / `DemandForecastResponse` từ
  `app.services.model_serving` để không sai lệch đầu vào so với serving layer.
- Idempotency: `IdempotencyMiddleware` (đã đăng ký toàn cục trong main.py) xử
  lý POST kèm header `Idempotency-Key`: cùng key + cùng payload -> replay
  response đã lưu (A3); cùng key + khác payload -> 409 (A4).
- Rate limit: per-process, theo IP client (fail-closed), ném 429 kèm
  `Retry-After` khi vượt ngưỡng (mặc định 10 request/phút, tuỳ chỉnh qua
  env `ML_REQUESTS_PER_MINUTE`).
"""

from __future__ import annotations

import os
import time

from fastapi import APIRouter, HTTPException, Request

from app.services.model_serving import (
    DemandForecastRequest,
    DemandForecastResponse,
    get_model_server,
)

router = APIRouter(prefix="/ml", tags=["ml-serving"])

def _client_ip(request: Request) -> str:
    """IP client thật (fail-closed): bỏ qua X-Forwarded-For để client không
    giả mạo IP và né rate-limit. Hành vi khớp mặc định của auth_utils.client_ip
    khi chưa cấu hình proxy đáng tin."""
    client = getattr(request, "client", None)
    host = getattr(client, "host", None) if client is not None else None
    return (host or "unknown").strip().lower()


_ML_WINDOWS: dict[str, tuple[float, int]] = {}

try:
    _ML_REQUESTS_PER_MINUTE = max(
        1, int(os.environ.get("ML_REQUESTS_PER_MINUTE", "10"))
    )
except ValueError:
    _ML_REQUESTS_PER_MINUTE = 10
_ML_WINDOW_SECONDS = 60.0


def _enforce_ml_rate_limit(key: str) -> None:
    """Rate limit per-process theo IP client (demo giới hạn)."""
    now = time.monotonic()
    for k in list(_ML_WINDOWS):
        if now - _ML_WINDOWS[k][0] >= _ML_WINDOW_SECONDS:
            del _ML_WINDOWS[k]
    start, count = _ML_WINDOWS.get(key, (now, 0))
    if now - start >= _ML_WINDOW_SECONDS:
        start, count = now, 0
    if count >= _ML_REQUESTS_PER_MINUTE:
        retry_after = max(1, int(_ML_WINDOW_SECONDS - (now - start)))
        raise HTTPException(
            status_code=429,
            detail={
                "code": "RATE_LIMITED",
                "message": f"Vượt giới hạn {_ML_REQUESTS_PER_MINUTE} yêu cầu/phút. Thử lại sau {retry_after} giây.",
            },
            headers={"Retry-After": str(retry_after)},
        )
    _ML_WINDOWS[key] = (start, count + 1)


@router.post("/forecast", response_model=DemandForecastResponse)
async def forecast(body: DemandForecastRequest, request: Request) -> DemandForecastResponse:
    """Dự báo nhu cầu multi-period từ model Production của MLflow Registry."""
    _enforce_ml_rate_limit(_client_ip(request))

    try:
        server = get_model_server()
    except RuntimeError as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "MODEL_NOT_AVAILABLE",
                "message": "Chưa có model Production được đăng ký. Huấn luyện và promote model trước khi gọi dự báo.",
            },
        ) from exc

    return server.predict(body)
