## 2026-11-02T16:15:59Z
You are Worker 1 (Frontend Implementer) for Milestone 2 of project QuanLyKho.
Your working directory is: /Users/mainguyenbinhtan/Downloads/QuanLyKho/.agents/teamwork/worker_m2_1/

MANDATORY FIRST STEP:
Read /Users/mainguyenbinhtan/Downloads/QuanLyKho/.agents/teamwork/ORIGINAL_REQUEST.md verbatim before writing any code.

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

Consult the authoritative specifications and explorer findings:
1. /Users/mainguyenbinhtan/Downloads/QuanLyKho/PROJECT.md
2. /Users/mainguyenbinhtan/Downloads/QuanLyKho/.agents/teamwork/explorer_m2_1/handoff.md (AuthService & Watcher architecture)
3. /Users/mainguyenbinhtan/Downloads/QuanLyKho/.agents/teamwork/explorer_m2_2/handoff.md (AdminPromotionBanner UI & Layout)
4. /Users/mainguyenbinhtan/Downloads/QuanLyKho/.agents/teamwork/explorer_m2_3/handoff.md (Widget Test Harness & Verification)

File Ownership (You own these files exclusively — do NOT modify files outside this list):
- `frontend/lib/src/features/auth/auth_service.dart`
- `frontend/lib/src/core/widgets/admin_promotion_banner.dart`
- `frontend/lib/src/features/commerce/commerce_workspace.dart`
- `frontend/test/admin_promotion_banner_test.dart`

Task Specifications:
1. `frontend/lib/src/features/auth/auth_service.dart`:
   - Add state: `bool _adminRolePromoted = false;`, `AppUser? _promotedUser;`
   - Add getters: `bool get adminRolePromoted => _adminRolePromoted;`, `AppUser? get promotedUser => _promotedUser;`
   - Add test hook: `@visibleForTesting void setAdminRolePromotedForTest(bool value, {AppUser? promotedUser})`
   - Add role watcher methods:
     * `void startRolePromotionWatcher({Duration interval = const Duration(seconds: 12)})`
     * `void stopRolePromotionWatcher()`
     * `Future<void> checkUserRoleUpdate()`
   - Add refresh method:
     * `Future<void> applyAdminPromotionAndRefresh({List<String>? newRoles, List<String>? newCapabilities})`
     which updates `_user` with promoted roles/capabilities, clears `_adminRolePromoted = false`, and calls `notifyListeners()`.
   - Ensure clean disposal in `dispose()` cancelling any active timers.

2. `frontend/lib/src/core/widgets/admin_promotion_banner.dart`:
   - Implement `AdminPromotionBanner` as a stateful widget.
   - Key: `Key('admin-promotion-banner')`
   - Exact headline text: `"Tài khoản của bạn đã được nâng cấp lên Quản Trị Viên (Admin)"`
   - Subtitle: `"Tài khoản vừa được cấp quyền Quản Trị Viên. Tự động làm mới trong $_remainingSeconds giây..."`
   - Shield icon with Amber `#FBBF24` accent.
   - Enterprise Indigo gradient background (`#312E81` to `#4338CA`) with high contrast text.
   - Action button: `[Làm mới ngay]` with `key: const ValueKey('btn-admin-promoted-refresh')`.
   - Action button: `[Để sau]` with `key: const ValueKey('btn-admin-promoted-dismiss')`.
   - 5-second countdown timer (`Timer.periodic(const Duration(seconds: 1))`): auto-triggers `onRefresh` when countdown reaches 0.
   - In `State.dispose()`, ALWAYS cancel `_countdownTimer?.cancel()`.
   - Adaptive responsive layout: `<500px` 2-tier stacked Column (375px/390px/414px) with zero overflow; `>=500px` Row.

3. `frontend/lib/src/features/commerce/commerce_workspace.dart`:
   - Mount `AdminPromotionBanner` at top of `Column(children: [if (auth.adminRolePromoted || _isAdminPromotionPending) AdminPromotionBanner(...), _WorkspaceTopbar(...), Expanded(...)])`.
   - In `session-revoked-dialog` (`btn-refresh-session`), call `auth.applyAdminPromotionAndRefresh()`.

4. `frontend/test/admin_promotion_banner_test.dart`:
   - Implement 8 comprehensive widget tests according to Explorer 3's blueprint:
     * Test 1: Banner renders with headline, icon, countdown, and `ValueKey('btn-admin-promoted-refresh')`.
     * Test 2: Tapping `btn-admin-promoted-refresh` calls `onRefresh` immediately and cancels timer.
     * Test 3: Auto-countdown steps with `tester.pump(const Duration(seconds: 1))` from 5 down to 0 and automatically triggers `onRefresh`. (IMPORTANT: DO NOT use `pumpAndSettle()` while countdown is active).
     * Test 4: Disposing banner cancels countdown cleanly without timer leak exceptions.
     * Test 5: Mobile viewport parity: renders cleanly on 375x812 and 390x844 without RenderFlex overflow.
     * Test 6: Role promotion unlock: after refresh, `RoleVisibility.isAdmin(roles) == true`, `userRoleLabel == 'Chủ Quán (Admin)'`, and Reports, Approvals, RBAC settings card unlock.
     * Test 7: Tapping `[Để sau]` dismisses the banner and cancels timer.
     * Test 8: Pause countdown when draft form / modal is active.

5. Run Verification Commands:
   - Run `cd frontend && flutter test test/admin_promotion_banner_test.dart`
   - Run `cd frontend && flutter test test/user_sync_and_header_icons_test.dart test/root_role_update_test.dart test/homepage_subsystem_sync_test.dart`
   - Ensure all tests pass with exit code 0.
