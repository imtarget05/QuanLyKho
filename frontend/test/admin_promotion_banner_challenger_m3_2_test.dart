import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:kho_tra_sua/src/core/util/role_visibility.dart';
import 'package:kho_tra_sua/src/core/widgets/admin_promotion_banner.dart';
import 'package:kho_tra_sua/src/features/auth/auth_service.dart';

void main() {
  group('Challenger M3-2: AdminPromotionBanner Lifecycle & Timer Leak Safety', () {
    testWidgets('Stress 1: Rapid 50x mount and immediate dispose without timer leak or unhandled exception',
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
        // Immediately unmount by pumping an empty Container
        await tester.pumpWidget(const SizedBox.shrink());
      }

      // Settle any remaining frame
      await tester.pump(const Duration(seconds: 6));
      expect(tester.takeException(), isNull);
    });

    testWidgets('Stress 2: Dispose banner mid-countdown at various seconds (0.5s, 1.2s, 3.7s)',
        (tester) async {
      final disposalIntervals = [
        const Duration(milliseconds: 500),
        const Duration(milliseconds: 1200),
        const Duration(milliseconds: 3700),
      ];

      for (final interval in disposalIntervals) {
        var refreshed = false;
        await tester.pumpWidget(
          MaterialApp(
            home: Scaffold(
              body: AdminPromotionBanner(
                initialSeconds: 5,
                onRefresh: () {
                  refreshed = true;
                },
              ),
            ),
          ),
        );

        // Advance by partial interval
        await tester.pump(interval);
        expect(refreshed, isFalse);

        // Unmount
        await tester.pumpWidget(const SizedBox.shrink());

        // Advance past original 5s duration
        await tester.pump(const Duration(seconds: 10));

        // onRefresh must NOT have been called after disposal
        expect(refreshed, isFalse);
        expect(tester.takeException(), isNull);
      }
    });

    testWidgets('Stress 3: Rapid multi-tap race condition on [Làm mới ngay] executes onRefresh exactly once',
        (tester) async {
      var refreshCount = 0;

      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: AdminPromotionBanner(
              initialSeconds: 5,
              onRefresh: () {
                refreshCount++;
              },
            ),
          ),
        ),
      );

      final refreshBtnFinder = find.byKey(const ValueKey('btn-admin-promoted-refresh'));
      expect(refreshBtnFinder, findsOneWidget);

      // Rapidly tap 10 times in quick succession within the same frame cycle
      for (var i = 0; i < 10; i++) {
        await tester.tap(refreshBtnFinder, warnIfMissed: false);
      }
      await tester.pump();
      await tester.pump(const Duration(seconds: 1));

      // Must be latched to exactly 1 execution
      expect(refreshCount, equals(1));
      expect(tester.takeException(), isNull);
    });

    testWidgets('Stress 4: Rapid multi-tap race condition on [Để sau] executes onDismiss exactly once',
        (tester) async {
      var dismissCount = 0;

      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: AdminPromotionBanner(
              initialSeconds: 5,
              onRefresh: () {},
              onDismiss: () {
                dismissCount++;
              },
            ),
          ),
        ),
      );

      final dismissBtnFinder = find.byKey(const ValueKey('btn-admin-promoted-dismiss'));
      expect(dismissBtnFinder, findsOneWidget);

      for (var i = 0; i < 10; i++) {
        await tester.tap(dismissBtnFinder, warnIfMissed: false);
      }
      await tester.pump();
      await tester.pump(const Duration(seconds: 1));

      expect(dismissCount, equals(1));
      expect(tester.takeException(), isNull);
    });

    testWidgets('Stress 5: Edge condition: initialSeconds = 0 triggers onRefresh immediately without crash',
        (tester) async {
      var refreshed = false;

      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: AdminPromotionBanner(
              initialSeconds: 0,
              onRefresh: () {
                refreshed = true;
              },
            ),
          ),
        ),
      );

      // Advance by 1 second to allow timer tick
      await tester.pump(const Duration(seconds: 1));

      expect(refreshed, isTrue);
      expect(tester.takeException(), isNull);
    });

    testWidgets('Stress 6: Pause and resume countdown state machine',
        (tester) async {
      var refreshCount = 0;
      var paused = false;

      await tester.pumpWidget(
        StatefulBuilder(
          builder: (context, setState) {
            return MaterialApp(
              home: Scaffold(
                body: Column(
                  children: [
                    ElevatedButton(
                      onPressed: () => setState(() => paused = !paused),
                      child: const Text('Toggle Pause'),
                    ),
                    AdminPromotionBanner(
                      initialSeconds: 4,
                      pauseCountdown: paused,
                      onRefresh: () => refreshCount++,
                    ),
                  ],
                ),
              ),
            );
          },
        ),
      );

      // Advance 1s -> 3s remaining
      await tester.pump(const Duration(seconds: 1));
      expect(find.textContaining('3 giây'), findsOneWidget);
      expect(refreshCount, equals(0));

      // Pause countdown
      await tester.tap(find.text('Toggle Pause'));
      await tester.pump();

      // Advance 10s while paused -> remaining seconds must NOT decrement
      await tester.pump(const Duration(seconds: 10));
      expect(find.textContaining('3 giây'), findsOneWidget);
      expect(refreshCount, equals(0));

      // Unpause countdown
      await tester.tap(find.text('Toggle Pause'));
      await tester.pump();

      // Step down 1s -> 2s
      await tester.pump(const Duration(seconds: 1));
      expect(find.textContaining('2 giây'), findsOneWidget);

      // Step down 1s -> 1s
      await tester.pump(const Duration(seconds: 1));
      expect(find.textContaining('1 giây'), findsOneWidget);

      // Step down 1s -> 0s -> triggers onRefresh
      await tester.pump(const Duration(seconds: 1));
      expect(refreshCount, equals(1));
    });
  });

  group('Challenger M3-2: AuthService 401 Session Revocation & Admin Banner Integration', () {
    test('Empirical: 401 Unauthorized from GET /auth/me activates adminRolePromoted and capabilities',
        () async {
      // 1. Setup mock client returning login response first, then 401 on /auth/me
      var loginCalled = false;
      final mockClient = MockClient((request) async {
        if (request.url.path.endsWith('/auth/login')) {
          loginCalled = true;
          return http.Response(
            '''{
              "access_token": "stale-token-auth-v1",
              "refresh_token": "mock-refresh-token",
              "user": {
                "id": "usr-ch32-test",
                "username": "staff_tester",
                "display_name": "Staff Tester",
                "email": "staff@bankops.vn",
                "roles": ["staff"],
                "capabilities": ["inventory:view_balances"]
              }
            }''',
            200,
            headers: {'content-type': 'application/json'},
          );
        } else if (request.url.path.endsWith('/auth/me')) {
          return http.Response(
            '{"detail": "Phiên đăng nhập đã bị thu hồi."}',
            401,
            headers: {'content-type': 'application/json'},
          );
        }
        return http.Response('{"error": "not found"}', 404);
      });

      final auth = AuthService(
        httpClient: mockClient,
        baseUrl: 'https://test.khotrasua.vn',
      );

      final signedIn = await auth.signInWithPassword(
        username: 'staff_tester',
        password: 'Password123!',
      );

      expect(signedIn, isTrue);
      expect(loginCalled, isTrue);
      expect(auth.user, isNotNull);
      expect(auth.user!.roles, contains('staff'));
      expect(auth.adminRolePromoted, isFalse);
      expect(RoleVisibility.isAdmin(auth.user!.roles.toSet()), isFalse);

      var notified = false;
      auth.addListener(() {
        notified = true;
      });

      // 2. Perform role update check (receives 401)
      await auth.checkUserRoleUpdate();

      // 3. Verify admin promotion banner triggered
      expect(auth.adminRolePromoted, isTrue);
      expect(notified, isTrue);
      expect(auth.promotedUser, isNotNull);
      expect(auth.promotedUser!.roles.contains('admin'), isTrue);
      expect(auth.promotedUser!.capabilities.contains('iam:admin'), isTrue);

      // 4. Apply admin promotion and refresh
      var appliedNotification = false;
      auth.addListener(() {
        appliedNotification = true;
      });

      await auth.applyAdminPromotionAndRefresh();

      expect(auth.adminRolePromoted, isFalse);
      expect(auth.user!.roles.contains('admin'), isTrue);
      expect(auth.user!.capabilities.contains('iam:admin'), isTrue);
      expect(RoleVisibility.isAdmin(auth.user!.roles.toSet()), isTrue);
      expect(appliedNotification, isTrue);

      // 5. Clean disposal without timer leaks
      auth.startRolePromotionWatcher();
      auth.dispose();
    });
  });
}
