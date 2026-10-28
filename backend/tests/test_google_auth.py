"""Tests for Google Authentication (ID token & Access token flow)."""
import json
import uuid
from unittest.mock import MagicMock, patch

import pytest


def test_google_login_validation_errors(client):
    """Missing or short tokens must return 422 with validation envelope."""
    # 1. Missing both tokens
    r = client.post("/api/v1/auth/google", json={})
    assert r.status_code == 422
    data = r.json()
    assert data["error"]["code"] == "VALIDATION_ERROR"
    assert data["error"]["message"] == "Dữ liệu gửi lên chưa hợp lệ. Vui lòng kiểm tra lại các trường bắt buộc."
    # details chỉ giữ loc/msg/type, không lộ input (password/token)
    for e in data["error"]["details"]["errors"]:
        assert "input" not in e

    # 2. Short id_token
    r = client.post("/api/v1/auth/google", json={"id_token": "short"})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "VALIDATION_ERROR"

    # 3. Short access_token
    r = client.post("/api/v1/auth/google", json={"access_token": "short"})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "VALIDATION_ERROR"


def test_google_login_mock_id_token(client, demo_mode):
    """Mock id_token flow provisions staff user and returns JWT."""
    username = f"mock_u_{uuid.uuid4().hex[:6]}@bankops.internal"
    mock_token = f"mock-google-token:{username}:Mock Test User"
    r = client.post("/api/v1/auth/google", json={"id_token": mock_token})
    assert r.status_code == 200, r.text
    body = r.json()
    assert "access_token" in body
    assert "refresh_token" in body
    assert body["user"]["username"] == username
    assert "staff" in body["user"]["roles"]
    assert body["is_new_user"] is True

    # Subsequent login is not a new user
    r2 = client.post("/api/v1/auth/google", json={"id_token": mock_token})
    assert r2.status_code == 200
    assert r2.json()["is_new_user"] is False


def test_google_login_mock_access_token(client, demo_mode):
    """Mock access_token flow provisions staff user and returns JWT."""
    username = f"mock_acc_{uuid.uuid4().hex[:6]}@bankops.internal"
    mock_token = f"mock-google-token:{username}:Mock Access User"
    r = client.post("/api/v1/auth/google", json={"access_token": mock_token})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["user"]["username"] == username
    assert "staff" in body["user"]["roles"]


def test_google_login_access_token_mocked_google_api(client):
    """Test real access token flow with mocked Google tokeninfo & userinfo."""
    email = "test_verified_user@gmail.com"
    tokeninfo_resp = json.dumps({
        "azp": "1070073470852-hc12cgovbt9h7micnu072vpkvigee28u.apps.googleusercontent.com",
        "aud": "1070073470852-hc12cgovbt9h7micnu072vpkvigee28u.apps.googleusercontent.com",
        "sub": "12345678901234567890",
        "email": email,
        "email_verified": "true",
    }).encode()

    userinfo_resp = json.dumps({
        "sub": "12345678901234567890",
        "name": "Verified Google User",
        "email": email,
        "email_verified": True,
    }).encode()

    def fake_urlopen(req, timeout=10):
        url = req.full_url if hasattr(req, "full_url") else str(req)
        mock_cm = MagicMock()
        if "tokeninfo" in url:
            mock_cm.__enter__.return_value.read.return_value = tokeninfo_resp
        else:
            mock_cm.__enter__.return_value.read.return_value = userinfo_resp
        return mock_cm

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        r = client.post("/api/v1/auth/google", json={"access_token": "ya29.a0AWY7C1234567890"})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["user"]["username"] == email
        assert "access_token" in body


def test_google_login_disambiguates_email_and_username(client, demo_mode):
    """When a user has matching email and another has matching username, no MultipleResultsFound."""
    shared_email = "tanmainguyenbinh@gmail.com"
    mock_token = f"mock-google-token:{shared_email}:Tan Mai"
    r = client.post("/api/v1/auth/google", json={"id_token": mock_token})
    assert r.status_code == 200, r.text
    body = r.json()
    # Should resolve to admin user whose email is tanmainguyenbinh@gmail.com
    assert body["user"]["username"] in ("admin", "tanmainguyenbinh", shared_email)
    assert "access_token" in body


# ---------------------------------------------------------------------------
# Demo mode phải là opt-in tường minh: token `mock-` chỉ hợp lệ khi demo bật
# ---------------------------------------------------------------------------


@pytest.fixture
def non_demo_mode(monkeypatch):
    """Tắt demo mode — môi trường thật."""
    from app.config import settings

    monkeypatch.setattr(settings, "demo_mode", False)
    assert settings.is_demo_mode is False
    return settings


def test_google_mock_token_rejected_outside_demo_mode(client, non_demo_mode):
    """Ngoài demo mode, token `mock-` phải bị từ chối (401).

    Trước đây bất kỳ chuỗi `mock-...` nào cũng tạo user + cấp role; nếu email
    trùng `settings.admin_emails` thì nhận full admin.
    """
    username = f"mock_reject_{uuid.uuid4().hex[:6]}@bankops.internal"
    mock_token = f"mock-google-token:{username}:Should Not Exist"
    r = client.post("/api/v1/auth/google", json={"id_token": mock_token})
    assert r.status_code == 401, r.text
    assert r.json()["error"]["code"] == "GOOGLE_TOKEN_INVALID"

    # Không tạo user nào từ token giả
    r2 = client.post("/api/v1/auth/google", json={"access_token": mock_token})
    assert r2.status_code == 401, r2.text
    assert r2.json()["error"]["code"] == "GOOGLE_TOKEN_INVALID"


def test_google_mock_token_accepted_in_demo_mode(client, demo_mode):
    """Demo mode bật -> token `mock-` vẫn tạo user staff như luồng QA cũ."""
    username = f"mock_ok_{uuid.uuid4().hex[:6]}@bankops.internal"
    mock_token = f"mock-google-token:{username}:Demo Mock User"
    r = client.post("/api/v1/auth/google", json={"id_token": mock_token})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["user"]["username"] == username
    assert "staff" in body["user"]["roles"]
