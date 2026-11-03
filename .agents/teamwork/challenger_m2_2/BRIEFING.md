# BRIEFING — 2026-11-02T16:50:00Z

## Mission
Adversarially challenge and stress-test Milestone 2 artifacts: Mobile viewport extremes (320px, 375px, 390px, 414px) and Draft resilience / countdown pause safety for AdminPromotionBanner and CommerceWorkspace.

## 🔒 My Identity
- Archetype: empirical challenger
- Roles: critic, specialist
- Working directory: /Users/mainguyenbinhtan/Downloads/QuanLyKho/.agents/teamwork/challenger_m2_2/
- Original parent: f96c6aba-c50c-476b-ba75-261e5bbc41a1
- Milestone: Milestone 2
- Instance: Challenger 2 of 2

## 🔒 Key Constraints
- Review-only — do NOT modify implementation code
- Empirical verification mandatory — must run tests and stress test harnesses myself
- Record findings in handoff.md and send structured message to parent

## Current Parent
- Conversation ID: f96c6aba-c50c-476b-ba75-261e5bbc41a1
- Updated: 2026-11-02T16:50:00Z

## Review Scope
- **Files reviewed**:
  * `frontend/lib/src/features/auth/auth_service.dart`
  * `frontend/lib/src/core/widgets/admin_promotion_banner.dart`
  * `frontend/lib/src/features/commerce/commerce_workspace.dart`
  * `frontend/test/admin_promotion_banner_test.dart`
- **Interface contracts**: `/Users/mainguyenbinhtan/Downloads/QuanLyKho/PROJECT.md`
- **Review criteria**:
  1. Mobile viewport extremes: 320px, 375px, 390px, 414px without RenderFlex overflow
  2. Draft safety: pauseCountdown: true stops auto-refresh during active draft or modal dialog
  3. Flutter test execution & results

## Attack Surface
- **Hypotheses tested**:
  * Viewport extremes (320px, 375px, 390px, 414px) with both buttons and single button
  * Viewport 320px under accessibility text scaling (1.3x)
  * Viewport 320px inside CommerceWorkspace
  * `pauseCountdown: true` in AdminPromotionBanner (timer pausing, remaining seconds freezing, manual refresh)
  * `CommerceWorkspace` integration with `AdminPromotionBanner` during active dialogs
- **Vulnerabilities found**:
  1. RenderFlex overflow by 52px on 320px screens when both action buttons are present (and 121px under 1.3x text scaling) due to unconstrained `Row` at `admin_promotion_banner.dart:213`.
  2. `pauseCountdown` is never passed by `CommerceWorkspace` (`commerce_workspace.dart:413`), meaning auto-refresh is never paused during active modals/drafts in real workspace usage.
- **Untested angles**: None.

## Loaded Skills
- None requested in dispatch

## Key Decisions Made
- Formulated verdict: **REQUEST_CHANGES** based on empirical reproducibility of 52px RenderFlex overflow on 320px and missing `pauseCountdown` wiring in `CommerceWorkspace`.
- Authored test oracle in `frontend/test/admin_promotion_banner_adversarial_test.dart` capturing the exact bugs and verifying baseline contracts.

## Artifact Index
- `DISPATCH.md` — Inbound dispatch instructions
- `BRIEFING.md` — Working state and identity
- `progress.md` — Execution steps completed
- `handoff.md` — Comprehensive 5-component report with verdict and exact code lines
- `frontend/test/admin_promotion_banner_adversarial_test.dart` — Reproducible adversarial test suite
