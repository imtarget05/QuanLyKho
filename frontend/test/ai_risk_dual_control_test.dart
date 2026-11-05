import 'package:kho_tra_sua/src/app/app_shell.dart';
import 'package:kho_tra_sua/src/core/theme/app_theme.dart';
import 'package:kho_tra_sua/src/data/models/dtos.dart';
import 'package:kho_tra_sua/src/data/repositories/fake_repository.dart';
import 'package:kho_tra_sua/src/features/approvals/approvals_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  testWidgets(
    'AI Copilot risk assessment modal displays score, rules and audit stamp',
    (WidgetTester tester) async {
      tester.view.physicalSize = const Size(1400, 900);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);

      final repo = FakeBankOpsRepository(latency: Duration.zero);

      // Create and submit high risk request: 600,000,000 VND
      final created = await repo.createCashRequest(
        cashboxId: '11111111-1111-4111-8111-111111111111',
        kind: RequestKind.payment,
        amount: '600000000.00',
        reason: 'Xuất quỹ khẩn cấp tiếp quỹ ATM trung tâm',
      );
      await repo.submitCashRequest(created.id);

      await tester.pumpWidget(
        RepositoryScope(
          repository: repo,
          child: SessionScope(
            user: const AppUser(
              id: 'risk-checker',
              username: 'risk_checker',
              displayName: 'Risk Checker',
              roles: ['admin'],
            ),
            child: MaterialApp(
              theme: AppTheme.light(),
              home: const Scaffold(body: ApprovalsScreen()),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      // Verify AI assessment button is present
      final assessBtn = find.byKey(Key('btn-ai-assess-${created.id}'));
      expect(assessBtn, findsOneWidget);

      // Open AI assessment modal
      await tester.tap(assessBtn);
      await tester.pumpAndSettle();

      expect(find.text('Đánh giá rủi ro bằng AI'), findsOneWidget);
      expect(find.textContaining('Phiếu: ${created.id}'), findsOneWidget);
      expect(find.text('Dấu kiểm toán số (Audit Stamp SHA-256):'), findsOneWidget);
      expect(find.text('Kiến nghị hành động cho Kiểm soát viên:'), findsOneWidget);

      // Close modal
      await tester.tap(find.byIcon(Icons.close));
      await tester.pumpAndSettle();
    },
  );

  testWidgets(
    'High-risk request requires Supervisor PIN verification before approval',
    (WidgetTester tester) async {
      tester.view.physicalSize = const Size(1400, 900);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);

      final repo = FakeBankOpsRepository(latency: Duration.zero);

      // Create and submit high risk request: 600,000,000 VND (>= 500M threshold)
      final created = await repo.createCashRequest(
        cashboxId: '11111111-1111-4111-8111-111111111111',
        kind: RequestKind.payment,
        amount: '600000000.00',
        reason: 'Xuất quỹ khẩn cấp tiếp quỹ ATM trung tâm',
      );
      await repo.submitCashRequest(created.id);

      await tester.pumpWidget(
        RepositoryScope(
          repository: repo,
          child: SessionScope(
            user: const AppUser(
              id: 'risk-checker',
              username: 'risk_checker',
              displayName: 'Risk Checker',
              roles: ['admin'],
            ),
            child: MaterialApp(
              theme: AppTheme.light(),
              home: const Scaffold(body: ApprovalsScreen()),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.byKey(Key('approval-card-${created.id}')), findsOneWidget);

      // Tap approve on high-risk card -> triggers Supervisor PIN dialog
      await tester.tap(find.byKey(Key('btn-approve-${created.id}')));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 300));

      expect(find.text('Xác Thực Quyền Kiểm Soát Kép (Supervisor Authorization)'), findsOneWidget);
      expect(find.byKey(const Key('supervisor-pin-input')), findsOneWidget);

      // Enter incorrect PIN -> shows error message
      await tester.enterText(find.byKey(const Key('supervisor-pin-input')), '999999');
      await tester.tap(find.byKey(const Key('confirm-supervisor-pin-btn')));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 300));

      expect(find.textContaining('Mã PIN không đúng'), findsOneWidget);

      // Enter correct Supervisor PIN (123456)
      await tester.enterText(find.byKey(const Key('supervisor-pin-input')), '123456');
      await tester.tap(find.byKey(const Key('confirm-supervisor-pin-btn')));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 500));

      // Card is approved and removed from pending inbox
      expect(find.byKey(Key('approval-card-${created.id}')), findsNothing);
    },
  );
}

