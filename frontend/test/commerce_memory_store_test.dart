import 'package:flutter_test/flutter_test.dart';
import 'package:kho_tra_sua/src/features/commerce/commerce_memory_store.dart';

void main() {
  late CommerceMemoryStore store;

  setUp(() {
    store = CommerceMemoryStore.empty();
    store.replaceSnapshot(
      products: [
        const CommerceProduct(
            id: 'p1',
            sku: 'P1',
            name: 'Sản phẩm 1',
            category: 'Hàng hóa',
            unit: 'cái',
            stock: 18,
            minimum: 2,
            cost: 10000,
            price: 15000),
        const CommerceProduct(
            id: 'p2',
            sku: 'P2',
            name: 'Sản phẩm 2',
            category: 'Hàng hóa',
            unit: 'cái',
            stock: 12,
            minimum: 2,
            cost: 12000,
            price: 18000),
        const CommerceProduct(
            id: 'p3',
            sku: 'P3',
            name: 'Sản phẩm 3',
            category: 'Hàng hóa',
            unit: 'cái',
            stock: 8,
            minimum: 2,
            cost: 14000,
            price: 21000),
        const CommerceProduct(
            id: 'p4',
            sku: 'P4',
            name: 'Sản phẩm 4',
            category: 'Hàng hóa',
            unit: 'cái',
            stock: 3,
            minimum: 2,
            cost: 16000,
            price: 24000),
      ],
      customers: [
        const CommerceParty(id: 'c1', name: 'Khách kiểm thử', kind: 'customer')
      ],
      suppliers: [
        const CommerceParty(
            id: 's1', name: 'Nhà cung cấp kiểm thử', kind: 'supplier')
      ],
      orders: const [],
      payments: const [],
    );
  });
  tearDown(() => store.dispose());

  CommerceLine line(CommerceProduct product, double quantity) => CommerceLine(
        productId: product.id,
        name: product.name,
        unit: product.unit,
        quantity: quantity,
        unitPrice: product.price,
        unitCost: product.cost,
      );

  test('new RAM session starts without sample records', () {
    final blank = CommerceMemoryStore.empty();
    addTearDown(blank.dispose);
    expect(blank.products, isEmpty);
    expect(blank.customers, isEmpty);
    expect(blank.suppliers, isEmpty);
    expect(blank.orders, isEmpty);
    expect(blank.payments, isEmpty);
  });

  test('new products start at zero stock and duplicate SKU is rejected', () {
    final blank = CommerceMemoryStore.empty();
    addTearDown(blank.dispose);
    final product = blank.addProduct(
      sku: 'NEW-1',
      name: 'Sản phẩm mới',
      category: 'Hàng hóa',
      unit: 'cái',
      cost: 10000,
      price: 15000,
      minimum: 2,
    );
    expect(product.stock, 0);
    expect(
        () => blank.addProduct(
              sku: 'NEW-1',
              name: 'Tên khác',
              category: 'Hàng hóa',
              unit: 'cái',
              cost: 10000,
              price: 15000,
              minimum: 2,
            ),
        throwsStateError);
  });

  test('quotation does not reserve stock or create receivables', () {
    final product = store.products.first;
    final initialStock = product.stock;
    final initialReceivable = store.receivableTotal;

    final quote = store.createOrder(
      kind: 'quote',
      partyName: store.customers.first.name,
      lines: [line(product, 2)],
    );

    expect(quote.state, CommerceOrderState.draft);
    expect(store.product(product.id).stock, initialStock);
    expect(store.receivableTotal, initialReceivable);
    expect(store.quotes, contains(quote));
  });

  test('sale validates and reserves without changing on-hand stock', () {
    final before = store.products.map((product) => product.stock).toList();

    expect(
      () => store.createOrder(
        kind: 'sale',
        partyName: store.customers.first.name,
        lines: [
          line(store.products[0], 1),
          line(store.products[3], store.products[3].stock + 1),
        ],
      ),
      throwsStateError,
    );

    expect(
      store.products.map((product) => product.stock).toList(),
      before,
    );

    final product = store.products.first;
    final sale = store.createOrder(
      kind: 'sale',
      partyName: store.customers.first.name,
      lines: [line(product, 2)],
    );
    expect(sale.state, CommerceOrderState.pending);
    expect(store.product(product.id).stock, product.stock);
    expect(store.pendingOrders, contains(sale));
    store.approveOrder(sale.id);
    expect(store.product(product.id).stock, product.stock - 2);
    expect(store.orders.singleWhere((order) => order.id == sale.id).state,
        CommerceOrderState.completed);
  });

  test('converting a quote creates one pending sale without changing stock',
      () {
    final product = store.products.first;
    final quote = store.createOrder(
      kind: 'quote',
      partyName: store.customers.first.name,
      lines: [line(product, 2)],
    );
    final initialStock = store.product(product.id).stock;

    final sale = store.convertQuote(quote.id);

    expect(sale.kind, 'sale');
    expect(sale.state, CommerceOrderState.pending);
    expect(store.orders.where((order) => order.kind == 'sale'), hasLength(1));
    expect(store.product(product.id).stock, initialStock);
    store.approveOrder(sale.id);
    expect(store.product(product.id).stock, initialStock - 2);
    expect(
      store.orders.singleWhere((order) => order.id == quote.id).state,
      CommerceOrderState.converted,
    );
    expect(() => store.convertQuote(quote.id), throwsStateError);
  });

  test('rejecting a sale releases its reservation for another sale', () {
    final product = store.products.last;
    final sale = store.createOrder(
      kind: 'sale',
      partyName: store.customers.first.name,
      lines: [line(product, product.stock)],
    );
    store.rejectOrder(sale.id);

    final replacement = store.createOrder(
      kind: 'sale',
      partyName: store.customers.first.name,
      lines: [line(product, product.stock)],
    );
    expect(replacement.state, CommerceOrderState.pending);
    expect(store.product(product.id).stock, product.stock);
  });

  test('purchase and stocktake change stock only after approval', () {
    final product = store.products.first;
    final initialStock = product.stock;
    expect(
      () => store.createOrder(
        kind: 'purchase',
        partyName: store.suppliers.first.name,
        lines: [line(product, 1)],
      ),
      throwsStateError,
    );
    final purchase = store.createOrder(
      kind: 'purchase',
      partyName: store.suppliers.first.name,
      lines: [
        CommerceLine(
          productId: product.id,
          name: product.name,
          unit: product.unit,
          quantity: 3,
          unitPrice: product.cost,
          unitCost: product.cost,
          lotNo: 'LOT-TEST-1',
          expiryDate: DateTime.now().add(const Duration(days: 90)),
        )
      ],
    );
    expect(store.product(product.id).stock, initialStock);
    store.approveOrder(purchase.id);
    expect(store.product(product.id).stock, initialStock + 3);

    final stocktake = store.submitStocktake({product.id: 7});
    expect(store.product(product.id).stock, initialStock + 3);
    store.approveStocktake(stocktake.id);
    expect(store.product(product.id).stock, 7);
    expect(store.stocktakeHistory.single.status, 'Đã duyệt');
    expect(
        store.stocktakeHistory.single.bookCounts[product.id], initialStock + 3);
  });
}
