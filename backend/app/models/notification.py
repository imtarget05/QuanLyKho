"""Notification and Device Registration models."""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import Base, TimestampMixin, utc_now


class DeviceRegistration(Base, TimestampMixin):
    """Device registration for Web / Mobile push notifications."""
    __tablename__ = "iam_device_registrations"
    __table_args__ = (
        Index("ix_device_user_active", "user_id", "is_active"),
    )

    id: str = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: str = Column(UUID(as_uuid=True), ForeignKey("iam_users.id", ondelete="CASCADE"), nullable=False, index=True)
    device_token: str = Column(String(512), unique=True, nullable=False, index=True)
    platform: str = Column(String(32), nullable=False, default="web")  # web, android, ios
    device_name: str | None = Column(String(256), nullable=True)
    is_active: bool = Column(Boolean, default=True, nullable=False)
    last_seen_at: datetime = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    def __repr__(self):
        return f"<DeviceRegistration user={self.user_id} platform={self.platform} active={self.is_active}>"
