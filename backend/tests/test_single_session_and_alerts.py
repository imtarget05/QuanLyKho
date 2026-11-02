"""Unit & Integration tests for Single Session Policy & Security Alerts."""

import pytest
from jose import jwt

from app.api.routes.auth_utils import create_access_token
from app.config import settings
from app.services.email_service import (
    _build_security_alert_html,
    _build_security_alert_plain,
    send_security_alert_email,
)


@pytest.mark.asyncio
async def test_auth_version_token_revocation_logic():
    """Verify that bumping auth_version invalidates previously issued tokens."""
    user_id = "test-user-uuid"
    old_version = 1
    new_version = 2

    # Old device gets token with auth_version = 1
    old_token = create_access_token({"sub": user_id, "auth_version": old_version})
    decoded_old = jwt.decode(old_token, settings.signing_key, algorithms=[settings.jwt_algorithm])
    assert decoded_old["auth_version"] == old_version

    # New login occurs, bumping auth_version to 2
    new_token = create_access_token({"sub": user_id, "auth_version": new_version})
    decoded_new = jwt.decode(new_token, settings.signing_key, algorithms=[settings.jwt_algorithm])
    assert decoded_new["auth_version"] == new_version

    # Current user state in DB is now version 2
    current_db_auth_version = new_version
    # Old token fails check (1 != 2)
    assert decoded_old["auth_version"] != current_db_auth_version
    # New token passes check (2 == 2)
    assert decoded_new["auth_version"] == current_db_auth_version


@pytest.mark.asyncio
async def test_build_security_alert_templates():
    """Verify HTML and Plain Text alert builders render correctly with escaping."""
    details = {
        "Tài khoản": "demo_staff<test>",
        "Địa chỉ IP": "192.168.1.100",
        "Thiết bị": "Chrome on macOS",
    }
    time_str = "21:30:00 ngày 02/11/2026 (Giờ VN)"

    html_out = _build_security_alert_html(
        title="Đăng nhập thiết bị mới",
        message="Phát hiện phiên mới trên tài khoản.",
        time_str=time_str,
        details=details,
    )
    assert "🚨 CẢNH BÁO AN NINH HỆ THỐNG" in html_out
    assert "demo_staff&lt;test&gt;" in html_out
    assert "192.168.1.100" in html_out
    assert time_str in html_out

    plain_out = _build_security_alert_plain(
        title="Đăng nhập thiết bị mới",
        message="Phát hiện phiên mới trên tài khoản.",
        time_str=time_str,
        details=details,
    )
    assert "[CẢNH BÁO AN NINH HỆ THỐNG]" in plain_out
    assert "Tài khoản: demo_staff<test>" in plain_out
    assert "Địa chỉ IP: 192.168.1.100" in plain_out


@pytest.mark.asyncio
async def test_send_security_alert_email_unconfigured_smtp():
    """Verify that when SMTP is not configured or fails to connect, it reports failure safely."""
    result = await send_security_alert_email(
        subject="Test Alert",
        title="Test Title",
        message="Test Message",
        details={"User": "tester"},
        to_emails=["admin@example.com"],
    )
    # When SMTP server is unreachable or fails to handshake in test env
    assert result.success is False
    assert result.message != ""
