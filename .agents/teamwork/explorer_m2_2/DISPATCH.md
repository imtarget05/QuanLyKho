## 2026-11-02T16:00:19Z
Sender: f96c6aba-c50c-476b-ba75-261e5bbc41a1
Priority: MESSAGE_PRIORITY_HIGH

You are Explorer 2 (Frontend UI & Banner Component Specialist) for Milestone 2 of project QuanLyKho.
Your working directory is: /Users/mainguyenbinhtan/Downloads/QuanLyKho/.agents/teamwork/explorer_m2_2/
You MUST read the following authoritative files first:
1. /Users/mainguyenbinhtan/Downloads/QuanLyKho/.agents/teamwork/ORIGINAL_REQUEST.md (MANDATORY — read this verbatim before doing anything)
2. /Users/mainguyenbinhtan/Downloads/QuanLyKho/PROJECT.md
3. /Users/mainguyenbinhtan/Downloads/QuanLyKho/.agents/teamwork/explorer_1/handoff.md (predecessor exploration report)

Target codebase: /Users/mainguyenbinhtan/Downloads/QuanLyKho

Task:
Perform a deep, read-only technical investigation of the frontend workspace UI and notification presentation layer:
- `frontend/lib/src/features/commerce/commerce_workspace.dart`
- `frontend/lib/src/app/app_shell.dart`
- `frontend/lib/src/core/util/web_helpers_web.dart` and `web_helpers_stub.dart`
- `frontend/lib/src/core/util/role_visibility.dart`

Investigate and produce an actionable design for:
1. Admin Promotion Banner Component (`_AdminPromotionBanner`):
   - Placement in `CommerceWorkspace` (top banner above workspace tabs or sticky header banner) and/or `AppShell`.
   - Visual styling: enterprise branding, clear callout that Admin rights have been granted.
   - User interaction: prominent `[Làm mới ngay]` button (assigning ValueKey('btn-admin-promoted-refresh')) for manual immediate refresh.
   - Countdown auto-refresh: automatic countdown (5 seconds) displaying "Tự động làm mới trong X giây..." that executes refresh automatically when reaching 0, satisfying Acceptance Criteria: "Người dùng không cần tự phán đoán và thao tác reload trình duyệt thủ công để nhận quyền hạn mới".
2. Reload mechanisms:
   - In-app session refresh (updating `AuthService` state, reloading workspace data) vs browser page reload via `forceAppUpdate()`.
   - Preserving draft data or confirming before reloading if user is mid-action.
3. Mobile layout & accessibility:
   - Ensure banner renders cleanly on compact viewports (375px, 390px, 414px) as well as desktop without overflow errors.
4. Provide concrete widget tree integration points, state variables, and callbacks.

Rules:
- Read-only investigation: DO NOT modify source files.
- Update `progress.md` in your working directory with `Last visited: [timestamp]` at each step.
- Write `analysis.md` and `handoff.md` (Observation, Logic Chain, Caveats, Conclusion, Verification Method) in your working directory.
- When finished, send a message to the orchestrator with your summary and handoff path.
