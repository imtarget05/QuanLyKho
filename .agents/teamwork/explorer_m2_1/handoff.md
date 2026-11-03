# Handoff Report — Explorer 1 (Frontend Auth & Role Detection Specialist)

- **Agent:** Explorer 1 (`explorer_m2_1`)
- **Working Directory:** `/Users/mainguyenbinhtan/Downloads/QuanLyKho/.agents/teamwork/explorer_m2_1/`
- **Milestone:** Milestone 2 — Frontend Auth & Role Detection Architecture
- **Date:** 2026-11-02
- **Type:** Hard (Investigation and Architecture Complete)

---

## 1. Observation

1. **Frontend Architecture & Entry Points**:
   - `frontend/lib/main.dart:40–57`: `AuthService` is provided at app root via `ChangeNotifierProvider(create: (_) => AuthService()..tryAutoLogin())`.
   - `frontend/lib/main.dart:60–86`: `SessionBridge` listens to `AuthService` and constructs `SessionScope(user: auth.user, onSignOut: auth.signOut, child: RepositoryScope(repository: repo, child: child))`.
   - `frontend/lib/main.dart:158, 192–196`: `_AuthGate` watches `AuthService` and mounts `_LiveCommerceGate(auth: auth, onSignOut: ...)`, which in turn passes `user: widget.auth.user`, `roles: widget.auth.user?.roles.toSet()`, and `capabilities: widget.auth.user?.capabilities.toSet()` to `CommerceWorkspace`.
   - `frontend/lib/src/data/models/dtos.dart:7–80`: Class `AppUser` has fields `id`, `username`, `displayName`, `roles` (`List<String>`), `capabilities` (`List<String>`), `email`, `avatarUrl`, and method `copyWith(...)`.

2. **Current `AuthService` Implementation & Invalidation Defect**:
   - `frontend/lib/src/features/auth/auth_service.dart:24–42`: `AuthService` holds `AppUser? _user`, `String? _memoryToken`, `bool _isOfflineSession`, `bool _isLoading`, and `FlutterSecureStorage _storage`.
   - `frontend/lib/src/features/auth/auth_service.dart:310–322`:
     ```dart
     final resp = await _http.get(
       Uri.parse('$_baseUrl/auth/me'),
       headers: {'Authorization': 'Bearer $token'},
     ).timeout(const Duration(seconds: 12));
     if (resp.statusCode == 200) {
       _user = _userFromJson(json.decode(resp.body) as Map<String, dynamic>);
       _isOfflineSession = false;
       await _writeStorage(_offlineSessionKey, null);
     } else {
       await _clearLocal();
       _user = null;
     }
     ```
     **Observation**: If the backend returns 401 due to an `auth_version` bump (following a role promotion), `tryAutoLogin()` calls `_clearLocal()` and nulls `_user`, unexpectedly evicting the user to the login screen and wiping draft inputs.
   - `frontend/lib/src/features/auth/auth_service.dart`: There is currently **zero background polling logic** or lifecycle watcher checking for role updates while the user is actively working in the application.

3. **Role Gating & Capability Visibility**:
   - `frontend/lib/src/core/util/role_visibility.dart:62–67`:
     ```dart
     static bool isAdmin(Set<String> roles) =>
         roles.contains('admin') ||
         roles.contains('root_admin') ||
         roles.contains('system_admin') ||
         roles.contains('manager') ||
         roles.contains('owner');
     ```
   - `frontend/lib/src/core/util/role_visibility.dart:92–114`: `canManageEmployees(user)` returns `true` if `user.roles` has an admin role or `user.capabilities` contains `'iam:admin'` or `'admin:user_management'`.
   - `frontend/lib/src/features/commerce/commerce_workspace.dart:243–249`: `_canViewOwnerData` delegates directly to `RoleVisibility.canManageEmployees(currentUser)`.
   - `frontend/lib/src/features/commerce/commerce_workspace.dart:304–305`: If `canViewOwnerData == false`, tabs 4/5 (Reports/Approvals) are redirected to tab 0 (Overview).
   - `frontend/lib/src/features/commerce/commerce_settings_view.dart:146–149`: RBAC Employee Management card is rendered only `if (canManageUsers)`.

4. **Existing 401 Session Interceptor in `CommerceApi` and Refresh Gap**:
   - `frontend/lib/src/features/commerce/commerce_api.dart:71–85`:
     ```dart
     if (response.statusCode == 401) {
       final message = data is Map
           ? (data['detail'] ?? data['error']?['message'] ?? '...')
           : '...';
       final msgStr = message.toString();
       if (msgStr.contains('Phiên đăng nhập đã bị thu hồi') ||
           msgStr.contains('quyền tài khoản đã thay đổi') ||
           msgStr.toLowerCase().contains('role') ||
           msgStr.toLowerCase().contains('unauthorized')) {
         onSessionRevoked?.call(msgStr);
       }
       throw StateError(msgStr);
     }
     ```
   - `frontend/lib/src/features/commerce/commerce_workspace.dart:178–189`:
     ```dart
     FilledButton.icon(
       key: const Key('btn-refresh-session'),
       onPressed: () async {
         Navigator.of(dialogCtx).pop();
         _isSessionRevokedDialogShowing = false;
         if (widget.onRefresh != null) {
           await widget.onRefresh!();
         } else if (widget.api != null) {
           try {
             await widget.api!.reload(widget.store);
           } catch (_) {}
         }
       },
       label: const Text('Làm mới phiên'),
     )
     ```
     **Observation**: Tapping *"Làm mới phiên"* (`Key('btn-refresh-session')`) only calls `_api.reload(widget.store)`. It **never refreshes `AuthService`'s tokens or user state**. Because the in-memory token still has the old `auth_version`, the subsequent `_api.reload()` fails with 401 again.

5. **Backend Invalidation & Verification Behavior**:
   - `backend/app/api/routes/admin_users.py:642`:
     `user.auth_version = getattr(user, "auth_version", 1) + 1`
   - `backend/app/api/routes/auth_utils.py:491–498`: Compares `payload.get("auth_version")` with `user.auth_version`. If mismatched, raises `HTTP 401 UNAUTHORIZED: Phiên đăng nhập đã bị thu hồi.`.
   - `backend/app/api/routes/auth_utils.py:470–474`: Locked accounts (`user.status != "active"`) return `HTTP 403 FORBIDDEN: Tài khoản đã bị khóa hoặc ngừng hoạt động.`.
   - `backend/app/api/routes/auth.py:472–476`: `POST /auth/refresh` checks `token_auth_version != user.auth_version`. If mismatched, raises 401.
   - `frontend/test/homepage_subsystem_sync_test.dart:268–321`: Verified that `Session Revoked 401 triggers non-disruptive refresh dialog and invokes session refresh` passes with widget key `Key('session-revoked-dialog')` and `Key('btn-refresh-session')`.

---

## 2. Logic Chain

1. **Role Mutation Invalidation Chain**:
   - When an administrator promotes a user (`admin_users.py:638–642`), `user.auth_version` is bumped from $N$ to $N+1$ in PostgreSQL.
   - As observed in Observation 5 (`auth_utils.py:491–498`), any authenticated request carrying access token version $N$ is immediately rejected with `HTTP 401 UNAUTHORIZED: Phiên đăng nhập đã bị thu hồi.`.

2. **Identification of Flaw in Current Frontend**:
   - From Observation 2, `AuthService` has no periodic role watcher. The user remains stuck on non-admin screens indefinitely until a network request fails.
   - From Observation 2, when 401 occurs, `AuthService.tryAutoLogin()` calls `_clearLocal()`, wiping the session and forcing an abrupt logout, discarding form state and pending work.
   - From Observation 4, in `CommerceWorkspace`, clicking *"Làm mới phiên"* only calls `_api.reload(_store)` without refreshing `AuthService`, creating an infinite 401 loop.

3. **Distinguishing Promotion vs. Revocation**:
   - From Observation 5, intentional account lockouts produce `HTTP 403 FORBIDDEN` (`user.status != 'active'`).
   - `HTTP 401` with `"Phiên đăng nhập đã bị thu hồi."` indicates `auth_version` mismatch.
   - For Google OAuth users, `AuthService` can execute silent re-authentication (`_resolveGoogleSignIn().signInSilently()` -> `POST /auth/google`), which obtains fresh tokens with `auth_version = N+1` and new `roles: ['admin', ...]` without user typing.
   - For password users, `AuthService` must retain user state, avoid `_clearLocal()`, and prompt the user via the non-disruptive `session-revoked-dialog` (`homepage_subsystem_sync_test.dart:303`), invoking `auth.applyAdminPromotionAndRefresh()` to unlock admin privileges.

4. **Reactive Unlocking Mechanism**:
   - From Observation 1 & 3, `_AuthGate` and `SessionBridge` consume `AuthService`.
   - Calling `auth.applyAdminPromotionAndRefresh()` updates `_user.roles` with `admin` and calls `notifyListeners()`.
   - This immediately triggers rebuilds of `SessionScope` and `CommerceWorkspace`.
   - `RoleVisibility.canManageEmployees(user)` evaluates to `true`, instantly unlocking financial overview cards, Reports, Approvals, and RBAC settings across the application.

---

## 3. Caveats

- **Scope Boundary**: As Explorer 1, this investigation was strictly READ-ONLY. No source files were modified.
- **Backend Refresh Endpoint Behavior**: In `backend/app/api/routes/auth.py:475`, `POST /auth/refresh` enforces `token_auth_version == user.auth_version`. As verified by `test_security_wave2_identity.py:423`, refresh tokens minted prior to the role change are also rejected with 401. Therefore, seamless automatic refresh is fully silent for Google OAuth sessions, while password sessions rely on in-place re-authentication or `applyAdminPromotionAndRefresh()`.
- **Offline Session Isolation**: The role detection watcher must be disabled during offline ca trực / sandbox mode (`_isOfflineSession == true`) to prevent spurious network requests when running without a server.

---

## 4. Conclusion

The technical path for Milestone 2 is fully analyzed and designed:
1. **`AuthService` Role Detection Watcher**:
   - Add `startRolePromotionWatcher({Duration interval = const Duration(seconds: 12)})` and `stopRolePromotionWatcher()`.
   - Implement `checkUserRoleUpdate()` which probes `GET $_baseUrl/auth/me`.
   - Bind to `WidgetsBindingObserver` on `AppLifecycleState.resumed` to immediately check roles when switching browser tabs.
2. **2-Tier Invalidation Handling**:
   - Tier 1: Silent Google re-authentication (`signInSilently()` -> `POST /auth/google`) for zero-touch token re-minting.
   - Tier 2: Non-disruptive session refresh dialog (`session-revoked-dialog`) preserving form drafts and pending inputs.
3. **State Mutation & Reactive Notification**:
   - Implement `applyAdminPromotionAndRefresh({List<String>? newRoles, List<String>? newCapabilities})`.
   - Implement `reloadUser()`.
   - Add `_AdminPromotionBanner` with key `Key('btn-admin-promoted-refresh')` displaying a 5-second auto-refresh countdown.
   - Wire `Key('btn-refresh-session')` in `commerce_workspace.dart` to call `auth.applyAdminPromotionAndRefresh()`.

Complete code signatures and implementation blueprints are documented in `analysis.md`.

---

## 5. Verification Method

To independently verify this investigation and the upcoming implementation:

1. **Frontend Unit & Widget Test Suites**:
   ```bash
   cd /Users/mainguyenbinhtan/Downloads/QuanLyKho/frontend && \
   flutter test test/user_sync_and_header_icons_test.dart test/root_role_update_test.dart
   ```
   *Expected result*: All 8 tests pass cleanly.

2. **Session Revoked 401 Dialog Test**:
   ```bash
   cd /Users/mainguyenbinhtan/Downloads/QuanLyKho/frontend && \
   flutter test test/homepage_subsystem_sync_test.dart --plain-name "Session Revoked 401 triggers non-disruptive refresh dialog and invokes session refresh"
   ```
   *Expected result*: Test passes; verifies `session-revoked-dialog` and `btn-refresh-session` interactions.

3. **New Test Suite for Implementer**:
   Create `frontend/test/auth_role_detection_watcher_test.dart` asserting:
   - Poller triggers every 12 seconds when logged in as `staff`.
   - When server responds with `admin` role, `auth.adminRolePromoted` becomes `true`.
   - Tapping `[Làm mới ngay]` (`btn-admin-promoted-refresh`) calls `applyAdminPromotionAndRefresh()`, unlocking `RoleVisibility.isAdminUser` and `canManageEmployees`.
   - When server returns 401 on `auth_version` bump, `auth.user` is preserved and `auth.needsSessionRefresh` is set to `true`.

4. **Invalidation Conditions**:
   - If a 401 error results in `_clearLocal()` and clears the user to the login screen during role update, the requirement is violated.
   - If admin capabilities remain locked after `applyAdminPromotionAndRefresh()`, the reactive state propagation is broken.
