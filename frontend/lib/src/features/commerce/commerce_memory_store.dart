import 'package:flutter/foundation.dart';

enum CommerceOrderState { completed, pending, draft, converted, cancelled }

@immutable
class CommerceProduct {
  const CommerceProduct({
    required this.id,
    required this.sku,
    required this.name,
    required this.category,
    required this.unit,
    required this.stock,
    required this.minimum,
    required this.cost,
    required this.price,
  });

  final String id;
  final String sku;
  final String name;
  final String category;
  final String unit;
  final double stock;
  final double minimum;
  final int cost;
  final int price;

  CommerceProduct copyWith({
    double? stock,
    int? cost,
    int? price,
  }) =>
      CommerceProduct(
        id: id,
        sku: sku,
        name: name,
        category: category,
        unit: unit,
        stock: stock ?? this.stock,
        minimum: minimum,
        cost: cost ?? this.cost,
        price: price ?? this.price,
      );
}

@immutable
class CommerceParty {
  const CommerceParty({
    required this.id,
    required this.name,
    required this.kind,
    this.phone = '',
  });

  final String id;
  final String name;
  final String kind;
  final String phone;
}

@immutable
class CommerceLine {
  const CommerceLine({
    required this.productId,
    required this.name,
    required this.unit,
    required this.quantity,
    required this.unitPrice,
    required this.unitCost,
    this.lotNo = '',
    this.expiryDate,
  });

  final String productId;
  final String name;
  final String unit;
  final double quantity;
  final int unitPrice;
  final int unitCost;
  final String lotNo;
  final DateTime? expiryDate;

  int get amount => (quantity * unitPrice).round();
  int get costAmount => (quantity * unitCost).round();
}

@immutable
class CommerceOrder {
  const CommerceOrder({
    required this.id,
    required this.code,
    required this.kind,
    required this.partyName,
    required this.createdAt,
    required this.lines,
    required this.subtotal,
    required this.discount,
    required this.vat,
    required this.shipping,
    required this.total,
    required this.paid,
    required this.state,
    this.note = '',
    this.dueDate,
  });

  final String id;
  final String code;
  final String kind;
  final String partyName;
  final DateTime createdAt;
  final List<CommerceLine> lines;
  final int subtotal;
  final int discount;
  final int vat;
  final int shipping;
  final int total;
  final int paid;
  final CommerceOrderState state;
  final String note;
  final DateTime? dueDate;

  int get outstanding => total - paid;
  String get paymentStatus => kind == 'quote'
      ? state == CommerceOrderState.converted
          ? 'Đã chuyển đơn'
          : 'Chờ phản hồi'
      : state == CommerceOrderState.cancelled
          ? 'Đã từ chối'
          : state == CommerceOrderState.pending
              ? 'Chờ duyệt kho'
              : paid == 0
                  ? 'Chưa thanh toán'
                  : outstanding == 0
                      ? 'Đã thanh toán'
                      : 'Thanh toán một phần';

  CommerceOrder copyWith({int? paid, CommerceOrderState? state}) =>
      CommerceOrder(
        id: id,
        code: code,
        kind: kind,
        partyName: partyName,
        createdAt: createdAt,
        lines: lines,
        subtotal: subtotal,
        discount: discount,
        vat: vat,
        shipping: shipping,
        total: total,
        paid: paid ?? this.paid,
        state: state ?? this.state,
        note: note,
        dueDate: dueDate,
      );
}

@immutable
class CommercePayment {
  const CommercePayment({
    required this.orderCode,
    required this.partyName,
    required this.kind,
    required this.amount,
    required this.date,
    this.method = 'cash',
    this.reference = '',
  });

  final String orderCode;
  final String partyName;
  final String kind;
  final int amount;
  final DateTime date;
  final String method;
  final String reference;
}

@immutable
class CommerceStocktake {
  const CommerceStocktake({
    required this.id,
    required this.counts,
    required this.bookCounts,
    required this.createdAt,
    this.status = 'pending',
    this.inspector = 'Hệ thống',
    this.note = '',
  });
  final String id;
  final Map<String, double> counts;
  final Map<String, double> bookCounts;
  final DateTime createdAt;
  final String status;
  final String inspector;
  final String note;

  int get itemsCount => counts.length;
  int get increaseCount {
    var c = 0;
    for (final e in counts.entries) {
      final book = bookCounts[e.key] ?? 0;
      if (e.value > book) c++;
    }
    return c;
  }
  int get decreaseCount {
    var c = 0;
    for (final e in counts.entries) {
      final book = bookCounts[e.key] ?? 0;
      if (e.value < book) c++;
    }
    return c;
  }

  CommerceStocktake copyWithStatus(String value) => CommerceStocktake(
        id: id,
        counts: counts,
        bookCounts: bookCounts,
        createdAt: createdAt,
        status: value,
        inspector: inspector,
        note: note,
      );
}

class _LotBalance {
  _LotBalance({
    required this.lotNo,
    required this.expiryDate,
    required this.quantity,
  });
  final String lotNo;
  final DateTime? expiryDate;
  double quantity;
}

/// Offline business state. All collections live in process memory, start empty,
/// and are discarded when the app session ends; this class has no I/O.
class CommerceMemoryStore extends ChangeNotifier {
  CommerceMemoryStore._({
    required List<CommerceProduct> products,
    required List<CommerceParty> customers,
    required List<CommerceParty> suppliers,
    required List<CommerceOrder> orders,
    required List<CommercePayment> payments,
  })  : _products = products,
        _customers = customers,
        _suppliers = suppliers,
        _orders = orders,
        _payments = payments;

  factory CommerceMemoryStore.empty() => CommerceMemoryStore._(
        products: <CommerceProduct>[],
        customers: <CommerceParty>[],
        suppliers: <CommerceParty>[],
        orders: <CommerceOrder>[],
        payments: <CommercePayment>[],
      );

  factory CommerceMemoryStore.demo() {
    final products = <CommerceProduct>[
      const CommerceProduct(id: 'p-sy001', sku: 'SY001', name: 'Đường syrup', category: 'Nguyên liệu', unit: 'chai', stock: 0, minimum: 20, cost: 120000, price: 160000),
      const CommerceProduct(id: 'p-bm02', sku: 'BM02', name: 'Bánh Tiramisu', category: 'Thực phẩm', unit: 'cái', stock: 15, minimum: 15, cost: 25000, price: 45000),
      const CommerceProduct(id: 'p-mp015', sku: 'MP015', name: 'Máy pha mini', category: 'Thiết bị', unit: 'máy', stock: 2, minimum: 3, cost: 1500000, price: 2300000),
      const CommerceProduct(id: 'p-bt018', sku: 'BT018', name: 'Bánh cheesecake', category: 'Thực phẩm', unit: 'cái', stock: 3, minimum: 10, cost: 28000, price: 50000),
      const CommerceProduct(id: 'p-nl023', sku: 'NL023', name: 'Bột quế', category: 'Nguyên liệu', unit: 'gói', stock: 3, minimum: 6, cost: 106666, price: 150000),
      const CommerceProduct(id: 'p-hg005', sku: 'HG005', name: 'Hộp giấy', category: 'Bao bì', unit: 'hộp', stock: 181, minimum: 50, cost: 71050, price: 95000),
      const CommerceProduct(id: 'p-tc099', sku: 'TC099', name: 'Trân châu', category: 'Nguyên liệu', unit: 'kg', stock: 223, minimum: 20, cost: 40000, price: 75000),
      const CommerceProduct(id: 'p-tm027', sku: 'TM027', name: 'Máy xay lớn', category: 'Thiết bị', unit: 'máy', stock: 59, minimum: 2, cost: 511000, price: 850000),
      const CommerceProduct(id: 'p-cp001', sku: 'CP001', name: 'Cà phê rang xay', category: 'Nguyên liệu', unit: 'kg', stock: 304, minimum: 50, cost: 125000, price: 180000),
      const CommerceProduct(id: 'p-cc002', sku: 'CC002', name: 'Bột cacao', category: 'Nguyên liệu', unit: 'hộp', stock: 84, minimum: 20, cost: 90000, price: 135000),
      const CommerceProduct(id: 'p-st010', sku: 'ST010', name: 'Sữa tươi', category: 'Nguyên liệu', unit: 'hộp', stock: 179, minimum: 30, cost: 18000, price: 28000),
      const CommerceProduct(id: 'p-td011', sku: 'TD011', name: 'Trà đào túi lọc', category: 'Nguyên liệu', unit: 'gói', stock: 80, minimum: 25, cost: 35000, price: 55000),
      const CommerceProduct(id: 'p-ln001', sku: 'LN001', name: 'Ly nhựa', category: 'Bao bì', unit: 'ly', stock: 600, minimum: 100, cost: 1000, price: 2000),
      const CommerceProduct(id: 'p-kb003', sku: 'KB003', name: 'Kem béo', category: 'Nguyên liệu', unit: 'hộp', stock: 45, minimum: 15, cost: 65000, price: 95000),
      const CommerceProduct(id: 'p-bc016', sku: 'BC016', name: 'Bánh croissant', category: 'Thực phẩm', unit: 'cái', stock: 45, minimum: 10, cost: 22000, price: 39000),
    ];

    final customers = <CommerceParty>[
      const CommerceParty(id: 'c-1', name: 'Quán Trà Nhà Gió', kind: 'customer', phone: '0901234567'),
      const CommerceParty(id: 'c-2', name: 'Thanh Tuyền', kind: 'customer', phone: '0912345678'),
      const CommerceParty(id: 'c-3', name: 'NexUp', kind: 'customer', phone: '0988776655'),
      const CommerceParty(id: 'c-4', name: 'Cửa hàng An Nhiên', kind: 'customer', phone: '0933221100'),
      const CommerceParty(id: 'c-5', name: 'Đại lý Hoàng Gia', kind: 'customer', phone: '0944556677'),
      const CommerceParty(id: 'c-6', name: 'Shop Mộc Nhiên', kind: 'customer', phone: '0922334455'),
      const CommerceParty(id: 'c-7', name: 'Công ty Minh An', kind: 'customer', phone: '0966778899'),
      const CommerceParty(id: 'c-8', name: 'Khách vãng lai', kind: 'customer', phone: '0900000000'),
      const CommerceParty(id: 'c-9', name: 'Công ty Gia Phát', kind: 'customer', phone: '0977889900'),
      const CommerceParty(id: 'c-10', name: 'Siêu thị Mini Hòa Bình', kind: 'customer', phone: '0911223344'),
      const CommerceParty(id: 'c-11', name: 'Cafe Mây Trắng', kind: 'customer', phone: '0955667788'),
    ];

    final suppliers = <CommerceParty>[
      const CommerceParty(id: 's-1', name: 'Nguyên Liệu Pha Chế Pro', kind: 'supplier', phone: '0283838383'),
      const CommerceParty(id: 's-2', name: 'Thực phẩm GreenFarm', kind: 'supplier', phone: '0283939393'),
      const CommerceParty(id: 's-3', name: 'NCC An Phát', kind: 'supplier', phone: '0283737373'),
      const CommerceParty(id: 's-4', name: 'Nông sản Sạch Việt', kind: 'supplier', phone: '0283636363'),
      const CommerceParty(id: 's-5', name: 'Sản xuất Bao Bì Tấn Việt', kind: 'supplier', phone: '0283535353'),
      const CommerceParty(id: 's-6', name: 'Nhà phân phối Đông Á', kind: 'supplier', phone: '0283434343'),
      const CommerceParty(id: 's-7', name: 'Công ty Hoàng Nam', kind: 'supplier', phone: '0283333333'),
      const CommerceParty(id: 's-8', name: 'Bao bì Việt Phú', kind: 'supplier', phone: '0283232323'),
    ];

    final now = DateTime.now();

    final orders = <CommerceOrder>[
      // Bán hàng (Sales) khớp ảnh
      CommerceOrder(
        id: 'hd-029',
        code: 'HD029',
        kind: 'sale',
        partyName: 'NexUp',
        createdAt: DateTime(now.year, 7, 5),
        dueDate: DateTime(now.year, 7, 20),
        lines: const [
          CommerceLine(productId: 'p-cp001', name: 'Cà phê rang xay', unit: 'kg', quantity: 15, unitPrice: 180000, unitCost: 125000),
          CommerceLine(productId: 'p-cc002', name: 'Bột cacao', unit: 'hộp', quantity: 6, unitPrice: 135000, unitCost: 90000),
        ],
        subtotal: 3510000,
        discount: 0,
        vat: 28000,
        shipping: 0,
        total: 3538000,
        paid: 0,
        state: CommerceOrderState.completed,
        note: 'HD cashback VIP',
      ),
      CommerceOrder(
        id: 'hd-027',
        code: 'HD027',
        kind: 'sale',
        partyName: 'Thanh Tuyền',
        createdAt: DateTime(now.year, 7, 4),
        dueDate: DateTime(now.year, 7, 18),
        lines: const [
          CommerceLine(productId: 'p-tc099', name: 'Trân châu', unit: 'kg', quantity: 80, unitPrice: 75000, unitCost: 40000),
          CommerceLine(productId: 'p-st010', name: 'Sữa tươi', unit: 'hộp', quantity: 45, unitPrice: 28000, unitCost: 18000),
        ],
        subtotal: 7260000,
        discount: 0,
        vat: 36000,
        shipping: 0,
        total: 7296000,
        paid: 150000,
        state: CommerceOrderState.completed,
        note: 'Giao sáng sớm',
      ),
      CommerceOrder(
        id: 'hd-025',
        code: 'HD025',
        kind: 'sale',
        partyName: 'Quán Trà Nhà Gió',
        createdAt: DateTime(now.year, 7, 3),
        dueDate: DateTime(now.year, 7, 7),
        lines: const [
          CommerceLine(productId: 'p-bm02', name: 'Bánh Tiramisu', unit: 'cái', quantity: 10, unitPrice: 45000, unitCost: 25000),
          CommerceLine(productId: 'p-bc016', name: 'Bánh croissant', unit: 'cái', quantity: 10, unitPrice: 39000, unitCost: 22000),
        ],
        subtotal: 840000,
        discount: 84000,
        vat: 75600,
        shipping: 0,
        total: 831600,
        paid: 831600,
        state: CommerceOrderState.completed,
        note: 'Hẹn 07 thanh toán',
      ),
      CommerceOrder(
        id: 'hd-024',
        code: 'HD024',
        kind: 'sale',
        partyName: 'Cửa hàng An Nhiên',
        createdAt: DateTime(now.year, 6, 27),
        dueDate: DateTime(now.year, 7, 15),
        lines: const [
          CommerceLine(productId: 'p-td011', name: 'Trà đào túi lọc', unit: 'gói', quantity: 50, unitPrice: 55000, unitCost: 35000),
          CommerceLine(productId: 'p-kb003', name: 'Kem béo', unit: 'hộp', quantity: 4, unitPrice: 95000, unitCost: 65000),
        ],
        subtotal: 3130000,
        discount: 31200,
        vat: 0,
        shipping: 0,
        total: 3098800,
        paid: 0,
        state: CommerceOrderState.completed,
        note: 'Bên cửa hàng nợ cần theo dõi',
      ),
      CommerceOrder(
        id: 'hd-023',
        code: 'HD023',
        kind: 'sale',
        partyName: 'Đại lý Hoàng Gia',
        createdAt: DateTime(now.year, 6, 22),
        dueDate: DateTime(now.year, 7, 2),
        lines: const [
          CommerceLine(productId: 'p-cp001', name: 'Cà phê rang xay', unit: 'kg', quantity: 16, unitPrice: 180000, unitCost: 125000),
        ],
        subtotal: 2880000,
        discount: 0,
        vat: 51500,
        shipping: 0,
        total: 2931500,
        paid: 0,
        state: CommerceOrderState.completed,
        note: 'Chờ đối soát cuối tháng',
      ),
      CommerceOrder(
        id: 'hd-022',
        code: 'HD022',
        kind: 'sale',
        partyName: 'Shop Mộc Nhiên',
        createdAt: DateTime(now.year, 6, 17),
        dueDate: DateTime(now.year, 6, 25),
        lines: const [
          CommerceLine(productId: 'p-hg005', name: 'Hộp giấy', unit: 'hộp', quantity: 16, unitPrice: 95000, unitCost: 71050),
        ],
        subtotal: 1520000,
        discount: 0,
        vat: 53360,
        shipping: 0,
        total: 1573360,
        paid: 1573360,
        state: CommerceOrderState.completed,
        note: 'Đã thanh toán',
      ),
      CommerceOrder(
        id: 'hd-021',
        code: 'HD021',
        kind: 'sale',
        partyName: 'Công ty Minh An',
        createdAt: DateTime(now.year, 6, 12),
        dueDate: DateTime(now.year, 6, 22),
        lines: const [
          CommerceLine(productId: 'p-tc099', name: 'Trân châu', unit: 'kg', quantity: 33, unitPrice: 75000, unitCost: 40000),
        ],
        subtotal: 2475000,
        discount: 0,
        vat: 52208,
        shipping: 0,
        total: 2527208,
        paid: 0,
        state: CommerceOrderState.completed,
        note: 'Đang xử lý nợ',
      ),
      CommerceOrder(
        id: 'hd-020',
        code: 'HD020',
        kind: 'sale',
        partyName: 'Khách vãng lai',
        createdAt: DateTime(now.year, 6, 11),
        dueDate: DateTime(now.year, 6, 11),
        lines: const [
          CommerceLine(productId: 'p-mp015', name: 'Máy pha mini', unit: 'máy', quantity: 1, unitPrice: 2300000, unitCost: 1500000),
        ],
        subtotal: 2300000,
        discount: 20000,
        vat: 0,
        shipping: 0,
        total: 2280000,
        paid: 2280000,
        state: CommerceOrderState.completed,
        note: 'Thanh toán tiền mặt',
      ),

      // Mua hàng (Purchases) khớp ảnh
      CommerceOrder(
        id: 'pm-019',
        code: 'PM019',
        kind: 'purchase',
        partyName: 'Nguyên Liệu Pha Chế Pro',
        createdAt: DateTime(now.year, 7, 1),
        dueDate: DateTime(now.year, 7, 31),
        lines: const [
          CommerceLine(productId: 'p-cp001', name: 'Cà phê rang xay', unit: 'kg', quantity: 20, unitPrice: 120000, unitCost: 120000, lotNo: 'LOT-CP-01'),
          CommerceLine(productId: 'p-cc002', name: 'Bột cacao', unit: 'hộp', quantity: 10, unitPrice: 90000, unitCost: 90000, lotNo: 'LOT-CC-01'),
          CommerceLine(productId: 'p-st010', name: 'Sữa tươi', unit: 'hộp', quantity: 10, unitPrice: 18000, unitCost: 18000, lotNo: 'LOT-ST-01'),
        ],
        subtotal: 3480000,
        discount: 0,
        vat: 348000,
        shipping: 0,
        total: 3828000,
        paid: 0,
        state: CommerceOrderState.completed,
        note: 'Đã nhập kho nguyên liệu',
      ),
      CommerceOrder(
        id: 'pm-018',
        code: 'PM018',
        kind: 'purchase',
        partyName: 'Thực phẩm GreenFarm',
        createdAt: DateTime(now.year, 6, 16),
        dueDate: DateTime(now.year, 6, 30),
        lines: const [
          CommerceLine(productId: 'p-bm02', name: 'Bánh Tiramisu', unit: 'cái', quantity: 1500, unitPrice: 25000, unitCost: 25000, lotNo: 'LOT-BM-02'),
          CommerceLine(productId: 'p-bt018', name: 'Bánh cheesecake', unit: 'cái', quantity: 1000, unitPrice: 28000, unitCost: 28000, lotNo: 'LOT-BT-02'),
        ],
        subtotal: 65500000,
        discount: 0,
        vat: 1647000,
        shipping: 0,
        total: 67147000,
        paid: 67147000,
        state: CommerceOrderState.completed,
        note: 'Đã thanh toán đủ',
      ),
      CommerceOrder(
        id: 'pm-017',
        code: 'PM017',
        kind: 'purchase',
        partyName: 'NCC An Phát',
        createdAt: DateTime(now.year, 6, 8),
        dueDate: DateTime(now.year, 7, 8),
        lines: const [
          CommerceLine(productId: 'p-tm027', name: 'Máy xay lớn', unit: 'máy', quantity: 25, unitPrice: 511000, unitCost: 511000, lotNo: 'LOT-TM-01'),
        ],
        subtotal: 12775000,
        discount: 0,
        vat: 2423830,
        shipping: 0,
        total: 15198830,
        paid: 5198830,
        state: CommerceOrderState.pending,
        note: 'Đang chờ hàng giao đợt 2',
      ),
      CommerceOrder(
        id: 'pm-016',
        code: 'PM016',
        kind: 'purchase',
        partyName: 'Nông sản Sạch Việt',
        createdAt: DateTime(now.year, 5, 29),
        dueDate: DateTime(now.year, 6, 29),
        lines: const [
          CommerceLine(productId: 'p-td011', name: 'Trà đào túi lọc', unit: 'gói', quantity: 150, unitPrice: 35000, unitCost: 35000, lotNo: 'LOT-TD-01'),
        ],
        subtotal: 5250000,
        discount: 0,
        vat: 580000,
        shipping: 0,
        total: 5830000,
        paid: 0,
        state: CommerceOrderState.completed,
        note: 'Đã nhập kho trà',
      ),
      CommerceOrder(
        id: 'pm-015',
        code: 'PM015',
        kind: 'purchase',
        partyName: 'Sản xuất Bao Bì Tấn Việt',
        createdAt: DateTime(now.year, 5, 27),
        dueDate: DateTime(now.year, 6, 27),
        lines: const [
          CommerceLine(productId: 'p-hg005', name: 'Hộp giấy', unit: 'hộp', quantity: 340, unitPrice: 71050, unitCost: 71050, lotNo: 'LOT-HG-01'),
        ],
        subtotal: 24157000,
        discount: 7000,
        vat: 0,
        shipping: 0,
        total: 24150000,
        paid: 0,
        state: CommerceOrderState.completed,
        note: 'Nhập bao bì giấy đợt 1',
      ),
      CommerceOrder(
        id: 'pm-011',
        code: 'PM011',
        kind: 'purchase',
        partyName: 'Bao bì Việt Phú',
        createdAt: DateTime(now.year, 4, 19),
        dueDate: DateTime(now.year, 5, 19),
        lines: const [
          CommerceLine(productId: 'p-ln001', name: 'Ly nhựa', unit: 'ly', quantity: 74470, unitPrice: 1000, unitCost: 1000, lotNo: 'LOT-LN-01'),
        ],
        subtotal: 74470000,
        discount: 0,
        vat: 0,
        shipping: 0,
        total: 74470000,
        paid: 0,
        state: CommerceOrderState.completed,
        note: 'Hợp đồng ly số lượng lớn',
      ),

      // Báo giá (Quotes) khớp ảnh
      CommerceOrder(
        id: 'bg-008',
        code: 'BG008',
        kind: 'quote',
        partyName: 'Quán Trà Nhà Gió',
        createdAt: DateTime(now.year, 6, 28),
        dueDate: DateTime(now.year, 7, 15),
        lines: const [
          CommerceLine(productId: 'p-cp001', name: 'Cà phê rang xay', unit: 'kg', quantity: 5, unitPrice: 180000, unitCost: 125000),
          CommerceLine(productId: 'p-tc099', name: 'Trân châu', unit: 'kg', quantity: 3, unitPrice: 75000, unitCost: 40000),
        ],
        subtotal: 1125000,
        discount: 0,
        vat: 24500,
        shipping: 0,
        total: 1149500,
        paid: 0,
        state: CommerceOrderState.converted,
        note: 'Đã chốt và chuyển đơn',
      ),
      CommerceOrder(
        id: 'bg-007',
        code: 'BG007',
        kind: 'quote',
        partyName: 'Công ty Gia Phát',
        createdAt: DateTime(now.year, 6, 26),
        dueDate: DateTime(now.year, 7, 10),
        lines: const [
          CommerceLine(productId: 'p-tc099', name: 'Trân châu', unit: 'kg', quantity: 10, unitPrice: 75000, unitCost: 40000),
          CommerceLine(productId: 'p-kb003', name: 'Kem béo', unit: 'hộp', quantity: 10, unitPrice: 95000, unitCost: 65000),
        ],
        subtotal: 1700000,
        discount: 0,
        vat: 45000,
        shipping: 0,
        total: 1745000,
        paid: 0,
        state: CommerceOrderState.draft,
        note: 'Chờ sếp duyệt',
      ),
      CommerceOrder(
        id: 'bg-006',
        code: 'BG006',
        kind: 'quote',
        partyName: 'Siêu thị Mini Hòa Bình',
        createdAt: DateTime(now.year, 6, 23),
        dueDate: DateTime(now.year, 7, 5),
        lines: const [
          CommerceLine(productId: 'p-cp001', name: 'Cà phê rang xay', unit: 'kg', quantity: 19, unitPrice: 180000, unitCost: 125000),
        ],
        subtotal: 3420000,
        discount: 0,
        vat: 0,
        shipping: 0,
        total: 3420000,
        paid: 0,
        state: CommerceOrderState.draft,
        note: 'Gửi báo giá qua zalo',
      ),
      CommerceOrder(
        id: 'bg-005',
        code: 'BG005',
        kind: 'quote',
        partyName: 'Cafe Mây Trắng',
        createdAt: DateTime(now.year, 6, 20),
        dueDate: DateTime(now.year, 6, 30),
        lines: const [
          CommerceLine(productId: 'p-cc002', name: 'Bột cacao', unit: 'hộp', quantity: 6, unitPrice: 135000, unitCost: 90000),
        ],
        subtotal: 810000,
        discount: 0,
        vat: 80000,
        shipping: 0,
        total: 890000,
        paid: 0,
        state: CommerceOrderState.draft,
        note: 'Hết hạn phản hồi',
      ),
      CommerceOrder(
        id: 'bg-004',
        code: 'BG004',
        kind: 'quote',
        partyName: 'Cửa hàng An Nhiên',
        createdAt: DateTime(now.year, 6, 17),
        dueDate: DateTime(now.year, 6, 27),
        lines: const [
          CommerceLine(productId: 'p-st010', name: 'Sữa tươi', unit: 'hộp', quantity: 70, unitPrice: 28000, unitCost: 18000),
        ],
        subtotal: 1960000,
        discount: 0,
        vat: 190000,
        shipping: 0,
        total: 2150000,
        paid: 0,
        state: CommerceOrderState.converted,
        note: 'Đã chuyển thành HD024',
      ),
    ];

    final payments = <CommercePayment>[
      CommercePayment(orderCode: 'HD025', partyName: 'Quán Trà Nhà Gió', kind: 'Thu tiền', amount: 831600, date: DateTime(now.year, 7, 3), method: 'Chuyển khoản VietQR'),
      CommercePayment(orderCode: 'HD027', partyName: 'Thanh Tuyền', kind: 'Thu tiền', amount: 150000, date: DateTime(now.year, 7, 4), method: 'Tiền mặt'),
      CommercePayment(orderCode: 'HD022', partyName: 'Shop Mộc Nhiên', kind: 'Thu tiền', amount: 1573360, date: DateTime(now.year, 6, 17), method: 'Chuyển khoản'),
      CommercePayment(orderCode: 'HD020', partyName: 'Khách vãng lai', kind: 'Thu tiền', amount: 2280000, date: DateTime(now.year, 6, 11), method: 'Tiền mặt'),
      CommercePayment(orderCode: 'PM018', partyName: 'Thực phẩm GreenFarm', kind: 'Trả tiền', amount: 67147000, date: DateTime(now.year, 6, 16), method: 'Ủy nhiệm chi'),
      CommercePayment(orderCode: 'PM017', partyName: 'NCC An Phát', kind: 'Trả tiền', amount: 5198830, date: DateTime(now.year, 6, 8), method: 'Chuyển khoản'),
    ];

    final store = CommerceMemoryStore._(
      products: products,
      customers: customers,
      suppliers: suppliers,
      orders: orders,
      payments: payments,
    );

    // Initial stocktake history matching photo 4
    store._stocktakeHistory.addAll([
      CommerceStocktake(
        id: 'KK07',
        counts: {'p-cp001': 290, 'p-td011': 80, 'p-st010': 179, 'p-cc002': 84, 'p-sy001': 0, 'p-ln001': 600},
        bookCounts: {'p-cp001': 304, 'p-td011': 80, 'p-st010': 179, 'p-cc002': 84, 'p-sy001': 0, 'p-ln001': 600},
        createdAt: DateTime(now.year, 7, 4),
        status: 'Hoàn tất',
        inspector: 'Hệ thống',
        note: 'Kiểm kê định kỳ tháng 7',
      ),
      CommerceStocktake(
        id: 'KK06',
        counts: {'p-bm02': 17, 'p-bt018': 3},
        bookCounts: {'p-bm02': 15, 'p-bt018': 3},
        createdAt: DateTime(now.year, 6, 17),
        status: 'Hoàn tất',
        inspector: 'Hệ thống',
        note: 'Kiểm kê thực phẩm',
      ),
      CommerceStocktake(
        id: 'KK05',
        counts: {'p-tc099': 220},
        bookCounts: {'p-tc099': 223},
        createdAt: DateTime(now.year, 6, 2),
        status: 'Hoàn tất',
        inspector: 'Hệ thống',
        note: 'Hao hụt tự nhiên',
      ),
      CommerceStocktake(
        id: 'KK04',
        counts: {'p-hg005': 181},
        bookCounts: {'p-hg005': 181},
        createdAt: DateTime(now.year, 5, 18),
        status: 'Hoàn tất',
        inspector: 'Hệ thống',
        note: 'Khớp 100%',
      ),
      CommerceStocktake(
        id: 'KK03',
        counts: {'p-tm027': 61},
        bookCounts: {'p-tm027': 59},
        createdAt: DateTime(now.year, 5, 3),
        status: 'Hoàn tất',
        inspector: 'Hệ thống',
        note: 'Tìm thấy 2 máy kiểm thử',
      ),
      CommerceStocktake(
        id: 'KK02',
        counts: {'p-st010': 174},
        bookCounts: {'p-st010': 179},
        createdAt: DateTime(now.year, 4, 18),
        status: 'Hoàn tất',
        inspector: 'Hệ thống',
        note: 'Hỏng vỏ hộp sữa',
      ),
      CommerceStocktake(
        id: 'KK01',
        counts: {'p-mp015': 3},
        bookCounts: {'p-mp015': 2},
        createdAt: DateTime(now.year, 4, 3),
        status: 'Hoàn tất',
        inspector: 'Hệ thống',
        note: 'Kiểm kê ban đầu',
      ),
    ]);

    return store;
  }

  final List<CommerceProduct> _products;
  final List<CommerceParty> _customers;
  final List<CommerceParty> _suppliers;
  final List<CommerceOrder> _orders;
  final List<CommercePayment> _payments;
  final Map<String, double> _reserved = {};
  final Map<String, List<_LotBalance>> _lots = {};
  final List<CommerceStocktake> _stocktakes = [];
  final List<CommerceStocktake> _stocktakeHistory = [];

  /// Replace the UI snapshot after a successful API reload. In live mode the
  /// server remains the source of truth; this is only an in-process cache.
  void replaceSnapshot({
    required List<CommerceProduct> products,
    required List<CommerceParty> customers,
    required List<CommerceParty> suppliers,
    required List<CommerceOrder> orders,
    required List<CommercePayment> payments,
  }) {
    _products
      ..clear()
      ..addAll(products);
    _customers
      ..clear()
      ..addAll(customers);
    _suppliers
      ..clear()
      ..addAll(suppliers);
    _orders
      ..clear()
      ..addAll(orders);
    _payments
      ..clear()
      ..addAll(payments);
    _reserved.clear();
    _lots.clear();
    _stocktakes.clear();
    _stocktakeHistory.clear();
    notifyListeners();
  }

  List<CommerceProduct> get products => List.unmodifiable(_products);
  List<CommerceParty> get customers => List.unmodifiable(_customers);
  List<CommerceParty> get suppliers => List.unmodifiable(_suppliers);
  List<CommerceOrder> get orders => List.unmodifiable(_orders);
  List<CommercePayment> get payments => List.unmodifiable(_payments);
  List<CommerceStocktake> get pendingStocktakes =>
      List.unmodifiable(_stocktakes);
  List<CommerceStocktake> get stocktakeHistory =>
      List.unmodifiable(_stocktakeHistory);
  List<CommerceOrder> get pendingOrders => _orders
      .where((order) => order.state == CommerceOrderState.pending)
      .toList(growable: false);
  List<CommerceOrder> get confirmedSales => sales
      .where((order) => order.state == CommerceOrderState.completed)
      .toList(growable: false);
  List<CommerceOrder> get sales =>
      _orders.where((o) => o.kind == 'sale').toList(growable: false);
  List<CommerceOrder> get quotes =>
      _orders.where((o) => o.kind == 'quote').toList(growable: false);
  List<CommerceOrder> get purchases =>
      _orders.where((o) => o.kind == 'purchase').toList(growable: false);
  List<CommerceOrder> get receivables => sales
      .where(
          (o) => o.state == CommerceOrderState.completed && o.outstanding > 0)
      .toList(growable: false);
  List<CommerceOrder> get payables => purchases
      .where(
          (o) => o.state == CommerceOrderState.completed && o.outstanding > 0)
      .toList(growable: false);
  int get revenueToday => sales
      .where((o) =>
          o.state == CommerceOrderState.completed &&
          sameDay(o.createdAt, DateTime.now()))
      .fold(0, (sum, o) => sum + o.total);
  int get profitToday => sales
      .where((o) =>
          o.state == CommerceOrderState.completed &&
          sameDay(o.createdAt, DateTime.now()))
      .fold(
          0,
          (sum, o) =>
              sum +
              o.subtotal -
              o.discount -
              o.lines.fold(0, (cost, line) => cost + line.costAmount));
  int get receivableTotal => receivables
      .where((o) => o.state == CommerceOrderState.completed)
      .fold(0, (sum, o) => sum + o.outstanding);
  int get payableTotal => payables.fold(0, (sum, o) => sum + o.outstanding);
  int get lowStockCount => _products.where((p) => p.stock <= p.minimum).length;
  double get inventoryValue =>
      _products.fold<double>(0, (sum, p) => sum + p.stock * p.cost);

  static bool sameDay(DateTime a, DateTime b) =>
      a.year == b.year && a.month == b.month && a.day == b.day;

  CommerceStocktake recordDirectStocktake(Map<String, double> actualCounts,
      {String note = '', String inspector = 'Hệ thống'}) {
    for (final entry in actualCounts.entries) {
      if (!_products.any((product) => product.id == entry.key)) {
        throw StateError('Không tìm thấy sản phẩm cần kiểm kê.');
      }
      if (!entry.value.isFinite || entry.value < 0) {
        throw StateError('Tồn thực tế phải là số không âm.');
      }
    }
    final bookCounts = {
      for (final id in actualCounts.keys) id: product(id).stock,
    };
    final serial = (_stocktakeHistory.length + 1).toString().padLeft(2, '0');
    final stocktake = CommerceStocktake(
      id: 'KK$serial',
      counts: Map.unmodifiable(actualCounts),
      bookCounts: Map.unmodifiable(bookCounts),
      createdAt: DateTime.now(),
      status: 'Hoàn tất',
      inspector: inspector,
      note: note,
    );
    for (final entry in actualCounts.entries) {
      final pIndex = _products.indexWhere((p) => p.id == entry.key);
      if (pIndex >= 0) {
        _products[pIndex] = _products[pIndex].copyWith(stock: entry.value);
      }
    }
    _stocktakeHistory.insert(0, stocktake);
    notifyListeners();
    return stocktake;
  }

  CommerceStocktake submitStocktake(Map<String, double> countedQuantities) {
    for (final entry in countedQuantities.entries) {
      if (!_products.any((product) => product.id == entry.key)) {
        throw StateError('Không tìm thấy sản phẩm cần kiểm kê.');
      }
      if (!entry.value.isFinite || entry.value < 0) {
        throw StateError('Tồn thực tế phải là số không âm.');
      }
    }
    final stocktake = CommerceStocktake(
      id: 'ST-${DateTime.now().microsecondsSinceEpoch}',
      counts: Map.unmodifiable(countedQuantities),
      bookCounts: Map.unmodifiable({
        for (final id in countedQuantities.keys) id: product(id).stock,
      }),
      createdAt: DateTime.now(),
    );
    _stocktakes.insert(0, stocktake);
    _stocktakeHistory.insert(0, stocktake);
    notifyListeners();
    return stocktake;
  }

  void approveStocktake(String id) {
    final index = _stocktakes.indexWhere((stocktake) => stocktake.id == id);
    if (index < 0) throw StateError('Không tìm thấy phiếu kiểm kê.');
    final counts = _stocktakes[index].counts;
    for (final entry in counts.entries) {
      if (entry.value < (_reserved[entry.key] ?? 0)) {
        throw StateError(
            'Tồn kiểm kê thấp hơn số lượng đang giữ cho đơn chờ duyệt.');
      }
    }
    _stocktakes.removeAt(index);
    for (final entry in counts.entries) {
      final productIndex = _products.indexWhere((p) => p.id == entry.key);
      _products[productIndex] =
          _products[productIndex].copyWith(stock: entry.value);
    }
    final historyIndex =
        _stocktakeHistory.indexWhere((stocktake) => stocktake.id == id);
    _stocktakeHistory[historyIndex] =
        _stocktakeHistory[historyIndex].copyWithStatus('Đã duyệt');
    notifyListeners();
  }

  void rejectStocktake(String id) {
    final index = _stocktakes.indexWhere((stocktake) => stocktake.id == id);
    if (index < 0) throw StateError('Không tìm thấy phiếu kiểm kê.');
    _stocktakes.removeAt(index);
    final historyIndex =
        _stocktakeHistory.indexWhere((stocktake) => stocktake.id == id);
    _stocktakeHistory[historyIndex] =
        _stocktakeHistory[historyIndex].copyWithStatus('Từ chối');
    notifyListeners();
  }

  CommerceProduct product(String id) => _products.firstWhere((p) => p.id == id);

  CommerceParty addParty({
    required String name,
    required String kind,
    String phone = '',
  }) {
    final cleanName = name.trim();
    if (cleanName.isEmpty || (kind != 'customer' && kind != 'supplier')) {
      throw StateError('Vui lòng nhập tên khách hàng hoặc nhà cung cấp.');
    }
    final rows = kind == 'customer' ? _customers : _suppliers;
    if (rows
        .any((party) => party.name.toLowerCase() == cleanName.toLowerCase())) {
      throw StateError('Đối tác này đã có trong danh sách.');
    }
    final party = CommerceParty(
      id: '${kind == 'customer' ? 'c' : 's'}-${DateTime.now().microsecondsSinceEpoch}',
      name: cleanName,
      kind: kind,
      phone: phone.trim(),
    );
    rows.add(party);
    notifyListeners();
    return party;
  }

  CommerceProduct addProduct({
    required String sku,
    required String name,
    required String category,
    required String unit,
    required int cost,
    required int price,
    required double minimum,
  }) {
    final cleanSku = sku.trim();
    final cleanName = name.trim();
    if (cleanSku.isEmpty || cleanName.isEmpty || unit.trim().isEmpty) {
      throw StateError('Vui lòng nhập mã, tên và đơn vị sản phẩm.');
    }
    if (cost < 0 || price < 0 || minimum < 0 || !minimum.isFinite) {
      throw StateError('Giá và tồn tối thiểu không được âm.');
    }
    if (_products.any((product) =>
        product.sku.toLowerCase() == cleanSku.toLowerCase() ||
        product.name.toLowerCase() == cleanName.toLowerCase())) {
      throw StateError('Mã hoặc tên sản phẩm đã tồn tại.');
    }
    final product = CommerceProduct(
      id: 'p-${DateTime.now().microsecondsSinceEpoch}',
      sku: cleanSku,
      name: cleanName,
      category: category.trim().isEmpty ? 'Khác' : category.trim(),
      unit: unit.trim(),
      stock: 0,
      minimum: minimum,
      cost: cost,
      price: price,
    );
    _products.add(product);
    notifyListeners();
    return product;
  }

  CommerceOrder createOrder({
    required String kind,
    required String partyName,
    required List<CommerceLine> lines,
    int discount = 0,
    double vatPercent = 0,
    int shipping = 0,
    int paid = 0,
    String note = '',
    DateTime? dueDate,
  }) {
    if (kind != 'sale' && kind != 'purchase' && kind != 'quote') {
      throw ArgumentError.value(kind, 'kind', 'Loại chứng từ không hợp lệ');
    }
    if (partyName.trim().isEmpty) {
      throw StateError('Vui lòng chọn khách hàng/nhà cung cấp.');
    }
    if (lines.isEmpty) {
      throw StateError('Phiếu cần có ít nhất một sản phẩm.');
    }
    if (lines.any((line) =>
        !line.quantity.isFinite ||
        line.quantity <= 0 ||
        line.unitPrice < 0 ||
        line.unitCost < 0)) {
      throw StateError('Số lượng phải lớn hơn 0 và đơn giá không được âm.');
    }
    if (dueDate != null) {
      final today = DateTime.now();
      if (DateTime(dueDate.year, dueDate.month, dueDate.day)
          .isBefore(DateTime(today.year, today.month, today.day))) {
        throw StateError('Hạn thanh toán không được trước ngày chứng từ.');
      }
    }
    if (kind == 'purchase') {
      final today = DateTime.now();
      for (final line in lines) {
        if (line.lotNo.trim().isEmpty || line.expiryDate == null) {
          throw StateError(
              'Phiếu mua cần số lô và hạn dùng cho từng sản phẩm.');
        }
        final expiry = line.expiryDate!;
        if (DateTime(expiry.year, expiry.month, expiry.day)
            .isBefore(DateTime(today.year, today.month, today.day))) {
          throw StateError('Không thể nhập lô hàng đã hết hạn.');
        }
      }
    }
    if (discount < 0 || shipping < 0 || vatPercent < 0 || vatPercent > 100) {
      throw StateError('Chiết khấu, VAT hoặc phí vận chuyển không hợp lệ.');
    }

    final normalized = lines
        .map((line) => line.copyWithProduct(product(line.productId)))
        .toList(growable: false);
    final subtotal = normalized.fold<int>(0, (sum, line) => sum + line.amount);
    if (discount > subtotal) {
      throw StateError('Chiết khấu không được lớn hơn tiền hàng.');
    }
    final taxable = subtotal - discount;
    final vat = (taxable * vatPercent / 100).round();
    final total = taxable + vat + shipping;
    if (paid != 0) {
      throw StateError('Hãy ghi nhận thanh toán sau khi phiếu được duyệt.');
    }

    // Validate the complete sale before changing any stock. Aggregation also
    // prevents duplicate lines from independently passing the stock check.
    final quantities = <String, double>{};
    if (kind == 'sale') {
      for (final line in normalized) {
        quantities.update(line.productId, (value) => value + line.quantity,
            ifAbsent: () => line.quantity);
      }
      for (final entry in quantities.entries) {
        final available =
            product(entry.key).stock - (_reserved[entry.key] ?? 0);
        if (available < entry.value) {
          throw StateError(
              'Không đủ tồn kho ${product(entry.key).name}. Còn $available ${product(entry.key).unit}.');
        }
        final lots = _lots[entry.key];
        if (lots != null && lots.isNotEmpty) {
          final today = DateTime.now();
          final unexpired = lots
              .where((lot) =>
                  lot.quantity > 0 &&
                  (lot.expiryDate == null ||
                      !DateTime(lot.expiryDate!.year, lot.expiryDate!.month,
                              lot.expiryDate!.day)
                          .isBefore(
                              DateTime(today.year, today.month, today.day))))
              .fold<double>(0, (sum, lot) => sum + lot.quantity);
          if (unexpired - (_reserved[entry.key] ?? 0) < entry.value) {
            throw StateError(
                'Tồn khả dụng của ${product(entry.key).name} không đủ sau khi loại trừ lô hết hạn.');
          }
        }
      }
    }

    final now = DateTime.now();
    final prefix = kind == 'sale'
        ? 'HD'
        : kind == 'quote'
            ? 'BG'
            : 'NM';
    final serial = (_orders.where((order) => order.kind == kind).length + 1)
        .toString()
        .padLeft(4, '0');
    final order = CommerceOrder(
      id: '$prefix-$serial-${now.microsecondsSinceEpoch}',
      code: '$prefix$serial',
      kind: kind,
      partyName: partyName.trim(),
      createdAt: now,
      lines: normalized,
      subtotal: subtotal,
      discount: discount,
      vat: vat,
      shipping: shipping,
      total: total,
      paid: paid,
      state: kind == 'quote'
          ? CommerceOrderState.draft
          : CommerceOrderState.pending,
      note: note.trim(),
      dueDate: dueDate,
    );

    if (kind == 'sale') {
      for (final entry in quantities.entries) {
        _reserved.update(entry.key, (value) => value + entry.value,
            ifAbsent: () => entry.value);
      }
    }
    _orders.insert(0, order);
    notifyListeners();
    return order;
  }

  CommerceOrder recordPayment(String orderId, int amount,
      {String method = 'cash', String reference = ''}) {
    if (amount <= 0) {
      throw StateError('Số tiền thanh toán phải lớn hơn 0.');
    }
    final index = _orders.indexWhere((o) => o.id == orderId);
    if (index < 0) throw StateError('Không tìm thấy chứng từ.');
    final order = _orders[index];
    if (order.kind == 'quote' || order.state != CommerceOrderState.completed) {
      throw StateError('Chỉ chứng từ đã xác nhận mới nhận hoặc trả tiền.');
    }
    if (amount > order.outstanding) {
      throw StateError('Số tiền vượt quá phần còn phải thanh toán.');
    }
    final updated = order.copyWith(paid: order.paid + amount);
    _orders[index] = updated;
    _payments.insert(
        0,
        CommercePayment(
          orderCode: order.code,
          partyName: order.partyName,
          kind: order.kind == 'sale' ? 'Thu tiền' : 'Trả tiền',
          amount: amount,
          date: DateTime.now(),
          method: method,
          reference: reference.trim(),
        ));
    notifyListeners();
    return updated;
  }

  CommerceOrder approveOrder(String orderId) {
    final index = _orders.indexWhere((order) => order.id == orderId);
    if (index < 0) throw StateError('Không tìm thấy chứng từ.');
    final order = _orders[index];
    if (order.state != CommerceOrderState.pending) {
      throw StateError('Chỉ phiếu chờ duyệt mới được xác nhận.');
    }
    if (order.kind == 'sale') {
      final quantities = <String, double>{};
      for (final line in order.lines) {
        quantities.update(line.productId, (value) => value + line.quantity,
            ifAbsent: () => line.quantity);
      }
      for (final entry in quantities.entries) {
        if (product(entry.key).stock < entry.value) {
          throw StateError('Tồn kho đã thay đổi, không thể duyệt đơn này.');
        }
      }
      for (final entry in quantities.entries) {
        _consumeAvailableLots(entry.key, entry.value);
        final itemIndex = _products.indexWhere((p) => p.id == entry.key);
        _products[itemIndex] = _products[itemIndex]
            .copyWith(stock: _products[itemIndex].stock - entry.value);
        _reserved.update(
          entry.key,
          (value) => (value - entry.value).clamp(0, double.infinity).toDouble(),
        );
      }
    } else if (order.kind == 'purchase') {
      for (final line in order.lines) {
        final lots = _lots.putIfAbsent(line.productId, () => []);
        final existingLot = lots.cast<_LotBalance?>().firstWhere(
              (lot) =>
                  lot?.lotNo == line.lotNo &&
                  lot?.expiryDate == line.expiryDate,
              orElse: () => null,
            );
        if (existingLot == null) {
          lots.add(_LotBalance(
            lotNo: line.lotNo,
            expiryDate: line.expiryDate,
            quantity: line.quantity,
          ));
        } else {
          existingLot.quantity += line.quantity;
        }
        final itemIndex = _products.indexWhere((p) => p.id == line.productId);
        final current = _products[itemIndex];
        final nextQuantity = current.stock + line.quantity;
        final weightedCost =
            ((current.stock * current.cost + line.quantity * line.unitPrice) /
                    nextQuantity)
                .round();
        _products[itemIndex] =
            current.copyWith(stock: nextQuantity, cost: weightedCost);
      }
    }
    final updated = order.copyWith(state: CommerceOrderState.completed);
    _orders[index] = updated;
    notifyListeners();
    return updated;
  }

  void rejectOrder(String orderId) {
    final index = _orders.indexWhere((order) => order.id == orderId);
    if (index < 0) throw StateError('Không tìm thấy chứng từ.');
    final order = _orders[index];
    if (order.state != CommerceOrderState.pending) {
      throw StateError('Chỉ phiếu chờ duyệt mới được từ chối.');
    }
    if (order.kind == 'sale') {
      for (final line in order.lines) {
        _reserved.update(
          line.productId,
          (value) =>
              (value - line.quantity).clamp(0, double.infinity).toDouble(),
        );
      }
    }
    _orders[index] = order.copyWith(state: CommerceOrderState.cancelled);
    notifyListeners();
  }

  CommerceOrder convertQuote(String quoteId) {
    final quoteIndex = _orders.indexWhere((order) => order.id == quoteId);
    if (quoteIndex < 0) throw StateError('Không tìm thấy báo giá.');
    final quote = _orders[quoteIndex];
    if (quote.kind != 'quote' || quote.state != CommerceOrderState.draft) {
      throw StateError('Chỉ báo giá đang chờ mới được chuyển thành đơn bán.');
    }
    final taxable = quote.subtotal - quote.discount;
    final vatPercent = taxable == 0 ? 0.0 : quote.vat * 100 / taxable;
    final sale = createOrder(
      kind: 'sale',
      partyName: quote.partyName,
      lines: quote.lines,
      discount: quote.discount,
      vatPercent: vatPercent,
      shipping: quote.shipping,
      note: quote.note,
    );
    final updatedQuoteIndex =
        _orders.indexWhere((order) => order.id == quoteId);
    _orders[updatedQuoteIndex] =
        quote.copyWith(state: CommerceOrderState.converted);
    notifyListeners();
    return sale;
  }

  void _consumeAvailableLots(String productId, double quantity) {
    final lots = _lots[productId];
    if (lots == null || lots.isEmpty) return;
    final today = DateTime.now();
    final available = lots
        .where((lot) =>
            lot.quantity > 0 &&
            (lot.expiryDate == null ||
                !DateTime(lot.expiryDate!.year, lot.expiryDate!.month,
                        lot.expiryDate!.day)
                    .isBefore(DateTime(today.year, today.month, today.day))))
        .toList()
      ..sort((a, b) => (a.expiryDate ?? DateTime(9999))
          .compareTo(b.expiryDate ?? DateTime(9999)));
    if (available.fold<double>(0, (sum, lot) => sum + lot.quantity) <
        quantity) {
      throw StateError('Không đủ tồn theo lô còn hạn sử dụng.');
    }
    var remaining = quantity;
    for (final lot in available) {
      final taken = lot.quantity < remaining ? lot.quantity : remaining;
      lot.quantity -= taken;
      remaining -= taken;
      if (remaining <= 0) break;
    }
  }
}

extension on CommerceLine {
  CommerceLine copyWithProduct(CommerceProduct product) => CommerceLine(
        productId: product.id,
        name: product.name,
        unit: product.unit,
        quantity: quantity,
        unitPrice: unitPrice,
        unitCost: product.cost,
        lotNo: lotNo,
        expiryDate: expiryDate,
      );
}
