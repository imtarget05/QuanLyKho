"""Các task callable thật cho DAG ingest của QuanLyKho.

Quy tắc: **không lambda, không `lambda: None`**.  Mỗi callable ở đây là hàm
cấp module nên Airflow serialize được (``qlk_ingest.tasks.read_source``) và
test được trực tiếp ở mức unit.

Chuỗi task (mỗi DAG dùng chung):

``read_source`` → ``parse_rows`` → ``validate_rows`` → ``load_staging``
(+ ``train_demand_model`` → ``promote_demand_model`` cho DAG inventory)

Mỗi task tự resolve nguồn dữ liệu từ biến môi trường (fail-closed) nên vẫn
chạy được khi gọi độc lập — thuận tiện cho unit test và cho `airflow tasks test`.
"""

from __future__ import annotations

import hashlib
import json
import os
from typing import Any

from qlk_ingest import config as cfg
from qlk_ingest import staging


def _etl_engine():
    """Import lười hàm thật của ứng dụng (parse/fingerprint)."""
    from app.services import etl_engine

    return etl_engine


def _rows_from_context(context: dict[str, Any], task_id: str) -> list[dict[str, Any]] | None:
    """Lấy dòng từ XCom nếu task trước đã xuất (best effort)."""
    ti = context.get("ti")
    if ti is None:
        return None
    try:
        payload = ti.xcom_pull(task_ids=task_id)
    except Exception:  # noqa: BLE001 - XCom là tối ưu, không phải nguồn sự thật
        return None
    if isinstance(payload, dict) and isinstance(payload.get("rows"), list):
        return list(payload["rows"])
    if isinstance(payload, list):
        return list(payload)
    return None


def _reparse(dataset: str) -> list[dict[str, Any]]:
    """Parse lại nguồn (fallback khi không có XCom)."""
    return parse_rows(dataset)["rows"]


def _extract_collection(parsed: list[dict[str, Any]], collection: str | None) -> list[dict[str, Any]]:
    """Lấy collection con (vd ``items`` trong ``inventory.json``) nếu có."""
    if not collection:
        return list(parsed)
    for row in parsed:
        if isinstance(row, dict) and isinstance(row.get(collection), list):
            return list(row[collection])
    raise ValueError(f"Không tìm thấy collection '{collection}' trong dữ liệu nguồn")


def read_source(dataset: str, **context: Any) -> dict[str, Any]:
    """Task 1: đọc file nguồn và trả metadata thật (kích thước, sha256)."""
    spec = cfg.resolve_source(dataset)
    if not spec.path.exists():
        raise FileNotFoundError(f"[{dataset}] Không tìm thấy nguồn dữ liệu: {spec.path}")
    content = spec.path.read_bytes()
    return {
        "dataset": dataset,
        "path": str(spec.path),
        "source_name": spec.path.name,
        "source_type": spec.source_type,
        "size_bytes": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
    }


def parse_rows(dataset: str, **context: Any) -> dict[str, Any]:
    """Task 2: parse nguồn bằng ``app.services.etl_engine`` (không tự parse lại)."""
    spec = cfg.resolve_source(dataset)
    if not spec.path.exists():
        raise FileNotFoundError(f"[{dataset}] Không tìm thấy nguồn dữ liệu: {spec.path}")
    content = spec.path.read_bytes()
    etl = _etl_engine()
    parsed = etl.parse_raw_source(content, spec.source_type)
    rows = _extract_collection(parsed, spec.collection)
    if not rows:
        raise ValueError(f"[{dataset}] Nguồn {spec.path} không có dòng dữ liệu nào")
    bad = [i for i, row in enumerate(rows, start=1) if not isinstance(row, dict)]
    if bad:
        raise ValueError(f"[{dataset}] Dòng không phải object: {bad[:5]}")
    return {
        "dataset": dataset,
        "row_count": len(rows),
        "rows": rows,
    }


def validate_rows(
    dataset: str,
    rows: list[dict[str, Any]] | None = None,
    **context: Any,
) -> dict[str, Any]:
    """Task 3: kiểm tra dòng bắt buộc + tính fingerprint (idempotency key)."""
    spec = cfg.resolve_source(dataset)
    if rows is None:
        rows = _rows_from_context(context, "parse_rows")
    if rows is None:
        rows = _reparse(dataset)

    etl = _etl_engine()
    fingerprint = etl.compute_fingerprint(rows)

    invalid: list[dict[str, Any]] = []
    for index, row in enumerate(rows, start=1):
        problems: list[str] = []
        for field in spec.required_fields:
            value = row.get(field)
            if value is None or str(value).strip() == "":
                problems.append(f"thiếu '{field}'")
        for field in spec.numeric_fields:
            value = row.get(field)
            try:
                if value is None or float(str(value).strip()) <= 0:
                    problems.append(f"'{field}' phải > 0")
            except (TypeError, ValueError):
                problems.append(f"'{field}' không phải số")
        if problems:
            invalid.append({"row_number": index, "problems": problems})

    if invalid and cfg.is_strict():
        raise ValueError(
            f"[{dataset}] {len(invalid)}/{len(rows)} dòng không hợp lệ: {invalid[:5]}"
        )

    return {
        "dataset": dataset,
        "row_count": len(rows),
        "valid_rows": len(rows) - len(invalid),
        "invalid_rows": len(invalid),
        "invalid_detail": invalid[:20],
        "fingerprint": fingerprint,
        "required_fields": list(spec.required_fields),
        "business_key": spec.business_key,
    }


def load_staging(
    dataset: str,
    rows: list[dict[str, Any]] | None = None,
    fingerprint: str | None = None,
    **context: Any,
) -> dict[str, Any]:
    """Task 4: nạp dòng vào bảng staging (idempotent theo fingerprint + row hash)."""
    spec = cfg.resolve_source(dataset)
    if rows is None:
        rows = _rows_from_context(context, "parse_rows")
    if rows is None:
        rows = _reparse(dataset)
    etl = _etl_engine()
    fingerprint = fingerprint or etl.compute_fingerprint(rows)

    database_url = cfg.resolve_database_url()
    table_name = cfg.staging_table_name()
    engine = staging.create_staging_engine(database_url)
    try:
        result = staging.load_rows(
            engine=engine,
            table_name=table_name,
            dataset=dataset,
            source_name=spec.path.name,
            fingerprint=fingerprint,
            rows=rows,
            business_key=spec.business_key,
        )
    finally:
        engine.dispose()

    return {
        **result,
        "fingerprint": fingerprint,
        "database": staging.normalize_sync_url(database_url).rsplit("@", 1)[-1],
    }


def train_demand_model(**context: Any) -> dict[str, Any]:
    """Task 5: huấn luyện model nhu cầu (gọi ``app.services.ml_training``).

    Model, params, metrics và artifact đều được ghi vào MLflow thật.
    """
    import mlflow

    tracking_uri = cfg.resolve_mlflow_tracking_uri()
    artifact_dir = cfg.resolve_mlflow_artifact_dir()
    artifact_dir.mkdir(parents=True, exist_ok=True)

    mlflow.set_tracking_uri(tracking_uri)
    if mlflow.get_experiment_by_name(cfg.MLFLOW_EXPERIMENT) is None:
        mlflow.create_experiment(
            cfg.MLFLOW_EXPERIMENT,
            artifact_location=artifact_dir.as_uri(),
        )
    mlflow.set_experiment(cfg.MLFLOW_EXPERIMENT)

    from app.services.ml_training import run_full_pipeline

    n_periods = int(os.environ.get("QLK_INGEST_ML_N_PERIODS", "120"))
    train_ratio = float(os.environ.get("QLK_INGEST_ML_TRAIN_RATIO", "0.8"))
    seed = int(os.environ.get("QLK_INGEST_ML_SEED", "42"))

    result = run_full_pipeline(n_periods=n_periods, train_ratio=train_ratio, seed=seed)
    return {
        "run_id": result["run_id"],
        "mae": result["mae"],
        "rmse": result["rmse"],
        "r2": result["r2"],
        "train_size": result["train_size"],
        "test_size": result["test_size"],
        "model_name": cfg.MLFLOW_MODEL_NAME,
        "tracking_uri": tracking_uri,
    }


def promote_demand_model(r2: float | None = None, **context: Any) -> dict[str, Any]:
    """Task 6: promote model lên Production **chỉ khi** đạt ngưỡng chất lượng."""
    import mlflow

    tracking_uri = cfg.resolve_mlflow_tracking_uri()
    mlflow.set_tracking_uri(tracking_uri)

    from app.services import ml_registry

    if r2 is None:
        upstream = _rows_from_context(context, "train_demand_model")
        if isinstance(upstream, dict):
            r2 = upstream.get("r2")
    if r2 is None:
        payload = context.get("ti")
        if payload is not None:
            try:
                trained = payload.xcom_pull(task_ids="train_demand_model")
                if isinstance(trained, dict):
                    r2 = trained.get("r2")
            except Exception:  # noqa: BLE001
                r2 = None

    threshold = ml_registry.PROMOTION_THRESHOLD_R2
    versions = ml_registry.list_model_versions()
    if not versions:
        return {
            "promoted": False,
            "reason": "no_model_versions",
            "r2": r2,
            "threshold": threshold,
        }

    latest = max(int(v["version"]) for v in versions)
    if r2 is not None and float(r2) < threshold:
        return {
            "promoted": False,
            "reason": "r2_below_threshold",
            "r2": float(r2),
            "threshold": threshold,
            "version": latest,
        }

    result = ml_registry.promote_model(from_version=latest)
    return {
        "promoted": bool(result.get("success")),
        "version": result.get("version"),
        "stage": result.get("stage"),
        "r2": float(r2) if r2 is not None else None,
        "threshold": threshold,
        "message": result.get("message"),
    }


def detect_drift(
    reference_days: int | None = None,
    current_days: int | None = None,
    **context: Any,
) -> dict[str, Any]:
    """Task: phát hiện data/concept drift trên dữ liệu staging (gọi ``app.services.drift_detection``).

    So sánh phân phối features trong cửa sổ tham chiếu (reference_days) với cửa sổ hiện tại (current_days).
    Trả về kết quả drift + recommendation (no_action / scheduled_retraining / data_preprocessing / investigate).
    """
    from datetime import UTC, datetime, timedelta

    import pandas as pd
    from app.services import drift_detection
    from sqlalchemy import select

    # Resolve DB connection and staging table
    database_url = cfg.resolve_database_url()
    table_name = cfg.staging_table_name()

    # Defaults: reference = 30 days ago to 7 days ago; current = last 7 days
    ref_days_back = int(reference_days or os.environ.get("QLK_INGEST_DRIFT_REFERENCE_DAYS", "30"))
    ref_window = int(os.environ.get("QLK_INGEST_DRIFT_REFERENCE_WINDOW", "23"))
    cur_days_back = int(current_days or os.environ.get("QLK_INGEST_DRIFT_CURRENT_DAYS", "7"))
    cur_window = int(os.environ.get("QLK_INGEST_DRIFT_CURRENT_WINDOW", "7"))

    # Feature columns to monitor (inventory domain)
    feature_cols = ["cost_price", "selling_price", "min_qty", "min_stock", "max_qty"]
    table = staging.staging_metadata(table_name).tables[table_name]
    now = datetime.now(UTC)
    ref_start = now - timedelta(days=ref_days_back)
    ref_end = ref_start + timedelta(days=ref_window)
    cur_start = now - timedelta(days=cur_days_back)
    cur_end = cur_start + timedelta(days=cur_window)

    def load_features(conn: Any, start: datetime, end: datetime) -> pd.DataFrame:
        payloads = conn.execute(
            select(table.c.payload).where(
                table.c.dataset == "inventory",
                table.c.ingested_at >= start,
                table.c.ingested_at < end,
            )
        ).scalars()
        frame = pd.DataFrame(json.loads(payload) for payload in payloads)
        for feature in feature_cols:
            frame[feature] = pd.to_numeric(frame.get(feature), errors="coerce")
        return frame.dropna(subset=feature_cols)

    engine = staging.create_staging_engine(database_url)
    try:
        with engine.connect() as conn:
            ref_df = load_features(conn, ref_start, ref_end)
            cur_df = load_features(conn, cur_start, cur_end)
    finally:
        engine.dispose()

    if ref_df.empty or cur_df.empty:
        return {
            "drifted": False,
            "reason": "insufficient_data",
            "reference_rows": len(ref_df),
            "current_rows": len(cur_df),
        }

    # Run drift analysis
    result = drift_detection.analyze_drift(
        reference_data=ref_df[feature_cols],
        current_data=cur_df[feature_cols],
        feature_cols=feature_cols,
    )

    # Push summary to XCom for visibility
    return {
        "drifted": result["drift_result"]["drifted"],
        "drift_type": result["drift_result"]["drift_type"],
        "overall_psi": result["drift_result"]["psi"],
        "affected_features": result["drift_result"]["affected_features"],
        "recommendation": result["recommendation"],
        "reference_rows": len(ref_df),
        "current_rows": len(cur_df),
        "reference_days_back": ref_days_back,
        "reference_window": ref_window,
        "current_days_back": cur_days_back,
        "current_window": cur_window,
        "threshold_psi": drift_detection.PSI_THRESHOLD,
        "ks_confirm_alpha": drift_detection.KS_CONFIRM_ALPHA,
    }


def dump_json(payload: Any) -> str:
    """Helper: pretty JSON (dùng cho log/evidence)."""
    return json.dumps(payload, indent=2, ensure_ascii=False, default=str)
