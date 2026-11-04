# Kho Trà Sữa verification checkpoint — 2026-11-03

**Checkout:** `9175190` plus pre-existing uncommitted work. **Environment:** isolated Docker PostgreSQL/Redis test project, local Flutter SDK and web build. **Production verdict:** NOT ACCEPTED. No UAT on a physical device, released web build with live API data, or cloud deployment at this checkout was supplied.

## Frozen MVP denominator

The 2026-10-26 acceptance baseline contains 23 QLK IDs. `QLK-ALERT-PUSH` is explicitly after MVP; `QLK-OFFLINE-WEB` awaits a scope decision. The remaining **21 IDs** are the fixed MVP denominator. `PASS` requires the acceptance behavior, relevant backend/Flutter and permission evidence, plus UAT when the ID requires it. A related unit test alone is local support, not end-to-end acceptance. No BankOps module enters this denominator.

| ID | Current status | Local evidence and outstanding acceptance |
|---|---|---|
| QLK-CATALOG | OPEN | Catalog tests exist; Min/Max per warehouse and web UAT need proof. |
| QLK-RECEIPT | OPEN | Receipt/lot journey test; full field validation and released API/UI UAT remain. |
| QLK-APPROVAL | OPEN | Maker/checker and idempotency tests; concurrency/retry on release remain. |
| QLK-FEFO | OPEN | Outbound lot test; expired-lot and single-movement release proof remain. |
| QLK-SHIFT-OPEN | OPEN | Shift regression tests; three-shift real-day UAT remains. |
| QLK-SHIFT-COUNT | OPEN | Stocktake tests; multi-item movement reconciliation and UI UAT remain. |
| QLK-SHIFT-HANDOFF | OPEN | Full-cycle test includes afternoon; third shift and two-person handoff remain. |
| QLK-SHIFT-LOCK | OPEN | Lock and adjustment draft tests; approved movement on release remains. |
| QLK-DAMAGE | OPEN | Local spoilage test covers reason, approval and balance; device/report UAT remains. |
| QLK-ADJUST | OPEN | Adjustment path exists; locked-shift request → checker → one movement needs full proof. |
| QLK-ALERT-LOW | OPEN | API test; UI threshold and management event UAT remain. |
| QLK-ALERT-EXPIRY | OPEN | API test; boundary dates and released UI remain. |
| QLK-ALERT-VARIANCE | OPEN | Server variance/adjustment tests; explicit recount/confirmation UI remains. |
| QLK-ALERT-STREAM | OPEN | General SSE endpoint; alert event, reconnect and role proof remain. |
| QLK-REPORT-XNT | OPEN | Report tests; date filters and movement totals on released UI remain. |
| QLK-REPORT-TOP | OPEN | API test; ranking against ledger and released UI remain. |
| QLK-REPORT-HISTORY | OPEN | API test; three shifts, operator/timestamp and auditor UAT remain. |
| QLK-RBAC | OPEN | Cross-branch API tests; full role/action matrix with real accounts remains. |
| QLK-AUDIT | OPEN | Idempotency/outbox tests; fault-injected rollback across all writes remains. |
| QLK-OFFLINE-NATIVE | OPEN | Durable retry/restart Flutter tests; kill/reopen/network UAT on device remains. |
| QLK-PLATFORMS | OPEN | Widget tests and web build; mobile/tablet/web live-API journey remains. |

**MVP acceptance: 0/21 PASS.** This strict result does not mean the code is absent: many paths have local regression coverage. It means the user-facing acceptance conditions at this SHA have not been demonstrated. Owners: repo engineering for local gaps; product owner for offline-web scope; QA/business owner for device and released-cloud UAT.

## Fresh gate output

| Gate | Result |
|---|---|
| `make test-backend` (isolated project; empty DB migrated through `034_general_ledger_coa`) | First run: 946 passed, 1 failed, 8 skipped, 1 xfailed in 869.61s; failure: `test_rate_limiter_uses_redis_backend_when_configured`. Repeat full run: **947 passed, 8 skipped, 1 xfailed, 0 failed** in 1096.06s ([retained log](evidence/2026-11-03/full-backend-pytest.log)). The first failure did not reproduce; its order/timing cause remains OPEN. |
| `make analyze-backend` | PASS after selecting the repo's `backend/.venv` Ruff; zero findings. |
| `flutter test --no-pub` | **355 passed, 0 failed** again after mounted-guard edits (03:59; [retained log](evidence/2026-11-03/full-flutter-test.log)); 11 focused commerce tests also passed. |
| `flutter analyze --no-pub` | No issues after 94 mechanical Dart fixes and mounted guards. |
| `flutter build web --release --no-tree-shake-icons` | PASS; WASM dry-run warnings are nonblocking. |
| `npm run typecheck` (worker), `scripts/check_no_secrets.py`, `docker compose config --quiet` | PASS. |

The earlier `QA_REPORT.md` 245 backend/80 Flutter numbers are from 2026-10-15. The migration `034_general_ledger_coa.py` is untracked and must be included in a reviewed release; a local migration run alone does not prove deployability. Keep the first-run Redis test failure visible until its cause is isolated; the passing repeat is evidence of current suite behavior, not a regression fix.

## Claim traceability

Eight priority claims from the attached reports were checked against the current checkout. **Seven have direct code or command evidence; one is inconclusive**: historical 245/80 test counts (`QA_REPORT.md`, fresh gate output); migration head 034 (`backend/alembic/versions/`, isolated migrate); clean Ruff (`make analyze-backend`); Flutter analysis (`flutter analyze`); native offline restart (`frontend/test/stocktake_outbox_test.dart`); branch-scoped RBAC (`backend/tests/test_b2_authorization_scope.py`); outbox/worker implementation (`backend/app/services/kafka_publisher.py`, relevant tests). The eighth, cloud/device acceptance, lacks current release/UAT evidence in the baseline and remains **INCONCLUSIVE**, not disproven. **Selected-claim direct evidence: 7/8 = 87.5%.** The full attachment claim denominator has not been frozen, so a claim-wide >90% verdict is **not established**. Production acceptance remains 0/21.

## Production gate

OPEN/BLOCKED: intermittent Redis rate-limiter test diagnosis; completed 21-ID journey matrix; two-account branch/role UAT; physical mobile/tablet offline drill; released web + live API journey; cloud rollout/rollback evidence; signed business/security acceptance. Historical health 200, widget tests and old cloud G4 do not close these gates.
