"""OTP single-use codes (password reset / login 2FA / sensitive action).

Durable storage for OTP codes so they survive process restarts and are shared
across API replicas. Plaintext code is never stored; only bcrypt hash.
"""

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import DateTime, Integer, String
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import Base, TimestampMixin, utc_now


class OtpCode(Base, TimestampMixin):
    """A single-use OTP code bound to a username + purpose."""

    __tablename__ = "otp_codes"

    id: str = sa.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    username: str = sa.Column(String(64), nullable=False, index=True)
    code_hash: str = sa.Column(String(256), nullable=False)
    purpose: str = sa.Column(
        String(32), nullable=False
    )  # password_reset | login_2fa | sensitive_action
    channel: str = sa.Column(
        String(16), nullable=False, server_default="email"
    )  # email | sms
    expires_at: datetime = sa.Column(DateTime(timezone=True), nullable=False)
    consumed_at: datetime | None = sa.Column(DateTime(timezone=True), nullable=True)
    attempts: int = sa.Column(Integer, nullable=False, default=0)
    locked_until: datetime | None = sa.Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        sa.UniqueConstraint("username", "purpose", name="uq_otp_codes_username_purpose"),
    )

    def is_expired(self, now: datetime | None = None) -> bool:
        check = now or utc_now()
        return check > self.expires_at

    def is_consumed(self) -> bool:
        return self.consumed_at is not None

    def is_locked(self, now: datetime | None = None) -> bool:
        check = now or utc_now()
        return self.locked_until is not None and check < self.locked_until

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<OtpCode {self.username} purpose={self.purpose} consumed={self.is_consumed()}>"
