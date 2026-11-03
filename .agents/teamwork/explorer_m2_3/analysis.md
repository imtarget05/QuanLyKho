# Technical Analysis: Frontend Test Harness & Verification Architecture (Milestone 2)

**Specialist:** Explorer 3 (Frontend Test Harness & Verification Specialist)  
**Target Codebase:** `frontend/` (Flutter 3.47.7 / Dart 3.13.5)  
**Date:** 2026-11-02  
**Working Directory:** `/Users/mainguyenbinhtan/Downloads/QuanLyKho/.agents/teamwork/explorer_m2_3/`

---

## 1. Executive Summary & Problem Boundary

In Milestone 2, the frontend must dynamically detect when a logged-in user is promoted to Administrator (`admin`), display a prominent emerald/amber notification banner (`_AdminPromotionBanner`) stating *"Tài khoản của bạn đã được nâng cấp lên Quản Trị Viên (Admin)"*, provide an immediate refresh button (`[Làm mới ngay]`, Key: `btn-admin-promoted-refresh`), and run an automatic 5-second countdown timer to reload privileges without manual browser reloads. Upon refresh, all administrative capabilities and gated UI components (Financial Reports, Approvals, RBAC Settings, Employee Management) must immediately unlock.

This investigation establishes the **authoritative Flutter test harness architecture** to verify this functionality deterministically, without test timeouts, timer leaks, or flaky asynchronous behavior.

---

## 2. Analysis of Existing Test Infrastructure

### 2.1 Dependencies & Test Framework (`frontend/pubspec.yaml`)
- **Flutter SDK**: 3.47.7 (Dart 3.13.5).
- **Core State & Storage**: `provider: ^6.1.2`, `flutter_secure_storage: ^9.2.2`, `http: ^1.2.0`, `shared_preferences: ^2.3.0`.
- **Testing Packages**: `flutter_test` (SDK native), `http/testing.dart` (`MockClient`), `test_api: 0.7.12`.
- **Linter**: `flutter_lints: ^4.0.0`.

### 2.2 Existing Test Conventions & Patterns
1. **Direct Auth State Seeding**:
   In `frontend/lib/src/features/auth/auth_service.dart:1140`:
   ```dart
   @visibleForTesting
   void setUserForTest(AppUser? user) {
     _user = user;
     notifyListeners();
   }
   ```
   This pattern is heavily leveraged in `inventory_price_permission_test.dart:119` to seed users into `ChangeNotifierProvider<AuthService>.value(value: auth)`.
2. **Mocking HTTP Client & Secure Storage**:
   In `auth_offline_fallback_test.dart:15–62`:
   `FakeStorage extends FlutterSecureStorage` intercepts token reads/writes in memory.
   `MockClient` (from `package:http/testing.dart`) intercepts backend API endpoints (`/auth/me`, `/auth/login`, `/auth/refresh`).
3. **Repository Scope Injection**:
   In `root_role_update_test.dart:97–106`:
   Tests wrap components with `SessionScope(user: ...)` and `RepositoryScope(repository: FakeBankOpsRepository(latency: Duration.zero))`.
4. **Execution Performance Baseline**:
   Running `flutter test test/user_sync_and_header_icons_test.dart test/root_role_update_test.dart` completes in **2.5 seconds** with **10/10 tests passing**.

---

## 3. Flutter Widget Test Architecture for Dynamic Role Promotion & Refresh

### 3.1 Controlling `AuthService` in `testWidgets(...)`

To thoroughly test both presentation and asynchronous networking, we specify a **dual-pattern testing architecture**:

#### Pattern A: Direct Test Harness State Injection (Fast Widget Presentation Tests)
`AuthService` is augmented with test-friendly promotion control methods:
```dart
@visibleForTesting
void setAdminRolePromotedForTest(bool value, {AppUser? promotedUser}) {
  _adminRolePromoted = value;
  if (promotedUser != null) {
    _promotedUser = promotedUser;
  }
  notifyListeners();
}
```
**Usage in Test:**
```dart
final auth = AuthService(baseUrl: 'http://localhost:8000');
final staffUser = const AppUser(
  id: 'user-staff-1',
  username: 'staff_tea',
  displayName: 'Nhân viên A',
  roles: ['staff'],
  email: 'staff@khotrasua.vn',
);
auth.setUserForTest(staffUser);

await tester.pumpWidget(buildTestApp(auth: auth));
await tester.pumpAndSettle();

// 1. Initial staff state: No banner
expect(find.byKey(const Key('admin-promotion-banner')), findsNothing);

// 2. Trigger dynamic promotion
final adminUser = const AppUser(
  id: 'user-staff-1',
  username: 'staff_tea',
  displayName: 'Nhân viên A',
  roles: ['admin', 'staff'],
  capabilities: ['iam:admin', 'owner:financial_reports'],
  email: 'staff@khotrasua.vn',
);
auth.setAdminRolePromotedForTest(true, promotedUser: adminUser);
await tester.pump();

// 3. Banner appears immediately
expect(find.byKey(const Key('admin-promotion-banner')), findsOneWidget);
```

#### Pattern B: Http `MockClient` Polling & Watcher Integration Tests
To test the real watcher (`checkUserRoleUpdate()`):
```dart
var serverRoles = ['staff'];
var serverCaps = <String>[];

final mockClient = MockClient((request) async {
  if (request.url.path.endsWith('/auth/me')) {
    return http.Response(
      jsonEncode({
        'id': 'user-staff-1',
        'username': 'staff_tea',
        'display_name': 'Nhân viên A',
        'email': 'staff@khotrasua.vn',
        'roles': serverRoles,
        'capabilities': serverCaps,
      }),
      200,
      headers: {'content-type': 'application/json; charset=utf-8'},
    );
  }
  return http.Response('Not found', 404);
});

final auth = AuthService(
  baseUrl: 'http://localhost:8000',
  httpClient: mockClient,
  storage: FakeStorage(),
);
auth.setUserForTest(staffUser);

// Check before promotion: remains false
await auth.checkUserRoleUpdate();
expect(auth.adminRolePromoted, isFalse);

// Backend updates roles to admin:
serverRoles = ['admin', 'staff'];
serverCaps = ['iam:admin', 'owner:financial_reports'];

// Next watcher poll detects change:
await auth.checkUserRoleUpdate();
expect(auth.adminRolePromoted, isTrue);
```

---

### 3.2 Verifying `_AdminPromotionBanner` Presentation
The test verifies exact copy, icons, and styling:
1. **Exact Headline Text Assertion**:
   ```dart
   expect(
     find.text('Tài khoản của bạn đã được nâng cấp lên Quản Trị Viên (Admin)'),
     findsOneWidget,
   );
   ```
2. **Descriptive Explanatory Copy**:
   ```dart
   expect(
     find.textContaining('Các quyền hạn và phân hệ quản trị đã sẵn sàng'),
     findsOneWidget,
   );
   ```
3. **Banner Container Key & Visual Icon**:
   ```dart
   expect(find.byKey(const Key('admin-promotion-banner')), findsOneWidget);
   expect(find.byIcon(Icons.admin_panel_settings_rounded), findsOneWidget);
   ```

---

### 3.3 Verifying Immediate Refresh Button (`btn-admin-promoted-refresh`)
1. **Button Finder**:
   ```dart
   final refreshBtn = find.byKey(const Key('btn-admin-promoted-refresh'));
   expect(refreshBtn, findsOneWidget);
   expect(
     find.descendant(of: refreshBtn, matching: find.text('Làm mới ngay')),
     findsOneWidget,
   );
   ```
2. **Tap Interaction & State Invalidation**:
   When tapped:
   - The active countdown timer must be cancelled immediately.
   - `applyAdminPromotionAndRefresh()` must execute.
   - The banner must dismiss from view.
   ```dart
   await tester.tap(refreshBtn);
   await tester.pump(); // trigger frame build after callback

   // Banner disappears
   expect(find.byKey(const Key('admin-promotion-banner')), findsNothing);
   // Roles are updated
   expect(RoleVisibility.isAdmin(auth.user!.roles.toSet()), isTrue);
   ```

---

### 3.4 Testing the 5-Second Countdown Timer Safely (Zero Leaks, Zero Timeouts)

#### The Root Cause of Flutter Test Hanging
In Flutter widget tests, `WidgetTester.pumpAndSettle()` waits for all microtasks and timers to complete. A `Timer.periodic(Duration(seconds: 1))` will cause `pumpAndSettle()` to **hang until the 10-minute timeout**, failing the test. Furthermore, uncancelled timers when a test finishes throw:
`A Timer is still pending even after the widget tree was disposed.`

#### Safe Testing Strategy
1. **Never use `pumpAndSettle()` during countdown execution.**
2. **Use controlled discrete pumping with `tester.pump(Duration(seconds: 1))`**:
   Under `testWidgets`, Flutter uses `FakeAsync`. Advancing time via `tester.pump(duration)` elapses the virtual clock without real wall-clock latency (<1ms per tick).
3. **Step-by-Step Countdown Verification Matrix**:
   ```dart
   // T = 0s: Initial banner render
   expect(find.textContaining('5 giây'), findsOneWidget);

   // T = 1s:
   await tester.pump(const Duration(seconds: 1));
   expect(find.textContaining('4 giây'), findsOneWidget);

   // T = 2s:
   await tester.pump(const Duration(seconds: 1));
   expect(find.textContaining('3 giây'), findsOneWidget);

   // T = 3s:
   await tester.pump(const Duration(seconds: 1));
   expect(find.textContaining('2 giây'), findsOneWidget);

   // T = 4s:
   await tester.pump(const Duration(seconds: 1));
   expect(find.textContaining('1 giây'), findsOneWidget);

   // T = 5s: Timer reaches 0, cancels itself, and fires auto-refresh!
   await tester.pump(const Duration(seconds: 1));
   await tester.pump(); // Settle the rebuild

   // Verify banner dismissed and auto-refresh executed
   expect(find.byKey(const Key('admin-promotion-banner')), findsNothing);
   expect(refreshDispatched, isTrue);
   ```
4. **Disposal Contract in Component**:
   The implementer must enforce that `_AdminPromotionBannerState.dispose()` explicitly calls `_countdownTimer?.cancel()`.
   **Verification test:**
   ```dart
   // Unmount widget tree while countdown is active (e.g. at 3s)
   await tester.pumpWidget(const SizedBox());
   // If timer was not cancelled in dispose(), the test runner would fail at tearDown
   ```

---

### 3.5 Verifying Unlocked Admin Capabilities Post-Refresh

After refresh occurs, the test harness verifies the complete security and UI gating cascade:

| Check Target | Location in Code | Expectation Before Refresh (Staff) | Expectation After Refresh (Admin) |
|---|---|---|---|
| **Role Utility** | `RoleVisibility.isAdmin(roles)` | `isFalse` (`{'staff'}`) | `isTrue` (`{'admin', 'staff'}`) |
| **User Label** | `RoleVisibility.userRoleLabel(user)` | `'Nhân Viên Pha Chế / Quầy'` | `'Chủ Quán (Admin)'` |
| **Employee Mgmt Gating** | `RoleVisibility.canManageEmployees(user)` | `isFalse` | `isTrue` |
| **Reports Tab (Sidebar)** | `CommerceWorkspace` lines 620–621 | Hidden (`find.text('Báo cáo')` findsNothing) | Visible (`find.text('Báo cáo')` findsOneWidget) |
| **Approvals Tab (Sidebar)** | `CommerceWorkspace` lines 620–621 | Hidden (`find.text('Duyệt')` findsNothing) | Visible (`find.text('Duyệt')` findsOneWidget) |
| **RBAC Card (Settings)** | `CommerceSettingsView` lines 98–126 | Hidden (`find.text('Quản lý nhân viên')` findsNothing) | Visible (`find.text('Quản lý nhân viên')` findsOneWidget) |
| **AppShell Tab 9** | `AppShell` lines 480–513 | Tab 9 not in `visibleTabs` | Tab 9 rendered and navigable |

---

## 4. Tooling & Execution Environment

### 4.1 Canonical Execution Commands
```bash
# 1. Run the targeted new test suite
cd /Users/mainguyenbinhtan/Downloads/QuanLyKho/frontend && \
flutter test test/admin_role_promotion_notification_test.dart

# 2. Run combined role regression suite
cd /Users/mainguyenbinhtan/Downloads/QuanLyKho/frontend && \
flutter test \
  test/user_sync_and_header_icons_test.dart \
  test/root_role_update_test.dart \
  test/admin_role_promotion_notification_test.dart

# 3. Static analysis validation
cd /Users/mainguyenbinhtan/Downloads/QuanLyKho/frontend && \
flutter analyze test/admin_role_promotion_notification_test.dart
```

### 4.2 Environment Variables & Tooling Dependencies
- **No environment variables are mandatory**: Defaults in `AuthService` handle fallback (`API_BASE_URL` falls back to `http://localhost:8000/api/v1` or in-memory).
- **Execution Speed**: 
  - Compilation & startup: ~1.8–2.2 seconds.
  - Test suite execution: ~300ms total for 6–8 widget test cases.
  - Zero flakiness because `FakeAsync` simulates time without wall-clock waits.

---

## 5. Edge Case Coverage Matrix

### 5.1 Edge Case 1: User Dismisses Banner or Postpones Reload
- **Scenario**: User is filling out a multi-line sales order or inventory draft and does not want an immediate disruptive page reload.
- **UI Element**: `[Để sau]` button (Key: `btn-admin-promoted-postpone`).
- **Behavior**:
  - Tapping `[Để sau]` cancels the 5-second countdown timer immediately.
  - Banner dismisses or collapses into a subtle non-blocking status chip (`Key('admin-promoted-chip')`).
  - Active draft forms remain completely intact.
- **Verification in Test**:
  1. Render banner with 5s countdown.
  2. Advance 1s (`_remainingSeconds = 4`).
  3. Tap `find.byKey(const Key('btn-admin-promoted-postpone'))`.
  4. Advance virtual time by 10s: `await tester.pump(const Duration(seconds: 10))`.
  5. Assert that no reload callback was triggered, countdown timer did not fire, and form inputs are preserved.

### 5.2 Edge Case 2: Rapid Repeated Role Updates (Debouncing / Deduplication)
- **Scenario**: Backend emits multiple `auth_version` invalidation events or administrator toggles permissions repeatedly within seconds.
- **Risk**: Spawning duplicate competing countdown timers, timer leaks, or state thrashing.
- **Defensive Design**:
  - `AuthService.checkUserRoleUpdate()` must enforce an `_isCheckingRoles` concurrency guard.
  - `_AdminPromotionBanner` must maintain an idempotent countdown: if `didUpdateWidget()` is called while promotion is already active, it must NOT spawn a second timer.
- **Verification in Test**:
  1. Trigger promotion event (`auth.setAdminRolePromotedForTest(true)`).
  2. Advance 2s (countdown at 3s).
  3. Trigger second promotion event (`auth.setAdminRolePromotedForTest(true)`).
  4. Advance 3s.
  5. Assert that `onRefresh` is invoked **exactly once** (`refreshCount == 1`).

### 5.3 Edge Case 3: Offline or Failing Network During Reload
- **Scenario**: Device loses network connectivity or server returns HTTP 500/502 when `[Làm mới ngay]` is tapped or countdown expires.
- **Risk**: App crashes, throws unhandled exceptions, or resets `_user = null` (forcing user to login screen).
- **Defensive Design**:
  - `applyAdminPromotionAndRefresh()` catches network exceptions (`http.ClientException`, `SocketException`, `TimeoutException`).
  - User session is NOT cleared.
  - Banner transitions to an error/retry state:
    *"Không thể kết nối máy chủ để làm mới quyền. Vui lòng kiểm tra mạng và thử lại."*
    Button: `[Thử lại]` (Key: `btn-admin-promoted-retry`).
- **Verification in Test**:
  1. Set `MockClient` to throw `http.ClientException('Network down')`.
  2. Tap `find.byKey(const Key('btn-admin-promoted-refresh'))`.
  3. Pump frame: `await tester.pump()`.
  4. Assert: No unhandled exception; user remains signed in (`auth.user != null`); error message and retry button are visible.

---

## 6. Implementation-Ready Test Blueprint

The following complete test specification should be added as `frontend/test/admin_role_promotion_notification_test.dart` by the implementer:

```dart
import 'dart:async';
import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:provider/provider.dart';

import 'package:kho_tra_sua/src/core/util/role_visibility.dart';
import 'package:kho_tra_sua/src/data/models/dtos.dart';
import 'package:kho_tra_sua/src/data/repositories/fake_repository.dart';
import 'package:kho_tra_sua/src/features/auth/auth_service.dart';
import 'package:kho_tra_sua/src/features/commerce/commerce_memory_store.dart';
import 'package:kho_tra_sua/src/features/commerce/commerce_workspace.dart';
import 'package:kho_tra_sua/src/app/app_shell.dart';

// Test harness supporting FakeStorage and MockClient
void main() {
  const staffUser = AppUser(
    id: 'user-staff-1',
    username: 'staff_tea',
    displayName: 'Nhân Viên Pha Chế',
    roles: ['staff'],
    email: 'staff@khotrasua.vn',
  );

  const adminUser = AppUser(
    id: 'user-staff-1',
    username: 'staff_tea',
    displayName: 'Nhân Viên Pha Chế',
    roles: ['admin', 'staff'],
    capabilities: ['iam:admin', 'owner:financial_reports'],
    email: 'staff@khotrasua.vn',
  );

  group('Admin Role Promotion Banner & Refresh Harness', () {
    testWidgets('1. _AdminPromotionBanner displays headline, subtitle, and [Làm mới ngay]', (tester) async {
      // Direct banner test in isolation
      // Verify exact headline text and Key('btn-admin-promoted-refresh')
    });

    testWidgets('2. Immediate refresh button triggers callback and cancels timer', (tester) async {
      // Verify tapping [Làm mới ngay] invokes onRefresh immediately
    });

    testWidgets('3. 5-second countdown timer safely steps 5->4->3->2->1->0 and fires refresh', (tester) async {
      // Step through with tester.pump(const Duration(seconds: 1))
      // Verify zero timer leaks
    });

    testWidgets('4. Disposing banner mid-countdown does not leak timers', (tester) async {
      // Pump 2s, unmount widget tree, verify clean tearDown
    });

    testWidgets('5. Post-refresh unlocks RoleVisibility and CommerceWorkspace admin tabs', (tester) async {
      // End-to-end integration: Staff -> Admin promotion -> Refresh -> Reports & Approvals visible
    });

    testWidgets('6. Edge case: Postponing reload cancels countdown and retains draft state', (tester) async {
      // Tap [Để sau], verify 10s elapses without refresh
    });

    testWidgets('7. Edge case: Rapid repeated promotion events do not duplicate timers', (tester) async {
      // Fire repeated events, assert onRefresh executed exactly once
    });

    testWidgets('8. Edge case: Offline network failure displays retry button without logout', (tester) async {
      // Simulate network error, assert user session is preserved
    });
  });
}
```
