"""Test change password and change PIN endpoints."""
import asyncio
import re

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.config import Settings
from app.services.approval_controls import verify_supervisor_pin

DEMO_PASSWORD = "DemoPass123!"


@pytest.fixture
def non_demo_mode(monkeypatch):
    """Tắt demo mode — môi trường thật: không được có bất kỳ đường tắt demo nào."""
    from app.config import settings

    monkeypatch.setattr(settings, "demo_mode", False)
    assert settings.is_demo_mode is False
    return settings


def test_change_password_flow(client):
    # 1. Login with demo_maker
    login_resp = client.post(
        "/api/v1/auth/login",
        data={"username": "demo_maker", "password": DEMO_PASSWORD},
    )
    assert login_resp.status_code == 200, login_resp.text
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 2. Try changing password with wrong old password -> 400
    bad_resp = client.post(
        "/api/v1/auth/change-password",
        headers=headers,
        json={"old_password": "WrongPassword123!", "new_password": "NewSecretPassword123!"},
    )
    assert bad_resp.status_code == 400
    assert "Mật khẩu hiện tại không đúng" in bad_resp.json()["error"]["message"]

    # 3. Change password successfully
    new_pass = "BrandNewPass2026!"
    ok_resp = client.post(
        "/api/v1/auth/change-password",
        headers=headers,
        json={"old_password": DEMO_PASSWORD, "new_password": new_pass},
    )
    assert ok_resp.status_code == 200
    assert "Đổi mật khẩu thành công" in ok_resp.json()["message"]

    # 4. Verify login with old password fails
    old_login = client.post(
        "/api/v1/auth/login",
        data={"username": "demo_maker", "password": DEMO_PASSWORD},
    )
    assert old_login.status_code == 401

    # 5. Verify login with new password succeeds
    new_login = client.post(
        "/api/v1/auth/login",
        data={"username": "demo_maker", "password": new_pass},
    )
    assert new_login.status_code == 200
    assert new_login.json()["access_token"]

    # Revert password back to DEMO_PASSWORD so other test suites stay idempotent
    rev_token = new_login.json()["access_token"]
    revert_resp = client.post(
        "/api/v1/auth/change-password",
        headers={"Authorization": f"Bearer {rev_token}"},
        json={"old_password": new_pass, "new_password": DEMO_PASSWORD},
    )
    assert revert_resp.status_code == 200


def test_change_pin_flow(client):
    # 1. Login with demo_checker
    login_resp = client.post(
        "/api/v1/auth/login",
        data={"username": "demo_checker", "password": DEMO_PASSWORD},
    )
    assert login_resp.status_code == 200, login_resp.text
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 2. Try with wrong account password -> 400
    wrong_resp = client.post(
        "/api/v1/auth/change-pin",
        headers=headers,
        json={"current_password": "WrongPassword999!", "new_pin": "654321"},
    )
    assert wrong_resp.status_code == 400
    assert "Mật khẩu tài khoản không đúng" in wrong_resp.json()["error"]["message"]

    # 3. Try with invalid pin format (not 6 digits) -> 422
    invalid_resp = client.post(
        "/api/v1/auth/change-pin",
        headers=headers,
        json={"current_password": DEMO_PASSWORD, "new_pin": "1234"},
    )
    assert invalid_resp.status_code == 422

    # 4. Change pin successfully to '777888'
    ok_resp = client.post(
        "/api/v1/auth/change-pin",
        headers=headers,
        json={"current_password": DEMO_PASSWORD, "new_pin": "777888"},
    )
    assert ok_resp.status_code == 200
    assert "Đổi mã PIN kiểm soát viên thành công" in ok_resp.json()["message"]

    # 5. Verify unit logic with updated user pin
    class MockUserWithPin:
        from app.api.routes.auth_utils import get_password_hash
        pin_hash = get_password_hash("777888")

    settings = Settings(database_url="sqlite://", app_env="demo")
    user = MockUserWithPin()

    # Old demo PIN '123456' must now be rejected
    with pytest.raises(HTTPException) as exc:
        verify_supervisor_pin("123456", settings, user=user)
    assert exc.value.status_code == 403

    # New PIN '777888' must be accepted
    verify_supervisor_pin("777888", settings, user=user)

    # Revert pin back to '123456'
    rev_resp = client.post(
        "/api/v1/auth/change-pin",
        headers=headers,
        json={"current_password": DEMO_PASSWORD, "new_pin": "123456"},
    )
    assert rev_resp.status_code == 200


def test_forgot_password_and_reset_flow(client, demo_mode):
    # 1. Request reset for non-existent user -> 404
    bad_req = client.post(
        "/api/v1/auth/forgot-password",
        json={"username": "non_existent_user_999"},
    )
    assert bad_req.status_code == 404
    assert "Không tìm thấy tài khoản" in bad_req.json()["error"]["message"]

    # 2. Request OTP for demo_maker -> 200 (demo mode: OTP được trả lại cho QA)
    forgot_resp = client.post(
        "/api/v1/auth/forgot-password",
        json={"username": "demo_maker"},
    )
    assert forgot_resp.status_code == 200
    data = forgot_resp.json()
    assert data["username"] == "demo_maker"
    otp = data["otp_demo"]
    assert len(otp) == 6

    # 3. Reset with wrong OTP -> 400
    wrong_otp_resp = client.post(
        "/api/v1/auth/reset-password",
        json={"username": "demo_maker", "otp": "000000", "new_password": "NewResetPassword2026!"},
    )
    assert wrong_otp_resp.status_code == 400
    assert "Mã xác thực OTP không chính xác" in wrong_otp_resp.json()["error"]["message"]

    # 4. Reset with valid OTP -> 200
    new_password = "NewResetPassword2026!"
    ok_reset = client.post(
        "/api/v1/auth/reset-password",
        json={"username": "demo_maker", "otp": otp, "new_password": new_password},
    )
    assert ok_reset.status_code == 200
    assert "Khôi phục mật khẩu thành công" in ok_reset.json()["message"]

    # 5. Verify old password no longer works
    old_login = client.post(
        "/api/v1/auth/login",
        data={"username": "demo_maker", "password": DEMO_PASSWORD},
    )
    assert old_login.status_code == 401

    # 6. Verify new password works
    new_login = client.post(
        "/api/v1/auth/login",
        data={"username": "demo_maker", "password": new_password},
    )
    assert new_login.status_code == 200
    assert new_login.json()["access_token"]

    # Revert password back to DEMO_PASSWORD
    rev_token = new_login.json()["access_token"]
    revert_resp = client.post(
        "/api/v1/auth/change-password",
        headers={"Authorization": f"Bearer {rev_token}"},
        json={"old_password": new_password, "new_password": DEMO_PASSWORD},
    )
    assert revert_resp.status_code == 200


def test_update_profile_flow(client):
    # 1. Login with demo_maker
    login_resp = client.post(
        "/api/v1/auth/login",
        data={"username": "demo_maker", "password": DEMO_PASSWORD},
    )
    assert login_resp.status_code == 200
    token = login_resp.json()["access_token"]
    orig_display_name = login_resp.json()["user"]["display_name"]
    headers = {"Authorization": f"Bearer {token}"}

    # 2. Validation error: empty display_name
    bad_resp = client.put(
        "/api/v1/auth/me",
        headers=headers,
        json={"display_name": "   "},
    )
    assert bad_resp.status_code == 422

    # 3. Update profile successfully via /api/v1/auth/me
    updated_name = "Nguyễn Hoàng An (Trưởng GDV)"
    ok_resp = client.put(
        "/api/v1/auth/me",
        headers=headers,
        json={
            "display_name": updated_name,
            "email": "hoangan@bankops.vn",
            "phone_number": "0912 345 678",
            "branch": "Chi nhánh Bến Thành (Hội sở)",
        },
    )
    assert ok_resp.status_code == 200
    data = ok_resp.json()
    assert data["display_name"] == updated_name
    assert data["email"] == "hoangan@bankops.vn"
    assert data["phone_number"] == "0912 345 678"

    # 4. Verify GET /api/v1/auth/me returns updated display_name
    me_resp = client.get("/api/v1/auth/me", headers=headers)
    assert me_resp.status_code == 200
    assert me_resp.json()["display_name"] == updated_name

    # 5. Verify alias PUT /api/v1/me works
    alias_resp = client.put(
        "/api/v1/me",
        headers=headers,
        json={"display_name": "Nguyễn Hoàng An (Maker Lead)"},
    )
    assert alias_resp.status_code == 200
    assert alias_resp.json()["display_name"] == "Nguyễn Hoàng An (Maker Lead)"

    # 6. Revert back to original display name
    revert_resp = client.put(
        "/api/v1/auth/me",
        headers=headers,
        json={"display_name": orig_display_name},
    )
    assert revert_resp.status_code == 200
    assert revert_resp.json()["display_name"] == orig_display_name



# ---------------------------------------------------------------------------
# Auth hardening (FIX WAVE 1 — S1/S3): demo mode phải là opt-in tường minh
# ---------------------------------------------------------------------------


def test_forgot_password_returns_no_otp_outside_demo_mode(client, non_demo_mode):
    """Ngoài demo mode, response KHÔNG được chứa OTP.

    Nếu OTP nằm trong response, bất kỳ ai cũng đọc được OTP của tài khoản
    khác rồi gọi /auth/reset-password để chiếm tài khoản.
    """
    resp = client.post(
        "/api/v1/auth/forgot-password",
        json={"username": "demo_maker"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "otp_demo" not in data
    # Không có mã 6 số nào lọt ra trong payload (message, expires_in_seconds, ...)
    assert not re.search(r"\b\d{6}\b", repr(data)), data


def test_forgot_password_returns_otp_only_in_demo_mode(client, demo_mode):
    """Demo mode bật tường minh -> vẫn trả otp_demo cho luồng QA."""
    resp = client.post(
        "/api/v1/auth/forgot-password",
        json={"username": "demo_maker"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "otp_demo" in data
    assert re.fullmatch(r"\d{6}", data["otp_demo"])


@pytest.mark.parametrize("demo_enabled", [True, False])
def test_demo_checker_has_no_synthetic_admin_roles(demo_enabled, monkeypatch):
    """Backdoor theo username đã bị gỡ.

    `demo_checker` không được tự sinh role `admin`/`approver` hay capability
    `iam:admin`/`admin:user_management` — bất kể demo mode bật hay tắt.
    Vai trò phải đến từ `iam_user_roles` trong DB.
    """
    from app.api.routes.auth_utils import get_user_capabilities, get_user_roles
    from app.config import settings
    from app.database import AsyncSessionLocal
    from app.models.iam import User, UserRole

    monkeypatch.setattr(settings, "demo_mode", demo_enabled)

    async def _run():
        async with AsyncSessionLocal() as db:
            user_id = (
                await db.execute(select(User.id).where(User.username == "demo_checker"))
            ).scalar_one_or_none()
            if user_id is None:
                pytest.skip("demo_checker chưa được seed trong DB test")
            rows = list(
                (
                    await db.execute(select(UserRole).where(UserRole.user_id == user_id))
                ).scalars().all()
            )
            for row in rows:
                await db.delete(row)
            await db.flush()  # autoflush tắt -> phải flush tường minh
            try:
                roles = await get_user_roles(db, user_id)
                caps = await get_user_capabilities(db, user_id)
            finally:
                # rollback: DB test không bị thay đổi (dùng chung với CI)
                await db.rollback()
            return roles, caps

    roles, caps = asyncio.run(_run())
    assert "admin" not in roles
    assert "approver" not in roles
    assert "iam:admin" not in caps
    assert "admin:user_management" not in caps


def test_authenticate_user_has_no_password_bypass():
    """Không bypass mật khẩu: hash trong DB là nguồn sự thật duy nhất.

    Trước đây `demo_checker` được nhận mọi mật khẩu (`DemoPass123!`) kể cả
    khi hash trong DB không khớp.
    """
    from app.api.routes.auth_utils import authenticate_user, get_password_hash
    from app.database import AsyncSessionLocal
    from app.models.iam import User

    other_password = "KhacMatKhau456!"

    async def _run():
        async with AsyncSessionLocal() as db:
            user = (
                await db.execute(select(User).where(User.username == "demo_checker"))
            ).scalar_one_or_none()
            if user is None:
                pytest.skip("demo_checker chưa được seed trong DB test")
            user.password_hash = get_password_hash(other_password)
            await db.flush()
            try:
                bypass = await authenticate_user(db, "demo_checker", DEMO_PASSWORD)
                legit = await authenticate_user(db, "demo_checker", other_password)
            finally:
                await db.rollback()  # giữ nguyên DB test
            return bypass, legit

    bypass, legit = asyncio.run(_run())
    assert bypass is None, "authenticate_user vẫn bypass mật khẩu theo username"
    assert legit is not None


def test_non_demo_env_without_signing_key_fails_fast(monkeypatch):
    """Môi trường non-demo thiếu BANKOPS_SIGNING_KEY -> fail fast lúc khởi động."""
    from app.config import Settings

    monkeypatch.delenv("BANKOPS_SIGNING_KEY", raising=False)
    monkeypatch.delenv("BANKOPS_signing", raising=False)
    settings = Settings(app_env="production")
    with pytest.raises(RuntimeError, match="JWT signing key must be set"):
        settings.assert_runtime_secrets()


def test_non_demo_env_with_signing_key_passes(monkeypatch):
    from app.config import Settings

    monkeypatch.setenv("BANKOPS_SIGNING_KEY", "test-signing-key-value")
    settings = Settings(app_env="production")
    settings.assert_runtime_secrets()  # không raise
    assert settings.signing_key == "test-signing-key-value"


def test_demo_mode_requires_explicit_opt_in(monkeypatch):
    """Demo mode mặc định TẮT; bật cần APP_ENV=demo + DEMO_MODE=true."""
    import app.config
    from app.config import Settings

    # Không có DEMO_MODE ở env lẫn ở file .env -> demo mode TẮT (an toàn).
    monkeypatch.delenv("DEMO_MODE", raising=False)
    monkeypatch.setitem(app.config._env_vals, "DEMO_MODE", None)
    default_settings = Settings(app_env="demo")
    assert default_settings.demo_mode is False
    assert default_settings.is_demo_mode is False

    # Bật tường minh bằng init kwargs.
    enabled = Settings(app_env="demo", demo_mode=True)
    assert enabled.is_demo_mode is True

    # DEMO_MODE=true nhưng APP_ENV=production -> vẫn tắt (an toàn).
    assert Settings(app_env="production", demo_mode=True).is_demo_mode is False

    # Tắt tường minh -> mọi đường tắt demo đều khoá.
    assert Settings(app_env="demo", demo_mode=False).is_demo_mode is False


def test_demo_mode_can_be_enabled_by_env(monkeypatch):
    """DEMO_MODE=true trong env là cách bật tường minh ở môi trường demo."""
    from app.config import Settings

    monkeypatch.setenv("DEMO_MODE", "true")
    settings = Settings(app_env="demo")
    assert settings.demo_mode is True
    assert settings.is_demo_mode is True

    monkeypatch.setenv("DEMO_MODE", "false")
    settings = Settings(app_env="demo")
    assert settings.demo_mode is False
    assert settings.is_demo_mode is False
