"""Integration test for the model serving lifecycle (Phase M — S6).

The endpoint must serve a model that is really registered *and* promoted in
the MLflow registry, and it must fail with a clear, safe error (503
``MODEL_NOT_AVAILABLE``) instead of a 500 when no Production model exists.

No mocks: the model is trained, logged, registered and promoted through the
real MLflow stack; the tracking store is a throw-away SQLite database.
"""

from __future__ import annotations

import os

import mlflow
import pytest
from httpx import ASGITransport, AsyncClient

from app.api import inference
from app.api.inference import ModelNotAvailableError, app
from app.services import ml_registry


@pytest.fixture
def tracking_store(tmp_path):
    """Point MLflow at a throw-away tracking store and restore the old one."""
    previous_uri = mlflow.get_tracking_uri()
    previous_env = os.environ.get("MLFLOW_TRACKING_URI")
    url = f"sqlite:///{tmp_path / 'mlflow_tracking.db'}"

    os.environ["MLFLOW_TRACKING_URI"] = url
    mlflow.set_tracking_uri(url)
    mlflow.create_experiment(
        "inventory-demand", artifact_location=str(tmp_path / "artifacts")
    )
    inference.reset_model_cache()
    try:
        yield url
    finally:
        mlflow.set_tracking_uri(previous_uri)
        if previous_env is None:
            os.environ.pop("MLFLOW_TRACKING_URI", None)
        else:
            os.environ["MLFLOW_TRACKING_URI"] = previous_env
        inference.reset_model_cache()


async def test_predict_returns_503_when_no_production_model(tracking_store, monkeypatch):
    """Without a Production model the endpoint answers 503, not 500."""
    monkeypatch.setattr(inference, "AUTO_BOOTSTRAP", False)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        response = await client.post("/predict", json={"period": 10, "month": 6})

    assert response.status_code == 503, response.text
    detail = response.json()["detail"]
    assert detail["code"] == "MODEL_NOT_AVAILABLE"
    assert "Production" in detail["message"]


async def test_health_reports_degraded_when_no_production_model(tracking_store, monkeypatch):
    """Health check stays 200 but reports the missing model explicitly."""
    monkeypatch.setattr(inference, "AUTO_BOOTSTRAP", False)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        response = await client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "degraded"
    assert body["code"] == "MODEL_NOT_AVAILABLE"


async def test_get_model_raises_typed_error_without_production_model(tracking_store, monkeypatch):
    """The service layer raises a typed error, not a bare RuntimeError."""
    monkeypatch.setattr(inference, "AUTO_BOOTSTRAP", False)

    with pytest.raises(ModelNotAvailableError) as excinfo:
        inference.get_model()

    assert excinfo.value.code == "MODEL_NOT_AVAILABLE"


async def test_train_register_promote_then_predict(tracking_store):
    """Real lifecycle: train -> register -> promote -> predict."""
    from app.services.ml_training import run_full_pipeline

    run_full_pipeline()

    versions = ml_registry.list_model_versions("DemandForecastModel")
    assert versions, "training must register a model version"

    result = ml_registry.promote_model(
        "DemandForecastModel", from_version=int(versions[0]["version"]), to_stage="Production"
    )
    assert result["success"] is True

    inference.reset_model_cache()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        response = await client.post("/predict", json={"period": 10, "month": 6})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["model_version"] == str(versions[0]["version"])
    assert body["predicted_demand"] > 0
    assert body["confidence_lower"] <= body["predicted_demand"] <= body["confidence_upper"]

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        health = await client.get("/health")

    assert health.status_code == 200
    assert health.json()["status"] == "healthy"
