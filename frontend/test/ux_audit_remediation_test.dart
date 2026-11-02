import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:kho_tra_sua/src/app/app_shell.dart';
import 'package:kho_tra_sua/src/core/theme/app_theme.dart';
import 'package:kho_tra_sua/src/data/models/dtos.dart';
import 'package:kho_tra_sua/src/data/repositories/fake_repository.dart';
import 'package:kho_tra_sua/src/features/approvals/approvals_screen.dart';
import 'package:kho_tra_sua/src/features/inventory/inventory_screen.dart';
import 'package:kho_tra_sua/src/features/requests/widgets/stock_request_dialog.dart';

void main() {
  group('UX Audit Remediation Tests', () {
    testWidgets(
        '1. (P1) Fresh manual stock request starts blank and prompts review before saving',
        (tester) async {
      tester.view.physicalSize = const Size(1024, 768);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);

      final repo = FakeBankOpsRepository(latency: Duration.zero);
      final locations = await repo.getLocations();
      final items = await repo.getItems();

      await tester.pumpWidget(
        MaterialApp(
          theme: AppTheme.light(),
          home: Scaffold(
            body: StockRequestDialog(
              locations: locations,
              items: items,
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      // Verify fresh ticket defaults are blank (not prefilled dummy data)
      final reasonFinder = find.byKey(const Key('stock-reason-input'));
      expect(reasonFinder, findsOneWidget);
      final reasonField = tester.widget<TextField>(reasonFinder);
      expect(reasonField.controller?.text.isEmpty ?? true, isTrue);

      final supplierFinder = find.byKey(const Key('stock-supplier-input'));
      expect(supplierFinder, findsOneWidget);
      final supplierField = tester.widget<TextField>(supplierFinder);
      expect(supplierField.controller?.text.isEmpty ?? true, isTrue);

      final qtyFinder = find.byKey(const Key('stock-qty-input'));
      expect(qtyFinder, findsOneWidget);
      final qtyField = tester.widget<TextField>(qtyFinder);
      expect(qtyField.controller?.text.isEmpty ?? true, isTrue);

      // Fill in required data
      await tester.enterText(qtyFinder, '10');
      await tester.enterText(find.byKey(const Key('stock-price-input')), '50000');
      await tester.enterText(find.byKey(const Key('stock-lot-input')), 'LOT-001');
      await tester.enterText(supplierFinder, 'NCC Vinamilk');
      await tester.enterText(reasonFinder, 'Nhập bổ sung quầy');
      await tester.pumpAndSettle();

      // Tap "Lưu Phiếu"
      final saveBtn = find.byKey(const Key('stock-dialog-save-btn'));
      await tester.tap(saveBtn);
      await tester.pumpAndSettle();

      // Confirmation review modal MUST appear
      expect(find.text('Xác nhận tạo phiếu kho'), findsOneWidget);
      expect(find.byKey(const Key('stock-confirm-save-btn')), findsOneWidget);
      expect(find.text('Quay lại sửa'), findsOneWidget);

      // User confirms save
      await tester.tap(find.byKey(const Key('stock-confirm-save-btn')));
      await tester.pumpAndSettle();
      expect(find.text('Xác nhận tạo phiếu kho'), findsNothing);
    });

    testWidgets(
        '2. (P1) Alert "Bổ Sung Ngay" pre-fills target warehouse and suggested quantity',
        (tester) async {
      final repo = FakeBankOpsRepository(latency: Duration.zero);
      final locations = await repo.getLocations();
      final items = await repo.getItems();
      final targetLoc = locations.length > 1 ? locations[1] : locations[0];

      await tester.pumpWidget(
        MaterialApp(
          theme: AppTheme.light(),
          home: Scaffold(
            body: StockRequestDialog(
              locations: locations,
              items: items,
              initialLocationId: targetLoc.id,
              initialItemId: items.first.id,
              initialQuantity: 15.0,
              isFromAlert: true,
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      // Suggested quantity is prefilled from alert
      final qtyField = tester.widget<TextField>(find.byKey(const Key('stock-qty-input')));
      expect(qtyField.controller?.text, '15');

      // Reason indicates auto-supplement from alert
      final reasonField = tester.widget<TextField>(find.byKey(const Key('stock-reason-input')));
      expect(reasonField.controller?.text, contains('Bổ sung tồn kho'));
    });

    testWidgets(
        '3. (P2) Alert banner shows distinct item count and warehouse filters',
        (tester) async {
      tester.view.physicalSize = const Size(1024, 768);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);

      final repo = FakeBankOpsRepository(latency: Duration.zero);
      const user = AppUser(
        id: 'u_mgr',
        username: 'mgr',
        displayName: 'Quản Lý',
        roles: ['inventory_manager'],
      );

      await tester.pumpWidget(
        RepositoryScope(
          repository: repo,
          child: SessionScope(
            user: user,
            child: MaterialApp(
              theme: AppTheme.light(),
              home: const Scaffold(
                body: InventoryScreen(mode: InventoryTabMode.stock),
              ),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      // Check distinct ingredient count label
      await tester.scrollUntilVisible(find.byKey(const Key('btn-toggle-stock-alerts')), 300);
      expect(find.textContaining('nguyên liệu'), findsWidgets);
      expect(find.byKey(const Key('btn-toggle-stock-alerts')), findsOneWidget);

      // Check warehouse filter chips exist
      expect(find.textContaining('Tất cả kho'), findsOneWidget);
    });

    testWidgets(
        '4. (P2) Approvals screen distinguishes rule-based review and shows line items sheet',
        (tester) async {
      tester.view.physicalSize = const Size(1200, 800);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);

      final repo = FakeBankOpsRepository(latency: Duration.zero);
      final items = await repo.getItems();
      final locations = await repo.getLocations();

      // Create and submit a receipt request
      final stockReq = await repo.createStockRequest(
        destLocationId: locations.first.id,
        kind: RequestKind.payment,
        subKind: 'receipt',
        reason: 'Nhập hàng lô mới',
        lines: [
          StockRequestLine(
            itemId: items.first.id,
            quantity: '50',
            unitPrice: '45000',
            lotNo: 'LOT-NEW-01',
          ),
        ],
      );
      await repo.submitStockRequest(stockReq.id);

      const user = AppUser(
        id: 'u_checker',
        username: 'demo_checker',
        displayName: 'Khai Kiểm Duyệt',
        roles: ['inventory_manager', 'checker'],
      );

      await tester.pumpWidget(
        RepositoryScope(
          repository: repo,
          child: SessionScope(
            user: user,
            child: MaterialApp(
              theme: AppTheme.light(),
              home: const Scaffold(
                body: ApprovalsScreen(),
              ),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      // Check line items inspection button exists
      final viewLinesBtn = find.byKey(Key('btn-view-lines-${stockReq.id}'));
      expect(viewLinesBtn, findsOneWidget);

      await tester.tap(viewLinesBtn);
      await tester.pumpAndSettle();

      // Bottom sheet displays line items preview
      expect(find.textContaining('Chi tiết chứng từ'), findsOneWidget);
      expect(find.text('Danh sách dòng hàng:'), findsOneWidget);
      expect(find.textContaining('LOT-NEW-01'), findsOneWidget);
      final closeBtn = find.byTooltip('Đóng');
      expect(closeBtn, findsOneWidget);
      await tester.tap(closeBtn);
      await tester.pumpAndSettle();
    });
  });
}
