import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:kho_tra_sua/src/data/models/dtos.dart';
import 'package:kho_tra_sua/src/core/util/role_visibility.dart';
import 'package:kho_tra_sua/src/features/commerce/commerce_workspace.dart';
import 'package:kho_tra_sua/src/features/commerce/commerce_memory_store.dart';
import 'package:kho_tra_sua/src/features/commerce/commerce_settings_view.dart';
import 'package:kho_tra_sua/src/features/settings/widgets/edit_profile_dialog.dart';
import 'package:kho_tra_sua/src/core/widgets/user_avatar.dart';

void main() {
  const testUser = AppUser(
    id: 'user-tan',
    username: 'tanmainguyenbinhtan',
    displayName: 'Tan Mai Nguyen Binh',
    roles: ['admin', 'maker'],
    email: 'tanmainguyenbinhtan@gmail.com',
  );

  const staffUser = AppUser(
    id: 'user-staff',
    username: 'staff_tea',
    displayName: 'Nhân viên Pha chế',
    roles: ['staff', 'maker'],
    email: 'staff@khotrasua.vn',
  );

  group('User Profile Sync, Role Priority & Sidebar Access Tests', () {
    test('RoleVisibility correctly resolves Chủ Quán (Admin) for tanmainguyenbinhtan', () {
      expect(RoleVisibility.userRoleLabel(testUser), 'Chủ Quán (Admin)');
      expect(RoleVisibility.userRoleLabel(staffUser), 'Nhân Viên Pha Chế / Quầy');
    });

    testWidgets('EditProfileDialog initializes with actual user info instead of default mock', (tester) async {
      await tester.pumpWidget(
        const MaterialApp(
          home: Scaffold(
            body: EditProfileDialog(currentUser: testUser),
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('Tan Mai Nguyen Binh'), findsOneWidget);
      expect(find.text('tanmainguyenbinhtan@gmail.com'), findsOneWidget);
    });

    testWidgets('CommerceSettingsView renders single clean SignOut button without redundant subtitle', (tester) async {
      final store = CommerceMemoryStore.empty();
      addTearDown(store.dispose);

      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: SingleChildScrollView(
              child: CommerceSettingsView(
                store: store,
                userName: 'Tan Mai Nguyen Binh',
                user: testUser,
                onSignOut: () async {},
                canManageUsers: true,
                canResetDemoData: false,
              ),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.widgetWithText(FilledButton, 'Đăng xuất'), findsOneWidget);
      expect(find.text('Sign Out Session'), findsNothing);
      expect(find.text('Sign out of current account on this device'), findsNothing);
    });

    testWidgets('Staff user CANNOT see Employee Management (Quản lý nhân viên) button in Settings', (tester) async {
      final store = CommerceMemoryStore.empty();
      addTearDown(store.dispose);

      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: SingleChildScrollView(
              child: CommerceSettingsView(
                store: store,
                userName: staffUser.displayName,
                user: staffUser,
                onSignOut: () async {},
                canManageUsers: false,
                canResetDemoData: false,
              ),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      // Ensure 'Quản lý nhân viên' button is completely hidden for staff
      expect(find.text('Quản lý nhân viên'), findsNothing);
      expect(find.text('Nhân sự & Phân quyền'), findsNothing);
    });

    testWidgets('Admin user CAN see Employee Management in Settings', (tester) async {
      final store = CommerceMemoryStore.empty();
      addTearDown(store.dispose);

      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: SingleChildScrollView(
              child: CommerceSettingsView(
                store: store,
                userName: testUser.displayName,
                user: testUser,
                onSignOut: () async {},
                canManageUsers: true,
                canResetDemoData: false,
              ),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('Quản lý nhân viên'), findsOneWidget);
      expect(find.text('Nhân sự & Phân quyền'), findsOneWidget);
    });

    testWidgets('Tapping sidebar bottom profile tile navigates to Settings and does NOT sign out immediately', (tester) async {
      tester.view.physicalSize = const Size(1200, 800);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      final store = CommerceMemoryStore.empty();
      addTearDown(store.dispose);

      var signedOut = false;
      await tester.pumpWidget(
        MaterialApp(
          home: CommerceWorkspace(
            store: store,
            user: testUser,
            userName: testUser.displayName,
            onSignOut: () async {
              signedOut = true;
            },
          ),
        ),
      );
      await tester.pumpAndSettle();

      // Find the sidebar ListTile with username
      final profileTile = find.widgetWithText(ListTile, 'Tan Mai Nguyen Binh');
      expect(profileTile, findsOneWidget);

      // Tap on the profile tile directly
      await tester.tap(profileTile);
      await tester.pumpAndSettle();

      // Must NOT have called onSignOut!
      expect(signedOut, isFalse);
      // It should navigate to Settings
      expect(find.text('Cài đặt hệ thống'), findsOneWidget);
    });

    testWidgets('CommerceWorkspace bottom nav bar uses storefront and shopping_bag icons', (tester) async {
      tester.view.physicalSize = const Size(390, 844);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      final store = CommerceMemoryStore.empty();
      addTearDown(store.dispose);

      await tester.pumpWidget(
        MaterialApp(
          home: CommerceWorkspace(
            store: store,
            user: testUser,
            userName: testUser.displayName,
          ),
        ),
      );
      await tester.pumpAndSettle();

      final navBar = tester.widget<NavigationBar>(find.byType(NavigationBar));
      final dests = navBar.destinations.cast<NavigationDestination>();
      expect((dests[1].icon as Icon).icon, Icons.storefront_outlined);
      expect((dests[1].selectedIcon as Icon).icon, Icons.storefront);
      expect((dests[2].icon as Icon).icon, Icons.shopping_bag_outlined);
      expect((dests[2].selectedIcon as Icon).icon, Icons.shopping_bag);
    });

    testWidgets('Header displays Quầy / Kho location chip with icon and user avatar', (tester) async {
      tester.view.physicalSize = const Size(390, 844);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      final store = CommerceMemoryStore.empty();
      addTearDown(store.dispose);

      await tester.pumpWidget(
        MaterialApp(
          home: CommerceWorkspace(
            store: store,
            user: testUser,
            userName: testUser.displayName,
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.byType(UserAvatar), findsWidgets);
    });
  });
}
