# BRIEFING — 2026-11-02T16:16:00Z

## Mission
Deep read-only technical investigation of frontend authentication and session architecture for Milestone 2 (Role Detection & Promotion watcher, Invalidation handling, State mutation & notification).

## 🔒 My Identity
- Archetype: explorer
- Roles: frontend auth & role detection specialist
- Working directory: /Users/mainguyenbinhtan/Downloads/QuanLyKho/.agents/teamwork/explorer_m2_1
- Original parent: f96c6aba-c50c-476b-ba75-261e5bbc41a1
- Milestone: milestone_2

## 🔒 Key Constraints
- Read-only investigation — do NOT implement
- Target codebase: /Users/mainguyenbinhtan/Downloads/QuanLyKho
- Must read authoritative files first: ORIGINAL_REQUEST.md, PROJECT.md, explorer_1/handoff.md, worker_m1/handoff.md
- Update progress.md with `Last visited: [timestamp]` at each step
- Produce analysis.md and handoff.md (Observation, Logic Chain, Caveats, Conclusion, Verification Method)
- Communicate results via send_message to parent agent

## Current Parent
- Conversation ID: f96c6aba-c50c-476b-ba75-261e5bbc41a1
- Updated: 2026-11-02T16:16:00Z

## Investigation State
- **Explored paths**:
  - `frontend/lib/src/features/auth/auth_service.dart`
  - `frontend/lib/src/data/models/dtos.dart`
  - `frontend/lib/src/core/util/role_visibility.dart`
  - `frontend/lib/src/features/commerce/commerce_api.dart`
  - `frontend/lib/src/features/commerce/commerce_workspace.dart`
  - `frontend/lib/main.dart`
  - `backend/app/api/routes/admin_users.py`
  - `backend/app/api/routes/auth_utils.py`
  - `backend/app/api/routes/auth.py`
  - `backend/app/api/routes/auth_google.py`
  - `frontend/test/homepage_subsystem_sync_test.dart`
  - `frontend/test/root_role_update_test.dart`
  - `frontend/test/user_sync_and_header_icons_test.dart`
- **Key findings**:
  1. `admin_users.py:642` bumps `user.auth_version += 1` on role changes.
  2. `auth_utils.py:491` raises 401 `"Phiên đăng nhập đã bị thu hồi."` on version mismatch.
  3. `AuthService.tryAutoLogin()` currently has a defect: receiving 401 wipes storage and evicts user to login.
  4. `CommerceWorkspace` has `session-revoked-dialog`, but `btn-refresh-session` only reloads store without refreshing `AuthService` tokens, causing a repeated 401 loop.
  5. 2-Tier recovery: Silent Google OAuth re-authentication for zero-touch token refresh, non-disruptive refresh dialog preserving form drafts for password users.
- **Unexplored areas**: None. All requested areas thoroughly explored.

## Key Decisions Made
- Watcher designed as 12-second periodic poller in `AuthService`, paused during offline mode, augmented with `WidgetsBindingObserver` resumed hook.
- State mutation methods `applyAdminPromotionAndRefresh()` and `reloadUser()` designed with full Dart signatures.
- UI notification widget `_AdminPromotionBanner` designed with countdown timer and key `btn-admin-promoted-refresh`.
- `session-revoked-dialog` button `btn-refresh-session` wired to `auth.applyAdminPromotionAndRefresh()`.

## Artifact Index
- DISPATCH.md — record of task dispatch
- BRIEFING.md — persistent situational awareness
- progress.md — liveness heartbeat
- analysis.md — technical analysis and proposed design
- handoff.md — 5-component handoff report
