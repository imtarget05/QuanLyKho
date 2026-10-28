"""Domain exceptions - business rule violations.

Tất cả exception trong domain layer đều là pure Python, không phụ thuộc
vào HTTP hay framework. API layer sẽ map các exception này sang HTTP status.
"""


class DomainError(Exception):
    """Base exception cho mọi domain error."""

    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(message)


class InsufficientStockError(DomainError):
    """Xuất quá tồn khả dụng tại kho."""

    def __init__(self, item_id: str, location_id: str, requested: float, available: float):
        super().__init__(
            "INSUFFICIENT_STOCK",
            f"Không đủ tồn khả dụng tại kho {location_id} cho mặt hàng {item_id}. "
            f"Yêu cầu: {requested}, khả dụng: {available}",
        )
        self.item_id = item_id
        self.location_id = location_id
        self.requested = requested
        self.available = available


class SelfApprovalError(DomainError):
    """Người tạo không được tự duyệt phiếu."""

    def __init__(self, user_id: str):
        super().__init__(
            "SELF_APPROVAL_FORBIDDEN",
            f"Người tạo ({user_id}) không được tự duyệt phiếu của chính mình",
        )
        self.user_id = user_id


class InvalidStateTransitionError(DomainError):
    """Chuyển trạng thái không hợp lệ."""

    def __init__(self, subject: str, from_status: str, to_status: str):
        super().__init__(
            "INVALID_STATE_TRANSITION",
            f"Không thể chuyển {subject} từ '{from_status}' sang '{to_status}'",
        )
        self.subject = subject
        self.from_status = from_status
        self.to_status = to_status


class IdempotencyConflictError(DomainError):
    """Idempotency key đã dùng với payload khác."""

    def __init__(self, key: str):
        super().__init__(
            "IDEMPOTENCY_KEY_REUSED",
            f"Idempotency key '{key}' đã dùng với payload khác",
        )
        self.key = key


class DuplicateSerialError(DomainError):
    """Mã serial đã tồn tại."""

    def __init__(self, serial: str):
        super().__init__(
            "DUPLICATE_SERIAL",
            f"Serial '{serial}' đã tồn tại",
        )
        self.serial = serial


class NotFoundError(DomainError):
    """Entity không tồn tại."""

    def __init__(self, subject: str, id_value: str):
        super().__init__(
            "NOT_FOUND",
            f"{subject} '{id_value}' không tồn tại",
        )
        self.subject = subject
        self.id_value = id_value


class BusinessRuleError(DomainError):
    """Lỗi quy tắc nghiệp vụ chung."""

    def __init__(self, code: str, message: str):
        super().__init__(code, message)