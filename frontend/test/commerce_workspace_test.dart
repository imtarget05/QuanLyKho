import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:kho_tra_sua/src/features/commerce/commerce_memory_store.dart';
import 'package:kho_tra_sua/src/features/commerce/commerce_workspace.dart';

void main() {
  testWidgets('mobile workspace keeps the main business pages usable',
      (tester) async {
    tester.view.physicalSize = const Size(390, 844);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final store = CommerceMemoryStore.empty();
    addTearDown(store.dispose);
    await tester.pumpWidget(MaterialApp(
      home: CommerceWorkspace(store: store),
    ));
    expect(find.byKey(const Key('commerce-demo-banner')), findsOneWidget);
    expect(find.textContaining('Dữ liệu mô phỏng trên thiết bị này'), findsOneWidget);

    await tester.tap(find.text('Bán hàng').first);
    await tester.pumpAndSettle();
    expect(find.text('Quản lý bán hàng'), findsOneWidget);
    await tester.tap(find.text('Báo giá').first);
    await tester.pumpAndSettle();
    expect(find.text('Danh sách báo giá'), findsOneWidget);

    await tester.tap(find.text('Mua hàng').first);
    await tester.pumpAndSettle();
    expect(find.text('Quản lý mua hàng'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('mobile approval cards fit and keep both actions visible',
      (tester) async {
    tester.view.physicalSize = const Size(390, 844);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final store = CommerceMemoryStore.empty();
    addTearDown(store.dispose);
    final product = store.addProduct(
      sku: 'MOBILE-1',
      name: 'Trà thử nghiệm',
      category: 'Nguyên liệu',
      unit: 'kg',
      cost: 10000,
      price: 15000,
      minimum: 1,
    );
    store.submitStocktake({product.id: 0});

    await tester.pumpWidget(MaterialApp(home: CommerceWorkspace(store: store)));
    await tester.tap(find.text('Thêm').last);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Duyệt phiếu'));
    await tester.pumpAndSettle();

    expect(find.text('Phiếu chờ duyệt'), findsOneWidget);
    expect(find.text('Từ chối'), findsOneWidget);
    expect(find.text('Duyệt'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('empty workspace exposes simple commerce sections and RAM setup',
      (tester) async {
    tester.view.physicalSize = const Size(1280, 900);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final store = CommerceMemoryStore.empty();
    addTearDown(store.dispose);
    await tester.pumpWidget(MaterialApp(
      home: CommerceWorkspace(store: store),
    ));

    expect(store.products, isEmpty);
    expect(store.orders, isEmpty);
    expect(find.text('Quản lý bán hàng'), findsOneWidget);

    await tester.tap(find.text('Bán hàng').first);
    await tester.pumpAndSettle();
    expect(find.text('Quản lý bán hàng'), findsOneWidget);
    expect(find.text('Khách hàng'), findsWidgets);
    await tester.tap(find.text('Báo giá').first);
    await tester.pumpAndSettle();
    expect(find.text('Danh sách báo giá'), findsOneWidget);
    await tester.tap(find.text('Khách hàng').first);
    await tester.pumpAndSettle();
    expect(find.text('Danh sách khách hàng'), findsOneWidget);

    await tester.tap(find.text('Mua hàng').first);
    await tester.pumpAndSettle();
    expect(find.text('Quản lý mua hàng'), findsOneWidget);
    await tester.tap(find.text('Nhà cung cấp').first);
    await tester.pumpAndSettle();
    expect(find.text('Danh sách nhà cung cấp'), findsOneWidget);

    await tester.tap(find.text('Kho hàng').first);
    await tester.pumpAndSettle();
    expect(find.text('Quản lý kho hàng'), findsOneWidget);
    expect(
      find.text(
          'Chưa có sản phẩm. Thêm sản phẩm trước, sau đó tạo phiếu mua để nhập tồn kho.'),
      findsOneWidget,
    );
    expect(find.text('Thêm sản phẩm'), findsOneWidget);
    await tester.tap(find.text('Lịch sử kho'));
    await tester.pumpAndSettle();
    expect(find.text('Biến động tồn kho'), findsOneWidget);
    expect(find.text('Lịch sử kiểm kê'), findsOneWidget);
    expect(find.text('Chưa có biến động kho.'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('live read-only capabilities hide all write actions',
      (tester) async {
    tester.view.physicalSize = const Size(1280, 900);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final store = CommerceMemoryStore.empty();
    addTearDown(store.dispose);
    await tester.pumpWidget(MaterialApp(
      home: CommerceWorkspace(
        store: store,
        capabilities: const {'inventory:view_balances'},
      ),
    ));

    await tester.tap(find.text('Bán hàng').first);
    await tester.pumpAndSettle();
    expect(find.text('Tạo đơn bán'), findsNothing);
    expect(find.text('Tạo báo giá'), findsNothing);
    expect(find.text('Thêm khách hàng'), findsNothing);

    await tester.tap(find.text('Kho hàng').first);
    await tester.pumpAndSettle();
    expect(find.text('Thêm sản phẩm'), findsNothing);
    expect(find.text('Kiểm kê'), findsNothing);

    await tester.tap(find.text('Công nợ').first);
    await tester.pumpAndSettle();
    expect(find.text('Ghi nhận'), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('desktop exposes approval only to approvers', (tester) async {
    tester.view.physicalSize = const Size(1280, 900);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final store = CommerceMemoryStore.empty();
    addTearDown(store.dispose);

    await tester.pumpWidget(MaterialApp(
      home: CommerceWorkspace(
        store: store,
        capabilities: const {'inventory:approve_request'},
      ),
    ));
    expect(find.text('Duyệt phiếu'), findsOneWidget);
    await tester.tap(find.text('Duyệt phiếu'));
    await tester.pumpAndSettle();
    expect(find.text('Phiếu chờ duyệt'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('tablet uses the operations sidebar and sales filters',
      (tester) async {
    tester.view.physicalSize = const Size(750, 900);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final store = CommerceMemoryStore.empty();
    addTearDown(store.dispose);

    await tester.pumpWidget(MaterialApp(
      home: CommerceWorkspace(store: store),
    ));

    expect(find.text('VẬN HÀNH'), findsOneWidget);
    expect(find.text('Quản lý bán hàng'), findsOneWidget);
    expect(find.byType(NavigationBar), findsNothing);
    expect(find.byType(DropdownButton<String>), findsNWidgets(3));
    expect(tester.takeException(), isNull);
  });

  testWidgets('inventory can filter out-of-stock products', (tester) async {
    tester.view.physicalSize = const Size(1280, 900);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final store = CommerceMemoryStore.empty();
    addTearDown(store.dispose);
    store.replaceSnapshot(
      products: const [
        CommerceProduct(
          id: 'empty',
          sku: 'EMPTY-1',
          name: 'Hết hàng',
          category: 'Nguyên liệu',
          unit: 'kg',
          stock: 0,
          minimum: 2,
          cost: 10000,
          price: 15000,
        ),
        CommerceProduct(
          id: 'available',
          sku: 'READY-1',
          name: 'Còn hàng',
          category: 'Nguyên liệu',
          unit: 'kg',
          stock: 9,
          minimum: 2,
          cost: 10000,
          price: 15000,
        ),
      ],
      customers: const [],
      suppliers: const [],
      orders: const [],
      payments: const [],
    );

    await tester.pumpWidget(MaterialApp(home: CommerceWorkspace(store: store)));
    await tester.tap(find.text('Kho hàng').first);
    await tester.pumpAndSettle();
    expect(find.text('EMPTY-1'), findsOneWidget);
    expect(find.text('READY-1'), findsOneWidget);

    await tester.tap(find.byType(DropdownButton<String>).at(1));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Hết hàng').last);
    await tester.pumpAndSettle();

    expect(find.text('EMPTY-1'), findsOneWidget);
    expect(find.text('READY-1'), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('debt view filters by payment due date', (tester) async {
    tester.view.physicalSize = const Size(1280, 900);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final store = CommerceMemoryStore.empty();
    addTearDown(store.dispose);
    final product = store.addProduct(
      sku: 'DEBT-1',
      name: 'Nguyên liệu công nợ',
      category: 'Nguyên liệu',
      unit: 'kg',
      cost: 10000,
      price: 15000,
      minimum: 2,
    );
    final supplier = store.addParty(
      kind: 'supplier',
      name: 'Nhà cung cấp thử nghiệm',
    );
    final dueDate = DateTime.now().add(const Duration(days: 2));
    final purchase = store.createOrder(
      kind: 'purchase',
      partyName: supplier.name,
      dueDate: dueDate,
      lines: [
        CommerceLine(
          productId: product.id,
          name: product.name,
          unit: product.unit,
          quantity: 10,
          unitPrice: product.cost,
          unitCost: product.cost,
          lotNo: 'DEBT-LOT-1',
          expiryDate: DateTime.now().add(const Duration(days: 90)),
        ),
      ],
    );
    store.approveOrder(purchase.id);
    store.recordPayment(purchase.id, purchase.total ~/ 2);

    await tester.pumpWidget(MaterialApp(home: CommerceWorkspace(store: store)));
    await tester.tap(find.text('Công nợ').first);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Phải trả nhà cung cấp'));
    await tester.pumpAndSettle();
    expect(find.text(supplier.name), findsOneWidget);
    expect(find.byType(DropdownButton<String>), findsOneWidget);

    await tester.tap(find.byType(DropdownButton<String>));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Quá hạn').last);
    await tester.pumpAndSettle();
    expect(find.text(supplier.name), findsNothing);

    await tester.tap(find.byType(DropdownButton<String>));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Còn hạn').last);
    await tester.pumpAndSettle();
    expect(find.text(supplier.name), findsOneWidget);
    expect(find.text('Ghi nhận'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
}
