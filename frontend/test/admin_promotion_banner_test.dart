import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';

import 'package:kho_tra_sua/src/core/util/role_visibility.dart';
import 'package:kho_tra_sua/src/core/widgets/admin_promotion_banner.dart';
import 'package:kho_tra_sua/src/data/models/dtos.dart';
import 'package:kho_tra_sua/src/features/auth/auth_service.dart';
import 'package:kho_tra_sua/src/features/commerce/commerce_memory_store.dart';
import 'package:kho_tra_sua/src/features/commerce/commerce_workspace.dart';

void main() {
  group('AdminPromotionBanner Widget & Lifecycle Test Suite', () {
    testWidgets(
        'Test 1: Banner renders with headline, icon, countdown, and btn-admin-promoted-refresh',
        (tester) async {
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

      // Root container key
      expect(find.byKey(const Key('admin-promotion-banner')), findsOneWidget);

      // Exact headline text
      expect(
        find.text(
            'Tài khoản của bạn đã được nâng cấp lên Quản Trị Viên (Admin)'),
        findsOneWidget,
      );

      // Shield icon
      expect(find.byIcon(Icons.shield_rounded), findsOneWidget);

      // Subtitle countdown text
      expect(
        find.text(
            'Tài khoản vừa được cấp quyền Quản Trị Viên. Tự động làm mới trong 5 giây...'),
        findsOneWidget,
      );

      // Refresh button key and label
      expect(
        find.byKey(const ValueKey('btn-admin-promoted-refresh')),
        findsOneWidget,
      );
      expect(find.text('Làm mới ngay'), findsOneWidget);

      // Dismiss button key and label
      expect(
        find.byKey(const ValueKey('btn-admin-promoted-dismiss')),
        findsOneWidget,
      );
      expect(find.text('Để sau'), findsOneWidget);
    });

    testWidgets(
        'Test 2: Tapping btn-admin-promoted-refresh calls onRefresh immediately and cancels timer',
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

      expect(refreshCount, equals(0));

      // Tap refresh button
      await tester.tap(find.byKey(const ValueKey('btn-admin-promoted-refresh')));
      await tester.pump();

      expect(refreshCount, equals(1));

      // Advance time by 10 seconds; timer must be cancelled and not trigger further callbacks
      await tester.pump(const Duration(seconds: 10));
      expect(refreshCount, equals(1));
    });

    testWidgets(
        'Test 3: Auto-countdown steps with tester.pump(1s) from 5 down to 0 and automatically triggers onRefresh',
        (tester) async {
      var refreshed = false;

      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: AdminPromotionBanner(
              initialSeconds: 5,
              onRefresh: () => refreshed = true,
            ),
          ),
        ),
      );

      expect(
        find.text(
            'Tài khoản vừa được cấp quyền Quản Trị Viên. Tự động làm mới trong 5 giây...'),
        findsOneWidget,
      );
      expect(refreshed, isFalse);

      // Step to 4s
      await tester.pump(const Duration(seconds: 1));
      expect(
        find.text(
            'Tài khoản vừa được cấp quyền Quản Trị Viên. Tự động làm mới trong 4 giây...'),
        findsOneWidget,
      );
      expect(refreshed, isFalse);

      // Step to 3s
      await tester.pump(const Duration(seconds: 1));
      expect(
        find.text(
            'Tài khoản vừa được cấp quyền Quản Trị Viên. Tự động làm mới trong 3 giây...'),
        findsOneWidget,
      );
      expect(refreshed, isFalse);

      // Step to 2s
      await tester.pump(const Duration(seconds: 1));
      expect(
        find.text(
            'Tài khoản vừa được cấp quyền Quản Trị Viên. Tự động làm mới trong 2 giây...'),
        findsOneWidget,
      );
      expect(refreshed, isFalse);

      // Step to 1s
      await tester.pump(const Duration(seconds: 1));
      expect(
        find.text(
            'Tài khoản vừa được cấp quyền Quản Trị Viên. Tự động làm mới trong 1 giây...'),
        findsOneWidget,
      );
      expect(refreshed, isFalse);

      // Step to 0s (trigger)
      await tester.pump(const Duration(seconds: 1));
      expect(refreshed, isTrue);

      // Subsequent ticks should not re-trigger
      await tester.pump(const Duration(seconds: 3));
      expect(refreshed, isTrue);
    });

    testWidgets(
        'Test 4: Disposing banner cancels countdown cleanly without timer leak exceptions',
        (tester) async {
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: AdminPromotionBanner(
              initialSeconds: 5,
              onRefresh: () {},
            ),
          ),
        ),
      );

      // Advance clock partially (2 seconds)
      await tester.pump(const Duration(seconds: 2));

      // Dispose widget tree while timer is still active
      await tester.pumpWidget(const SizedBox());

      // Advance simulated clock further
      await tester.pump(const Duration(seconds: 10));

      // Must have zero unhandled timer exceptions
      expect(tester.takeException(), isNull);
    });

    testWidgets(
        'Test 5: Mobile viewport parity: renders cleanly on 375x812, 390x844, and 414x896 without RenderFlex overflow',
        (tester) async {
      const viewports = [
        Size(375, 812), // iPhone SE / Mini
        Size(390, 844), // iPhone 12/13/14
        Size(414, 896), // Standard Large Mobile
      ];

      for (final size in viewports) {
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
        expect(tester.takeException(), isNull);
      }
    });

    testWidgets(
        'Test 6: Role promotion unlock: after refresh, RoleVisibility.isAdmin == true, userRoleLabel == Chủ Quán (Admin), and Reports, Approvals, RBAC unlock',
        (tester) async {
      tester.view.physicalSize = const Size(1280, 900);
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

      // Verify initial staff state
      expect(RoleVisibility.isAdmin(auth.user!.roles.toSet()), isFalse);
      expect(RoleVisibility.canManageEmployees(auth.user), isFalse);

      // Signal admin promotion
      auth.setAdminRolePromotedForTest(true);
      expect(auth.adminRolePromoted, isTrue);

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

      // Banner is rendered
      expect(find.byKey(const Key('admin-promotion-banner')), findsOneWidget);

      // Tap [Làm mới ngay]
      await tester.tap(find.byKey(const ValueKey('btn-admin-promoted-refresh')));
      await tester.pump();

      // Banner is dismissed
      expect(find.byKey(const Key('admin-promotion-banner')), findsNothing);
      expect(auth.adminRolePromoted, isFalse);

      // Admin privileges are unlocked
      expect(RoleVisibility.isAdmin(auth.user!.roles.toSet()), isTrue);
      expect(RoleVisibility.userRoleLabel(auth.user), equals('Chủ Quán (Admin)'));
      expect(RoleVisibility.canManageEmployees(auth.user), isTrue);

      // Reports and Approvals quick launch tiles are present on overview
      expect(find.byKey(const Key('tile-subsystem-reports')), findsOneWidget);
      expect(find.byKey(const Key('tile-subsystem-approvals')), findsOneWidget);

      // Navigate to Settings tab
      final settingsTile = find.byKey(const Key('tile-subsystem-settings'));
      expect(settingsTile, findsOneWidget);
      await tester.tap(settingsTile);
      await tester.pump();

      // RBAC user management card is unlocked
      expect(find.text('Quản lý nhân viên'), findsOneWidget);
      expect(find.text('Nhân sự & Phân quyền'), findsOneWidget);
    });

    testWidgets(
        'Test 7: Tapping [Để sau] dismisses the banner and cancels timer',
        (tester) async {
      var dismissed = false;
      var refreshed = false;

      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: AdminPromotionBanner(
              initialSeconds: 5,
              onRefresh: () => refreshed = true,
              onDismiss: () => dismissed = true,
            ),
          ),
        ),
      );

      expect(
        find.byKey(const ValueKey('btn-admin-promoted-dismiss')),
        findsOneWidget,
      );

      // Tap [Để sau]
      await tester.tap(find.byKey(const ValueKey('btn-admin-promoted-dismiss')));
      await tester.pump();

      expect(dismissed, isTrue);

      // Advance time by 10s: onRefresh must NOT be called because timer was cancelled
      await tester.pump(const Duration(seconds: 10));
      expect(refreshed, isFalse);
    });

    testWidgets(
        'Test 8: Pause countdown when draft form / modal is active',
        (tester) async {
      var refreshed = false;

      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: AdminPromotionBanner(
              initialSeconds: 5,
              pauseCountdown: true,
              onRefresh: () => refreshed = true,
            ),
          ),
        ),
      );

      // Advance 10s with pauseCountdown: true
      await tester.pump(const Duration(seconds: 10));
      expect(refreshed, isFalse);

      // Resume countdown
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: AdminPromotionBanner(
              initialSeconds: 5,
              pauseCountdown: false,
              onRefresh: () => refreshed = true,
            ),
          ),
        ),
      );

      // Step countdown down to 0
      for (var i = 0; i < 5; i++) {
        expect(refreshed, isFalse);
        await tester.pump(const Duration(seconds: 1));
      }

      // Now auto-refresh triggers
      expect(refreshed, isTrue);
    });
  });
}
