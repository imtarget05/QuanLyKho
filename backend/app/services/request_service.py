"""Request service - phiếu nhập - xuất - điều chỉnh kho."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from app.domain.approval import ApprovalWorkflow
from app.domain.exceptions import (
    DomainError,
    IdempotencyConflictError,
    InvalidStateTransitionError,
    NotFoundError,
)
from app.domain.inventory import (
    RequestStatus,
)
from app.domain.request import InventoryRequest as DomainRequest
from app.domain.request import InventoryRequestLine as DomainRequestLine
from app.repositories.inventory_repository import (
    BalanceRepository,
    ItemRepository,
    LocationRepository,
    MovementRepository,
)
from app.repositories.request_repository import (
    InventoryRequestLineRepository,
    InventoryRequestRepository,
)
from app.repositories.user_repository import UserRepository


@dataclass(frozen=True)
class RequestLine:
    """Frontend request line (dòng phiếu)."""
    id: str
    item_id: str
    item_name: str
    item_sku: str
    quantity: float
    unit_price: float
    line_total: float
    note: str | None = None


@dataclass(frozen=True)
class RequestResponse:
    """Frontend request response."""
    id: str
    number: str
    kind: str
    status: str
    total_amount: float
    requested_by: str
    requested_by_name: str
    location_id: str
    location_name: str
    created_at: str
    lines: list[RequestLine]
    total_quantity: float


class RequestService:
    """
    Phiếu nhập và xuất - nghiệp vụ chính của kho.
    """

    def __init__(
        self,
        request_repo: InventoryRequestRepository,
        line_repo: InventoryRequestLineRepository,
        item_repo: ItemRepository,
        location_repo: LocationRepository,
        balance_repo: BalanceRepository,
        movement_repo: MovementRepository,
        user_repo: UserRepository,
    ):
        self.request_repo = request_repo
        self.line_repo = line_repo
        self.item_repo = item_repo
        self.location_repo = location_repo
        self.balance_repo = balance_repo
        self.movement_repo = movement_repo
        self.user_repo = user_repo

    def _generate_request_number(self, kind: str) -> str:
        """Tự động sinh số phiếu."""
        import random
        prefixes = {"receipt": "RR", "issue": "RI", "transfer": "TR", "adjustment": "AD"}
        prefix = prefixes.get(kind, "RF")
        seq = random.randint(1, 9999)
        return f"{prefix}{seq:04d}"

    def _get_user_name(self, user_id: str) -> str:
        """Lấy tên người dùng."""
        user = self.user_repo.get(user_id)
        return user.name if user else "?"

    def create_request(
        self,
        user_id: str,
        kind: str,
        location_id: str,
        lines: list[dict],
        idempotency_key: str | None = None,
    ) -> RequestResponse:
        """
        Tạo phiếu nhập/xuất khảo.
        Chỉ tạo phiếu draft, không đổi trạng thái.
        """
        # Kiểm tra idempotency
        if idempotency_key:
            existing = self.request_repo.get_by_number(idempotency_key)
            if existing:
                raise IdempotencyConflictError(idempotency_key)

        # Lấy location
        location = self.location_repo.get(location_id)
        if location is None:
            raise NotFoundError("Kho", location_id)

        # Tạo request domain
        request_id = f"req_{uuid.uuid4().hex[:12]}"
        number = self._generate_request_number(kind)

        domain_request = DomainRequest.create(
            id=request_id,
            number=number,
            kind=kind,
            location_id=location_id,
            user_id=user_id,
            status=RequestStatus.DRAFT,
            lines=[],
            version=1,
            created_at=datetime.now(UTC),
        )

        # Tạo dòng
        for line_data in lines:
            item = self.item_repo.get(line_data["item_id"])
            if item is None:
                raise NotFoundError("Mặt hàng", line_data["item_id"])

            domain_line = DomainRequestLine.create(
                id=uuid.uuid4().hex[:12],
                request_id=request_id,
                item_id=item.id.value,
                quantity=Decimal(str(line_data["quantity"])),
                unit_price=Decimal(str(line_data.get("unit_price", 0))),
                note=line_data.get("note"),
            )
            domain_request.add_line(domain_line)

        # Lưu request
        saved = self.request_repo.add(domain_request)

        # Lưu dòng
        for domain_line in saved.lines:
            self.line_repo.add(domain_line)

        # Chuyển đổi sang frontend response
    def _to_response(self, request: DomainRequest, location) -> RequestResponse:
        """Chuyển đổi sang frontend response."""
        total_amount = sum(
            line.unit_price * line.quantity for line in request.lines
        )
        total_quantity = sum(line.quantity for line in request.lines)

        lines_response = []
        for line in request.lines:
            item = self.item_repo.get(line.item_id)
            lines_response.append(RequestLine(
                id=line.id,
                item_id=line.item_id,
                item_name=item.name if item else "Unknown",
                item_sku=item.sku if item else "",
                quantity=float(line.quantity),
                unit_price=float(line.unit_price),
                line_total=float(line.unit_price * line.quantity),
                note=line.note,
            ))

        return RequestResponse(
            id=request.id,
            number=request.number,
            kind=request.kind,
            status=request.status.value,
            total_amount=float(total_amount),
            requested_by=request.user_id,
            requested_by_name=self._get_user_name(request.user_id),
            location_id=request.location_id,
            location_name=location.name,
            created_at=request.created_at.isoformat() if request.created_at else "",
            lines=lines_response,
            total_quantity=float(total_quantity),
        )

    def submit(self, request_id: str, user_id: str) -> RequestResponse:
        """Chuyển phiếu từ draft sang pending."""
        request = self.request_repo.get(request_id)
        if request is None:
            raise NotFoundError("Phiếu", request_id)

        if request.status != RequestStatus.DRAFT:
            raise InvalidStateTransitionError(
                subject="request", from_status=request.status.value, to_status="pending"
            )

        request.status = RequestStatus.PENDING
        request.version += 1

        # TODO: tạo approval workflow tự động ở đây
        self.request_repo.update(request)

        location = self.location_repo.get(request.location_id)
        return self._to_response(request, location)

    def approve(self, request_id: str, approver_id: str, reason: str | None = None) -> RequestResponse:
        """
        Duyệt phiếu - chuyển từ pending sang posted.
        """
        request = self.request_repo.get(request_id)
        if request is None:
            raise NotFoundError("Phiếu", request_id)

        if request.status != RequestStatus.PENDING:
            raise InvalidStateTransitionError(
                subject="request", from_status=request.status.value, to_status="approved"
            )

        # Xác thực approver
        user = self.user_repo.get(approver_id)
        if user is None or not user.is_admin:
            raise DomainError("UNAUTHORIZED", "Chỉ admin được phép duyệt phiếu")

        # Tạo approval record
        approval = ApprovalWorkflow(
            subject_type="inventory_request",
            subject_id=request_id,
            maker_id=request.user_id,
            approver_id=approver_id,
            status="approved",
        )
        approval.approve(approver_id, reason)

        # Cập nhật status
        request.status = RequestStatus.POSTED
        request.version += 1
        self.request_repo.update(request)

        location = self.location_repo.get(request.location_id)
        return self._to_response(request, location)

    def get(self, request_id: str) -> RequestResponse:
        """Lấy thông tin phiếu."""
        request = self.request_repo.get(request_id)
        if request is None:
            raise NotFoundError("Phiếu", request_id)

        location = self.location_repo.get(request.location_id)
        if location is None:
            raise NotFoundError("Kho", request.location_id)

        return self._to_response(request, location)

    def list(
        self,
        skip: int = 0,
        limit: int = 50,
        kind: str | None = None,
        status: str | None = None,
        location_id: str | None = None,
    ) -> list[RequestResponse]:
        """Danh sách phiếu."""
        requests = self.request_repo.list(
            skip=skip,
            limit=limit,
            kind=kind,
            status=status,
            location_id=location_id,
        )
        return [
            self._to_response(req, self.location_repo.get(req.location_id))
            for req in requests
        ]

    def cancel(self, request_id: str, user_id: str) -> RequestResponse:
        """Hủy phiếu - chỉ khi draft."""
        request = self.request_repo.get(request_id)
        if request is None:
            raise NotFoundError("Phiếu", request_id)

        if request.status != RequestStatus.DRAFT:
            raise InvalidStateTransitionError(
                subject="request", from_status=request.status.value, to_status="cancelled"
            )

        request.status = RequestStatus.CANCELLED
        request.version += 1
        self.request_repo.update(request)

        location = self.location_repo.get(request.location_id)
        return self._to_response(request, location)
