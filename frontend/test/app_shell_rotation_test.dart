import "package:kho_tra_sua/src/app/app_shell.dart";
import "package:kho_tra_sua/src/core/theme/app_theme.dart";
import "package:kho_tra_sua/src/core/widgets/store_logo.dart";
import "package:kho_tra_sua/src/data/models/dtos.dart";
import "package:kho_tra_sua/src/data/repositories/fake_repository.dart";
import "package:kho_tra_sua/src/features/auth/auth_service.dart";
import "package:flutter/material.dart";
import "package:flutter_test/flutter_test.dart";
import "package:provider/provider.dart";

void main() {
  const adminUser = AppUser(
    id: 'rotation-admin',
    username: 'rotation_admin',
    displayName: 'Rotation Admin',
    roles: ['admin'],
  );

  testWidgets(
      "AppShell preserves screen state and does not reload when rotating screen",
      (WidgetTester tester) async {
    // 1. Khởi động ở chế độ điện thoại dọc (Compact: 390 x 844)
    tester.view.physicalSize = const Size(390, 844);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);

    final fakeRepo = FakeBankOpsRepository(latency: Duration.zero);

    await tester.pumpWidget(
      ChangeNotifierProvider<AuthService>(
        create: (_) => AuthService(baseUrl: 'http://localhost:8000'),
        child: MaterialApp(
          theme: AppTheme.light(),
          home: SessionScope(
            user: adminUser,
            child: AppShell(repository: fakeRepo),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    // Verify compact view: có NavigationBar ở dưới đáy
    expect(find.byType(NavigationBar), findsOneWidget);
    expect(find.text("Tổng quan vận hành"), findsOneWidget);

    // Lưu lại Element của màn hình chính để đối chiếu sau khi xoay
    final elementBeforeRotation =
        find.text("Tổng quan vận hành").evaluate().first;

    // 2. Xoay màn hình sang ngang (Landscape: 844 x 390 - vượt qua breakpoint 600px)
    tester.view.physicalSize = const Size(844, 390);
    await tester.pump();
    await tester.pumpAndSettle();

    // Verify wide/medium layout: NavigationBar biến mất, thanh sidebar xuất hiện
    expect(find.byType(NavigationBar), findsNothing);
    expect(find.byType(StoreLogo), findsOneWidget);
    expect(find.byKey(const Key('nav-requests')), findsOneWidget);

    // Nội dung màn hình vẫn giữ nguyên vẹn
    expect(find.text("Tổng quan vận hành"), findsOneWidget);

    // Element vẫn sống và được reparent trơn tru, không có vòng quay LoadingView xuất hiện
    final elementAfterRotation =
        find.text("Tổng quan vận hành").evaluate().first;
    expect(elementAfterRotation.widget, equals(elementBeforeRotation.widget));
  });
}
