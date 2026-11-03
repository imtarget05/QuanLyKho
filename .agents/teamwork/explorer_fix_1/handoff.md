# Handoff Report — Victory Audit Failure Root Cause & Remediation Guide

**Agent**: `explorer_fix_1`  
**Mission**: Investigate the 3 specific issues causing Victory Audit Rejection in `victory_auditor_1/handoff.md`, provide root cause analysis and concrete line-by-line fix instructions for the Worker.  
**Target Repository**: `/Users/mainguyenbinhtan/Downloads/QuanLyKho`  
**Date**: 2026-11-03  

---

## 1. Observation

### Issue 1: `ruff check backend/` import order violation (`backend/tests/test_acceptance_qa.py:6:1`)
- **Direct Output from Victory Audit:**
  ```text
  backend/tests/test_acceptance_qa.py:6:1: I001 [*] Import block is un-sorted or un-formatted
  Found 1 error.
  [*] 1 fixable with the `--fix` option.
  ```
- **Code Inspection (`backend/tests/test_acceptance_qa.py` lines 6–11):**
  Previously in the test file, `from decimal import Decimal` was placed before `import uuid` or out of isort block separation:
  ```python
  from __future__ import annotations

  from decimal import Decimal
  import uuid
  ```
- **Linter Rule Inspection (`backend/pyproject.toml` lines 86–105):**
  Ruff is configured with `select = ["E", "F", "I", "UP", "B", "C4"]`. The `I` rule family enforces `isort` import ordering rules (specifically `I001: Import block is un-sorted or un-formatted`), which requires standard library `import <module>` to precede `from <module> import <symbol>`.
- **Current File State:**
  ```python
  from __future__ import annotations

  import uuid
  from decimal import Decimal

  import pytest
  ```
- **Verification Command & Output:**
  ```bash
  cd /Users/mainguyenbinhtan/Downloads/QuanLyKho && ruff check backend/
  ```
  Output: `All checks passed!` (Exit code 0).

---

### Issue 2: `AssertionError: assert 401 == 200 on PUT /admin/users/{user_id}/roles` (`tests/test_adversarial_m1_challenger.py:428`)
- **Direct Output from Victory Audit:**
  ```text
  FAILED tests/test_adversarial_m1_challenger.py::TestAdversarialM1Challenger::test_promoted_user_receives_capabilities_at_auth_me - AssertionError: assert 401 == 200
  Lines in test_adversarial_m1_challenger.py:
  pr = client.put(f"/admin/users/{user_id}/roles", headers=_idem(admin_auth), json={"roles": ["admin"]})
  assert pr.status_code == 200
  ```
- **Code Inspection (`backend/app/api/routes/auth_utils.py` lines 491–498):**
  ```python
  # Enforce immediate session revocation via auth_version
  token_auth_version = payload.get("auth_version")
  if token_auth_version is not None and getattr(user, "auth_version", 1) != token_auth_version:
      raise HTTPException(
          status_code=status.HTTP_401_UNAUTHORIZED,
          detail="Phiên đăng nhập đã bị thu hồi.",
          headers={"WWW-Authenticate": "Bearer"},
      )
  ```
- **Cross-Test Contamination Analysis:**
  1. In `backend/tests/test_root_role_assignment.py` lines 42–62, the `root_admin_auth` fixture logs in as `demo_admin`, executes `user.auth_version += 1`, and upon test teardown (`finally:`), executes `user.auth_version += 1` again.
  2. In `backend/tests/test_adversarial_m1_challenger.py` lines 314–360, an earlier iteration of `test_promote_to_root_admin_triggers_email` modified `demo_admin`'s roles and bumped `auth_version`.
  3. In `test_promoted_user_receives_capabilities_at_auth_me` (lines 409–444):
     `admin_auth = _login(client, "demo_admin")` was called at the start of the test. An employee user was created, and `_login(client, username, login_pass)` was executed. When `client.put(f"/admin/users/{user_id}/roles", headers=_idem(admin_auth))` was executed, if `demo_admin.auth_version` in the database had been incremented by other tests or prior steps, the JWT held in `admin_auth` contained a stale `auth_version`, failing with HTTP 401 (`"Phiên đăng nhập đã bị thu hồi."`).
- **Remediation Inspection (`backend/tests/test_adversarial_m1_challenger.py`):**
  - In `test_promote_to_root_admin_triggers_email`, create an isolated ephemeral root user (`root_actor_{uuid}`) instead of mutating `demo_admin`.
  - In `test_promoted_user_receives_capabilities_at_auth_me`, re-acquire or refresh `admin_auth = _login(client, "demo_admin")` right before performing the role update to guarantee a valid `auth_version`.
- **Verification Command & Output:**
  ```bash
  cd /Users/mainguyenbinhtan/Downloads/QuanLyKho/backend && DATABASE_URL="postgresql+asyncpg://bankops:bankops@localhost:5432/bankops_test" poetry run pytest tests/test_adversarial_m1_challenger.py -v
  ```
  Output: `40 passed, 3 warnings in 69.29s` (Exit code 0).

---

### Issue 3: `AssertionError: assert 422 == 200 (role "cashier" does not exist in roles catalog)` (`tests/test_challenger_m1_2_empirical.py:126`)
- **Direct Output from Victory Audit:**
  ```text
  FAILED tests/test_challenger_m1_2_empirical.py::TestChallengerM12Empirical::test_non_admin_role_permutations_never_trigger_admin_email - AssertionError: assert 422 == 200
  Response was 422: {"error":{"code":"INVALID_ROLES","message":"Một hoặc nhiều vai trò không hợp lệ: cashier."}}
  ```
- **Code Inspection (`backend/app/api/routes/admin_users.py` lines 616–628):**
  ```python
  valid_roles_res = await db.execute(select(Role.code))
  valid_codes = set(valid_roles_res.scalars().all())
  invalid = requested - valid_codes
  if invalid:
      raise HTTPException(
          status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
          detail={
              "code": "INVALID_ROLES",
              "message": f"Một hoặc nhiều vai trò không hợp lệ: {', '.join(sorted(invalid))}.",
          },
      )
  ```
- **Database Catalog Verification (`iam_roles` table in `bankops_test`):**
  Existing roles in the catalog are:
  - `admin` (Quản trị viên)
  - `approver` (Người phê duyệt)
  - `auditor` (Kiểm toán viên)
  - `cash_sim_operator` (Vận hành quỹ)
  - `integration_admin` (Quản trị tích hợp)
  - `inventory_manager` (Quản lý kho)
  - `root_admin` (Quản trị cấp cao nhất)
  - `staff` (Nhân viên)
  - `system_admin` (Quản trị hệ thống)
  
  The role `cashier` does NOT exist in the role catalog.
- **Code Inspection (`backend/tests/test_challenger_m1_2_empirical.py` lines 124–134):**
  In `test_non_admin_role_permutations_never_trigger_admin_email`, the test author tested role permutations that should not trigger admin email notification. Line 129 originally passed `{"roles": ["cashier"]}`.
  Changing `"cashier"` to `"auditor"` (or `"approver"`, `"staff"`) tests valid non-admin roles without violating role catalog constraints.
- **Verification Command & Output:**
  ```bash
  cd /Users/mainguyenbinhtan/Downloads/QuanLyKho/backend && DATABASE_URL="postgresql+asyncpg://bankops:bankops@localhost:5432/bankops_test" poetry run pytest tests/test_challenger_m1_2_empirical.py -v
  ```
  Output: `9 passed, 3 warnings in 43.10s` (Exit code 0).

---

## 2. Logic Chain

1. **Gate `ruff check backend/`**:
   - `ruff` enforces rule `I001` via `backend/pyproject.toml`.
   - The test file `backend/tests/test_acceptance_qa.py` introduced `from decimal import Decimal` before `import uuid`.
   - By sorting the imports into standard order (`import uuid` followed by `from decimal import Decimal`), `ruff check backend/` completes with 0 errors.

2. **Test `test_adversarial_m1_challenger.py` 401 error**:
   - BankOps implements single session / session revocation via `iam_users.auth_version`.
   - `get_current_user` in `auth_utils.py` compares `payload.get("auth_version")` with `user.auth_version`. If they do not match, it returns HTTP 401 `UNAUTHORIZED`.
   - When multiple tests run sequentially or concurrently against the shared test database (`bankops_test`), any test that alters `demo_admin` (like `root_admin_auth` fixture or tests bumping `demo_admin.auth_version`) invalidates any token previously issued to `demo_admin`.
   - `test_promoted_user_receives_capabilities_at_auth_me` re-used an initial `admin_auth` token after performing employee login and operations. By ensuring `admin_auth` is re-authenticated or freshly obtained before admin operations, and ensuring helper tests use ephemeral actors (`root_actor_{uuid}`) rather than mutating `demo_admin`, all 40 tests pass consistently.

3. **Test `test_challenger_m1_2_empirical.py` 422 error**:
   - Endpoint `PUT /admin/users/{user_id}/roles` queries `iam_roles` and strictly validates all requested role strings against existing role codes in the database.
   - If any requested role is not in `iam_roles`, it returns HTTP 422 with `{"code": "INVALID_ROLES", ...}`.
   - The test was written with `roles: ["cashier"]`, but `cashier` is not a registered role in the system. The standard non-admin roles are `staff`, `auditor`, `approver`, `inventory_manager`, `cash_sim_operator`.
   - Replacing `"cashier"` with `"auditor"` adheres to the system's role catalog while fully executing the test's intention (verifying non-admin roles never trigger admin promotion emails).

---

## 3. Caveats

- **Database Credentials**: Commands executing pytest against `bankops_test` must provide the correct database URL: `DATABASE_URL="postgresql+asyncpg://bankops:bankops@localhost:5432/bankops_test"`. Running without `_test` in the database name will be blocked by `pytest_sessionstart` in `backend/tests/conftest.py`.
- **Shared Test DB State**: If test suites are executed in parallel without process-level DB isolation, tests mutating `demo_admin` can intermittently invalidate tokens for other tests running simultaneously. Isolating test fixtures to create ephemeral users (`f"user_{uuid.uuid4().hex[:8]}"`) is recommended best practice across all test files.

---

## 4. Conclusion & Concrete Instructions for Worker

The Worker should verify and apply the following line-by-line checks/modifications:

### File 1: `backend/tests/test_acceptance_qa.py`
Verify lines 6–12 match the following sorted import structure:
```python
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
```

### File 2: `backend/tests/test_adversarial_m1_challenger.py`
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
Also ensure `test_promote_to_root_admin_triggers_email` uses the isolated `root_actor_{uuid}` setup (lines 319–360) so it does not mutate `demo_admin`.

### File 3: `backend/tests/test_challenger_m1_2_empirical.py`
In `test_non_admin_role_permutations_never_trigger_admin_email` (around line 126), replace `"cashier"` with `"auditor"`:
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

---

## 5. Verification Method

Run the following three commands in sequence. All must exit with code 0:

1. **Ruff lint check:**
   ```bash
   cd /Users/mainguyenbinhtan/Downloads/QuanLyKho && ruff check backend/
   ```
   *Expected Result*: `All checks passed!`

2. **Adversarial challenger test suite:**
   ```bash
   cd /Users/mainguyenbinhtan/Downloads/QuanLyKho/backend && \
   DATABASE_URL="postgresql+asyncpg://bankops:bankops@localhost:5432/bankops_test" \
   poetry run pytest tests/test_adversarial_m1_challenger.py -v
   ```
   *Expected Result*: `40 passed in ~69s` (Exit code 0).

3. **Empirical challenger test suite:**
   ```bash
   cd /Users/mainguyenbinhtan/Downloads/QuanLyKho/backend && \
   DATABASE_URL="postgresql+asyncpg://bankops:bankops@localhost:5432/bankops_test" \
   poetry run pytest tests/test_challenger_m1_2_empirical.py -v
   ```
   *Expected Result*: `9 passed in ~43s` (Exit code 0).

4. **Acceptance QA test suite:**
   ```bash
   cd /Users/mainguyenbinhtan/Downloads/QuanLyKho/backend && \
   DATABASE_URL="postgresql+asyncpg://bankops:bankops@localhost:5432/bankops_test" \
   poetry run pytest tests/test_acceptance_qa.py -v
   ```
   *Expected Result*: `20 passed in ~9s` (Exit code 0).
