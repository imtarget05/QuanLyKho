import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:kho_tra_sua/src/data/models/dtos.dart';
import 'package:kho_tra_sua/src/features/commerce/commerce_api.dart';
import 'package:kho_tra_sua/src/features/commerce/commerce_memory_store.dart';
import 'package:kho_tra_sua/src/features/commerce/commerce_workspace.dart';

void main() {
  const adminUser = AppUser(
    id: 'user-admin-1',
    username: 'admin_test',
    displayName: 'Quản Trị Viên Test',
    roles: ['admin'],
    capabilities: [
      'admin',
      'iam:admin',
      'owner:financial_reports',
      'inventory:create_request',
      'inventory:approve_request',
      'inventory:manage_catalog',
    ],
    email: 'admin@khotrasua.vn',
  );

  CommerceMemoryStore createPopulatedStore() {
    final store = CommerceMemoryStore.empty();
    store.init(
      items: [
        {
          'id': 'item-1',
          'sku': 'TRA-DEN-01',
          'name': 'Trà Đen Đặc Biệt',
          'category': 'Trà',
          'unit': 'kg',
          'min_stock': 10,
          'cost_price': 100000,
          'selling_price': 150000,
        },
        {
          'id': 'item-2',
          'sku': 'SUA-TUOI-01',
          'name': 'Sữa Tươi Thanh Trùng',
          'category': 'Sữa',
          'unit': 'hộp',
          'min_stock': 20,
          'cost_price': 30000,
          'selling_price': 45000,
        },
      ],
      balances: [
        {'item_id': 'item-1', 'quantity': 5.0, 'location_id': 'loc-1'}, // low stock: 5 <= 10
        {'item_id': 'item-2', 'quantity': 50.0, 'location_id': 'loc-1'},
      ],
      customers: [
        {'id': 'cust-1', 'name': 'Khách Vãng Lai', 'phone': '0901234567'},
      ],
      suppliers: [
        {'id': 'sup-1', 'name': 'Nhà Cung Cấp Trà', 'phone': '0987654321'},
      ],
      documents: [
        {
          'id': 'order-1',
          'code': 'SO-20261102-001',
          'kind': 'sale',
          'party_name': 'Khách Vãng Lai',
          'status': 'completed',
          'created_at': DateTime.now().toIso8601String(),
          'subtotal': 300000,
          'discount': 0,
          'vat': 0,
          'shipping': 0,
          'total': 300000,
          'paid': 200000, // outstanding: 100000
          'lines': [
            {
              'product_id': 'item-1',
              'product_name': 'Trà Đen Đặc Biệt',
              'quantity': 2.0,
              'unit_price': 150000,
              'cost_price': 100000,
              'amount': 300000,
            }
          ],
        },
        {
          'id': 'po-1',
          'code': 'PO-20261102-001',
          'kind': 'purchase',
          'party_name': 'Nhà Cung Cấp Trà',
          'status': 'completed',
          'created_at': DateTime.now().toIso8601String(),
          'subtotal': 500000,
          'discount': 0,
          'vat': 0,
          'shipping': 0,
          'total': 500000,
          'paid': 300000, // payable outstanding: 200000
          'lines': [
            {
              'product_id': 'item-1',
              'product_name': 'Trà Đen Đặc Biệt',
              'quantity': 5.0,
              'unit_price': 100000,
              'cost_price': 100000,
              'amount': 500000,
            }
          ],
        },
      ],
    );
    return store;
  }

  group('Milestone M1 - Homepage Revamp & Operational KPI Cards', () {
    testWidgets('Overview dashboard renders operational KPI cards and formatted numbers',
        (tester) async {
      tester.view.physicalSize = const Size(1280, 900);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      final store = createPopulatedStore();
      addTearDown(store.dispose);

      // Verify getters on CommerceMemoryStore
      expect(store.todayRevenue, equals(300000));
      expect(store.grossProfitToday, equals(100000));
      expect(store.customerReceivables, equals(100000));
      expect(store.supplierPayables, equals(200000));
      expect(store.lowStockItemsCount, equals(1));
      expect(store.inventoryValue, greaterThan(0));

      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: CommerceWorkspace(
              store: store,
              user: adminUser,
              userName: adminUser.displayName,
              initialIndex: 0,
              capabilities: adminUser.capabilities.toSet(),
              roles: adminUser.roles.toSet(),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      // Verify all 6 KPI cards exist
      expect(find.byKey(const Key('kpi-today-revenue')), findsOneWidget);
      expect(find.byKey(const Key('kpi-gross-profit')), findsOneWidget);
      expect(find.byKey(const Key('kpi-inventory-value')), findsOneWidget);
      expect(find.byKey(const Key('kpi-customer-receivables')), findsOneWidget);
      expect(find.byKey(const Key('kpi-supplier-payables')), findsOneWidget);
      expect(find.byKey(const Key('kpi-low-stock')), findsOneWidget);

      // Verify labels and trend badges
      expect(find.text('Doanh thu hôm nay'), findsOneWidget);
      expect(find.text('Lợi nhuận gộp'), findsOneWidget);
      expect(find.text('Giá trị tồn kho'), findsOneWidget);
      expect(find.text('Phải thu khách hàng'), findsOneWidget);
      expect(find.text('Phải trả nhà cung cấp'), findsOneWidget);
      expect(find.descendant(of: find.byKey(const Key('kpi-low-stock')), matching: find.text('Cảnh báo tồn kho')), findsOneWidget);
      expect(find.text('Hôm nay'), findsWidgets);
      expect(find.text('Cảnh báo'), findsOneWidget);
    });

    testWidgets('Quick-action subsystem launch tiles directly on homepage navigate into all 7 subsystems',
        (tester) async {
      tester.view.physicalSize = const Size(1280, 900);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      final store = createPopulatedStore();
      addTearDown(store.dispose);

      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: CommerceWorkspace(
              store: store,
              user: adminUser,
              userName: adminUser.displayName,
              initialIndex: 0,
              capabilities: adminUser.capabilities.toSet(),
              roles: adminUser.roles.toSet(),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      // 1. Launch Bán hàng (POS)
      final posTile = find.byKey(const Key('tile-subsystem-sales'));
      expect(posTile, findsOneWidget);
      await tester.tap(posTile);
      await tester.pumpAndSettle();
      expect(find.text('Quản lý bán hàng'), findsOneWidget);

      // Return to Overview via Sidebar
      await tester.tap(find.text('Tổng quan').first);
      await tester.pumpAndSettle();

      // 2. Launch Nhập hàng (Purchases)
      final purchaseTile = find.byKey(const Key('tile-subsystem-purchases'));
      expect(purchaseTile, findsOneWidget);
      await tester.tap(purchaseTile);
      await tester.pumpAndSettle();
      expect(find.text('Quản lý mua hàng'), findsOneWidget);

      // Return to Overview
      await tester.tap(find.text('Tổng quan').first);
      await tester.pumpAndSettle();

      // 3. Launch Kho hàng (Inventory)
      final invTile = find.byKey(const Key('tile-subsystem-inventory'));
      expect(invTile, findsOneWidget);
      await tester.tap(invTile);
      await tester.pumpAndSettle();
      expect(find.text('Kho hàng & Tồn kho'), findsOneWidget);

      // Return to Overview
      await tester.tap(find.text('Tổng quan').first);
      await tester.pumpAndSettle();

      // 4. Launch Công nợ (Debt)
      final debtTile = find.byKey(const Key('tile-subsystem-debt'));
      expect(debtTile, findsOneWidget);
      await tester.tap(debtTile);
      await tester.pumpAndSettle();
      expect(find.text('Sổ công nợ'), findsOneWidget);

      // Return to Overview
      await tester.tap(find.text('Tổng quan').first);
      await tester.pumpAndSettle();

      // 5. Launch Báo cáo (Reports)
      final reportTile = find.byKey(const Key('tile-subsystem-reports'));
      expect(reportTile, findsOneWidget);
      await tester.tap(reportTile);
      await tester.pumpAndSettle();
      expect(find.text('Báo cáo kinh doanh'), findsOneWidget);

      // Return to Overview
      await tester.tap(find.text('Tổng quan').first);
      await tester.pumpAndSettle();

      // 6. Launch Phê duyệt (Approvals)
      final appTile = find.byKey(const Key('tile-subsystem-approvals'));
      expect(appTile, findsOneWidget);
      await tester.tap(appTile);
      await tester.pumpAndSettle();
      expect(find.text('Phê duyệt phiếu'), findsOneWidget);

      // Return to Overview
      await tester.tap(find.text('Tổng quan').first);
      await tester.pumpAndSettle();

      // 7. Launch Cấu hình (Settings)
      final setTile = find.byKey(const Key('tile-subsystem-settings'));
      expect(setTile, findsOneWidget);
      await tester.tap(setTile);
      await tester.pumpAndSettle();
      expect(find.text('Cài đặt hệ thống'), findsOneWidget);
    });

    testWidgets('Session Revoked 401 triggers non-disruptive refresh dialog and invokes session refresh',
        (tester) async {
      final store = createPopulatedStore();
      addTearDown(store.dispose);

      bool refreshCalled = false;
      final api = CommerceApi(
        baseUrl: 'http://localhost:8000/api/v1',
        tokenProvider: () async => 'sample_token',
        userId: 'user-admin-1',
      );

      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: CommerceWorkspace(
              store: store,
              api: api,
              user: adminUser,
              userName: adminUser.displayName,
              initialIndex: 0,
              onRefresh: () async {
                refreshCalled = true;
              },
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      // Simulate 401 Session Revoked notification from api
      api.onSessionRevoked?.call('Phiên đăng nhập đã bị thu hồi hoặc quyền tài khoản đã thay đổi. Vui lòng đăng nhập lại.');
      await tester.pumpAndSettle();

      // Verify the session revoked dialog appeared
      expect(find.byKey(const Key('session-revoked-dialog')), findsOneWidget);
      expect(find.text('Thông báo quyền tài khoản'), findsOneWidget);
      expect(
        find.text('Quyền tài khoản đã thay đổi. Vui lòng làm mới phiên đăng nhập để tiếp tục.'),
        findsOneWidget,
      );

      final refreshBtn = find.byKey(const Key('btn-refresh-session'));
      expect(refreshBtn, findsOneWidget);
      expect(find.text('Làm mới phiên'), findsOneWidget);

      // Tap refresh action button
      await tester.tap(refreshBtn);
      await tester.pumpAndSettle();

      // Dialog is dismissed and onRefresh callback was triggered
      expect(find.byKey(const Key('session-revoked-dialog')), findsNothing);
      expect(refreshCalled, isTrue);
    });
  });
}
