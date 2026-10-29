"""ETL Routes (Phase 2).

Provides the 4-layer ETL API:
  - /etl/connections: data source configs & secret references
  - /etl/pipelines: scoped pipelines with targets & branch/location binding
  - /etl/pipelines/{id}/mapping-versions: column mappings, transforms & validation
  - /etl/pipelines/{id}/runs: ingestion runs, row staging, and previews
  - /etl/runs/{id}/rows: paginated row inspection & error drill-down
  - /etl/runs/{id}/review: maker/checker staging approval
  - /etl/runs/{id}/post: ledger & catalog posting with single-admin balance adjustment override
  - /etl/runs/{id}/error-report: CSV/JSON downloadable error report
"""

import csv
import io
import json
import re
import uuid
from typing import Any

from fastapi import (
    APIRouter,
    Depends,
    Query,
    Request,
    status,
)
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import AppError
from app.api.routes.auth_utils import (
    check_user_scope,
    get_current_user_with_capabilities,
)
from app.database import get_db
from app.models.etl import (
    EtlConnection,
    EtlMappingVersion,
    EtlPipeline,
    EtlRun,
    EtlRunRow,
)
from app.models.iam import User
from app.models.inventory import Location
from app.services import etl_engine

router = APIRouter(prefix="/etl", tags=["etl"])

_CAP_ADMIN = "etl:admin"
_CAP_DESIGN = "etl:design"
_CAP_RUN = "etl:run"
_CAP_REVIEW = "etl:review"
_CAP_POST_BALANCE = "etl:post_balance"

# CWE-1236: Excel/Sheets treat a cell starting with these as a formula.
_FORMULA_LEAD = ("=", "+", "-", "@", "\t", "\r")
_NUMERIC_RE = re.compile(r"^-?\d+(\.\d+)?$")


def _csv_safe(value: object) -> str:
    """Neutralise spreadsheet formula injection in an exported CSV cell.

    A value beginning with ``=`` ``+`` ``-`` ``@`` TAB or CR is executed as a
    formula by Excel / Google Sheets. Prefixing an apostrophe forces text.
    Plain numbers (including negatives) are left untouched so numeric columns
    stay numeric.
    """
    text = "" if value is None else str(value)
    if text[:1] in _FORMULA_LEAD and not _NUMERIC_RE.match(text):
        return "'" + text
    return text


# --------------------------------------------------------------------------
# Request Schemas
# --------------------------------------------------------------------------


class ConnectionCreateInput(BaseModel):
    name: str = Field(..., min_length=1, max_length=256)
    type: str = Field(..., pattern="^(csv|json|xlsx|google_sheets)$")
    secret_ref: str | None = None
    allowlist_sheets: list[str] | None = None
    config_json: dict[str, Any] | None = None
    branch_id: str | None = None


class ConnectionUpdateInput(BaseModel):
    name: str | None = None
    status: str | None = None
    secret_ref: str | None = None
    allowlist_sheets: list[str] | None = None
    config_json: dict[str, Any] | None = None
    branch_id: str | None = None


class PipelineCreateInput(BaseModel):
    name: str = Field(..., min_length=1, max_length=256)
    target: str = Field(
        ...,
        pattern="^(catalog_upsert|inventory_receipt|inventory_issue|inventory_transfer|stocktake|balance_adjustment_admin)$",
    )
    connection_id: str
    branch_id: str | None = None
    location_id: str | None = None
    destination_location_id: str | None = None
    schedule_cron: str | None = None
    config_json: dict[str, Any] | None = None


class PipelineUpdateInput(BaseModel):
    name: str | None = None
    status: str | None = None
    branch_id: str | None = None
    location_id: str | None = None
    destination_location_id: str | None = None
    schedule_cron: str | None = None
    config_json: dict[str, Any] | None = None


class MappingRuleInput(BaseModel):
    source_field: str
    target_field: str
    required: bool = False
    transform: str | None = None  # trim, trim_upper, trim_lower, to_int, to_float, to_decimal, to_bool
    default: Any | None = None


class MappingVersionCreateInput(BaseModel):
    mapping_rules: list[MappingRuleInput]
    duplicate_policy: str = "reject"  # reject, skip, overwrite
    validation_rules: dict[str, Any] | None = None


class ReviewInput(BaseModel):
    decision: str = Field(..., pattern="^(approved|rejected)$")
    note: str | None = None


class RunJsonInput(BaseModel):
    raw_rows: list[dict[str, Any]]
    external_event_id: str | None = None


# --------------------------------------------------------------------------
# Helper serializers
# --------------------------------------------------------------------------


def _serialize_connection(c: EtlConnection) -> dict[str, Any]:
    return {
        "id": str(c.id),
        "name": c.name,
        "type": c.type,
        "status": c.status,
        "secret_ref": c.secret_ref,
        "allowlist_sheets": c.allowlist_sheets or [],
        "config_json": c.config_json or {},
        "branch_id": str(c.branch_id) if c.branch_id else None,
        "owner_id": str(c.owner_id) if c.owner_id else None,
        "created_at": c.created_at.isoformat() if c.created_at else None,
        "updated_at": c.updated_at.isoformat() if c.updated_at else None,
    }


def _serialize_pipeline(p: EtlPipeline) -> dict[str, Any]:
    return {
        "id": str(p.id),
        "name": p.name,
        "target": p.target,
        "connection_id": str(p.connection_id),
        "branch_id": str(p.branch_id) if p.branch_id else None,
        "location_id": str(p.location_id) if p.location_id else None,
        "destination_location_id": str(p.destination_location_id) if p.destination_location_id else None,
        "schedule_cron": p.schedule_cron,
        "status": p.status,
        "owner_id": str(p.owner_id) if p.owner_id else None,
        "config_json": p.config_json or {},
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "updated_at": p.updated_at.isoformat() if p.updated_at else None,
    }


def _serialize_mapping_version(mv: EtlMappingVersion) -> dict[str, Any]:
    return {
        "id": str(mv.id),
        "pipeline_id": str(mv.pipeline_id),
        "version": mv.version,
        "status": mv.status,
        "mapping_json": mv.mapping_json or [],
        "validation_rules_json": mv.validation_rules_json or {},
        "duplicate_policy": mv.duplicate_policy,
        "created_by": str(mv.created_by) if mv.created_by else None,
        "published_at": mv.published_at.isoformat() if mv.published_at else None,
        "created_at": mv.created_at.isoformat() if mv.created_at else None,
    }


def _serialize_run(r: EtlRun) -> dict[str, Any]:
    return {
        "id": str(r.id),
        "pipeline_id": str(r.pipeline_id),
        "mapping_version_id": str(r.mapping_version_id) if r.mapping_version_id else None,
        "mapping_version_num": r.mapping_version_num,
        "runner_id": str(r.runner_id),
        "status": r.status,
        "progress_pct": r.progress_pct,
        "total_rows": r.total_rows,
        "valid_rows": r.valid_rows,
        "invalid_rows": r.invalid_rows,
        "source_fingerprint": r.source_fingerprint,
        "external_event_id": r.external_event_id,
        "single_admin_override": r.single_admin_override,
        "reviewer_id": str(r.reviewer_id) if r.reviewer_id else None,
        "review_decision": r.review_decision,
        "review_note": r.review_note,
        "posted_at": r.posted_at.isoformat() if r.posted_at else None,
        "generated_reference_type": r.generated_reference_type,
        "generated_reference_id": r.generated_reference_id,
        "error_code": r.error_code,
        "error_message": r.error_message,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


def _serialize_run_row(rr: EtlRunRow) -> dict[str, Any]:
    return {
        "id": str(rr.id),
        "run_id": str(rr.run_id),
        "row_number": rr.row_number,
        "source_row_key": rr.source_row_key,
        "raw_data_json": rr.raw_data_json,
        "canonical_data_json": rr.canonical_data_json,
        "valid": rr.valid,
        "errors_json": rr.errors_json or [],
        "action_preview": rr.action_preview or {},
    }


# --------------------------------------------------------------------------
# 1. Connections API
# --------------------------------------------------------------------------


@router.get("/connections")
async def list_connections(
    branch_id: str | None = None,
    user_caps: tuple[User, list[str]] = Depends(get_current_user_with_capabilities),
    db: AsyncSession = Depends(get_db),
):
    user, caps = user_caps
    if not any(c in caps for c in (_CAP_ADMIN, _CAP_DESIGN, _CAP_RUN, _CAP_REVIEW)):
        raise AppError(403, "FORBIDDEN", "Bạn không có quyền truy cập ETL.")

    stmt = select(EtlConnection).order_by(desc(EtlConnection.created_at))
    if branch_id:
        stmt = stmt.where(EtlConnection.branch_id == uuid.UUID(branch_id))
    elif _CAP_ADMIN not in caps and user.branch_id:
        stmt = stmt.where((EtlConnection.branch_id == user.branch_id) | (EtlConnection.branch_id.is_(None)))

    conns = (await db.execute(stmt)).scalars().all()
    return {"connections": [_serialize_connection(c) for c in conns]}


@router.post("/connections", status_code=status.HTTP_201_CREATED)
async def create_connection(
    payload: ConnectionCreateInput,
    user_caps: tuple[User, list[str]] = Depends(get_current_user_with_capabilities),
    db: AsyncSession = Depends(get_db),
):
    user, caps = user_caps
    if not any(c in caps for c in (_CAP_ADMIN, _CAP_DESIGN)):
        raise AppError(403, "FORBIDDEN", "Chỉ quản trị viên hoặc nhà thiết kế mới được tạo kết nối.")

    branch_uuid = uuid.UUID(payload.branch_id) if payload.branch_id else None
    conn = EtlConnection(
        id=uuid.uuid4(),
        name=payload.name,
        type=payload.type,
        status="active",
        secret_ref=payload.secret_ref,
        allowlist_sheets=payload.allowlist_sheets,
        config_json=payload.config_json,
        branch_id=branch_uuid,
        owner_id=user.id,
    )
    db.add(conn)
    await db.commit()
    await db.refresh(conn)
    return _serialize_connection(conn)


@router.get("/connections/{conn_id}")
async def get_connection(
    conn_id: str,
    user_caps: tuple[User, list[str]] = Depends(get_current_user_with_capabilities),
    db: AsyncSession = Depends(get_db),
):
    user, caps = user_caps
    if not any(c in caps for c in (_CAP_ADMIN, _CAP_DESIGN, _CAP_RUN, _CAP_REVIEW)):
        raise AppError(403, "FORBIDDEN", "Bạn không có quyền truy cập ETL.")

    conn = await db.get(EtlConnection, uuid.UUID(conn_id))
    if not conn:
        raise AppError(404, "CONNECTION_NOT_FOUND", "Không tìm thấy connection")
    return _serialize_connection(conn)


@router.patch("/connections/{conn_id}")
async def update_connection(
    conn_id: str,
    payload: ConnectionUpdateInput,
    user_caps: tuple[User, list[str]] = Depends(get_current_user_with_capabilities),
    db: AsyncSession = Depends(get_db),
):
    user, caps = user_caps
    if not any(c in caps for c in (_CAP_ADMIN, _CAP_DESIGN)):
        raise AppError(403, "FORBIDDEN", "Bạn không có quyền sửa kết nối.")

    conn = await db.get(EtlConnection, uuid.UUID(conn_id))
    if not conn:
        raise AppError(404, "CONNECTION_NOT_FOUND", "Không tìm thấy connection")

    if payload.name is not None:
        conn.name = payload.name
    if payload.status is not None:
        conn.status = payload.status
    if payload.secret_ref is not None:
        conn.secret_ref = payload.secret_ref
    if payload.allowlist_sheets is not None:
        conn.allowlist_sheets = payload.allowlist_sheets
    if payload.config_json is not None:
        conn.config_json = payload.config_json
    if payload.branch_id is not None:
        conn.branch_id = uuid.UUID(payload.branch_id) if payload.branch_id else None

    await db.commit()
    await db.refresh(conn)
    return _serialize_connection(conn)


# --------------------------------------------------------------------------
# 2. Pipelines API
# --------------------------------------------------------------------------


@router.get("/pipelines")
async def list_pipelines(
    target: str | None = None,
    branch_id: str | None = None,
    user_caps: tuple[User, list[str]] = Depends(get_current_user_with_capabilities),
    db: AsyncSession = Depends(get_db),
):
    user, caps = user_caps
    if not any(c in caps for c in (_CAP_ADMIN, _CAP_DESIGN, _CAP_RUN, _CAP_REVIEW)):
        raise AppError(403, "FORBIDDEN", "Bạn không có quyền truy cập ETL.")

    stmt = select(EtlPipeline).order_by(desc(EtlPipeline.created_at))
    if target:
        stmt = stmt.where(EtlPipeline.target == target)
    if branch_id:
        stmt = stmt.where(EtlPipeline.branch_id == uuid.UUID(branch_id))

    pipelines = (await db.execute(stmt)).scalars().all()

    # Scope filtering for runner/review roles
    if _CAP_ADMIN not in caps and _CAP_DESIGN not in caps:
        filtered = []
        for p in pipelines:
            is_allowed = await check_user_scope(db, user, p.branch_id, p.location_id)
            if is_allowed:
                filtered.append(p)
        pipelines = filtered

    return {"pipelines": [_serialize_pipeline(p) for p in pipelines]}


@router.post("/pipelines", status_code=status.HTTP_201_CREATED)
async def create_pipeline(
    payload: PipelineCreateInput,
    user_caps: tuple[User, list[str]] = Depends(get_current_user_with_capabilities),
    db: AsyncSession = Depends(get_db),
):
    user, caps = user_caps
    if not any(c in caps for c in (_CAP_ADMIN, _CAP_DESIGN)):
        raise AppError(403, "FORBIDDEN", "Chỉ quản trị viên hoặc nhà thiết kế mới được tạo pipeline.")

    conn = await db.get(EtlConnection, uuid.UUID(payload.connection_id))
    if not conn:
        raise AppError(404, "CONNECTION_NOT_FOUND", "Connection không tồn tại")

    branch_uuid = uuid.UUID(payload.branch_id) if payload.branch_id else None
    loc_uuid = uuid.UUID(payload.location_id) if payload.location_id else None
    dest_loc_uuid = uuid.UUID(payload.destination_location_id) if payload.destination_location_id else None

    # Validate location exists if specified
    if loc_uuid:
        loc = await db.get(Location, loc_uuid)
        if not loc:
            raise AppError(404, "LOCATION_NOT_FOUND", "Vị trí kho không tồn tại")

    pipeline = EtlPipeline(
        id=uuid.uuid4(),
        name=payload.name,
        target=payload.target,
        connection_id=conn.id,
        branch_id=branch_uuid,
        location_id=loc_uuid,
        destination_location_id=dest_loc_uuid,
        schedule_cron=payload.schedule_cron,
        status="active",
        owner_id=user.id,
        config_json=payload.config_json,
    )
    db.add(pipeline)
    await db.flush()

    # Create default published mapping version v1 based on target
    default_rules = _get_default_mapping_for_target(payload.target)
    mv = EtlMappingVersion(
        id=uuid.uuid4(),
        pipeline_id=pipeline.id,
        version=1,
        status="published",
        mapping_json=default_rules,
        duplicate_policy="reject",
        created_by=user.id,
        published_at=etl_engine.utc_now(),
    )
    db.add(mv)

    await db.commit()
    await db.refresh(pipeline)
    return _serialize_pipeline(pipeline)


def _get_default_mapping_for_target(target: str) -> list[dict[str, Any]]:
    if target == "catalog_upsert":
        return [
            {"source_field": "sku", "target_field": "sku", "required": True, "transform": "trim_upper"},
            {"source_field": "name", "target_field": "name", "required": True, "transform": "trim"},
            {"source_field": "unit", "target_field": "unit", "required": False, "transform": "trim", "default": "đơn vị"},
            {"source_field": "tracked_serial", "target_field": "tracked_serial", "required": False, "transform": "to_bool", "default": False},
        ]
    elif target == "balance_adjustment_admin":
        return [
            {"source_field": "sku", "target_field": "sku", "required": True, "transform": "trim_upper"},
            {"source_field": "target_quantity", "target_field": "target_quantity", "required": False, "transform": "to_float"},
            {"source_field": "delta_quantity", "target_field": "delta_quantity", "required": False, "transform": "to_float"},
            {"source_field": "reason", "target_field": "reason", "required": False, "transform": "trim", "default": "Điều chỉnh tồn ETL Admin"},
        ]
    elif target == "inventory_receipt":
        return [
            {"source_field": "sku", "target_field": "sku", "required": True, "transform": "trim_upper"},
            {"source_field": "quantity", "target_field": "quantity", "required": True, "transform": "to_float"},
            {"source_field": "note", "target_field": "note", "required": False, "transform": "trim"},
        ]
    elif target == "inventory_issue":
        return [
            {"source_field": "sku", "target_field": "sku", "required": True, "transform": "trim_upper"},
            {"source_field": "quantity", "target_field": "quantity", "required": True, "transform": "to_float"},
            {"source_field": "reason", "target_field": "reason", "required": False, "transform": "trim"},
        ]
    elif target == "inventory_transfer":
        return [
            {"source_field": "sku", "target_field": "sku", "required": True, "transform": "trim_upper"},
            {"source_field": "quantity", "target_field": "quantity", "required": True, "transform": "to_float"},
        ]
    elif target == "stocktake":
        return [
            {"source_field": "sku", "target_field": "sku", "required": True, "transform": "trim_upper"},
            {"source_field": "counted_quantity", "target_field": "counted_quantity", "required": True, "transform": "to_float"},
            {"source_field": "note", "target_field": "note", "required": False, "transform": "trim"},
        ]
    return []


@router.get("/pipelines/{pipeline_id}")
async def get_pipeline(
    pipeline_id: str,
    user_caps: tuple[User, list[str]] = Depends(get_current_user_with_capabilities),
    db: AsyncSession = Depends(get_db),
):
    user, caps = user_caps
    if not any(c in caps for c in (_CAP_ADMIN, _CAP_DESIGN, _CAP_RUN, _CAP_REVIEW)):
        raise AppError(403, "FORBIDDEN", "Bạn không có quyền truy cập ETL.")

    p = await db.get(EtlPipeline, uuid.UUID(pipeline_id))
    if not p:
        raise AppError(404, "PIPELINE_NOT_FOUND", "Không tìm thấy pipeline")

    if _CAP_ADMIN not in caps and _CAP_DESIGN not in caps:
        allowed = await check_user_scope(db, user, p.branch_id, p.location_id)
        if not allowed:
            raise AppError(403, "SCOPE_FORBIDDEN", "Không có quyền truy cập pipeline ngoài chi nhánh/kho được cấp")

    return _serialize_pipeline(p)


@router.patch("/pipelines/{pipeline_id}")
async def update_pipeline(
    pipeline_id: str,
    payload: PipelineUpdateInput,
    user_caps: tuple[User, list[str]] = Depends(get_current_user_with_capabilities),
    db: AsyncSession = Depends(get_db),
):
    user, caps = user_caps
    if not any(c in caps for c in (_CAP_ADMIN, _CAP_DESIGN)):
        raise AppError(403, "FORBIDDEN", "Bạn không có quyền sửa pipeline.")

    p = await db.get(EtlPipeline, uuid.UUID(pipeline_id))
    if not p:
        raise AppError(404, "PIPELINE_NOT_FOUND", "Không tìm thấy pipeline")

    if payload.name is not None:
        p.name = payload.name
    if payload.status is not None:
        p.status = payload.status
    if payload.branch_id is not None:
        p.branch_id = uuid.UUID(payload.branch_id) if payload.branch_id else None
    if payload.location_id is not None:
        p.location_id = uuid.UUID(payload.location_id) if payload.location_id else None
    if payload.destination_location_id is not None:
        p.destination_location_id = uuid.UUID(payload.destination_location_id) if payload.destination_location_id else None
    if payload.schedule_cron is not None:
        p.schedule_cron = payload.schedule_cron
    if payload.config_json is not None:
        p.config_json = payload.config_json

    await db.commit()
    await db.refresh(p)
    return _serialize_pipeline(p)


# --------------------------------------------------------------------------
# 3. Mapping Versions API
# --------------------------------------------------------------------------


@router.get("/pipelines/{pipeline_id}/mapping-versions")
async def list_mapping_versions(
    pipeline_id: str,
    user_caps: tuple[User, list[str]] = Depends(get_current_user_with_capabilities),
    db: AsyncSession = Depends(get_db),
):
    user, caps = user_caps
    if not any(c in caps for c in (_CAP_ADMIN, _CAP_DESIGN, _CAP_RUN, _CAP_REVIEW)):
        raise AppError(403, "FORBIDDEN", "Bạn không có quyền xem các phiên bản ánh xạ.")

    p = await db.get(EtlPipeline, uuid.UUID(pipeline_id))
    if not p:
        raise AppError(404, "PIPELINE_NOT_FOUND", "Pipeline không tồn tại")

    stmt = select(EtlMappingVersion).where(EtlMappingVersion.pipeline_id == p.id).order_by(desc(EtlMappingVersion.version))
    versions = (await db.execute(stmt)).scalars().all()
    return {"mapping_versions": [_serialize_mapping_version(v) for v in versions]}


@router.post("/pipelines/{pipeline_id}/mapping-versions", status_code=status.HTTP_201_CREATED)
async def create_mapping_version(
    pipeline_id: str,
    payload: MappingVersionCreateInput,
    user_caps: tuple[User, list[str]] = Depends(get_current_user_with_capabilities),
    db: AsyncSession = Depends(get_db),
):
    user, caps = user_caps
    if not any(c in caps for c in (_CAP_ADMIN, _CAP_DESIGN)):
        raise AppError(403, "FORBIDDEN", "Chỉ quản trị viên hoặc nhà thiết kế mới được tạo phiên bản ánh xạ.")

    p = await db.get(EtlPipeline, uuid.UUID(pipeline_id))
    if not p:
        raise AppError(404, "PIPELINE_NOT_FOUND", "Pipeline không tồn tại")

    # Determine next version number
    max_ver = (
        await db.execute(
            select(func.coalesce(func.max(EtlMappingVersion.version), 0)).where(
                EtlMappingVersion.pipeline_id == p.id
            )
        )
    ).scalar_one()

    mv = EtlMappingVersion(
        id=uuid.uuid4(),
        pipeline_id=p.id,
        version=max_ver + 1,
        status="draft",
        mapping_json=[r.model_dump() for r in payload.mapping_rules],
        validation_rules_json=payload.validation_rules or {},
        duplicate_policy=payload.duplicate_policy,
        created_by=user.id,
    )
    db.add(mv)
    await db.commit()
    await db.refresh(mv)
    return _serialize_mapping_version(mv)


@router.post("/pipelines/{pipeline_id}/mapping-versions/{version_id}/publish")
async def publish_mapping_version(
    pipeline_id: str,
    version_id: str,
    user_caps: tuple[User, list[str]] = Depends(get_current_user_with_capabilities),
    db: AsyncSession = Depends(get_db),
):
    user, caps = user_caps
    if not any(c in caps for c in (_CAP_ADMIN, _CAP_DESIGN)):
        raise AppError(403, "FORBIDDEN", "Chỉ quản trị viên hoặc nhà thiết kế mới được phát hành ánh xạ.")

    mv = await db.get(EtlMappingVersion, uuid.UUID(version_id))
    if not mv or str(mv.pipeline_id) != pipeline_id:
        raise AppError(404, "MAPPING_NOT_FOUND", "Không tìm thấy mapping version")

    # Retire previous published versions
    prev_stmt = select(EtlMappingVersion).where(
        EtlMappingVersion.pipeline_id == mv.pipeline_id,
        EtlMappingVersion.status == "published",
        EtlMappingVersion.id != mv.id,
    )
    published = (await db.execute(prev_stmt)).scalars().all()
    for prev in published:
        prev.status = "retired"

    mv.status = "published"
    mv.published_at = etl_engine.utc_now()
    await db.commit()
    await db.refresh(mv)
    return _serialize_mapping_version(mv)


# --------------------------------------------------------------------------
# 4. Runs & Ingestion API
# --------------------------------------------------------------------------


@router.post("/pipelines/{pipeline_id}/runs", status_code=status.HTTP_201_CREATED)
async def trigger_run(
    pipeline_id: str,
    request: Request,
    user_caps: tuple[User, list[str]] = Depends(get_current_user_with_capabilities),
    db: AsyncSession = Depends(get_db),
):
    user, caps = user_caps
    if not any(c in caps for c in (_CAP_ADMIN, _CAP_RUN)):
        raise AppError(403, "FORBIDDEN", "Bạn không có quyền chạy ETL.")

    p = await db.get(EtlPipeline, uuid.UUID(pipeline_id))
    if not p:
        raise AppError(404, "PIPELINE_NOT_FOUND", "Pipeline không tồn tại")

    if p.status != "active":
        raise AppError(400, "PIPELINE_NOT_ACTIVE", f"Pipeline đang ở trạng thái {p.status}, không thể chạy.")

    # Scope verification
    if _CAP_ADMIN not in caps:
        allowed = await check_user_scope(db, user, p.branch_id, p.location_id)
        if not allowed:
            raise AppError(403, "SCOPE_FORBIDDEN", "Bạn không có quyền chạy pipeline ngoài chi nhánh/kho được cấp")

    # Load published mapping version
    mv_stmt = (
        select(EtlMappingVersion)
        .where(EtlMappingVersion.pipeline_id == p.id, EtlMappingVersion.status == "published")
        .order_by(desc(EtlMappingVersion.version))
    )
    mapping_version = (await db.execute(mv_stmt)).scalars().first()
    if not mapping_version:
        raise AppError(400, "NO_PUBLISHED_MAPPING", "Pipeline chưa có phiên bản ánh xạ nào được phát hành.")

    raw_rows: list[dict[str, Any]] = []
    external_event_id: str | None = None

    content_type = (request.headers.get("content-type") or "").lower()
    if "multipart/form-data" in content_type:
        form = await request.form()
        upload_file = form.get("file")
        if upload_file and hasattr(upload_file, "read"):
            content = await upload_file.read()
            filename = getattr(upload_file, "filename", "upload.csv") or "upload.csv"
            file_ext = filename.split(".")[-1].lower() if "." in filename else "csv"
            raw_rows = etl_engine.parse_raw_source(content, file_ext)
    else:
        try:
            body_dict = await request.json()
            if isinstance(body_dict, dict):
                raw_rows = body_dict.get("raw_rows") or []
                external_event_id = body_dict.get("external_event_id")
            elif isinstance(body_dict, list):
                raw_rows = body_dict
        except Exception:
            pass

    if not raw_rows:
        raise AppError(422, "MISSING_INPUT", "Cần tải file đính kèm hoặc truyền raw_rows trong JSON")

    # Idempotency / Duplicate Run check
    fingerprint = etl_engine.compute_fingerprint(raw_rows)
    existing_stmt = select(EtlRun).where(
        EtlRun.pipeline_id == p.id,
        EtlRun.source_fingerprint == fingerprint,
        EtlRun.status.in_(["staged", "reviewing", "posted"]),
    )
    existing_run = (await db.execute(existing_stmt)).scalars().first()
    if existing_run:
        return _serialize_run(existing_run)

    run, staged_rows = await etl_engine.generate_staging_run(
        db=db,
        pipeline=p,
        mapping_version=mapping_version,
        raw_rows=raw_rows,
        runner=user,
        external_event_id=external_event_id,
    )
    await db.commit()
    await db.refresh(run)

    return _serialize_run(run)


@router.get("/runs")
async def list_runs(
    pipeline_id: str | None = None,
    status_filter: str | None = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=200),
    user_caps: tuple[User, list[str]] = Depends(get_current_user_with_capabilities),
    db: AsyncSession = Depends(get_db),
):
    user, caps = user_caps
    if not any(c in caps for c in (_CAP_ADMIN, _CAP_DESIGN, _CAP_RUN, _CAP_REVIEW)):
        raise AppError(403, "FORBIDDEN", "Bạn không có quyền xem danh sách tiến trình ETL.")

    stmt = select(EtlRun).order_by(desc(EtlRun.created_at)).limit(limit)
    if pipeline_id:
        stmt = stmt.where(EtlRun.pipeline_id == uuid.UUID(pipeline_id))
    if status_filter:
        stmt = stmt.where(EtlRun.status == status_filter)

    runs = (await db.execute(stmt)).scalars().all()
    return {"runs": [_serialize_run(r) for r in runs]}


@router.get("/runs/{run_id}")
async def get_run(
    run_id: str,
    user_caps: tuple[User, list[str]] = Depends(get_current_user_with_capabilities),
    db: AsyncSession = Depends(get_db),
):
    user, caps = user_caps
    if not any(c in caps for c in (_CAP_ADMIN, _CAP_DESIGN, _CAP_RUN, _CAP_REVIEW)):
        raise AppError(403, "FORBIDDEN", "Bạn không có quyền xem tiến trình ETL.")

    run = await db.get(EtlRun, uuid.UUID(run_id))
    if not run:
        raise AppError(404, "RUN_NOT_FOUND", "Không tìm thấy ETL run")
    return _serialize_run(run)


@router.get("/runs/{run_id}/rows")
async def get_run_rows(
    run_id: str,
    valid: bool | None = None,
    search: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    user_caps: tuple[User, list[str]] = Depends(get_current_user_with_capabilities),
    db: AsyncSession = Depends(get_db),
):
    user, caps = user_caps
    if not any(c in caps for c in (_CAP_ADMIN, _CAP_DESIGN, _CAP_RUN, _CAP_REVIEW)):
        raise AppError(403, "FORBIDDEN", "Bạn không có quyền xem chi tiết dòng ETL.")

    run_uuid = uuid.UUID(run_id)
    stmt = select(EtlRunRow).where(EtlRunRow.run_id == run_uuid).order_by(EtlRunRow.row_number)

    if valid is not None:
        stmt = stmt.where(EtlRunRow.valid == valid)
    if search:
        stmt = stmt.where(EtlRunRow.source_row_key.ilike(f"%{search}%"))

    # Total count
    count_stmt = select(func.count(EtlRunRow.id)).where(EtlRunRow.run_id == run_uuid)
    if valid is not None:
        count_stmt = count_stmt.where(EtlRunRow.valid == valid)
    total = (await db.execute(count_stmt)).scalar_one()

    offset = (page - 1) * page_size
    rows = (await db.execute(stmt.offset(offset).limit(page_size))).scalars().all()

    return {
        "run_id": run_id,
        "total": total,
        "page": page,
        "page_size": page_size,
        "rows": [_serialize_run_row(r) for r in rows],
    }


@router.post("/runs/{run_id}/review")
async def review_run(
    run_id: str,
    payload: ReviewInput,
    user_caps: tuple[User, list[str]] = Depends(get_current_user_with_capabilities),
    db: AsyncSession = Depends(get_db),
):
    user, caps = user_caps
    if not any(c in caps for c in (_CAP_ADMIN, _CAP_REVIEW)):
        raise AppError(403, "FORBIDDEN", "Chỉ người kiểm tra hoặc quản trị viên mới được rà soát staging.")

    run = await db.get(EtlRun, uuid.UUID(run_id))
    if not run:
        raise AppError(404, "RUN_NOT_FOUND", "Không tìm thấy ETL run")

    if run.status not in ("staged", "reviewing"):
        raise AppError(409, "INVALID_STATE", f"Run đang ở trạng thái {run.status}, không thể review")

    run.reviewer_id = user.id
    run.review_decision = payload.decision
    run.review_note = payload.note

    if payload.decision == "approved":
        run.status = "reviewing"  # Ready to post
    else:
        run.status = "rejected"

    await db.commit()
    await db.refresh(run)
    return _serialize_run(run)


@router.post("/runs/{run_id}/post")
async def post_run(
    run_id: str,
    user_caps: tuple[User, list[str]] = Depends(get_current_user_with_capabilities),
    db: AsyncSession = Depends(get_db),
):
    user, caps = user_caps
    run = await db.get(EtlRun, uuid.UUID(run_id))
    if not run:
        raise AppError(404, "RUN_NOT_FOUND", "Không tìm thấy ETL run")

    pipeline = await db.get(EtlPipeline, run.pipeline_id)
    if not pipeline:
        raise AppError(404, "PIPELINE_NOT_FOUND", "Pipeline liên kết không tồn tại")

    target = pipeline.target
    single_admin_override = False

    # Target specific authorization checks
    if target == "balance_adjustment_admin":
        if _CAP_POST_BALANCE not in caps and _CAP_ADMIN not in caps:
            raise AppError(
                403,
                "MISSING_CAPABILITY",
                "Bạn không có quyền tự phê duyệt điều chỉnh tồn kho.",
            )
        # Single admin override policy
        if str(run.runner_id) == str(user.id):
            single_admin_override = True
    else:
        if not any(c in caps for c in (_CAP_ADMIN, _CAP_REVIEW)):
            raise AppError(403, "FORBIDDEN", "Bạn không có quyền phát hành (post) kết quả ETL.")

    result = await etl_engine.execute_etl_posting(
        db=db,
        run=run,
        pipeline=pipeline,
        actor=user,
        single_admin_override=single_admin_override,
    )
    return result


@router.get("/runs/{run_id}/error-report")
async def get_error_report(
    run_id: str,
    format: str = Query("csv", pattern="^(csv|json)$"),
    user_caps: tuple[User, list[str]] = Depends(get_current_user_with_capabilities),
    db: AsyncSession = Depends(get_db),
):
    user, caps = user_caps
    if not any(c in caps for c in (_CAP_ADMIN, _CAP_DESIGN, _CAP_RUN, _CAP_REVIEW)):
        raise AppError(403, "FORBIDDEN", "Bạn không có quyền tải báo cáo lỗi.")

    run_uuid = uuid.UUID(run_id)
    stmt = (
        select(EtlRunRow)
        .where(EtlRunRow.run_id == run_uuid, EtlRunRow.valid.is_(False))
        .order_by(EtlRunRow.row_number)
    )
    invalid_rows = (await db.execute(stmt)).scalars().all()

    if format == "json":
        return {
            "run_id": run_id,
            "invalid_count": len(invalid_rows),
            "errors": [
                {
                    "row_number": r.row_number,
                    "source_row_key": r.source_row_key,
                    "raw_data": r.raw_data_json,
                    "errors": r.errors_json,
                }
                for r in invalid_rows
            ],
        }

    # CSV format
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Dòng", "Khóa dữ liệu (SKU/Code)", "Chi tiết lỗi", "Dữ liệu gốc"])
    for r in invalid_rows:
        err_msg = "; ".join(r.errors_json or [])
        raw_str = json.dumps(r.raw_data_json, ensure_ascii=False)
        writer.writerow([
            _csv_safe(r.row_number),
            _csv_safe(r.source_row_key or ""),
            _csv_safe(err_msg),
            _csv_safe(raw_str),
        ])

    csv_content = output.getvalue()
    return PlainTextResponse(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="etl_error_report_{run_id}.csv"'},
    )


@router.post("/runs/{run_id}/cancel")
async def cancel_run(
    run_id: str,
    user_caps: tuple[User, list[str]] = Depends(get_current_user_with_capabilities),
    db: AsyncSession = Depends(get_db),
):
    user, caps = user_caps
    run = await db.get(EtlRun, uuid.UUID(run_id))
    if not run:
        raise AppError(404, "RUN_NOT_FOUND", "Không tìm thấy ETL run")

    if run.status in ("posted", "cancelled"):
        raise AppError(409, "CANNOT_CANCEL", f"Run ở trạng thái {run.status} không thể hủy")

    run.status = "cancelled"
    await db.commit()
    await db.refresh(run)
    return _serialize_run(run)
