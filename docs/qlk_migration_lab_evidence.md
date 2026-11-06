# QLK Migration Lab Evidence — codex/qlk-migration-lab

**Branch:** `codex/qlk-migration-lab` (from `main` @ 6f18714)  
**Commit:** `feat(qlk): migration lab 001-034 backup restore rollback evidence`  
**Signed-off-by:** Kilo <kilo@kilo.ai>  
**Status:** PARTIAL — migration lab core verified; full backend suite is flaky (see below)

## 1. make test-backend (recorded result)

Command: `make test-backend` (docker-compose.test.yml postgres:16 on 5433, DB `bankops_test`, alembic upgrade head → seed → pytest)

**Result: FLAKY / HANGS — does not reach a clean full-suite pass.**
- Alembic `upgrade head` (001→034) on empty DB: OK.
- Seed: OK.
- pytest: hangs at varying points across runs (≈21% non-verbose; ≈7% on `test_database_resilience_when_both_emails_raise`; ≈30% on `test_regular_to_admin_promotion_triggers_exactly_once` after `test_challenger_m1_2_empirical`/`test_challenger_m3_2_empirical` FAILED).
- `test_challenger_m1_2_empirical.py` (40 cases) passes alone in ~85s → hang is order/state-dependent, **not deterministic**.

Raw output: `/tmp/qlk_test_backend_full.log`, `/tmp/pytest_verbose2.log`, `/tmp/adv.log`.

## 2. Redis test error investigation

- Reproduced: yes (suite hangs / challenger failures), but **not a Redis outage**.
- Root cause: challenger test-suite state pollution / test-ordering dependency in `tests/test_challenger_*.py` (shared `demo_admin` state, email-mock interactions, auth_version), not Redis.
- `redis_url` defaults to `""` in test env (`app/config.py:116`); `test_redis_rate_limit.py` and `test_approval_events_redis.py` use mocks, no real Redis connection. `docker-compose.test.yml` runs only postgres (no Redis).
- Did **not** skip flaky runs; recorded them.

## 3. make analyze-backend (lint)

Command: `backend/.venv/bin/python -m ruff check backend/ ai/` (ruff 0.17.2)  
**Result: PASS — `All checks passed!` (0 warnings).** Raw: `/tmp/ruff2.log`.

## 4. Migration 001→034 on empty DB

Target DB: `qlk_migration_demo` on `quanlykho-test-postgres-test-1` (postgres:16, 127.0.0.1:5433)

| Step | `alembic_version` before | `alembic_version` after |
|------|--------------------------|-------------------------|
| Empty DB → `alembic upgrade head` | (table absent) | `034_general_ledger_coa (head)` |
| Snapshot 033 → `alembic upgrade head` | `033_inventory_ledger` | `034_general_ledger_coa (head)` |

Migration 001→034 applies cleanly on an empty DB. Gap noted: no `023` migration file (022 → 024). Raw alembic logs captured in session output.

## 5. Backup / restore / rollback from snapshot

- Backup taken at snapshot version `033_inventory_ledger`: `pg_dump -U bankops -d qlk_migration_demo --no-owner` → `/tmp/qlk_migration_evidence/backup_at_033.sql` (94,618 bytes).
- DB upgraded 033 → 034 (`034_general_ledger_coa`).
- Rollback via restore: dropped + recreated `qlk_migration_demo`, restored `backup_at_033.sql`.
- Version after restore: `033_inventory_ledger` — **rollback to snapshot confirmed.**
- Raw restore log: `/tmp/restore_033.log` (all CREATE TABLE / COPY / ALTER TABLE / CREATE INDEX applied).

## 6. Negative cases added per docs/QA_PLAN.md

New file: `backend/tests/test_migration_lab_negatives.py` (3 tests, modeled on `test_business_journey_full.py`)

| QA_PLAN ID | Case | Expected | Result |
|------------|------|----------|--------|
| R02 | Receipt with past expiry | 422 EXPIRED_LOT | PASS |
| F03 | Issue exceeding available stock | 409 INSUFFICIENT_STOCK (at submit) | PASS |
| S05 | Maker self-approves own request | 403 SELF_APPROVAL_FORBIDDEN | PASS |

Verified in isolation on a clean seeded `bankops_test`: **3 passed**. (`INVALID_CONVERSION_RATE` skipped — field not exposed in current schemas; not applicable.)

## 7. Status

**PARTIAL.** Migration lab core (migration 001→034, snapshot upgrade 033→034, backup/restore/rollback, lint, QA_PLAN negative cases) is fully demonstrated and verified. `make test-backend` result recorded but the full suite does not complete cleanly (flaky challenger-test hang), so a fully-green backend suite cannot be claimed.

**Does NOT claim cloud acceptance** — needs cloud DB + UAT accounts + real devices (per constraint `no_azure_production_mutations`; kind-local only).
