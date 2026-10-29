"""Multimodal Document Intake Routes.

Endpoints:
- POST /inventory/intake/extract: Upload invoice (PDF, image, text) -> parse + mathematical validation.
- POST /inventory/intake/create-draft: Create a draft InventoryRequest from validated extraction.
- POST /inventory/intake/process: Combined upload, validation, and draft creation.

Guarantees:
- Never auto-posts or updates stock balances.
- Creates InventoryRequest with status="draft", strictly preserving Maker-Checker.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes.auth_utils import require_any_capability
from app.database import get_db
from app.models.iam import User
from app.schemas.invoice_intake import (
    CreateDraftFromExtractionRequest,
    InvoiceIntakeResponse,
)
from app.services import multimodal_service

router = APIRouter(prefix="/inventory/intake", tags=["multimodal-intake"])

_MAKER_CAPS = require_any_capability("inventory:create_request")


@router.post("/extract", response_model=InvoiceIntakeResponse)
async def extract_invoice_document(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(_MAKER_CAPS),
) -> InvoiceIntakeResponse:
    """Extract structured data from an uploaded invoice document and validate mathematics."""
    content = await file.read()
    try:
        extraction = multimodal_service.parse_invoice_bytes(
            content, file.filename or "invoice.txt"
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Lỗi phân tích tài liệu: {exc}",
        ) from exc

    report = await multimodal_service.match_catalog_items(db, extraction)
    status_str = "extracted" if report.is_valid else "validation_failed"
    msg = (
        "Trích xuất thành công và các kiểm tra toán học hợp lệ."
        if report.is_valid
        else f"Phát hiện sai lệch số học trong chứng từ: {'; '.join(report.errors)}"
    )

    return InvoiceIntakeResponse(
        extraction=extraction,
        validation=report,
        draft_request_id=None,
        status=status_str,
        message=msg,
    )


@router.post("/create-draft")
async def create_draft_from_extraction(
    payload: CreateDraftFromExtractionRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(_MAKER_CAPS),
) -> dict[str, Any]:
    """Create a draft InventoryRequest from an extraction payload.

    Strictly preserves Maker-Checker: the created request is in 'draft' status
    and must be explicitly submitted and approved by an authorized checker.
    """
    try:
        req = await multimodal_service.create_draft_receipt_from_invoice(
            db,
            payload.extraction,
            maker_id=user.id,
            dest_location_id=payload.dest_location_id,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    return {
        "draft_request_id": str(req.id),
        "status": req.status,
        "kind": req.kind,
        "supplier": req.supplier,
        "invoice_no": req.invoice_no,
        "message": (
            "Phiếu nhập kho nháp (draft) đã được tạo thành công từ hóa đơn. "
            "Vui lòng nộp duyệt (submit) và chờ Kiểm soát viên phê duyệt theo quy trình Maker-Checker."
        ),
    }


@router.post("/process", response_model=InvoiceIntakeResponse)
async def process_and_create_draft(
    file: UploadFile = File(...),
    dest_location_id: str | None = Form(None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(_MAKER_CAPS),
) -> InvoiceIntakeResponse:
    """End-to-end pipeline: parse document, validate math, and create draft receipt if location provided."""
    content = await file.read()
    try:
        extraction = multimodal_service.parse_invoice_bytes(
            content, file.filename or "invoice.txt"
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Lỗi phân tích tài liệu: {exc}",
        ) from exc

    report = await multimodal_service.match_catalog_items(db, extraction)
    draft_id = None

    if report.is_valid and dest_location_id:
        try:
            req = await multimodal_service.create_draft_receipt_from_invoice(
                db,
                extraction,
                maker_id=user.id,
                dest_location_id=dest_location_id,
            )
            draft_id = str(req.id)
            status_str = "draft_created"
            msg = (
                f"Trích xuất thành công và đã tạo phiếu nhập kho nháp (ID: {draft_id}). "
                "Cần hoàn tất quy trình Maker-Checker trước khi ghi nhận tồn kho."
            )
        except Exception as exc:
            report.is_valid = False
            report.errors.append(str(exc))
            status_str = "validation_failed"
            msg = f"Không thể tạo phiếu nháp: {exc}"
    elif not report.is_valid:
        status_str = "validation_failed"
        msg = f"Chứng từ có lỗi kiểm tra toán học: {'; '.join(report.errors)}"
    else:
        status_str = "extracted"
        msg = "Trích xuất và kiểm tra toán học hợp lệ. Chưa cung cấp dest_location_id để tạo phiếu nháp."

    return InvoiceIntakeResponse(
        extraction=extraction,
        validation=report,
        draft_request_id=draft_id,
        status=status_str,
        message=msg,
    )
