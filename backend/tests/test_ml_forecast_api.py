"""HTTP tests for C4 — POST /api/v1/ml/forecast (no DB required).

Uses httpx.ASGITransport (does not run lifespan) so the test does not require a
reachable PostgreSQL. The model server is faked: this suite verifies routing,
rate limiting and error mapping, not model quality.
"""

from __future__ import annotations

import time

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.routes import ml as ml_route
from app.main import app
from app.services.model_serving import DemandForecastResponse


class _FakeServer:
    def predict(self, request):
        return DemandForecastResponse(
            model_version=1,
            model_stage="Production",
            predictions=[1.0, 2.0, 3.0][: request.periods] or [1.0],
            forecast_periods=request.periods,
            generated_at="2026-01-01T00:00:00",
        )


@pytest.fixture(autouse=True)
def _reset_state(monkeypatch):
    ml_route._ML_WINDOWS.clear()
    yield
    ml_route._ML_WINDOWS.clear()


async def _client():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver")


async def test_forecast_returns_production_model(monkeypatch):
    monkeypatch.setattr(ml_route, "get_model_server", lambda: _FakeServer())
    async with await _client() as client:
        res = await client.post("/api/v1/ml/forecast", json={"periods": 3})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["model_stage"] == "Production"
    assert body["forecast_periods"] == 3
    assert len(body["predictions"]) == 3


async def test_forecast_returns_503_when_no_production_model(monkeypatch):
    def _raise():
        raise RuntimeError("no model")

    monkeypatch.setattr(ml_route, "get_model_server", _raise)
    async with await _client() as client:
        res = await client.post("/api/v1/ml/forecast", json={"periods": 1})
    assert res.status_code == 503
    assert res.json()["error"]["code"] == "MODEL_NOT_AVAILABLE"


async def test_forecast_rate_limited_with_retry_after(monkeypatch):
    monkeypatch.setattr(ml_route, "get_model_server", lambda: _FakeServer())
    monkeypatch.setattr(ml_route, "_ML_REQUESTS_PER_MINUTE", 2)
    async with await _client() as client:
        first = await client.post("/api/v1/ml/forecast", json={"periods": 1})
        second = await client.post("/api/v1/ml/forecast", json={"periods": 1})
        third = await client.post("/api/v1/ml/forecast", json={"periods": 1})
    assert first.status_code == 200
    assert second.status_code == 200
    assert third.status_code == 429
    assert "Retry-After" in third.headers
    assert int(third.headers["Retry-After"]) >= 1


async def test_forecast_validates_payload(monkeypatch):
    monkeypatch.setattr(ml_route, "get_model_server", lambda: _FakeServer())
    async with await _client() as client:
        res = await client.post("/api/v1/ml/forecast", json={"periods": 10_000})
    assert res.status_code == 422


async def test_rate_limit_window_expires(monkeypatch):
    monkeypatch.setattr(ml_route, "get_model_server", lambda: _FakeServer())
    monkeypatch.setattr(ml_route, "_ML_REQUESTS_PER_MINUTE", 1)
    ml_route._ML_WINDOWS["testclient"] = (time.monotonic() - 61, 5)
    async with await _client() as client:
        res = await client.post("/api/v1/ml/forecast", json={"periods": 1})
    assert res.status_code == 200
