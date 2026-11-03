# Empirical Challenge Report: Milestone 3 / M5 Comprehensive Verification

**Agent:** `challenger_m3_2` (Empirical Challenger)  
**Date:** 2026-11-02T20:16:00Z  
**Type:** Hard Handoff  
**Workspace:** `/Users/mainguyenbinhtan/Downloads/QuanLyKho`  
**Verdict:** **APPROVE**

---

## 1. Observation

All stress tests, boundary conditions, and adversarial concurrency harnesses were constructed, executed, and validated independently against live services.

### 1.1. Backend Empirical Stress Harness (`backend/tests/test_challenger_m3_2_empirical.py`)

- **Target Files Tested**:
  - `backend/app/api/routes/admin_users.py` (Lines 600–707: `update_user_roles`, `is_newly_admin` state machine)
  - `backend/app/api/routes/auth_utils.py` (Lines 491–498: session revocation on `auth_version` mismatch)
  - `backend/app/api/routes/auth.py` (Lines 163, 200, 209, 300, 474–475: `auth_version` tracking)
  - `backend/app/services/email_service.py` (Lines 907–978: `send_admin_role_granted_email`)
- **Command Executed**:
  ```bash
  cd /Users/mainguyenbinhtan/Downloads/QuanLyKho/backend && \
  DATABASE_URL="postgresql+psycopg2://bankops:bankops@127.0.0.1:5432/bankops_test" \
  .venv/bin/python -m pytest tests/test_admin_user_role_notification.py \
    tests/test_admin_role_email_notification.py \
    tests/test_e2e_admin_notification_sync.py \
    tests/test_challenger_m3_2_empirical.py -v
  ```
- **Exit Code**: `0`
- **Duration**: `106.02s (0:01:46)`
- **Verbatim Output**:
  ```
  collecting ... collected 31 items
  tests/test_admin_user_role_notification.py::TestAdminRoleEmailTemplates::test_build_admin_role_granted_html_structure PASSED [  3%]
  tests/test_admin_user_role_notification.py::TestAdminRoleEmailTemplates::test_build_admin_role_granted_html_escapes_xss PASSED [  6%]
  tests/test_admin_user_role_notification.py::TestAdminRoleEmailTemplates::test_build_admin_role_granted_plain_structure PASSED [  9%]
  tests/test_admin_user_role_notification.py::TestSendAdminRoleGrantedEmailService::test_invalid_or_empty_email_returns_failed_result PASSED [ 12%]
  tests/test_admin_user_role_notification.py::TestSendAdminRoleGrantedEmailService::test_demo_mode_unconfigured_smtp_returns_clean_result PASSED [ 16%]
  tests/test_admin_user_role_notification.py::TestSendAdminRoleGrantedEmailService::test_configured_smtp_dispatches_successfully PASSED [ 19%]
  tests/test_admin_user_role_notification.py::TestAdminRoleNotificationIntegration::test_promote_user_to_admin_triggers_email PASSED [ 22%]
  tests/test_admin_user_role_notification.py::TestAdminRoleNotificationIntegration::test_database_resilience_when_email_raises_exception PASSED [ 25%]
  tests/test_admin_user_role_notification.py::TestAdminRoleNotificationIntegration::test_non_admin_role_update_does_not_trigger_email PASSED [ 29%]
  tests/test_admin_user_role_notification.py::TestAdminRoleNotificationIntegration::test_already_admin_role_update_does_not_retrigger_email PASSED [ 32%]
  tests/test_admin_user_role_notification.py::TestAdminRoleNotificationIntegration::test_promote_user_without_email_completes_safely PASSED [ 35%]
  tests/test_admin_role_email_notification.py::TestAdminRoleEmailNotification::test_role_update_enqueues_outbox_and_triggers_email PASSED [ 38%]
  tests/test_admin_role_email_notification.py::TestAdminRoleEmailNotification::test_database_resilience_when_email_fails PASSED [ 41%]
  tests/test_e2e_admin_notification_sync.py::TestAdminNotificationFeatureCoverage::test_admin_role_update_bumps_auth_version PASSED [ 45%]
  tests/test_e2e_admin_notification_sync.py::TestAdminNotificationFeatureCoverage::test_old_token_revoked_with_401_after_role_change PASSED [ 48%]
  tests/test_e2e_admin_notification_sync.py::TestAdminNotificationFeatureCoverage::test_outbox_event_emitted_in_same_transaction PASSED [ 51%]
  tests/test_e2e_admin_notification_sync.py::TestAdminNotificationFeatureCoverage::test_audit_event_logged_on_role_update PASSED [ 54%]
  tests/test_e2e_admin_notification_sync.py::TestAdminNotificationFeatureCoverage::test_email_notification_dispatch_mock PASSED [ 58%]
  tests/test_e2e_admin_notification_sync.py::TestAdminNotificationFeatureCoverage::test_email_dispatch_db_resilience_on_smtp_error PASSED [ 61%]
  tests/test_e2e_admin_notification_sync.py::TestAdminRoleBoundaryAndCornerCases::test_empty_roles_list_rejected_with_422 PASSED [ 64%]
  tests/test_e2e_admin_notification_sync.py::TestAdminRoleBoundaryAndCornerCases::test_invalid_role_code_rejected_with_422 PASSED [ 67%]
  tests/test_e2e_admin_notification_sync.py::TestAdminRoleBoundaryAndCornerCases::test_admin_cannot_self_escalate_or_strip_admin PASSED [ 70%]
  tests/test_e2e_admin_notification_sync.py::TestAdminRoleBoundaryAndCornerCases::test_non_admin_forbidden_from_role_update PASSED [ 74%]
  tests/test_e2e_admin_notification_sync.py::TestAdminRolePromotionCrossFeature::test_cross_feature_promotion_unlocks_new_admin_capabilities PASSED [ 77%]
  tests/test_e2e_admin_notification_sync.py::TestRealWorldPromotionWorkflow::test_real_world_store_supervisor_promotion_scenario PASSED [ 80%]
  tests/test_challenger_m3_2_empirical.py::TestRoleUpdatePermutationsAndEmailTriggers::test_non_admin_role_permutations_never_trigger_admin_email PASSED [ 83%]
  tests/test_challenger_m3_2_empirical.py::TestRoleUpdatePermutationsAndEmailTriggers::test_regular_to_admin_promotion_triggers_exactly_once PASSED [ 87%]
  tests/test_challenger_m3_2_empirical.py::TestRoleUpdatePermutationsAndEmailTriggers::test_user_without_email_promoted_to_admin_completes_without_error PASSED [ 90%]
  tests/test_challenger_m3_2_empirical.py::TestRoleUpdatePermutationsAndEmailTriggers::test_invalid_role_rejection PASSED [ 93%]
  tests/test_challenger_m3_2_empirical.py::TestTokenInvalidationOnAuthVersionMismatch::test_old_bearer_token_rejected_with_401_immediately_upon_role_update PASSED [ 96%]
  tests/test_challenger_m3_2_empirical.py::TestTokenInvalidationOnAuthVersionMismatch::test_rapid_sequential_role_updates_and_auth_version_progression PASSED [100%]
  ================== 31 passed, 3 warnings in 106.02s (0:01:46) ==================
  ```

### 1.2. Frontend Empirical Stress Harness (`frontend/test/admin_promotion_banner_challenger_m3_2_test.dart`)

- **Target Files Tested**:
  - `frontend/lib/src/core/widgets/admin_promotion_banner.dart` (Lines 37–115: `_AdminPromotionBannerState`, `_hasTriggered` latch, timer disposal, `Wrap` container)
  - `frontend/lib/src/features/auth/auth_service.dart` (Lines 1176–1314: `checkUserRoleUpdate`, 401 handling, capability elevation, watcher timer cancellation)
- **Command Executed**:
  ```bash
  cd /Users/mainguyenbinhtan/Downloads/QuanLyKho/frontend && \
  flutter test test/admin_promotion_banner_test.dart \
    test/admin_promotion_banner_adversarial_test.dart \
    test/admin_promotion_banner_challenger_m3_2_test.dart
  ```
- **Exit Code**: `0`
- **Duration**: `00:02`
- **Verbatim Output**:
  ```
  00:02 +32: All tests passed!
  ```
- **Individual Stress Test Results**:
  1. `Stress 1: Rapid 50x mount and immediate dispose without timer leak or unhandled exception` -> **PASSED**
  2. `Stress 2: Dispose banner mid-countdown at various seconds (0.5s, 1.2s, 3.7s)` -> **PASSED**
  3. `Stress 3: Rapid multi-tap race condition on [Làm mới ngay] executes onRefresh exactly once` -> **PASSED**
  4. `Stress 4: Rapid multi-tap race condition on [Để sau] executes onDismiss exactly once` -> **PASSED**
  5. `Stress 5: Edge condition: initialSeconds = 0 triggers onRefresh immediately without crash` -> **PASSED**
  6. `Stress 6: Pause and resume countdown state machine` -> **PASSED**
  7. `Empirical: 401 Unauthorized from GET /auth/me activates adminRolePromoted and capabilities` -> **PASSED**

### 1.3. Linter & Static Hygiene
- **Command Executed**:
  ```bash
  cd /Users/mainguyenbinhtan/Downloads/QuanLyKho && ruff check backend/tests/test_challenger_m3_2_empirical.py
  ```
- **Exit Code**: `0`
- **Verbatim Output**: `All checks passed!`

---

## 2. Logic Chain

1. **State Machine Verification for Role Permutations**:
   - In `test_challenger_m3_2_empirical.py`, user roles were systematically transitioned through permutations of valid non-admin IAM roles:
     `staff` -> `approver` -> `inventory_manager` -> `cash_sim_operator` -> `auditor` -> `integration_admin` -> multi-role combo -> back to `staff`.
   - Observation 1.1 confirms `mock_email.call_count == 0` throughout all 7 non-admin permutations.
   - When promoting from `staff` -> `admin`, `mock_email` was called with `call_count == 1`.
   - Modifying the existing admin's roles (`admin` -> `["admin", "approver"]` and `["admin", "approver"]` -> `["system_admin"]`) did NOT trigger additional emails (`call_count` remained 1).
   - Demoting (`system_admin` -> `staff`) did NOT trigger email (`call_count == 1`).
   - Re-promoting (`staff` -> `admin`) triggered the email notification again (`call_count == 2`).
   - Therefore, the `is_newly_admin = bool((after & ADMIN_ROLES) and not (before & ADMIN_ROLES))` state machine is mathematically and empirically sound.

2. **Session Invalidation via `auth_version` Invariant**:
   - In `test_old_bearer_token_rejected_with_401_immediately_upon_role_update`, an employee was created and authenticated with token `T1` (carrying `auth_version = 1`).
   - While `T1` was valid, `GET /auth/me` returned HTTP 200.
   - An administrator updated the user's roles via `PUT /admin/users/{user_id}/roles`, which committed an increment of `user.auth_version` to `2`.
   - Re-querying with token `T1` immediately resulted in HTTP 401 Unauthorized (`detail: "Phiên đăng nhập đã bị thu hồi."`) across both `/auth/me` and `/inventory/items`.
   - Issuing a fresh token `T2` after the update resulted in HTTP 200 and reflected the new capabilities.
   - In `test_rapid_sequential_role_updates_and_auth_version_progression`, successive role updates progressively bumped `auth_version` (1 -> 2 -> 3), invalidating all prior tokens.
   - Therefore, token revocation via `auth_version` operates immediately and deterministically across all protected routes.

3. **Frontend Lifecycle, Multi-Tap Safety, and Timer Leak Prevention**:
   - In `admin_promotion_banner_challenger_m3_2_test.dart`, Stress 1 subjected `AdminPromotionBanner` to 50 rapid sequential mount and unmount cycles; no unhandled timer exceptions or orphaned background tasks were detected.
   - In Stress 2, disposing the banner mid-countdown (at 0.5s, 1.2s, 3.7s) cancelled the internal `Timer.periodic`, ensuring `onRefresh` was never executed after unmount.
   - In Stress 3 & 4, 10 rapid taps delivered in a single animation frame on `[Làm mới ngay]` and `[Để sau]` resulted in exactly 1 invocation of `onRefresh` and `onDismiss`, respectively, proving the `_hasTriggered` boolean latch effectively prevents double-invocation races.
   - In Stress 6, pausing the countdown froze the remaining seconds for 10 seconds of simulated time, and unpausing resumed decrementing to 0 cleanly.
   - In the `AuthService` integration test, an HTTP 401 response from `GET /auth/me` triggered `adminRolePromoted = true`, populated `promotedUser` with administrative capabilities (`iam:admin`, `admin:user_management`), and notified listeners. Calling `applyAdminPromotionAndRefresh()` successfully promoted the local user session, reset the banner flag, and notified listeners. Disposing `AuthService` stopped the periodic watcher without leaks.

4. **Resolution of Prior Challenger Test Mismatches**:
   - The test failures previously observed in `test_challenger_m1_2_empirical.py` (`422 INVALID_ROLES`) were caused by the test attempting to assign `cashier`, which does not exist in the QuanLyKho IAM role catalog (`admin`, `staff`, `approver`, `inventory_manager`, `cash_sim_operator`, `integration_admin`, `auditor`, `system_admin`, `root_admin`).
   - The new test suite `test_challenger_m3_2_empirical.py` operates strictly against canonical IAM catalog roles, proving that all intended role transitions function correctly and that non-existent roles are properly rejected with HTTP 422.

---

## 3. Caveats

- **Test Database Balance Accumulation**: Running `pytest tests/` across legacy suites that rely on hardcoded initial balance numbers (such as `test_acceptance_qa.py`) requires running `python -m app.reset_demo_db` to clear accumulated balance rows from `bankops_test`, as documented in `AGENTS.md § 7`. All target suites for Milestone 1, 2, and 3 pass 100% without dependencies on balance state.
- **Demo SMTP Server**: In local development environments, SMTP dispatch operates in mock or demo mode (`EmailSendResult(False, "Chưa cấu hình tài khoản SMTP...")`) unless explicit environment variables (`SMTP_USER`, `SMTP_PASSWORD`) are supplied. Production logic handles both unconfigured and live SMTP dispatch without raising unhandled errors or blocking database commits.

---

## 4. Conclusion

All empirical tests designed to challenge the implementation across:
1. Role upgrade state transitions and email state machine,
2. Token revocation and immediate 401 enforcement via `auth_version`,
3. `AdminPromotionBanner` widget lifecycle, multi-tap race latching, and timer leak prevention,
4. Frontend `AuthService` 401 session revocation and capability elevation,

have executed to completion with **zero failures** and **zero defects**.

**Verdict: APPROVE**

---

## 5. Verification Method

To independently reproduce all empirical verification results:

```bash
# 1. Execute backend milestone and challenger test suites
cd /Users/mainguyenbinhtan/Downloads/QuanLyKho/backend && \
DATABASE_URL="postgresql+psycopg2://bankops:bankops@127.0.0.1:5432/bankops_test" \
.venv/bin/python -m pytest \
  tests/test_admin_user_role_notification.py \
  tests/test_admin_role_email_notification.py \
  tests/test_e2e_admin_notification_sync.py \
  tests/test_challenger_m3_2_empirical.py -v

# 2. Execute frontend banner, adversarial, and challenger test suites
cd /Users/mainguyenbinhtan/Downloads/QuanLyKho/frontend && \
flutter test \
  test/admin_promotion_banner_test.dart \
  test/admin_promotion_banner_adversarial_test.dart \
  test/admin_promotion_banner_challenger_m3_2_test.dart

# 3. Verify linter cleanliness on challenger code
cd /Users/mainguyenbinhtan/Downloads/QuanLyKho && \
ruff check backend/tests/test_challenger_m3_2_empirical.py
```

**Invalidation Conditions**:
- Any role transition between non-admin roles triggers `send_admin_role_granted_email`.
- Stale tokens with previous `auth_version` succeed with HTTP 200 on `/auth/me` or `/inventory/items`.
- Rapid tapping on `[Làm mới ngay]` triggers duplicate executions of `onRefresh`.
- Disposing `AdminPromotionBanner` during active countdown leaves pending timers in the Flutter test binding.
