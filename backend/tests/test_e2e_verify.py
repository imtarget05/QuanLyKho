"""Contracts for the S11 chain gate (fail-closed, cùng một tracking store)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import mlflow

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "e2e_verify.py"


def _load_script():
    spec = importlib.util.spec_from_file_location("e2e_verify", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_registry_verification_fails_closed_without_a_registered_model(tmp_path):
    script = _load_script()

    result = script.verify_registry(
        tracking_uri=f"sqlite:///{tmp_path / 'tracking.db'}",
        model_name="MissingDemandForecastModel",
    )

    assert result["status"] == "failed"
    assert result["reason"] == "no_model_versions"


def test_chain_gate_passes_and_rollback_inference_matches(tmp_path, monkeypatch):
    """Seed 2 versions → chain promote/predict/drift/rollback trên cùng store."""
    import numpy as np
    from sklearn.linear_model import LinearRegression

    script = _load_script()
    tracking_uri = f"sqlite:///{tmp_path / 'chain.db'}"
    monkeypatch.setenv("MLFLOW_TRACKING_URI", tracking_uri)
    mlflow.set_tracking_uri(tracking_uri)
    mlflow.set_experiment("inventory-demand")

    for slope in (2.0, 3.0):
        with mlflow.start_run() as run:
            # S11 trains the same three inputs used by the serving endpoint:
            # month sine, month cosine, and a scaled trend.
            X = np.array(
                [[0, 1, 0], [1, 0, 0], [0, -1, 0], [-1, 0, 0], [0, 0, 1]],
                dtype=float,
            )
            y = slope * X[:, 0] + slope * X[:, 1] + 2 * X[:, 2]
            mlflow.sklearn.log_model(LinearRegression().fit(X, y), "model")
            mlflow.register_model(f"runs:/{run.info.run_id}/model", "DemandForecastModel")

    result = script.verify_chain(
        tracking_uri=tracking_uri,
        model_name="DemandForecastModel",
        predict_payload={"period": 1, "month": 6},
    )

    assert result["status"] == "passed", result
    assert result["production_version"] == 2
    assert result["rollback_version"] == 1
    assert str(result["rollback_inference_version"]) == "1"
    assert np.isclose(result["prediction"]["predicted_demand"], -3.0)
    assert np.isclose(result["rollback_prediction"]["predicted_demand"], -2.0)
    assert np.isclose(result["drift"]["psi"], 0.5)


def test_chain_gate_fails_closed_without_model(tmp_path):
    script = _load_script()
    result = script.verify_chain(
        tracking_uri=f"sqlite:///{tmp_path / 'empty.db'}",
        model_name="MissingDemandForecastModel",
        predict_payload={"period": 1, "month": 6},
    )
    assert result["status"] == "failed"
    assert result["reason"] == "no_model_versions"
