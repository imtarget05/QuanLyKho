import 'package:kho_tra_sua/src/app/app_shell.dart';
import 'package:kho_tra_sua/src/core/theme/app_theme.dart';
import 'package:kho_tra_sua/src/data/models/dtos.dart';
import 'package:kho_tra_sua/src/data/repositories/fake_repository.dart';
import 'package:kho_tra_sua/src/features/approvals/approvals_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  const checker = AppUser(
    id: 'bulk-approver',
    username: 'bulk_approver',
    displayName: 'Bulk Approver',
    roles: ['admin'],
  );

  testWidgets(
    'ApprovalsScreen bulk-select approves all pending items at once',
    (WidgetTester tester) async {
      tester.view.physicalSize = const Size(1400, 900);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);

      final repo = FakeBankOpsRepository(latency: Duration.zero);
      await tester.pumpWidget(
        RepositoryScope(
          repository: repo,
          child: SessionScope(
            user: checker,
            child: MaterialApp(
              theme: AppTheme.light(),
              home: const Scaffold(body: ApprovalsScreen()),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      // Seed có sẵn 3 phiếu pending: sr-0002 (kho), sr-0004 (chuyển kho) + cr-0002 (quỹ).
      expect(
        find.byKey(const Key('approval-select-sr-0002')),
        findsOneWidget,
      );
      expect(
        find.byKey(const Key('approval-select-sr-0004')),
        findsOneWidget,
      );
      expect(
        find.byKey(const Key('approval-select-cr-0002')),
        findsOneWidget,
      );
      expect(find.byKey(const Key('approve-selected-btn')), findsNothing);

      // Chọn tất cả -> nút duyệt hàng loạt hiện với đúng số lượng.
      await tester.tap(find.byKey(const Key('approval-select-all')));
      await tester.pumpAndSettle();
      expect(find.text('Đã chọn 3/3'), findsOneWidget);
      expect(find.byKey(const Key('approve-selected-btn')), findsOneWidget);

      // Duyệt hàng loạt -> dialog xác nhận -> inbox trống.
      await tester.tap(find.byKey(const Key('approve-selected-btn')));
      await tester.pumpAndSettle();
      expect(find.textContaining('Duyệt hàng loạt 3 phiếu'), findsWidgets);
      await tester.tap(find.byKey(const Key('confirm_dialog_confirm')));
      await tester.pumpAndSettle();

      expect(
        find.text('Hộp thư phê duyệt hoàn toàn trống'),
        findsOneWidget,
      );
    },
  );

  testWidgets(
    'ApprovalsScreen single approve still works without selection',
    (WidgetTester tester) async {
      tester.view.physicalSize = const Size(1400, 900);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);

      final repo = FakeBankOpsRepository(latency: Duration.zero);
      await tester.pumpWidget(
        RepositoryScope(
          repository: repo,
          child: SessionScope(
            user: checker,
            child: MaterialApp(
              theme: AppTheme.light(),
              home: const Scaffold(body: ApprovalsScreen()),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      await tester.tap(find.byKey(const Key('btn-approve-sr-0002')));
      await tester.pumpAndSettle();
      expect(find.byKey(const Key('approval-card-sr-0002')), findsNothing);
      expect(find.byKey(const Key('approval-card-cr-0002')), findsOneWidget);
    },
  );
}
