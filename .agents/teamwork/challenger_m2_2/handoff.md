# Handoff Report — Challenger 2 (Adversarial Verifier: Mobile Viewports & Draft Resilience)

- **Agent**: Challenger 2 (`challenger_m2_2`)
- **Working Directory**: `/Users/mainguyenbinhtan/Downloads/QuanLyKho/.agents/teamwork/challenger_m2_2/`
- **Milestone**: Milestone 2 (Mobile Viewport Parity & Admin Promotion Banner)
- **Date**: 2026-11-02
- **Type**: Hard (Task Complete)
- **Verdict**: **REQUEST_CHANGES**

---

## 1. Observation

1. **Test Execution (`flutter test test/admin_promotion_banner_test.dart`)**:
   - Command: `cd /Users/mainguyenbinhtan/Downloads/QuanLyKho/frontend && flutter test test/admin_promotion_banner_test.dart`
   - Result: 8 passed, 0 failed in 2.0s. All 8 baseline tests authored by Worker 1 pass.

2. **Empirical Mobile Viewport Stress Testing (`frontend/test/admin_promotion_banner_adversarial_test.dart`)**:
   - Command: `cd /Users/mainguyenbinhtan/Downloads/QuanLyKho/frontend && flutter test test/admin_promotion_banner_adversarial_test.dart`
   - Results on target viewports:
     * **375px** (`375x667` & `375x812`): PASSES cleanly at 1.0x text scaling. However, margin is extremely tight (available inner width = `375 - 24 (margin) - 28 (padding) - 2 (border) = 321px`; required row width is ~318px, leaving only 3px margin).
     * **390px** (`390x844`): PASSES cleanly (available width = 336px).
     * **414px** (`414x896`): PASSES cleanly (available width = 360px).
     * **320px** (`320x568`): **FAILS with RenderFlex overflow** when both `[Để sau]` and `[Làm mới ngay]` are present:
       ```text
       Expected: null
         Actual: FlutterError:<A RenderFlex overflowed by 52 pixels on the right.>
       ```
     * **320px with 1.3x Accessibility Text Scaling**: **FAILS with RenderFlex overflow by 121 pixels**:
       ```text
       Expected: null
         Actual: FlutterError:<A RenderFlex overflowed by 121 pixels on the right.>
       ```

3. **Source Code Inspection — Action Row (`frontend/lib/src/core/widgets/admin_promotion_banner.dart:213-222`)**:
   - Lines 213-222:
     ```dart
     Row(
       mainAxisAlignment: MainAxisAlignment.end,
       children: [
         if (widget.onDismiss != null) ...[
           dismissButton,
           const SizedBox(width: 8),
         ],
         refreshButton,
       ],
     ),
     ```
   - On a 320px viewport, container horizontal margin is 12px each side (`24px`), horizontal padding is 14px each side (`28px`), and border is 1px each side (`2px`), yielding an available inner width of `320 - 54 = 266px`.
   - `dismissButton` (~78px) + `SizedBox(width: 8)` (8px) + `refreshButton` (~150px) requires 318px. Because it is wrapped in an inflexible `Row`, it overflows 266px by exactly `52px`.

4. **Source Code Inspection — Draft Resilience in Workspace (`frontend/lib/src/features/commerce/commerce_workspace.dart:412-431`)**:
   - `AdminPromotionBanner` declares `final bool pauseCountdown;` (default `false`).
   - In `CommerceWorkspace` (`commerce_workspace.dart:412-431`), the banner is mounted as:
     ```dart
     if (auth?.adminRolePromoted == true || _isAdminPromotionPending)
       AdminPromotionBanner(
         onRefresh: () async {
           setState(() => _isAdminPromotionPending = false);
           if (auth != null) {
             await auth.applyAdminPromotionAndRefresh();
           }
           if (widget.onRefresh != null) {
             await widget.onRefresh!();
           } else if (widget.api != null) {
             try {
               await widget.api!.reload(widget.store);
             } catch (_) {}
           }
         },
         onDismiss: () {
           setState(() => _isAdminPromotionPending = false);
           auth?.dismissAdminPromotionBanner();
         },
       ),
     ```
   - `pauseCountdown` is **never passed** by `CommerceWorkspace`. It defaults to `false`.
   - When a user is in an active modal dialog (such as `_showCreateOrder`, stock transfer, or stocktake), the countdown timer continues ticking unconditionally. At 0s, `reload(widget.store)` is invoked, calling `store.replaceSnapshot(...)` which clears `_reserved`, `_stocktakes`, etc. beneath the active dialog.

---

## 2. Logic Chain

1. **Viewport Parity Requirement**: Milestone 2 and the dispatch mission explicitly demand verifying viewport extremes: *"Does AdminPromotionBanner adapt cleanly on 320px, 375px, 390px, 414px without any RenderFlex overflow?"*
2. **Empirical Evidence of Overflow**: The adversarial test suite `admin_promotion_banner_adversarial_test.dart` reproduces a 52px horizontal RenderFlex overflow on 320px viewports (and 121px under 1.3x text scaling) because the action button container uses an unconstrained `Row` instead of `Wrap` or vertical stacking.
3. **Draft Safety Requirement**: The dispatch mission asks: *"Does pauseCountdown: true completely stop auto-refresh when user has an active draft or modal dialog open?"*
4. **Draft Safety Evaluation**:
   - Inside the isolated `AdminPromotionBanner` component, `pauseCountdown: true` does stop auto-refresh indefinitely, freezes countdown ticks, and resumes without resetting.
   - However, in `CommerceWorkspace`, `pauseCountdown` was never plumbed to `AdminPromotionBanner`. In an integrated environment, background auto-refresh is never paused during modal dialogs or draft entries, defeating the safety mechanism.
5. **Verdict**: Because 320px viewport has a reproducible RenderFlex overflow and `pauseCountdown` is omitted in `CommerceWorkspace`, the solution does not yet satisfy mobile extremes and draft resilience. The verdict is **REQUEST_CHANGES**.

---

## 3. Caveats

- On standard modern mobile devices (375px iPhone SE 2/3, 390px iPhone 12/13/14, 414px iPhone Plus/XR), the banner renders without overflow at 1.0x text scaling. The overflow specifically affects 320px screens (iPhone SE 1st gen, small Android devices, split-screen mobile) and users with accessibility text scaling (>=1.2x).
- The dialog on top of the Navigator does not immediately crash when `onRefresh` fires, but background data reload (`replaceSnapshot`) invalidates in-memory store collections while the user is editing.

---

## 4. Conclusion & Required Actions

**Verdict: REQUEST_CHANGES**

Worker 1 should apply two targeted fixes:

1. **Fix RenderFlex overflow on 320px / accessibility font scaling**:
   In `frontend/lib/src/core/widgets/admin_promotion_banner.dart` (lines 213-222), replace the `Row` with `Wrap`:
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
   This ensures that when inner width < 318px (such as 320px screens or enlarged text scaling), the action buttons wrap cleanly without overflowing.

2. **Plumb `pauseCountdown` in `CommerceWorkspace`**:
   In `frontend/lib/src/features/commerce/commerce_workspace.dart` (lines 413-431), pass `pauseCountdown`:
   Detect if a dialog or draft is active (e.g., track modal dialog state or pass `pauseCountdown: ...`) so that user inputs are not disturbed by background reload.

---

## 5. Verification Method

To verify these findings independently:

```bash
cd /Users/mainguyenbinhtan/Downloads/QuanLyKho/frontend

# 1. Run baseline worker test suite (8 tests pass)
flutter test test/admin_promotion_banner_test.dart

# 2. Run adversarial challenger test suite (12 tests pass, reproducing 52px and 121px overflows on 320px and asserting pauseCountdown contracts)
flutter test test/admin_promotion_banner_adversarial_test.dart

# 3. Analyze code quality
flutter analyze test/admin_promotion_banner_adversarial_test.dart test/admin_promotion_banner_test.dart lib/src/core/widgets/admin_promotion_banner.dart
```
