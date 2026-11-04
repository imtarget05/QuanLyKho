from unittest.mock import Mock

import pytest
from fastapi import HTTPException

from app.api.routes import auth_utils
from app.config import settings


@pytest.fixture(autouse=True)
def reset_redis_state(monkeypatch):
    monkeypatch.setattr(auth_utils, "_redis_client", None)
    monkeypatch.setattr(auth_utils, "_redis_resolved", False)
    auth_utils._login_failures.clear()


def test_production_requires_tls_redis_url(monkeypatch):
    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "redis_url", "")
    monkeypatch.setenv("REDIS_URL", "")

    with pytest.raises(HTTPException) as exc_info:
        auth_utils._get_redis_client()

    assert exc_info.value.status_code == 503


def test_production_redis_operation_failure_does_not_fall_back_to_memory(
    monkeypatch,
):
    monkeypatch.setattr(settings, "app_env", "production")
    client = Mock()
    client.get.side_effect = OSError("Redis unavailable")
    monkeypatch.setattr(auth_utils, "_redis_client", client)
    monkeypatch.setattr(auth_utils, "_redis_resolved", True)

    with pytest.raises(HTTPException) as exc_info:
        auth_utils.login_rate_limited("alice", "192.0.2.1")

    assert exc_info.value.status_code == 503
    assert "alice|192.0.2.1" not in auth_utils._login_failures


def test_test_environment_keeps_in_memory_rate_limit_fallback(monkeypatch):
    monkeypatch.setattr(settings, "app_env", "test")
    monkeypatch.setattr(settings, "redis_url", "")
    monkeypatch.setenv("REDIS_URL", "")
    monkeypatch.setattr(settings, "rate_limit_login_attempts", 2)

    assert not auth_utils.login_rate_limited("alice", "192.0.2.1")
    auth_utils.record_login_failure("alice", "192.0.2.1")
    assert not auth_utils.login_rate_limited("alice", "192.0.2.1")
    auth_utils.record_login_failure("alice", "192.0.2.1")
    assert auth_utils.login_rate_limited("alice", "192.0.2.1")
