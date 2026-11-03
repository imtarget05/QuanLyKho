## 2026-11-02T16:06:49Z

You are Worker M2 (Frontend & Mobile Parity Implementer) for Milestone M2 of project QuanLyKho.

Identity & Working Directory:
- Working directory: /Users/mainguyenbinhtan/Downloads/QuanLyKho/.agents/teamwork/worker_m2
- Role: Frontend & Mobile Parity Worker
- Target codebase: /Users/mainguyenbinhtan/Downloads/QuanLyKho

MANDATORY INPUTS — Read these first before touching any code:
1. /Users/mainguyenbinhtan/Downloads/QuanLyKho/.agents/teamwork/ORIGINAL_REQUEST.md (MANDATORY — read this verbatim)
2. /Users/mainguyenbinhtan/Downloads/QuanLyKho/PROJECT.md
3. /Users/mainguyenbinhtan/Downloads/QuanLyKho/TEST_INFRA.md
4. /Users/mainguyenbinhtan/Downloads/QuanLyKho/.agents/teamwork/explorer_survey_1/survey_frontend.md (Authoritative detailed findings for BUG-01 through BUG-12)
5. /Users/mainguyenbinhtan/Downloads/QuanLyKho/AGENTS.md

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

Exclusive Write Ownership:
- frontend/lib/src/features/commerce/commerce_workspace.dart
- frontend/lib/src/features/commerce/commerce_reports_page.dart
- frontend/lib/src/features/settings/widgets/edit_profile_dialog.dart (or wherever edit_profile_dialog.dart is located)
- frontend/test/mobile_viewport_audit_test.dart

Tasks:
1. Fix BUG-01 & BUG-02 in `_WorkspaceTopbar` (`commerce_workspace.dart`):
   - In `_WorkspaceTopbar`, on compact screens (<600px), eliminate the redundant `const Spacer()` that squashed the page title down to ~51px. Ensure the title receives >= 140px width and is never squashed.
   - Adjust warehouse location chip (`_locationChip`) so it renders an icon and compact name without truncating aggressively or squeezing the title.
2. Fix BUG-03 in `_MiniSummaryRow` (`commerce_workspace.dart`):
   - Wrap summary card values in `FittedBox(fit: BoxFit.scaleDown, alignment: Alignment.centerLeft)` so numbers like `125.400.000 ₫` never clip or truncate on 375px/390px/414px viewports.
3. Fix BUG-04 (`_showCreateOrder` in `commerce_workspace.dart`):
   - In the create order dialog, when viewport width < 600px, adapt the product row and lot/expiry chips into a responsive layout (vertical column or wrap) so SKU/product dropdown and quantity don't crush or overflow.
4. Fix BUG-05 (`_showCreateProduct` in `commerce_workspace.dart`):
   - Replace hardcoded `SizedBox(width: 440)` with responsive constraints (`constraints.maxWidth < 600 ? double.infinity : 440`) and stack side-by-side inputs vertically on mobile.
5. Fix BUG-06 (`_showStockTransferDialog` in `commerce_workspace.dart`):
   - Replace hardcoded `width: 420` with responsive constraints and adapt warehouse source/dest selectors for mobile.
6. Fix BUG-07 (`_showStocktake` in `commerce_workspace.dart`):
   - Replace hardcoded `width: 580` and the cramped 4-column row table with a clean responsive card/list layout per item on mobile viewports so users can comfortably enter physical counts without `TextFormField` being squished.
8. Fix BUG-08 (`EditProfileDialog` in `edit_profile_dialog.dart`):
   - Replace hardcoded `width: 480` with responsive constraints.
9. Fix BUG-09 (`_DebtPage` in `commerce_workspace.dart`):
   - Remove fixed `SizedBox(height: 480)` nested scroll in `_DebtPage` to prevent touch scroll trapping.
10. Fix BUG-10 (`CommerceReportsPage` in `commerce_reports_page.dart`):
    - Set `cols = 1` when screen width < 500px so KPI cards don't cramp.
11. Fix BUG-11 (`_OrderListTile` in `commerce_workspace.dart`):
    - Add `maxLines: 1` and `overflow: TextOverflow.ellipsis` to `order.partyName`.
12. Fix BUG-12 (Mobile Bottom Nav & More Sheet in `commerce_workspace.dart`):
    - Show clear active indicators and "Quay lại Tổng quan" / navigation clarity when viewing sub-pages from the "Thêm" (More) tab.
13. Comprehensive Verification Test Suite:
    - Author `frontend/test/mobile_viewport_audit_test.dart` with comprehensive Flutter widget tests:
      * Test canvases 375x667 (iPhone SE), 390x844 (iPhone 12/13/14), 414x896 (iPhone XR/11).
      * Verify zero RenderFlex overflows on each screen.
      * Verify title width >= 140px on compact screens.
      * Verify dialogs open cleanly without overflow on 375px width.
14. Execute tests:
    - Run `flutter test test/mobile_viewport_audit_test.dart`
    - Run `flutter test test/homepage_subsystem_sync_test.dart`
    - Report full test output and logs.
15. Output Requirements:
    - Update `progress.md` in your working directory with timestamps.
    - Write complete handoff report in `/Users/mainguyenbinhtan/Downloads/QuanLyKho/.agents/teamwork/worker_m2/handoff.md`.
    - Notify orchestrator with `send_message`.


## 2026-11-02T16:19:01Z
[Message] timestamp=2026-11-02T16:19:01Z sender=20f69e0b-87ee-497a-9906-986d3f7b03f8 priority=MESSAGE_PRIORITY_HIGH content=**Context**: Milestone M2 Mobile Viewport Parity
**Content**: Heartbeat check at 10 minutes. Please report your current progress on BUG-01..12 and test authoring.
**Action**: Update progress.md and reply with status.


## 2026-11-02T16:29:04Z
[Message] timestamp=2026-11-02T16:29:04Z sender=20f69e0b-87ee-497a-9906-986d3f7b03f8 priority=MESSAGE_PRIORITY_HIGH content=**Context**: Milestone M2 Implementation
**Content**: Heartbeat check at iteration 3. Please update on current step (BUG-01/02, BUG-04, BUG-07, BUG-12, or test authoring).
**Action**: Update progress.md with your latest step.

## 2026-11-02T16:39:20Z
[Message] timestamp=2026-11-02T16:39:20Z sender=20f69e0b-87ee-497a-9906-986d3f7b03f8 priority=MESSAGE_PRIORITY_HIGH content=**Context**: Milestone M2 Mobile Viewport Parity
**Content**: Heartbeat tick 4. Detected mobile_viewport_audit_test.dart created. How are test results and handoff preparation progressing?
**Action**: Reply with current test status.
