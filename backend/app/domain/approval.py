"""Approval domain - business rules cho kiểm soát kép (maker-checker)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .exceptions import SelfApprovalError


@dataclass(frozen=True)
class ApprovalDecision:
    """Kết quả quyết định duyệt."""

    subject_type: str  # 'inventory_request', 'stocktake', 'cash_request'
    subject_id: str
    decision: str  # 'approve', 'reject', 'return'
    actor_id: str
    reason: str | None = None
    occurred_at: datetime | None = None


@dataclass
class ApprovalWorkflow:
    """Quản lý vòng đời duyệt phiếu."""

    subject_type: str
    subject_id: str
    maker_id: str
    approver_id: str | None = None
    status: str = "pending"  # pending, approved, rejected, returned
    version: int = 1
    decision: ApprovalDecision | None = None

    def can_submit(self, user_id: str) -> bool:
        """Chỉ người tạo (maker) có thể submit."""
        return self.status == "pending" and self.maker_id == user_id

    def can_approve(self, user_id: str) -> bool:
        """Chỉ người khác maker và có quyền approver mới được duyệt."""
        if self.status != "pending":
            return False
        if self.maker_id == user_id:
            return False  # Maker không tự duyệt
        if self.approver_id is not None and self.approver_id != user_id:
            return False  # Chỉ người được phân quyền
        return True

    def can_reject(self, user_id: str) -> bool:
        """Chỉ người khác maker và có quyền approver mới được từ chối."""
        return self.can_approve(user_id)

    def approve(self, user_id: str, reason: str | None = None) -> ApprovalDecision:
        """Duyệt phiếu - tạo bút toán duyệt."""
        if not self.can_approve(user_id):
            raise SelfApprovalError(user_id)
        self.decision = ApprovalDecision(
            subject_type=self.subject_type,
            subject_id=self.subject_id,
            decision="approve",
            actor_id=user_id,
            reason=reason,
            occurred_at=datetime.utcnow(),
        )
        self.status = "approved"
        self.version += 1
        self.approver_id = user_id
        return self.decision

    def reject(self, user_id: str, reason: str) -> ApprovalDecision:
        """Từ chối phiếu - bắt buộc có lý do."""
        if not self.can_reject(user_id):
            raise SelfApprovalError(user_id)
        if not reason:
            from .exceptions import DomainError
            raise DomainError("REASON_REQUIRED", "Từ chối phải có lý do")
        self.decision = ApprovalDecision(
            subject_type=self.subject_type,
            subject_id=self.subject_id,
            decision="reject",
            actor_id=user_id,
            reason=reason,
            occurred_at=datetime.utcnow(),
        )
        self.status = "rejected"
        self.version += 1
        return self.decision

    def return_for_rework(self, user_id: str, reason: str) -> ApprovalDecision:
        """Trả về chỉnh sửa - bắt buộc có lý do."""
        if not self.can_reject(user_id):
            raise SelfApprovalError(user_id)
        if not reason:
            from .exceptions import DomainError
            raise DomainError("REASON_REQUIRED", "Trả về phải có lý do")
        self.decision = ApprovalDecision(
            subject_type=self.subject_type,
            subject_id=self.subject_id,
            decision="return",
            actor_id=user_id,
            reason=reason,
            occurred_at=datetime.utcnow(),
        )
        self.status = "returned"
        self.version += 1
        return self.decision

    def resubmit(self, user_id: str) -> None:
        """Maker resubmit sau khi đã sửa."""
        if self.status != "returned":
            from .exceptions import DomainError
            raise DomainError("INVALID_STATE", "Chỉ có thể resubmit phiếu đã trả về")
        if self.maker_id != user_id:
            raise SelfApprovalError(user_id)
        self.status = "pending"
        self.version += 1