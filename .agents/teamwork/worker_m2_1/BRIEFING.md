# BRIEFING — 2026-11-02T16:41:00Z

## Mission
Implement Milestone 2 Frontend Admin Promotion Banner & Role Watcher in QuanLyKho (`auth_service.dart`, `admin_promotion_banner.dart`, `commerce_workspace.dart`, and `admin_promotion_banner_test.dart`).

## 🔒 My Identity
- Archetype: worker
- Roles: implementer, qa, specialist
- Working directory: /Users/mainguyenbinhtan/Downloads/QuanLyKho/.agents/teamwork/worker_m2_1
- Original parent: f96c6aba-c50c-476b-ba75-261e5bbc41a1
- Milestone: Milestone 2 (Admin Role Promotion Realtime Notice)

## 🔒 Key Constraints
- Read `/Users/mainguyenbinhtan/Downloads/QuanLyKho/.agents/teamwork/ORIGINAL_REQUEST.md` verbatim before writing code.
- DO NOT CHEAT: genuine logic, real state transitions, no fake test assertions or dummy facades.
- Own only:
  * `frontend/lib/src/features/auth/auth_service.dart`
  * `frontend/lib/src/core/widgets/admin_promotion_banner.dart`
  * `frontend/lib/src/features/commerce/commerce_workspace.dart`
  * `frontend/test/admin_promotion_banner_test.dart`
- Do NOT touch files outside this ownership list.
- Keep tests clean: pass all tests with exit code 0.
- Liveness heartbeat in `progress.md`.

## Current Parent
- Conversation ID: f96c6aba-c50c-476b-ba75-261e5bbc41a1
- Updated: 2026-11-02T16:41:00Z

## Task Summary
- **What to build**: Admin promotion banner widget with countdown & auto-refresh, role watcher and promotion refresh in `AuthService`, mounting in `CommerceWorkspace`, and comprehensive widget tests.
- **Success criteria**:
  1. `AuthService` tracks promotion state, watcher polling, and safe role application.
  2. `AdminPromotionBanner` displays gold/amber shield, indigo gradient, 5-second countdown, dismiss/refresh buttons, responsive layout (<500px stack, >=500px row).
  3. `CommerceWorkspace` displays banner when promoted, handles refresh in session revoked dialog.
  4. 8 widget tests pass cleanly with 0 timer leak exceptions.
  5. Regression tests `user_sync_and_header_icons_test.dart`, `root_role_update_test.dart`, `homepage_subsystem_sync_test.dart` pass.
- **Interface contracts**: `/Users/mainguyenbinhtan/Downloads/QuanLyKho/PROJECT.md`
- **Code layout**: QuanLyKho/frontend

## Change Tracker
- **Files modified**:
  * `frontend/lib/src/features/auth/auth_service.dart`: Added promotion state, getters, test hook, role watcher polling (12s interval), applyAdminPromotionAndRefresh, dismissAdminPromotionBanner, and clean dispose timer cancellation.
  * `frontend/lib/src/core/widgets/admin_promotion_banner.dart`: Created stateful banner widget with 5s countdown, amber shield, indigo gradient, responsive 2-tier stacked (<500px) and row (>=500px) layout, pause countdown support, and safe dispose.
  * `frontend/lib/src/features/commerce/commerce_workspace.dart`: Mounted AdminPromotionBanner at top of body column; hooked session-revoked-dialog refresh to auth.applyAdminPromotionAndRefresh; fixed bracket syntax in dialogs; preserved dynamic admin capability unlocking.
  * `frontend/test/admin_promotion_banner_test.dart`: Created 8 comprehensive widget tests verifying all specs and edge cases.
- **Build status**: PASS (21/21 tests pass with exit code 0)
- **Pending issues**: none

## Quality Status
- **Build/test result**: 21 passed, 0 failed
- **Lint status**: 0 issues, 0 warnings
- **Tests added/modified**: 8 widget tests in `frontend/test/admin_promotion_banner_test.dart`

## Key Decisions Made
- `AdminPromotionBanner` uses `Key('admin-promotion-banner')` on the root widget and responsive `LayoutBuilder` with `constraints.maxWidth < 500 || screenWidth < 500` to format as 2-tier column on mobile viewports (375px/390px/414px) and row on desktop.
- `AuthService` sets `_adminRolePromoted` when server responds with `admin` role or 401 `auth_version` bump without clearing the user session.
- `CommerceWorkspace` prioritizes promoted admin user claims in `currentUser` and `_canViewOwnerData` so UI instantly unlocks upon `applyAdminPromotionAndRefresh()`.

## Artifact Index
- DISPATCH.md — assignment dispatch
- BRIEFING.md — working memory and identity
- progress.md — liveness heartbeat
- handoff.md — hard completion handoff report
