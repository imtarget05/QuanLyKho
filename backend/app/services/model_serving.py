# Model Serving (Phase M — S7)
#
# Production model serving: loads the Production-stage model from MLflow Model
# Registry and serves demand-forecast predictions via a FastAPI endpoint.
#
# Dependencies (already in pyproject.toml):
#   - mlflow, pandas, scikit-learn

from __future__ import annotations

import mlflow
import mlflow.sklearn
import numpy as np
import pandas as pd
from pydantic import BaseModel, Field

from app.services.ml_registry import (
    MODEL_NAME,
    get_current_model_version,
    set_tracking_uri,
)


# ── Request / Response schemas ─────────────────────────────────────────────────
class DemandForecastRequest(BaseModel):
    periods: int = Field(default=30, ge=1, le=365, description="Number of periods to forecast")
    seed: int = Field(default=42, description="Random seed for reproducibility")


class DemandForecastResponse(BaseModel):
    model_version: int
    model_stage: str
    predictions: list[float]
    forecast_periods: int
    generated_at: str


# ── Model loader ───────────────────────────────────────────────────────────────
class ModelServer:
    """
    Loads the Production-stage DemandForecastModel from MLflow Model Registry.
    Falls back to the most recent registered version if none is in Production.
    """

    def __init__(self, tracking_uri: str = "sqlite:///./mlflow.db"):
        self.tracking_uri = tracking_uri
        self.model = None
        self.model_version: int | None = None
        self.model_stage: str | None = None
        self._load_production_model()

    def _load_production_model(self) -> None:
        set_tracking_uri(self.tracking_uri)
        current = get_current_model_version(MODEL_NAME)
        version = current.get("version")

        if version is None:
            # No Production model — fall back to latest registered version
            from app.services.ml_registry import list_model_versions

            versions = list_model_versions(MODEL_NAME)
            if versions:
                version = versions[0]["version"]
                self.model_stage = versions[0]["stage"]
            else:
                raise RuntimeError(
                    f"No registered model versions found for '{MODEL_NAME}'. "
                    "Train and register a model first."
                )
        else:
            self.model_stage = current.get("stage", "Production")

        self.model_version = version
        model_uri = f"models:/{MODEL_NAME}/{version}"
        self.model = mlflow.sklearn.load_model(model_uri)

    def predict(self, request: DemandForecastRequest) -> DemandForecastResponse:
        """
        Generate demand forecasts for the requested number of periods.
        Uses the same feature engineering as training (month sin/cos + trend).
        """
        if self.model is None:
            raise RuntimeError("Model not loaded")

        # Build future feature matrix: month sin/cos + scaled trend index
        t = np.arange(self.model_version or 1, (self.model_version or 1) + request.periods)
        months = ((t % 12) + 1).astype(float)

        month_sin = np.sin(2 * np.pi * months / 12).reshape(-1, 1)
        month_cos = np.cos(2 * np.pi * months / 12).reshape(-1, 1)
        trend_scaled = (t / request.periods).reshape(-1, 1).astype(float)

        X = np.hstack([month_sin, month_cos, trend_scaled])
        predictions = self.model.predict(X)

        return DemandForecastResponse(
            model_version=self.model_version,
            model_stage=self.model_stage or "Unknown",
            predictions=[float(p) for p in predictions],
            forecast_periods=request.periods,
            generated_at=pd.Timestamp.utcnow().isoformat(),
        )


# ── Singleton instance ─────────────────────────────────────────────────────────
_model_server: ModelServer | None = None


def get_model_server(tracking_uri: str = "sqlite:///./mlflow.db") -> ModelServer:
    global _model_server
    if _model_server is None:
        _model_server = ModelServer(tracking_uri=tracking_uri)
    return _model_server