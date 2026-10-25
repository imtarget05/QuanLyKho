import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:kho_tra_sua/src/app/app_shell.dart';
import 'package:kho_tra_sua/src/core/util/role_visibility.dart';
import 'package:kho_tra_sua/src/data/models/dtos.dart';
import 'package:kho_tra_sua/src/data/repositories/fake_repository.dart';
import 'package:kho_tra_sua/src/features/admin/employee_management_screen.dart';

class RootRoleRepository extends FakeBankOpsRepository {
  RootRoleRepository() : super(latency: Duration.zero);

  int scopeUpdates = 0;
  List<String>? savedRoles;

  @override
  Future<List<RoleDto>> getRoles() async => [
        ...await super.getRoles(),
        const RoleDto(code: 'root_admin', name: 'Root Administrator'),
      ];

  @override
  Future<List<EmployeeUserDto>> getEmployees({
    String? search,
    String? branchId,
    String? role,
    String? status,
  }) async {
    final users = await super.getEmployees(
      search: search,
      branchId: branchId,
      role: role,
      status: status,
    );
    return users.map((user) {
      if (user.id != 'emp_1') return user;
      return EmployeeUserDto(
        id: user.id,
        username: user.username,
        displayName: user.displayName,
        email: user.email,
        status: user.status,
        branchId: 'br_q1',
        roles: const ['admin', 'root_admin'],
        capabilities: user.capabilities,
      );
    }).toList();
  }

  @override
  Future<EmployeeUserDto> updateEmployeeRoles(
      String userId, List<String> roles) async {
    savedRoles = roles;
    return super.updateEmployeeRoles(userId, roles);
  }

  @override
  Future<EmployeeUserDto> updateEmployeeScopes(
      String userId, List<Map<String, dynamic>> scopes) async {
    scopeUpdates++;
    return super.updateEmployeeScopes(userId, scopes);
  }
}

void main() {
  test('root-only role retains administrator navigation', () {
    const user = AppUser(
      id: 'root-1',
      username: 'root-user',
      displayName: 'Root',
      roles: ['root_admin'],
      capabilities: ['iam:root', 'iam:admin'],
    );
    final roles = RoleVisibility.rolesOf(user);
    expect(RoleVisibility.isAdmin(roles), isTrue);
    expect(RoleVisibility.canManageEmployees(user), isTrue);
    expect(RoleVisibility.canCreate(roles), isTrue);
    expect(RoleVisibility.canApprove(roles), isTrue);
    expect(RoleVisibility.canManageCatalog(roles), isTrue);
  });

  testWidgets(
      'self root-only role update does not reuse a revoked token for scopes',
      (tester) async {
    tester.view.physicalSize = const Size(1400, 1100);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);

    final repo = RootRoleRepository();
    var signOuts = 0;
    const currentUser = AppUser(
      id: 'emp_1',
      username: 'tanmainguyenbinh',
      displayName: 'Bình Tân',
      roles: ['admin', 'root_admin'],
      capabilities: ['iam:admin', 'iam:root'],
    );
    await tester.pumpWidget(MaterialApp(
      home: SessionScope(
        user: currentUser,
        onSignOut: () async => signOuts++,
        child: RepositoryScope(
          repository: repo,
          child: const Scaffold(body: EmployeeManagementScreen()),
        ),
      ),
    ));
    await tester.pumpAndSettle();

    await tester.tap(find.byTooltip('Tác vụ nhân viên').first);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Phân vai trò & Chi nhánh').last);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Chủ Quán / Quản Trị Viên (Admin)').last);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Lưu phân quyền'));
    await tester.pumpAndSettle();

    expect(repo.savedRoles, ['root_admin']);
    expect(repo.scopeUpdates, 0);
    expect(signOuts, 1);
  });
}
