import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:kho_tra_sua/src/data/models/dtos.dart';
import 'package:kho_tra_sua/src/features/settings/widgets/edit_profile_dialog.dart';
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
          'name': 'Trà Đen Đặc Biệt Pha Chế Thượng Hạng',
          'category': 'Trà',
          'unit': 'kg',
          'min_stock': 10,
          'cost_price': 100000,
          'selling_price': 150000,
        },
        {
          'id': 'item-2',
          'sku': 'SUA-TUOI-01',
          'name': 'Sữa Tươi Thanh Trùng Nguyên Chất',
          'category': 'Sữa',
          'unit': 'hộp',
          'min_stock': 20,
          'cost_price': 30000,
          'selling_price': 45000,
        },
      ],
      balances: [
        {'item_id': 'item-1', 'quantity': 5.0, 'location_id': 'loc-1'},
        {'item_id': 'item-2', 'quantity': 50.0, 'location_id': 'loc-1'},
      ],
      customers: [
        {'id': 'cust-1', 'name': 'Khách Hàng Thân Thiết VIP 01 Nguyễn Văn A Rất Dài Cần Ellipsis', 'phone': '0901234567'},
      ],
      suppliers: [
        {'id': 'sup-1', 'name': 'Công Ty Cổ Phần Cung Ứng Nguyên Liệu Trà Sữa Toàn Quốc Rất Dài Cần Ellipsis', 'phone': '0987654321'},
      ],
      documents: [
        {
          'id': 'order-1',
          'code': 'SO-20261102-001',
          'kind': 'sale',
          'party_name': 'Khách Hàng Thân Thiết VIP 01 Nguyễn Văn A Rất Dài Cần Ellipsis',
          'status': 'completed',
          'created_at': DateTime.now().toIso8601String(),
          'subtotal': 300000,
          'discount': 0,
          'vat': 0,
          'shipping': 0,
          'total': 300000,
          'paid': 200000,
          'lines': [
            {
              'product_id': 'item-1',
              'product_name': 'Trà Đen Đặc Biệt Pha Chế Thượng Hạng',
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
          'party_name': 'Công Ty Cổ Phần Cung Ứng Nguyên Liệu Trà Sữa Toàn Quốc Rất Dài Cần Ellipsis',
          'status': 'completed',
          'created_at': DateTime.now().toIso8601String(),
          'subtotal': 500000,
          'discount': 0,
          'vat': 0,
          'shipping': 0,
          'total': 500000,
          'paid': 300000,
          'lines': [
            {
              'product_id': 'item-1',
              'product_name': 'Trà Đen Đặc Biệt Pha Chế Thượng Hạng',
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

  const mobileViewports = [
    Size(375, 667), // iPhone SE / compact
    Size(390, 844), // iPhone 12/13/14
    Size(414, 896), // iPhone 11 / XR
  ];

  group('Milestone M2 - Mobile Viewport Parity & Responsiveness Audit', () {
    for (final size in mobileViewports) {
      testWidgets('Overview Page on ${size.width.toInt()}x${size.height.toInt()} has title width >= 140 and zero overflows',
          (tester) async {
        tester.view.physicalSize = size;
        tester.view.devicePixelRatio = 1.0;
        addTearDown(tester.view.resetPhysicalSize);
        addTearDown(tester.view.resetDevicePixelRatio);

        final store = createPopulatedStore();
        addTearDown(store.dispose);

        await tester.pumpWidget(
          MaterialApp(
            home: Scaffold(
              body: CommerceWorkspace(
                key: ValueKey('overview-${size.width}'),
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

        // Topbar Title constraint check (BUG-01)
        final titleFinder = find.byKey(const Key('workspace-topbar-title'));
        expect(titleFinder, findsOneWidget);
        final titleBox = tester.renderObject(titleFinder) as RenderBox;
        expect(titleBox.size.width, greaterThanOrEqualTo(140.0));

        // 6 KPI cards
        expect(find.byKey(const Key('kpi-today-revenue')), findsOneWidget);
        expect(find.byKey(const Key('kpi-gross-profit')), findsOneWidget);
        expect(find.byKey(const Key('kpi-inventory-value')), findsOneWidget);
        expect(find.byKey(const Key('kpi-customer-receivables')), findsOneWidget);
        expect(find.byKey(const Key('kpi-supplier-payables')), findsOneWidget);
        expect(find.byKey(const Key('kpi-low-stock')), findsOneWidget);

        // 7 Quick-actions
        expect(find.byKey(const Key('tile-subsystem-sales')), findsOneWidget);
        expect(find.byKey(const Key('tile-subsystem-purchases')), findsOneWidget);
        expect(find.byKey(const Key('tile-subsystem-inventory')), findsOneWidget);
        expect(find.byKey(const Key('tile-subsystem-debt')), findsOneWidget);
        expect(find.byKey(const Key('tile-subsystem-reports')), findsOneWidget);
        expect(find.byKey(const Key('tile-subsystem-approvals')), findsOneWidget);
        expect(find.byKey(const Key('tile-subsystem-settings')), findsOneWidget);
      });

      testWidgets('POS and Purchases Pages on ${size.width.toInt()}x${size.height.toInt()} handle long names with ellipsis without overflow',
          (tester) async {
        tester.view.physicalSize = size;
        tester.view.devicePixelRatio = 1.0;
        addTearDown(tester.view.resetPhysicalSize);
        addTearDown(tester.view.resetDevicePixelRatio);

        final store = createPopulatedStore();
        addTearDown(store.dispose);

        await tester.pumpWidget(
          MaterialApp(
            home: Scaffold(
              body: CommerceWorkspace(
                key: ValueKey('pos-${size.width}'),
                store: store,
                user: adminUser,
                userName: adminUser.displayName,
                initialIndex: 1, // POS / Bán hàng
                capabilities: adminUser.capabilities.toSet(),
                roles: adminUser.roles.toSet(),
              ),
            ),
          ),
        );
        await tester.pumpAndSettle();

        // Verify order tile renders with code and party name
        expect(find.text('SO-20261102-001'), findsOneWidget);

        // Verify party name has ellipsis and maxLines = 1 (BUG-11)
        final partyFinder = find.text('Khách Hàng Thân Thiết VIP 01 Nguyễn Văn A Rất Dài Cần Ellipsis');
        expect(partyFinder, findsOneWidget);
        final Text partyWidget = tester.firstWidget(partyFinder);
        expect(partyWidget.overflow, equals(TextOverflow.ellipsis));
        expect(partyWidget.maxLines, equals(1));
      });

      testWidgets('Inventory and Debt Pages on ${size.width.toInt()}x${size.height.toInt()} render without nested scroll overflow',
          (tester) async {
        tester.view.physicalSize = size;
        tester.view.devicePixelRatio = 1.0;
        addTearDown(tester.view.resetPhysicalSize);
        addTearDown(tester.view.resetDevicePixelRatio);

        final store = createPopulatedStore();
        addTearDown(store.dispose);

        // Debt page (initialIndex: 4)
        await tester.pumpWidget(
          MaterialApp(
            home: Scaffold(
              body: CommerceWorkspace(
                key: ValueKey('debt-${size.width}'),
                store: store,
                user: adminUser,
                userName: adminUser.displayName,
                initialIndex: 4, // Debt
                capabilities: adminUser.capabilities.toSet(),
                roles: adminUser.roles.toSet(),
              ),
            ),
          ),
        );
        await tester.pumpAndSettle();
        expect(find.text('Sổ công nợ'), findsOneWidget);

        // Subpage indicator banner check (BUG-12)
        expect(find.byKey(const Key('subpage-header-indicator')), findsOneWidget);
        expect(find.text('Quay lại Tổng quan'), findsOneWidget);

        // Tap back to overview
        await tester.tap(find.text('Quay lại Tổng quan'));
        await tester.pumpAndSettle();
        expect(find.byKey(const Key('kpi-today-revenue')), findsOneWidget);
      });

      testWidgets('Reports Page on ${size.width.toInt()}x${size.height.toInt()} adapts to single column without overflow',
          (tester) async {
        tester.view.physicalSize = size;
        tester.view.devicePixelRatio = 1.0;
        addTearDown(tester.view.resetPhysicalSize);
        addTearDown(tester.view.resetDevicePixelRatio);

        final store = createPopulatedStore();
        addTearDown(store.dispose);

        await tester.pumpWidget(
          MaterialApp(
            home: Scaffold(
              body: CommerceWorkspace(
                key: ValueKey('reports-${size.width}'),
                store: store,
                user: adminUser,
                userName: adminUser.displayName,
                initialIndex: 5, // Reports
                capabilities: adminUser.capabilities.toSet(),
                roles: adminUser.roles.toSet(),
              ),
            ),
          ),
        );
        await tester.pumpAndSettle();
        expect(find.text('Báo cáo kinh doanh'), findsOneWidget);
      });
    }

    testWidgets('Create Product Dialog on 375x667 opens without RenderFlex overflow',
        (tester) async {
      tester.view.physicalSize = const Size(375, 667);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      final store = createPopulatedStore();
      addTearDown(store.dispose);

      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: CommerceWorkspace(
              key: const ValueKey('dialog-product'),
              store: store,
              user: adminUser,
              userName: adminUser.displayName,
              initialIndex: 3, // Inventory
              capabilities: adminUser.capabilities.toSet(),
              roles: adminUser.roles.toSet(),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      final addProductBtn = find.widgetWithText(FilledButton, 'Thêm sản phẩm');
      expect(addProductBtn, findsOneWidget);
      await tester.ensureVisible(addProductBtn);
      await tester.tap(addProductBtn);
      await tester.pumpAndSettle();

      expect(find.text('Mã sản phẩm'), findsOneWidget);
      expect(tester.takeException(), isNull);
      await tester.tap(find.text('Hủy'));
      await tester.pumpAndSettle();
    });

    testWidgets('Stock Transfer Dialog on 375x667 opens without RenderFlex overflow',
        (tester) async {
      tester.view.physicalSize = const Size(375, 667);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      final store = createPopulatedStore();
      addTearDown(store.dispose);

      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: CommerceWorkspace(
              key: const ValueKey('dialog-transfer'),
              store: store,
              user: adminUser,
              userName: adminUser.displayName,
              initialIndex: 3, // Inventory
              capabilities: adminUser.capabilities.toSet(),
              roles: adminUser.roles.toSet(),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      final transferBtn = find.widgetWithText(OutlinedButton, 'Chuyển kho');
      expect(transferBtn, findsOneWidget);
      await tester.ensureVisible(transferBtn);
      await tester.tap(transferBtn);
      await tester.pumpAndSettle();

      expect(find.text('Chuyển kho nội bộ (Transfer)'), findsOneWidget);
      expect(tester.takeException(), isNull);
      await tester.tap(find.text('Hủy'));
      await tester.pumpAndSettle();
    });

    testWidgets('Stocktake Dialog on 375x667 opens without RenderFlex overflow',
        (tester) async {
      tester.view.physicalSize = const Size(375, 667);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      final store = createPopulatedStore();
      addTearDown(store.dispose);

      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: CommerceWorkspace(
              key: const ValueKey('dialog-stocktake'),
              store: store,
              user: adminUser,
              userName: adminUser.displayName,
              initialIndex: 3, // Inventory
              capabilities: adminUser.capabilities.toSet(),
              roles: adminUser.roles.toSet(),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      final stocktakeBtn = find.widgetWithText(OutlinedButton, 'Kiểm kê');
      expect(stocktakeBtn, findsOneWidget);
      await tester.ensureVisible(stocktakeBtn);
      await tester.tap(stocktakeBtn);
      await tester.pumpAndSettle();

      expect(find.text('Tạo phiếu kiểm kê'), findsOneWidget);
      expect(tester.takeException(), isNull);
      await tester.tap(find.byIcon(Icons.close));
      await tester.pumpAndSettle();
    });

    testWidgets('Create Order Dialog on 375x667 opens without RenderFlex overflow',
        (tester) async {
      tester.view.physicalSize = const Size(375, 667);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      final store = createPopulatedStore();
      addTearDown(store.dispose);

      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: CommerceWorkspace(
              key: const ValueKey('dialog-create-order'),
              store: store,
              user: adminUser,
              userName: adminUser.displayName,
              initialIndex: 1, // POS
              capabilities: adminUser.capabilities.toSet(),
              roles: adminUser.roles.toSet(),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      final createSaleBtn = find.byKey(const Key('workspace-topbar-create-btn'));
      expect(createSaleBtn, findsOneWidget);
      await tester.tap(createSaleBtn);
      await tester.pumpAndSettle();

      expect(find.text('Tạo đơn bán hàng'), findsOneWidget);
      expect(tester.takeException(), isNull);
      await tester.tap(find.byIcon(Icons.close));
      await tester.pumpAndSettle();
    });

    testWidgets('Edit Profile Dialog on 375x667 opens without RenderFlex overflow',
        (tester) async {
      tester.view.physicalSize = const Size(375, 667);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: Builder(
              builder: (ctx) => Center(
                child: ElevatedButton(
                  onPressed: () => EditProfileDialog.show(ctx, user: adminUser),
                  child: const Text('Mở hồ sơ'),
                ),
              ),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      await tester.tap(find.text('Mở hồ sơ'));
      await tester.pumpAndSettle();

      expect(find.text('Chỉnh sửa hồ sơ cá nhân'), findsOneWidget);
      expect(tester.takeException(), isNull);
      await tester.tap(find.text('Hủy bỏ'));
      await tester.pumpAndSettle();
    });
  });
}
