"""Durable OTP single-use service (password reset / login 2FA / sensitive action).

Plaintext code is NEVER stored — only bcrypt hash. Codes survive process restart
via the `otp_codes` table (migration `031_otp_codes`).

Hợp đồng:
- `create_otp` sinh mã 6 chữ số, lưu hash vào DB, TTL mặc định 900s (15p).
- `verify_otp` consuming: mã chỉ dùng được 1 lần, sau đó đánh dấu consumed.
- Sai 3 lần → khóa tạm 15 phút (`locked_until`).
- Rate-limit gửi OTP: tối đa 5 lần / 15 phút theo username+IP (Redis nếu có,
  fallback RAM).
"""

from __future__ import annotations

import secrets
import time
import uuid
from datetime import UTC, datetime, timedelta

from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.otp import OtpCode

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

_OTP_TTL_SECONDS = 900  # 15 phút
_MAX_ATTEMPTS = 3
_LOCK_MINUTES = 15
_SEND_RATE_LIMIT = 5  # gửi tối đa 5 OTP / 15p theo username+ip
_SEND_WINDOW_SECONDS = 15 * 60

# In-memory send rate-limit (fallback khi Redis không có).
_send_attempts: dict[str, list[float]] = {}
def _hash_code(code: str, username: str) -> str:
    """Băm mã OTP kèm username để rainbow-table khó hơn."""
    return pwd_context.hash(f"{username}:{code}")


def _verify_code(plain: str, stored_hash: str, username: str) -> bool:
    return pwd_context.verify(f"{username}:{plain}", stored_hash)


def _send_rate_key(username: str, ip: str | None) -> str:
    return f"otp:send:{username.strip().lower()}:{(ip or 'unknown').strip().lower()}"


def _is_send_rate_limited(username: str, ip: str | None) -> bool:
    """Kiểm tra số lần gửi OTP trong cửa sổ thời gian (in-memory fallback)."""
    key = _send_rate_key(username, ip)
    now = time.time()
    window = _SEND_WINDOW_SECONDS
    recent = [t for t in _send_attempts.get(key, []) if now - t < window]
    _send_attempts[key] = recent
    return len(recent) >= _SEND_RATE_LIMIT


def _record_send_attempt(username: str, ip: str | None) -> None:
    key = _send_rate_key(username, ip)
    _send_attempts.setdefault(key, []).append(time.time())

async def create_otp(
    db: AsyncSession,
    username: str,
    purpose: str,
    channel: str = "email",
    ttl_seconds: int = _OTP_TTL_SECONDS,
    ip: str | None = None,
) -> tuple[str, bool]:
    """Tạo OTP mới cho `username` + `purpose`.

    Trả về `(code, created)` — `code` là mã rõ ràng chỉ trả về cho caller
    (gửi qua email/SMS), KHÔNG được để trong response HTTP ngoài demo mode.

    Nếu đã có OTP chưa dùng cho cùng username+purpose → reset mã mới (không
    tạo duplicate row nhờ unique constraint).
    """
    now = datetime.now(UTC)

    # Kiểm tra rate-limit gửi.
    if _is_send_rate_limited(username, ip):
        return "", False

    # Tìm OTP đang hiệu lực chưa consumed.
    existing = (
        await db.execute(
            select(OtpCode).where(
                OtpCode.username == username.strip().lower(),
                OtpCode.purpose == purpose,
            )
        )
    ).scalar_one_or_none()

    if existing is not None and not existing.is_locked(now):
        # Reset mã mới trên row cũ (unique constraint tránh duplicate).
        code = f"{secrets.randbelow(1_000_000):06d}"
        existing.code_hash = _hash_code(code, existing.username)
        existing.expires_at = now + timedelta(seconds=ttl_seconds)
        existing.attempts = 0
        existing.locked_until = None
        existing.consumed_at = None  # reset consumed state
        existing.channel = channel
        existing.updated_at = now
        db.add(existing)
        await db.commit()
        _record_send_attempt(username, ip)
        return code, True

    # Nếu existing đã consumed hoặc locked, xóa row cũ để tạo mới.
    if existing is not None:
        await db.delete(existing)
        await db.flush()

    # Tạo OTP mới.
    code = f"{secrets.randbelow(1_000_000):06d}"
    otp = OtpCode(
        id=uuid.uuid4(),
        username=username.strip().lower(),
        code_hash=_hash_code(code, username),
        purpose=purpose,
        channel=channel,
        expires_at=now + timedelta(seconds=ttl_seconds),
        consumed_at=None,
        attempts=0,
        locked_until=None,
        created_at=now,
        updated_at=now,
    )
    db.add(otp)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        # Race condition: row đã tồn tại, thử lại
        existing = (
            await db.execute(
                select(OtpCode).where(
                    OtpCode.username == username.strip().lower(),
                    OtpCode.purpose == purpose,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            code = f"{secrets.randbelow(1_000_000):06d}"
            existing.code_hash = _hash_code(code, existing.username)
            existing.expires_at = now + timedelta(seconds=ttl_seconds)
            existing.attempts = 0
            existing.locked_until = None
            existing.consumed_at = None
            existing.channel = channel
            existing.updated_at = now
            db.add(existing)
            await db.commit()
            _record_send_attempt(username, ip)
            return code, True
        raise
    _record_send_attempt(username, ip)
    return code, True

async def verify_otp(
    db: AsyncSession,
    username: str,
    code: str,
    purpose: str,
    ip: str | None = None,
) -> tuple[bool, str | None]:
    """Verify OTP. Trả về `(ok, error_code)`.

    - Nếu OTP chưa tồn tại / hết hạn / đã consumed → (False, lỗi).
    - Nếu đang trong thời gian khóa → (False, "OTP_LOCKED").
    - Nếu sai quá `_MAX_ATTEMPTS` → khóa `_LOCK_MINUTES` và (False, "OTP_LOCKED").
    - Nếu đúng → đánh dấu `consumed_at`, (True, None).
    """
    now = datetime.now(UTC)
    username_l = username.strip().lower()

    otp = (
        await db.execute(
            select(OtpCode).where(
                OtpCode.username == username_l,
                OtpCode.purpose == purpose,
                OtpCode.consumed_at.is_(None),
            )
        )
    ).scalar_one_or_none()

    if otp is None:
        # Kiểm tra xem có OTP đã consumed không (để trả lỗi đúng)
        consumed_otp = (
            await db.execute(
                select(OtpCode).where(
                    OtpCode.username == username_l,
                    OtpCode.purpose == purpose,
                )
            )
        ).scalar_one_or_none()
        if consumed_otp is not None and consumed_otp.consumed_at is not None:
            return False, "OTP_CONSUMED"
        return False, "OTP_NOT_FOUND"

    if otp.is_locked(now):
        return False, "OTP_LOCKED"

    if otp.is_expired(now):
        return False, "OTP_EXPIRED"

    if not _verify_code(code, otp.code_hash, username_l):
        otp.attempts = (otp.attempts or 0) + 1
        if otp.attempts >= _MAX_ATTEMPTS:
            otp.locked_until = now + timedelta(minutes=_LOCK_MINUTES)
        otp.updated_at = now
        db.add(otp)
        await db.commit()
        return False, "OTP_INVALID"

    # Đúng → consume.
    otp.consumed_at = now
    otp.attempts = 0
    otp.locked_until = None
    otp.updated_at = now
    db.add(otp)
    await db.commit()
    return True, None


async def consume_otp(
    db: AsyncSession, username: str, purpose: str
) -> None:
    """Đánh dấu tất cả OTP chưa consumed của username+purpose là consumed."""
    now = datetime.now(UTC)
    result = await db.execute(
        select(OtpCode).where(
            OtpCode.username == username.strip().lower(),
            OtpCode.purpose == purpose,
            OtpCode.consumed_at.is_(None),
        )
    )
    for otp in result.scalars().all():
        otp.consumed_at = now
        otp.updated_at = now
        db.add(otp)
    await db.commit()

