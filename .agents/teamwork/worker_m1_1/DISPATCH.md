## 2026-11-02T15:09:25Z

You are a Worker agent for Milestone M1 (Homepage Revamp & Subsystem Synchronization: F1, F2, F3) in project QuanLyKho.

Identity & Working Directory:
- Working directory: /Users/mainguyenbinhtan/Downloads/QuanLyKho/.agents/teamwork/worker_m1_1
- Role: Homepage Revamp & Subsystem Sync Worker
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

Write Ownership (Exclusive to this Worker):
- frontend/lib/src/features/commerce/commerce_workspace.dart (Overview tab, quick navigation, session refresh hook)
- frontend/lib/src/features/commerce/commerce_api.dart
- frontend/lib/src/features/commerce/commerce_memory_store.dart
- backend/app/api/routes/admin_users.py
- backend/tests/test_admin_role_email_notification.py
- frontend/test/homepage_subsystem_sync_test.dart

Objective:
Implement Milestone M1 according to the specifications in PROJECT.md and Explorer 1's blueprint:
1. Feature F1 - Modern Homepage Revamp:
   - In `frontend/lib/src/features/commerce/commerce_workspace.dart` (Overview tab `_OverviewPage`):
     * Redesign the overview tab into a modern, intuitive, and responsive dashboard.
     * Render operational KPI cards: Today's Revenue (`todayRevenue`), Gross Profit (`grossProfitToday`), Inventory Value (`inventoryValue`), Customer Receivables (`customerReceivables`), Supplier Payables (`supplierPayables`), and Low Stock Items (`lowStockItemsCount`).
     * Ensure cards use clean gradient or bordered cards with icon, trend badge, and formatted currency/numbers.
     * Add quick-action subsystem launch tiles directly on the homepage leading into all other 7 subsystems: Bán hàng (POS), Nhập hàng (Purchases), Kho hàng (Inventory), Công nợ (Debt), Báo cáo (Reports), Phê duyệt (Approvals), Cấu hình (Settings).
2. Feature F2 - Real-Time Subsystem Data Freshness:
   - In `CommerceWorkspace` and `CommerceApi`:
     * Introduce automatic background data reload (every 60 seconds or on tab resume if stale > 30s) calling `widget.api.reload(widget.store)`.
     * Ensure background reloads are silent (no full-screen spinners) and preserve the user's active tab, scroll position, and open modal state.
3. Feature F3 - Admin Role Change Notification & Session Refresh:
   - In `backend/app/api/routes/admin_users.py` (`update_user_roles`):
     * When `user.auth_version` is incremented, invoke `email_service.send_email(...)` to send an informative HTML notification to `user.email` detailing the updated roles. Wrap in try/except so SMTP failures do not prevent database transaction commit.
   - In `frontend/lib/src/features/commerce/commerce_api.dart` and `commerce_workspace.dart`:
     * Handle HTTP 401 errors. When 401 returns detail containing "Phiên đăng nhập đã bị thu hồi" or role update message, display a non-disruptive dialog ("Quyền tài khoản đã thay đổi. Vui lòng làm mới phiên đăng nhập để tiếp tục") with a "Làm mới phiên" action button that invokes session refresh.
4. Verification & Testing:
   - Backend: Create and run `backend/tests/test_admin_role_email_notification.py` verifying that role update enqueues outbox and triggers email service call.
   - Frontend: Create and run `frontend/test/homepage_subsystem_sync_test.dart` verifying Overview dashboard rendering, KPI cards, and subsystem navigation callbacks.
   - Run:
     `cd /Users/mainguyenbinhtan/Downloads/QuanLyKho/backend && pytest tests/test_admin_role_email_notification.py -v`
     `cd /Users/mainguyenbinhtan/Downloads/QuanLyKho/frontend && flutter test test/homepage_subsystem_sync_test.dart`

Output Requirements:
- Write handoff report in:
  /Users/mainguyenbinhtan/Downloads/QuanLyKho/.agents/teamwork/worker_m1_1/handoff.md
- Include: Observation, Logic Chain, Changes Made, Test Commands & Results, Verification.
- Notify parent upon completion via send_message.
