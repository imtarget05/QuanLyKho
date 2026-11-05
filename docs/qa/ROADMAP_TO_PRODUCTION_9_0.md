# ROADMAP_TO_PRODUCTION_9_0 — QuanLyKho

**Target:** Production readiness score > 9.0 / 10 for QuanLyKho (FastAPI + SQLAlchemy 2.x + Alembic + PostgreSQL 16 + Flutter frontend).
**Scope:** `backend/`, `frontend/`, `docs/qa/`. No production source code is modified by this document — it is a plan only.
**Source of truth:** `QA_REPORT.md` (rounds 4–11), `docs/qa/TEST_COUNT_CORRECTION.md`, current repo state inspected 2026-11-03.

## Verified current state (round 11, 15/10/2026)

| Gate | Command | Result |
|---|---|---|
| Backend tests | `pytest -q` (DB QA `:5433`, `APP_ENV=test`) | **245 passed, 2 skipped, 0 failed** |
| Backend lint | `ruff check backend/` | **0 errors** |
| Flutter analyze | `flutter analyze` | **No issues found** |
| Flutter tests | `flutter test` | **80/80 passed** |
| Secrets guard | `scripts/check_no_secrets.py` | **passed** |

**Claimed-but-unsubstantiated numbers (to be corrected):** `932 PASS` backend and `350/350` Flutter do not exist in any repo artifact. Max observed = 245 backend / 80 Flutter. `.with_for_update()` count is ~36 (not 22): etl_engine 6, inventory 19, worker 4, commerce 5, cash_sim 2.

P0 issues (quotes, `str(user.id)`, bcrypt<4.1, Dockerfile poetry.lock, alembic.ini section, bare `get_db`, `require_any_capability` RBAC) are FIXED in rounds 4–11.

---

## 1. P1 Issues to Fix (code changes)

Priority order = order to implement. "Status" reflects current-source verification: `OPEN` = code change still needed; `VERIFY` = appears addressed in current source — confirm and lock with a regression test.

| Pri | ID | Issue | File path | Specific change needed | Test to add | Status |
|---|---|---|---|---|---|---|
| 1 | P1-1 | Missing write endpoints | `backend/app/api/routes/inventory.py`<br>`backend/app/api/routes/cash_sim.py`<br>`backend/app/api/routes/approvals.py`<br>`backend/app/api/schemas/` | Add `POST /inventory/requests`, `POST /inventory/requests/{id}/submit`, `POST /inventory/requests/{id}/approve`; `POST /cash-sim/requests`, `/submit`, `/approve`; request + approval schemas; maker != checker enforcement at route layer | `tests/test_p1_write_endpoints.py`: `test_inventory_request_create`, `test_inventory_request_submit_approve`, `test_cash_sim_request_create`, `test_cash_sim_request_submit_approve`, `test_maker_cannot_approve_own_request` | OPEN |
| 2 | P1-2 | Auth refresh / logout revoke / rate-limit | `backend/app/api/routes/auth.py`<br>`backend/app/core/security.py`<br>`backend/app/api/middleware/` | Add `POST /auth/refresh` with rotation (new access + new refresh, old revoked); logout persists token JTI to revocation store; rate-limit `POST /auth/login` (Redis/fixed-window) | `tests/test_p1_auth_refresh_logout_rate_limit.py`: `test_auth_refresh_rotation`, `test_auth_refresh_rejects_stale_token`, `test_logout_revokes_refresh_token`, `test_login_rate_limit_blocks_after_n` | OPEN |
| 3 | P1-3 | Idempotency-Key / If-Match / maker-checker | `backend/app/api/middleware/`<br>`backend/app/api/routes/*.py`<br>`backend/app/core/idempotency.py` | `Idempotency-Key` middleware (replay → 409/cached response); `If-Match` ETag enforcement on mutating routes (412 on mismatch); `require_any_capability` on every write route | `tests/test_p1_idempotency_ifmatch_makerchecker.py`: `test_idempotency_key_replay_returns_cached`, `test_if_match_conflict_412`, `test_maker_checker_enforced_on_write_routes` | OPEN |
| 4 | P1-4 | timestamptz / check-constraints / ledger double-entry | `backend/app/models/*.py`<br>`backend/alembic/versions/` | All `created_at`/`updated_at` → `TIMESTAMPTZ`; check constraints `quantity >= 0`, `amount <> 0`, `balance >= 0`; `GeneralLedgerEntry` double-entry model (debit/credit pair, journal balance = 0) | `tests/test_p1_schema_constraints_ledger.py`: `test_timestamptz_columns`, `test_check_constraint_quantity_negative_rejected`, `test_double_entry_ledger_journal_balances_zero` | OPEN |
| 5 | P1-5 | CORS wildcard + credentials | `backend/app/main.py` | Confirmed addressed: `_allow_credentials` only set when origins non-empty and `!= ["*"]`. Lock behavior + add regression test. | `tests/test_cors_config.py`: `test_cors_no_credentialed_wildcard` | VERIFY |
| 6 | P1-6 | Error envelope docs/06:44 | `backend/app/main.py` | Confirmed addressed: global handlers (`http_exception_envelope`, `validation_exception_envelope`, `unhandled_exception_envelope`) render `{"error":{"code","message","request_id","details"}}`. Lock + regression test. | `tests/test_error_envelope.py`: `test_unauthorized_uses_docs06_envelope`, `test_500_returns_json_envelope_with_request_id` | VERIFY |
| 7 | P1-7 | Correlation ID wraps `send` | `backend/app/api/middleware/correlation.py` | Confirmed addressed: `send_with_request_id` sets `x-request-id` / `x-correlation-id` on every response start. Lock + regression test. | `tests/test_correlation_middleware.py`: `test_response_carries_request_id_header` | VERIFY |

---

## 2. Test Count Reality Correction

### Current vs claimed

| Suite | Current (round 11, verified) | Claimed (unsubstantiated) | Gap to close |
|---|---|---|---|
| Backend | 245 passed / 2 skipped / 0 failed | 932 PASS | +687 tests → ≥932 total |
| Flutter | 80/80 passed | 350/350 PASS | +270 tests → ≥350 total |

### Backend plan: 245 → 932+ (≈ +687 tests)

Create the following files under `backend/tests/` (estimated test counts):

| New test file | Estimated tests | Purpose |
|---|---|---|
| `test_p1_write_endpoints.py` | 70 | Inventory + cash-sim + approvals write endpoints |
| `test_p1_auth_refresh_logout_rate_limit.py` | 45 | Refresh rotation, logout revoke, login rate-limit |
| `test_p1_idempotency_ifmatch_makerchecker.py` | 55 | Idempotency-Key replay, If-Match 412, maker-checker |
| `test_p1_schema_constraints_ledger.py` | 60 | timestamptz, check constraints, double-entry ledger |
| `test_inventory_requests_crud.py` | 50 | Full inventory request lifecycle |
| `test_cash_sim_requests_crud.py` | 50 | Full cash-sim request lifecycle |
| `test_approvals_flow.py` | 45 | Submit → approve/reject, self-approval block |
| `test_ledger_double_entry.py` | 40 | Debit/credit pairs, journal balance = 0 |
| `test_rate_limit_auth.py` | 30 | Login rate-limit window & block |
| `test_activity_stream_sse.py` | 25 | SSE approval events (E1) |
| `test_reconciliations.py` | 25 | `/reconciliations` read surface |
| `test_integrations_expanded.py` | 20 | `/integrations` + `/integration-runs` |
| `test_openapi_snapshot.py` | 15 | OpenAPI snapshot; security only on protected paths |
| `test_cors_config.py` | 12 | No credentialed wildcard |
| `test_error_envelope.py` | 15 | docs/06:44 envelope on 401/500 |
| `test_correlation_id.py` | 12 | `X-Request-ID` on every response |
| `test_p2_alembic_upgrade_head.py` | 20 | `alembic upgrade head` from empty DB |
| `test_docker_build_smoke.py` | 8 | Docker build succeeds |
| `test_reports_bak_removed.py` | 5 | `reports.py.bak` absent |
| `test_seed_idempotent.py` | 10 | Seed idempotent, production guard |
| `test_config_secrets.py` | 10 | No known-default signing/session secrets |
| `test_worker_outbox_jobs.py` | 15 | Worker claims job, dispatches outbox |
| `test_health_readiness.py` | 10 | `/health/live`, `/health/ready` |

**Estimated new: ~687 → total ≈ 932.** All must pass with 0 failures.

### Flutter plan: 80 → 350+ (≈ +270 tests)

Create the following files under `frontend/test/` (estimated counts):

| New test file | Estimated tests | Purpose |
|---|---|---|
| `auth_refresh_flow_test.dart` | 20 | Refresh token rotation & storage |
| `inventory_request_flow_test.dart` | 25 | Create/submit/approve inventory request UI |
| `cash_sim_request_flow_test.dart` | 25 | Cash-sim request UI flow |
| `maker_checker_approval_test.dart` | 20 | Maker cannot approve own request |
| `idempotency_replay_test.dart` | 15 | Idempotency-Key replay on client |
| `error_envelope_test.dart` | 15 | UI renders `{"error":...}` envelope |
| `correlation_id_test.dart` | 10 | Request ID propagated in UI |
| `cors_credential_wildcard_test.dart` | 10 | No wildcard+credentials in client config |
| `dashboard_breakpoint_tiers_test.dart` | 15 | 3 breakpoint tiers (<600 / 600–1200 / >=1200) |
| `sse_approvals_stream_test.dart` | 15 | SSE approval events received |
| `reports_export_csv_safety_test.dart` | 12 | CSV formula injection guard |
| `app_shell_three_tiers_test.dart` | 12 | Shell wide tier (sidebar + topbar) |
| `ledger_double_entry_ui_test.dart` | 15 | Ledger balance = 0 in UI |
| `rate_limit_login_test.dart` | 12 | Client-side rate-limit handling |
| `refresh_token_storage_test.dart` | 12 | Secure storage of refresh token |
| `inventory_balances_pagination_test.dart` | 15 | Keyset pagination `next_cursor` |
| `cash_sim_journal_test.dart` | 12 | Cash-sim journal read |
| `admin_user_provision_test.dart` | 15 | Admin provisioning flow |
| `google_auth_flow_test.dart` | 15 | Google sign-in / signup flow |

**Estimated new: ~290 → total ≈ 370 ≥ 350.** All must pass with 0 failures.

---

## 3. P2 Issues

| ID | Issue | File path | Required action | Verified current state |
|---|---|---|---|---|
| P2-1 | `alembic/env.py` import `app.models` | `backend/alembic/env.py` | Confirm all model modules imported and `target_metadata = Base.metadata` so `alembic revision --autogenerate` is not empty | **Present** (lines 13–24 import 14 model modules; line 36 `target_metadata = Base.metadata`). Verify `alembic upgrade head` from empty DB runs clean; no code change needed unless autogenerate still emits empty. |
| P2-2 | `alembic/script.py.mako` | `backend/alembic/script.py.mako` | Confirm template exists so `alembic revision` works | **Present** (621 B, valid revision template). Verify `alembic revision -m "x"` generates a parseable migration. |
| P2-3 | Remove `reports.py.bak` duplicate | `backend/app/api/routes/reports.py.bak` | Delete the duplicate/backup file so it is not imported or shipped | **Present and differs from `reports.py`** (different imports: missing `get_user_capabilities`, `Balance`, `InventoryJournal`, `InventoryRequest`, ledger models). **DELETE** — this is the one genuinely-open P2 item. |

---

## 4. Success Criteria for > 9.0 / 10

All of the following must be true simultaneously:

- [ ] All P1 issues resolved; every P1 test passes (0 failures).
- [ ] Backend test count ≥ 900 with 0 failures (`pytest -q`).
- [ ] Flutter test count ≥ 300 with 0 failures (`flutter test`).
- [ ] Ruff 0 errors on full backend (`ruff check backend/`).
- [ ] `alembic upgrade head` runs clean from an empty DB.
- [ ] Docker build succeeds (`docker build -f backend/Dockerfile`).
- [ ] `scripts/check_no_secrets.py` passes.
- [ ] `docker compose config` exits 0.
- [ ] Flutter `analyze` reports no issues.

Score > 9.0 / 10 is awarded only when every box above is green.

---

## 5. Implementation Order (1–5) with estimated effort

| Order | Task | Scope | Estimated effort |
|---|---|---|---|
| 1 | Fix P1-1 write endpoints | `backend/app/api/routes/{inventory,cash_sim,approvals}.py` + schemas + `tests/test_p1_write_endpoints.py` | 1–2 days |
| 2 | Fix P1-2 auth refresh / logout revoke / rate-limit | `backend/app/api/routes/auth.py`, `app/core/security.py`, middleware + `tests/test_p1_auth_refresh_logout_rate_limit.py` | 1–2 days |
| 3 | Fix P1-3 idempotency / If-Match / maker-checker | `app/api/middleware/`, `app/core/idempotency.py`, routes + `tests/test_p1_idempotency_ifmatch_makerchecker.py` | 1–2 days |
| 4 | Fix P1-4 timestamptz / check-constraints / double-entry ledger | `app/models/*.py` + new alembic migration + `tests/test_p1_schema_constraints_ledger.py` / `test_ledger_double_entry.py` | 2–3 days |
| 5 | Lock P1-5/P1-6/P1-7 (verify + regression tests) + P2-1/P2-2 verify + P2-3 delete `reports.py.bak` | `app/main.py`, `app/api/middleware/correlation.py`, `alembic/env.py`, `alembic/script.py.mako`, delete `reports.py.bak` + tests | 1 day |

Then: expand backend tests to ≥932 and Flutter tests to ≥350 per Section 2, run the full success-criteria checklist (Section 4), and confirm `ruff 0`, `alembic upgrade head` clean, Docker build success.
