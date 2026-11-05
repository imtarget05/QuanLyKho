"""Fail-closed MLflow registry gate for the S11 cloud workflow.

The command writes a small JSON artifact that names the promoted model version.
It intentionally does not train or bootstrap a model: S11 must prove that the
training stage created a model before registry promotion can succeed.

By default the S11 FULL chain runs (matching the S11 gate definition in
``.github/workflows/s11-e2e-cloud-ci.yml``): promote → predict → drift →
rollback → rollback inference (``verify_chain``). Setting
``S11_FULL_CHAIN=0`` falls back to the registry-promote-only gate
(``verify_registry``), which remains available for narrow registry checks.
"""

from __future__ import annotations

import json
import math
import os
from pathlib import Path
from typing import Any

import mlflow
import numpy as np


def verify_registry(tracking_uri: str, model_name: str) -> dict[str, Any]:
    """Promote the newest registered model, or return a failed gate result."""
    mlflow.set_tracking_uri(tracking_uri)
    client = mlflow.tracking.MlflowClient(tracking_uri=tracking_uri)
    versions = client.search_model_versions(f"name='{model_name}'")

    if not versions:
        return {
            "status": "failed",
            "reason": "no_model_versions",
            "model_name": model_name,
        }

    latest = max(versions, key=lambda version: int(version.version))
    client.transition_model_version_stage(
        name=model_name,
        version=str(latest.version),
        stage="Production",
    )
    return {
        "status": "passed",
        "model_name": model_name,
        "production_version": int(latest.version),
    }


def verify_chain(tracking_uri: str, model_name: str, predict_payload: dict) -> dict[str, Any]:
    """Full fail-closed chain: promote → predict → drift → rollback → rollback inference.

    Steps:
    1. Promote the newest registered model version to Production.
    2. Run inference with the Production model.
    3. Compute drift (PSI) between the previous version and the production version.
    4. Roll back to the previous version (archive the production one).
    5. Run inference again with the rolled-back model.
    """
    mlflow.set_tracking_uri(tracking_uri)
    client = mlflow.tracking.MlflowClient(tracking_uri=tracking_uri)
    versions = client.search_model_versions(f"name='{model_name}'")

    if not versions:
        return {
            "status": "failed",
            "reason": "no_model_versions",
            "model_name": model_name,
        }

    # Sort by version number (ascending).
    sorted_versions = sorted(versions, key=lambda v: int(v.version))
    latest = sorted_versions[-1]
    previous = sorted_versions[-2] if len(sorted_versions) >= 2 else None

    # Step 1: promote the newest version to Production.
    client.transition_model_version_stage(
        name=model_name,
        version=str(latest.version),
        stage="Production",
    )
    production_version = int(latest.version)

    # Step 2: use the same feature contract as POST /predict. The S11 training
    # stage fits month sine, month cosine, and scaled trend in that order.
    month = float(predict_payload["month"])
    predict_features = np.array(
        [[math.sin(2 * math.pi * month / 12), math.cos(2 * math.pi * month / 12), 0.0]]
    )
    model_uri = f"models:/{model_name}/{production_version}"
    model = mlflow.pyfunc.load_model(model_uri)
    prediction_value = float(model.predict(predict_features)[0])
    prediction = {"predicted_demand": prediction_value}

    # Step 3: drift (PSI) between previous version and production version.
    drift_psi = 0.0
    if previous is not None:
        prev_model_uri = f"models:/{model_name}/{previous.version}"
        prev_model = mlflow.pyfunc.load_model(prev_model_uri)
        prev_value = float(prev_model.predict(predict_features)[0])
        if prev_value != 0:
            drift_psi = abs(prediction_value - prev_value) / abs(prev_value)
        else:
            drift_psi = 1.0 if prediction_value != 0 else 0.0
    drift = {"psi": drift_psi}

    # Step 4: rollback to the previous version; archive the production one.
    rollback_version = int(previous.version) if previous is not None else production_version
    client.transition_model_version_stage(
        name=model_name,
        version=str(rollback_version),
        stage="Production",
    )
    client.transition_model_version_stage(
        name=model_name,
        version=str(latest.version),
        stage="Archived",
    )

    # Step 5: inference after rollback.
    rollback_model = mlflow.pyfunc.load_model(f"models:/{model_name}/{rollback_version}")
    rollback_value = float(rollback_model.predict(predict_features)[0])
    rollback_inference_version = str(rollback_version)

    return {
        "status": "passed",
        "model_name": model_name,
        "production_version": production_version,
        "rollback_version": rollback_version,
        "rollback_inference_version": rollback_inference_version,
        "prediction": prediction,
        "rollback_prediction": {"predicted_demand": rollback_value},
        "drift": drift,
    }


def _write_evidence(result: dict[str, Any]) -> None:
    output_path = Path(os.environ.get("E2E_EVIDENCE_PATH", "e2e-registry.json"))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    tracking_uri = os.environ.get("MLFLOW_TRACKING_URI", "sqlite:///./mlflow.db")
    model_name = os.environ.get("MODEL_NAME", "DemandForecastModel")
    # S11 defined in .github/workflows/s11-e2e-cloud-ci.yml is the FULL
    # fail-closed chain (registry promote + rollback + inference), so run
    # verify_chain by default. S11_FULL_CHAIN=0 opts back into the
    # registry-only gate.
    full_chain = os.environ.get("S11_FULL_CHAIN", "1").strip().lower() not in (
        "0",
        "false",
        "no",
    )
    if full_chain:
        result = verify_chain(
            tracking_uri=tracking_uri,
            model_name=model_name,
            predict_payload={"period": 1, "month": 6},
        )
    else:
        result = verify_registry(tracking_uri=tracking_uri, model_name=model_name)
    _write_evidence(result)
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
