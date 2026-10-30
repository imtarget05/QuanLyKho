"""Bounded stocktake/adjustment assessment loop (read-only MVP, deterministic)."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.iam import User
from app.models.inventory import (
    InventoryRequest,
    InventoryRequestLine,
    Stocktake,
    StocktakeLine,
)


class AssessmentVerdict(StrEnum):
    NORMAL = "normal"
    HIGH_RISK = "high_risk"
    STALE_VERSION = "stale_version"
    MISSING_EVIDENCE = "missing_evidence"
    SCOPE_VIOLATION = "scope_violation"
    POLICY_VIOLATION = "policy_violation"


@dataclass
class StocktakeAssessmentOptions:
    enabled: bool = False
    staleness_minutes: int = 60
    source_sha: str = ""


@dataclass
class TriageResult:
    verdict: AssessmentVerdict
    reasoning: str
    can_proceed: bool


@dataclass
class AnalysisNotes:
    supported_risk_factors: str
    discrepancies: str
    source_references: str
    uncertainty: str
    cannot_lower_deterministic_risk: bool = True


@dataclass
class CriticBrief:
    evidence_validated: bool
    version_fresh: bool
    brief_for_checker: str
    actions_blocked: bool


@dataclass
class AssessmentResult:
    request_id: str
    verdict: AssessmentVerdict
    triaged: TriageResult
    analyzed: AnalysisNotes
    critiqued: CriticBrief
    recommendation: str
    is_read_only: bool = True
    completed_at: datetime = field(default_factory=lambda: datetime.now(UTC))


_READ_ONLY_RECOMMENDATION = (
    "Recommend Checker review via Maker/Checker approval flow. "
    "Agent cannot approve/post/change inventory."
)

_BLOCKED_RECOMMENDATION = (
    "Resolve blocked issue before Checker review via Maker/Checker approval flow. "
    "Agent cannot approve/post/change inventory."
)

_HIGH_RISK_QTY = 10.0
_MIN_REASON_LEN = 5


def _parse_quantity(value: Any) -> float:
    if value is None:
        return 0.0
    digits = re.sub(r"[^0-9.\-]", "", str(value))
    try:
        return float(digits) if digits else 0.0
    except ValueError:
        return 0.0


def _blocked_result(request_id: str, verdict: AssessmentVerdict, reasoning: str) -> AssessmentResult:
    triaged = TriageResult(verdict=verdict, reasoning=reasoning, can_proceed=False)
    analyzed = AnalysisNotes(
        supported_risk_factors="Chặn trước khi đánh giá rủi ro deterministik.",
        discrepancies="Xem lý do chặn trong trường triaged.",
        source_references=request_id,
        uncertainty="Không phân tích sâu do phiếu bị chặn.",
        cannot_lower_deterministic_risk=True,
    )
    critiqued = CriticBrief(
        evidence_validated=False,
        version_fresh=False,
        brief_for_checker=f"Brief Checker: {request_id} bị chặn ({verdict.value}): {reasoning}",
        actions_blocked=True,
    )
    return AssessmentResult(
        request_id=request_id,
        verdict=verdict,
        triaged=triaged,
        analyzed=analyzed,
        critiqued=critiqued,
        recommendation=_BLOCKED_RECOMMENDATION,
        is_read_only=True,
    )


def _disabled_result(request_id: str) -> AssessmentResult:
    triaged = TriageResult(
        verdict=AssessmentVerdict.NORMAL,
        reasoning="Stocktake assessment agent is disabled (ai_agent_enabled=false).",
        can_proceed=False,
    )
    analyzed = AnalysisNotes(
        supported_risk_factors="Agent tắt; không đánh giá rủi ro.",
        discrepancies="Agent tắt; không đánh giá chênh lệch.",
        source_references="Agent tắt; không có nguồn tham chiếu.",
        uncertainty="Agent tắt — không đánh giá thực tế.",
    )
    critiqued = CriticBrief(
        evidence_validated=False,
        version_fresh=False,
        brief_for_checker="Agent tắt; không có brief gửi Checker.",
        actions_blocked=True,
    )
    return AssessmentResult(
        request_id=request_id,
        verdict=AssessmentVerdict.NORMAL,
        triaged=triaged,
        analyzed=analyzed,
        critiqued=critiqued,
        recommendation=_READ_ONLY_RECOMMENDATION,
        is_read_only=True,
    )


class StocktakeAssessmentWorkflow:
    def __init__(
        self,
        options: StocktakeAssessmentOptions | None = None,
        settings_obj: Any = None,
    ) -> None:
        from app.config import settings as _settings

        self.options = options or StocktakeAssessmentOptions()
        self.settings = settings_obj or _settings

    async def assess_async(
        self,
        request_id: str | UUID,
        assessed_by: str,
        db_session: AsyncSession,
    ) -> AssessmentResult:
        request_id_str = str(request_id)
        if not self.options.enabled:
            return _disabled_result(request_id_str)

        from app.api.routes.auth_utils import get_accessible_location_ids

        rid: UUID | None = None
        try:
            rid = UUID(request_id_str)
        except (ValueError, AttributeError, TypeError):
            rid = None

        request_obj: Any = None
        kind = ""
        location_id: Any = None
        maker_id: Any = None
        version = 1
        reason = ""
        updated_at: datetime | None = None
        total_qty = 0.0
        line_count = 0

        if rid is not None:
            inventory_request = (
                await db_session.execute(
                    select(InventoryRequest).where(InventoryRequest.id == rid)
                )
            ).scalars().first()
            if inventory_request is not None:
                kind = "inventory"
                request_obj = inventory_request
                location_id = inventory_request.source_id or inventory_request.dest_id
                maker_id = inventory_request.maker_id
                version = inventory_request.version
                reason = inventory_request.reason or ""
                updated_at = inventory_request.updated_at
                qty_row = await db_session.execute(
                    select(func.coalesce(func.sum(InventoryRequestLine.quantity), 0)).where(
                        InventoryRequestLine.request_id == inventory_request.id
                    )
                )
                total_qty = _parse_quantity(qty_row.scalar())
                line_row = await db_session.execute(
                    select(func.count(InventoryRequestLine.id)).where(
                        InventoryRequestLine.request_id == inventory_request.id
                    )
                )
                line_count = int(line_row.scalar() or 0)
            else:
                stocktake = (
                    await db_session.execute(select(Stocktake).where(Stocktake.id == rid))
                ).scalars().first()
                if stocktake is not None:
                    kind = "stocktake"
                    request_obj = stocktake
                    location_id = stocktake.location_id
                    maker_id = stocktake.maker_id
                    version = stocktake.version
                    reason = stocktake.note or ""
                    updated_at = stocktake.updated_at
                    var_row = await db_session.execute(
                        select(func.coalesce(func.sum(StocktakeLine.variance), 0)).where(
                            StocktakeLine.stocktake_id == stocktake.id
                        )
                    )
                    total_qty = abs(_parse_quantity(var_row.scalar()))
                    line_row = await db_session.execute(
                        select(func.count(StocktakeLine.id)).where(
                            StocktakeLine.stocktake_id == stocktake.id
                        )
                    )
                    line_count = int(line_row.scalar() or 0)

        if request_obj is None:
            return _blocked_result(
                request_id_str,
                AssessmentVerdict.MISSING_EVIDENCE,
                "Không tìm thấy phiếu trong cơ sở dữ liệu.",
            )

        assessed_user: User | None = None
        if assessed_by:
            user_row = (
                await db_session.execute(select(User).where(User.username == assessed_by))
            ).scalars().first()
            assessed_user = user_row
        if assessed_user is None:
            return _blocked_result(
                request_id_str,
                AssessmentVerdict.SCOPE_VIOLATION,
                "Không xác định được người đánh giá.",
            )

        allowed_location_ids = await get_accessible_location_ids(db_session, assessed_user)
        if allowed_location_ids is not None and location_id not in allowed_location_ids:
            return _blocked_result(
                request_id_str,
                AssessmentVerdict.SCOPE_VIOLATION,
                "Kho yêu cầu nằm ngoài phạm vi chi nhánh/vị trí được cấp quyền.",
            )

        if (
            maker_id is not None
            and assessed_user is not None
            and str(maker_id) == str(assessed_user.id)
        ):
            return _blocked_result(
                request_id_str,
                AssessmentVerdict.POLICY_VIOLATION,
                "Trưởng ca không được tự duyệt phiếu của mình (Maker self-approval).",
            )

        now = datetime.now(UTC)
        if not reason or len(reason.strip()) < _MIN_REASON_LEN:
            return _blocked_result(
                request_id_str,
                AssessmentVerdict.MISSING_EVIDENCE,
                "Thiếu lý do phiếu (diễn giải quá ngắn hoặc trống).",
            )
        if line_count <= 0:
            return _blocked_result(
                request_id_str,
                AssessmentVerdict.MISSING_EVIDENCE,
                "Không có dòng phiếu/kể kê kèm theo.",
            )
        if updated_at is None or (now - updated_at).total_seconds() > self.options.staleness_minutes * 60:
            return _blocked_result(
                request_id_str,
                AssessmentVerdict.STALE_VERSION,
                "Phiếu phiên bản cũ; dữ liệu tồn kho có thể đã thay đổi kể từ khi phiên bản này được ghi.",
            )

        if total_qty >= _HIGH_RISK_QTY:
            verdict = AssessmentVerdict.HIGH_RISK
            reasoning = f"Số lượng {total_qty} vượt ngưỡng rủi ro cao (>= {_HIGH_RISK_QTY})."
            can_proceed = True
        else:
            verdict = AssessmentVerdict.NORMAL
            reasoning = "Trong định mức cho phép; không có dấu hiệu rủi ro cao deterministik."
            can_proceed = True

        analyzed = AnalysisNotes(
            supported_risk_factors=(
                f"Loại phiếu: {kind}; số lượng: {total_qty}; phiên bản: {version}; "
                f"mã đơn: {request_id_str}; lý do dài {len(reason)} ký tự; số dòng: {line_count}."
            ),
            discrepancies=(
                f"Tổng chênh lệch kiểm kê: {total_qty}; "
                f"{'cần đối chiếu thực tế' if kind == 'stocktake' else 'trong ngưỡng cho phép'}."
            ),
            source_references=(
                f"{request_id_str} · {kind} · version={version} · "
                "nguồn: inv_requests / inv_request_lines hoặc inv_stocktakes / inv_stocktake_lines."
            ),
            uncertainty=(
                "Đánh giá định lượng tại chỗ, không gọi mô hình ngôn ngữ; "
                "không có sai sót không xác định về rủi ro deterministik."
            ),
            cannot_lower_deterministic_risk=True,
        )

        evidence_validated = bool(
            reason and len(reason.strip()) >= _MIN_REASON_LEN and line_count > 0
        )
        version_fresh = (
            updated_at is not None
            and (now - updated_at).total_seconds() <= self.options.staleness_minutes * 60
        )
        critiqued = CriticBrief(
            evidence_validated=evidence_validated,
            version_fresh=version_fresh,
            brief_for_checker=(
                f"Brief Checker: phiếu {request_id_str} ({kind}), bản {version}, "
                f"rủi ro {verdict.value}; {reasoning}"
            ),
            actions_blocked=verdict != AssessmentVerdict.NORMAL,
        )

        recommendation = (
            _READ_ONLY_RECOMMENDATION
            if verdict in (AssessmentVerdict.NORMAL, AssessmentVerdict.HIGH_RISK)
            else _BLOCKED_RECOMMENDATION
        )

        return AssessmentResult(
            request_id=request_id_str,
            verdict=verdict,
            triaged=TriageResult(verdict=verdict, reasoning=reasoning, can_proceed=can_proceed),
            analyzed=analyzed,
            critiqued=critiqued,
            recommendation=recommendation,
            is_read_only=True,
        )
