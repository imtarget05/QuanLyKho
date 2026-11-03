## 2026-11-02T15:56:04Z
You are a Worker agent for Frontend Milestones M1 & M2 (Homepage Revamp, Subsystem Sync, Mobile Viewport Parity & Component Fixes: F1 through F7) in project QuanLyKho.

Identity & Working Directory:
- Working directory: /Users/mainguyenbinhtan/Downloads/QuanLyKho/.agents/teamwork/worker_m1_m2_1
- Role: Frontend & Mobile Parity Worker
- Project root: /Users/mainguyenbinhtan/Downloads/QuanLyKho

Mandatory Input:
Read ORIGINAL_REQUEST.md at:
/Users/mainguyenbinhtan/Downloads/QuanLyKho/.agents/teamwork/ORIGINAL_REQUEST.md
Read PROJECT.md at:
/Users/mainguyenbinhtan/Downloads/QuanLyKho/PROJECT.md
Read Explorer 1's survey report at:
/Users/mainguyenbinhtan/Downloads/QuanLyKho/.agents/teamwork/explorer_survey_1/survey_frontend.md
and handoff report at:
/Users/mainguyenbinhtan/Downloads/QuanLyKho/.agents/teamwork/explorer_survey_1/handoff.md
Also read project conventions in:
/Users/mainguyenbinhtan/Downloads/QuanLyKho/AGENTS.md

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

Write Ownership (Exclusive):
- frontend/lib/src/features/commerce/commerce_workspace.dart
- frontend/lib/src/features/commerce/commerce_api.dart
- frontend/lib/src/features/commerce/commerce_memory_store.dart
- frontend/lib/src/features/commerce/commerce_reports_page.dart
- frontend/lib/src/features/auth/edit_profile_dialog.dart
- frontend/test/homepage_subsystem_sync_test.dart
- frontend/test/mobile_viewport_audit_test.dart

Objective:
Implement and complete Milestones M1 & M2 according to PROJECT.md and Explorer 1's blueprint:
1. Milestone M1 (Homepage Revamp & Subsystem Sync):
   - Review and polish the Overview tab (`_OverviewPage`) in `commerce_workspace.dart`:
     * Modern visual hierarchy with 6 KPI cards (Today's Revenue, Gross Profit, Total Inventory Valuation, Customer Receivables, Supplier Payables, Low-Stock items count).
     * Quick-action launcher cards leading into all 7 other subsystems (POS, Purchases, Inventory, Debt, Reports, Approvals, Settings).
   - Silent background freshness sync (periodic / tab-switch) without resetting user navigation tab or clearing active inputs.
   - HTTP 401 session revocation handling: display informative session refresh dialog ("Làm mới phiên") when `auth_version` invalidation occurs.
2. Milestone M2 (Mobile Viewport Parity & Bug Fixes: BUG-01 to BUG-12):
   - Fix BUG-01 & BUG-02: In `_WorkspaceTopbar`, on compact screens (<600px), eliminate the redundant `const Spacer()` that squashed title down to 51px. Ensure title gets >=140px of width and location chip is compact.
   - Fix BUG-03: Wrap `_MiniSummaryRow` card values in `FittedBox(fit: BoxFit.scaleDown, alignment: Alignment.centerLeft)` so numbers never clip on 375px/390px/414px viewports.
   - Fix BUG-04 to BUG-08: In modal dialogs (`_showCreateOrder`, `_showCreateProduct`, `_showStockTransferDialog`, `_showStocktake`, `edit_profile_dialog`), replace rigid width constraints (`width: 440`, `width: 420`, `width: 580`) on viewports <600px with responsive bottom sheets or full-screen dialogs where input fields stack vertically cleanly.
   - Fix BUG-09: Remove fixed `SizedBox(height: 480)` nested scroll in `_DebtPage`.
   - Fix BUG-10: In `commerce_reports_page.dart`, set `cols = 1` when screen width < 500px so cards don't cramp.
   - Fix BUG-11: Add `overflow: TextOverflow.ellipsis` to `_OrderListTile.partyName`.
   - Fix BUG-12: In mobile bottom navigation, show clear active indicators and "Quay lại Tổng quan" header when viewing sub-pages from the "Thêm" (More) tab.
3. Verification & Testing:
   - Run existing and new Flutter widget tests:
     `cd /Users/mainguyenbinhtan/Downloads/QuanLyKho/frontend && flutter test test/homepage_subsystem_sync_test.dart test/user_sync_and_header_icons_test.dart`
   - Create `frontend/test/mobile_viewport_audit_test.dart` testing 375x667, 390x844, and 414x896 canvas sizes, confirming zero RenderFlex overflows and title width >= 140px.
   - Run `flutter test test/mobile_viewport_audit_test.dart`.
4. Output Requirements:
   - Write handoff report in `/Users/mainguyenbinhtan/Downloads/QuanLyKho/.agents/teamwork/worker_m1_m2_1/handoff.md`.
   - Notify parent upon completion via `send_message`.

## 2026-11-02T16:48:00Z
**Context**: Status check on Frontend Milestones M1 & M2 (Homepage & Mobile Parity)
**Content**: We observed that `mobile_viewport_audit_test.dart` and `homepage_subsystem_sync_test.dart` have been created and tests executed. How is the implementation progressing? Are you ready to compile and deliver your final handoff report?
**Action**: Please update `progress.md` and deliver `handoff.md` with your test results.
