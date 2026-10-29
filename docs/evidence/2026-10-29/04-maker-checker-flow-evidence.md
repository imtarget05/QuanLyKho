# Maker-Checker Flow Evidence — QuanLyKho

| Field | Value |
|-------|-------|
| **Task** | P3.7 — Python Evaluation Harvest: maker-checker flow evidence |
| **Commit SHA** | `9f877c2ad25ee5639c7a96b3c69037b2f40ff63c` (HEAD at packaging) |
| **Command** | `grep -R "approve\|maker\|checker\|four.eyes\|dual approval" backend/app backend/tests frontend/lib/src frontend/test docs` |
| **Output** | Maker-checker / four-eyes approval flows implemented across backend API, services, models, tests, and Flutter UI |
| **Status** | VERIFIED |

## Implementation surface

| Layer | File | Role |
|-------|------|------|
| API routes | `backend/app/api/routes/approvals.py` | Approval endpoints (submit/approve/reject) |
| API routes | `backend/app/api/routes/auth_utils.py` | `require_capability` guard |
| Models | `backend/app/models/approval.py` | Approval domain model |
| Services | `backend/app/services/approval_controls.py` | Approval control logic |
| Services | `backend/app/services/approval_events.py` | Approval events (SSE) |
| Tests | `backend/tests/test_approval_controls.py` | Approval control tests |
| Tests | `backend/tests/test_approval_controls_service.py` | Service-level approval tests |
| Tests | `backend/tests/test_approval_events_redis.py` | Redis-backed approval events |
| Tests | `backend/tests/test_approval_events_service.py` | Approval events service |
| Tests | `backend/tests/test_sse_approvals.py` | SSE approval streaming |
| Tests | `backend/tests/test_etl_self_approval.py` | ETL self-approval |
| Tests | `backend/tests/test_portfolio_ai_checker_demo.py` | AI checker demo |
| Tests | `backend/tests/test_b2_authorization_scope.py` | B2 authorization scope |
| Flutter UI | `frontend/lib/src/features/approvals/approvals_screen.dart` | Approvals screen |
| Flutter UI | `frontend/lib/src/core/util/approval_pdf.dart` | Approval PDF |
| Flutter test | `frontend/test/approvals_role_visibility_test.dart` | Role visibility |
| Flutter test | `frontend/test/bulk_approve_test.dart` | Bulk approve flow |
| Doc | `docs/17-b2-authorization-scope-audit.md` | B2 authorization scope audit |

## Eval mapping

- `business_logic.maker_checker` — PASS (17 pts), evidence: `QA_REPORT.md`, `backend/app/api/routes/approvals.py`, `backend/app/models/approval.py`, + 15 more files.
- `flows.approval_flows` — PASS (20 pts), evidence: `QA_REPORT.md`, `backend/app/api/routes/approvals.py`, `backend/app/models/approval.py`, + Flutter UI/tests.

## Known gap

`require_capability` is defined but **no route calls it** yet → RBAC not enforced on protected routes (`QA_REPORT.md` P1 #7, `test_capability_checks_are_enforced_on_protected_routes` ❌). Tracked in `docs/13-backlog.md`; does not invalidate the maker-checker surface that exists and is tested.
