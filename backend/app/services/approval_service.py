"""Approval service - nghiệp vụ phê duyệt."""

from app.domain.approval import ApprovalWorkflow as DomainApprovalService


class ApprovalService:
    """Dịch vụ nghiệp vụ phê duyệt."""

    def __init__(self):
        self.domain_service = DomainApprovalService()
