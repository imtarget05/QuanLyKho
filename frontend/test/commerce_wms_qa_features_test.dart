import 'package:flutter_test/flutter_test.dart';
import 'package:kho_tra_sua/src/features/commerce/commerce_memory_store.dart';

void main() {
  group('WMS QA Improvements & Business Logic Tests', () {
    test('Multi-UOM support on CommerceProduct works correctly', () {
      final p1 = CommerceProduct(
        id: 'p-syrup',
        sku: 'NL-SYRUP',
        name: 'Siro Đường Đen',
        category: 'Nguyên liệu',
        unit: 'Chai',
        stock: 24,
        minimum: 6,
        cost: 65000,
        price: 95000,
        purchaseUnit: 'Thùng',
        conversionRate: 12.0,
      );

      expect(p1.hasConversion, isTrue);
      expect(p1.effectivePurchaseUnit, equals('Thùng'));
      expect(p1.conversionRate, equals(12.0));

      final p2 = CommerceProduct(
        id: 'p-cup',
        sku: 'VT-LY',
        name: 'Ly Nhựa 500ml',
        category: 'Vật tư',
        unit: 'Cái',
        stock: 500,
        minimum: 100,
        cost: 500,
        price: 1000,
      );

      expect(p2.hasConversion, isFalse);
      expect(p2.effectivePurchaseUnit, equals('Cái'));
      expect(p2.conversionRate, equals(1.0));
    });

    test('CommerceMemoryStore supports multi-locations and stock transfer', () {
      final store = CommerceMemoryStore.demo();
      expect(store.locations.length, greaterThanOrEqualTo(3));
      expect(store.locations.any((loc) => loc.code == 'MAIN'), isTrue);
      expect(store.locations.any((loc) => loc.code == 'BAR'), isTrue);

      final p = store.products.first;
      final initialTransfers = store.transfers.length;

      store.transferStock(
        productId: p.id,
        fromLocationId: 'loc-main',
        toLocationId: 'loc-bar',
        quantity: 5.0,
        note: 'Cấp nguyên liệu cho ca sáng',
      );

      expect(store.transfers.length, equals(initialTransfers + 1));
      final lastTransfer = store.transfers.first;
      expect(lastTransfer.productId, equals(p.id));
      expect(lastTransfer.fromLocationId, equals('loc-main'));
      expect(lastTransfer.toLocationId, equals('loc-bar'));
      expect(lastTransfer.quantity, equals(5.0));
      expect(lastTransfer.note, contains('Cấp nguyên liệu'));
    });

    test('addProduct in store correctly preserves purchaseUnit and conversionRate', () {
      final store = CommerceMemoryStore.demo();
      final p = store.addProduct(
        sku: 'NL-TEST-UOM',
        name: 'Bột Cacao Cao Cấp',
        category: 'Bột & Trà',
        unit: 'Gói 1kg',
        cost: 120000,
        price: 180000,
        minimum: 2,
        purchaseUnit: 'Thùng 10 gói',
        conversionRate: 10.0,
      );

      expect(p.purchaseUnit, equals('Thùng 10 gói'));
      expect(p.conversionRate, equals(10.0));
      expect(p.hasConversion, isTrue);
    });
  });
}
