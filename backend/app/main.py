"""Quản Lý Kho Trà Sữa API Application."""
import logging
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI, Request
from fastapi.exceptions import HTTPException, RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse

from app.api.errors import register_error_handlers
from app.api.middleware.correlation import CorrelationIdMiddleware
from app.api.observability import configure_metrics
from app.api.openapi import custom_openapi
from app.api.request_context import correlation_id_var, request_id_var
from app.api.routes import (
    activity,
    admin_users,
    ai,
    ai_forecasting,
    approvals,
    auth,
    auth_google,
    cash_sim,
    dashboard,
    demo,
    etl,
    events,
    health,
    intake,
    integrations,
    inventory,
    notifications,
    reconciliations,
    reports,
)
from app.api.structured_logging import configure_json_logging
from app.api.telemetry import (
    create_tracer_provider,
    instrument_fastapi,
    instrument_sqlalchemy,
)
from app.config import settings
from app.database import init_db

PUBLIC_WEB_ORIGIN = "https://quan-ly-kho-tra-sua.tanmainguyenbinh.workers.dev"

logger = logging.getLogger("quanlykho.api")
tracer_provider = create_tracer_provider()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Initialize database on startup (lifespan thay on_event deprecated)."""
    configure_json_logging()
    await init_db()
    from app.database import engine

    instrument_sqlalchemy(engine, tracer_provider=tracer_provider)
    try:
        yield
    finally:
        tracer_provider.shutdown()


app = FastAPI(
    title="Quản Lý Kho Trà Sữa API",
    description="API quản lý nhập, xuất và tồn nguyên vật liệu quán trà sữa.",
    version="0.1.0",
    openapi_url="/api/v1/openapi.json",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)
configure_metrics(app)

@app.get("/", include_in_schema=False)
async def root_status():
    return {
        "service": "Quản Lý Kho Trà Sữa FastAPI",
        "status": "alive",
        "docs": "/docs",
        "health": "/api/v1/health/live",
    }

@app.get("/api/v1/docs", include_in_schema=False)
async def redirect_api_v1_docs():
    return RedirectResponse(url="/docs")

@app.get("/openapi.json", include_in_schema=False)
async def redirect_openapi_json():
    return RedirectResponse(url="/api/v1/openapi.json")

app.openapi = lambda: custom_openapi(app)

# Không echo wildcard origin kèm credentials (docs/08: CORS cụ thể).
# Không dùng `allow_origin_regex` vì regex chấp nhận mọi subdomain
# (`.tanmainguyenbinh.workers.dev`, `.pages.dev`) kèm credentials → rủi ro P0.
_allowed_origins = list(
    dict.fromkeys(
        [
            *settings.allowed_origins,
            PUBLIC_WEB_ORIGIN,
            "https://quan-ly-kho-tra-sua.tanmainguyenbinh.workers.dev",
            "https://kho-tra-sua-api.tanmainguyenbinh.workers.dev",
        ]
    )
)
_allow_credentials = bool(_allowed_origins) and _allowed_origins != ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=_allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID", "X-Correlation-ID"],
)
app.add_middleware(CorrelationIdMiddleware)
instrument_fastapi(app, tracer_provider=tracer_provider)

# --- Error envelope docs/06:44 -----------------------------------------------
_ERROR_CODES = {
    400: "BAD_REQUEST",
    401: "UNAUTHENTICATED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    409: "CONFLICT",
    422: "VALIDATION_ERROR",
    429: "RATE_LIMITED",
    503: "DEPENDENCY_UNAVAILABLE",
}


def _request_id(request: Request) -> str:
    rid = getattr(request.state, "request_id", None)
    if rid:
        return rid
    return request.headers.get("x-request-id") or uuid.uuid4().hex


@app.middleware("http")
async def request_id_mw(request: Request, call_next):
    """docs/06:3 — propagate/generate X-Request-ID, envelope HTTP errors."""
    rid = request.headers.get("x-request-id") or uuid.uuid4().hex
    correlation_id = request.headers.get("x-correlation-id") or rid
    request.state.request_id = rid
    request_token = request_id_var.set(rid)
    correlation_token = correlation_id_var.set(correlation_id)
    request.scope["headers"] = [
        (key, value)
        for key, value in request.scope.get("headers", [])
        if key.lower() not in (b"x-request-id", b"x-correlation-id")
    ] + [
        (b"x-request-id", rid.encode("utf-8")),
        (b"x-correlation-id", correlation_id.encode("utf-8")),
    ]
    started = time.perf_counter()
    status_code = 500
    try:
        resp = await call_next(request)
        status_code = resp.status_code
    except HTTPException as e:
        code, message = _http_error_code_and_message(e)
        resp = JSONResponse(
            status_code=e.status_code,
            content={"error": {"code": code, "message": message, "request_id": rid, "details": {}}},
            headers={"X-Request-ID": rid},
        )
        status_code = e.status_code
    finally:
        route = request.scope.get("route")
        route_template = getattr(route, "path", "unmatched")
        logging.getLogger("quanlykho.http").info(
            "http_request",
            extra={
                "http_method": request.method,
                "http_route": route_template,
                "http_status_class": f"{status_code // 100}xx",
                "duration_ms": round((time.perf_counter() - started) * 1000, 2),
            },
        )
        request_id_var.reset(request_token)
        correlation_id_var.reset(correlation_token)

    resp.headers["X-Request-ID"] = rid
    resp.headers["X-Correlation-ID"] = correlation_id
    return resp


def _http_error_code_and_message(exc: HTTPException) -> tuple[str, str]:
    """Unpack detail theo hợp đồng envelope docs/06:44.

    - `detail` là `{"code": ..., "message": ...}` (vd AI_UNAVAILABLE) -> lấy
      đúng code/message đó.
    - `detail` là string -> dùng trực tiếp.
    - còn lại -> thông điệp chung chung, không lộ nội bộ.
    """
    code = _ERROR_CODES.get(exc.status_code, f"HTTP_{exc.status_code}")
    message = "Yêu cầu không hợp lệ. Vui lòng thử lại."
    if isinstance(exc.detail, str) and exc.detail.strip():
        message = exc.detail
    elif isinstance(exc.detail, dict):
        if isinstance(exc.detail.get("code"), str) and exc.detail["code"].strip():
            code = exc.detail["code"]
        if isinstance(exc.detail.get("message"), str) and exc.detail["message"].strip():
            message = exc.detail["message"]
    return code, message


@app.exception_handler(HTTPException)
async def http_exception_envelope(request: Request, exc: HTTPException):
    """Mọi HTTPException trả theo envelope docs/06:44, không phải {"detail": ...}."""
    code, message = _http_error_code_and_message(exc)
    rid = _request_id(request)
    headers = dict(exc.headers or {})
    headers.setdefault("X-Request-ID", rid)
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": code,
                "message": message,
                "request_id": rid,
                "details": {},
            }
        },
        headers=headers,
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_envelope(request: Request, exc: RequestValidationError):
    """422 theo cùng envelope docs/06:44 (không phải {"detail": ...}).

    Chỉ giữ loc/msg/type — KHÔNG trả lại `input` (password/tokens có thể lọt
    qua đó) và không lộ chi tiết kỹ thuật nội bộ cho người dùng cuối.
    """
    rid = _request_id(request)
    safe_errors = [
        {key: err.get(key) for key in ("loc", "msg", "type") if key in err}
        for err in exc.errors()
    ]
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": _ERROR_CODES[422],
                "message": "Dữ liệu gửi lên chưa hợp lệ. Vui lòng kiểm tra lại các trường bắt buộc.",
                "request_id": rid,
                "details": {"errors": safe_errors},
            }
        },
        headers={"X-Request-ID": rid},
    )

@app.exception_handler(Exception)
async def unhandled_exception_envelope(request: Request, exc: Exception):
    """500 theo cùng envelope docs/06:44."""
    rid = getattr(request.state, "request_id", None) or _request_id(request)
    logger.exception("unhandled error request_id=%s path=%s", rid, request.url.path)
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "INTERNAL_ERROR",
                "message": "Máy chủ đang gặp sự cố. Vui lòng thử lại sau ít phút.",
                "request_id": rid,
                "details": {},
            }
        },
        headers={"X-Request-ID": rid},
    )


# Lỗi nghiệp vụ có code riêng (AppError, IdempotencyConflict) -> envelope docs/06.
register_error_handlers(app)

def _mount_routes(target: FastAPI | APIRouter, *, include_in_schema: bool = True) -> None:
    target.include_router(ai.router, tags=["ai"], include_in_schema=include_in_schema)
    target.include_router(ai_forecasting.router, tags=["ai-forecasting"], include_in_schema=include_in_schema)
    target.include_router(health.router, prefix="/health", tags=["health"], include_in_schema=include_in_schema)
    target.include_router(auth.router, prefix="/auth", tags=["auth"], include_in_schema=include_in_schema)
    target.include_router(auth_google.router, prefix="/auth", tags=["auth"], include_in_schema=include_in_schema)
    target.include_router(admin_users.router, tags=["admin"], include_in_schema=include_in_schema)
    target.include_router(inventory.router, tags=["inventory"], include_in_schema=include_in_schema)
    target.include_router(intake.router, tags=["intake"], include_in_schema=include_in_schema)
    target.include_router(dashboard.router, tags=["dashboard"], include_in_schema=include_in_schema)
    target.include_router(cash_sim.router, tags=["cash-sim"], include_in_schema=include_in_schema)
    target.include_router(approvals.router, prefix="/approvals", tags=["approvals"], include_in_schema=include_in_schema)
    target.include_router(activity.router, tags=["activity"], include_in_schema=include_in_schema)
    target.include_router(events.router, tags=["events"], include_in_schema=include_in_schema)
    target.include_router(reports.router, prefix="/reports", tags=["reports"], include_in_schema=include_in_schema)
    target.include_router(notifications.router, prefix="/notifications", tags=["notifications"], include_in_schema=include_in_schema)
    target.include_router(etl.router, tags=["etl"], include_in_schema=include_in_schema)
    target.include_router(integrations.router, tags=["integrations"], include_in_schema=include_in_schema)
    target.include_router(reconciliations.router, tags=["reconciliations"], include_in_schema=include_in_schema)
    target.include_router(demo.router, tags=["demo"], include_in_schema=include_in_schema)
    # docs/06:9 khai báo `GET /me` (không qua /auth) — alias tới cùng handler.
    target.add_api_route("/me", auth.get_current_user_info, methods=["GET"], tags=["auth"], include_in_schema=include_in_schema)
    target.add_api_route("/me", auth.update_profile, methods=["PUT"], tags=["auth"], include_in_schema=include_in_schema)


_mount_routes(app, include_in_schema=True)

api_v1_router = APIRouter(prefix="/api/v1")
_mount_routes(api_v1_router, include_in_schema=False)
app.include_router(api_v1_router, include_in_schema=False)
