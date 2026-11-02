import "package:kho_tra_sua/src/app/app_shell.dart";
import "package:kho_tra_sua/src/core/theme/app_theme.dart";
import "package:kho_tra_sua/src/data/repositories/fake_repository.dart";
import "package:kho_tra_sua/src/features/auth/auth_service.dart";
import "package:flutter/material.dart";
import "package:flutter_test/flutter_test.dart";
import "package:provider/provider.dart";

void main() {
  testWidgets("AppShell renders navigation and dashboard",
      (WidgetTester tester) async {
    tester.view.physicalSize = const Size(1400, 900);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    final fakeRepo = FakeBankOpsRepository(latency: Duration.zero);
    await tester.pumpWidget(
      ChangeNotifierProvider<AuthService>(
        create: (_) => AuthService(baseUrl: 'http://localhost:8000'),
        child: MaterialApp(
          theme: AppTheme.light(),
          home: AppShell(repository: fakeRepo),
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.text("Tổng quan"), findsWidgets);
    expect(find.text("Kho"), findsWidgets);
    expect(find.text("Tổng quan vận hành"), findsOneWidget);
    expect(find.text("Kho đang hoạt động"), findsOneWidget);
    // A reconciliation with exceptions must not be presented as "100% matched".
    expect(find.text('Có ngoại lệ'), findsOneWidget);

    // Navigate to Requests -> submit draft -> navigate to Approvals -> approve
    await tester.tap(find.byKey(const Key('nav-requests')));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('btn-create-stock-request')), findsOneWidget);
    expect(find.byKey(const Key('btn-create-cash-request')), findsOneWidget);
    expect(find.byKey(const Key('btn-submit-stock-sr-0001')), findsOneWidget);

    await tester.tap(find.byKey(const Key('btn-submit-stock-sr-0001')));
    await tester.pumpAndSettle();

    // Navigate to Approvals
    await tester.tap(find.byKey(const Key('nav-approvals')));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('btn-approve-sr-0001')), findsOneWidget);
    await tester.tap(find.byKey(const Key('btn-approve-sr-0001')));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('btn-approve-sr-0001')), findsNothing);

    // Navigate to Reports
    await tester.tap(find.byKey(const Key('nav-reports')));
    await tester.pumpAndSettle();
    expect(find.text('Báo cáo & Biểu đồ'), findsOneWidget);

    // Navigate to Activity
    await tester.tap(find.byKey(const Key('nav-activity')));
    await tester.pumpAndSettle();
    expect(find.text('Hoạt động & Tiến trình nền'), findsOneWidget);
  });

  testWidgets('dashboard renders with providers', (WidgetTester tester) async {
    tester.view.physicalSize = const Size(1400, 900);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    final fakeRepo = FakeBankOpsRepository(latency: Duration.zero);
    await tester.pumpWidget(
      ChangeNotifierProvider<AuthService>(
        create: (_) => AuthService(baseUrl: 'http://localhost:8000'),
        child: MaterialApp(
          theme: AppTheme.light(),
          home: AppShell(repository: fakeRepo),
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.text('Tổng quan'), findsWidgets);
  });

  testWidgets(
      'Clicking Lập phiếu kho mới in Inventory auto-redirects to Requests and opens stock dialog',
      (WidgetTester tester) async {
    tester.view.physicalSize = const Size(1400, 900);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);

    final fakeRepo = FakeBankOpsRepository(latency: Duration.zero);
    await tester.pumpWidget(
      ChangeNotifierProvider<AuthService>(
        create: (_) => AuthService(baseUrl: 'http://localhost:8000'),
        child: MaterialApp(
          theme: AppTheme.light(),
          home: AppShell(repository: fakeRepo),
        ),
      ),
    );
    await tester.pumpAndSettle();

    // Navigate to Inventory tab
    await tester.tap(find.byKey(const Key('nav-inventory')));
    await tester.pumpAndSettle();
    expect(find.textContaining('Quản Lý Nhập Xuất Tồn'), findsOneWidget);

    // Tap "Lập phiếu kho mới"
    final btnCreate = find.byKey(const Key('btn-create-stock-request'));
    await tester.ensureVisible(btnCreate);
    await tester.tap(btnCreate, warnIfMissed: false);
    await tester.pumpAndSettle();

    // Verify it automatically redirected to Requests screen and opened the stock creation dialog
    expect(find.text('Quản Lý & Lập Phiếu Yêu Cầu'), findsOneWidget);
    expect(find.text('Tạo Phiếu Kho Mới'), findsOneWidget);
    expect(find.byKey(const Key('stock-qty-input')), findsOneWidget);
    // Verify no snackbar notification was shown
    expect(find.byType(SnackBar), findsNothing);
  });
}
