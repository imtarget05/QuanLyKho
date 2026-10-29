# ML Training Pipeline (Phase M — S4)
#
# Inventory demand forecasting using time-aware split.
# - Train on first N periods (earliest data)
# - Test on remaining later periods (no leakage from future)
# - Baseline model: scikit-learn LinearRegression
# - Log metrics/artifacts to MLflow Tracking (already configured in S3)
# - Reproducible with fixed seed
#
# Dependencies (already in pyproject.toml):
#   - pandas, scikit-learn, mlflow

from pathlib import Path

import mlflow
import mlflow.sklearn
import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score


def generate_synthetic_inventory_demand(n_periods: int = 120, seed: int = 42) -> pd.DataFrame:
    """
    Generate synthetic inventory demand data with seasonality and trend.
    Returns DataFrame with columns: ds (period), y (demand), month (int).
    """
    rng = np.random.default_rng(seed)
    t = np.arange(n_periods)

    # Trend component
    trend = 100 + 0.5 * t

    # Seasonality (monthly pattern)
    seasonality = 20 * np.sin(2 * np.pi * t / 12)

    # Weekly noise
    noise = rng.normal(0, 5, n_periods)

    y = np.maximum(0, trend + seasonality + noise)

    df = pd.DataFrame({
        "ds": pd.period_range(start="2023-01", periods=n_periods, freq="D"),
        "y": y.astype(float),
        "month": (t % 12) + 1,
    })

    return df


def time_aware_split(df: pd.DataFrame, train_ratio: float = 0.8) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Split data chronologically: train on earliest periods, test on latest.
    No future data leaks into training.
    """
    df_sorted = df.sort_values("ds").reset_index(drop=True)
    train_size = int(len(df_sorted) * train_ratio)
    train = df_sorted.iloc[:train_size].copy()
    test = df_sorted.iloc[train_size:].copy()
    return train, test


def train_demand_forecast_model(train: pd.DataFrame, test: pd.DataFrame, experiment_name: str = "inventory-demand") -> dict:
    """
    Train a baseline LinearRegression model on time-aware split.
    Uses month + day-of-year sine/cosine features to capture seasonality.
    Log parameters, metrics, and model to MLflow Tracking (already configured in S3).
    Returns dict with model, metrics, and mlflow run info.
    """

    import os

    artifact_root = os.getenv("MLFLOW_ARTIFACT_ROOT", "/data/mlruns" if os.path.exists("/data") else "./mlruns")
    client = mlflow.tracking.MlflowClient()
    exp = client.get_experiment_by_name(experiment_name)
    if exp is None:
        try:
            client.create_experiment(experiment_name, artifact_location=f"{artifact_root}/{experiment_name}")
        except Exception:
            pass
    mlflow.set_experiment(experiment_name)

    with mlflow.start_run() as run:
        # Prepare features: month sin/cos + day-of-year sin/cos to capture seasonality
        # plus linear trend index
        t_train = np.arange(len(train))
        t_test = np.arange(len(train), len(train) + len(test))

        month_train = train["month"].values
        month_test = test["month"].values

        # Circular encoding of month (1-12) to capture seasonal pattern
        month_sin_train = np.sin(2 * np.pi * month_train / 12).reshape(-1, 1)
        month_cos_train = np.cos(2 * np.pi * month_train / 12).reshape(-1, 1)
        month_sin_test = np.sin(2 * np.pi * month_test / 12).reshape(-1, 1)
        month_cos_test = np.cos(2 * np.pi * month_test / 12).reshape(-1, 1)

        # Day-of-year encoding (approximate: use day of period)
        # We'll use period index * 2π / n_periods for overall trend seasonality

        X_train = np.hstack([
            month_sin_train,
            month_cos_train,
            t_train.reshape(-1, 1).astype(float) / len(train),
        ])
        X_test = np.hstack([
            month_sin_test,
            month_cos_test,
            t_test.reshape(-1, 1).astype(float) / len(train),
        ])

        y_train = train["y"].values
        y_test = test["y"].values

        model = LinearRegression()
        model.fit(X_train, y_train)

        y_pred = model.predict(X_test)

        mae = mean_absolute_error(y_test, y_pred)
        mse = mean_squared_error(y_test, y_pred)
        rmse = np.sqrt(mse)
        r2 = r2_score(y_test, y_pred)

        # Log parameters
        mlflow.log_param("train_size", len(train))
        mlflow.log_param("test_size", len(test))
        mlflow.log_param("train_ratio", 0.8)
        mlflow.log_param("feature_combination", "month_sincos+trend_scaled")
        mlflow.log_param("random_seed", 42)

        # Log metrics
        mlflow.log_metric("mae", float(mae))
        mlflow.log_metric("mse", float(mse))
        mlflow.log_metric("rmse", float(rmse))
        mlflow.log_metric("r2", float(r2))

        # Log model artifact
        mlflow.sklearn.log_model(model, "model", registered_model_name="DemandForecastModel")

        # Log sample data artifact
        temp_dir = Path("/tmp/artifacts") if Path("/tmp").exists() else Path("artifacts")
        temp_dir.mkdir(parents=True, exist_ok=True)
        sample_file = temp_dir / "train_data_sample.csv"
        train.head(10).to_csv(sample_file, index=False)
        mlflow.log_artifact(str(sample_file))

        # Cleanup
        import shutil
        shutil.rmtree(temp_dir, ignore_errors=True)

        result = {
            "run_id": run.info.run_id,
            "model": model,
            "mae": float(mae),
            "rmse": float(rmse),
            "r2": float(r2),
            "train_size": len(train),
            "test_size": len(test),
        }

        print(f"[S4] MLflow run {run.info.run_id}: MAE={mae:.2f}, RMSE={rmse:.2f}, R2={r2:.4f}")
        return result


def run_full_pipeline(n_periods: int = 120, train_ratio: float = 0.8, seed: int = 42) -> dict:
    """
    Full end-to-end pipeline: generate data → split → train → log.
    Designed to be called from Airflow task (S2) or manual execution.
    """
    # Generate synthetic demand data
    df = generate_synthetic_inventory_demand(n_periods=n_periods, seed=seed)
    print(f"[S4] Generated synthetic demand data: {len(df)} periods")

    # Time-aware split
    train, test = time_aware_split(df, train_ratio=train_ratio)
    print(f"[S4] Split: train={len(train)} periods, test={len(test)} periods")

    # Train and log to MLflow
    result = train_demand_forecast_model(train, test, experiment_name="inventory-demand")

    print(f"[S4] Pipeline complete. Run: {result['run_id']}")
    return result