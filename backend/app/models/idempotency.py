"""Durable Idempotency-Key store (R2 — docs/06:3, docs/10 A3/A4).

Bảng `idempotency_keys` lưu key + hash payload + response đã trả, để:

- key còn hiệu lực **sau khi restart** process (store in-memory mất trắng),
- key dùng chung giữa nhiều replica/process (không phải per-process),
- `INSERT ... ON CONFLICT DO NOTHING` trong cùng transaction với nghiệp vụ để
  hai request cùng key không tạo ra hai bản ghi.

ORM khai báo ở đây (không phải `app/models/inventory.py` hay
`app/models/reconciliation.py`) vì các bảng nghiệp vụ đó thuộc luồng thay đổi
khác; module này được import bởi `app/services/idempotency.py` (runtime) và
bởi migration `027_idempotency_keys` (alembic).
"""
import uuid

from sqlalchemy import JSON, Column, DateTime, Index, Integer, String, text
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import Base


class IdempotencyKey(Base):
    """Một lần sử dụng Idempotency-Key (một key ↔ một request)."""

    __tablename__ = "idempotency_keys"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    key = Column(String(128), nullable=False, unique=True)
    scope = Column(String(128), nullable=False, default="")
    request_hash = Column(String(64), nullable=False)
    request_path = Column(String(255), nullable=True)
    status = Column(String(32), nullable=False, default="PENDING", server_default="PENDING")
    status_code = Column(Integer, nullable=True)
    response_body = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    expires_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_idempotency_keys_expires_at", "expires_at"),
        Index("ix_idempotency_keys_status", "status"),
    )

    def __repr__(self) -> str:
        return f"<IdempotencyKey {self.key} scope={self.scope}>"


IdempotencyKeyRecord = IdempotencyKey

