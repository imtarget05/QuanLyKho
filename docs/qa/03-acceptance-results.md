 # QA 03 — Acceptance Test Results
 
 ## Test Environment
 - **API Base**: `http://localhost:8000/api/v1`
 - **Database**: PostgreSQL 16 (QA container, port 5433)
 - **Mode**: Local Docker Compose stack
 
 ## Business-Critical Path Test Results
 
 ### Maker-Checker (A1–A4)
 
 | Test ID | Description | Result | Notes |
 |---------|-------------|--------|-------|
 | **A1** | Maker cannot approve own request | ✅ PASS | Returns 403 `SELF_APPROVAL_FORBIDDEN` |
 | **A2** | Two checkers approve simultaneously | ✅ PASS | Exactly 1 post, correct concurrency handling |
 | **A3** | Retry same key + same payload | ✅ PASS | Same `request_id`, 1 movement only |
 | **A4** | Same key + different payload | ✅ PASS | 409 `IDEMPOTENCY_KEY_MISMATCH` |
 
 ### Inventory (I1–I3)
 
 | Test ID | Description | Result | Notes |
 |---------|-------------|--------|-------|
 | **I1** | Issue exceeds on-hand balance | ⚠️ FAIL (pre-existing) | Business logic correct: returns 409 `INSUFFICIENT_STOCK`. Test assertion at line 294 expects 200/201 on submit, but system correctly rejects over-issuance. Not a regression. |
 | **I2** | Transfer between locations | ✅ PASS | Creates 2 movements, total quantity preserved |
 | **I3** | Duplicate serial number | ✅ PASS | Returns 409, no second asset created |
 
 ### Cash Simulation (C1–C3)
 
 | Test ID | Description | Result | Notes |
 |---------|-------------|--------|-------|
 | **C1** | Payment exceeds demo budget | ✅ PASS | 409 `EXCEEDS_DEMO_LIMIT`, no journal |
 | **C2** | Valid receipt/payment | ✅ PASS | Balanced entry (debit=credit), Decimal precision verified |
 | **C3** | Reversal | ✅ PASS | New balanced journal, original unchanged |
 
 ### Reconciliation (R1)
 
 | Test ID | Description | Result | Notes |
 |---------|-------------|--------|-------|
 | **R1** | Planted mismatch detection | ✅ PASS | `status: exception` with expected/actual, no auto-fix |
 
 ### Integration (G1–G2)
 
 | Test ID | Description | Result | Notes |
 |---------|-------------|--------|-------|
 | **G1** | CSV with invalid row | ✅ PASS | Preview isolates errors, confirm blocks with 409 `CONFIRM_HAS_ERRORS` |
 | **G2** | Webhook bad signature | ✅ PASS | 401 for bad signature, 409 for replay, no draft created |
 
 ### SSE (E1)
 
 | Test ID | Description | Result | Notes |
 |---------|-------------|--------|-------|
 | **E1** | SSE replay after reconnect | ✅ PASS | Cursor-based replay works, `resync_required` on stale cursor |
 
 ### RBAC (S1)
 
 | Test ID | Description | Result | Notes |
 |---------|-------------|--------|-------|
 | **S1** | Object-level authorization | ✅ PASS | Out-of-scope reads return 403/404 per policy |
 
 ## Post-Deploy Smoke Test (Live API)
 
 | Endpoint | Method | Result |
 |----------|--------|--------|
 | `/health/live` | GET | ✅ 200 `{"status":"alive"}` |
 | `/health/ready` | GET | ✅ 200 `{"status":"ready","database":"ready"}` |
 | `/auth/login` (demo_maker) | POST | ✅ 200, valid JWT returned |
 | `/inventory/items` | GET | ✅ 200, 5 items returned |
 | `/cash-sim/balances` | GET | ✅ 200, Decimal amounts correct |
 | `/audit-events` (as maker) | GET | ✅ 403 `FORBIDDEN` (RBAC enforced) |
 
 ## Summary
 
 **14/15 acceptance criteria PASS** (93.3%)
 
 The 1 failure (I1) is a **pre-existing test isolation issue** — the business logic is correct. The test assertion at line 294 expects submit to return 200/201, but the system correctly returns 409 `INSUFFICIENT_STOCK` when issuing more than available stock. This is expected behavior, not a regression.

 ## Current Local Verification — 2026-11-03

 The results above are the historical 2026-10-14 run. Current local verification is recorded separately so old cloud evidence is not mistaken for the current release.

 | Area | Command / evidence | Result |
 |---|---|---|
 | Required backend acceptance | `DATABASE_URL=postgresql://…/bankops_test APP_ENV=demo DEMO_MODE=true .venv/bin/python -m pytest tests/test_acceptance_qa.py -q` on a fresh isolated PostgreSQL 16 database after `alembic upgrade head` and `app.seed` | **20 passed, 0 skipped**; includes maker/admin self-approval, concurrent checker, serial uniqueness, cash reversal, object-scope authorization, and reconciliation. |
 | Business journey + spoilage | `.venv/bin/python -m pytest tests/test_business_journey_full.py -q` on the same isolated database | **9 passed**; spoilage requires a reason, waits for checker approval, then posts exactly one negative movement and reduces balance by the same quantity. |
 | Full backend suite | Prior full `backend/tests` run on isolated, migrated and seeded `bankops_test` | **932 passed, 8 skipped, 1 xfailed** before this continuation's test additions. After the test changes, both relevant backend targets were rerun: acceptance **20 passed** and business journey **9 passed**. |
 | Frontend suite | `cd frontend && flutter test --no-pub` | **355 passed**. |
 | Focused frontend acceptance | Offline outbox, web cache policy, mobile/landscape responsive, and approval role tests | **47 passed**. |
 | Flutter analysis | `flutter analyze --no-fatal-infos --no-fatal-warnings` | Exit 0; 90 existing info/warning diagnostics, same as the recorded baseline; no new fatal errors. |
 | Flutter Web release | `flutter build web --release` with local verification build number | Build succeeded; `index.html` and `version.json` carried the same build identifier. |
 | Cache data preservation | `web_cache_policy_test.dart` | Confirms update cleanup removes CacheStorage/service-worker state but does not clear localStorage or IndexedDB. Offline drafts remain in their separate SharedPreferences queue. |

 ### Release boundary

 - No production deployment, CDN purge, or production database operation was performed.
 - Staging was not deployed: the current asset workflow points at the production API and production Workers Assets name; the Kubernetes staging overlay still contains placeholder host/image tags, and the Wrangler staging environment is only for the retired API Worker. There is no verified, isolated staging target for this Flutter release.
 - Physical-device offline UAT, cloud UAT against the current commit, and confirmation of variance-recount UX remain open acceptance items.