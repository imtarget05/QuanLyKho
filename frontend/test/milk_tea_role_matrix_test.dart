import 'package:flutter_test/flutter_test.dart';
import 'package:kho_tra_sua/src/core/util/role_visibility.dart';

void main() {
  // The UI only hides actions. The API remains the authorization boundary.
  // These roles mirror the inventory capabilities assigned in backend seed.
  const cases = <({
    String role,
    bool create,
    bool approve,
    bool requestsTab,
    bool approvalsTab,
  })>[
    (role: 'staff', create: true, approve: false, requestsTab: true, approvalsTab: true),
    (role: 'approver', create: false, approve: true, requestsTab: true, approvalsTab: true),
    (role: 'inventory_manager', create: true, approve: true, requestsTab: true, approvalsTab: true),
    (role: 'admin', create: true, approve: true, requestsTab: true, approvalsTab: true),
    (role: 'auditor', create: false, approve: false, requestsTab: false, approvalsTab: false),
  ];

  for (final row in cases) {
    test('inventory role matrix: ${row.role}', () {
      final roles = {row.role};
      final tabs = RoleVisibility.visibleTabs(roles);
      expect(RoleVisibility.canCreate(roles), row.create);
      expect(RoleVisibility.canApprove(roles), row.approve);
      expect(tabs.contains(3), row.requestsTab);
      expect(tabs.contains(4), row.approvalsTab);
      expect(tabs.contains(5), isFalse, reason: 'legacy integrations are hidden in tea-shop pilot');
      expect(tabs.contains(1), isTrue, reason: 'inventory remains readable');
      expect(tabs.contains(7), isTrue, reason: 'reports remain visible');
    });
  }
}
