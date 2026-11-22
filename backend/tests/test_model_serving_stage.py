"""Serving phải bám đúng stage Production (rollback có hiệu lực).

Regression cho bug: `ModelServer` chọn version cao nhất thay vì version đang ở
stage Production → rollback không thay đổi kết quả dự báo.
"""

from __future__ import annotations

import os

import mlflow
import pytest

from app.services import ml_registry
from app.services.ml_training import (
    generate_synthetic_inventory_demand,
    time_aware_split,
    train_demand_forecast_model,
)
from app.services.model_serving import DemandForecastRequest, ModelServer


@pytest.fixture
def tracking_store(tmp_path):
    previous_uri = mlflow.get_tracking_uri()
    previous_env = os.environ.get("MLFLOW_TRACKING_URI")
    previous_artifacts = os.environ.get("MLFLOW_ARTIFACT_ROOT")
    url = f"sqlite:///{tmp_path / 'mlflow.db'}"
    artifacts = str(tmp_path / "artifacts")

    os.environ["MLFLOW_TRACKING_URI"] = url
    os.environ["MLFLOW_ARTIFACT_ROOT"] = artifacts
    mlflow.set_tracking_uri(url)
    try:
        yield url
    finally:
        mlflow.set_tracking_uri(previous_uri)
        for name, value in (("MLFLOW_TRACKING_URI", previous_env), ("MLFLOW_ARTIFACT_ROOT", previous_artifacts)):
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def _train(seed: int) -> dict:
    df = generate_synthetic_inventory_demand(n_periods=60, seed=seed)
    train, test = time_aware_split(df, train_ratio=0.8)
    return train_demand_forecast_model(train, test, experiment_name="inventory-demand")


def test_serving_uses_production_stage_not_latest_version(tracking_store):
    first = _train(seed=1)
    second = _train(seed=2)
    assert first["run_id"] != second["run_id"]

    versions = {v["version"] for v in ml_registry.list_model_versions()}
    assert len(versions) >= 2

    promoted = ml_registry.promote_model(from_version=1, to_stage="Production")
    assert promoted["success"] is True

    server = ModelServer(tracking_uri=tracking_store)
    result = server.predict(DemandForecastRequest(periods=3))
    assert result.model_version == 1, "serving phải dùng version Production, không phải version cao nhất"
    assert result.model_stage == "Production"


def test_serving_falls_back_to_latest_when_no_production(tracking_store):
    _train(seed=3)
    _train(seed=4)

    server = ModelServer(tracking_uri=tracking_store)
    result = server.predict(DemandForecastRequest(periods=2))
    assert result.model_version >= 1
    assert result.forecast_periods == 2
