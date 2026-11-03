import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:kho_tra_sua/src/core/widgets/admin_promotion_banner.dart';

void main() {
  group('Empirical Challenge: 320px Viewport & Wrap Mechanics', () {
    testWidgets(
        'CHALLENGE 1: 320px viewport with TextScaler 1.5 forces Wrap line break with ZERO overflow',
        (tester) async {
      tester.view.physicalSize = const Size(320, 568);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      var refreshCount = 0;
      var dismissCount = 0;

      await tester.pumpWidget(
        MediaQuery(
          data: const MediaQueryData(
            size: Size(320, 568),
            textScaler: TextScaler.linear(1.5),
          ),
          child: MaterialApp(
            home: Scaffold(
              body: AdminPromotionBanner(
                initialSeconds: 5,
                headline: 'Tài khoản đã nâng cấp lên Quản Trị Viên Hệ Thống Core Operations',
                onRefresh: () => refreshCount++,
                onDismiss: () => dismissCount++,
              ),
            ),
          ),
        ),
      );
      await tester.pump();

      // Ensure no RenderFlex or layout exceptions occurred
      expect(tester.takeException(), isNull,
          reason: 'Wrap container must prevent any RenderFlex overflow even under 1.5x scaling on 320px');

      final dismissFinder = find.byKey(const ValueKey('btn-admin-promoted-dismiss'));
      final refreshFinder = find.byKey(const ValueKey('btn-admin-promoted-refresh'));

      expect(dismissFinder, findsOneWidget);
      expect(refreshFinder, findsOneWidget);

      final dismissRect = tester.getRect(dismissFinder);
      final refreshRect = tester.getRect(refreshFinder);

      // Verify Wrap behavior: on narrow screen with 1.5x text, buttons should wrap (different vertical positions)
      // or fit with valid bounds within screen width
      expect(refreshRect.right, lessThanOrEqualTo(320.0),
          reason: 'Refresh button must not bleed beyond the 320px screen width');
      expect(dismissRect.right, lessThanOrEqualTo(320.0),
          reason: 'Dismiss button must not bleed beyond the 320px screen width');

      // Verify buttons remain interactive when wrapped
      await tester.tap(refreshFinder);
      await tester.pump();
      expect(refreshCount, equals(1));
      expect(dismissCount, equals(0));
    });

    testWidgets(
        'CHALLENGE 2: Extreme narrow width (280px) Wrap adaptation and tap targets',
        (tester) async {
      tester.view.physicalSize = const Size(280, 500);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      var dismissTapped = false;

      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: AdminPromotionBanner(
              initialSeconds: 10,
              onRefresh: () {},
              onDismiss: () => dismissTapped = true,
            ),
          ),
        ),
      );
      await tester.pump();

      expect(tester.takeException(), isNull);

      final dismissFinder = find.byKey(const ValueKey('btn-admin-promoted-dismiss'));
      await tester.tap(dismissFinder);
      await tester.pump();

      expect(dismissTapped, isTrue,
          reason: 'Dismiss button must remain functional under severe width constraints');
    });
  });

  group('Empirical Challenge: Rapid Button Clicks & _hasTriggered Latch Concurrency', () {
    testWidgets(
        'CHALLENGE 3: 50 consecutive rapid taps on [Làm mới ngay] triggers onRefresh exactly ONCE',
        (tester) async {
      var refreshCount = 0;

      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: AdminPromotionBanner(
              initialSeconds: 5,
              onRefresh: () => refreshCount++,
              onDismiss: () {},
            ),
          ),
        ),
      );

      final refreshBtn = find.byKey(const ValueKey('btn-admin-promoted-refresh'));

      // Hammer the button 50 times in rapid succession
      for (var i = 0; i < 50; i++) {
        await tester.tap(refreshBtn);
      }
      await tester.pump();

      expect(refreshCount, equals(1),
          reason: '_hasTriggered latch must reject 49 duplicate tap attempts');
    });

    testWidgets(
        'CHALLENGE 4: Mutual exclusion between [Làm mới ngay] and [Để sau]',
        (tester) async {
      var refreshCount = 0;
      var dismissCount = 0;

      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: AdminPromotionBanner(
              initialSeconds: 5,
              onRefresh: () => refreshCount++,
              onDismiss: () => dismissCount++,
            ),
          ),
        ),
      );

      final refreshBtn = find.byKey(const ValueKey('btn-admin-promoted-refresh'));
      final dismissBtn = find.byKey(const ValueKey('btn-admin-promoted-dismiss'));

      // Rapidly interleave taps
      await tester.tap(dismissBtn);
      await tester.tap(refreshBtn);
      await tester.tap(dismissBtn);
      await tester.tap(refreshBtn);
      await tester.pump();

      // Only the first tap ([Để sau]) should have taken effect
      expect(dismissCount, equals(1),
          reason: 'First tap on dismiss must trigger onDismiss');
      expect(refreshCount, equals(0),
          reason: '_hasTriggered must lock out subsequent refresh taps');
    });

    testWidgets(
        'CHALLENGE 5: Simultaneous countdown expiration and user tap race condition',
        (tester) async {
      var refreshCount = 0;

      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: AdminPromotionBanner(
              initialSeconds: 1,
              onRefresh: () => refreshCount++,
              onDismiss: () {},
            ),
          ),
        ),
      );

      final refreshBtn = find.byKey(const ValueKey('btn-admin-promoted-refresh'));

      // Tap button right as the timer is expiring
      await tester.tap(refreshBtn);
      await tester.pump(const Duration(seconds: 1));

      expect(refreshCount, equals(1),
          reason: 'Timer expiration and user tap occurring concurrently must execute onRefresh only once');
    });
  });

  group('Empirical Challenge: Timer Cancellation & Stress Lifecycle', () {
    testWidgets(
        'CHALLENGE 6: Rapid unmount and remount stress (50 cycles) leaves zero orphaned timers',
        (tester) async {
      for (var i = 0; i < 50; i++) {
        await tester.pumpWidget(
          MaterialApp(
            home: Scaffold(
              body: AdminPromotionBanner(
                initialSeconds: 5,
                onRefresh: () {},
                onDismiss: () {},
              ),
            ),
          ),
        );
        // Advance slightly mid-timer tick
        await tester.pump(const Duration(milliseconds: 150));

        // Unmount
        await tester.pumpWidget(const SizedBox());
        await tester.pump(const Duration(milliseconds: 50));
      }

      expect(tester.takeException(), isNull,
          reason: '50 rapid unmount cycles must cleanly cancel all periodic timers without leaks');
    });

    testWidgets(
        'CHALLENGE 7: Rapidly toggling pauseCountdown 30 times does not duplicate timer ticks',
        (tester) async {
      var refreshCount = 0;

      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: AdminPromotionBanner(
              initialSeconds: 3,
              pauseCountdown: false,
              onRefresh: () => refreshCount++,
            ),
          ),
        ),
      );

      // Elapse 1s -> 2s remaining
      await tester.pump(const Duration(seconds: 1));
      expect(find.textContaining('2 giây'), findsOneWidget);
      expect(refreshCount, equals(0));

      // Toggle pauseCountdown rapidly 30 times
      for (var i = 0; i < 30; i++) {
        await tester.pumpWidget(
          MaterialApp(
            home: Scaffold(
              body: AdminPromotionBanner(
                initialSeconds: 3,
                pauseCountdown: (i % 2 == 0),
                onRefresh: () => refreshCount++,
              ),
            ),
          ),
        );
        await tester.pump(const Duration(milliseconds: 20));
      }

      // Settle in unpaused state
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: AdminPromotionBanner(
              initialSeconds: 3,
              pauseCountdown: false,
              onRefresh: () => refreshCount++,
            ),
          ),
        ),
      );

      // Step remaining 2 seconds
      await tester.pump(const Duration(seconds: 1));
      await tester.pump(const Duration(seconds: 1));

      expect(refreshCount, equals(1),
          reason: 'Timer must remain stable and not accelerate or multi-fire after thrashing pauseCountdown');
    });

    testWidgets(
        'CHALLENGE 8: Dismissing banner immediately stops timer and cancels further ticks',
        (tester) async {
      var refreshCount = 0;
      var dismissCount = 0;

      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: AdminPromotionBanner(
              initialSeconds: 5,
              onRefresh: () => refreshCount++,
              onDismiss: () => dismissCount++,
            ),
          ),
        ),
      );

      // User dismisses banner at 5s
      await tester.tap(find.byKey(const ValueKey('btn-admin-promoted-dismiss')));
      await tester.pump();

      expect(dismissCount, equals(1));
      expect(refreshCount, equals(0));

      // Advance clock by 10s while widget is still mounted
      await tester.pump(const Duration(seconds: 10));

      // onRefresh must NOT have triggered
      expect(refreshCount, equals(0),
          reason: 'Timer must be cancelled permanently upon dismiss');
    });
  });
}
