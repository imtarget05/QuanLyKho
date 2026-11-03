# BRIEFING — 2026-11-02T21:05:00Z

## Mission
Backend review and adversarial challenge of Milestone 5 changes (email validation, demo reset, test suites, exports, gsheets sync, admin notifications).

## 🔒 My Identity
- Archetype: reviewer
- Roles: reviewer, critic
- Working directory: /Users/mainguyenbinhtan/Downloads/QuanLyKho/.agents/teamwork/reviewer_m5_2/
- Original parent: c779b1bc-b9ef-4b3f-bb7a-160f56263325
- Milestone: milestone_5
- Instance: 1 of 1

## 🔒 Key Constraints
- Review-only — do NOT modify implementation code
- Check for integrity violations (hardcoded test results, facade implementations, bypassed tasks, fabricated outputs)
- Run independent verification commands using poetry/pytest/ruff
- Follow 5-component handoff report protocol

## Current Parent
- Conversation ID: c779b1bc-b9ef-4b3f-bb7a-160f56263325
- Updated: 2026-11-02T20:55:05Z

## Review Scope
- **Files to review**:
  - `backend/app/services/email_service.py`
  - `backend/app/reset_demo_db.py`
  - `backend/tests/test_e2e_exports_multiformat.py`
  - `backend/tests/test_e2e_gsheets_sync.py`
  - `backend/tests/test_e2e_admin_notification_sync.py`
  - `backend/tests/test_admin_user_role_notification.py`
  - `backend/tests/test_exports_multiformat.py`
  - `backend/tests/test_google_sheets_sync.py`
- **Interface contracts**: `/Users/mainguyenbinhtan/Downloads/QuanLyKho/PROJECT.md`, `/Users/mainguyenbinhtan/Downloads/QuanLyKho/.agents/teamwork/ORIGINAL_REQUEST.md`
- **Review criteria**: correctness, style, test integrity, adversarial robustness, database invariants

## Key Decisions Made
- Executed `poetry run ruff check app/ tests/` -> 0 errors.
- Executed pytest 91 tests suite -> Initially 90 passed, 1 failed due to stale test location from `test_milk_tea_rbac_uat.py` causing 404 on `demo_maker`.
- Verified and ran `reset_demo_db.py` with `APP_ENV=demo DEMO_MODE=true` -> successfully cleaned cascading FK records and re-seeded demo catalog.
- Re-executed full 91 tests suite -> 91/91 PASSED in 63.57s.
- Audited implementation code for integrity violations -> CLEAN. Genuine logic, zero facade/shortcuts.
- Verdict: APPROVE with 3 advisory findings (1 Medium test isolation, 2 Minor operational polish).

## Artifact Index
- DISPATCH.md — incoming dispatch instructions
- progress.md — liveness heartbeat and subtask progress
- BRIEFING.md — persistent working memory
- handoff.md — final review verdict and 5-component report

## Review Checklist
- **Items reviewed**: `email_service.py`, `reset_demo_db.py`, `export_engine.py`, `google_sheets_service.py`, `exports.py`, `etl.py`, `admin_users.py`, and 6 test suites
- **Verdict**: APPROVE
- **Unverified claims**: none

## Attack Surface
- **Hypotheses tested**:
  - Foreign key cascade deletions in reset_demo_db: Verified.
  - Multi-branch location isolation causing test failure when DB accumulates test rows: Confirmed and reproduced.
  - Email dot injection / malformed email validation: Verified.
  - SMTP timeout / failure error resilience in DB transaction: Verified.
  - CSV single BOM and CWE-1236 formula neutralization: Verified.
- **Vulnerabilities found**:
  - 1 Medium: Test `test_cross_feature_receipt_movement_to_export_reconciliation` relies on `locs[0]` from admin query instead of maker-scoped locations.
  - 1 Minor: `is_valid_email` does not check `val.endswith(".")`.
  - 1 Minor: `reset_demo_db.py` requires `APP_ENV=demo DEMO_MODE=true` to bypass production guard.
- **Untested angles**: Full scale production SMTP load (mocked in tests).
