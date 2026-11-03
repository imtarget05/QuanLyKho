# Quality Review & Adversarial Verification Report: Milestone 3 & Final Integration

**Reviewer / Critic:** `reviewer_m3_2`  
**Date:** 2026-11-03T03:16:00Z  
**Type:** Hard Handoff  
**Workspace:** `/Users/mainguyenbinhtan/Downloads/QuanLyKho`  
**Verdict:** **APPROVE**  
**Overall Risk Assessment:** **LOW**

---

## 1. Observation

All source files, database invariants, and test suites were independently inspected and executed against the live local environment:
- Database: `postgresql+psycopg2://bankops:bankops@127.0.0.1:5432/bankops_test` (PostgreSQL 16)
- Python environment: `/Users/mainguyenbinhtan/Downloads/QuanLyKho/backend/.venv` (Python 3.11.15, pytest-8.4.2)
- Flutter environment: Flutter 3.27.7, Dart 3.6.1

### 1.1. Backend Transactional Safety & Auth Invariants
In `backend/app/api/routes/admin_users.py` (`PUT /admin/users/{user_id}/roles`):
1. **Self-Escalation & Self-Demotion Guards** (Lines 624–632):
   ```python
   if current_user.id == user.id:
       if after - before:
           raise AppError(403, "CANNOT_ESCALATE_SELF", "Không thể tự cấp thêm vai trò cho chính mình.")
       retained_caps = set((await db.execute(
           select(RoleCapability.capability_code).where(RoleCapability.role_code.in_(after))
       )).scalars().all())
       if not retained_caps.intersection(_ADMIN_CAPS):
           raise AppError(400, "CANNOT_DEMOTE_SELF", "Quản trị viên không thể tự gỡ vai trò admin của chính mình.")
   ```
2. **Session Invalidation** (Line 642):
   ```python
   user.auth_version = getattr(user, "auth_version", 1) + 1
   ```
3. **Outbox & Audit Trail** (Lines 644–656):
   - Emits `IAM_USER_ROLES_UPDATED` audit record with metadata `{"new_roles": cleaned_roles}`.
   - Emits OutboxEvent `user.roles_updated` with payload `{"username": user.username, "roles": cleaned_roles}`.
4. **Transaction Commit Precedence** (Lines 663–664):
   ```python
   await db.commit()
   await db.refresh(user)
   ```
   The database transaction commits **strictly prior** to triggering email dispatch.
5. **Non-Blocking Email Dispatch** (Lines 686–706):
   Email delivery is wrapped in a `try...except Exception as exc: logger.warning(...)` guard so that SMTP network timeouts or socket disconnects cannot cause an unhandled 500 error or rollback the persisted role changes in PostgreSQL.

### 1.2. Frontend AdminPromotionBanner Lifecycle & Mobile Parity
In `frontend/lib/src/core/widgets/admin_promotion_banner.dart`:
1. **Multi-Tap Latch Guard** (`_hasTriggered`):
   - Defined as `bool _hasTriggered = false;` (Line 40).
   - In `_startTimer()` (Lines 62–64):
     ```dart
     if (_hasTriggered) return;
     _hasTriggered = true;
     timer.cancel();
     _countdownTimer = null;
     widget.onRefresh();
     ```
   - In `_handleRefresh()` (Lines 98–104):
     ```dart
     void _handleRefresh() {
       if (_hasTriggered) return;
       _hasTriggered = true;
       _countdownTimer?.cancel();
       _countdownTimer = null;
       widget.onRefresh();
     }
     ```
   - In `_handleDismiss()` (Lines 106–114):
     ```dart
     void _handleDismiss() {
       if (_hasTriggered) return;
       _hasTriggered = true;
       _countdownTimer?.cancel();
       _countdownTimer = null;
       widget.onDismiss?.call();
     }
     ```
2. **320px Mobile Screen Parity & Responsive Layout**:
   In `build()` (Lines 150–232):
   - Detects compact screens via `constraints.maxWidth < 500 || screenWidth < 500`.
   - Uses `Wrap` layout with `spacing: 8` and `runSpacing: 8` for action buttons (Lines 220–232), allowing the dismiss and refresh buttons to wrap cleanly without `RenderFlex` overflow on narrow viewports (320px, 280px).
3. **Draft Form Pause Safety**:
   - `pauseCountdown: true` freezes the countdown without resetting elapsed seconds.
   - Verified in `didUpdateWidget` (Lines 79–89) and widget tests.
4. **Timer Leak Elimination**:
   - Cleanly calls `_countdownTimer?.cancel(); _countdownTimer = null;` in `dispose()` (Lines 91–96).

### 1.3. Independent Test Execution Results

#### Backend Test Suite 1: `test_admin_user_role_notification.py`
- Command:
  ```bash
  cd backend && DATABASE_URL="postgresql+psycopg2://bankops:bankops@127.0.0.1:5432/bankops_test" \
  .venv/bin/python -m pytest tests/test_admin_user_role_notification.py -v
  ```
- Result: **11 passed, 3 warnings in 13.58s** (Exit code `0`).

#### Backend Test Suite 2: `test_admin_role_email_notification.py` & `test_e2e_admin_notification_sync.py`
- Command:
  ```bash
  cd backend && DATABASE_URL="postgresql+psycopg2://bankops:bankops@127.0.0.1:5432/bankops_test" \
  .venv/bin/python -m pytest tests/test_admin_role_email_notification.py tests/test_e2e_admin_notification_sync.py -v
  ```
- Result: **14 passed, 3 warnings in 44.07s** (Exit code `0`).
- **Total Backend Targeted Tests**: **25 passed out of 25 (100% PASS)**.

#### Backend Linter Check: `ruff check backend/app`
- Command:
  ```bash
  ruff check backend/app
  ```
- Result: **All checks passed! (0 errors, 0 warnings)** (Exit code `0`).

#### Frontend Widget & Adversarial Banner Suites:
- Command:
  ```bash
  cd frontend && flutter test \
    test/admin_promotion_banner_test.dart \
    test/admin_promotion_banner_adversarial_test.dart \
    test/admin_promotion_banner_challenger_m3_2_test.dart \
    test/admin_promotion_banner_m3_stress_test.dart
  ```
- Result: **40 passed, 0 failed in 00:02** (Exit code `0`).

#### Full Frontend Test Suite:
- Command:
  ```bash
  cd frontend && flutter test --no-pub
  ```
- Result: **350 passed, 0 failed in 00:48** (Exit code `0`).

---

## 2. Logic Chain

1. **Transactional Safety Invariant**:
   - Observation 1.1 proves that `await db.commit()` occurs on line 663 of `admin_users.py`, before any call to `send_admin_role_granted_email` at line 689.
   - Observation 1.3 confirms via `test_database_resilience_when_email_raises_exception` that when email delivery raises an unhandled `RuntimeError("SMTP connection timed out")`, the HTTP endpoint returns 200 OK and subsequent queries confirm the admin role update is permanently recorded in PostgreSQL.
   - Therefore, transactional safety is completely sound and decoupled from external network/SMTP failures.

2. **Session Revocation Invariant**:
   - Observation 1.1 proves that `user.auth_version` is incremented on line 642 of `admin_users.py`.
   - Observation 1.3 confirms via `test_old_token_revoked_with_401_after_role_change` that any JWT token issued prior to the role change is immediately rejected with HTTP 401 Unauthorized across all protected endpoints (`/auth/me`).
   - Therefore, privilege changes take immediate effect across active sessions.

3. **Frontend Concurrency & Responsive Integrity**:
   - Observation 1.2 demonstrates that `_hasTriggered` locks `onRefresh()` against multiple invocations.
   - In Observation 1.3, stress test suites (`admin_promotion_banner_adversarial_test.dart`, `admin_promotion_banner_challenger_m3_2_test.dart`, and `admin_promotion_banner_m3_stress_test.dart`) subjected the widget to 50 rapid taps, rapid unmount/remount cycles, and simultaneous timer completion. In all cases, `onRefresh()` fired exactly once, with zero timer leaks.
   - Observation 1.2 demonstrates that action buttons use `Wrap` with `spacing: 8, runSpacing: 8` on compact viewports (<500px).
   - In Observation 1.3, adversarial tests across 320px and 280px screens with up to 1.5x text scaling produced zero `RenderFlex` overflows.
   - Observation 1.3 confirms the entire frontend test suite (350/350 tests) passes cleanly.

4. **Integrity & Anti-Cheating Verification**:
   - No mock shortcuts, hardcoded user IDs, or dummy facades exist in `admin_users.py`, `email_service.py`, or `admin_promotion_banner.dart`.
   - Tests execute real database transactions, verify cryptographic auth version checking, test HTML XSS sanitization, and manipulate simulated widget clocks.
   - Zero integrity violations were detected.

---

## 3. Findings

### Minor Finding 1: Unused import in scratch challenger test file
- **What**: `import pytest` is imported but unused.
- **Where**: `backend/tests/test_challenger_m3_2_empirical.py:21:8`.
- **Why**: Triggers a ruff F401 lint warning if running `ruff check backend/` across untracked challenger files (while `backend/app/` is completely clean).
- **Suggestion**: Remove `import pytest` from `backend/tests/test_challenger_m3_2_empirical.py`.

### Minor Finding 2: Missing route assertion in challenger test file
- **What**: `test_challenger_m3_2_empirical.py:315` asserts `client.get("/auth/profile").status_code == 401`, returning 404.
- **Where**: `backend/tests/test_challenger_m3_2_empirical.py:315`.
- **Why**: `/auth/profile` is not a registered endpoint in the API (user profile is at `/auth/me`).
- **Suggestion**: Update endpoint path to `/auth/me` in the challenger test.

*(Note: Neither minor finding affects production source code in `backend/app/` or `frontend/lib/`).*

---

## 4. Stress Test Results

| Challenge Scenario | Expected Behavior | Actual Behavior | Verdict |
|---|---|---|---|
| **Rapid Multi-Tap (50 clicks on [Làm mới ngay])** | Callback fires exactly once; timer cancelled | `refreshCount == 1`, no duplicate API calls | **PASS** |
| **Simultaneous Timer Expiry + User Tap Race** | Single execution via `_hasTriggered` latch | `refreshCount == 1`, no unhandled state crash | **PASS** |
| **320px & 280px Viewport + TextScaler 1.5x** | Action buttons wrap cleanly to next line | Zero RenderFlex overflow (`takeException() == null`) | **PASS** |
| **Draft Form Active (`pauseCountdown: true`)** | Timer freezes indefinitely without reset | Timer paused; resumes accurately when unpaused | **PASS** |
| **Unmount during active countdown (50 cycles)** | Timer cleanly cancelled in `dispose()` | 0 orphaned timers, 0 exceptions | **PASS** |
| **SMTP Network Timeout / Disconnect on Role Change** | DB commits successfully; API returns 200 OK | DB role updated, API returns 200 OK | **PASS** |
| **Old Token Revocation on `auth_version` Bump** | Immediate HTTP 401 Unauthorized on `/auth/me` | HTTP 401 returned; new login succeeds | **PASS** |

---

## 5. Caveats

- **Persistent Dev DB Accumulation**: Running `pytest backend/tests/` without executing `python -m app.reset_demo_db` experiences 7 legacy failures due to accumulated rows in `inv_balances` and demo user state in `bankops_test`, a known repository condition documented in `QuanLyKho/AGENTS.md § 7`. All 25 targeted test suites for Milestone 3 pass 100%.

---

## 6. Conclusion

The work products for Milestone 3 & Final Integration (backend transactional safety, email notification, token invalidation via `auth_version`, and frontend `AdminPromotionBanner` with `_hasTriggered` latch and `Wrap` responsive layout) meet and exceed all requirements. No integrity violations or cheating patterns exist.

**Final Verdict**: **APPROVE**

---

## 7. Verification Method

To independently verify this report, execute:

```bash
# 1. Backend Targeted Notification & Resilience Test Suites (25 tests)
cd /Users/mainguyenbinhtan/Downloads/QuanLyKho/backend
DATABASE_URL="postgresql+psycopg2://bankops:bankops@127.0.0.1:5432/bankops_test" \
.venv/bin/python -m pytest \
  tests/test_admin_user_role_notification.py \
  tests/test_admin_role_email_notification.py \
  tests/test_e2e_admin_notification_sync.py \
  -v

# 2. Production Source Code Hygiene
cd /Users/mainguyenbinhtan/Downloads/QuanLyKho
ruff check backend/app/

# 3. Frontend AdminPromotionBanner Widget & Adversarial Suites (40 tests)
cd /Users/mainguyenbinhtan/Downloads/QuanLyKho/frontend
flutter test \
  test/admin_promotion_banner_test.dart \
  test/admin_promotion_banner_adversarial_test.dart \
  test/admin_promotion_banner_challenger_m3_2_test.dart \
  test/admin_promotion_banner_m3_stress_test.dart

# 4. Full Frontend Test Suite (350 tests)
cd /Users/mainguyenbinhtan/Downloads/QuanLyKho/frontend
flutter test --no-pub
```
