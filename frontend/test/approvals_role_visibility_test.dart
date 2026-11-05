import 'package:kho_tra_sua/src/app/app_shell.dart';
import 'package:kho_tra_sua/src/core/theme/app_theme.dart';
import 'package:kho_tra_sua/src/data/models/dtos.dart';
import 'package:kho_tra_sua/src/data/repositories/fake_repository.dart';
import 'package:kho_tra_sua/src/features/approvals/approvals_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  Widget buildApprovalsWidget({
    required FakeBankOpsRepository repo,
    AppUser? user,
  }) {
    return RepositoryScope(
      repository: repo,
      child: SessionScope(
        user: user,
        child: MaterialApp(
          theme: AppTheme.light(),
          home: const Scaffold(body: ApprovalsScreen()),
        ),
      ),
    );
  }

  group('ApprovalsScreen Role-Based Action Buttons', () {
    testWidgets(
      'Admin role sees action buttons (approve, reject, return) and batch selection bar',
      (WidgetTester tester) async {
        tester.view.physicalSize = const Size(1400, 900);
        tester.view.devicePixelRatio = 1.0;
        addTearDown(tester.view.resetPhysicalSize);

        final repo = FakeBankOpsRepository(latency: Duration.zero);
        const adminUser = AppUser(
          id: 'admin-uuid',
          username: 'admin_test',
          displayName: 'Admin User',
          roles: ['admin'],
        );

        await tester.pumpWidget(buildApprovalsWidget(repo: repo, user: adminUser));
        await tester.pumpAndSettle();

        // Admin should see action buttons
        expect(find.byKey(const Key('btn-approve-sr-0002')), findsOneWidget);
        expect(find.byKey(const Key('btn-reject-sr-0002')), findsOneWidget);
        expect(find.byKey(const Key('btn-return-sr-0002')), findsOneWidget);

        // Admin should see batch select-all checkbox
        expect(find.byKey(const Key('approval-select-all')), findsOneWidget);
        expect(find.byKey(const Key('approval-select-sr-0002')), findsOneWidget);

        // Admin should NOT see read-only banner or badge
        expect(find.byKey(const Key('approvals-readonly-banner')), findsNothing);
        expect(find.byKey(const Key('approval-readonly-tag-sr-0002')), findsNothing);
      },
    );

    testWidgets(
      'Checker / Approver role sees action buttons and batch selection bar',
      (WidgetTester tester) async {
        tester.view.physicalSize = const Size(1400, 900);
        tester.view.devicePixelRatio = 1.0;
        addTearDown(tester.view.resetPhysicalSize);

        final repo = FakeBankOpsRepository(latency: Duration.zero);
        const checkerUser = AppUser(
          id: 'checker-uuid',
          username: 'checker_test',
          displayName: 'Checker User',
          roles: ['checker'],
        );

        await tester.pumpWidget(buildApprovalsWidget(repo: repo, user: checkerUser));
        await tester.pumpAndSettle();

        // Checker should see action buttons
        expect(find.byKey(const Key('btn-approve-sr-0002')), findsOneWidget);
        expect(find.byKey(const Key('btn-reject-sr-0002')), findsOneWidget);
        expect(find.byKey(const Key('btn-return-sr-0002')), findsOneWidget);
        expect(find.byKey(const Key('approval-select-all')), findsOneWidget);

        // No read-only banner
        expect(find.byKey(const Key('approvals-readonly-banner')), findsNothing);
        expect(find.byKey(const Key('approval-readonly-tag-sr-0002')), findsNothing);
      },
    );

    testWidgets(
      'Maker / Staff role does NOT see action buttons, sees read-only banner and tag',
      (WidgetTester tester) async {
        tester.view.physicalSize = const Size(1400, 900);
        tester.view.devicePixelRatio = 1.0;
        addTearDown(tester.view.resetPhysicalSize);

        final repo = FakeBankOpsRepository(latency: Duration.zero);
        const staffUser = AppUser(
          id: 'staff-uuid',
          username: 'staff_maker',
          displayName: 'Staff Maker',
          roles: ['maker', 'staff'],
        );

        await tester.pumpWidget(buildApprovalsWidget(repo: repo, user: staffUser));
        await tester.pumpAndSettle();

        // Staff / Maker should NOT see approval action buttons
        expect(find.byKey(const Key('btn-approve-sr-0002')), findsNothing);
        expect(find.byKey(const Key('btn-reject-sr-0002')), findsNothing);
        expect(find.byKey(const Key('btn-return-sr-0002')), findsNothing);

        // Staff / Maker should NOT see batch selection bar or checkboxes
        expect(find.byKey(const Key('approval-select-all')), findsNothing);
        expect(find.byKey(const Key('approval-select-sr-0002')), findsNothing);

        // Staff / Maker should NOT see yellow banner (removed per clean business UI)
        expect(find.byKey(const Key('approvals-readonly-banner')), findsNothing);
        expect(find.byKey(const Key('approval-readonly-tag-sr-0002')), findsOneWidget);
        expect(find.text('Chờ kiểm soát viên duyệt (Chỉ xem)'), findsWidgets);

        // Print button remains accessible for voucher checking
        expect(find.byKey(const Key('print-approval-sr-0002')), findsOneWidget);
      },
    );

    testWidgets(
      'Unauthenticated / null user cannot see approval actions',
      (WidgetTester tester) async {
        tester.view.physicalSize = const Size(1400, 900);
        tester.view.devicePixelRatio = 1.0;
        addTearDown(tester.view.resetPhysicalSize);

        final repo = FakeBankOpsRepository(latency: Duration.zero);

        await tester.pumpWidget(buildApprovalsWidget(repo: repo, user: null));
        await tester.pumpAndSettle();

        expect(find.byKey(const Key('btn-approve-sr-0002')), findsNothing);
        expect(find.byKey(const Key('btn-reject-sr-0002')), findsNothing);
        expect(find.byKey(const Key('approval-select-all')), findsNothing);
        expect(
          find.byKey(const Key('approval-readonly-tag-sr-0002')),
          findsOneWidget,
        );
      },
    );
  });
}
