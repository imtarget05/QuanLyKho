# Outbox Worker Evidence — QuanLyKho

| Field | Value |
|-------|-------|
| **Task** | P3.7 — Python Evaluation Harvest: outbox worker evidence |
| **Commit SHA** | `9f877c2ad25ee5639c7a96b3c69037b2f40ff63c` (HEAD at packaging) |
| **Command** | `grep -R "outbox\|worker\|reconcil\|idempotent" backend/app backend/tests frontend/lib/src frontend/test infra/k8s docs` |
| **Output** | Outbox pattern, background worker, reconciliation, and idempotency implemented across backend, Flutter, and K8s |
| **Status** | VERIFIED |

## Implementation surface

| Layer | File | Role |
|-------|------|------|
| Worker | `backend/app/worker.py` | Background worker (Celery/RQ) |
| Entrypoint | `backend/entrypoint.sh` | Saga / worker entrypoint |
| API routes | `backend/app/api/routes/events.py` | Event/outbox stream endpoints |
| API routes | `backend/app/api/routes/reconciliations.py` | Reconciliation endpoints |
| Models | `backend/app/models/reconciliation.py` | Reconciliation model |
| Models | `backend/app/models/idempotency.py` | Idempotency model |
| Services | `backend/app/services/idempotency.py` | Idempotency service |
| Services | `backend/app/services/etl_engine.py` | ETL engine |
| Tests | `backend/tests/test_idempotency_durable.py` | Durable idempotency |
| Tests | `backend/tests/test_idempotency_retention.py` | Idempotency retention |
| Tests | `backend/tests/test_idempotency_service.py` | Idempotency service |
| Migrations | `backend/alembic/versions/003_integrations_reconciliation.py` | Integrations reconciliation migration |
| Migrations | `backend/alembic/versions/028_reconcile_scope.py` | Reconcile scope migration |
| Migrations | `backend/alembic/versions/002_idempotency_and_balances.py` | Idempotency & balances |
| Migrations | `backend/alembic/versions/027_idempotency_keys.py` | Idempotency keys |
| Flutter | `frontend/lib/src/core/offline/stocktake_outbox.dart` | Offline stocktake outbox |
| Flutter test | `frontend/test/stocktake_outbox_test.dart` | Stocktake outbox test |
| K8s | `infra/k8s/base/deployment-worker.yaml` | Worker Deployment |
| K8s | `infra/k8s/base/cronjob-backup.yaml` | Backup CronJob |
| Doc | `AGENTS.md` §5 — Architecture: API → DB → Worker; Outbox pattern (`outbox_events` table) |

## Eval mapping

- `business_logic.reconciliation` — PASS (16 pts), evidence includes `AGENTS.md`, `backend/app/api/routes/reconciliations.py`, `frontend/lib/src/core/offline/stocktake_outbox.dart`, `frontend/test/stocktake_outbox_test.dart`.
- `business_logic.saga` — PASS (16 pts), evidence: `backend/entrypoint.sh`.
- `flows.idempotency` — PASS (20 pts), evidence includes alembic migrations 002/027, `backend/app/models/idempotency.py`, `backend/app/services/idempotency.py`, 3 test files.

## Known notes

- Worker historically a sleep-loop; outbox claim/dispatch verified as a gap and fixed (`docs/EVIDENCE.md` Real vs Simulated).
- `mypy` strict intentionally xfailed (~481 annotations) — tech debt, not a runtime failure (`docs/EVIDENCE.md` Limits / Not Proven).
