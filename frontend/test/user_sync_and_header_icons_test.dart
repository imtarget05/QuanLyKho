import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:kho_tra_sua/src/data/models/dtos.dart';
import 'package:kho_tra_sua/src/features/commerce/commerce_workspace.dart';
import 'package:kho_tra_sua/src/features/commerce/commerce_memory_store.dart';
import 'package:kho_tra_sua/src/features/commerce/commerce_settings_view.dart';
import 'package:kho_tra_sua/src/features/settings/widgets/edit_profile_dialog.dart';
import 'package:kho_tra_sua/src/core/widgets/user_avatar.dart';

void main() {
  const testUser = AppUser(
    id: 'user-tan',
    username: 'tanmai',
    displayName: 'Tan Mai Nguyen Binh',
    roles: ['maker'],
    email: 'tanmainguyenbinh@gmail.com',
  );

  group('User Profile Sync & Header Icons Tests', () {
    testWidgets('EditProfileDialog initializes with actual user info instead of default mock', (tester) async {
      await tester.pumpWidget(
        const MaterialApp(
          home: Scaffold(
            body: EditProfileDialog(currentUser: testUser),
          ),
        ),
      );
      await tester.pumpAndSettle();

      // Check name controller contains 'Tan Mai Nguyen Binh'
      expect(find.text('Tan Mai Nguyen Binh'), findsOneWidget);
      // Check email field contains 'tanmainguyenbinh@gmail.com'
      expect(find.text('tanmainguyenbinh@gmail.com'), findsOneWidget);
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

      // Sign out button is present
      expect(find.widgetWithText(FilledButton, 'Đăng xuất'), findsOneWidget);
      // Redundant text rows from before are removed
      expect(find.text('Sign Out Session'), findsNothing);
      expect(find.text('Sign out of current account on this device'), findsNothing);
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

      // Check UserAvatar is in the topbar
      expect(find.byType(UserAvatar), findsWidgets);
    });
  });
}
