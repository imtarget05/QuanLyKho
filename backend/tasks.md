# Trạng thái thực thi — Track A/B/C/D

Cập nhật: 2026-11-19. Mỗi mục `[x]` kèm bằng chứng đã chạy thật trên máy local.

## Track A — GraphQL (QuanLyKho)

### A1–A5 — hoàn tất
- [x] `app/graphql/` (Ariadne 0.20.0) + `router.py` mount tại `/graphql` (`app/main.py`).
- [x] `app/services/balance_lock.py`: pessimistic lock `SELECT … FOR UPDATE`, overdraft guard, debit/credit atomic + CAS version.
- [x] Types/inputs/schema/resolvers: banking (transferFunds, createTransaction, account, balance), inventory (adjustInventory, stockMovement), saga (executeSaga, sagaStatus).
- [x] Idempotency middleware toàn cục (`app/api/middleware/idempotency.py`, `main.py:128`) + rate limit FastAPI.
- [x] Health query: `{'health': {'status': 'healthy', 'service': 'quanlykho-graphql'}}`.

### Còn mở
- [ ] A6 — DataLoader chống N+1: `app/graphql/loaders/` hiện rỗng (chưa có AccountLoader/LedgerEntryLoader).
- [ ] A7 — bộ test GraphQL đầy đủ (`test_graphql_double_entry/concurrency/idempotency/saga_rollback/audit_chain/outbox`): hiện chỉ có smoke test health.
- [ ] A8 — deprecate REST banking/cash_sim/saga khỏi `main.py` (rủi ro vỡ frontend, cần quyết định trước khi làm).

## Track B — baseline
- [x] QuanLyKho backend test suite: `pytest tests -q` → **1345 passed, 8 skipped, 1 xfailed** (PostgreSQL local).
- [x] GraphQL endpoint mount + health OK.
- [ ] FlashSale load test (k6 ≥1000 TPS): chưa chạy — cần k6/JDK/Maven/Docker.

## Track C — MLOps (QuanLyKho)

- [x] **C1** MLflow local: `sqlite:///./mlflow.db`, artifacts `./mlruns`, không hardcode `/data`. `ml_training.run_full_pipeline` gọi `set_tracking_uri(os.getenv("MLFLOW_TRACKING_URI", "sqlite:///./mlflow.db"))`.
- [x] **C2** ETL → train → register → promote (R² ≥ 0.7) → serve, có rollback.
  - Bằng chứng: R²=0.8871, run `eb81841a…`, version 13 → gate `success=True` → serving trả version 13 → `rollback_model()` → v12.
  - Sửa bug: `ModelServer._load_production_model` trước đây lấy **version cao nhất** thay vì version ở stage `Production` → rollback không có tác dụng. Nay ưu tiên `get_current_model_version()`, fallback latest khi không có Production (test: `tests/test_model_serving_stage.py`).
- [x] **C3** Drift (PSI/KS) nối vào DAG: `infra/airflow/dags/qlk_ingest/tasks.py::detect_drift` chạy sau `promote_demand_model`, emit outbox `topic="ml.drift.detected"`.
  - Bằng chứng: DagBag Airflow 2.11 parse `inventory_ingestion` 0 lỗi, tasks gồm `detect_drift` + `train_demand_model` + `promote_demand_model`.
- [x] **C4** `POST /api/v1/ml/forecast` (+ alias `/ml/forecast`): idempotency qua middleware toàn cục (`Idempotency-Key`), rate limit per-IP (429 + `Retry-After`), 503 envelope `MODEL_NOT_AVAILABLE`.
  - Bằng chứng: `tests/test_ml_forecast_api.py` 5 passed; gọi thật với model 13 → HTTP 200.
- [x] **C5** CreditFlow re-train + model card + gate: `python gate8a_model_quality.py` → **13/13 PASS** (recall 0.7, f1 0.5344, cost 0.3227), model card `CreditFlow/docs/model-card.md`, script `scripts/build_model_card.py`.
- [x] **C6** IncidentIQ DAGs chạy/parse local: DagBag (Airflow 2.10.4) → 0 import error.
  - `incidentiq_model_retrain_pipeline` (`0 3 * * 0`): build_dataset → submit_training → poll_training → verify_adapter.
  - `incidentiq_drift_monitor_dag` (`*/30 * * * *`): evaluate_drift → trigger_retrain.

## Track D — Agent

- [x] **D1** LangGraph SOP agent (`app/services/ai_agent.py`: classify → retrieve → decide → generate → format) trích dẫn nguồn, abstention khi thiếu căn cứ.
- [x] **D2** HITL gate: node quyết định trả `hitl_pending` cho hành động ghi; `POST /agent/hitl/{request_id}/decision` yêu cầu capability duyệt và trả `executed=False` (agent không tự ghi).
- [x] **D3** `llm-router`: local-first (LM Studio → Ollama → Cloudflare) — `pytest tests/test_routing.py tests/test_service.py` → **21 passed**.
- [x] **D4** Tool use GraphQL read-only (`app/services/agent_tools.py` + `app/api/routes/agent.py`):
  - Guard AST: chỉ `OperationType.QUERY`, whitelist root field, chặn `__schema`/`__type`/mutation/subscription, giới hạn 4000 ký tự / 40 field — kiểm tra **trước** khi executor chạy (fail-closed).
  - Tools: `service_health`, `account_balances`, `saga_status`, `outbox_events`, `audit_trail`.
  - `POST /agent/ask` (auth + 429 rate limit per-user), HITL duyệt/từ chối. Cùng handler còn phục vụ tại `POST /api/v1/agent/ask` qua mount `api_v1_router` (`main.py:320-322`).
  - Bằng chứng (chạy lại 2026-11-19): `pytest tests/test_agent_tools.py tests/test_agent_api.py` → **27 passed**; tập D4+ML với coverage → **48 passed, TOTAL 95%** (agent_tools 93%, ai_agent 97%, routes/agent 98%, routes/ml 92%, model_serving 91%). Full suite `pytest tests -q` chạy lại tại thời điểm cập nhật (xem log bên dưới).
- [x] **D5** Eval harness: `tests/test_ai_agent_eval.py` (golden dataset + heuristic judge + regression) — nằm trong 1345 test pass.

## Lệnh kiểm chứng (đã chạy)

```bash
cd QuanLyKho/backend
python -m pytest tests -q            # 1345 passed, 8 skipped, 1 xfailed (baseline từ lượt trước; chạy lại đang hoàn tất — xem /tmp/kilo/full_suite2.log)
python -m pytest tests/test_agent_tools.py tests/test_agent_api.py \
  tests/test_ai_agent.py tests/test_ml_forecast_api.py tests/test_model_serving_stage.py \
  --cov=app.services.agent_tools --cov=app.services.ai_agent \
  --cov=app.api.routes.agent --cov=app.api.routes.ml \
  --cov=app.services.model_serving   # 48 passed, TOTAL 95%
python -m pytest tests/test_graphql_schema.py -q   # 8 passed (A6 DataLoader batching + A7 smoke queries)

cd CreditFlow && python gate8a_model_quality.py   # 13/13 PASS
cd Enterprise-Document-Intelligence-Corrective-RAG-Platform/llm-router && pytest tests/test_routing.py tests/test_service.py -q  # 21 passed
```
Kết quả chạy lại (2026-11-19): D4+ML **48 passed, TOTAL 95%** (agent_tools 93%, ai_agent 97%, routes/agent 98%, routes/ml 92%, model_serving 91%); GraphQL schema **8 passed**. Full suite `pytest tests -q` đang chạy — thất bại hiện có chỉ ở các Test cần PostgreSQL local (Track A e2e, chưa liên quan D4); chi tiết: `/tmp/kilo/full_suite2.log`.

Airflow: DAG parse bằng `DagBag` trong venv tạm (2.10.4 / 2.11.0) — incidentiq + CreditFlow 0 import error;
QuanLyKho cần shim `async_sessionmaker` vì constraint Airflow pin SQLAlchemy 1.4 trong khi code dùng 2.0
(venv Airflow thật của deploy cần Python 3.12 + SQLAlchemy ≥2, hoặc nâng Airflow ≥3 / chạy qua Docker image hiện có).

## Rủi ro còn lại

- HITL pending store là dict in-process → không dùng được multi-worker (cần Redis/DB nếu scale >1 worker).
- MLflow `transition_model_version_stage` đã deprecated (2.9+) — sẽ phải chuyển sang aliases trước khi bỏ stages.
- `/api/v1/ml/forecast` chưa yêu cầu auth (rate limit per-IP) — nếu public cần thêm API key/JWT.
- A6/A7/A8 chưa làm (xem trên); A8 cần quyết định sản phẩm trước.
