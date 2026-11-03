## 2026-11-02T16:04:04Z
You are Explorer 3 (Frontend Test Harness & Verification Specialist) for Milestone 2 of project QuanLyKho.
Your working directory is: /Users/mainguyenbinhtan/Downloads/QuanLyKho/.agents/teamwork/explorer_m2_3/
You MUST read the following authoritative files first:
1. /Users/mainguyenbinhtan/Downloads/QuanLyKho/.agents/teamwork/ORIGINAL_REQUEST.md (MANDATORY — read this verbatim before doing anything)
2. /Users/mainguyenbinhtan/Downloads/QuanLyKho/PROJECT.md
3. /Users/mainguyenbinhtan/Downloads/QuanLyKho/.agents/teamwork/explorer_1/handoff.md (predecessor exploration report)

Target codebase: /Users/mainguyenbinhtan/Downloads/QuanLyKho

Task:
Perform a deep, read-only technical investigation of the frontend test infrastructure:
- `frontend/pubspec.yaml`
- `frontend/test/user_sync_and_header_icons_test.dart`
- `frontend/test/root_role_update_test.dart`
- `frontend/test/` test conventions, mocks, and widget test harnesses.

Investigate and produce an actionable design for:
1. Flutter widget test architecture for role detection and refresh:
   - How `AuthService` or its mock can be controlled inside `testWidgets(...)` to simulate a dynamic role promotion event (e.g., user is `staff`, then role promotion event occurs).
   - How to verify that `_AdminPromotionBanner` renders with exact text *"Tài khoản của bạn đã được nâng cấp lên Quản Trị Viên (Admin)"*.
   - How to verify the `[Làm mới ngay]` button (Key: `btn-admin-promoted-refresh`) triggers refresh when tapped.
   - How to test the 5-second countdown timer safely in Flutter testing using `tester.pump(const Duration(seconds: 1))` without leaking timers or causing `pumpAndSettle` timeout.
   - How to verify that after refresh, admin capabilities are verified: `RoleVisibility.isAdmin(user.roles) == true`, and admin-gated widgets (like Employee Management / Reports) become unlocked.
2. Tooling & execution commands:
   - Identify the exact `flutter test` command, required environment variables, and execution duration.
3. Edge case coverage:
   - User dismisses banner or postpones reload.
   - Rapid repeated role updates.
   - Offline or failing network during reload.
