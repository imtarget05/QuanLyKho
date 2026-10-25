import 'package:kho_tra_sua/src/app/app_shell.dart';
import 'package:kho_tra_sua/src/core/theme/app_theme.dart';
import 'package:kho_tra_sua/src/data/models/dtos.dart';
import 'package:kho_tra_sua/src/data/repositories/fake_repository.dart';
import 'package:kho_tra_sua/src/features/inventory/inventory_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  testWidgets(
    'InventoryScreen displays low stock alerts and allows stocktaking workflow',
    (WidgetTester tester) async {
      tester.view.physicalSize = const Size(1400, 1000);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);

      final repo = FakeBankOpsRepository(latency: Duration.zero);

      // The stocktake outbox persists to SharedPreferences; mock the plugin.
      SharedPreferences.setMockInitialValues({});

      // Pre-seed a stock level where min_qty > current balance
      final locs = await repo.getLocations();
      final items = await repo.getItems();
      await repo.putStockLevel(
        locationId: locs.first.id,
        itemId: items.first.id,
        minQty: '999999',
        maxQty: '1000000',
      );

      // Pre-seed a stocktake
      await repo.createStocktake(
        locationId: locs.first.id,
        note: 'Đợt kiểm kê mẫu quý 4',
      );

      const user = AppUser(
        id: 'u_manager',
        username: 'demo_manager',
        displayName: 'Quản Lý Kho',
        roles: ['manager', 'admin'],
      );

      await tester.pumpWidget(
        RepositoryScope(
          repository: repo,
          child: SessionScope(
            user: user,
            child: MaterialApp(
              theme: AppTheme.light(),
              home: const Scaffold(body: InventoryScreen()),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      // 1. Verify Low Stock Alert Banner
      expect(find.textContaining('Cảnh Báo Thiếu Tồn Kho Định Mức'),
          findsOneWidget);
      expect(find.text('Bổ Sung Ngay'), findsWidgets);

      // 2. Scroll and Verify Stocktake Section
      final stocktakeTitle =
          find.text('Kiểm Kê Kho Định Kỳ & Đối Soát Chênh Lệch');
      await tester.scrollUntilVisible(stocktakeTitle, 500,
          scrollable: find.byType(Scrollable).first);
      await tester.pumpAndSettle();

      expect(stocktakeTitle, findsOneWidget);
      expect(find.text('Mở Đợt Kiểm Kê Mới'), findsOneWidget);
      expect(find.text('Quầy kiểm kê theo ca'), findsOneWidget);
      final countButton = find.text('Nhập Số Đếm').first;
      await tester.scrollUntilVisible(countButton, 300,
          scrollable: find.byType(Scrollable).first);
      await tester.pumpAndSettle();

      // 3. Open Stocktake Detail Dialog
      await tester.tap(countButton);
      await tester.pumpAndSettle();

      expect(find.textContaining('Kiểm Kê Kho:'), findsOneWidget);
      expect(find.text('Gửi Duyệt Đối Soát'), findsOneWidget);
      expect(find.text('Lưu Số Đếm'), findsOneWidget);

      // Submit stocktake
      await tester.tap(find.text('Gửi Duyệt Đối Soát'));
      await tester.pumpAndSettle();

      final submittedText = find.textContaining('Chờ Quản lý duyệt');
      await tester.scrollUntilVisible(submittedText, 500,
          scrollable: find.byType(Scrollable).first);
      await tester.pumpAndSettle();

      // Verify status changed to submitted
      expect(submittedText, findsOneWidget);
    },
  );
}
