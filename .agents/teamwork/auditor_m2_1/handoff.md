# Forensic Audit Report — Milestone 2 (Frontend Admin Promotion Banner)

- **Agent**: Forensic Auditor (`auditor_m2_1`)
- **Working Directory**: `/Users/mainguyenbinhtan/Downloads/QuanLyKho/.agents/teamwork/auditor_m2_1/`
- **Target Work Product**: Milestone 2 Frontend Implementation
- **Profile**: General Project
- **Integrity Mode**: Development Mode (ground truth: `ORIGINAL_REQUEST.md` line 8)
- **Verdict**: **CLEAN**

---

## 1. Observation

1. **Ground-Truth User Request & Mode (`ORIGINAL_REQUEST.md`)**:
   - Line 8: `Integrity mode: development`.
   - Line 15-16: `R2. Khắc phục lỗi component và đồng bộ trải nghiệm trên Mobile: Sửa chữa toàn bộ các component bị lỗi hiển thị hoặc lỗi tương tác khi chuyển sang giao diện mobile từ ngoài vào trong ứng dụng; đảm bảo trải nghiệm sử dụng và dữ liệu hiển thị đồng bộ nhất quán giữa phiên bản web và mobile.`
   - Line 26: `tiếp tục: Milestone M4 (Export Engine) và M3 (Google Sheets API) đã hoàn thành; tiếp tục triển khai Milestone M2 (Chuẩn hóa giao diện Mobile Viewport Parity 375px/390px/414px, sửa triệt để các component lỗi khi dùng trên mobile từ ngoài vào trong app)...`

2. **Source Code Inspection — `frontend/lib/src/features/auth/auth_service.dart`**:
   - Added promotion fields: `bool _adminRolePromoted = false;`, `AppUser? _promotedUser;`, `Timer? _rolePromotionWatcherTimer;`.
   - Polling watcher: `startRolePromotionWatcher({Duration interval = const Duration(seconds: 12)})` initiates `Timer.periodic`.
   - Real backend HTTP verification in `checkUserRoleUpdate()`:
     ```dart
     final resp = await _http.get(
       Uri.parse('$_baseUrl/auth/me'),
       headers: {'Authorization': 'Bearer $token'},
     ).timeout(const Duration(seconds: 8));
     ```
   - Authentic role comparison using `RoleVisibility.isAdmin`:
     ```dart
     final wasAdmin = RoleVisibility.isAdmin(_user!.roles.toSet());
     final isNowAdmin = RoleVisibility.isAdmin(updatedUser.roles.toSet());
     if (!wasAdmin && isNowAdmin) {
       _adminRolePromoted = true;
       _promotedUser = updatedUser;
       notifyListeners();
     }
     ```
   - Robust error handling: wrapped in `try { ... } catch (_) {}` to avoid disrupting foreground UI on network hiccups.
   - Clean lifecycle management: `dispose()` calls `stopRolePromotionWatcher()`.
   - Test hook `setAdminRolePromotedForTest` is annotated with `@visibleForTesting`.

3. **Source Code Inspection — `frontend/lib/src/core/widgets/admin_promotion_banner.dart`**:
   - Real `StatefulWidget` with state class `_AdminPromotionBannerState`.
   - Exact typography & styling:
     * Headline: `'Tài khoản của bạn đã được nâng cấp lên Quản Trị Viên (Admin)'`.
     * Subtitle: `'Tài khoản vừa được cấp quyền Quản Trị Viên. Tự động làm mới trong $_remainingSeconds giây...'`.
     * Amber `#FBBF24` shield icon: `Icon(Icons.shield_rounded, color: Color(0xFFFBBF24), size: isCompact ? 24 : 28)`.
     * Indigo gradient: `LinearGradient(colors: [Color(0xFF312E81), Color(0xFF4338CA)])`.
   - Real responsive layout via `LayoutBuilder`:
     * Mobile/compact (`<500px`): 2-tier stacked `Column` with icon and text in Row, followed by action buttons row aligned right.
     * Desktop (`>=500px`): Single horizontal `Row`.
   - Real timer controls:
     * `Timer.periodic(const Duration(seconds: 1), (timer) { ... })` ticking down `_remainingSeconds`.
     * Automatic trigger when `_remainingSeconds <= 1`: invokes `widget.onRefresh()`.
     * Clean timer cancellation in `dispose()`, `_handleRefresh()`, and `_handleDismiss()`.
     * `pauseCountdown` parameter properly handled in `didUpdateWidget`.
   - Verified Keys:
     * Root: `Key('admin-promotion-banner')`.
     * Refresh button: `ValueKey('btn-admin-promoted-refresh')`.
     * Dismiss button: `ValueKey('btn-admin-promoted-dismiss')`.

4. **Source Code Inspection — `frontend/lib/src/features/commerce/commerce_workspace.dart`**:
   - Mounted at top of workspace column above `_WorkspaceTopbar`:
     ```dart
     if (auth?.adminRolePromoted == true || _isAdminPromotionPending)
       AdminPromotionBanner(
         onRefresh: () async {
           setState(() => _isAdminPromotionPending = false);
           if (auth != null) {
             await auth.applyAdminPromotionAndRefresh();
           }
           if (widget.onRefresh != null) {
             await widget.onRefresh!();
           } else if (widget.api != null) {
             try {
               await widget.api!.reload(widget.store);
             } catch (_) {}
           }
         },
         onDismiss: () {
           setState(() => _isAdminPromotionPending = false);
           auth?.dismissAdminPromotionBanner();
         },
       ),
     ```
   - In `_CommerceWorkspaceState.build()`, watched `AuthService` via `Provider.of<AuthService?>(context)`.
   - Dynamically re-evaluates `_canViewOwnerData` and `currentUser` upon `notifyListeners()`, unlocking administrative tabs (Reports, Approvals, RBAC User Management) without page reloads.

5. **Test Code Inspection — `frontend/test/admin_promotion_banner_test.dart`**:
   - 8 comprehensive tests:
     * Test 1: Renders headline, amber shield icon, subtitle countdown, and action button keys.
     * Test 2: Tapping `btn-admin-promoted-refresh` calls `onRefresh` immediately and cancels timer.
     * Test 3: Advances clock step-by-step from 5s down to 0s, updating subtitle text each second, and triggers `onRefresh` at 0s.
     * Test 4: Disposing widget while timer active cancels timer without unhandled exceptions.
     * Test 5: Tests mobile viewport parity on 375x812, 390x844, and 414x896 with 0 RenderFlex overflow.
     * Test 6: Full role promotion unlock integration: promotes staff user, verifies banner renders, clicks refresh, verifies `RoleVisibility.isAdmin` becomes true, role label becomes `'Chủ Quán (Admin)'`, and Reports, Approvals, and RBAC user management cards unlock.
     * Test 7: Dismiss button cancels timer and does not trigger refresh.
     * Test 8: `pauseCountdown: true` freezes countdown and resumes properly.
   - Zero trivial assertions: no `expect(true, isTrue)`. All assertions evaluate real UI elements and state variables.

6. **Tool Commands and Verifications (Empirical Proof)**:
   - Command: `flutter test test/admin_promotion_banner_test.dart`
     Result: **8 passed, 0 failed** in 2.0s (exit code 0).
   - Command: `flutter test test/user_sync_and_header_icons_test.dart test/root_role_update_test.dart test/homepage_subsystem_sync_test.dart`
     Result: **13 passed, 0 failed** in 5.0s (exit code 0).
   - Command: `flutter test test/admin_promotion_banner_test.dart test/user_sync_and_header_icons_test.dart test/root_role_update_test.dart test/homepage_subsystem_sync_test.dart`
     Result: **21 passed, 0 failed** in 7.0s (exit code 0).
   - Command: `flutter analyze lib/src/core/widgets/admin_promotion_banner.dart test/admin_promotion_banner_test.dart`
     Result: **No issues found!** (ran in 1.9s, exit code 0).
   - Pre-populated artifacts: search for pre-existing result/log files in `frontend/` showed only standard `.dart_tool` build caches and `flutter_01.log`.

---

## 2. Logic Chain

1. **No Hardcoded Outputs**: Every value displayed in `AdminPromotionBanner` (countdown seconds, user role labels, unlocked permissions) originates from real Flutter state variables and `AuthService` state models. Tests simulate actual timer ticks and verify the state transitions.
2. **No Dummy Facades**: The widget implements complete Flutter layout hierarchies with `LayoutBuilder`, `Container`, `BoxDecoration`, `LinearGradient`, `BoxShadow`, `Row`, `Column`, `Icon`, and buttons. The timer control logic in `_AdminPromotionBannerState` handles start, pause, resume, cancel, and disposal with real lifecycle methods.
3. **Real Role Integration**: In `AuthService`, role detection uses real HTTP probing with Bearer authentication against `/auth/me`, real JSON decoding, and real role permission verification via `RoleVisibility.isAdmin`.
4. **Authentic Test Assertions**: The test suite exercises realistic user interactions (`tap`, `pump`, `pumpAndSettle`) and asserts against exact widget keys, text content, and model mutations. No fake assertions or bypass mechanisms exist.
5. **Mobile Viewport Compliance**: On all required target viewports specified in `ORIGINAL_REQUEST.md` (375px, 390px, 414px), the banner adapts cleanly with zero RenderFlex overflow.

---

## 3. Caveats

1. **Adversarial Edge Case on Ultra-Compact 320px Viewports**:
   - The user specification in `ORIGINAL_REQUEST.md` (R2 & Follow-up) mandates viewport parity on **375px, 390px, and 414px**. On all three required viewports, the banner renders with zero RenderFlex overflow.
   - However, during adversarial stress testing on an ultra-narrow **320px** canvas (e.g. legacy iPhone SE 1st gen from 2016) when **both** `[Để sau]` (dismiss) and `[Làm mới ngay]` (refresh) action buttons are rendered side-by-side, the button row exceeds the 268px container content width by 52px.
   - *Recommendation (Non-blocking)*: In a future polish iteration, wrap the action buttons in a `Wrap` widget or vertically stack the buttons when `constraints.maxWidth < 360px`.
2. **Modal Countdown Suspension**:
   - While `AdminPromotionBanner` provides a `pauseCountdown` boolean property, `CommerceWorkspace` currently passes the banner without explicitly binding `pauseCountdown` to open modal states. When a dialog opens, auto-refresh reloads the memory store underneath the dialog while the dialog remains safely visible on top of the navigator stack.

---

## 4. Conclusion

The Milestone 2 Frontend Admin Promotion Banner & Role Watcher changes are **fully authentic, free of shortcuts, dummy facades, or hardcoded values**. All 21 target and regression tests pass cleanly.

**Verdict: CLEAN**

---

## 5. Verification Method

To independently verify the empirical results of this forensic audit:

```bash
cd /Users/mainguyenbinhtan/Downloads/QuanLyKho/frontend

# 1. Run dedicated Admin Promotion Banner test suite (8 tests)
flutter test test/admin_promotion_banner_test.dart

# 2. Run regression test suites (13 tests)
flutter test test/user_sync_and_header_icons_test.dart test/root_role_update_test.dart test/homepage_subsystem_sync_test.dart

# 3. Run all test suites together (21 tests)
flutter test test/admin_promotion_banner_test.dart test/user_sync_and_header_icons_test.dart test/root_role_update_test.dart test/homepage_subsystem_sync_test.dart

# 4. Run static analysis on banner and test files
flutter analyze lib/src/core/widgets/admin_promotion_banner.dart test/admin_promotion_banner_test.dart
```

Expected result:
- Tests: 21 passed, 0 failed, exit code 0.
- Analyze: No issues found, exit code 0.
