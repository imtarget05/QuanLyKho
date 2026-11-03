# BRIEFING — 2026-11-02T15:10:00Z

## Mission
Implement Milestone M1 (Homepage Revamp & Subsystem Synchronization: F1, F2, F3) for QuanLyKho.

## 🔒 My Identity
- Archetype: worker
- Roles: implementer, qa, specialist
- Working directory: /Users/mainguyenbinhtan/Downloads/QuanLyKho/.agents/teamwork/worker_m1_1
- Original parent: fbdb9d15-e07c-4143-974c-2efe416095ff
- Milestone: M1 (Homepage Revamp & Subsystem Synchronization)

## 🔒 Key Constraints
- Follow Clean Architecture and write ownership.
- Only modify designated files:
  - frontend/lib/src/features/commerce/commerce_workspace.dart
  - frontend/lib/src/features/commerce/commerce_api.dart
  - frontend/lib/src/features/commerce/commerce_memory_store.dart
  - backend/app/api/routes/admin_users.py
  - backend/tests/test_admin_role_email_notification.py
  - frontend/test/homepage_subsystem_sync_test.dart
- Integrity Mandate: No dummy implementations, real state & logic.
- Background sync must be silent and preserve UI state.
- Handle role revocation / 401 gracefully with refresh prompt.
- Backend email sending on role change must be wrapped in try/except.

## Current Parent
- Conversation ID: fbdb9d15-e07c-4143-974c-2efe416095ff
- Updated: 2026-11-02T15:10:00Z

## Task Summary
- **What to build**:
  1. F1: Redesign overview page in `commerce_workspace.dart` with modern KPI cards (todayRevenue, grossProfitToday, inventoryValue, customerReceivables, supplierPayables, lowStockItemsCount) and quick action subsystem launch tiles leading to all other 7 subsystems.
  2. F2: Real-time background data freshness (periodic 60s or resume >30s) without blocking UI.
  3. F3: Backend email notification on admin role change + frontend 401 handling for revoked sessions with refresh dialog.
- **Success criteria**:
  - All unit/widget tests pass (`pytest tests/test_admin_role_email_notification.py`, `flutter test test/homepage_subsystem_sync_test.dart`).
- **Interface contracts**: PROJECT.md, survey_frontend.md
- **Code layout**: AGENTS.md

## Key Decisions Made
- [TBD]

## Artifact Index
- DISPATCH.md — Assignment instructions
- progress.md — Liveness & step-by-step progress
- handoff.md — Final handoff report

## Change Tracker
- **Files modified**: [None yet]
- **Build status**: [Not run yet]
- **Pending issues**: None

## Quality Status
- **Build/test result**: [Not run yet]
- **Lint status**: Clean
- **Tests added/modified**: backend/tests/test_admin_role_email_notification.py, frontend/test/homepage_subsystem_sync_test.dart

## Loaded Skills
- None
