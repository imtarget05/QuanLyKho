import 'package:flutter_test/flutter_test.dart';
import 'package:kho_tra_sua/src/core/util/role_visibility.dart';
import 'package:kho_tra_sua/src/data/models/dtos.dart';

void main() {
  group('RBAC UAT Integration Matrix - RoleVisibility', () {
    test('canCreate: correct permission per role', () {
      // Creators
      expect(RoleVisibility.canCreate({'staff'}), isTrue);
      expect(RoleVisibility.canCreate({'maker'}), isTrue);
      expect(RoleVisibility.canCreate({'admin'}), isTrue);
      expect(RoleVisibility.canCreate({'root_admin'}), isTrue);
      expect(RoleVisibility.canCreate({'integration_admin'}), isTrue);

      // Non-creators (pure approver or pure auditor)
      expect(RoleVisibility.canCreate({'auditor'}), isFalse);
      expect(RoleVisibility.canCreate({'approver'}), isFalse);
      expect(RoleVisibility.canCreate({'checker'}), isFalse);
      expect(RoleVisibility.canCreate({'supervisor'}), isFalse);

      // Mixed roles: creator + approver
      expect(RoleVisibility.canCreate({'staff', 'approver'}), isTrue);
      expect(RoleVisibility.canCreate({'auditor', 'admin'}), isTrue);

      // Empty roles defaults to true (fail-open for unauthenticated dev/test)
      expect(RoleVisibility.canCreate({}), isTrue);
    });

    test('canApprove: correct permission per role', () {
      // Approvers
      expect(RoleVisibility.canApprove({'approver'}), isTrue);
      expect(RoleVisibility.canApprove({'checker'}), isTrue);
      expect(RoleVisibility.canApprove({'admin'}), isTrue);
      expect(RoleVisibility.canApprove({'root_admin'}), isTrue);
      expect(RoleVisibility.canApprove({'system_admin'}), isTrue);
      expect(RoleVisibility.canApprove({'supervisor'}), isTrue);

      // Non-approvers
      expect(RoleVisibility.canApprove({'staff'}), isFalse);
      expect(RoleVisibility.canApprove({'maker'}), isFalse);
      expect(RoleVisibility.canApprove({'auditor'}), isFalse);
      expect(RoleVisibility.canApprove({'integration_admin'}), isFalse);

      // Mixed roles
      expect(RoleVisibility.canApprove({'staff', 'approver'}), isTrue);
      expect(RoleVisibility.canApprove({'auditor', 'checker'}), isTrue);

      // Empty roles defaults to true
      expect(RoleVisibility.canApprove({}), isTrue);
    });

    test('isAuditorOnly: strictly identifies unprivileged auditors', () {
      expect(RoleVisibility.isAuditorOnly({'auditor'}), isTrue);

      // If user has any privileged role (admin, staff, approver, etc.), isAuditorOnly is FALSE
      expect(RoleVisibility.isAuditorOnly({'auditor', 'admin'}), isFalse);
      expect(RoleVisibility.isAuditorOnly({'auditor', 'staff'}), isFalse);
      expect(RoleVisibility.isAuditorOnly({'auditor', 'approver'}), isFalse);
      expect(RoleVisibility.isAuditorOnly({'staff'}), isFalse);
      expect(RoleVisibility.isAuditorOnly({'admin'}), isFalse);
      expect(RoleVisibility.isAuditorOnly({}), isFalse);
    });

    test('visibleTabs: tab visibility per role and user profile', () {
      final staffUser = const AppUser(
        id: 'u_staff',
        username: 'barista_01',
        displayName: 'Barista One',
        roles: ['staff'],
      );

      final auditorUser = const AppUser(
        id: 'u_auditor',
        username: 'auditor_01',
        displayName: 'Internal Auditor',
        roles: ['auditor'],
      );

      final adminUser = const AppUser(
        id: 'u_admin',
        username: 'admin_01',
        displayName: 'Store Manager',
        roles: ['admin'],
      );

      // 1. Staff tabs: 0,1,2 (Overview, Inventory, Shifts), 3,4 (Requests, Approvals), 6,7,8 (Activity, Reports, Settings).
      // Tab 5 is hiddenPilotTabs. Tab 9 is employee management (admin only).
      final staffTabs = RoleVisibility.visibleTabs(
        RoleVisibility.rolesOf(staffUser),
        staffUser,
      );
      expect(staffTabs, containsAll([0, 1, 2, 3, 4, 6, 7, 8]));
      expect(staffTabs.contains(5), isFalse);
      expect(staffTabs.contains(9), isFalse);

      // 2. Auditor tabs: tabs 3 (Requests) and 4 (Approvals) must be HIDDEN.
      final auditorTabs = RoleVisibility.visibleTabs(
        RoleVisibility.rolesOf(auditorUser),
        auditorUser,
      );
      expect(auditorTabs, containsAll([0, 1, 2, 6, 7, 8]));
      expect(auditorTabs.contains(3), isFalse, reason: 'Auditor must not see Requests tab');
      expect(auditorTabs.contains(4), isFalse, reason: 'Auditor must not see Approvals tab');
      expect(auditorTabs.contains(9), isFalse, reason: 'Auditor must not see Employee Admin tab');

      // 3. Admin tabs: includes all standard tabs PLUS tab 9 (Employee Management)
      final adminTabs = RoleVisibility.visibleTabs(
        RoleVisibility.rolesOf(adminUser),
        adminUser,
      );
      expect(adminTabs, containsAll([0, 1, 2, 3, 4, 6, 7, 8, 9]));
    });

    test('canManageCatalog: restricted to admin, root_admin, inventory_manager', () {
      expect(RoleVisibility.canManageCatalog({'admin'}), isTrue);
      expect(RoleVisibility.canManageCatalog({'root_admin'}), isTrue);
      expect(RoleVisibility.canManageCatalog({'inventory_manager'}), isTrue);

      expect(RoleVisibility.canManageCatalog({'staff'}), isFalse);
      expect(RoleVisibility.canManageCatalog({'auditor'}), isFalse);
      expect(RoleVisibility.canManageCatalog({'approver'}), isFalse);
    });

    test('canManageEmployees: only for admin roles or authorized email/username', () {
      final staffUser = const AppUser(
        id: 'u1',
        username: 'staff',
        displayName: 'Staff',
        roles: ['staff'],
      );
      expect(RoleVisibility.canManageEmployees(staffUser), isFalse);

      final adminUser = const AppUser(
        id: 'u2',
        username: 'admin',
        displayName: 'Admin',
        roles: ['admin'],
      );
      expect(RoleVisibility.canManageEmployees(adminUser), isTrue);

      final rootAdminUser = const AppUser(
        id: 'u3',
        username: 'root',
        displayName: 'Root Admin',
        roles: ['root_admin'],
      );
      expect(RoleVisibility.canManageEmployees(rootAdminUser), isTrue);
    });

    test('canPostCashAdjustment: enforces capability or role allowlist', () {
      // User with explicit capability
      final userWithCap = const AppUser(
        id: 'u_cap',
        username: 'cap_user',
        displayName: 'Cap User',
        roles: ['staff'],
        capabilities: ['cash:post_adjustment'],
      );
      expect(RoleVisibility.canPostCashAdjustment(userWithCap), isTrue);

      // User without capability but with admin role
      final userWithAdminRole = const AppUser(
        id: 'u_admin',
        username: 'admin_user',
        displayName: 'Admin User',
        roles: ['admin'],
        capabilities: [],
      );
      expect(RoleVisibility.canPostCashAdjustment(userWithAdminRole), isTrue);

      // Pure staff with no capability cannot adjust cash balance
      final plainStaff = const AppUser(
        id: 'u_staff',
        username: 'plain_staff',
        displayName: 'Plain Staff',
        roles: ['staff'],
        capabilities: ['inventory:view'],
      );
      expect(RoleVisibility.canPostCashAdjustment(plainStaff), isFalse);
    });
  });
}
