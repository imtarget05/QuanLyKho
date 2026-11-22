"""API-level tests for the AI forecasting endpoints (reorder point / anomaly).

Uses a minimal FastAPI app with the capability dependency overridden, so the
tests exercise routing, validation, and response shaping without needing a
database or MLflow.
"""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.routes import ai_forecasting
from app.api.routes.auth_utils import get_current_user_with_capabilities
from app.models.iam import User


@pytest.fixture
async def client() -> AsyncClient:
    app = FastAPI()
    app.include_router(ai_forecasting.router)

    async def _override() -> tuple[User, list[str]]:
        return User(id=1, username="tester"), ["inventory:view_balances"]

    app.dependency_overrides[get_current_user_with_capabilities] = _override
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as c:
        c.app = app
        yield c


class TestReorderPointEndpoint:
    async def test_requires_authentication(self, client: AsyncClient):
        app = client.app
        app.dependency_overrides.clear()
        resp = await client.post(
            "/ai/reorder-point",
            json={"forecast_values": [10, 12, 11], "lead_time_days": 3},
        )
        assert resp.status_code in (401, 403, 422)

    async def test_returns_reorder_recommendation(self, client: AsyncClient):
        resp = await client.post(
            "/ai/reorder-point",
            json={
                "forecast_values": [40, 50, 60, 50, 45, 55, 50, 45, 55, 50],
                "lead_time_days": 7,
                "service_level": 0.95,
                "current_stock": 100,
            },
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["reorder_point"] > 0
        assert body["safety_stock"] > 0
        assert body["needs_order"] is True
        assert body["risk_level"] in {"critical", "warning", "healthy"}
        assert body["suggested_order_quantity"] > 0

    async def test_rejects_non_positive_lead_time(self, client: AsyncClient):
        resp = await client.post(
            "/ai/reorder-point",
            json={"forecast_values": [10, 12], "lead_time_days": 0},
        )
        assert resp.status_code == 422

    async def test_rejects_empty_forecast(self, client: AsyncClient):
        resp = await client.post(
            "/ai/reorder-point",
            json={"forecast_values": [], "lead_time_days": 3},
        )
        assert resp.status_code == 422

    async def test_rejects_invalid_service_level(self, client: AsyncClient):
        resp = await client.post(
            "/ai/reorder-point",
            json={
                "forecast_values": [10, 12],
                "lead_time_days": 3,
                "service_level": 1.5,
            },
        )
        assert resp.status_code == 422

    async def test_rejects_negative_current_stock(self, client: AsyncClient):
        resp = await client.post(
            "/ai/reorder-point",
            json={
                "forecast_values": [10, 12],
                "lead_time_days": 3,
                "current_stock": -5,
            },
        )
        assert resp.status_code == 422

    async def test_rejects_unknown_fields(self, client: AsyncClient):
        resp = await client.post(
            "/ai/reorder-point",
            json={
                "forecast_values": [10, 12],
                "lead_time_days": 3,
                "unexpected": True,
            },
        )
        assert resp.status_code == 422


class TestAnomalyEndpoint:
    async def test_detects_spike(self, client: AsyncClient):
        resp = await client.post(
            "/ai/anomaly",
            json={
                "actual_demand": 200,
                "expected_demand": 100,
                "std_demand": 10,
            },
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["is_anomaly"] is True
        assert body["direction"] == "spike"
        assert body["severity"] == "high"

    async def test_normal_demand_is_not_anomaly(self, client: AsyncClient):
        resp = await client.post(
            "/ai/anomaly",
            json={
                "actual_demand": 102,
                "expected_demand": 100,
                "std_demand": 10,
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["is_anomaly"] is False
        assert body["direction"] == "normal"

    async def test_zero_variance_returns_consistent_payload(self, client: AsyncClient):
        resp = await client.post(
            "/ai/anomaly",
            json={
                "actual_demand": 100,
                "expected_demand": 100,
                "std_demand": 0,
            },
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["is_anomaly"] is False
        assert body["direction"] == "unknown"
        assert body["expected_demand"] == 100
        assert body["actual_demand"] == 100
