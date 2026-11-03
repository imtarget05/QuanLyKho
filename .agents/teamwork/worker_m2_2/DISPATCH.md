## 2026-11-02T16:52:46Z
You are Worker 2 (Frontend Hardening & Concurrency Fixer) for Milestone 2 Iteration 2 of project QuanLyKho.
Your working directory is: /Users/mainguyenbinhtan/Downloads/QuanLyKho/.agents/teamwork/worker_m2_2/

MANDATORY FIRST STEP:
Read /Users/mainguyenbinhtan/Downloads/QuanLyKho/.agents/teamwork/ORIGINAL_REQUEST.md verbatim before writing any code.

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

Context & Challenge Feedback to Fix:
Gate Iteration 1 resulted in REQUEST_CHANGES from Challenger 1 and Challenger 2:
- Challenger 1 handoff: /Users/mainguyenbinhtan/Downloads/QuanLyKho/.agents/teamwork/challenger_m2_1/handoff.md
- Challenger 2 handoff: /Users/mainguyenbinhtan/Downloads/QuanLyKho/.agents/teamwork/challenger_m2_2/handoff.md
- Test harness with reproducers: `frontend/test/admin_promotion_banner_adversarial_test.dart`

File Ownership:
- `frontend/lib/src/core/widgets/admin_promotion_banner.dart`
- `frontend/lib/src/features/commerce/commerce_workspace.dart`
- `frontend/test/admin_promotion_banner_test.dart`
- `frontend/test/admin_promotion_banner_adversarial_test.dart`

Tasks to execute:
1. Concurrency Latch & Debounce (`frontend/lib/src/core/widgets/admin_promotion_banner.dart`):
   In `_AdminPromotionBannerState`:
   - Add state boolean: `bool _isActionTriggered = false;`
   - In `_handleRefresh()`:
     ```dart
     void _handleRefresh() {
       if (_isActionTriggered) return;
       _isActionTriggered = true;
       _countdownTimer?.cancel();
       _countdownTimer = null;
       widget.onRefresh();
     }
     ```
   - In `_handleDismiss()`:
     ```dart
     void _handleDismiss() {
       if (_isActionTriggered) return;
       _isActionTriggered = true;
       _countdownTimer?.cancel();
       _countdownTimer = null;
       if (widget.onDismiss != null) {
         widget.onDismiss!();
       }
     }
     ```
   - In the timer periodic callback when `_remainingSeconds <= 1`:
     ```dart
     if (_isActionTriggered) return;
     _isActionTriggered = true;
     _countdownTimer?.cancel();
     _countdownTimer = null;
     widget.onRefresh();
     ```
   This completely eliminates race conditions when user taps `[Làm mới ngay]` while countdown hits 0 or multi-taps rapidly.

2. Mobile Viewport 320px & Accessibility Font Scaling (`frontend/lib/src/core/widgets/admin_promotion_banner.dart`):
   - In `_buildCompactLayout()` around lines 213-222, replace the fixed `Row` of action buttons with:
     ```dart
     Wrap(
       alignment: WrapAlignment.end,
       crossAxisAlignment: WrapCrossAlignment.center,
       spacing: 8,
       runSpacing: 6,
       children: [
         if (widget.onDismiss != null) dismissButton,
         refreshButton,
       ],
     )
     ```
   This ensures that when available width < 318px (such as 320px canvas or enlarged accessibility text scaling), the action buttons wrap cleanly without any RenderFlex overflow.

3. Draft Safety Wiring (`frontend/lib/src/features/commerce/commerce_workspace.dart`):
   - In `CommerceWorkspace` around lines 413-431, pass `pauseCountdown`:
     e.g., `pauseCountdown: _isSessionRevokedDialogShowing` or ensure countdown pauses when modal dialogs are active.

4. Run Verification Commands:
   - `cd frontend && flutter test test/admin_promotion_banner_test.dart`
   - `cd frontend && flutter test test/admin_promotion_banner_adversarial_test.dart`
   - `cd frontend && flutter test test/user_sync_and_header_icons_test.dart test/root_role_update_test.dart test/homepage_subsystem_sync_test.dart`
   All tests must pass with exit code 0!

5. Write detailed `handoff.md` and message the orchestrator when complete.
