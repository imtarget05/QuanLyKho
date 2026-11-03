# BRIEFING — 2026-11-02T15:06:00Z

## Mission
Investigate QuanLyKho frontend architecture, authentication/role storage, admin UI gating, and role change detection mechanism to fulfill Requirement R1 (admin role update notification / auto-refresh).

## 🔒 My Identity
- Archetype: explorer
- Roles: frontend explorer, investigator, synthesizer
- Working directory: /Users/mainguyenbinhtan/Downloads/QuanLyKho/.agents/teamwork/explorer_1
- Original parent: eb3ef222-d19e-45a6-a876-1ab4961ac627
- Milestone: exploration

## 🔒 Key Constraints
- Read-only investigation — do NOT implement
- Do NOT modify any code in QuanLyKho repository
- Only write metadata, reports, and analysis in /Users/mainguyenbinhtan/Downloads/QuanLyKho/.agents/teamwork/explorer_1/

## Current Parent
- Conversation ID: eb3ef222-d19e-45a6-a876-1ab4961ac627
- Updated: 2026-11-02T15:06:00Z

## Investigation State
- **Explored paths**:
  - `frontend/lib/main.dart` (entry point, Provider, SessionBridge, _AuthGate, _LiveCommerceGate)
  - `frontend/lib/src/features/auth/auth_service.dart` (AuthService, token management, tryAutoLogin, user parsing)
  - `frontend/lib/src/core/util/role_visibility.dart` (RBAC gating rules: isAdmin, canManageEmployees, userRoleLabel, visibleTabs)
  - `frontend/lib/src/app/app_shell.dart` (SessionScope, 3-tier responsive shell, Tab 9 IAM gating, _AppUpdateBanner)
  - `frontend/lib/src/features/commerce/commerce_workspace.dart` (_canViewOwnerData, Reports tab, Approvals tab, Overview KPIs)
  - `frontend/lib/src/features/commerce/commerce_settings_view.dart` (Employee Management RBAC card)
  - `frontend/lib/src/core/util/web_helpers_web.dart` (forceAppUpdate via html.window.location.reload)
  - `backend/app/api/routes/admin_users.py` (update_user_roles bumping auth_version)
  - `backend/app/api/routes/auth_utils.py` (get_current_user enforcing auth_version mismatch 401)
  - `frontend/test/user_sync_and_header_icons_test.dart` & `root_role_update_test.dart` (ran and passed)
- **Key findings**:
  1. Frontend is a Flutter Web / Multi-platform app using Provider + SessionScope (`InheritedWidget`).
  2. Role updates on backend bump `iam_users.auth_version` -> client access token triggers 401 on next request.
  3. Client currently has no role promotion watcher, leading to unexpected 401 logout or stale staff UI.
  4. Gating is centralized in `RoleVisibility`. Updating `AuthService.user` unlocks all admin features seamlessly.
  5. Recommended solution: Tri-layer detection (10s polling watcher + lifecycle resume + 401 interceptor) + `_AdminPromotionBanner` with `[Làm mới ngay]` button & 5s auto-refresh countdown.
- **Unexplored areas**: None within frontend scope; backend email delivery (R2) assigned to Backend Explorer.

## Key Decisions Made
- Recommend non-blocking top banner with immediate refresh action + countdown instead of silent abrupt reload.
- Document backend handoff contract regarding token refresh when `auth_version` increments on role promotion.

## Artifact Index
- `DISPATCH.md` — Incoming dispatch message
- `BRIEFING.md` — Persistent situational awareness
- `progress.md` — Liveness heartbeat & checklist
- `analysis.md` — In-depth technical analysis report
- `handoff.md` — 5-component structured handoff report
