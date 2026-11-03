# Handoff Report: Frontend Explorer (Explorer 1)

- **Agent**: Explorer 1 (Frontend Explorer)
- **Working Directory**: `/Users/mainguyenbinhtan/Downloads/QuanLyKho/.agents/teamwork/explorer_1/`
- **Scope**: Frontend Architecture, Role/Identity Storage, Admin UI Gating, Role Change Detection & Refresh (Requirement R1).
- **Date**: 2026-11-02
- **Type**: Hard (Investigation & Analysis Complete)

---

## 1. Observation

1. **Frontend Framework & Entry Points**:
   - Project: Flutter (`pubspec.yaml:6–15`: `sdk: ">=3.4.0 <4.0.0"`, `provider: ^6.1.2`, `http: ^1.2.0`, `flutter_secure_storage: ^9.2.2`).
   - Main entry: `frontend/lib/main.dart:40–57`: `runApp(MultiProvider(providers: [ChangeNotifierProvider(create: (_) => AuthService()..tryAutoLogin()), ...]))`.
   - Session bridge: `frontend/lib/main.dart:61–86`: `SessionBridge` builds `SessionScope(user: auth.user, onSignOut: auth.signOut, child: RepositoryScope(repository: repo, child: child))`.
   - Primary user screen: `frontend/lib/main.dart:192–196`, `277–286`: logged-in users enter `_LiveCommerceGate` which renders `CommerceWorkspace`. Alternatively, `frontend/lib/src/app/app_shell.dart:71–80` renders responsive 3-tier `AppShell`.

2. **User Identity & Role Storage**:
   - Class `AppUser` in `frontend/lib/src/data/models/dtos.dart:5–35`: fields `id`, `username`, `displayName`, `roles` (`List<String>`), `capabilities` (`List<String>`), `email`, `avatarUrl`.
   - Class `AuthService` in `frontend/lib/src/features/auth/auth_service.dart:24–42`: extends `ChangeNotifier`, stores `AppUser? _user`, `String? _memoryToken`, and persists `access_token` and `refresh_token` in `FlutterSecureStorage`.
   - In `auth_service.dart:305–325`: `tryAutoLogin()` calls `GET $_baseUrl/auth/me` with `Authorization: Bearer $token`. If `resp.statusCode == 200`, `_user = _userFromJson(json.decode(resp.body))` and `notifyListeners()`. If 401, calls `_clearLocal()` and resets `_user = null`.

3. **Admin Privilege Gating in Frontend**:
   - `frontend/lib/src/core/util/role_visibility.dart:62–67`:
     ```dart
     static bool isAdmin(Set<String> roles) =>
         roles.contains('admin') ||
         roles.contains('root_admin') ||
         roles.contains('system_admin') ||
         roles.contains('manager') ||
         roles.contains('owner');
     ```
   - `frontend/lib/src/core/util/role_visibility.dart:92–114`: `canManageEmployees(AppUser? user)` checks if user has admin role or capabilities `iam:admin` / `admin:user_management`.
   - `frontend/lib/src/features/commerce/commerce_workspace.dart:95–129`: `_canViewOwnerData` calls `RoleVisibility.canManageEmployees(currentUser)`.
   - `frontend/lib/src/features/commerce/commerce_workspace.dart:471–478`: Navigation tabs 5 (Reports) and 6 (Approvals) are hidden unless `canViewOwnerData` and `canApprove`.
   - `frontend/lib/src/features/commerce/commerce_settings_view.dart:146–149`, `484–542`: Card "Quản trị Nhân sự & Phân quyền (RBAC)" is conditionally rendered: `if (canManageUsers) ...[ _buildEmployeeManagementCard(context, compact) ]`.
   - `frontend/lib/src/app/app_shell.dart:480–513`: Tab 9 (`EmployeeManagementScreen`) is gated by `RoleVisibility.canManageEmployees(session?.user)`.

4. **Backend Role Update & Session Invalidation Behavior**:
   - `backend/app/api/routes/admin_users.py:633–637`:
     ```python
     for role_code in after - before:
         db.add(UserRole(user_id=u_uuid, role_code=role_code))

     # Invalidate token version so user gets refreshed permissions
     user.auth_version = getattr(user, "auth_version", 1) + 1
     ```
   - `backend/app/api/routes/auth_utils.py:491–498`:
     ```python
     token_auth_version = payload.get("auth_version")
     if token_auth_version is not None and getattr(user, "auth_version", 1) != token_auth_version:
         raise HTTPException(
             status_code=status.HTTP_401_UNAUTHORIZED,
             detail="Phiên đăng nhập đã bị thu hồi.",
             headers={"WWW-Authenticate": "Bearer"},
         )
     ```
   - `backend/tests/test_root_role_assignment.py:150–165`:
     ```python
     response = client.put(f"/admin/users/{user_id}/roles", headers=_headers(auth), json={"roles": ["root_admin"]})
     assert client.get("/admin/users", headers=auth).status_code == 401
     ```
     Verifies that after role update, old access tokens are rejected with 401.

5. **Existing Reload Utilities & Test Suite**:
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
   - `frontend/test/user_sync_and_header_icons_test.dart` and `frontend/test/root_role_update_test.dart`: Executed via `flutter test` and passed 100% (8/8 tests passed).

---

## 2. Logic Chain

1. **Premise**: When an administrator updates a user's role to admin in the backend (`admin_users.py:633–637`), `user.auth_version` is incremented by 1 in the database.
2. **Inference 1 (Observation 4)**: The user's active client session holds an access token stamped with `auth_version = N`. The next time the client makes an authenticated HTTP call, `auth_utils.py:491–498` detects the version mismatch and rejects the request with `401 UNAUTHORIZED: Phiên đăng nhập đã bị thu hồi.`.
3. **Inference 2 (Observation 2)**: In `auth_service.dart:318–322`, any unhandled 401 error results in `_clearLocal()` and resetting `_user = null`, which forces the user to the login screen unexpectedly. There is currently no logic in `AuthService` to detect that the session invalidation was caused by a role promotion, nor any automatic prompt to reload/refresh.
4. **Inference 3 (Observation 3)**: All admin UI capabilities (Overview financial KPIs, Reports page, Approvals, RBAC Settings card, Tab 9 Employee Management) are gated strictly by `RoleVisibility.isAdmin(roles)` and `RoleVisibility.canManageEmployees(user)`. Once `AuthService.user` is updated with `roles: ['admin', ...]` and `notifyListeners()` is called, `SessionBridge` and `SessionScope` immediately re-render and unlock all admin capabilities across the entire application without any code duplication.
5. **Inference 4 (Observation 5)**: Flutter Web already possesses a clean page reload bridge via `forceAppUpdate()` (`html.window.location.reload()`), while in-app state refresh can be achieved by calling `auth.applyAdminPromotionAndRefresh()`.
6. **Deduction (Requirement R1)**: By implementing a lightweight role-check watcher in `AuthService` (polling every 10–15s for non-admin accounts, checking on window focus/resume, and intercepting 401 on role updates) coupled with a dedicated `_AdminPromotionBanner` widget providing a `[Làm mới ngay]` button and automatic countdown refresh, Requirement R1 is fully and cleanly satisfied.

---

## 3. Caveats

- **Scope Boundary**: As Explorer 1, this investigation was strictly READ-ONLY. No project source files were altered.
- **Backend Email Scope (R2)**: Requirement R2 (sending notification email via SMTP upon admin promotion) belongs to Backend Explorer / Implementer; however, frontend must ensure user email is preserved in `AppUser` so profile displays correctly.
- **Backend Token Refresh Consideration**: The backend team should ensure that `POST /auth/refresh` or a dedicated role refresh endpoint allows an active user whose roles changed to receive fresh tokens with the updated `auth_version` rather than treating them as an adversarial stolen session revocation.

---

## 4. Conclusion

1. **Frontend Tech Stack**: Flutter Web / Multi-platform using `Provider` + `SessionScope` (`InheritedWidget`).
2. **Current Root Cause**: When roles are modified, `user.auth_version` is bumped on the server. The client has no promotion watcher, so the user either remains stuck on the outdated staff UI or gets an unhandled 401 error, requiring manual guesswork.
3. **Target Architecture for R1**:
   - Add `checkUserRoleUpdate()` and `startRolePromotionWatcher()` in `AuthService` (`frontend/lib/src/features/auth/auth_service.dart`).
   - Introduce `_AdminPromotionBanner` (with key `btn-admin-promoted-refresh`) displayed prominently when `auth.adminRolePromoted == true`.
   - Provide both immediate user action (`[Làm mới ngay]`) and auto-refresh countdown (5 seconds) to trigger `forceAppUpdate()` / `notifyListeners()`.
   - Update `AppUser.roles` and `AppUser.capabilities` upon refresh so all admin UI elements (Reports, RBAC, Approvals, Financial KPIs) activate immediately.

---

## 5. Verification Method

1. **Unit & Widget Tests**:
   - Run existing frontend tests:
     ```bash
     cd /Users/mainguyenbinhtan/Downloads/QuanLyKho/frontend && flutter test test/user_sync_and_header_icons_test.dart test/root_role_update_test.dart
     ```
   - Target condition: All tests pass with zero failures.
2. **New Integration/Widget Test to Add (for Implementer)**:
   - File: `frontend/test/admin_role_promotion_notification_test.dart`
   - Scenario:
     1. Log in as a staff user (`roles: ['staff']`). Verify Admin card and Reports tab are hidden.
     2. Simulate role update to admin (`roles: ['admin', 'staff']`).
     3. Verify `_AdminPromotionBanner` appears with text *"Tài khoản của bạn đã được nâng cấp lên Quản Trị Viên (Admin)"* and button `[Làm mới ngay]`.
     4. Tap `[Làm mới ngay]` (or trigger auto-refresh).
     5. Verify `RoleVisibility.isAdminUser` is `true`, `RoleVisibility.userRoleLabel` is `'Chủ Quán (Admin)'`, and all admin UI gates unlock.
3. **Backend Test Suite Regression**:
   - Run backend tests to ensure `auth_version` tests remain unaffected:
     ```bash
     cd /Users/mainguyenbinhtan/Downloads/QuanLyKho/backend && poetry run pytest tests/test_iam_admin.py tests/test_root_role_assignment.py -q
     ```
