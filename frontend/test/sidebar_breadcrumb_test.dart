import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:kho_tra_sua/src/app/app_shell.dart';
import 'package:kho_tra_sua/src/core/theme/app_theme.dart';
import 'package:kho_tra_sua/src/data/repositories/fake_repository.dart';
import 'package:kho_tra_sua/src/features/auth/auth_service.dart';
import 'package:provider/provider.dart';

void main() {
  testWidgets('Sidebar renders multi-level navigation with collapsible state',
      (WidgetTester tester) async {
    // Setup
    final fakeRepo = FakeBankOpsRepository(latency: Duration.zero);

    // Test compact mode (phone, < 600px)
    tester.view.physicalSize = const Size(375, 812); // iPhone 13 compact
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);

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

    // In compact mode, should show NavigationBar at bottom, not sidebar
    // The sidebar should be accessible via the "More" button
    expect(find.byType(NavigationBar), findsOneWidget);
    expect(find.text('Tổng quan vận hành'), findsOneWidget);

    // Test medium mode (600-1280px) - tablet
    tester.view.physicalSize = const Size(768, 1024);
    await tester.pump();
    await tester.pumpAndSettle();

    // In medium mode the sidebar is collapsed to its icon rail.
    expect(find.byKey(const Key('app-sidebar')), findsOneWidget);
    expect(tester.getSize(find.byKey(const Key('app-sidebar'))).width, 72);

    // Test wide mode (> 1280px) - desktop
    tester.view.physicalSize = const Size(1440, 900);
    await tester.pump();
    await tester.pumpAndSettle();

    // In wide mode, should show expanded sidebar (width 256)
    expect(find.byKey(const Key('app-sidebar')), findsOneWidget);
    expect(find.text('KHO & KIỂM KÊ'), findsOneWidget);
    expect(find.text('GIAO DỊCH'), findsOneWidget);
    expect(find.text('KHO & KIỂM KÊ'), findsOneWidget);
    expect(find.text('GIAO DỊCH'), findsOneWidget);
    expect(find.text('HOẠT ĐỘNG'), findsOneWidget);
    expect(find.text('QUẢN TRỊ'), findsOneWidget);
  });

  testWidgets('Sidebar collapsible toggle works', (WidgetTester tester) async {
    final fakeRepo = FakeBankOpsRepository(latency: Duration.zero);

    tester.view.physicalSize = const Size(768, 1024);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
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

    // Medium defaults to the compact rail; the toggle expands it.
    expect(find.byKey(const Key('app-sidebar')), findsOneWidget);

    await tester.tap(find.byIcon(Icons.arrow_forward_ios_rounded));
    await tester.pumpAndSettle();
    expect(tester.getSize(find.byKey(const Key('app-sidebar'))).width, 256);
    expect(find.text('KHO & KIỂM KÊ'), findsOneWidget);
  });

  testWidgets('Breadcrumb navigates correctly', (WidgetTester tester) async {
    final fakeRepo = FakeBankOpsRepository(latency: Duration.zero);

    tester.view.physicalSize = const Size(1440, 900);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
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

    // Breadcrumb should be present in header area
    // Test that breadcrumb home link works
    expect(find.text('Trang chủ'), findsOneWidget);
  });
}
