# Systems & Session Lifecycle Review Analysis — Milestone 2

- **Reviewer**: Reviewer 2 (`reviewer_m2_2`)
- **Role**: Systems & Session Lifecycle Reviewer & Adversarial Critic
- **Target Files**:
  * `frontend/lib/src/features/auth/auth_service.dart`
  * `frontend/lib/src/core/widgets/admin_promotion_banner.dart`
  * `frontend/lib/src/features/commerce/commerce_workspace.dart`
  * `frontend/test/admin_promotion_banner_test.dart`
- **Date**: 2026-11-02
- **Verdict**: **APPROVE** (with 1 non-blocking hardening recommendation & 1 related subsystem observation)

---

## 1. Review Summary

**Verdict**: **APPROVE**

Worker 1's implementation of the Admin Promotion Banner, Role Promotion Watcher, and in-memory privilege propagation in Milestone 2 has been thoroughly evaluated against the 4 core mission requirements, systems integration contracts, and adversarial stress criteria:

1. **401 Session Interception & Recovery**: `AuthService.checkUserRoleUpdate()` catches 401 status codes resulting from backend `auth_version` invalidation on role update. Rather than destructively wiping local storage and logging the user out (`_clearLocal()`), it marks `_adminRolePromoted = true`, populates `_promotedUser` with administrative roles/capabilities, and dispatches change notifications to the UI.
2. **Dynamic UI Capability Propagation**: `CommerceWorkspace` seamlessly mounts `AdminPromotionBanner` at the top of the body Column above `_WorkspaceTopbar`. When `applyAdminPromotionAndRefresh()` executes, `_canViewOwnerData` evaluates to `true`, reactively unlocking Reports quick-launch tiles, Approvals, full `CommerceReportsPage`, and the RBAC user management panel in Settings without a browser refresh.
3. **Automated Countdown & Reload**: The 5-second countdown timer (`Timer.periodic`) decrements smoothly from 5 down to 0, automatically triggering in-memory data refresh and privilege promotion without requiring manual browser reload (`window.location.reload()`), while respecting `pauseCountdown` when modal dialogs are active.
4. **Mobile Responsiveness**: `LayoutBuilder` cleanly adapts the banner between desktop (single Row, $\ge 500\text{px}$) and mobile (2-tier stacked Column with `Expanded` text and trailing action Row, $<500\text{px}$). Verified across 375x812, 390x844, and 414x896 viewports with zero RenderFlex overflow.
5. **Zero Integrity Violations**: Comprehensive audit confirmed zero hardcoded test outputs, zero facade/dummy implementations, zero bypassed requirements, and genuine independent test verification.

---

## 2. Findings

### [Minor / Non-Blocking] Finding 1: Refresh Button Action Debounce Guard

- **What**: In `AdminPromotionBanner`, `_handleRefresh()` cancels the countdown timer and immediately invokes `widget.onRefresh()`, but lacks a boolean guard flag (`_actionTriggered`) to prevent duplicate callbacks if the user rapidly double-taps the button before the Flutter widget tree rebuilds.
- **Where**: `frontend/lib/src/core/widgets/admin_promotion_banner.dart:95-99`
- **Why**: In synthetic adversarial tests where the widget is kept mounted after `onRefresh`, multiple rapid taps invoke `onRefresh` multiple times (`refreshCallCount == 2` or `3`).
- **Production Context & Mitigation**: In `CommerceWorkspace`, `onRefresh` immediately sets `_isAdminPromotionPending = false` and `auth.applyAdminPromotionAndRefresh()` clears `_adminRolePromoted = false`, causing the banner to unmount on the subsequent frame. Furthermore, `applyAdminPromotionAndRefresh()` is idempotent (`!contains()` check on roles).
- **Suggestion**: Add a local state flag `bool _actionTriggered = false;` in `_handleRefresh()`:
  ```dart
  void _handleRefresh() {
    if (_actionTriggered) return;
    _actionTriggered = true;
    _countdownTimer?.cancel();
    _countdownTimer = null;
    widget.onRefresh();
  }
  ```

### [Advisory / Related Subsystem] Finding 2: RenderFlex Overflow in `_showStocktake` Modal on 375px Canvas

- **What**: The Stocktake Dialog (`_showStocktake`) overflows by 29 pixels horizontally on a 375x667 canvas:
  `FlutterError: <A RenderFlex overflowed by 29 pixels on the right.>`
- **Where**: `frontend/lib/src/features/commerce/commerce_workspace.dart:6067-6076`
- **Why**: The date display row inside the dialog content box has a fixed-width container of 289px. The inner `Row(children: [Icon, SizedBox, Text('Ngày kiểm kê: $dateText')])` is not wrapped in `Expanded` or `Flexible`, causing the text to overflow by 29px on 375px mobile viewports.
- **Scope Note**: This issue resides in the Stocktake modal dialog (Feature F6 / BUG-07), not in `AdminPromotionBanner` or `AuthService`. It was discovered during comprehensive testing of `test/mobile_viewport_audit_test.dart`.
- **Suggestion**: Wrap the inner text widget in `Expanded` or `Flexible(child: Text('Ngày kiểm kê: $dateText', overflow: TextOverflow.ellipsis))` during modal polish work.

---

## 3. Verified Claims

| # | Claim | Verification Method | Result |
|---|-------|---------------------|--------|
| C1 | `AuthService` handles 401 on role update without clearing local session | Inspected `auth_service.dart:1216-1235` and executed `homepage_subsystem_sync_test.dart` ("Session Revoked 401 triggers non-disruptive refresh dialog") | **PASS** |
| C2 | `CommerceWorkspace` mounts banner and unlocks admin privileges | Executed `admin_promotion_banner_test.dart` Test 6 (Reports, Approvals, RBAC unlocked) | **PASS** |
| C3 | 5s countdown timer steps down to 0 and automatically invokes `onRefresh` | Executed `admin_promotion_banner_test.dart` Test 3 with simulated clock pumps | **PASS** |
| C4 | Unmounting banner during active countdown cleanly cancels timer | Executed `admin_promotion_banner_test.dart` Test 4 and adversarial rapid unmount/remount 10x | **PASS** (Zero leaks) |
| C5 | Banner layout adapts to mobile viewports (<500px) with zero RenderFlex overflow | Executed `admin_promotion_banner_test.dart` Test 5 on 375x812, 390x844, and 414x896 | **PASS** |
| C6 | User can dismiss banner with `[Để sau]` | Executed `admin_promotion_banner_test.dart` Test 7; cancels countdown cleanly | **PASS** |
| C7 | Countdown pauses when draft forms/modals are active | Executed `admin_promotion_banner_test.dart` Test 8; advances 10s with no trigger | **PASS** |
| C8 | Independent execution of all assigned test suites passes with exit code 0 | `flutter test test/admin_promotion_banner_test.dart` (8/8) + `flutter test test/user_sync_and_header_icons_test.dart test/root_role_update_test.dart test/homepage_subsystem_sync_test.dart` (13/13) | **PASS** (21/21 passed) |

---

## 4. Adversarial Challenge Report

### Risk Assessment: LOW
All identified failure modes are either safely mitigated by architectural idempotency or isolated to non-blocking edge cases.

### Challenges

#### Challenge 1: Concurrent Token Invalidation & Role Polling
- **Assumption**: When the backend bumps `auth_version`, polling `GET /auth/me` returns 401 and the app cleanly transitions to promoted state.
- **Attack Scenario**: Network packet drops or intermittent offline connectivity occur exactly when `auth_version` is bumped.
- **Blast Radius**: `checkUserRoleUpdate()` throws a network timeout or socket exception.
- **Observed Defense**: Lines 1236-1238 wrap the entire request in `try { ... } catch (_) {}`. Network errors are swallowed gracefully without clearing the session or disrupting the user's active screen. On the next 12-second tick, the request retries.

#### Challenge 2: Rapid Multi-Tapping on [Làm mới ngay]
- **Assumption**: The user taps `[Làm mới ngay]` once.
- **Attack Scenario**: User clicks 3 times in quick succession before the banner unmounts.
- **Blast Radius**: `onRefresh` callback executed multiple times.
- **Observed Defense**: `applyAdminPromotionAndRefresh()` uses set-based idempotency checks (`!currentRoles.contains('admin')`). Tapping repeatedly produces the identical updated state without data duplication. Once unmounted, further taps are impossible.

#### Challenge 3: Smallest Screen Parity (320px width)
- **Assumption**: Mobile viewports are $\ge 375\text{px}$.
- **Attack Scenario**: App opened on an ultra-compact screen (320px width, e.g. iPhone SE 1st gen).
- **Blast Radius**: Potential horizontal button overflow on Tier 2 of the banner.
- **Calculation**: Total available width = $320 - (12 \times 2) - (14 \times 2) = 264\text{px}$. Dismiss button (~69px) + gap (8px) + refresh button (~135px) = 212px. Since $212\text{px} \le 264\text{px}$, the layout accommodates 320px screens with 52px of breathing room.

---

## 5. Integrity & Verification Attestation

- **Independent Command Execution**:
  1. `cd frontend && flutter test test/admin_promotion_banner_test.dart` -> 8 passed, 0 failed in 2.0s.
  2. `cd frontend && flutter test test/user_sync_and_header_icons_test.dart test/root_role_update_test.dart test/homepage_subsystem_sync_test.dart` -> 13 passed, 0 failed in 6.0s.
  3. `cd frontend && flutter test test/admin_promotion_banner_adversarial_test.dart` -> 5 passed, 0 failed.
  4. Total verified passing tests: 26 tests across 5 test suites.
- **Integrity Attestation**: No facades, mocks in production code, or fabricated artifacts were detected. The work is genuine, robust, and verified.
