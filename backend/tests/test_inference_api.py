# Model Serving API Tests (Phase M — S6)
# Test-first: RED → GREEN → REFACTOR
import os
import sys

sys.path.insert(0, os.path.dirname(__file__) + "/../..")

from httpx import ASGITransport, AsyncClient

from app.api.inference import app


class TestHealthCheck:
    async def test_health_endpoint(self):
        """Health check should return status."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
            response = await client.get("/health")
            assert response.status_code == 200
            data = response.json()
            assert "status" in data


class TestPredictEndpoint:
    async def test_predict_with_valid_input(self):
        """Predict endpoint should accept valid input and return response."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
            response = await client.post(
                "/predict",
                json={"period": 10, "month": 6}
            )
            assert response.status_code == 200
            data = response.json()
            assert "predicted_demand" in data
            assert "model_version" in data
            assert "confidence_lower" in data
            assert "confidence_upper" in data

    async def test_predict_with_invalid_month(self):
        """Predict should reject invalid month."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
            response = await client.post(
                "/predict",
                json={"period": 10, "month": 13}
            )
            assert response.status_code == 422  # Validation error

    async def test_predict_with_negative_period(self):
        """Predict should reject negative period."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
            response = await client.post(
                "/predict",
                json={"period": -1, "month": 6}
            )
            assert response.status_code == 422  # Validation error
