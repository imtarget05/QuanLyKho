# Dispatch Assignment: worker_fix_1

- Role: Remediation Worker (teamwork_worker)
- Working Directory: /Users/mainguyenbinhtan/Downloads/QuanLyKho/.agents/teamwork/worker_fix_1/
- Original Request: /Users/mainguyenbinhtan/Downloads/QuanLyKho/.agents/teamwork/ORIGINAL_REQUEST.md
- Scope Document: /Users/mainguyenbinhtan/Downloads/QuanLyKho/PROJECT.md
- Explorer Handoff: /Users/mainguyenbinhtan/Downloads/QuanLyKho/.agents/teamwork/explorer_fix_1/handoff.md

## MANDATORY INTEGRITY WARNING
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

## Tasks to Execute:
Follow the exact instructions from `explorer_fix_1/handoff.md`:
1. **File 1 (`backend/tests/test_acceptance_qa.py`)**:
   Verify and fix lines 6–12 to ensure proper sorted import order:
   ```python
   from __future__ import annotations

   import uuid
   from decimal import Decimal

   import pytest
   ```
2. **File 2 (`backend/tests/test_adversarial_m1_challenger.py`)**:
   In `test_promoted_user_receives_capabilities_at_auth_me` (around line 438), re-authenticate `admin_auth` before the role update call:
   ```python
   # Ensure fresh admin credentials with current auth_version
   admin_auth = _login(client, "demo_admin")
   pr = client.put(
       f"/admin/users/{user_id}/roles",
       headers=_idem(admin_auth),
       json={"roles": ["admin"]},
   )
   assert pr.status_code == 200
   ```
   Ensure `test_promote_to_root_admin_triggers_email` uses isolated `root_actor_{uuid}` setup so it does not mutate `demo_admin`.
3. **File 3 (`backend/tests/test_challenger_m1_2_empirical.py`)**:
   In `test_non_admin_role_permutations_never_trigger_admin_email` (around line 126), replace `"cashier"` with valid catalog role `"auditor"`:
   ```python
   # staff -> auditor
   r1 = client.put(
       f"/admin/users/{user_id}/roles",
       headers=_idem(admin_auth),
       json={"roles": ["auditor"]},
   )
   assert r1.status_code == 200, r1.text
   assert "admin" not in r1.json()["user"]["roles"]
   mock_email.assert_not_called()
   ```
4. **Verification Commands**:
   - `ruff check backend/` (must exit 0 with "All checks passed!")
   - `cd backend && DATABASE_URL="postgresql+psycopg2://bankops:bankops@127.0.0.1:5432/bankops_test" .venv/bin/python -m pytest tests/test_adversarial_m1_challenger.py tests/test_challenger_m1_2_empirical.py -v` (must pass 100%)
   - `cd backend && DATABASE_URL="postgresql+psycopg2://bankops:bankops@127.0.0.1:5432/bankops_test" .venv/bin/python -m pytest tests/test_admin_user_role_notification.py tests/test_admin_role_email_notification.py tests/test_e2e_admin_notification_sync.py -v` (must pass 25/25)
   - `cd frontend && flutter test test/admin_promotion_banner_test.dart` (must pass 8/8)
5. Document all executed commands, diffs, and results in `/Users/mainguyenbinhtan/Downloads/QuanLyKho/.agents/teamwork/worker_fix_1/handoff.md`.

## 2026-11-02T20:59:14Z
You are worker_fix_1.
Your working directory: /Users/mainguyenbinhtan/Downloads/QuanLyKho/.agents/teamwork/worker_fix_1/
Read:
- /Users/mainguyenbinhtan/Downloads/QuanLyKho/.agents/teamwork/ORIGINAL_REQUEST.md
- /Users/mainguyenbinhtan/Downloads/QuanLyKho/PROJECT.md
- /Users/mainguyenbinhtan/Downloads/QuanLyKho/.agents/teamwork/worker_fix_1/DISPATCH.md
- /Users/mainguyenbinhtan/Downloads/QuanLyKho/.agents/teamwork/explorer_fix_1/handoff.md

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

Your task:
1. Apply the fixes detailed in `explorer_fix_1/handoff.md`:
   - `backend/tests/test_acceptance_qa.py`: fix import order (import uuid before from decimal import Decimal).
   - `backend/tests/test_adversarial_m1_challenger.py`: re-authenticate `admin_auth` before the role update call in `test_promoted_user_receives_capabilities_at_auth_me`.
   - `backend/tests/test_challenger_m1_2_empirical.py`: replace role `"cashier"` with valid catalog role `"auditor"`.
2. Run the verification commands:
   - `ruff check backend/` (must pass 0 errors)
   - `cd backend && DATABASE_URL="postgresql+psycopg2://bankops:bankops@127.0.0.1:5432/bankops_test" .venv/bin/python -m pytest tests/test_adversarial_m1_challenger.py tests/test_challenger_m1_2_empirical.py -v`
   - `cd backend && DATABASE_URL="postgresql+psycopg2://bankops:bankops@127.0.0.1:5432/bankops_test" .venv/bin/python -m pytest tests/test_admin_user_role_notification.py tests/test_admin_role_email_notification.py tests/test_e2e_admin_notification_sync.py -v`
   - `cd frontend && flutter test test/admin_promotion_banner_test.dart`
3. Write your report to `/Users/mainguyenbinhtan/Downloads/QuanLyKho/.agents/teamwork/worker_fix_1/handoff.md`.
4. Send a message to your orchestrator when done.

