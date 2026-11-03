# BRIEFING — 2026-11-02T16:04:00Z

## Mission
Frontend UI & Banner Component Specialist investigation for Milestone 2: Admin promotion notification, banner placement, countdown auto-refresh, reload mechanisms, and responsive UX across devices.

## 🔒 My Identity
- Archetype: explorer
- Roles: frontend UI, notification presentation, banner component design, responsive UI/a11y specialist
- Working directory: /Users/mainguyenbinhtan/Downloads/QuanLyKho/.agents/teamwork/explorer_m2_2
- Original parent: f96c6aba-c50c-476b-ba75-261e5bbc41a1
- Milestone: Milestone 2 (Frontend UI & Banner Component Specialist)

## 🔒 Key Constraints
- Read-only investigation — do NOT implement or modify source files
- Strictly follow Clean Architecture & layout rules
- Keep message and handoff formats standardized (5-component handoff report)

## Current Parent
- Conversation ID: f96c6aba-c50c-476b-ba75-261e5bbc41a1
- Updated: not yet

## Investigation State
- **Explored paths**:
  - `frontend/lib/src/features/commerce/commerce_workspace.dart` (workspace layout, topbar, reload, 401 hooks, order modals)
  - `frontend/lib/src/app/app_shell.dart` (banner presentation in `_withLiveTicker`, `_AppUpdateBanner`, `_OfflineDemoBanner`)
  - `frontend/lib/src/core/util/web_helpers_web.dart` & `web_helpers_stub.dart` (`forceAppUpdate()`, PWA, update events)
  - `frontend/lib/src/core/util/role_visibility.dart` (role evaluation, admin capabilities, userRoleLabel)
  - `frontend/lib/src/features/auth/auth_service.dart` (session state, user refresh, token persistence)
  - `frontend/lib/src/features/commerce/commerce_api.dart` (401 interception, `onSessionRevoked` callback)
  - `frontend/test/commerce_workspace_test.dart` and `homepage_subsystem_sync_test.dart`
- **Key findings**:
  - `CommerceWorkspace` is the production web SPA root; `AppShell` is the enterprise 3-tier shell. Both benefit from a unified `AdminPromotionBanner`.
  - On compact viewports (<500px, 375px, 390px, 414px), a single horizontal row overflows; a responsive 2-tier stacked Column layout completely eliminates overflow.
  - In-app session refresh preserves draft forms and tab states; browser reload (`forceAppUpdate()`) is destructive and should only be a fallback.
  - Auto-countdown must pause when order composition dialogs are active.
- **Unexplored areas**: None; deep investigation and actionable design completed.

## Key Decisions Made
- Designed `AdminPromotionBanner` with key `ValueKey('btn-admin-promoted-refresh')`, 5-second auto-refresh countdown, and responsive 2-tier mobile layout.
- Decided on top sticky placement within `SafeArea(child: Column(children: [banner, Expanded(...)]))` across both `CommerceWorkspace` and `AppShell`.
- Formulated draft safety strategy: pause countdown when order forms are active; prefer in-app refresh; fallback to `forceAppUpdate()`.
- Wrote full specifications in `analysis.md` and 5-component report in `handoff.md`.

## Artifact Index
- DISPATCH.md — Record of dispatch
- BRIEFING.md — Situational awareness
- progress.md — Liveness heartbeat
- analysis.md — Deep technical analysis report
- handoff.md — 5-component handoff report
