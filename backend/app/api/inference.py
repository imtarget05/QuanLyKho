# Model Serving API (Phase M — S6)
#
# FastAPI inference endpoint với model đã Promotion sang Production.
# - Chỉ serving model đang ở stage Production
# - Validation đầu vào với Pydantic v2
# - Log inference request/response metrics
# - Health check endpoint
#
# Dependencies (already in pyproject.toml):
#   - fastapi, uvicorn, pydantic, mlflow

import logging
import math
import os
from datetime import datetime

import mlflow
import numpy as np
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, field_validator

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("model-serving")

# MLflow configuration
def _default_tracking_uri() -> str:
    """Use the image data mount when writable, otherwise a local SQLite store."""
    if os.path.isdir("/data") and os.access("/data", os.W_OK):
        return "sqlite:////data/mlflow.db"
    return "sqlite:///./mlflow.db"


MLFLOW_TRACKING_URI = os.getenv("MLFLOW_TRACKING_URI") or _default_tracking_uri()
MLFLOW_ARTIFACT_ROOT = os.getenv(
    "MLFLOW_ARTIFACT_ROOT",
    "/data/mlruns" if os.path.exists("/data") else "./mlruns",
)

# Ensure writable directories exist for container runtime
for d in (MLFLOW_ARTIFACT_ROOT, "/data", "/app/mlruns", "/tmp/artifacts"):
    try:
        os.makedirs(d, exist_ok=True)
    except Exception:
        pass

os.environ["_MLFLOW_SERVER_ARTIFACT_ROOT"] = MLFLOW_ARTIFACT_ROOT
os.environ["MLFLOW_REGISTRY_DIR"] = MLFLOW_ARTIFACT_ROOT
os.environ["MLFLOW_ARTIFACT_ROOT"] = MLFLOW_ARTIFACT_ROOT
mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
# With no explicit registry URI, MLflow follows the current tracking URI. This
# matters for local tests that replace the tracking URI with a temporary store.

MODEL_NAME = "DemandForecastModel"
# When the registry holds no Production model the service can train, register
# and promote a baseline model itself (a real MLflow run, no mock). Set
# INFERENCE_AUTO_BOOTSTRAP=0 to disable it — then the endpoint fails with a
# clear 503 MODEL_NOT_AVAILABLE instead.
AUTO_BOOTSTRAP = os.getenv("INFERENCE_AUTO_BOOTSTRAP", "1").strip().lower() in (
    "1",
    "true",
    "yes",
    "on",
)

mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)


class ModelNotAvailableError(RuntimeError):
    """No model is available in the Production stage of the registry."""

    code = "MODEL_NOT_AVAILABLE"


# Request/Response schemas
class InferenceRequest(BaseModel):
    """Request body for model inference."""
    period: int
    month: int

    @field_validator("month")
    @classmethod
    def month_must_be_valid(cls, v):
        if not 1 <= v <= 12:
            raise ValueError("Month must be between 1 and 12")
        return v

    @field_validator("period")
    @classmethod
    def period_must_be_positive(cls, v):
        if v < 1:
            raise ValueError("Period must be >= 1")
        return v


class InferenceResponse(BaseModel):
    """Response body for model inference."""
    period: int
    month: int
    predicted_demand: float
    confidence_lower: float
    confidence_upper: float
    model_version: str
    timestamp: str


# FastAPI app
app = FastAPI(
    title="Demand Forecasting API",
    description="API for inventory demand forecasting using MLflow-registered models",
    version="1.0.0",
)


# Global model state
_model = None
_model_version = None


def reset_model_cache() -> None:
    """Forget the cached model (used when the registry or URI changes)."""
    global _model, _model_version
    _model = None
    _model_version = None


def _production_versions() -> list:
    """All model versions that are currently in the Production stage."""
    client = mlflow.tracking.MlflowClient()
    versions = client.search_model_versions(f"name='{MODEL_NAME}'")
    return [v for v in versions if v.current_stage == "Production"]


def bootstrap_production_model() -> int:
    """Train, register and promote a baseline model; return its version.

    This is a *real* MLflow run (train → log → register → promote), not a
    stub: the promoted model is the one that is served afterwards.
    """
    from app.ai.training import run_full_pipeline
    from app.services import ml_registry

    logger.warning(
        "No %s model in Production stage — training and promoting a baseline model",
        MODEL_NAME,
    )
    run_full_pipeline()

    versions = ml_registry.list_model_versions(MODEL_NAME)
    if not versions:
        raise ModelNotAvailableError(
            f"Model '{MODEL_NAME}' could not be registered in the MLflow registry"
        )
    latest = max(versions, key=lambda item: int(item["version"]))
    result = ml_registry.promote_model(
        MODEL_NAME, from_version=int(latest["version"]), to_stage="Production"
    )
    if not result.get("success"):
        raise ModelNotAvailableError(
            f"Model '{MODEL_NAME}' could not be promoted to Production: "
            f"{result.get('message')}"
        )
    logger.info("Bootstrapped %s version %s into Production", MODEL_NAME, latest["version"])
    return int(latest["version"])


def get_model() -> tuple:
    """Load the latest Production model from MLflow Registry."""
    global _model, _model_version
    if _model is None or _model_version is None:
        production_versions = _production_versions()
        if not production_versions:
            if not AUTO_BOOTSTRAP:
                raise ModelNotAvailableError(
                    f"No model '{MODEL_NAME}' in Production stage. "
                    "Register and promote a model before serving predictions."
                )
            try:
                bootstrap_production_model()
            except ModelNotAvailableError:
                raise
            except Exception as exc:  # noqa: BLE001 - any failure is a missing model
                raise ModelNotAvailableError(
                    f"No model '{MODEL_NAME}' in Production stage and the baseline "
                    f"model could not be trained: {exc}"
                ) from exc
            production_versions = _production_versions()
            if not production_versions:
                raise ModelNotAvailableError(
                    f"No model '{MODEL_NAME}' in Production stage after bootstrapping"
                )
        # Sort by version descending and take latest
        production_versions.sort(key=lambda v: int(v.version), reverse=True)
        version_number = production_versions[0].version

        # Load the model
        model_uri = f"models:/{MODEL_NAME}/{version_number}"
        try:
            _model = mlflow.pyfunc.load_model(model_uri)
        except Exception as exc:  # noqa: BLE001 - a broken artifact is a missing model
            _model = None
            raise ModelNotAvailableError(
                f"Model '{MODEL_NAME}' version {version_number} could not be loaded: {exc}"
            ) from exc
        _model_version = str(version_number)

        logger.info(f"Loaded model {MODEL_NAME} v{_model_version} from Production stage")
    return _model, _model_version


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    try:
        model, version = get_model()
        return {"status": "healthy", "model": MODEL_NAME, "version": version}
    except ModelNotAvailableError as exc:
        logger.warning(f"Health check failed: {exc}")
        return {
            "status": "degraded",
            "model": MODEL_NAME,
            "error": str(exc),
            "code": exc.code,
        }
    except Exception as e:  # noqa: BLE001 - health must never raise
        logger.warning(f"Health check failed: {e}")
        return {"status": "degraded", "model": MODEL_NAME, "error": str(e)}


@app.post("/predict", response_model=InferenceResponse)
async def predict(request: InferenceRequest):
    """Run model inference on input features."""
    # Manual validation
    if request.month < 1 or request.month > 12:
        raise HTTPException(status_code=422, detail="Month must be between 1 and 12")
    if request.period < 1:
        raise HTTPException(status_code=422, detail="Period must be >= 1")

    try:
        model, version = get_model()
    except ModelNotAvailableError as exc:
        logger.error(f"Model not available: {exc}")
        raise HTTPException(
            status_code=503,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc

    try:
        # Prepare features for model prediction
        # For the baseline LinearRegression model, we use month sin/cos encoding
        month_sin = math.sin(2 * math.pi * request.month / 12)
        month_cos = math.cos(2 * math.pi * request.month / 12)

        # Create feature array: [month_sin, month_cos, trend_scaled]
        # The model was trained with: hstack([month_sin, month_cos, trend_scaled])
        # trend_scaled = 0 for single prediction
        features = np.array([[month_sin, month_cos, 0.0]])

        # Run inference
        prediction = float(model.predict(features)[0])

        # Calculate simple confidence interval (based on model RMSE from training)
        # In production, this would use proper uncertainty quantification
        rmse = 30.0  # This would be fetched from model metadata
        margin = 1.96 * rmse  # 95% confidence interval

        response = InferenceResponse(
            period=request.period,
            month=request.month,
            predicted_demand=max(0, prediction),  # Ensure non-negative
            confidence_lower=max(0, prediction - margin),
            confidence_upper=prediction + margin,
            model_version=version,
            timestamp=datetime.now().isoformat(),
        )

        logger.info(
            f"Inference request: period={request.period}, month={request.month}, "
            f"predicted={response.predicted_demand:.2f}, version={version}"
        )

        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Inference error: {e}")
        raise HTTPException(status_code=500, detail=f"Inference failed: {str(e)}") from e


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
