"""Test *thực thi* cho các task của DAG Airflow (Phase M — S2).

`test_airflow_dags.py` kiểm tra cấu trúc DAG; file này kiểm tra **side effect
thật** của từng callable:

* `read_source` trả metadata thật của file nguồn (size + sha256);
* `parse_rows` parse bằng `app.services.etl_engine` và trả về số dòng thật;
* `validate_rows` sinh fingerprint ổn định và **fail-closed** khi dòng sai;
* `load_staging` **ghi dòng vào database** và chạy lại thì không nạp trùng;
* `train_demand_model` **ghi run/params/metrics/artifact vào MLflow** và đăng ký
  model;
* `promote_demand_model` chỉ promote khi R² ≥ ngưỡng.

DB dùng trong test là database disposable của phiên pytest (`DATABASE_URL`,
tên phải chứa `_test` theo `backend/tests/conftest.py`); bảng staging dùng tên
riêng và được xoá sau test.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
AIRFLOW_DAGS_DIR = Path(__file__).resolve().parents[2] / "infra" / "airflow" / "dags"

for _candidate in (str(BACKEND_DIR), str(AIRFLOW_DAGS_DIR)):
    if _candidate not in sys.path:
        sys.path.insert(0, _candidate)

from qlk_ingest import config as qlk_config  # noqa: E402
from qlk_ingest import staging as qlk_staging  # noqa: E402
from qlk_ingest import tasks as qlk_tasks  # noqa: E402

TEST_TABLE = "qlk_ingest_staging_pytest"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def database_url() -> str:
    """URL database disposable của phiên pytest (bỏ qua nếu không kết nối được)."""
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        pytest.skip("DATABASE_URL chưa được set — bỏ qua test ghi DB")
    try:
        from sqlalchemy import create_engine, text

        engine = create_engine(qlk_staging.normalize_sync_url(url), pool_pre_ping=True)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        engine.dispose()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"Không kết nối được database test: {exc}")
    return url


@pytest.fixture
def staging_table(database_url: str, monkeypatch: pytest.MonkeyPatch):
    """Bảng staging riêng cho test, xoá sau khi test."""
    monkeypatch.setenv("QLK_INGEST_STAGING_TABLE", TEST_TABLE)
    engine = qlk_staging.create_staging_engine(database_url)
    metadata = qlk_staging.staging_metadata(TEST_TABLE)
    try:
        metadata.create_all(engine)
    except Exception as exc:  # noqa: BLE001
        engine.dispose()
        pytest.skip(f"Role test không có quyền tạo bảng staging: {exc}")
    try:
        yield engine
    finally:
        with engine.begin() as conn:
            conn.exec_driver_sql(f"DROP TABLE IF EXISTS {TEST_TABLE}")
        engine.dispose()


@pytest.fixture
def mlflow_tracking(tmp_path, monkeypatch: pytest.MonkeyPatch):
    """Tracking store MLflow cô lập cho từng test."""
    import mlflow

    tracking_dir = tmp_path / "mlflow"
    tracking_dir.mkdir(parents=True, exist_ok=True)
    url = f"sqlite:///{tracking_dir / 'mlflow.db'}"
    previous_uri = mlflow.get_tracking_uri()
    monkeypatch.setenv("MLFLOW_TRACKING_URI", url)
    monkeypatch.setenv("QLK_INGEST_MLFLOW_TRACKING_URI", url)
    monkeypatch.setenv("QLK_INGEST_MLFLOW_ARTIFACT_DIR", str(tracking_dir / "mlruns"))
    monkeypatch.setenv("QLK_INGEST_ML_N_PERIODS", "40")
    mlflow.set_tracking_uri(url)
    try:
        yield url
    finally:
        mlflow.set_tracking_uri(previous_uri)


# ---------------------------------------------------------------------------
# 1. Đọc nguồn
# ---------------------------------------------------------------------------

def test_read_source_reports_real_file_metadata() -> None:
    """read_source trả size + sha256 thật của file nguồn."""
    result = qlk_tasks.read_source("inventory")
    assert result["dataset"] == "inventory"
    assert result["source_name"] == "inventory.json"
    assert result["size_bytes"] > 0
    assert len(result["sha256"]) == 64
    assert Path(result["path"]).is_file()


def test_read_source_fails_closed_when_file_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Nguồn không tồn tại ⇒ task fail, không âm thầm trả dữ liệu rỗng."""
    monkeypatch.setenv("QLK_INGEST_INVENTORY_SOURCE", "/nonexistent/inventory.json")
    with pytest.raises(FileNotFoundError):
        qlk_tasks.read_source("inventory")


# ---------------------------------------------------------------------------
# 2. Parse
# ---------------------------------------------------------------------------

def test_parse_rows_extracts_inventory_items() -> None:
    """parse_rows dùng etl_engine thật và lấy collection `items`."""
    result = qlk_tasks.parse_rows("inventory")
    assert result["row_count"] == 30
    assert len(result["rows"]) == 30
    first = result["rows"][0]
    assert "sku" in first and "name" in first


@pytest.mark.parametrize(
    ("dataset", "expected_rows"),
    [("inventory", 30), ("expense", 8), ("supplier", 3)],
)
def test_parse_rows_for_every_dataset(dataset: str, expected_rows: int) -> None:
    """Cả 3 dataset đều parse được ra số dòng thật."""
    result = qlk_tasks.parse_rows(dataset)
    assert result["row_count"] == expected_rows
    assert all(isinstance(row, dict) for row in result["rows"])


# ---------------------------------------------------------------------------
# 3. Validate
# ---------------------------------------------------------------------------

def test_validate_rows_produces_stable_fingerprint() -> None:
    """Fingerprint ổn định giữa hai lần chạy (khóa idempotency)."""
    rows = qlk_tasks.parse_rows("inventory")["rows"]
    first = qlk_tasks.validate_rows("inventory", rows=rows)
    second = qlk_tasks.validate_rows("inventory", rows=rows)
    assert first["fingerprint"] == second["fingerprint"]
    assert len(first["fingerprint"]) == 64
    assert first["valid_rows"] == 30
    assert first["invalid_rows"] == 0


def test_validate_rows_fails_closed_on_invalid_rows(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Dòng thiếu trường bắt buộc ⇒ raise (không nạp dữ liệu bẩn)."""
    bad_csv = tmp_path / "bad_expenses.csv"
    bad_csv.write_text(
        "expense_ref,supplier_code,category,amount,currency,occurred_on\n"
        "EXP-1,SUP-001,raw_material,1000,VND,2026-10-01\n"
        ",SUP-002,raw_material,abc,VND,2026-10-02\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("QLK_INGEST_EXPENSE_SOURCE", str(bad_csv))
    rows = qlk_tasks.parse_rows("expense")["rows"]
    with pytest.raises(ValueError, match="không hợp lệ"):
        qlk_tasks.validate_rows("expense", rows=rows)


# ---------------------------------------------------------------------------
# 4. Nạp staging (side effect thật vào DB)
# ---------------------------------------------------------------------------

def test_load_staging_writes_rows_to_database(staging_table) -> None:
    """load_staging ghi dòng thật vào bảng staging, đếm được số dòng."""
    result = qlk_tasks.load_staging("inventory")
    assert result["inserted"] == 30
    assert result["skipped"] == 0
    assert result["total_rows"] == 30
    assert result["table"] == TEST_TABLE

    stored = qlk_staging.count_rows(staging_table, TEST_TABLE, "inventory")
    assert stored == 30


def test_load_staging_is_idempotent(staging_table) -> None:
    """Chạy lại cùng dữ liệu ⇒ không nạp trùng (skipped = toàn bộ)."""
    first = qlk_tasks.load_staging("inventory")
    second = qlk_tasks.load_staging("inventory")
    assert first["inserted"] == 30
    assert second["inserted"] == 0
    assert second["skipped"] == 30
    assert qlk_staging.count_rows(staging_table, TEST_TABLE, "inventory") == 30


def test_detect_drift_reads_staging_payload_without_invented_columns(staging_table) -> None:
    """A fresh ingest has no historical reference window, but the DAG must run."""
    qlk_tasks.load_staging("inventory")

    result = qlk_tasks.detect_drift()

    assert result == {
        "drifted": False,
        "reason": "insufficient_data",
        "reference_rows": 0,
        "current_rows": 30,
    }


def test_detect_drift_uses_both_time_windows(staging_table) -> None:
    """Rows from both windows produce an actual distribution comparison."""
    from datetime import UTC, datetime, timedelta

    from sqlalchemy import update

    qlk_tasks.load_staging("inventory")
    table = qlk_staging.staging_metadata(TEST_TABLE).tables[TEST_TABLE]
    with staging_table.begin() as conn:
        conn.execute(
            update(table)
            .where(table.c.row_number <= 15)
            .values(ingested_at=datetime.now(UTC) - timedelta(days=20))
        )

    result = qlk_tasks.detect_drift()

    assert result["reference_rows"] == 15
    assert result["current_rows"] == 15
    assert result["recommendation"] in {
        "no_action", "scheduled_retraining", "data_preprocessing", "investigate"
    }


def test_load_staging_writes_expense_and_supplier(staging_table) -> None:
    """Các dataset còn lại cũng nạp được vào bảng staging."""
    expense = qlk_tasks.load_staging("expense")
    supplier = qlk_tasks.load_staging("supplier")
    assert expense["inserted"] == 8
    assert supplier["inserted"] == 3
    assert qlk_staging.count_rows(staging_table, TEST_TABLE, "expense") == 8
    assert qlk_staging.count_rows(staging_table, TEST_TABLE, "supplier") == 3


def test_resolve_database_url_refuses_non_test_database(monkeypatch: pytest.MonkeyPatch) -> None:
    """Guard an toàn: không ghi staging vào database dev `bankops`."""
    monkeypatch.setenv("QLK_INGEST_DATABASE_URL", "postgresql+psycopg2://bankops:bankops@127.0.0.1:5432/bankops")
    monkeypatch.delenv("QLK_INGEST_ALLOW_ANY_DB", raising=False)
    with pytest.raises(RuntimeError, match="test"):
        qlk_config.resolve_database_url()


# ---------------------------------------------------------------------------
# 5. MLflow: train + promote
# ---------------------------------------------------------------------------

def test_train_demand_model_logs_to_mlflow(mlflow_tracking: str) -> None:
    """Task train ghi run/params/metrics/artifact thật vào MLflow + đăng ký model."""
    import mlflow

    result = qlk_tasks.train_demand_model()
    assert result["run_id"]
    assert result["r2"] > 0
    assert result["mae"] > 0

    client = mlflow.tracking.MlflowClient()
    run = client.get_run(result["run_id"])
    assert run.info.status == "FINISHED"
    assert run.data.params["train_size"] == str(result["train_size"])
    assert "r2" in run.data.metrics
    assert abs(run.data.metrics["r2"] - result["r2"]) < 1e-9
    artifacts = [a.path for a in client.list_artifacts(result["run_id"])]
    assert "train_data_sample.csv" in artifacts

    versions = client.search_model_versions(f"name='{result['model_name']}'")
    assert versions, "Model chưa được đăng ký vào registry"


def test_promote_demand_model_blocks_low_r2(mlflow_tracking: str) -> None:
    """R² dưới ngưỡng ⇒ KHÔNG promote lên Production."""
    from app.services import ml_registry

    qlk_tasks.train_demand_model()
    result = qlk_tasks.promote_demand_model(r2=0.1)
    assert result["promoted"] is False
    assert result["reason"] == "r2_below_threshold"
    assert result["threshold"] == ml_registry.PROMOTION_THRESHOLD_R2


def test_promote_demand_model_promotes_when_gate_passes(mlflow_tracking: str) -> None:
    """R² đạt ngưỡng ⇒ promote lên Production (side effect thật trong registry)."""
    from app.services import ml_registry

    trained = qlk_tasks.train_demand_model()
    result = qlk_tasks.promote_demand_model(r2=trained["r2"])
    assert result["promoted"] is True
    assert result["stage"] == "Production"

    current = ml_registry.get_current_model_version()
    assert current["version"] is not None
    assert current["stage"] == "Production"
