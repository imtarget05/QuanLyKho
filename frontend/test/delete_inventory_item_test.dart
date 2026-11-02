import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:kho_tra_sua/src/app/app_shell.dart';
import 'package:kho_tra_sua/src/core/theme/app_theme.dart';
import 'package:kho_tra_sua/src/data/models/dtos.dart';
import 'package:kho_tra_sua/src/data/repositories/fake_repository.dart';
import 'package:kho_tra_sua/src/features/inventory/inventory_screen.dart';

void main() {
  testWidgets(
      'Manager can delete a single item with confirmation dialog',
      (WidgetTester tester) async {
    tester.view.physicalSize = const Size(1200, 2400);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);

    final repo = FakeBankOpsRepository(latency: Duration.zero);
    const user = AppUser(
      id: 'u_manager',
      username: 'manager_test',
      displayName: 'Quản Lý Kho',
      roles: ['inventory_manager', 'admin'],
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

    // Verify item catalog is loaded
    final initialItems = await repo.getItems();
    expect(initialItems.isNotEmpty, isTrue);
    final targetItem = initialItems.first;

    // Verify delete button exists for this item
    final deleteBtn = find.byKey(Key('btn-delete-item-${targetItem.sku}'));
    await tester.scrollUntilVisible(deleteBtn, 300,
        scrollable: find.byType(Scrollable).first);
    expect(deleteBtn, findsOneWidget);

    // Tap delete button
    await tester.tap(deleteBtn);
    await tester.pumpAndSettle();

    // Verify confirmation dialog
    expect(find.text('Xác nhận xóa mặt hàng'), findsOneWidget);
    expect(
        find.textContaining('Bạn có chắc chắn muốn xóa mặt hàng "${targetItem.name}"'),
        findsOneWidget);

    // Confirm deletion
    final confirmBtn = find.byKey(Key('btn-confirm-delete-${targetItem.sku}'));
    expect(confirmBtn, findsOneWidget);
    await tester.tap(confirmBtn);
    await tester.pumpAndSettle();

    // Dialog closed and snackbar appears
    expect(find.text('Xác nhận xóa mặt hàng'), findsNothing);
    expect(find.textContaining('Đã xóa mặt hàng'), findsOneWidget);

    // Item is deleted from repo
    final updatedItems = await repo.getItems();
    expect(updatedItems.any((it) => it.id == targetItem.id), isFalse);
  });

  testWidgets(
      'Confirmation dialog shows warning when item has stock > 0',
      (WidgetTester tester) async {
    tester.view.physicalSize = const Size(1200, 2400);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);

    final repo = FakeBankOpsRepository(latency: Duration.zero);
    const user = AppUser(
      id: 'u_manager',
      username: 'manager_test',
      displayName: 'Quản Lý Kho',
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

    final balances = await repo.getBalances();
    // Find an item with balance > 0
    final itemWithStockId = balances
        .firstWhere((b) => (double.tryParse(b.quantity) ?? 0) > 0)
        .itemId;
    final items = await repo.getItems();
    final itemWithStock = items.firstWhere((it) => it.id == itemWithStockId);

    // Find and tap delete button
    final deleteBtn = find.byKey(Key('btn-delete-item-${itemWithStock.sku}'));
    await tester.scrollUntilVisible(deleteBtn, 300,
        scrollable: find.byType(Scrollable).first);
    expect(deleteBtn, findsOneWidget);
    await tester.tap(deleteBtn);
    await tester.pumpAndSettle();

    // Dialog should show remaining stock warning
    expect(find.text('Xác nhận xóa mặt hàng'), findsOneWidget);
    expect(find.textContaining('Cảnh báo: Mặt hàng đang còn tồn kho'), findsOneWidget);

    // Cancel deletion
    await tester.tap(find.text('Hủy'));
    await tester.pumpAndSettle();
    expect(find.text('Xác nhận xóa mặt hàng'), findsNothing);
  });

  testWidgets(
      'Manager can toggle batch selection mode, select all, and batch delete',
      (WidgetTester tester) async {
    tester.view.physicalSize = const Size(1200, 2400);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);

    final repo = FakeBankOpsRepository(latency: Duration.zero);
    const user = AppUser(
      id: 'u_manager',
      username: 'manager_test',
      displayName: 'Quản Lý Kho',
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

    // Toggle batch selection mode
    final toggleBatchBtn = find.byKey(const Key('btn-toggle-batch-select'));
    await tester.scrollUntilVisible(toggleBatchBtn, 300,
        scrollable: find.byType(Scrollable).first);
    expect(toggleBatchBtn, findsOneWidget);
    await tester.tap(toggleBatchBtn);
    await tester.pumpAndSettle();

    // Check batch selection UI appears
    expect(find.byKey(const Key('btn-close-batch-select')), findsOneWidget);
    expect(find.byKey(const Key('btn-select-all-items')), findsOneWidget);
    expect(find.byKey(const Key('btn-batch-delete-confirm')), findsOneWidget);

    // Tap "Chọn tất cả"
    await tester.tap(find.byKey(const Key('btn-select-all-items')));
    await tester.pumpAndSettle();

    final allItems = await repo.getItems();
    expect(find.text('Đã chọn ${allItems.length}/${allItems.length}'), findsOneWidget);

    // Tap "Xóa (N)"
    final batchDeleteBtn = find.byKey(const Key('btn-batch-delete-confirm'));
    await tester.tap(batchDeleteBtn);
    await tester.pumpAndSettle();

    // Verify batch delete confirmation dialog
    expect(find.text('Xác nhận xóa hàng loạt'), findsOneWidget);
    expect(find.textContaining('Bạn có chắc chắn muốn xóa ${allItems.length} mặt hàng'), findsOneWidget);

    // Confirm batch deletion
    final confirmBatchBtn = find.byKey(const Key('btn-confirm-batch-delete'));
    expect(confirmBatchBtn, findsOneWidget);
    await tester.tap(confirmBatchBtn);
    await tester.pumpAndSettle();

    // Dialog closes and all items deleted
    expect(find.text('Xác nhận xóa hàng loạt'), findsNothing);
    expect(find.textContaining('Đã xóa thành công'), findsOneWidget);

    final remainingItems = await repo.getItems();
    expect(remainingItems.isEmpty, isTrue);
  });

  testWidgets(
      'Non-manager role cannot see delete buttons or batch select',
      (WidgetTester tester) async {
    tester.view.physicalSize = const Size(1200, 2400);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);

    final repo = FakeBankOpsRepository(latency: Duration.zero);
    const user = AppUser(
      id: 'u_teller',
      username: 'teller_test',
      displayName: 'Giao dịch viên',
      roles: ['teller'], // Not inventory_manager / admin
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

    // Batch toggle button must NOT be visible
    expect(find.byKey(const Key('btn-toggle-batch-select')), findsNothing);

    // Single item delete buttons must NOT be visible
    final items = await repo.getItems();
    for (final it in items) {
      expect(find.byKey(Key('btn-delete-item-${it.sku}')), findsNothing);
    }
  });

  testWidgets(
      'Compact mobile mode shows PopupMenuButton with delete option and no layout overflow',
      (WidgetTester tester) async {
    // Mobile screen width (< 960 compact)
    tester.view.physicalSize = const Size(390, 844);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);

    final repo = FakeBankOpsRepository(latency: Duration.zero);
    const user = AppUser(
      id: 'u_manager',
      username: 'manager_test',
      displayName: 'Quản Lý Kho',
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
              body: InventoryScreen(
                mode: InventoryTabMode.stock,
                initialViewMode: 'list',
              ),
            ),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    final items = await repo.getItems();
    final firstItem = items.first;

    final menuBtn = find.byKey(Key('menu-item-${firstItem.sku}'));
    await tester.scrollUntilVisible(
      menuBtn,
      100,
      scrollable: find.byType(Scrollable).first,
    );
    await tester.ensureVisible(menuBtn);
    await tester.pumpAndSettle();
    expect(menuBtn, findsOneWidget);

    // Tap menu button to open popup menu
    await tester.tap(menuBtn);
    await tester.pumpAndSettle();

    // Verify "Xóa mặt hàng" menu item is shown
    final deleteMenuItem = find.text('Xóa mặt hàng');
    expect(deleteMenuItem, findsOneWidget);

    // Tap delete in menu
    await tester.tap(deleteMenuItem);
    await tester.pumpAndSettle();

    // Verify confirmation dialog opens
    expect(find.text('Xác nhận xóa mặt hàng'), findsOneWidget);

    // Cancel
    await tester.tap(find.text('Hủy'));
    await tester.pumpAndSettle();
    expect(find.text('Xác nhận xóa mặt hàng'), findsNothing);
  });
}
