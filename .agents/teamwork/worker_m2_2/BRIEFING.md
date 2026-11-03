# BRIEFING — 2026-11-02T16:55:00Z

## Mission
Frontend Hardening & Concurrency Fixer for Milestone 2 Iteration 2: Eliminate race conditions/double-tap in AdminPromotionBanner, resolve 320px & accessibility font RenderFlex overflow via Wrap, wire pauseCountdown in CommerceWorkspace, and verify full test pass.

## 🔒 My Identity
- Archetype: worker
- Roles: implementer, qa
- Working directory: /Users/mainguyenbinhtan/Downloads/QuanLyKho/.agents/teamwork/worker_m2_2/
- Original parent: f96c6aba-c50c-476b-ba75-261e5bbc41a1
- Milestone: Milestone 2 (Mobile Viewport Parity & Admin Promotion Banner Hardening)

## 🔒 Key Constraints
- Integrity Mandate: genuine implementation only, no hardcoded or facade solutions.
- Follow Clean Architecture & Project conventions in QuanLyKho.
- File ownership:
  - frontend/lib/src/core/widgets/admin_promotion_banner.dart
  - frontend/lib/src/features/commerce/commerce_workspace.dart
  - frontend/test/admin_promotion_banner_test.dart
  - frontend/test/admin_promotion_banner_adversarial_test.dart
- All tests must pass with exit code 0.

## Current Parent
- Conversation ID: f96c6aba-c50c-476b-ba75-261e5bbc41a1
- Updated: 2026-11-02T16:55:00Z

## Task Summary
- **What to build**:
  1. Concurrency Latch & Debounce (`admin_promotion_banner.dart`): `_isActionTriggered` guard in `_handleRefresh`, `_handleDismiss`, and periodic timer callback.
  2. Mobile Viewport 320px & Font Scaling: Replace action `Row` with `Wrap` in `_buildCompactLayout()`.
  3. Draft Safety Wiring (`commerce_workspace.dart`): Pass `pauseCountdown` to `AdminPromotionBanner`.
  4. Test suite update: Update `admin_promotion_banner_adversarial_test.dart` and `admin_promotion_banner_test.dart` to assert that 320px no longer overflows, multi-tap and race at 0s are guarded against.
- **Success criteria**:
  - Zero RenderFlex overflows at 320px/375px/390px/414px with normal and 1.3x font scaling.
  - Exactly 1 invocation of `onRefresh()` even with spam tapping or simultaneous timer expiry.
  - Modal dialog active in CommerceWorkspace pauses countdown.
  - `flutter test` passes across test suites.

## Key Decisions Made
- [TBD]

## Artifact Index
- /Users/mainguyenbinhtan/Downloads/QuanLyKho/.agents/teamwork/worker_m2_2/DISPATCH.md
- /Users/mainguyenbinhtan/Downloads/QuanLyKho/.agents/teamwork/worker_m2_2/BRIEFING.md
- /Users/mainguyenbinhtan/Downloads/QuanLyKho/.agents/teamwork/worker_m2_2/progress.md
- /Users/mainguyenbinhtan/Downloads/QuanLyKho/.agents/teamwork/worker_m2_2/handoff.md

## Change Tracker
- **Files modified**: [TBD]
- **Build status**: pending
- **Pending issues**: none

## Quality Status
- **Build/test result**: pending
- **Lint status**: clean
- **Tests added/modified**: pending
