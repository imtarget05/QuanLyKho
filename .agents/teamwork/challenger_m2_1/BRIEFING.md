# BRIEFING — 2026-11-02T16:48:00Z

## Mission
Adversarially challenge and stress-test Milestone 2 (AdminPromotionBanner & Auth integration), specifically lifecycle, timer leakage, race conditions, and concurrency between countdown timeout and manual user tap.

## 🔒 My Identity
- Archetype: challenger (Empirical Challenger)
- Roles: critic, specialist
- Working directory: /Users/mainguyenbinhtan/Downloads/QuanLyKho/.agents/teamwork/challenger_m2_1/
- Original parent: f96c6aba-c50c-476b-ba75-261e5bbc41a1
- Milestone: milestone_2
- Instance: 1 of 1

## 🔒 Key Constraints
- Review-only — do NOT modify production implementation code directly (findings report to worker/orchestrator)
- Must empirically reproduce and verify claims through test execution; unverified claims do not count
- Do not write source code or tests into `.agents/teamwork/`
- Formulate explicit verdict: APPROVE or REQUEST_CHANGES

## Current Parent
- Conversation ID: f96c6aba-c50c-476b-ba75-261e5bbc41a1
- Updated: 2026-11-02T16:44:00Z

## Review Scope
- **Files to review**:
  * `frontend/lib/src/features/auth/auth_service.dart`
  * `frontend/lib/src/core/widgets/admin_promotion_banner.dart`
  * `frontend/lib/src/features/commerce/commerce_workspace.dart`
  * `frontend/test/admin_promotion_banner_test.dart`
- **Interface contracts**: `/Users/mainguyenbinhtan/Downloads/QuanLyKho/PROJECT.md`, `/Users/mainguyenbinhtan/Downloads/QuanLyKho/.agents/teamwork/ORIGINAL_REQUEST.md`
- **Review criteria**: Concurrency & race conditions, lifecycle management & timer leaks, correctness, edge cases.

## Key Decisions Made
- Executed `flutter test test/admin_promotion_banner_test.dart` (8 passed).
- Created empirical stress harness `test/admin_promotion_banner_adversarial_test.dart` testing 5 adversarial scenarios.
- Empirically confirmed race condition: `onRefresh` is invoked multiple times (2 calls on countdown expire + user tap; 3 calls on rapid multi-tap).
- Formulated verdict: REQUEST_CHANGES.

## Artifact Index
- `DISPATCH.md` — Inbound messages log
- `BRIEFING.md` — Persistent state and attack surface
- `progress.md` — Liveness heartbeat
- `handoff.md` — 5-component handoff report with verdict
- `frontend/test/admin_promotion_banner_adversarial_test.dart` — Empirical reproduction harness

## Attack Surface
- **Hypotheses tested**:
  * H1 (Race condition / duplicate execution): Tapping `[Làm mới ngay]` simultaneously or after countdown expires causes double `onRefresh` invocation. -> CONFIRMED (Test failed with Expected: <1>, Actual: <2>).
  * H2 (Multi-tap reentrancy): Rapidly tapping `[Làm mới ngay]` triggers duplicate `onRefresh` calls without debounce/latch. -> CONFIRMED (Test failed with Expected: <1>, Actual: <3>).
  * H3 (Timer leakage on rapid unmount/remount): Rapid mount and unmount during countdown leaks timers or throws exceptions. -> DISPROVEN (Widget properly cancels timer in `dispose()`; passed 10 rapid cycles with 0 exceptions).
  * H4 (Dismiss post-refresh): Tapping `[Để sau]` after countdown expires invokes `onDismiss` after `onRefresh`. -> CONFIRMED (Both callbacks fire).
- **Vulnerabilities found**:
  * V1: Missing execution latch / idempotency flag (`_hasTriggered`) in `_AdminPromotionBannerState`.
  * V2: `AuthService.checkUserRoleUpdate()` treats any HTTP 401 on `GET /auth/me` as admin promotion.
- **Untested angles**:
  * Web browser background tab throttling of `Timer.periodic`.

## Loaded Skills
- None specified by orchestrator dispatch.
