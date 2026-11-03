# BRIEFING — 2026-11-02T15:58:00Z

## Mission
Implement and verify Milestones M1 & M2 (Homepage Revamp, Subsystem Sync, Mobile Viewport Parity & Component Fixes BUG-01 through BUG-12) for project QuanLyKho frontend.

## 🔒 My Identity
- Archetype: worker
- Roles: implementer, qa, specialist
- Working directory: /Users/mainguyenbinhtan/Downloads/QuanLyKho/.agents/teamwork/worker_m1_m2_1
- Original parent: fbdb9d15-e07c-4143-974c-2efe416095ff
- Milestone: M1 & M2 (Frontend Revamp & Mobile Parity)

## 🔒 Key Constraints
- Write ownership strictly limited to:
  * frontend/lib/src/features/commerce/commerce_workspace.dart
  * frontend/lib/src/features/commerce/commerce_api.dart
  * frontend/lib/src/features/commerce/commerce_memory_store.dart
  * frontend/lib/src/features/commerce/commerce_reports_page.dart
  * frontend/lib/src/features/auth/edit_profile_dialog.dart
  * frontend/test/homepage_subsystem_sync_test.dart
  * frontend/test/mobile_viewport_audit_test.dart
- Genuine implementation only: no dummy/facade implementations, no hardcoded test values.
- Must run build and tests, achieve zero RenderFlex overflow on 375px/390px/414px, and write 5-component handoff.md.

## Current Parent
- Conversation ID: fbdb9d15-e07c-4143-974c-2efe416095ff
- Updated: not yet

## Task Summary
- **What to build**:
  - M1: Overview tab revamp with 6 KPI cards, 7 subsystem launcher cards, silent background freshness sync without navigation/input resets, HTTP 401 session revocation handling dialog.
  - M2: Fixes BUG-01 to BUG-12 (Topbar title width >= 140px, location chip compact, FittedBox on mini summary cards, responsive modal dialogs on <600px screens, debt page nested scroll fix, reports page cols=1 on <500px, ellipsis on partyName, mobile bottom nav sub-page header indicator).
  - Tests: `homepage_subsystem_sync_test.dart` and `mobile_viewport_audit_test.dart` on 375x667, 390x844, 414x896.
- **Success criteria**:
  - Widget tests pass on Flutter.
  - Zero RenderFlex overflows across mobile viewports.
  - Title width >= 140px on compact screens.
  - Clean architecture and genuine logic.

## Change Tracker
- **Files modified**: none yet
- **Build status**: pending
- **Pending issues**: none

## Quality Status
- **Build/test result**: pending
- **Lint status**: pending
- **Tests added/modified**: pending

## Loaded Skills
- None requested

## Key Decisions Made
- Will inspect all target files first to understand existing implementation structure and line numbers.

## Artifact Index
- DISPATCH.md — Assignment instructions
- BRIEFING.md — Persistent memory
- progress.md — Liveness heartbeat and milestone tracking
- handoff.md — Final 5-component report
