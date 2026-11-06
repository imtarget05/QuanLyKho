"""Readiness must reflect dependencies required for a usable login flow."""

import json
from contextlib import asynccontextmanager

import pytest

from app import database
from app.api.routes import health


class _ReadyEngine:
    @asynccontextmanager
    async def connect(self):
        class _Connection:
            async def execute(self, _statement):
                return None

        yield _Connection()


class _FailedEngine:
    @asynccontextmanager
    async def connect(self):
        raise RuntimeError("postgresql://user:pass@secret-host/database")
        yield  # pragma: no cover


@pytest.mark.asyncio
async def test_ready_fails_when_login_rate_limit_is_unavailable(monkeypatch):
    monkeypatch.setattr(database, "engine", _ReadyEngine())

    def redis_down():
        raise RuntimeError("redis://secret-host:6379")

    monkeypatch.setattr(health, "assert_redis_ready", redis_down, raising=False)
    response = await health.readiness_check()
    assert response.status_code == 503
    body = json.loads(response.body)
    assert body["services"] == {"database": "ready", "login_rate_limit": "not_ready"}
    assert "secret-host" not in response.body.decode()


@pytest.mark.asyncio
async def test_ready_hides_database_exception_details(monkeypatch):
    monkeypatch.setattr(database, "engine", _FailedEngine())
    monkeypatch.setattr(health, "assert_redis_ready", lambda: None, raising=False)
    response = await health.readiness_check()
    assert response.status_code == 503
    body = json.loads(response.body)
    assert body["services"]["database"] == "not_ready"
    assert "secret-host" not in response.body.decode()


@pytest.mark.asyncio
async def test_ready_when_database_and_login_rate_limit_are_available(monkeypatch):
    monkeypatch.setattr(database, "engine", _ReadyEngine())
    monkeypatch.setattr(health, "assert_redis_ready", lambda: None, raising=False)
    body = await health.readiness_check()
    assert body["status"] == "ready"
    assert body["services"] == {"database": "ready", "login_rate_limit": "ready"}


def test_version_exposes_render_release_sha(monkeypatch):
    release_sha = "a" * 40
    monkeypatch.setenv("RENDER_GIT_COMMIT", release_sha)
    assert health.version_check() == {"release_sha": release_sha}


def test_version_reports_unknown_without_release_metadata(monkeypatch):
    monkeypatch.delenv("RENDER_GIT_COMMIT", raising=False)
    assert health.version_check() == {"release_sha": "unknown"}


def test_version_never_exposes_malformed_release_metadata(monkeypatch):
    monkeypatch.setenv("RENDER_GIT_COMMIT", "not-a-sha")
    assert health.version_check() == {"release_sha": "unknown"}
