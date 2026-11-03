# Dispatch Assignment: worker_m3_verify_1

- Target: Milestone 3 — Full Suite Backend & Frontend Verification, Ruff Checks
- Working Directory: /Users/mainguyenbinhtan/Downloads/QuanLyKho/.agents/teamwork/worker_m3_verify_1/
- Original Request: /Users/mainguyenbinhtan/Downloads/QuanLyKho/.agents/teamwork/ORIGINAL_REQUEST.md
- Scope Document: /Users/mainguyenbinhtan/Downloads/QuanLyKho/PROJECT.md

## MANDATORY INTEGRITY WARNING
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

## Tasks to execute:
1. Run backend unit & integration tests for admin role notification:
   `cd backend && DATABASE_URL="postgresql+psycopg2://bankops:bankops@127.0.0.1:5432/bankops_test" .venv/bin/python -m pytest tests/test_admin_user_role_notification.py -v`
2. Run full backend test suite:
   `cd backend && DATABASE_URL="postgresql+psycopg2://bankops:bankops@127.0.0.1:5432/bankops_test" .venv/bin/python -m pytest tests -q`
3. Run frontend widget tests for admin promotion banner:
   `cd frontend && flutter test test/admin_promotion_banner_test.dart`
4. Run full frontend test suite:
   `cd frontend && flutter test --no-pub`
5. Run ruff linter check:
   `ruff check backend/`
6. Document all execution commands, stdout/stderr outputs, test counts (passed/failed/skipped), and execution times in `handoff.md`.

## 2026-11-02T19:51:59Z
You are worker_m3_verify_1.
Your working directory: /Users/mainguyenbinhtan/Downloads/QuanLyKho/.agents/teamwork/worker_m3_verify_1/
Read /Users/mainguyenbinhtan/Downloads/QuanLyKho/.agents/teamwork/ORIGINAL_REQUEST.md and /Users/mainguyenbinhtan/Downloads/QuanLyKho/.agents/teamwork/worker_m3_verify_1/DISPATCH.md before starting.

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

Your task:
1. Run backend tests for admin role notification:
   `cd backend && DATABASE_URL="postgresql+psycopg2://bankops:bankops@127.0.0.1:5432/bankops_test" .venv/bin/python -m pytest tests/test_admin_user_role_notification.py -v`
2. Run full backend test suite:
   `cd backend && DATABASE_URL="postgresql+psycopg2://bankops:bankops@127.0.0.1:5432/bankops_test" .venv/bin/python -m pytest tests -q`
3. Run frontend widget tests for admin promotion banner:
   `cd frontend && flutter test test/admin_promotion_banner_test.dart`
4. Run full frontend test suite:
   `cd frontend && flutter test --no-pub`
5. Run ruff linter check:
   `ruff check backend/`
6. Write your comprehensive handoff report to `/Users/mainguyenbinhtan/Downloads/QuanLyKho/.agents/teamwork/worker_m3_verify_1/handoff.md` detailing all executed commands, exact test counts (passed/failed/skipped), test duration, and logs.
7. Send a message to your orchestrator when done.

