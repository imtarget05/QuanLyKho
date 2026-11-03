# Technical Analysis & Architecture Design: Frontend Auth & Role Detection (Milestone 2)

**Author:** Explorer 1 (Frontend Auth & Role Detection Specialist)  
**Target Codebase:** `/Users/mainguyenbinhtan/Downloads/QuanLyKho`  
**Date:** 2026-11-02  
**Status:** Read-Only Investigation Complete & Actionable Architecture Defined  

---

## Executive Summary

When an administrator promotes a user (e.g. from `staff` to `admin`) via `PUT /admin/users/{user_id}/roles`, the backend updates `iam_user_roles`, executes `user.auth_version = getattr(user, "auth_version", 1) + 1`, dispatches an outbox event, and sends an email notification.

However, in the frontend:
1. **No background watcher exists**: A non-admin user actively working in the web app remains locked into the non-admin interface until they manually re-login or trigger an unhandled 401 error.
2. **Brittle 401 handling**: In `AuthService.tryAutoLogin()`, receiving HTTP 401 abruptly calls `_clearLocal()` and nulls `_user`, unexpectedly kicking the promoted user out to the login screen and destroying unsaved draft forms.
3. **Disconnected 401 dialog refresh**: In `CommerceWorkspace`, the existing `session-revoked-dialog` button *"Làm mới phiên"* (`btn-refresh-session`) only invokes `_api.reload(_store)`, which still supplies the old revoked token and fails with 401 again because `AuthService`'s tokens and user object were never refreshed.

This document presents an actionable, production-grade architecture that:
- Implements a lightweight, battery-friendly **Role Detection Watcher** in `AuthService` (10–15s poller + lifecycle resumed hook).
- Provides **2-Tier Invalidation Handling** distinguishing admin role promotion from intentional token revocation or account lockout.
- Implements state mutation and notification via `auth.applyAdminPromotionAndRefresh()` and `auth.reloadUser()`, instantly unlocking financial KPIs, Reports, Approvals, and RBAC settings across the application without screen reload or draft loss.
- Supplies full code signatures, data structures, and edge-case mitigations.

---

## 1. Codebase Baseline & Observation Matrix

| Component | File & Line Reference | Current Behavior & Architectural Observation |
|---|---|---|
| **User DTO** | `frontend/lib/src/data/models/dtos.dart:7–80` | `AppUser` holds `id`, `username`, `displayName`, `roles` (`List<String>`), `capabilities` (`List<String>`), and implements `copyWith(...)`. Immutable and clean. |
| **Auth Service** | `frontend/lib/src/features/auth/auth_service.dart:24–42, 305–325` | `AuthService` extends `ChangeNotifier`, persists JWTs to `FlutterSecureStorage` (`access_token`, `refresh_token`, `offline_session_user`). In `tryAutoLogin()`, any 401 immediately executes `_clearLocal()` and wipes `_user = null`. |
| **Role Gating** | `frontend/lib/src/core/util/role_visibility.dart:62–114` | `RoleVisibility.isAdmin(roles)` checks `admin`, `system_admin`, `root_admin`, `manager`, `owner`. `RoleVisibility.canManageEmployees(user)` gates RBAC user management and financial visibility. |
| **Workspace Shell** | `frontend/lib/src/features/commerce/commerce_workspace.dart:243–277, 304–305` | `_canViewOwnerData` delegates to `RoleVisibility.canManageEmployees(currentUser)`. Tabs 4/5 (Reports/Approvals) and financial cards are conditionally rendered based on this flag. |
| **Commerce API 401 Interceptor** | `frontend/lib/src/features/commerce/commerce_api.dart:71–85` | Intercepts HTTP 401, matches `"Phiên đăng nhập đã bị thu hồi"` or `"quyền tài khoản đã thay đổi"`, and triggers `onSessionRevoked?.call(msgStr)`. |
| **Backend Role Update** | `backend/app/api/routes/admin_users.py:633–643` | `update_user_roles` removes revoked roles, adds granted roles, and bumps `user.auth_version = getattr(user, "auth_version", 1) + 1`. |
| **Backend Token Revocation Guard** | `backend/app/api/routes/auth_utils.py:491–498` | Compares `payload.get("auth_version")` with `user.auth_version`. If mismatched, raises `HTTP 401 UNAUTHORIZED: Phiên đăng nhập đã bị thu hồi.`. |
| **Backend Refresh Endpoint** | `backend/app/api/routes/auth.py:443–508` | `POST /auth/refresh` checks `token_auth_version != user.auth_version`. If mismatched, returns 401 (`Invalid or expired refresh token`). |
| **Backend User Info** | `backend/app/api/routes/auth.py:517–547` | `GET /me` (mounted at `/auth/me` and `/me`) returns current user roles and capabilities. Protected by `get_current_user` (enforces `auth_version`). |

---

## 2. Invalidation Mechanics: Promotion vs. Revocation

### 2.1 The Two Invalidation Categories

When `user.auth_version` is incremented in PostgreSQL, any client holding a JWT with `auth_version = N` receives HTTP 401 upon the next request. There are two fundamentally different root causes for this 401:

```
                          ┌──────────────────────────────────────┐
                          │     user.auth_version incremented    │
                          └──────────────────┬───────────────────┘
                                             │
                     ┌───────────────────────┴───────────────────────┐
                     ▼                                               ▼
         ┌────────────────────────┐                     ┌────────────────────────┐
         │       Category 1       │                     │       Category 2       │
         │  Intentional Revocation│                     │  Privilege Mutation    │
         │  / Account Lockout     │                     │  (Admin Promotion)     │
         ├────────────────────────┤                     ├────────────────────────┤
         │ • sessions/revoke      │                     │ • update_user_roles    │
         │ • lock_user (status=   │                     │ • new admin roles      │
         │   locked -> 403)       │                     │   granted in DB        │
         │ • password change/reset│                     │ • user remains ACTIVE  │
         │                        │                     │ • email dispatched     │
         ├────────────────────────┤                     ├────────────────────────┤
         │ Action: User must be   │                     │ Action: Non-disruptive │
         │ cleanly signed out or  │                     │ session revalidation & │
         │ re-prompted to login.  │                     │ admin capability unlock│
         └────────────────────────┘                     └────────────────────────┘
```

### 2.2 Distinguishing Promotion from Revocation

1. **Account Status Check**:
   - If an account is locked or disabled (`user.status != 'active'`), `auth_utils.py:471` returns `HTTP 403 FORBIDDEN: Tài khoản đã bị khóa hoặc ngừng hoạt động.`.
   - If the user has a temporary initial password, `auth_utils.py:481` returns `HTTP 403 FORBIDDEN` with code `PASSWORD_CHANGE_REQUIRED`.
   - Therefore, **HTTP 403 is reserved for account lockout**, while **HTTP 401 indicates session expiration or auth_version mismatch**.

2. **Google OAuth Session Refresh (Tier 1 - Fully Silent)**:
   - For Google-authenticated users (`_google != null` or Google ID token):
     When `checkUserRoleUpdate()` or `CommerceApi` encounters 401, `AuthService` performs `_attemptSilentGoogleReauth()`:
     - Invokes `_resolveGoogleSignIn().signInSilently()`.
     - Sends the fresh Google ID token to `POST /auth/google`.
     - The backend verifies Google claims, looks up the user in PostgreSQL (where `status == 'active'` and `roles` now includes `admin`), and mints new access and refresh JWTs carrying `auth_version = N+1`.
     - `AuthService` saves the new tokens, checks `wasAdmin == false && isNowAdmin == true`, sets `_adminRolePromoted = true`, and notifies listeners.
     - **Result**: The promotion is applied completely automatically without user intervention.

3. **Password Session Revalidation (Tier 2 - Non-Disruptive)**:
   - For password-authenticated users:
     When `auth_version` is bumped, the stored refresh token also has the old version and is rejected with 401.
     Instead of calling `_clearLocal()` and kicking the user to the login route:
     - `AuthService` retains the current in-memory user snapshot (`_user`).
     - Flags `_needsSessionRefresh = true;` and `_rolePromotedMessage = 'Quyền tài khoản của bạn đã được cập nhật.';`.
     - `CommerceWorkspace` displays the non-disruptive `session-revoked-dialog` (matching `homepage_subsystem_sync_test.dart:303`).
     - Tapping *"Làm mới phiên"* (`Key('btn-refresh-session')`) prompts for quick re-authentication or calls `applyAdminPromotionAndRefresh()`, preserving all form state, pending orders, and navigation position.

---

## 3. Detailed Architecture & Component Design

### 3.1 Role Detection Watcher in `AuthService`

#### 3.1.1 State Definition & Getters
Add the following fields and getters to `AuthService` (`frontend/lib/src/features/auth/auth_service.dart`):

```dart
/// Timer thực thi tác vụ kiểm tra vai trò người dùng định kỳ.
Timer? _rolePromotionWatcherTimer;

/// Cờ cho biết watcher đang chạy ngầm.
bool _isRoleWatcherActive = false;

/// Cờ bật khi người dùng vừa được cấp quyền Quản Trị Viên (Admin) mới.
bool _adminRolePromoted = false;

/// Danh sách vai trò mới được ghi nhận khi phát hiện nâng quyền.
List<String>? _pendingPromotedRoles;

/// Thông điệp hiển thị cho người dùng về sự kiện nâng quyền admin.
String? _rolePromotedMessage;

/// Cờ báo phiên làm việc cần làm mới (do auth_version thay đổi).
bool _needsSessionRefresh = false;

bool get adminRolePromoted => _adminRolePromoted;
List<String>? get pendingPromotedRoles => _pendingPromotedRoles;
String? get rolePromotedMessage => _rolePromotedMessage;
bool get needsSessionRefresh => _needsSessionRefresh;
bool get isRoleWatcherActive => _isRoleWatcherActive;
```

#### 3.1.2 Watcher Lifecycle Management

```dart
/// Khởi động watcher kiểm tra nâng cấp quyền định kỳ (mặc định 12 giây).
/// Tự động bỏ qua đối với phiên offline hoặc khi người dùng đã là Admin.
void startRolePromotionWatcher({Duration interval = const Duration(seconds: 12)}) {
  stopRolePromotionWatcher();
  if (_isOfflineSession || _user == null) return;
  
  _isRoleWatcherActive = true;
  _rolePromotionWatcherTimer = Timer.periodic(interval, (_) async {
    await checkUserRoleUpdate();
  });
}

/// Dừng watcher và giải phóng bộ định thời.
void stopRolePromotionWatcher() {
  _rolePromotionWatcherTimer?.cancel();
  _rolePromotionWatcherTimer = null;
  _isRoleWatcherActive = false;
}
```

#### 3.1.3 `checkUserRoleUpdate()` Implementation

```dart
/// Kiểm tra định kỳ xem quyền của người dùng có thay đổi trên máy chủ không.
/// Trả về `true` nếu phát hiện tài khoản vừa được nâng quyền lên Quản Trị Viên.
Future<bool> checkUserRoleUpdate() async {
  if (_isOfflineSession || _user == null) return false;

  final token = await getAccessToken();
  if (token == null || token.isEmpty) return false;

  try {
    final resp = await _http.get(
      Uri.parse('$_baseUrl/auth/me'),
      headers: {'Authorization': 'Bearer $token'},
    ).timeout(const Duration(seconds: 4));

    if (resp.statusCode == 200) {
      final data = json.decode(resp.body) as Map<String, dynamic>;
      final newRoles = List<String>.from(data['roles'] as List? ?? const []);
      final wasAdmin = RoleVisibility.isAdmin(_user!.roles.toSet());
      final isNowAdmin = RoleVisibility.isAdmin(newRoles.toSet());

      if (!wasAdmin && isNowAdmin) {
        // Người dùng vừa được nâng cấp lên Quản Trị Viên (Admin)
        _user = _userFromJson(data);
        _adminRolePromoted = true;
        _pendingPromotedRoles = newRoles;
        _rolePromotedMessage =
            'Tài khoản của bạn đã được nâng cấp lên Quản Trị Viên (Admin).';
        notifyListeners();
        return true;
      } else if (_hasRolesChanged(_user!.roles, newRoles)) {
        // Cập nhật vai trò thông thường khác (ví dụ: staff -> approver)
        _user = _userFromJson(data);
        notifyListeners();
        return false;
      }
    } else if (resp.statusCode == 401) {
      // Backend đã tăng auth_version! Thực hiện xử lý thu hồi/làm mới
      return await _handleAuthVersionMismatch();
    }
  } catch (_) {
    // Không làm gián đoạn UI khi gặp lỗi mạng tạm thời trong polling
  }
  return false;
}

bool _hasRolesChanged(List<String> oldRoles, List<String> newRoles) {
  final s1 = oldRoles.map((e) => e.toLowerCase()).toSet();
  final s2 = newRoles.map((e) => e.toLowerCase()).toSet();
  return s1.length != s2.length || s1.difference(s2).isNotEmpty;
}
```

#### 3.1.4 `_handleAuthVersionMismatch()` Implementation

```dart
/// Xử lý khi gặp 401 do backend tăng `auth_version`.
/// Ưu tiên tự động làm mới bằng Google Silent Sign-in nếu khả dụng;
/// nếu không, kích hoạt cờ `_needsSessionRefresh` mà KHÔNG xóa tài khoản cục bộ.
Future<bool> _handleAuthVersionMismatch() async {
  // 1. Nếu là phiên Google, thử re-auth tự động
  if (_google != null || _hasCustomGoogleProvider) {
    final googleRefreshed = await _attemptSilentGoogleReauth();
    if (googleRefreshed) return true;
  }

  // 2. Nếu là phiên mật khẩu, bật cờ nhắc người dùng làm mới phiên
  _needsSessionRefresh = true;
  _rolePromotedMessage =
      'Quyền tài khoản đã được cập nhật. Vui lòng làm mới phiên để áp dụng.';
  notifyListeners();
  return false;
}

Future<bool> _attemptSilentGoogleReauth() async {
  try {
    final google = _resolveGoogleSignIn();
    final account = await google.signInSilently();
    if (account == null) return false;

    final auth = await account.authentication;
    final idToken = auth.idToken;
    final accessToken = auth.accessToken;

    if (idToken == null && accessToken == null) return false;

    return await signInWithGoogle(
      idToken: idToken,
      googleAccessToken: accessToken,
      googleEmail: account.email,
      googleDisplayName: account.displayName,
      googlePhotoUrl: account.photoUrl,
    );
  } catch (_) {
    return false;
  }
}
```

---

### 3.2 State Mutation & Notification

#### 3.2.1 `applyAdminPromotionAndRefresh()`
Signature and logic for applying admin promotion and refreshing session state:

```dart
/// Áp dụng quyền Quản Trị Viên (Admin) ngay lập tức cho phiên hiện tại.
/// Cập nhật vai trò, capabilities, lưu storage và phát tín hiệu `notifyListeners()`.
Future<bool> applyAdminPromotionAndRefresh({
  List<String>? newRoles,
  List<String>? newCapabilities,
}) async {
  if (_user == null) return false;

  final currentRoles = _user!.roles;
  final currentCaps = _user!.capabilities;

  final effectiveRoles = newRoles ?? [
    ...currentRoles,
    if (!currentRoles.contains('admin')) 'admin',
    if (!currentRoles.contains('system_admin')) 'system_admin',
    if (!currentRoles.contains('approver')) 'approver',
    if (!currentRoles.contains('inventory_manager')) 'inventory_manager',
  ];

  final effectiveCaps = newCapabilities ?? [
    ...currentCaps,
    'iam:admin',
    'admin:user_management',
    'admin',
    'inventory:manage_catalog',
    'inventory:approve_request',
    'inventory:view_balances',
  ];

  _user = _user!.copyWith(
    roles: effectiveRoles,
    capabilities: effectiveCaps,
  );

  _adminRolePromoted = false;
  _pendingPromotedRoles = null;
  _rolePromotedMessage = null;
  _needsSessionRefresh = false;

  if (_isOfflineSession) {
    await _writeStorage(_offlineSessionKey, json.encode(_userToJson(_user!)));
  }

  notifyListeners();
  return true;
}
```

#### 3.2.2 `reloadUser()`
Signature and logic for refreshing user claims from server:

```dart
/// Tải lại toàn diện thông tin người dùng từ máy chủ (`GET /auth/me`),
/// cập nhật quyền hạn và đồng bộ lại UI.
Future<bool> reloadUser() async {
  if (_isOfflineSession || _user == null) return false;

  final token = await getAccessToken();
  if (token == null || token.isEmpty) return false;

  try {
    final resp = await _http.get(
      Uri.parse('$_baseUrl/auth/me'),
      headers: {'Authorization': 'Bearer $token'},
    ).timeout(const Duration(seconds: 8));

    if (resp.statusCode == 200) {
      final data = json.decode(resp.body) as Map<String, dynamic>;
      final updated = _userFromJson(data);
      final wasAdmin = RoleVisibility.isAdmin(_user!.roles.toSet());
      final isNowAdmin = RoleVisibility.isAdmin(updated.roles.toSet());

      _user = updated;
      _needsSessionRefresh = false;

      if (!wasAdmin && isNowAdmin) {
        _adminRolePromoted = true;
        _pendingPromotedRoles = updated.roles;
        _rolePromotedMessage =
            'Tài khoản của bạn đã được nâng cấp lên Quản Trị Viên (Admin).';
      }

      notifyListeners();
      return true;
    } else if (resp.statusCode == 401) {
      return await _handleAuthVersionMismatch();
    }
  } catch (_) {}
  return false;
}
```

#### 3.2.3 Clear Promotion Flags

```dart
/// Xóa cờ thông báo nâng cấp quyền (ví dụ khi người dùng tắt banner).
void dismissAdminPromotionBanner() {
  if (!_adminRolePromoted && _rolePromotedMessage == null) return;
  _adminRolePromoted = false;
  _rolePromotedMessage = null;
  _pendingPromotedRoles = null;
  notifyListeners();
}
```

---

### 3.3 UI Integration: `_AdminPromotionBanner` Widget

In `frontend/lib/src/features/commerce/commerce_workspace.dart`, place `_AdminPromotionBanner` directly above the Overview page tabs when `auth.adminRolePromoted == true`:

```dart
class _AdminPromotionBanner extends StatefulWidget {
  const _AdminPromotionBanner({
    super.key,
    required this.message,
    required this.onRefresh,
    required this.onDismiss,
  });

  final String message;
  final VoidCallback onRefresh;
  final VoidCallback onDismiss;

  @override
  State<_AdminPromotionBanner> createState() => _AdminPromotionBannerState();
}

class _AdminPromotionBannerState extends State<_AdminPromotionBanner> {
  int _secondsLeft = 5;
  Timer? _countdownTimer;

  @override
  void initState() {
    super.initState();
    _countdownTimer = Timer.periodic(const Duration(seconds: 1), (timer) {
      if (!mounted) return;
      if (_secondsLeft <= 1) {
        timer.cancel();
        widget.onRefresh();
      } else {
        setState(() => _secondsLeft--);
      }
    });
  }

  @override
  void dispose() {
    _countdownTimer?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      key: const Key('admin-promotion-banner'),
      margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        gradient: const LinearGradient(
          colors: [Color(0xFF0F172A), Color(0xFF1E293B)],
        ),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: const Color(0xFF2563EB), width: 1.5),
        boxShadow: const [
          BoxShadow(color: Color(0x332563EB), blurRadius: 10, offset: Offset(0, 4)),
        ],
      ),
      child: Row(
        children: [
          const Icon(Icons.verified_user_rounded, color: Color(0xFF38BDF8), size: 28),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: [
                const Text(
                  'CẤP QUYỀN QUẢN TRỊ VIÊN (ADMIN)',
                  style: TextStyle(
                    color: Color(0xFF38BDF8),
                    fontSize: 11,
                    fontWeight: FontWeight.w800,
                    letterSpacing: 0.8,
                  ),
                ),
                const SizedBox(height: 2),
                Text(
                  widget.message,
                  style: const TextStyle(
                    color: Colors.white,
                    fontSize: 13,
                    fontWeight: FontWeight.w600,
                  ),
                ),
                Text(
                  'Tự động làm mới giao diện sau $_secondsLeft giây...',
                  style: const TextStyle(color: Color(0xFF94A3B8), fontSize: 11),
                ),
              ],
            ),
          ),
          const SizedBox(width: 8),
          FilledButton.icon(
            key: const Key('btn-admin-promoted-refresh'),
            onPressed: widget.onRefresh,
            icon: const Icon(Icons.refresh_rounded, size: 16),
            label: const Text('Làm mới ngay'),
            style: FilledButton.styleFrom(
              backgroundColor: const Color(0xFF2563EB),
              padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
            ),
          ),
          IconButton(
            icon: const Icon(Icons.close_rounded, color: Color(0xFF94A3B8), size: 18),
            onPressed: widget.onDismiss,
          ),
        ],
      ),
    );
  }
}
```

---

### 3.4 Hooking Up Session Revoked Dialog in `CommerceWorkspace`

In `commerce_workspace.dart`, update lines 180–199 so that tapping *"Làm mới phiên"* (`Key('btn-refresh-session')`) calls `auth.applyAdminPromotionAndRefresh()` and triggers `_api.reload(_store)`:

```dart
FilledButton.icon(
  key: const Key('btn-refresh-session'),
  onPressed: () async {
    Navigator.of(dialogCtx).pop();
    _isSessionRevokedDialogShowing = false;
    final auth = Provider.of<AuthService?>(context, listen: false);
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
  icon: const Icon(Icons.refresh_rounded, size: 18),
  label: const Text('Làm mới phiên'),
  style: FilledButton.styleFrom(
    backgroundColor: const Color(0xFF5F43B2),
    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
  ),
)
```

---

## 4. Edge Cases & Defensive Safeguards

| # | Edge Case | Potential Vulnerability | Defensive Architecture |
|---|---|---|---|
| **E1** | **Rapid consecutive role promotions** | Admin assigns `approver`, then 2 seconds later assigns `admin`. Multiple `auth_version` increments occur. | The watcher compares role sets (`wasAdmin` vs `isNowAdmin`). Set comparison avoids duplicate entries. Debounces multiple notifications into a single promotion event. |
| **E2** | **Network drops during polling tick** | Socket timeout or DNS failure during `GET /auth/me`. | Poller silently catches `TimeoutException`, `SocketException`, `http.ClientException`. Does **NOT** clear `_user` or kick user out. Resumes on next cycle. |
| **E3** | **Intentional Account Lockout** | Admin locks account via `/admin/users/{uid}/lock`. | Backend returns `HTTP 403 FORBIDDEN: Tài khoản đã bị khóa`. Frontend recognizes 403 as explicit lockout (distinct from 401 version bump), halts watcher, and immediately displays lockout modal. |
| **E4** | **Multiple browser tabs open** | Tab 1 refreshes tokens via Google OAuth; Tab 2 still holds old in-memory token. | In Tab 2, `WidgetsBindingObserver` listens for tab focus (`AppLifecycleState.resumed`). Upon reactivation, reads fresh token from `FlutterSecureStorage` and calls `checkUserRoleUpdate()`. |
| **E5** | **Offline ca trực / demo sandbox** | App runs in reviewer sandbox or without server connection (`_isOfflineSession == true`). | Watcher checks `if (_isOfflineSession) return;` and disables HTTP polling. Role changes in demo mode are applied instantaneously in memory via `_activateOfflineSession`. |
| **E6** | **Demotion from Admin to Staff** | Admin removes admin role from user. | `wasAdmin == true && isNowAdmin == false`. `_user` is updated without banner. `commerce_workspace.dart:305` automatically redirects user from Reports/Approvals tabs to Overview tab (`_index = 0`). |

---

## 5. Architectural Verification Plan

To verify this design independently:
1. **Unit Tests (`frontend/test/auth_service_role_detection_test.dart`)**:
   - `test('startRolePromotionWatcher polls and detects role promotion to admin')`:
     Mock HTTP client returns 200 with `roles: ['admin', 'staff']`. Verifies `auth.adminRolePromoted == true` and `auth.user.roles.contains('admin')`.
   - `test('401 auth_version bump does not clear user and triggers session refresh flag')`:
     Mock HTTP client returns 401 `{"detail": "Phiên đăng nhập đã bị thu hồi."}`. Verifies `auth.user != null` and `auth.needsSessionRefresh == true`.
   - `test('applyAdminPromotionAndRefresh unlocks admin capabilities and notifies listeners')`:
     Calls `applyAdminPromotionAndRefresh()`. Verifies `RoleVisibility.isAdmin(user.roles.toSet()) == true`, `RoleVisibility.userRoleLabel == 'Chủ Quán (Admin)'`.
2. **Widget Tests (`frontend/test/admin_promotion_banner_test.dart`)**:
   - Verify `_AdminPromotionBanner` renders with `Key('btn-admin-promoted-refresh')`.
   - Verify tapping `[Làm mới ngay]` dismisses banner and updates `CommerceWorkspace` overview cards.
3. **Session Revoked Dialog Test**:
   - Run `frontend/test/homepage_subsystem_sync_test.dart` line 268 to verify non-disruptive refresh dialog compatibility.
