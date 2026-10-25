import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:kho_tra_sua/src/app/app_shell.dart';
import 'package:kho_tra_sua/src/core/theme/app_theme.dart';
import 'package:kho_tra_sua/src/data/models/dtos.dart';
import 'package:kho_tra_sua/src/data/repositories/fake_repository.dart';
import 'package:kho_tra_sua/src/features/inventory/inventory_screen.dart';
import 'package:kho_tra_sua/src/features/reports/reports_screen.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  const user = AppUser(
    id: 'u_manager',
    username: 'demo_manager',
    displayName: 'Quản Lý Kho',
    roles: ['manager', 'admin'],
  );

  testWidgets(
    'InventoryScreen renders Expiry Alert Banner and 10-column Stocktake Table with touch +/- controls',
    (tester) async {
      tester.view.physicalSize = const Size(1400, 1000);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);

      final repo = FakeBankOpsRepository(latency: Duration.zero);
      final locs = await repo.getLocations();

      // The stocktake outbox persists to SharedPreferences; mock the plugin.
      SharedPreferences.setMockInitialValues({});

      // Create an open shift stocktake
      await repo.createStocktake(
        locationId: locs.first.id,
        shiftCode: 'morning',
        note: 'Ca Sáng Trực Tiếp',
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

      // 1. Verify Expiry Alert Banner is displayed (from Fake repository seed)
      expect(
        find.textContaining('Cảnh Báo Hạn Sử Dụng Nguyên Liệu'),
        findsOneWidget,
      );
      expect(find.text('Ưu tiên dùng'), findsWidgets);

      // 2. Scroll to Stocktake Desk and open the shift stocktake
      final deskTitle = find.text('Quầy kiểm kê theo ca');
      await tester.scrollUntilVisible(deskTitle, 500,
          scrollable: find.byType(Scrollable).first);
      await tester.pumpAndSettle();

      final openStocktakeBtn = find.text('Mở phiên kiểm kê');
      expect(openStocktakeBtn, findsOneWidget);
      await tester.tap(openStocktakeBtn);
      await tester.pumpAndSettle();

      // 3. Verify 10-column headers in dialog
      final dialogFinder = find.byType(AlertDialog);
      expect(
          find.descendant(
              of: dialogFinder, matching: find.text('STT')),
          findsOneWidget);
      expect(
          find.descendant(
              of: dialogFinder, matching: find.text('Nguyên liệu')),
          findsOneWidget);
      expect(
          find.descendant(
              of: dialogFinder, matching: find.text('ĐVT')),
          findsOneWidget);
      expect(
          find.descendant(
              of: dialogFinder, matching: find.text('Tồn đầu')),
          findsOneWidget);
      expect(
          find.descendant(
              of: dialogFinder, matching: find.text('Nhập')),
          findsOneWidget);
      expect(
          find.descendant(
              of: dialogFinder, matching: find.text('Sử dụng (+/-)')),
          findsOneWidget);
      expect(
          find.descendant(
              of: dialogFinder, matching: find.text('Còn lại')),
          findsOneWidget);
      expect(
          find.descendant(
              of: dialogFinder, matching: find.text('Kiểm thực tế (+/-)')),
          findsOneWidget);
      expect(
          find.descendant(
              of: dialogFinder, matching: find.text('Độ lệch')),
          findsOneWidget);
      expect(
          find.descendant(
              of: dialogFinder, matching: find.text('Trạng thái & Lý do')),
          findsOneWidget);

      // 4. Verify touch +/- buttons exist
      final plusButtons = find.byIcon(Icons.add);
      expect(plusButtons, findsWidgets);
      final minusButtons = find.byIcon(Icons.remove);
      expect(minusButtons, findsWidgets);

      // Tap + button on the first touch field to increment used quantity
      await tester.tap(plusButtons.first);
      await tester.pumpAndSettle();

      // 5. Verify Save and Submit buttons exist
      expect(find.text('Lưu Số Đếm'), findsOneWidget);
      expect(find.text('Gửi Duyệt Đối Soát'), findsOneWidget);

      // Save counts
      await tester.tap(find.text('Lưu Số Đếm'));
      await tester.pumpAndSettle();

      expect(find.text('Đã lưu số kiểm đếm thực tế!'), findsOneWidget);
    },
  );

  testWidgets(
    'ReportsScreen renders Top Consumption F&B tab and Shift History tab',
    (tester) async {
      tester.view.physicalSize = const Size(1400, 1000);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);

      final repo = FakeBankOpsRepository(latency: Duration.zero);

      await tester.pumpWidget(
        RepositoryScope(
          repository: repo,
          child: SessionScope(
            user: user,
            child: MaterialApp(
              theme: AppTheme.light(),
              home: const Scaffold(body: ReportsScreen()),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      // 1. Verify Top Tiêu Hao F&B Tab
      final consumptionTab =
          find.byKey(const Key('tab-reports-consumption-top'));
      expect(consumptionTab, findsOneWidget);
      await tester.tap(consumptionTab);
      await tester.pumpAndSettle();

      expect(
        find.textContaining('Top Nguyên Liệu Tiêu Hao (SRS §3.5)'),
        findsOneWidget,
      );
      expect(find.text('#1'), findsOneWidget);

      // 2. Verify Shift History Tab
      final shiftHistoryTab = find.byKey(const Key('tab-reports-shift-history'));
      expect(shiftHistoryTab, findsOneWidget);
      await tester.tap(shiftHistoryTab);
      await tester.pumpAndSettle();

      expect(
        find.textContaining('Lịch Sử Chốt Ca & Đối Soát Nhân Viên (SRS §3.5)'),
        findsOneWidget,
      );
    },
  );
}
