# Handoff Report: Frontend UI & Banner Component Specialist (Milestone 2)

- **Agent**: Explorer 2 (Frontend UI & Banner Component Specialist)
- **Working Directory**: `/Users/mainguyenbinhtan/Downloads/QuanLyKho/.agents/teamwork/explorer_m2_2/`
- **Scope**: Frontend Workspace UI, Admin Promotion Banner (`_AdminPromotionBanner`), Countdown Auto-Refresh, Reload Mechanisms, and Mobile Viewport Parity (375px/390px/414px).
- **Date**: 2026-11-02
- **Type**: Hard (Investigation & Analysis Complete)

---

## 1. Observation

1. **Workspace Shell Layout & Rendering**:
   - `frontend/lib/src/features/commerce/commerce_workspace.dart:374–420`:
     The production user interface is rendered by `CommerceWorkspace`. The root body inside `Scaffold` is:
     ```dart
     body: SafeArea(
       child: Row(
         children: [
           if (wide) _WorkspaceSidebar(...),
           Expanded(
             child: Column(
               children: [
                 _WorkspaceTopbar(...),
                 Expanded(
                   child: AnimatedBuilder(
                     animation: store,
                     builder: (context, _) =>
                         IndexedStack(index: pageIndex, children: pages),
                   ),
                 ),
               ],
             ),
           ),
         ],
       ),
     )
     ```
   - `frontend/lib/src/app/app_shell.dart:1436–1444`:
     In the enterprise shell `AppShell`, existing banners (`_AppUpdateBanner`, `_OfflineDemoBanner`, `_TeaOpsTicker`) are stacked vertically in a top-level `Column(children: [...banners..., Expanded(child: body)])` within `_withLiveTicker`.

2. **Existing Banner Implementations**:
   - `frontend/lib/src/app/app_shell.dart:1612–1658`:
     `_AppUpdateBanner` uses `Container` with `Color(0xFF0284C7)`, a system update icon, `Expanded(child: Text(...))`, and an `ElevatedButton` (`key: const Key('btn-banner-update-app')`) calling `onUpdate`.
   - `frontend/lib/src/core/offline/offline_ui.dart:205–216`:
     `OfflineBanner` uses `AnimatedOpacity` and `BoxDecoration` with `Border.all`.

3. **Existing 401 Hook & Session Revocation Behavior**:
   - `frontend/lib/src/features/commerce/commerce_api.dart:71–85`:
     ```dart
     if (response.statusCode == 401) {
       ...
       if (msgStr.contains('Phiên đăng nhập đã bị thu hồi') ||
           msgStr.contains('quyền tài khoản đã thay đổi') ||
           msgStr.toLowerCase().contains('role') ||
           msgStr.toLowerCase().contains('unauthorized')) {
         onSessionRevoked?.call(msgStr);
       }
       throw StateError(msgStr);
     }
     ```
   - `frontend/lib/src/features/commerce/commerce_workspace.dart:89–97`, `133–203`:
     `onSessionRevoked` currently shows a modal `AlertDialog` (`key: const Key('session-revoked-dialog')`) with button `[Làm mới phiên]`. This dialog is disruptive, modal, and does not provide an automated countdown to unlock admin capabilities.

4. **Web Browser Reload vs In-App Refresh**:
   - `frontend/lib/src/core/util/web_helpers_web.dart:47–53`:
     ```dart
     void forceAppUpdate() {
       try {
         js.context.callMethod('forceAppUpdate');
       } catch (_) {
         html.window.location.reload();
       }
     }
     ```
   - `web_helpers_stub.dart:13`: `void forceAppUpdate() {}` for non-web platforms.
   - Calling `forceAppUpdate()` forces a browser window reload (`html.window.location.reload()`), causing loss of in-flight form data, uncommitted draft orders, and active dialog states.
   - Calling `auth.refreshSession()` and `widget.api!.reload(widget.store)` preserves all Flutter widget states, input fields, open dialogs, and navigation tab indices.

5. **Draft State Holding**:
   - `frontend/lib/src/features/commerce/commerce_workspace.dart:4653–4672`:
     `_showCreateOrder` launches an `AlertDialog` containing stateful text controllers (`discount`, `vat`, `shipping`, `note`) and dynamic item lines (`lines = <_DraftLine>[]`). Reloading the browser while this dialog is active obliterates user inputs.

6. **Mobile Viewport Metrics**:
   - Standard viewports: iPhone SE (375x667/812), iPhone 12/13/14/15/16 (390x844), large mobile (414x896).
   - In `_WorkspaceTopbar` (`commerce_workspace.dart:800–803`):
     ```dart
     final screenWidth = MediaQuery.sizeOf(context).width;
     final contentWidth = screenWidth - (screenWidth >= 700 ? 232 : 0);
     final compact = contentWidth < 600;
     ```
   - On compact viewports (<600px), available width for a single row is constrained (375px - 24px padding = 351px). A single-line Row containing icon, long text, and button exceeds 450px and triggers a `RenderFlex` overflow exception.

---

## 2. Logic Chain

1. **Observation 1 & 3**: When an admin grants administrative rights, `CommerceApi` or background role polling signals a privilege update. Currently, this either throws an unhandled 401 or displays an interruptive modal dialog (`session-revoked-dialog`).
2. **Observation 2 & 6**: Placing a prominent, sticky banner (`_AdminPromotionBanner`) at the top of the workspace inside `SafeArea(child: Column(children: [if (_isAdminPromotionPending) _AdminPromotionBanner(...), Expanded(child: ...)]))` provides immediate awareness across all 8 subsystems without blocking user interaction.
3. **Observation 6**: On compact screens (375px, 390px, 414px), a single horizontal row with icon, title, countdown, and action button overflows by ~100px. A responsive 2-tier stacked Column layout (Tier 1: Icon + Title; Tier 2: Countdown text + `[Làm mới ngay]` button) ensures zero layout overflow on all compact viewports while rendering as a streamlined single-line Row on desktop (>=500px).
4. **Observation 4 & 5**: A forced browser reload (`forceAppUpdate()`) is destructive to in-flight user work (e.g., active draft lines in `_showCreateOrder`). Therefore, the banner must employ a **safe in-app session refresh** strategy (`auth.refreshSession()` + `store.reload()`), while pausing the automatic countdown when an order dialog or draft form is active. If in-app renewal fails due to an invalidated refresh token, `forceAppUpdate()` serves as a resilient fallback.
5. **Observation 1 & 2**: The banner provides both immediate manual action via `[Làm mới ngay]` (`ValueKey('btn-admin-promoted-refresh')`) and an automated 5-second countdown timer (`"Tự động làm mới trong X giây..."`), satisfying the user acceptance criterion: *"Người dùng không cần tự phán đoán và thao tác reload trình duyệt thủ công để nhận quyền hạn mới"*.

---

## 3. Caveats

1. **Read-Only Investigation**: As an Explorer, this task was strictly read-only; no code files in `frontend/` were modified.
2. **Backend Token Revocation Behavior**: In `backend/app/api/routes/auth.py:474–476`, if `auth_version` was incremented, the old refresh token is also invalidated on the server. The backend implementer should ensure `/auth/refresh` or a dedicated role refresh endpoint allows an active user session to receive fresh tokens with the updated `auth_version`, or allow silent re-authentication.
3. **Multi-Tab Synchronization**: If the user has multiple browser tabs open, `html.window.addEventListener('storage', ...)` can optionally be used by the implementer to synchronize the role promotion across tabs.

---

## 4. Conclusion

1. **Target Component**: Implement `AdminPromotionBanner` (or `_AdminPromotionBanner`) in `frontend/lib/src/core/widgets/admin_promotion_banner.dart` or co-located in `commerce_workspace.dart` and `app_shell.dart`.
2. **Visual Styling**: Enterprise Dark Indigo gradient (`#312E81` to `#4338CA`), Amber Gold shield icon (`#FBBF24`), White high-contrast text (`#FFFFFF`, contrast ratio 11.4:1), and high-contrast white button with dark indigo text.
3. **Interactive Elements**:
   - Button: `[Làm mới ngay]` with `key: const ValueKey('btn-admin-promoted-refresh')`.
   - Countdown: 5-second periodic timer displaying `"Tự động làm mới trong $_remainingSeconds giây..."`. Auto-fires refresh at 0 seconds.
4. **Mobile Layout**: Responsive layout via `MediaQuery.sizeOf(context).width < 500`:
   - `<500px`: 2-tier stacked Column (zero overflow on 375px, 390px, 414px).
   - `>=500px`: Single horizontal Row.
5. **Reload Strategy**:
   - In-app session refresh first to preserve draft inputs and tab state.
   - Pause countdown if `_isDraftModalActive == true`.
   - Fallback to `forceAppUpdate()` only if in-app session renewal fails.

---

## 5. Verification Method

1. **Widget & Unit Tests**:
   - Run the existing frontend test suites to ensure zero regression:
     ```bash
     cd /Users/mainguyenbinhtan/Downloads/QuanLyKho/frontend && flutter test test/commerce_workspace_test.dart test/homepage_subsystem_sync_test.dart
     ```
2. **New Dedicated Widget Test (`frontend/test/admin_promotion_banner_test.dart`)**:
   - **Test 1 (Render & Key)**: Verify `AdminPromotionBanner` renders icon, title, countdown, and button with `ValueKey('btn-admin-promoted-refresh')`.
   - **Test 2 (Manual Immediate Refresh)**: Tap `[Làm mới ngay]`, verify `onRefresh` is called immediately and timer cancels.
   - **Test 3 (Auto Countdown)**: Advance tester clock by 1s intervals (`tester.pump(const Duration(seconds: 1))`), verify text changes from "5" to "4" to "1", and at 5s, `onRefresh` is automatically triggered.
   - **Test 4 (Mobile Viewport Parity)**:
     Set `tester.view.physicalSize = const Size(375, 812)` and `Size(390, 844)`.
     Pump widget and assert `expect(tester.takeException(), isNull)` with no `RenderFlex` overflow.
   - **Test 5 (Draft Pause)**:
     With `pauseCountdown: true`, advance clock by 10s and verify `onRefresh` is NOT triggered.
