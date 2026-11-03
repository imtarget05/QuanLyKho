import 'dart:convert';
import 'dart:math';

import 'package:http/http.dart' as http;

import 'commerce_memory_store.dart';

typedef SessionRevokedCallback = void Function(String message);

/// Authenticated commerce client. It holds only a display snapshot; every
/// business write is sent to the API and the snapshot is reloaded afterward.
class CommerceApi {
  CommerceApi({
    required this.baseUrl,
    required this.tokenProvider,
    required this.userId,
    this.onSessionRevoked,
    http.Client? client,
  }) : _client = client ?? http.Client();

  final String baseUrl;
  final Future<String?> Function() tokenProvider;
  final String userId;
  final http.Client _client;
  String? locationId;
  List<Map<String, dynamic>> locations = const [];
  SessionRevokedCallback? onSessionRevoked;

  static String newIdempotencyKey() =>
      'commerce_${DateTime.now().microsecondsSinceEpoch}_${Random.secure().nextInt(0x7fffffff)}';

  Uri _uri(String path) => Uri.parse('$baseUrl$path');

  Future<Map<String, String>> _headers(
      {bool write = false, String? idempotencyKey}) async {
    final token = await tokenProvider();
    if (token == null || token.isEmpty) {
      throw StateError('Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.');
    }
    return {
      'Authorization': 'Bearer $token',
      'Content-Type': 'application/json',
      if (write) 'Idempotency-Key': idempotencyKey ?? newIdempotencyKey(),
    };
  }

  Future<dynamic> _get(String path) async {
    final response = await _client.get(_uri(path), headers: await _headers());
    return _decode(response);
  }

  Future<dynamic> _send(String method, String path, Map<String, dynamic> body,
      {String? etag, String? idempotencyKey}) async {
    final headers = await _headers(write: true, idempotencyKey: idempotencyKey);
    if (etag != null) headers['If-Match'] = etag;
    final request = http.Request(method, _uri(path))
      ..headers.addAll(headers)
      ..body = jsonEncode(body);
    final response =
        await http.Response.fromStream(await _client.send(request));
    return _decode(response);
  }

  dynamic _decode(http.Response response) {
    dynamic data;
    try {
      data = jsonDecode(response.body);
    } catch (_) {
      data = null;
    }
    if (response.statusCode == 401) {
      final message = data is Map
          ? (data['detail'] ??
              data['error']?['message'] ??
              'Phiên đăng nhập đã bị thu hồi hoặc quyền tài khoản đã thay đổi. Vui lòng đăng nhập lại.')
          : 'Phiên đăng nhập đã bị thu hồi hoặc quyền tài khoản đã thay đổi. Vui lòng đăng nhập lại.';
      final msgStr = message.toString();
      if (msgStr.contains('Phiên đăng nhập đã bị thu hồi') ||
          msgStr.contains('quyền tài khoản đã thay đổi') ||
          msgStr.toLowerCase().contains('role') ||
          msgStr.toLowerCase().contains('unauthorized')) {
        onSessionRevoked?.call(msgStr);
      }
      throw StateError(msgStr);
    }
    if (response.statusCode < 200 || response.statusCode >= 300) {
      final message = data is Map
          ? (data['detail'] ??
              data['error']?['message'] ??
              'Lỗi máy chủ ${response.statusCode}')
          : 'Lỗi máy chủ ${response.statusCode}';
      throw StateError(message.toString());
    }
    return data;
  }

  Future<void> reload(CommerceMemoryStore store) async {
    final initial = await Future.wait([
      _get('/inventory/items'),
      _get('/inventory/locations'),
      _get('/commerce/parties'),
    ]);
    final items = _list(initial[0], 'items');
    locations = _list(initial[1], 'locations');
    if (locationId == null && locations.isNotEmpty) {
      locationId = locations.first['id']?.toString();
    }
    final balances = <Map<String, dynamic>>[];
    String? cursor;
    int balancePages = 0;
    do {
      final page = await _get(
          '/inventory/balances?limit=100${cursor == null ? '' : '&cursor=${Uri.encodeQueryComponent(cursor)}'}');
      balances.addAll(_list(page, 'balances'));
      cursor = page is Map ? page['next_cursor']?.toString() : null;
      balancePages++;
    } while (cursor != null && cursor.isNotEmpty && balancePages < 25);
    final parties = initial[2] as Map? ?? const {};
    final customerRows = _list(parties, 'customers');
    final supplierRows = _list(parties, 'suppliers');
    final customers = customerRows
        .map((p) => CommerceParty(
              id: '${p['id']}',
              name: '${p['name']}',
              kind: 'customer',
              phone: '${p['phone'] ?? ''}',
            ))
        .toList();
    final suppliers = supplierRows
        .map((p) => CommerceParty(
              id: '${p['id']}',
              name: '${p['name']}',
              kind: 'supplier',
              phone: '${p['phone'] ?? ''}',
            ))
        .toList();
    final balanceByItem = <String, double>{};
    for (final row in balances) {
      if (locationId == null || row['location_id']?.toString() == locationId) {
        balanceByItem[row['item_id'].toString()] = _num(row['quantity']);
      }
    }
    final products = items
        .map((item) => CommerceProduct(
              id: '${item['id']}',
              sku: '${item['sku'] ?? ''}',
              name: '${item['name'] ?? ''}',
              category: '${item['category'] ?? 'Khác'}',
              unit: '${item['unit'] ?? ''}',
              stock: balanceByItem['${item['id']}'] ?? 0,
              minimum: _num(item['min_stock'] ?? item['minStock']),
              cost: _num(item['cost_price'] ?? item['costPrice']).round(),
              price:
                  _num(item['selling_price'] ?? item['sellingPrice']).round(),
            ))
        .toList();
    final partyById = {
      for (final p in [...customers, ...suppliers]) p.id: p.name,
    };
    final documents = <Map<String, dynamic>>[];
    int? offset = 0;
    int docPages = 0;
    while (offset != null && docPages < 25) {
      final page = await _get(
          '/commerce/documents?limit=200&offset=$offset${locationId == null ? '' : '&location_id=${Uri.encodeQueryComponent(locationId!)}'}');
      documents.addAll(_list(page, 'documents'));
      offset = page is Map ? page['next_offset'] as int? : null;
      docPages++;
    }
    final orders = <CommerceOrder>[];
    final payments = <CommercePayment>[];
    for (final row in documents) {
      final kind = '${row['document_type']}';
      final partyId =
          row['customer_id']?.toString() ?? row['supplier_id']?.toString();
      final lines = _list(row, 'lines')
          .map((line) => CommerceLine(
                productId: '${line['item_id']}',
                name: '${line['name'] ?? line['sku'] ?? ''}',
                unit: '${line['unit'] ?? ''}',
                quantity: _num(line['quantity']),
                unitPrice: _num(line['unit_price']).round(),
                unitCost: _num(line['unit_cost']).round(),
                lotNo: '${line['lot_no'] ?? ''}',
                expiryDate: line['expiry_date'] == null
                    ? null
                    : DateTime.tryParse('${line['expiry_date']}'),
              ))
          .toList();
      final state = switch ('${row['status']}') {
        'confirmed' => CommerceOrderState.completed,
        'converted' => CommerceOrderState.converted,
        'draft' => CommerceOrderState.draft,
        'cancelled' => CommerceOrderState.cancelled,
        _ => CommerceOrderState.pending,
      };
      final order = CommerceOrder(
        id: '${row['id']}',
        code: '${row['code']}',
        kind: kind,
        partyName: partyById[partyId] ?? 'Đối tác đã ngừng hoạt động',
        createdAt:
            DateTime.tryParse('${row['document_date']}') ?? DateTime.now(),
        lines: lines,
        subtotal: _num(row['subtotal']).round(),
        discount: _num(row['discount']).round(),
        vat: _num(row['vat']).round(),
        shipping: _num(row['shipping']).round(),
        total: _num(row['total']).round(),
        paid: _num(row['paid']).round(),
        state: state,
        note: '${row['note'] ?? ''}',
        dueDate: row['due_date'] == null
            ? null
            : DateTime.tryParse('${row['due_date']}'),
      );
      orders.add(order);
      for (final payment in _list(row, 'payments')) {
        payments.add(CommercePayment(
          orderCode: order.code,
          partyName: order.partyName,
          kind: kind == 'sale' ? 'Thu tiền' : 'Trả tiền',
          amount: _num(payment['amount']).round(),
          date: DateTime.tryParse('${payment['payment_date']}') ??
              order.createdAt,
          method: '${payment['method'] ?? 'cash'}',
          reference: '${payment['reference'] ?? ''}',
        ));
      }
    }
    store.replaceSnapshot(
      products: products,
      customers: customers,
      suppliers: suppliers,
      orders: orders,
      payments: payments,
    );
  }

  Future<void> createDocument({
    required String kind,
    required CommerceParty party,
    required List<CommerceLine> lines,
    required int discount,
    required double vatPercent,
    required int shipping,
    required String note,
    DateTime? dueDate,
    String? idempotencyKey,
  }) async {
    final isPurchase = kind == 'purchase';
    if (kind != 'quote' && (locationId == null || locationId!.isEmpty)) {
      throw StateError(
          'Tài khoản chưa được phân kho. Vui lòng liên hệ quản trị viên.');
    }
    await _send(
        'POST',
        '/commerce/documents',
        {
          'document_type': kind,
          if (kind != 'quote') 'location_id': locationId,
          if (isPurchase) 'supplier_id': party.id else 'customer_id': party.id,
          'discount': discount,
          'vat_percent': vatPercent,
          'shipping': shipping,
          if (dueDate != null)
            'due_date': dueDate.toIso8601String().substring(0, 10),
          'note': note,
          'lines': [
            for (final line in lines)
              {
                'item_id': line.productId,
                'quantity': line.quantity,
                'unit_price': line.unitPrice,
                if (isPurchase) 'lot_no': line.lotNo,
                if (isPurchase)
                  'expiry_date':
                      line.expiryDate?.toIso8601String().substring(0, 10),
              }
          ],
        },
        idempotencyKey: idempotencyKey);
  }

  Future<void> convertQuote(String documentId) async {
    if (locationId == null) throw StateError('Chưa có kho được phân quyền.');
    await _send(
        'POST',
        '/commerce/documents/$documentId/convert',
        {
          'location_id': locationId,
        },
        idempotencyKey: 'commerce_quote_convert_${documentId}_$locationId');
  }

  Future<void> recordPayment(String documentId, int amount,
      {String method = 'cash',
      String reference = '',
      String? idempotencyKey}) async {
    await _send(
        'POST',
        '/commerce/documents/$documentId/payments',
        {
          'amount': amount,
          'method': method,
          'reference': reference.trim(),
          'payment_date': DateTime.now().toIso8601String().substring(0, 10),
        },
        idempotencyKey: idempotencyKey);
  }

  Future<CommerceParty> createParty({
    required String kind,
    required String name,
    String phone = '',
    String? idempotencyKey,
  }) async {
    final code =
        '${kind == 'customer' ? 'KH' : 'NCC'}-${DateTime.now().microsecondsSinceEpoch}';
    final path =
        kind == 'customer' ? '/commerce/customers' : '/commerce/suppliers';
    final result = await _send(
        'POST',
        path,
        {
          'code': code,
          'name': name.trim(),
          'phone': phone.trim(),
        },
        idempotencyKey: idempotencyKey) as Map;
    return CommerceParty(
      id: '${result['id']}',
      name: '${result['name'] ?? name.trim()}',
      kind: kind,
      phone: '${result['phone'] ?? phone.trim()}',
    );
  }

  Future<void> createProduct({
    required String sku,
    required String name,
    required String unit,
    required String category,
    required double cost,
    required double price,
    required double minimum,
    String? idempotencyKey,
  }) async {
    await _send(
        'POST',
        '/inventory/items',
        {
          'sku': sku.trim().toUpperCase(),
          'name': name.trim(),
          'unit': unit.trim(),
          'category': category.trim(),
          'cost_price': cost,
          'selling_price': price,
          'min_stock': minimum,
        },
        idempotencyKey: idempotencyKey);
  }

  Future<void> createLocation(
      {required String code,
      required String name,
      String? idempotencyKey}) async {
    await _send(
        'POST',
        '/inventory/locations',
        {
          'code': code.trim().toUpperCase(),
          'name': name.trim(),
        },
        idempotencyKey: idempotencyKey);
  }

  Future<void> submitStocktake(Map<String, double> counts,
      {String? idempotencyKey}) async {
    if (locationId == null) throw StateError('Chưa có kho được phân quyền.');
    final operationKey = idempotencyKey ?? newIdempotencyKey();
    final openRows = _list(
      await _get('/inventory/stocktakes?status=open&location_id=$locationId'),
      'stocktakes',
    );
    final matchingOpen = openRows
        .where((row) =>
            row['maker_id']?.toString() == userId &&
            row['location_id']?.toString() == locationId)
        .toList();
    final Map<String, dynamic> stocktake;
    if (matchingOpen.isNotEmpty) {
      stocktake = matchingOpen.first;
    } else {
      stocktake = Map<String, dynamic>.from(
        await _send(
            'POST',
            '/inventory/stocktakes',
            {
              'location_id': locationId,
              'note': 'Kiểm kê kho',
            },
            idempotencyKey: '${operationKey}_create') as Map,
      );
    }
    final id = stocktake['id'].toString();
    final version = stocktake['version'].toString();
    await _send(
        'PUT',
        '/inventory/stocktakes/$id/lines',
        {
          'lines': [
            for (final row in counts.entries)
              {'item_id': row.key, 'counted_qty': row.value}
          ],
        },
        etag: version,
        idempotencyKey: '${operationKey}_lines');
    await _send('POST', '/inventory/stocktakes/$id/submit', {},
        idempotencyKey: '${operationKey}_submit');
  }

  Future<List<Map<String, dynamic>>> pendingApprovals() async {
    final results = await Future.wait([
      _get('/inventory/requests?status=submitted&limit=100'),
      _get('/inventory/stocktakes?status=submitted'),
    ]);
    return [
      ..._list(results[0], 'requests')
          .map((row) => {...row, '_type': 'request'}),
      ..._list(results[1], 'stocktakes')
          .map((row) => {...row, '_type': 'stocktake'}),
    ];
  }

  Future<List<Map<String, dynamic>>> stocktakeHistory() async {
    final rows = _list(
      await _get(
          '/inventory/stocktakes${locationId == null ? '' : '?location_id=$locationId'}'),
      'stocktakes',
    );
    final completed = rows
        .where((row) => row['status'] != 'open' && row['status'] != 'submitted')
        .toList(growable: false);
    return Future.wait(completed.map((row) async {
      final detail = await _get('/inventory/stocktakes/${row['id']}');
      return {...row, ...Map<String, dynamic>.from(detail as Map)};
    }));
  }

  Future<List<Map<String, dynamic>>> inventoryMovements() async {
    final rows = <Map<String, dynamic>>[];
    String? cursor;
    do {
      final query = <String, String>{'limit': '100'};
      if (locationId != null) query['location_id'] = locationId!;
      if (cursor != null) query['cursor'] = cursor;
      final uri = _uri('/inventory/movements').replace(queryParameters: query);
      final response = await _client.get(uri, headers: await _headers());
      final page = _decode(response);
      rows.addAll(_list(page, 'movements'));
      cursor = page is Map ? page['next_cursor']?.toString() : null;
    } while (cursor != null && cursor.isNotEmpty);
    return rows;
  }

  Future<void> approveInventoryRequest(Map<String, dynamic> row) async {
    final id = '${row['id']}';
    final path = row['_type'] == 'stocktake'
        ? '/inventory/stocktakes/$id/approve'
        : '/inventory/requests/$id/approve';
    await _send('POST', path, {});
  }

  Future<void> rejectInventoryRequest(
      Map<String, dynamic> row, String reason) async {
    final id = '${row['id']}';
    if (row['_type'] == 'stocktake') {
      await _send(
          'POST', '/inventory/stocktakes/$id/reject', {'reason': reason});
    } else {
      await _send('POST', '/inventory/requests/$id/reject', {'reason': reason});
    }
  }

  static List<Map<String, dynamic>> _list(dynamic value, String key) {
    final rows = value is Map ? value[key] : value;
    if (rows is! List) return const [];
    return rows
        .whereType<Map>()
        .map((m) => Map<String, dynamic>.from(m))
        .toList();
  }

  static double _num(dynamic value) =>
      double.tryParse(value?.toString() ?? '') ?? 0;

  void dispose() => _client.close();
}
