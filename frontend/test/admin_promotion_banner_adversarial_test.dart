import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';

import 'package:kho_tra_sua/src/core/widgets/admin_promotion_banner.dart';
import 'package:kho_tra_sua/src/data/models/dtos.dart';
import 'package:kho_tra_sua/src/features/auth/auth_service.dart';
import 'package:kho_tra_sua/src/features/commerce/commerce_memory_store.dart';
import 'package:kho_tra_sua/src/features/commerce/commerce_workspace.dart';

void main() {
  group('Adversarial Viewport Stress Tests (320px, 375px, 390px, 414px)', () {
    const supportedStandardViewports = <Size>[
      Size(375, 667), // iPhone 8 / SE 2nd gen
      Size(375, 812), // iPhone X / 11 Pro / 12 mini / 13 mini
      Size(390, 844), // iPhone 12 / 13 / 14 standard
      Size(414, 896), // iPhone 11 / XR / Plus
    ];

    for (final size in supportedStandardViewports) {
      testWidgets(
          'PASSES: Viewport ${size.width}x${size.height} adapts cleanly without overflow',
          (tester) async {
        tester.view.physicalSize = size;
        tester.view.devicePixelRatio = 1.0;
        addTearDown(tester.view.resetPhysicalSize);
        addTearDown(tester.view.resetDevicePixelRatio);

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
        await tester.pump();

        expect(find.byKey(const Key('admin-promotion-banner')), findsOneWidget);
        expect(find.byKey(const ValueKey('btn-admin-promoted-refresh')), findsOneWidget);
        expect(find.byKey(const ValueKey('btn-admin-promoted-dismiss')), findsOneWidget);
        expect(tester.takeException(), isNull);
      });
    }

    testWidgets(
        'PASSES: 320px viewport with both buttons adapts cleanly without overflow using Wrap',
        (tester) async {
      tester.view.physicalSize = const Size(320, 568);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

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
      await tester.pump();

      expect(find.byKey(const Key('admin-promotion-banner')), findsOneWidget);
      expect(find.byKey(const ValueKey('btn-admin-promoted-refresh')), findsOneWidget);
      expect(find.byKey(const ValueKey('btn-admin-promoted-dismiss')), findsOneWidget);
      expect(tester.takeException(), isNull);
    });

    testWidgets(
        'EDGE CASE: 320px viewport WITHOUT dismiss button fits cleanly in 266px available width',
        (tester) async {
      tester.view.physicalSize = const Size(320, 568);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: AdminPromotionBanner(
              initialSeconds: 5,
              onRefresh: () {},
              onDismiss: null,
            ),
          ),
        ),
      );
      await tester.pump();

      expect(find.byKey(const Key('admin-promotion-banner')), findsOneWidget);
      expect(find.byKey(const ValueKey('btn-admin-promoted-refresh')), findsOneWidget);
      expect(find.byKey(const ValueKey('btn-admin-promoted-dismiss')), findsNothing);
      expect(tester.takeException(), isNull);
    });

    testWidgets(
        'PASSES: CommerceWorkspace at 320px adapts cleanly without overflow in AdminPromotionBanner',
        (tester) async {
      tester.view.physicalSize = const Size(320, 568);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      final store = CommerceMemoryStore.empty();
      addTearDown(store.dispose);

      final auth = AuthService();
      addTearDown(auth.dispose);

      const staffUser = AppUser(
        id: 'staff-user-1',
        username: 'nhanvien_01',
        displayName: 'Nhân Viên 01',
        roles: ['staff'],
        capabilities: ['inventory:create_request'],
        email: 'staff@khotrasua.vn',
      );
      auth.setUserForTest(staffUser);
      auth.setAdminRolePromotedForTest(true);

      await tester.pumpWidget(
        ChangeNotifierProvider<AuthService>.value(
          value: auth,
          child: MaterialApp(
            home: Scaffold(
              body: CommerceWorkspace(
                store: store,
                initialIndex: 0,
              ),
            ),
          ),
        ),
      );
      await tester.pump();

      expect(find.byKey(const Key('admin-promotion-banner')), findsOneWidget);
      expect(tester.takeException(), isNull);
    });

    testWidgets(
        'PASSES: Extreme text scaling (1.3x) on 320px viewport adapts without RenderFlex overflow',
        (tester) async {
      tester.view.physicalSize = const Size(320, 568);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await tester.pumpWidget(
        MediaQuery(
          data: const MediaQueryData(
            size: Size(320, 568),
            textScaler: TextScaler.linear(1.3),
          ),
          child: MaterialApp(
            home: Scaffold(
              body: AdminPromotionBanner(
                initialSeconds: 5,
                onRefresh: () {},
                onDismiss: () {},
              ),
            ),
          ),
        ),
      );
      await tester.pump();

      expect(find.byKey(const Key('admin-promotion-banner')), findsOneWidget);
      expect(tester.takeException(), isNull);
    });
  });

  group('Draft Resilience & pauseCountdown Safety Stress Tests', () {
    testWidgets(
        'pauseCountdown: true prevents auto-refresh indefinitely until resumed',
        (tester) async {
      var refreshCount = 0;

      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: AdminPromotionBanner(
              initialSeconds: 5,
              pauseCountdown: true,
              onRefresh: () => refreshCount++,
            ),
          ),
        ),
      );

      // Advance by 30 seconds
      await tester.pump(const Duration(seconds: 30));
      expect(refreshCount, equals(0),
          reason: 'Auto-refresh must never trigger while pauseCountdown is true');

      // Now toggle pauseCountdown to false
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: AdminPromotionBanner(
              initialSeconds: 5,
              pauseCountdown: false,
              onRefresh: () => refreshCount++,
            ),
          ),
        ),
      );

      // Countdown advances 5 seconds
      await tester.pump(const Duration(seconds: 5));
      expect(refreshCount, equals(1),
          reason: 'Auto-refresh should trigger once countdown completes');
    });

    testWidgets(
        'Toggling pauseCountdown mid-countdown pauses at current second without resetting',
        (tester) async {
      var refreshCount = 0;

      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: AdminPromotionBanner(
              initialSeconds: 5,
              pauseCountdown: false,
              onRefresh: () => refreshCount++,
            ),
          ),
        ),
      );

      // Let 2 seconds elapse (remaining: 3s)
      await tester.pump(const Duration(seconds: 2));
      expect(find.textContaining('3 giây'), findsOneWidget);
      expect(refreshCount, equals(0));

      // Pause countdown (e.g. user opens draft or modal dialog)
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: AdminPromotionBanner(
              initialSeconds: 5,
              pauseCountdown: true,
              onRefresh: () => refreshCount++,
            ),
          ),
        ),
      );

      // Wait 15 seconds while paused
      await tester.pump(const Duration(seconds: 15));
      expect(refreshCount, equals(0));
      // Remaining seconds must remain frozen at 3
      expect(find.textContaining('3 giây'), findsOneWidget);

      // Resume countdown (e.g. user closes modal dialog)
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: AdminPromotionBanner(
              initialSeconds: 5,
              pauseCountdown: false,
              onRefresh: () => refreshCount++,
            ),
          ),
        ),
      );

      // Step 1s -> 2s remaining
      await tester.pump(const Duration(seconds: 1));
      expect(find.textContaining('2 giây'), findsOneWidget);
      expect(refreshCount, equals(0));

      // Step 1s -> 1s remaining
      await tester.pump(const Duration(seconds: 1));
      expect(find.textContaining('1 giây'), findsOneWidget);
      expect(refreshCount, equals(0));

      // Step 1s -> 0s -> triggers onRefresh
      await tester.pump(const Duration(seconds: 1));
      expect(refreshCount, equals(1));
    });

    testWidgets(
        'Manual [Làm mới ngay] button works immediately even when pauseCountdown is true',
        (tester) async {
      var refreshCount = 0;

      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: AdminPromotionBanner(
              initialSeconds: 5,
              pauseCountdown: true,
              onRefresh: () => refreshCount++,
              onDismiss: () {},
            ),
          ),
        ),
      );

      expect(refreshCount, equals(0));

      // User explicitly taps [Làm mới ngay]
      await tester.tap(find.byKey(const ValueKey('btn-admin-promoted-refresh')));
      await tester.pump();

      expect(refreshCount, equals(1),
          reason: 'Manual refresh must immediately trigger even if countdown is paused');
    });

    testWidgets(
        'ANALYSIS: CommerceWorkspace mounts AdminPromotionBanner without pauseCountdown parameter',
        (tester) async {
      tester.view.physicalSize = const Size(390, 844);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      final store = CommerceMemoryStore.empty();
      addTearDown(store.dispose);

      final auth = AuthService();
      addTearDown(auth.dispose);

      const staffUser = AppUser(
        id: 'staff-user-1',
        username: 'nhanvien_01',
        displayName: 'Nhân Viên 01',
        roles: ['staff'],
        capabilities: ['inventory:create_request'],
        email: 'staff@khotrasua.vn',
      );
      auth.setUserForTest(staffUser);
      auth.setAdminRolePromotedForTest(true);

      var reloadCount = 0;

      await tester.pumpWidget(
        ChangeNotifierProvider<AuthService>.value(
          value: auth,
          child: MaterialApp(
            home: Scaffold(
              body: CommerceWorkspace(
                store: store,
                initialIndex: 0,
                onRefresh: () async {
                  reloadCount++;
                },
              ),
            ),
          ),
        ),
      );
      await tester.pump();

      expect(find.byKey(const Key('admin-promotion-banner')), findsOneWidget);

      // Verify banner instance in tree has pauseCountdown == false by default
      final AdminPromotionBanner bannerWidget =
          tester.widget<AdminPromotionBanner>(find.byKey(const Key('admin-promotion-banner')));
      expect(bannerWidget.pauseCountdown, isFalse,
          reason: 'CommerceWorkspace does not currently bind pauseCountdown');

      // Open a modal dialog over the workspace
      final BuildContext workspaceContext = tester.element(find.byType(CommerceWorkspace));
      showDialog<void>(
        context: workspaceContext,
        builder: (ctx) => const AlertDialog(
          key: Key('sample-draft-dialog'),
          title: Text('Đang tạo đơn hàng'),
          content: TextField(key: Key('draft-input')),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.byKey(const Key('sample-draft-dialog')), findsOneWidget);

      // Advance clock by 6 seconds.
      // Because pauseCountdown was not bound in CommerceWorkspace, countdown runs down to 0
      for (var i = 0; i < 6; i++) {
        await tester.pump(const Duration(seconds: 1));
      }

      // Banner has executed auto-refresh
      expect(reloadCount, equals(1));
      // Modal dialog is still present on the Navigator overlay stack
      expect(find.byKey(const Key('sample-draft-dialog')), findsOneWidget);
    });
  });

  group('AdminPromotionBanner Adversarial Stress & Concurrency Suite', () {
    testWidgets(
        'Adversarial 1: Countdown hits 0, user taps [Làm mới ngay] while still mounted -> checks for duplicate onRefresh',
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

      // Countdown steps down to 0 and triggers onRefresh
      await tester.pump(const Duration(seconds: 1));
      expect(refreshCount, equals(1));

      // User immediately taps refresh button while banner is still mounted
      await tester.tap(find.byKey(const ValueKey('btn-admin-promoted-refresh')));
      await tester.pump();

      expect(refreshCount, equals(1),
          reason: 'Race condition failure: onRefresh must not be called twice');
    });

    testWidgets(
        'Adversarial 2: Rapid multi-tap on [Làm mới ngay] -> checks if duplicate execution is guarded',
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

      // Multi-tap rapidly 3 times
      await tester.tap(find.byKey(const ValueKey('btn-admin-promoted-refresh')));
      await tester.tap(find.byKey(const ValueKey('btn-admin-promoted-refresh')));
      await tester.tap(find.byKey(const ValueKey('btn-admin-promoted-refresh')));
      await tester.pump();

      expect(refreshCount, equals(1),
          reason: 'Concurrency failure: multi-tapping must only invoke onRefresh once');
    });

    testWidgets(
        'Adversarial 3: Rapid unmount and remount during active countdown -> checks timer leaks & exceptions',
        (tester) async {
      for (var i = 0; i < 10; i++) {
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
        await tester.pump(const Duration(milliseconds: 200));
        await tester.pumpWidget(const SizedBox());
        await tester.pump(const Duration(milliseconds: 100));
      }
      expect(tester.takeException(), isNull);
    });

    testWidgets(
        'Adversarial 4: Tap [Để sau] after countdown reached 0 does not trigger onDismiss',
        (tester) async {
      var refreshCount = 0;
      var dismissCount = 0;
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: AdminPromotionBanner(
              initialSeconds: 1,
              onRefresh: () => refreshCount++,
              onDismiss: () => dismissCount++,
            ),
          ),
        ),
      );

      // Let countdown reach 0
      await tester.pump(const Duration(seconds: 1));
      expect(refreshCount, equals(1));

      // Attempt to tap [Để sau] after countdown has already refreshed
      await tester.tap(find.byKey(const ValueKey('btn-admin-promoted-dismiss')));
      await tester.pump();

      expect(dismissCount, equals(0),
          reason: 'onDismiss must not fire if onRefresh already triggered');
    });

    testWidgets(
        'Adversarial 5: Rapid toggle of pauseCountdown at countdown boundary',
        (tester) async {
      var refreshCount = 0;
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: AdminPromotionBanner(
              initialSeconds: 2,
              pauseCountdown: false,
              onRefresh: () => refreshCount++,
            ),
          ),
        ),
      );

      await tester.pump(const Duration(seconds: 1));
      expect(refreshCount, equals(0));

      // Toggle pause rapidly
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: AdminPromotionBanner(
              initialSeconds: 2,
              pauseCountdown: true,
              onRefresh: () => refreshCount++,
            ),
          ),
        ),
      );
      await tester.pump(const Duration(seconds: 2));
      expect(refreshCount, equals(0));

      // Resume
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: AdminPromotionBanner(
              initialSeconds: 2,
              pauseCountdown: false,
              onRefresh: () => refreshCount++,
            ),
          ),
        ),
      );
      await tester.pump(const Duration(seconds: 1));
      expect(refreshCount, equals(1));
    });
  });
}
