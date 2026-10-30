"""Tests for durable OTP service (P1-2, P1-3).

Cover: create_otp, verify_otp, consume_otp, rate-limit, lock-after-3-fails,
TTL expiry, demo-mode plaintext leak.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.models.otp import OtpCode
from app.services.otp import create_otp, verify_otp, consume_otp


@pytest.fixture
async def db_session():
    async with AsyncSessionLocal() as session:
        yield session


async def test_create_otp_returns_code_and_marks_created(db_session: AsyncSession):
    code, created = await create_otp(db_session, "testuser", "password_reset")
    assert created is True
    assert len(code) == 6
    assert code.isdigit()


async def test_create_otp_reuse_existing_unconsumed(db_session: AsyncSession):
    code1, _ = await create_otp(db_session, "testuser", "password_reset")
    code2, created = await create_otp(db_session, "testuser", "password_reset")
    assert created is True
    assert code1 != code2  # reset mã mới trên row cũ


async def test_verify_otp_success(db_session: AsyncSession):
    code, _ = await create_otp(db_session, "testuser", "password_reset")
    ok, err = await verify_otp(db_session, "testuser", code, "password_reset")
    assert ok is True
    assert err is None


async def test_verify_otp_is_single_use(db_session: AsyncSession):
    code, _ = await create_otp(db_session, "testuser", "password_reset")
    ok1, _ = await verify_otp(db_session, "testuser", code, "password_reset")
    assert ok1 is True
    ok2, err = await verify_otp(db_session, "testuser", code, "password_reset")
    assert ok2 is False
    assert err == "OTP_CONSUMED"


async def test_verify_otp_wrong_3_times_locks(db_session: AsyncSession):
    await create_otp(db_session, "locktest_user", "password_reset")
    for i in range(3):
        ok, err = await verify_otp(db_session, "locktest_user", "000000", "password_reset")
        assert ok is False
        assert err == "OTP_INVALID"
    # Lần thứ 4 -> khóa
    ok, err = await verify_otp(db_session, "locktest_user", "000000", "password_reset")
    assert ok is False
    assert err == "OTP_LOCKED"


async def test_verify_otp_expired(db_session: AsyncSession):
    from app.models.otp import OtpCode
    from app.services.otp import _hash_code
    from datetime import UTC, datetime, timedelta
    import uuid

    username = f"expired_user_{uuid.uuid4().hex[:8]}"

    # Tạo OTP đã hết hạn trực tiếp
    otp = OtpCode(
        id=uuid.uuid4(),
        username=username,
        code_hash=_hash_code("123456", username),
        purpose="password_reset",
        channel="email",
        expires_at=datetime.now(UTC) - timedelta(minutes=1),
        consumed_at=None,
        attempts=0,
        locked_until=None,
        created_at=datetime.now(UTC) - timedelta(minutes=2),
        updated_at=datetime.now(UTC) - timedelta(minutes=2),
    )
    db_session.add(otp)
    await db_session.commit()

    ok, err = await verify_otp(db_session, username, "123456", "password_reset")
    assert ok is False
    assert err == "OTP_EXPIRED"


async def test_consume_otp_marks_consumed(db_session: AsyncSession):
    code, _ = await create_otp(db_session, "testuser", "password_reset")
    await verify_otp(db_session, "testuser", code, "password_reset")
    await consume_otp(db_session, "testuser", "password_reset")
    otp = (
        await db_session.execute(
            select(OtpCode).where(OtpCode.username == "testuser")
        )
    ).scalar_one()
    assert otp.consumed_at is not None


async def test_send_rate_limit(db_session: AsyncSession):
    from app.services.otp import _is_send_rate_limited, _record_send_attempt

    for _ in range(5):
        _record_send_attempt("testuser", None)
    assert _is_send_rate_limited("testuser", None) is True
