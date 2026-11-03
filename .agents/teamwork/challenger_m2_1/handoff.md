# Handoff Report — Challenger 1 (Adversarial Verifier: Lifecycle & Concurrency)

- **Agent**: Challenger 1 (`challenger_m2_1`)
- **Working Directory**: `/Users/mainguyenbinhtan/Downloads/QuanLyKho/.agents/teamwork/challenger_m2_1/`
- **Milestone**: Milestone 2 (Admin Promotion Banner & Auth Integration)
- **Verdict**: **REQUEST_CHANGES**
- **Date**: 2026-11-02
- **Type**: Hard (Task Complete)

---

## 1. Observation

### 1.1 Source Code Inspection
In `/Users/mainguyenbinhtan/Downloads/QuanLyKho/frontend/lib/src/core/widgets/admin_promotion_banner.dart`:
- Lines 52–73:
```dart
    _countdownTimer = Timer.periodic(const Duration(seconds: 1), (timer) {
      if (!mounted) {
        timer.cancel();
        return;
      }
      if (widget.pauseCountdown) {
        return;
      }
      if (_remainingSeconds <= 1) {
        timer.cancel();
        _countdownTimer = null;
        setState(() {
          _remainingSeconds = 0;
        });
        widget.onRefresh();
      } else {
        setState(() {
          _remainingSeconds--;
        });
      }
    });
```
- Lines 95–99:
```dart
  void _handleRefresh() {
    _countdownTimer?.cancel();
    _countdownTimer = null;
    widget.onRefresh();
  }
```
- Lines 101–107:
```dart
  void _handleDismiss() {
    _countdownTimer?.cancel();
    _countdownTimer = null;
    if (widget.onDismiss != null) {
      widget.onDismiss!();
    }
  }
```
- Lines 127–139:
```dart
    final refreshButton = FilledButton.icon(
      key: const ValueKey('btn-admin-promoted-refresh'),
      onPressed: _handleRefresh,
      icon: const Icon(Icons.refresh_rounded, size: 16),
      label: const Text('Làm mới ngay'),
      style: FilledButton.styleFrom(
        backgroundColor: const Color(0xFFFBBF24),
        foregroundColor: const Color(0xFF1E1B4B),
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 9),
        textStyle: const TextStyle(fontWeight: FontWeight.bold, fontSize: 13),
      ),
    );
```

### 1.2 Calling Context Inspection
In `/Users/mainguyenbinhtan/Downloads/QuanLyKho/frontend/lib/src/features/commerce/commerce_workspace.dart` lines 413–426:
```dart
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

### 1.3 Empirical Reproduction
Executed custom adversarial harness `/Users/mainguyenbinhtan/Downloads/QuanLyKho/frontend/test/admin_promotion_banner_adversarial_test.dart` via:
```bash
cd /Users/mainguyenbinhtan/Downloads/QuanLyKho/frontend && flutter test test/admin_promotion_banner_adversarial_test.dart
```

**Verbatim Output & Failures**:
```
00:00 +0: AdminPromotionBanner Adversarial Stress & Concurrency Suite Adversarial 1: Countdown hits 0, user taps [Làm mới ngay] while still mounted -> checks for duplicate onRefresh
══╡ EXCEPTION CAUGHT BY FLUTTER TEST FRAMEWORK ╞════════════════════════════════════════════════════
The following TestFailure was thrown running a test:
Expected: <1>
  Actual: <2>
Race condition failure: onRefresh was called twice when user tapped refresh at/after countdown
reached 0!
...
The test description was: Adversarial 1: Countdown hits 0, user taps [Làm mới ngay] while still mounted -> checks for duplicate onRefresh

00:00 +0 -1: AdminPromotionBanner Adversarial Stress & Concurrency Suite Adversarial 2: Rapid multi-tap on [Làm mới ngay] -> checks if duplicate execution is allowed or guarded
══╡ EXCEPTION CAUGHT BY FLUTTER TEST FRAMEWORK ╞════════════════════════════════════════════════════
The following TestFailure was thrown running a test:
Expected: <1>
  Actual: <3>
Concurrency failure: multi-tapping [Làm mới ngay] invoked onRefresh multiple times (3)!
...
The test description was: Adversarial 2: Rapid multi-tap on [Làm mới ngay] -> checks if duplicate execution is allowed or guarded

00:00 +0 -2: AdminPromotionBanner Adversarial Stress & Concurrency Suite Adversarial 3: Rapid unmount and remount during active countdown -> checks timer leaks & exceptions [PASSED]
00:00 +1 -2: AdminPromotionBanner Adversarial Stress & Concurrency Suite Adversarial 4: Tap [Để sau] after countdown reached 0 -> does it trigger onDismiss or cancel anything?
>>> Adversarial 4 Result: dismissCount = 1, refreshCount = 1 [BOTH FIRED]
00:01 +2 -2: AdminPromotionBanner Adversarial Stress & Concurrency Suite Adversarial 5: Rapid toggle of pauseCountdown at countdown boundary [PASSED]
```

---

## 2. Logic Chain

1. **Absence of Idempotency Guard**: Observation 1.1 reveals that `_AdminPromotionBannerState` maintains state `_remainingSeconds` and `_countdownTimer`, but lacks any boolean latch or idempotency flag (e.g. `_hasTriggered`).
2. **Race Window on Countdown Expiration**: When the 1-second periodic timer decrements to `<= 1`, it cancels `_countdownTimer` and immediately calls `widget.onRefresh()`. However, the widget remains in the tree with button `[Làm mới ngay]` enabled (`onPressed: _handleRefresh`).
3. **Double Execution Verified**: Observation 1.3 empirically proves that if a user taps `[Làm mới ngay]` when or after countdown reaches 0 while `onRefresh` is in flight, `_handleRefresh()` invokes `widget.onRefresh()` a second time (`Actual: <2>`).
4. **Multi-Tap Reentrancy**: Observation 1.3 additionally demonstrates that rapid multi-tapping / button spamming on `[Làm mới ngay]` triggers `onRefresh` on every tap (`Actual: <3>`), lacking debounce or click locking.
5. **Caller Impact**: Observation 1.2 demonstrates that in `CommerceWorkspace`, `onRefresh` performs asynchronous state promotion and full store reload via `widget.api!.reload(widget.store)`. Duplicate or concurrent calls trigger redundant network requests and concurrent state mutations.
6. **Dismiss Post-Refresh**: When countdown finishes and calls `onRefresh()`, tapping `[Để sau]` subsequently invokes `onDismiss()` as well, resulting in inconsistent dismissal state after a successful refresh.
7. **Lifecycle & Timer Leak Assessment**: On the positive side, Observation 1.3 (Adversarial 3) confirms that `AdminPromotionBannerState.dispose()` properly cancels `_countdownTimer?.cancel()`, surviving 10 rapid mount/unmount cycles without timer leaks or unhandled framework exceptions.

---

## 3. Caveats

- **Network Timing**: The exact duration `AdminPromotionBanner` stays mounted after `onRefresh()` is triggered depends on how quickly `AuthService.applyAdminPromotionAndRefresh()` updates state and triggers a rebuild in the parent. However, even if `applyAdminPromotionAndRefresh()` is fast, user tap events scheduled in the same event loop tick or right at countdown expiry will trigger duplicate execution.
- **Role Watcher HTTP 401 Assumption**: In `frontend/lib/src/features/auth/auth_service.dart` lines 1216–1235, `checkUserRoleUpdate()` treats any HTTP 401 response from `GET /auth/me` on a non-admin session as an admin promotion. If a session is invalidated due to password reset, explicit admin session revocation, or token expiration, the UI will incorrectly display the Admin Promotion Banner and grant local admin privileges in memory until the next backend request rejects with 401. This is noted as a secondary finding for the Worker.

---

## 4. Conclusion

**Verdict: REQUEST_CHANGES**

The implementation succeeds at responsive rendering, UI presentation, and timer disposal on unmount, but fails critical concurrency and race condition requirements:
1. **CRITICAL**: No execution guard against concurrent/duplicate `onRefresh()` calls when auto-countdown finishes simultaneously with user tap (`Actual: <2>`).
2. **HIGH**: No click debounce or latch on `[Làm mới ngay]` — multi-tapping triggers multiple `onRefresh()` invocations (`Actual: <3>`).
3. **MEDIUM**: Tapping `[Để sau]` after auto-refresh triggers `onDismiss()` post-refresh.

### Required Changes for Worker (`worker_m2_1`):
In `frontend/lib/src/core/widgets/admin_promotion_banner.dart`:
1. Add a single-flight latch in `_AdminPromotionBannerState`:
   ```dart
   bool _hasTriggered = false;
   ```
2. In `_startTimer()` when countdown reaches `<= 1`:
   ```dart
   if (_hasTriggered) return;
   _hasTriggered = true;
   timer.cancel();
   _countdownTimer = null;
   setState(() {
     _remainingSeconds = 0;
   });
   widget.onRefresh();
   ```
3. In `_handleRefresh()`:
   ```dart
   if (_hasTriggered) return;
   _hasTriggered = true;
   _countdownTimer?.cancel();
   _countdownTimer = null;
   widget.onRefresh();
   ```
4. In `_handleDismiss()`:
   ```dart
   if (_hasTriggered) return;
   _hasTriggered = true;
   _countdownTimer?.cancel();
   _countdownTimer = null;
   if (widget.onDismiss != null) {
     widget.onDismiss!();
   }
   ```
5. In `build()`, disable `onPressed` when `_hasTriggered == true`:
   ```dart
   onPressed: _hasTriggered ? null : _handleRefresh,
   ```

---

## 5. Verification Method

To independently reproduce and verify this finding:

```bash
cd /Users/mainguyenbinhtan/Downloads/QuanLyKho/frontend

# 1. Run the adversarial stress & concurrency test suite:
flutter test test/admin_promotion_banner_adversarial_test.dart
```

**Expected verification failure**:
- Test `Adversarial 1` fails with `Expected: <1>, Actual: <2>`
- Test `Adversarial 2` fails with `Expected: <1>, Actual: <3>`

**Post-fix invalidation condition**:
Once the worker implements the `_hasTriggered` latch, running:
```bash
flutter test test/admin_promotion_banner_adversarial_test.dart test/admin_promotion_banner_test.dart
```
must pass **13 of 13 tests with 0 failures**.
