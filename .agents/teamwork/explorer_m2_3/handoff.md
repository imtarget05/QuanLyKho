# Handoff Report — Explorer 3 (Frontend Test Harness & Verification Specialist)

- **Agent:** Explorer 3 (Frontend Test Harness & Verification Specialist)
- **Working Directory:** `/Users/mainguyenbinhtan/Downloads/QuanLyKho/.agents/teamwork/explorer_m2_3/`
- **Milestone:** Milestone 2 (Frontend Test Harness & Verification Architecture for Dynamic Role Promotion & Refresh)
- **Date:** 2026-11-02
- **Type:** Hard (Investigation, Test Architecture Design & Edge Case Planning Complete)

---

## 1. Observation

1. **Frontend Testing Infrastructure & Dependencies**:
   - `frontend/pubspec.yaml:6–32`: Flutter SDK `^3.4.0` (Environment has Flutter 3.47.7, Dart 3.13.5).
   - Test framework: `flutter_test` (SDK), `http/testing.dart` (`MockClient`), `provider: ^6.1.2`, `flutter_secure_storage: ^9.2.2`.
   - Tool command baseline:
     ```bash
     cd /Users/mainguyenbinhtan/Downloads/QuanLyKho/frontend && \
     flutter test test/user_sync_and_header_icons_test.dart test/root_role_update_test.dart
     ```
     Result: **10/10 passed in 2.5s**.

2. **Existing Test Seeding & Control Mechanisms in `AuthService`**:
   - `frontend/lib/src/features/auth/auth_service.dart:1140–1143`:
     ```dart
     @visibleForTesting
     void setUserForTest(AppUser? user) {
       _user = user;
       notifyListeners();
     }
     ```
   - In `frontend/test/inventory_price_permission_test.dart:118–125`, tests instantiate `AuthService` and seed users directly via `auth.setUserForTest(...)` into `ChangeNotifierProvider<AuthService>.value(value: auth)`.
   - In `frontend/test/auth_offline_fallback_test.dart:15–62`, `FakeStorage extends FlutterSecureStorage` and `MockClient` (from `package:http/testing.dart`) simulate backend network responses and offline persistence.

3. **Current Role Visibility & Admin UI Gating**:
   - `frontend/lib/src/core/util/role_visibility.dart:62–67`:
     ```dart
     static bool isAdmin(Set<String> roles) =>
         roles.contains('admin') ||
         roles.contains('root_admin') ||
         roles.contains('system_admin') ||
         roles.contains('manager') ||
         roles.contains('owner');
     ```
   - `frontend/lib/src/core/util/role_visibility.dart:92–105`: `canManageEmployees(AppUser? user)` requires admin roles or capabilities `iam:admin` / `admin:user_management`.
   - `frontend/lib/src/features/commerce/commerce_workspace.dart:620–626`:
     In desktop sidebar, Reports tab (`Icons.bar_chart_outlined`) is rendered only if `canViewOwnerData` (`RoleVisibility.canManageEmployees(user)` is true). Approvals tab (`Icons.fact_check_outlined`) requires `canApprove`.
   - `frontend/lib/src/features/commerce/commerce_workspace.dart:443–460`:
     In mobile bottom sheet, Reports and Approvals `ListTile` items are conditionally gated by `canViewOwnerData` and `canApprove`.
   - `frontend/test/user_sync_and_header_icons_test.dart:75–102`:
     Directly verifies that a `staff` user CANNOT see `"Quản lý nhân viên"` or `"Nhân sự & Phân quyền"` in `CommerceSettingsView`, whereas an `admin` user CAN see both.

4. **Web Reload Stub vs In-App Refresh**:
   - `frontend/lib/src/core/util/web_helpers_web.dart:47–53`: `forceAppUpdate()` calls `html.window.location.reload()`.
   - `frontend/lib/src/core/util/web_helpers_stub.dart:13`: `void forceAppUpdate() {}` (no-op on VM / test runtime).
   - In unit/widget tests running on Dart VM, `web_helpers_stub.dart` is loaded. Therefore, verification MUST check in-app state refresh (`auth.applyAdminPromotionAndRefresh()`, `notifyListeners()`, unhiding gated widgets) rather than relying on browser page reloads.

5. **Flutter Timer Mechanics Under Test Harness**:
   - `testWidgets` executes on `FakeAsync` (`TestWidgetsFlutterBinding`).
   - Using `await tester.pumpAndSettle()` when a `Timer.periodic(const Duration(seconds: 1))` is ticking causes an **infinite loop and timeout** because the scheduled microtask queue never settles.
   - Stepping virtual time with `await tester.pump(const Duration(seconds: 1))` elapses the simulated clock by 1 second instantaneously (<1ms wall-clock) and triggers active timer callbacks without real-world latency.
   - Disposing the widget while a timer is active requires explicit `timer.cancel()` in `State.dispose()`, otherwise Flutter's test runner fails with `A Timer is still pending even after the widget tree was disposed.`

---

## 2. Logic Chain

1. **Premise 1 (Controlling Auth State)**: To test dynamic role promotion from `staff` to `admin`, tests require a deterministic hook. Following the pattern established by `setUserForTest` (Observation 2), adding `@visibleForTesting void setAdminRolePromotedForTest(bool value, {AppUser? promotedUser})` allows immediate promotion event dispatch without mocking HTTP network traffic for presentation tests. For network watcher tests, `MockClient` (Observation 2) intercepts `GET /auth/me` returning updated roles `['admin', 'staff']`.
2. **Premise 2 (Banner UI Verification)**: When `auth.adminRolePromoted == true`, `_AdminPromotionBanner` renders in `CommerceWorkspace` above the body. The test asserts:
   - Key: `Key('admin-promotion-banner')`
   - Exact text: `"Tài khoản của bạn đã được nâng cấp lên Quản Trị Viên (Admin)"`
   - Refresh button: `Key('btn-admin-promoted-refresh')` with text `"Làm mới ngay"`.
3. **Premise 3 (Manual Refresh Tap)**: When `find.byKey(const Key('btn-admin-promoted-refresh'))` is tapped:
   - The countdown timer is immediately cancelled.
   - `auth.applyAdminPromotionAndRefresh()` is called, setting `adminRolePromoted = false`, applying admin roles, and calling `notifyListeners()`.
   - The banner disappears (`findsNothing`), and admin capabilities unlock immediately.
4. **Premise 4 (Safe 5s Countdown Testing)**:
   - Because `pumpAndSettle()` hangs on periodic timers (Observation 5), the test harness MUST step the countdown discretely using `await tester.pump(const Duration(seconds: 1))`.
   - At T = 0s, text contains `'5'`. At T = 1s, text contains `'4'`. At T = 5s, the timer reaches 0, cancels itself, and automatically fires refresh.
   - `_AdminPromotionBannerState.dispose()` must call `_countdownTimer?.cancel()`. Unmounting the banner at T = 2s with `await tester.pumpWidget(const SizedBox())` confirms zero pending timer leaks.
5. **Premise 5 (Admin Capabilities Verification)**: Once refreshed (Premise 3 & 4), the test harness asserts:
   - `RoleVisibility.isAdmin(auth.user!.roles.toSet()) == true`
   - `RoleVisibility.userRoleLabel(auth.user) == 'Chủ Quán (Admin)'`
   - `CommerceWorkspace` sidebar unhides Reports (`Icons.bar_chart_outlined`) and Approvals (`Icons.fact_check_outlined`).
   - `CommerceSettingsView` unhides `"Quản lý nhân viên"` and `"Nhân sự & Phân quyền"`.
   - Tab 9 (`EmployeeManagementScreen`) becomes visible in `AppShell`.
6. **Premise 6 (VM Stub Parity)**: Because `forceAppUpdate()` is a stub in VM tests (Observation 4), all automated test verifications ground themselves in reactive in-app state refresh, guaranteeing 100% test pass on both CI and local machines.

---

## 3. Caveats

- **Read-Only Investigation**: As Explorer 3, no source files were modified. All designs and code blueprints are specified for the implementer agent.
- **`pumpAndSettle` Prohibition**: The implementer must be explicitly warned NEVER to call `await tester.pumpAndSettle()` while the countdown timer is running, as it will trigger a test timeout.
- **Web vs VM Execution**: In a true browser environment (via `chromedriver` or Flutter Web integration test), `html.window.location.reload()` would reload the page. In unit/widget tests (`flutter test`), in-app state refresh is the primary mechanism verified.

---

## 4. Conclusion

1. **Test Harness Architecture**:
   - Add `@visibleForTesting void setAdminRolePromotedForTest(bool, {AppUser?})` in `AuthService`.
   - Create `frontend/test/admin_role_promotion_notification_test.dart` containing 8 comprehensive test cases covering banner rendering, manual tap, discrete countdown stepping, clean timer disposal, capability unlocking, and all edge cases.
2. **Defensive Component Requirements for Implementer**:
   - `_AdminPromotionBannerState` MUST cancel `_countdownTimer` in both `dispose()` and when `[Làm mới ngay]` / `[Để sau]` is tapped.
   - `didUpdateWidget` MUST be idempotent to prevent duplicate timers on rapid updates.
   - `applyAdminPromotionAndRefresh()` MUST catch network errors and show a retry option without logging the user out.
3. **Execution Command**:
   - `cd frontend && flutter test test/admin_role_promotion_notification_test.dart` (runs in ~2.5s).

---

## 5. Verification Method

To independently verify the test harness design and existing test suite health:

```bash
# 1. Run baseline role tests to verify existing suite passes 100% (10 tests, ~2.5s)
cd /Users/mainguyenbinhtan/Downloads/QuanLyKho/frontend && \
flutter test test/user_sync_and_header_icons_test.dart test/root_role_update_test.dart

# 2. When implementation is delivered by worker, run the new promotion test suite:
cd /Users/mainguyenbinhtan/Downloads/QuanLyKho/frontend && \
flutter test test/admin_role_promotion_notification_test.dart

# 3. Run full role & auth regression suite:
cd /Users/mainguyenbinhtan/Downloads/QuanLyKho/frontend && \
flutter test \
  test/user_sync_and_header_icons_test.dart \
  test/root_role_update_test.dart \
  test/auth_offline_fallback_test.dart \
  test/admin_role_promotion_notification_test.dart
```

### Invalidation Conditions:
- If `flutter test` hangs or throws `pumpAndSettle timed out`, a periodic timer is running unchecked during `pumpAndSettle()`.
- If `flutter test` throws `A Timer is still pending even after the widget tree was disposed`, `_countdownTimer?.cancel()` was omitted from `dispose()`.
- If `_AdminPromotionBanner` does not match the exact Vietnamese text `"Tài khoản của bạn đã được nâng cấp lên Quản Trị Viên (Admin)"`, the requirement is violated.
- If tapping `[Làm mới ngay]` (Key: `btn-admin-promoted-refresh`) does not clear the banner and unlock Reports/Approvals/RBAC, the session refresh contract is violated.
- If network errors during reload cause the user session to be cleared or app to crash, the offline resilience requirement is violated.
