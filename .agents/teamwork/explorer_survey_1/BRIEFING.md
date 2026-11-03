# BRIEFING — 2026-11-02T15:10:00Z

## Mission
Survey frontend architecture of QuanLyKho, focusing on R1 (Homepage revamp & subsystem synchronization) and R2 (Component bug fixes & mobile viewport synchronization).

## 🔒 My Identity
- Archetype: explorer
- Roles: Frontend Architecture & Mobile UI Explorer
- Working directory: /Users/mainguyenbinhtan/Downloads/QuanLyKho/.agents/teamwork/explorer_survey_1
- Original parent: fbdb9d15-e07c-4143-974c-2efe416095ff
- Milestone: Frontend Survey & Mobile UI Audit (R1, R2)

## 🔒 Key Constraints
- Read-only investigation — do NOT implement
- Write findings and reports ONLY inside working directory (/Users/mainguyenbinhtan/Downloads/QuanLyKho/.agents/teamwork/explorer_survey_1)
- No modifying source code in the repo

## Current Parent
- Conversation ID: fbdb9d15-e07c-4143-974c-2efe416095ff
- Updated: 2026-11-02T15:02:32Z

## Investigation State
- **Explored paths**: `frontend/lib/main.dart`, `src/features/commerce/commerce_workspace.dart`, `src/features/commerce/commerce_api.dart`, `src/features/commerce/commerce_memory_store.dart`, `src/features/commerce/commerce_reports_page.dart`, `src/features/commerce/commerce_settings_view.dart`, `src/app/app_shell.dart`, `src/features/dashboard/dashboard_screen.dart`, `src/features/admin/employee_management_screen.dart`, `src/features/auth/auth_service.dart`, `src/features/auth/login_screen.dart`, `src/features/landing/landing_screen.dart`, `backend/app/api/routes/admin_users.py`, `backend/app/api/routes/auth.py`, `backend/app/services/email_service.py`, `frontend/web/index.html`, `frontend/nginx.conf`, `.github/workflows/deploy-pages.yml`
- **Key findings**:
  1. Frontend is a Flutter Web Single Page Application (SPA), compiled to release Web/Wasm and deployed via Cloudflare Workers Assets with Modal FastAPI backend.
  2. Architecture duality exists between legacy `AppShell` (using `DataSyncController`, SSE, heartbeat) and currently active `CommerceWorkspace` (POS, Sales, Purchases, Inventory, Debt, Reports, Approvals, Settings using `CommerceMemoryStore` and `CommerceApi`).
  3. `CommerceWorkspace` lacks background polling, SSE, or WebSocket. When an admin updates a user's role to `admin` in `PUT /admin/users/{user_id}/roles`, backend increments `user.auth_version`. The user's active session is invalidated, throwing 401 on next call with NO auto-refresh or notification dialog.
  4. Mobile layout audit reveals 12 concrete UI issues on 375px/390px/414px: Topbar title squashed to ~51px due to conflicting `Expanded(title)` + `Spacer()` with location chip; hardcoded modal dialog widths (440px, 420px, 580px) causing tight squeezing; `_MiniSummaryRow` truncating numbers; nested scroll view conflicts in Debt tab; and ActionChip touch targets under 48x48dp.
- **Unexplored areas**: None. Comprehensive survey and evidence gathering completed.

## Key Decisions Made
- Completed in-depth exploration of R1 and R2 across the entire frontend repository.
- Generated `survey_frontend.md` and 5-component `handoff.md`.
- Sent final completion report to parent orchestrator.

## Artifact Index
- `survey_frontend.md` — Comprehensive architectural & mobile audit report (182 lines)
- `handoff.md` — 5-component handoff report for parent orchestrator (Hard handoff)
- `progress.md` — Liveness heartbeat and milestone tracker
- `DISPATCH.md` — Log of incoming instructions from parent
