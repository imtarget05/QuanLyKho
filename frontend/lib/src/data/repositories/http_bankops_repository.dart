import 'dart:async';
import 'dart:convert';

import 'package:http/http.dart' as http;

import '../../features/auth/auth_service.dart';
import '../models/dtos.dart';
import 'bankops_repository.dart';

/// Repository HTTP thật, gọi backend FastAPI theo docs/06-api.md.
///
/// - `baseUrl` lấy từ `--dart-define=API_BASE_URL=...`, mặc định
///   `http://localhost:8000/api/v1` (chuẩn hoá qua [AuthService.normalizeApiBaseUrl]).
/// - Token Bearer lấy qua [tokenProvider] (do UI/AuthService cấp).
/// - Lỗi backend dạng envelope `{error:{code,message,request_id}}` được
///   chuyển thành [ApiException] giữ nguyên `requestId`.
class HttpBankOpsRepository implements BankOpsRepository {
  HttpBankOpsRepository({
    String? baseUrl,
    http.Client? client,
    Future<String?> Function()? tokenProvider,
  })  : _baseUrl = AuthService.normalizeApiBaseUrl(
          baseUrl ?? AuthService.defaultBaseUrl,
        ),
        _client = client ?? http.Client(),
        _tokenProvider = tokenProvider {
    _approvalStreamCtrl = StreamController<String>.broadcast(
      onListen: _startSse,
      onCancel: _stopSse,
    );
  }

  final String _baseUrl;
  final http.Client _client;
  final Future<String?> Function()? _tokenProvider;
  late final StreamController<String> _approvalStreamCtrl;
  bool _sseActive = false;
  bool _disposed = false;

  void _startSse() {
    if (_sseActive || _disposed) return;
    _sseActive = true;
    _runSseLoop();
  }

  void _stopSse() {
    _sseActive = false;
  }

  Future<void> _runSseLoop() async {
    while (_sseActive && !_disposed) {
      try {
        final token = await _tokenProvider?.call();
        if (token == null || token.isEmpty) {
          await Future.delayed(const Duration(seconds: 1));
          continue;
        }

        final uri = _uri('/approvals/stream', {'token': token});
        final request = http.Request('GET', uri);
        request.headers['Accept'] = 'text/event-stream';
        request.headers['Cache-Control'] = 'no-cache';

        final streamedResponse = await _client.send(request);
        if (streamedResponse.statusCode == 200) {
          await for (final line in streamedResponse.stream
              .transform(utf8.decoder)
              .transform(const LineSplitter())) {
            if (!_sseActive || _disposed) break;
            if (line.startsWith('data: ')) {
              final payload = line.substring(6).trim();
              if (payload.isNotEmpty && !_approvalStreamCtrl.isClosed) {
                _approvalStreamCtrl.add(payload);
              }
            }
          }
        }
      } catch (_) {
        // SSE network disconnect or error: wait before retry
      }
      if (!_sseActive || _disposed) break;
      await Future.delayed(const Duration(seconds: 3));
    }
  }

  String get baseUrl => _baseUrl;
  Future<String?> get accessToken =>
      _tokenProvider?.call() ?? Future.value(null);

  @override
  void dispose() {
    _disposed = true;
    _sseActive = false;
    _approvalStreamCtrl.close();
    _client.close();
  }

  @override
  Stream<String> get approvalNotifications => _approvalStreamCtrl.stream;

  Uri _uri(String path, [Map<String, String>? query]) =>
      Uri.parse('$_baseUrl$path').replace(
          queryParameters: query == null || query.isEmpty ? null : query);

  Future<Map<String, String>> _headers() async {
    final headers = <String, String>{'Content-Type': 'application/json'};
    final token = await _tokenProvider?.call();
    if (token != null && token.isNotEmpty) {
      headers['Authorization'] = 'Bearer $token';
    }
    return headers;
  }

  Map<String, String> _idem() => {
        'Idempotency-Key': 'fe_${DateTime.now().microsecondsSinceEpoch}',
      };

  Never _throwEnvelope(http.Response resp) {
    String code = 'HTTP_${resp.statusCode}';
    String message = 'Máy chủ trả lỗi ${resp.statusCode}.';
    String? requestId = resp.headers['x-request-id'];
    try {
      final decoded = json.decode(resp.body);
      if (decoded is Map) {
        final err = decoded['error'];
        if (err is Map) {
          if (err['code'] is String) code = err['code'] as String;
          if (err['message'] is String) message = err['message'] as String;
          if (err['request_id'] is String) {
            requestId = err['request_id'] as String;
          }
        } else if (decoded['detail'] is String) {
          message = decoded['detail'] as String;
        }
      }
    } catch (_) {}
    throw ApiException(code, message, requestId: requestId);
  }

  Future<dynamic> _get(String path, [Map<String, String>? query]) async {
    final resp =
        await _client.get(_uri(path, query), headers: await _headers());
    if (resp.statusCode < 200 || resp.statusCode >= 300) {
      _throwEnvelope(resp);
    }
    return json.decode(resp.body);
  }

  Future<Map<String, dynamic>> _post(String path, Map<String, dynamic> body,
      {Map<String, String>? extraHeaders}) async {
    final headers = await _headers();
    if (extraHeaders != null) headers.addAll(extraHeaders);
    final resp = await _client.post(_uri(path),
        headers: headers, body: json.encode(body));
    if (resp.statusCode < 200 || resp.statusCode >= 300) {
      _throwEnvelope(resp);
    }
    final decoded = json.decode(resp.body);
    if (decoded is Map<String, dynamic>) return decoded;
    return {'data': decoded};
  }

  Future<Map<String, dynamic>> _put(String path, Map<String, dynamic> body,
      {Map<String, String>? extraHeaders}) async {
    final headers = await _headers();
    if (extraHeaders != null) headers.addAll(extraHeaders);
    final resp = await _client.put(_uri(path),
        headers: headers, body: json.encode(body));
    if (resp.statusCode < 200 || resp.statusCode >= 300) {
      _throwEnvelope(resp);
    }
    final decoded = json.decode(resp.body);
    if (decoded is Map<String, dynamic>) return decoded;
    return {'data': decoded};
  }

  Future<dynamic> _delete(String path) async {
    final resp = await _client.delete(_uri(path), headers: await _headers());
    if (resp.statusCode < 200 || resp.statusCode >= 300) {
      _throwEnvelope(resp);
    }
    return json.decode(resp.body);
  }

  static List _asList(dynamic body, String key) {
    if (body is Map && body[key] is List) return body[key] as List;
    if (body is List) return body;
    return const [];
  }

  static String _str(Map m, String key, [String fallback = '']) {
    final v = m[key];
    if (v == null) return fallback;
    return v.toString();
  }

  static String? _nullableStr(Map m, String key) {
    final v = m[key];
    if (v == null) return null;
    final value = v.toString().trim();
    return value.isEmpty ? null : value;
  }

  static DateTime _date(Map m, String key) {
    final v = m[key];
    if (v is String) return DateTime.tryParse(v) ?? DateTime.now().toUtc();
    return DateTime.now().toUtc();
  }

  static RequestStatus _status(String raw) {
    if (raw == 'submitted') return RequestStatus.pending;
    for (final s in RequestStatus.values) {
      if (s.name == raw) return s;
    }
    return RequestStatus.draft;
  }

  /// Server kho dùng 'issue' cho xuất kho; quỹ dùng 'payment'.
  ///
  /// Backend còn có kind `adjustment_in` (bút toán điều chỉnh chiều TĂNG quỹ,
  /// xem `backend/app/api/routes/cash_sim.py::_ADJUSTMENT_IN_KINDS`). Frontend
  /// chưa có enum riêng cho chiều tăng -> ánh xạ về `RequestKind.adjustment`
  /// để UI hiển thị đúng là "phiếu điều chỉnh" (KHÔNG phải "phiếu thu").
  static RequestKind _kind(String raw) {
    if (raw == 'issue') return RequestKind.payment;
    if (raw == 'adjustment_in') return RequestKind.adjustment;
    for (final k in RequestKind.values) {
      if (k.name == raw) return k;
    }
    return RequestKind.receipt;
  }

  static String _serverStockKind(RequestKind kind) {
    if (kind == RequestKind.payment) return 'issue';
    return kind.name;
  }

  static AssetStatus _assetStatus(String raw) {
    for (final s in AssetStatus.values) {
      if (s.name == raw) return s;
    }
    return AssetStatus.available;
  }

  // ---- auth/users ----

  @override
  Future<List<AppUser>> loadUsers() async {
    try {
      final me = await _get('/me');
      if (me is Map) {
        return [
          AppUser(
            id: _str(me, 'id'),
            username: _str(me, 'username'),
            displayName: _str(me, 'display_name', _str(me, 'username')),
            email: me['email']?.toString(),
            phoneNumber: me['phone_number']?.toString(),
            branch: me['branch']?.toString(),
            roles: (me['roles'] is List ? me['roles'] as List : const [])
                .map((r) => r.toString())
                .toList(),
          ),
        ];
      }
    } catch (_) {}
    return const [
      AppUser(
        id: '00000000-0000-4000-8000-000000000001',
        username: 'tanmainguyenbinh',
        email: 'tanmainguyenbinh@gmail.com',
        displayName: 'Bình Tân (Chủ Quán / Admin)',
        roles: ['admin', 'inventory_manager', 'approver', 'system_admin'],
        capabilities: [
          'iam:admin',
          'admin:user_management',
          'admin',
          'inventory:approve_request',
          'catalog:manage',
          'price:view',
        ],
      ),
      AppUser(
        id: 'u_maker',
        username: 'demo_maker',
        displayName: 'Nguyễn Thị Mai',
        roles: ['staff', 'inventory_manager'],
      ),
      AppUser(
        id: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa2',
        username: 'demo_checker',
        displayName: 'Trần Văn Quản Lý',
        roles: ['admin', 'approver', 'inventory_manager'],
        capabilities: [
          'iam:admin',
          'admin:user_management',
          'admin',
          'inventory:approve_request',
        ],
      ),
      AppUser(
        id: 'u_auditor',
        username: 'demo_auditor',
        displayName: 'Lê Khánh Chi',
        roles: ['auditor'],
      ),
    ];
  }

  @override
  Future<AppUser> login(String username) async {
    final data = await _post('/auth/login', {
      'username': username,
      'password': 'DemoPass123!',
    });
    final u = (data['user'] is Map) ? data['user'] as Map : data;
    return AppUser(
      id: _str(u, 'id'),
      username: _str(u, 'username', username),
      displayName: _str(u, 'display_name', username),
      email: u['email']?.toString(),
      phoneNumber: u['phone_number']?.toString(),
      branch: u['branch']?.toString(),
      roles: (u['roles'] is List ? u['roles'] as List : const [])
          .map((r) => r.toString())
          .toList(),
    );
  }

  @override
  Future<void> changePassword({
    required String oldPassword,
    required String newPassword,
  }) async {
    await _post('/auth/change-password', {
      'old_password': oldPassword,
      'new_password': newPassword,
    });
  }

  @override
  Future<void> changePin({
    required String currentPassword,
    required String newPin,
  }) async {
    await _post('/auth/change-pin', {
      'current_password': currentPassword,
      'new_pin': newPin,
    });
  }

  @override
  Future<PasswordResetResult> requestPasswordReset(String username) async {
    final res = await _post('/auth/forgot-password', {
      'username': username.trim(),
    });
    return PasswordResetResult(
      username: _str(res, 'username', username.trim()),
      message: _str(res, 'message', 'Đã tạo mã xác thực OTP.'),
      otpDemo: res['otp_demo']?.toString(),
      expiresInSeconds: (res['expires_in_seconds'] is int)
          ? res['expires_in_seconds'] as int
          : 900,
    );
  }

  @override
  Future<void> resetPassword({
    required String username,
    required String otp,
    required String newPassword,
  }) async {
    await _post('/auth/reset-password', {
      'username': username.trim(),
      'otp': otp.trim(),
      'new_password': newPassword,
    });
  }

  @override
  Future<AppUser> updateProfile({
    required String displayName,
    String? email,
    String? phoneNumber,
    String? branch,
    String? avatarUrl,
  }) async {
    final res = await _put('/auth/me', {
      'display_name': displayName.trim(),
      if (email != null) 'email': email.trim(),
      if (phoneNumber != null) 'phone_number': phoneNumber.trim(),
      if (branch != null) 'branch': branch.trim(),
      if (avatarUrl != null) 'avatar_url': avatarUrl.trim(),
    });
    final u = (res['user'] is Map) ? res['user'] as Map : res;
    return AppUser(
      id: _str(u, 'id'),
      username: _str(u, 'username'),
      displayName: _str(u, 'display_name', displayName.trim()),
      email: u['email']?.toString(),
      phoneNumber: u['phone_number']?.toString(),
      branch: u['branch']?.toString(),
      avatarUrl: u['avatar_url']?.toString() ?? avatarUrl?.trim(),
      roles: (u['roles'] is List ? u['roles'] as List : const [])
          .map((r) => r.toString())
          .toList(),
    );
  }

  // ---- inventory ----

  @override
  Future<List<InventoryLocation>> getLocations() async {
    final body = await _get('/inventory/locations');
    return _asList(body, 'locations')
        .whereType<Map>()
        .map((m) => InventoryLocation(
              id: _str(m, 'id'),
              code: _str(m, 'code'),
              name: _str(m, 'name'),
            ))
        .toList();
  }

  @override
  Future<List<InventoryItem>> getItems() async {
    final body = await _get('/inventory/items');
    return _asList(body, 'items')
        .whereType<Map>()
        .map((m) => InventoryItem(
              id: _str(m, 'id'),
              sku: _str(m, 'sku'),
              name: _str(m, 'name'),
              unit: _str(m, 'unit'),
              trackedSerial: m['tracked_serial'] == true,
              category: _nullableStr(m, 'category'),
              packaging: _nullableStr(m, 'packaging'),
              costPrice: m['cost_price'] is num
                  ? (m['cost_price'] as num).toDouble()
                  : (m['costPrice'] is num ? (m['costPrice'] as num).toDouble() : null),
              sellingPrice: m['selling_price'] is num
                  ? (m['selling_price'] as num).toDouble()
                  : (m['sellingPrice'] is num ? (m['sellingPrice'] as num).toDouble() : null),
              minStock: m['min_stock'] is num
                  ? (m['min_stock'] as num).toDouble()
                  : (m['minStock'] is num ? (m['minStock'] as num).toDouble() : null),
            ))
        .toList();
  }

  @override
  Future<InventoryItem> createItem({
    required String sku,
    required String name,
    required String unit,
    bool trackedSerial = false,
    String? category,
    String? packaging,
    double? costPrice,
    double? sellingPrice,
    double? minStock,
  }) async {
    final body = await _post('/inventory/items', {
      'sku': sku,
      'name': name,
      'unit': unit,
      'tracked_serial': trackedSerial,
      if (category != null) 'category': category,
      if (packaging != null) 'packaging': packaging,
      if (costPrice != null) 'cost_price': costPrice,
      if (sellingPrice != null) 'selling_price': sellingPrice,
      if (minStock != null) 'min_stock': minStock,
    });
    return InventoryItem(
      id: _str(body, 'id'),
      sku: _str(body, 'sku', sku),
      name: _str(body, 'name', name),
      unit: _str(body, 'unit', unit),
      trackedSerial: body['tracked_serial'] == true,
      category: _nullableStr(body, 'category'),
      packaging: _nullableStr(body, 'packaging'),
      costPrice: costPrice,
      sellingPrice: sellingPrice,
      minStock: minStock,
    );
  }

  @override
  Future<BatchItemImportResult> createItemsBatch(
    List<Map<String, dynamic>> items,
  ) async {
    try {
      final body = await _post('/inventory/items/batch', {'items': items});
      final createdList = (body['items'] as List<dynamic>? ?? [])
          .map((i) => InventoryItem(
                id: _str(i as Map<String, dynamic>, 'id'),
                sku: _str(i, 'sku'),
                name: _str(i, 'name'),
                unit: _str(i, 'unit'),
                trackedSerial: i['tracked_serial'] == true,
                category: _nullableStr(i, 'category'),
                packaging: _nullableStr(i, 'packaging'),
                costPrice: i['cost_price'] is num ? (i['cost_price'] as num).toDouble() : null,
                sellingPrice: i['selling_price'] is num ? (i['selling_price'] as num).toDouble() : null,
                minStock: i['min_stock'] is num ? (i['min_stock'] as num).toDouble() : null,
              ))
          .toList();
      return BatchItemImportResult(
        createdCount: body['created_count'] as int? ?? createdList.length,
        skippedCount: body['skipped_count'] as int? ?? 0,
        items: createdList,
      );
    } catch (_) {
      // Fallback tuần tự nếu endpoint batch gặp lỗi mạng hoặc route
      final createdList = <InventoryItem>[];
      var skipped = 0;
      for (final it in items) {
        final sku = (it['sku'] ?? '').toString().trim();
        final name = (it['name'] ?? '').toString().trim();
        if (sku.isEmpty || name.isEmpty) {
          skipped++;
          continue;
        }
        try {
          final res = await createItem(
            sku: sku,
            name: name,
            unit: (it['unit'] ?? 'đơn vị').toString().trim(),
            trackedSerial: it['tracked_serial'] == true,
            category: it['category']?.toString(),
            packaging: it['packaging']?.toString(),
            costPrice: it['cost_price'] is num ? (it['cost_price'] as num).toDouble() : null,
            sellingPrice: it['selling_price'] is num ? (it['selling_price'] as num).toDouble() : null,
            minStock: it['min_stock'] is num ? (it['min_stock'] as num).toDouble() : null,
          );
          createdList.add(res);
        } catch (_) {
          skipped++;
        }
      }
      return BatchItemImportResult(
        createdCount: createdList.length,
        skippedCount: skipped,
        items: createdList,
      );
    }
  }

  @override
  Future<InventoryItem> updateItem({
    required String id,
    String? name,
    String? unit,
    bool? trackedSerial,
    String? category,
    String? packaging,
    double? costPrice,
    double? sellingPrice,
    double? minStock,
  }) async {
    final body = await _put('/inventory/items/$id', {
      if (name != null) 'name': name,
      if (unit != null) 'unit': unit,
      if (trackedSerial != null) 'tracked_serial': trackedSerial,
      if (category != null) 'category': category,
      if (packaging != null) 'packaging': packaging,
      if (costPrice != null) 'cost_price': costPrice,
      if (sellingPrice != null) 'selling_price': sellingPrice,
      if (minStock != null) 'min_stock': minStock,
    });
    return InventoryItem(
      id: _str(body, 'id', id),
      sku: _str(body, 'sku'),
      name: _str(body, 'name'),
      unit: _str(body, 'unit'),
      trackedSerial: body['tracked_serial'] == true,
      category: _nullableStr(body, 'category'),
      packaging: _nullableStr(body, 'packaging'),
      costPrice: costPrice,
      sellingPrice: sellingPrice,
      minStock: minStock,
    );
  }

  @override
  Future<void> deleteItem(String id) async {
    await _delete('/inventory/items/$id');
  }

  @override
  Future<void> resetStoreData({bool keepCatalog = true}) async {
    try {
      await _post('/admin/reset-store', {'keep_catalog': keepCatalog});
    } catch (_) {
      // offline or unsupported endpoint fallback
    }
  }

  @override
  Future<void> deleteItemsBatch(List<String> itemIds) async {
    if (itemIds.isEmpty) return;
    try {
      final res = await _post('/inventory/items/batch-delete', {'item_ids': itemIds});
      if (res['skipped_items'] is List &&
          (res['skipped_items'] as List).isNotEmpty &&
          res['deleted_count'] == 0) {
        final firstReason = (res['skipped_items'] as List).first;
        final msg = firstReason is Map && firstReason['message'] != null
            ? firstReason['message'] as String
            : 'Không thể xóa các mặt hàng đã chọn';
        throw ApiException('BATCH_DELETE_FAILED', msg);
      }
    } catch (e) {
      if (e is ApiException) rethrow;
      // Fallback sequentially in case backend does not have batch-delete endpoint yet
      for (final id in itemIds) {
        await deleteItem(id);
      }
    }
  }

  @override
  Future<InventoryLocation> createLocation({
    required String code,
    required String name,
  }) async {
    final body = await _post('/inventory/locations', {
      'code': code,
      'name': name,
    });
    return InventoryLocation(
      id: _str(body, 'id'),
      code: _str(body, 'code', code),
      name: _str(body, 'name', name),
    );
  }

  @override
  Future<InventoryLocation> updateLocation({
    required String id,
    String? name,
  }) async {
    final body = await _put('/inventory/locations/$id', {
      if (name != null) 'name': name,
    });
    return InventoryLocation(
      id: _str(body, 'id', id),
      code: _str(body, 'code'),
      name: _str(body, 'name'),
    );
  }

  @override
  Future<void> deleteLocation(String id) async {
    await _delete('/inventory/locations/$id');
  }

  @override
  Future<List<StockBalance>> getBalances({String? locationId}) async {
    final body = await _get('/inventory/balances',
        {if (locationId != null) 'location_id': locationId});
    return _asList(body, 'balances')
        .whereType<Map>()
        .map((m) => StockBalance(
              locationId: _str(m, 'location_id'),
              itemId: _str(m, 'item_id'),
              quantity: _str(m, 'quantity', '0'),
              reservedQuantity: _str(m, 'reserved_quantity', '0'),
              availableQuantity: m['available_quantity']?.toString(),
            ))
        .toList();
  }

  @override
  Future<List<AssetRecord>> getAssets({String? locationId}) async {
    final body = await _get('/inventory/assets');
    final all = _asList(body, 'assets').whereType<Map>().map((m) => AssetRecord(
          id: m['id']?.toString(),
          serial: _str(m, 'serial'),
          itemId: _str(m, 'item_id'),
          locationId: _str(m, 'location_id'),
          status: _assetStatus(_str(m, 'status')),
          assignee: m['assignee']?.toString(),
        ));
    if (locationId == null) return all.toList();
    return all.where((a) => a.locationId == locationId).toList();
  }

  @override
  Future<List<AssetLogItem>> getAssetHistory(String assetId) async {
    final body = await _get('/inventory/assets/$assetId/history');
    return _asList(body, 'logs')
        .whereType<Map>()
        .map((m) => AssetLogItem(
              id: _str(m, 'id'),
              serial: _str(m, 'serial'),
              fromLocationId: m['from_location_id']?.toString(),
              fromLocationName: m['from_location_name']?.toString(),
              toLocationId: m['to_location_id']?.toString(),
              toLocationName: m['to_location_name']?.toString(),
              fromAssignee: m['from_assignee']?.toString(),
              toAssignee: m['to_assignee']?.toString(),
              statusBefore: m['status_before']?.toString(),
              statusAfter: _str(m, 'status_after', 'in_stock'),
              actorId: m['actor_id']?.toString(),
              actorName: m['actor_name']?.toString(),
              requestId: m['request_id']?.toString(),
              notes: m['notes']?.toString(),
              createdAt: _date(m, 'created_at'),
            ))
        .toList();
  }

  @override
  Future<void> handoverAsset(
    String assetId, {
    String? toLocationId,
    String? toAssignee,
    String? status,
    String? notes,
  }) async {
    await _post(
      '/inventory/assets/$assetId/handover',
      {
        if (toLocationId != null) 'to_location_id': toLocationId,
        if (toAssignee != null) 'to_assignee': toAssignee,
        if (status != null) 'status': status,
        if (notes != null) 'notes': notes,
      },
      extraHeaders: {'Idempotency-Key': _idemKey()},
    );
  }

  @override
  Future<List<StockMovement>> getMovements({String? itemId}) async {
    final body = await _get('/inventory/movements');
    final all =
        _asList(body, 'movements').whereType<Map>().map((m) => StockMovement(
              id: _str(m, 'id'),
              itemId: _str(m, 'item_id'),
              locationId: _str(m, 'location_id'),
              quantity: _str(m, 'quantity_signed', '0'),
              kind: _str(m, 'kind', 'receipt'),
              createdAt: _date(m, 'created_at'),
            ));
    if (itemId == null) return all.toList();
    return all.where((x) => x.itemId == itemId).toList();
  }

  // ---- stock levels & low stock alerts ----

  @override
  Future<List<StockLevelItem>> getStockLevels(
      {String? locationId, String? itemId}) async {
    final query = <String, String>{};
    if (locationId != null) query['location_id'] = locationId;
    if (itemId != null) query['item_id'] = itemId;
    final path = query.isEmpty
        ? '/inventory/stock-levels'
        : '/inventory/stock-levels?${Uri(queryParameters: query).query}';
    final res = await _get(path);
    return _asList(res, 'stock_levels')
        .whereType<Map>()
        .map((m) => StockLevelItem(
              id: _str(m, 'id'),
              locationId: _str(m, 'location_id'),
              itemId: _str(m, 'item_id'),
              minQty: _str(m, 'min_qty', '0'),
              maxQty: m['max_qty']?.toString(),
            ))
        .toList();
  }

  @override
  Future<StockLevelItem> putStockLevel({
    required String locationId,
    required String itemId,
    required String minQty,
    String? maxQty,
  }) async {
    final res = await _put(
      '/inventory/stock-levels',
      {
        'location_id': locationId,
        'item_id': itemId,
        'min_qty': minQty,
        if (maxQty != null && maxQty.isNotEmpty) 'max_qty': maxQty,
      },
      extraHeaders: {'Idempotency-Key': _idemKey()},
    );
    return StockLevelItem(
      id: _str(res, 'id'),
      locationId: _str(res, 'location_id'),
      itemId: _str(res, 'item_id'),
      minQty: _str(res, 'min_qty', '0'),
      maxQty: res['max_qty']?.toString(),
    );
  }

  @override
  Future<List<LowStockAlertItem>> getLowStockAlerts(
      {String? locationId}) async {
    final path = locationId == null
        ? '/inventory/low-stock'
        : '/inventory/low-stock?location_id=$locationId';
    final res = await _get(path);
    return _asList(res, 'items')
        .whereType<Map>()
        .map((m) => LowStockAlertItem(
              locationId: _str(m, 'location_id'),
              locationCode: _str(m, 'location_code', 'N/A'),
              locationName: _str(m, 'location_name', 'N/A'),
              itemId: _str(m, 'item_id'),
              sku: _str(m, 'sku', 'N/A'),
              itemName: _str(m, 'item_name', 'N/A'),
              unit: _str(m, 'unit', 'đơn vị'),
              currentQty: _str(m, 'current_qty', '0'),
              minQty: _str(m, 'min_qty', '0'),
              maxQty: m['max_qty']?.toString(),
              status: _str(m, 'status', 'low'),
              deficit: _str(m, 'deficit', '0'),
              suggestedAction: _str(m, 'suggested_action', ''),
            ))
        .toList();
  }

  // ---- stocktakes ----

  StocktakeItem _parseStocktake(Map m) {
    final lines = (m['lines'] is List ? m['lines'] as List : const [])
        .whereType<Map>()
        .map((l) => StocktakeLineItem(
              id: _str(l, 'id'),
              itemId: _str(l, 'item_id'),
              bookQty: _str(l, 'book_qty', '0'),
              countedQty: _str(l, 'counted_qty', '0'),
              variance: _str(l, 'variance', '0'),
              openingQty: _str(l, 'opening_qty', '0'),
              receivedQty: _str(l, 'received_qty', '0'),
              usedQty: _str(l, 'used_qty', '0'),
              theoreticalQty: _str(l, 'theoretical_qty', '0'),
              reason: l['reason']?.toString(),
            ))
        .toList();
    return StocktakeItem(
      id: _str(m, 'id'),
      locationId: _str(m, 'location_id'),
      status: _str(m, 'status', 'open'),
      note: m['note']?.toString(),
      makerId: _str(m, 'maker_id'),
      approverId: m['approver_id']?.toString(),
      adjustmentRequestId: m['adjustment_request_id']?.toString(),
      createdAt: _date(m, 'created_at'),
      completedAt: m['completed_at'] != null ? _date(m, 'completed_at') : null,
      lines: lines,
      shiftCode: _nullableStr(m, 'shift_code'),
      businessDate: _nullableStr(m, 'business_date'),
      version: (m['version'] as num?)?.toInt() ?? 1,
    );
  }

  @override
  Future<List<StocktakeItem>> getStocktakes({String? locationId}) async {
    final path = locationId == null
        ? '/inventory/stocktakes'
        : '/inventory/stocktakes?location_id=$locationId';
    final res = await _get(path);
    return _asList(res, 'stocktakes')
        .whereType<Map>()
        .map(_parseStocktake)
        .toList();
  }

  @override
  Future<StocktakeItem> getStocktake(String id) async {
    final res = await _get('/inventory/stocktakes/$id');
    return _parseStocktake(res);
  }

  @override
  Future<StocktakeItem> createStocktake({
    required String locationId,
    String? note,
    String? shiftCode,
    String? businessDate,
    String? idempotencyKey,
  }) async {
    final res = await _post(
      '/inventory/stocktakes',
      {
        'location_id': locationId,
        if (note != null && note.isNotEmpty) 'note': note,
        if (shiftCode != null) 'shift_code': shiftCode,
        if (businessDate != null) 'business_date': businessDate,
      },
      extraHeaders: {'Idempotency-Key': idempotencyKey ?? _idemKey()},
    );
    return _parseStocktake(res);
  }

  @override
  Future<StocktakeItem> updateStocktakeLines(
      String id, List<Map<String, dynamic>> lines,
      {String? idempotencyKey, int? expectedVersion}) async {
    final res = await _put(
      '/inventory/stocktakes/$id/lines',
      {'lines': lines},
      extraHeaders: {
        'Idempotency-Key': idempotencyKey ?? _idemKey(),
        if (expectedVersion != null) 'If-Match': '$expectedVersion',
      },
    );
    return _parseStocktake(res);
  }

  @override
  Future<StocktakeItem> submitStocktake(String id,
      {String? idempotencyKey, int? expectedVersion}) async {
    final res = await _post(
      '/inventory/stocktakes/$id/submit',
      {},
      extraHeaders: {
        'Idempotency-Key': idempotencyKey ?? _idemKey(),
        if (expectedVersion != null) 'If-Match': '$expectedVersion',
      },
    );
    return _parseStocktake(res);
  }

  @override
  Future<StocktakeItem> approveStocktake(String id) async {
    final res = await _post(
      '/inventory/stocktakes/$id/approve',
      {},
      extraHeaders: {'Idempotency-Key': _idemKey()},
    );
    return _parseStocktake(res);
  }

  @override
  Future<StocktakeItem> rejectStocktake(String id, {String? reason}) async {
    final res = await _post(
      '/inventory/stocktakes/$id/reject',
      {'reason': reason ?? 'Yêu cầu kiểm đếm lại'},
    );
    return _parseStocktake(res);
  }

  @override
  Future<List<StockRequest>> getStockRequests() async {
    final body = await _get('/inventory/requests');
    return _asList(body, 'requests')
        .whereType<Map>()
        .map(_parseStockRequest)
        .toList();
  }

  @override
  Future<StockRequest> createStockRequest({
    required RequestKind kind,
    String? sourceLocationId,
    String? destLocationId,
    String? supplier,
    String? supplierName,
    String? invoiceNo,
    String? subKind,
    required List<StockRequestLine> lines,
    String? reason,
  }) async {
    final serverKind = _serverStockKind(kind);
    final payload = <String, dynamic>{
      'kind': serverKind,
      'reason': reason ?? '',
      if (subKind != null && subKind.trim().isNotEmpty)
        'sub_kind': subKind.trim(),
      if (invoiceNo != null && invoiceNo.trim().isNotEmpty)
        'invoice_no': invoiceNo.trim(),
      'lines': [
        for (final line in lines)
          {
            'item_id': line.itemId,
            'quantity': line.quantity,
            'serials': const <String>[],
            if (line.unitPrice != null && line.unitPrice!.trim().isNotEmpty)
              'unit_price': line.unitPrice!.trim(),
            if (line.lotNo != null && line.lotNo!.trim().isNotEmpty)
              'lot_no': line.lotNo!.trim(),
            if (line.expiryDate != null && line.expiryDate!.trim().isNotEmpty)
              'expiry_date': line.expiryDate!.trim(),
            if (line.unit != null && line.unit!.trim().isNotEmpty)
              'unit': line.unit!.trim(),
            if (line.conversionRate != null && line.conversionRate!.trim().isNotEmpty)
              'conversion_rate': line.conversionRate!.trim(),
          }
      ],
    };
    final effectiveSupplier = (supplierName ?? supplier)?.trim();
    if (serverKind == 'receipt' && effectiveSupplier != null &&
        effectiveSupplier.isNotEmpty) {
      payload['supplier'] = effectiveSupplier;
      payload['supplier_name'] = effectiveSupplier;
    }
    if (serverKind == 'receipt') {
      payload['dest_id'] = destLocationId ?? sourceLocationId;
    } else if (serverKind == 'issue') {
      payload['source_id'] = sourceLocationId ?? destLocationId;
      if (subKind == 'transfer' && destLocationId != null) {
        payload['dest_id'] = destLocationId;
      }
    } else if (serverKind == 'transfer') {
      payload['source_id'] = sourceLocationId;
      payload['dest_id'] = destLocationId ?? sourceLocationId;
    } else {
      payload['source_id'] = sourceLocationId;
      payload['dest_id'] = destLocationId ?? sourceLocationId;
    }
    final res = await _post(
      '/inventory/requests',
      payload,
      extraHeaders: {'Idempotency-Key': _idemKey()},
    );
    return _parseStockRequest(res);
  }

  @override
  Future<void> deleteStockRequest(String id) async {
    await _delete('/inventory/requests/$id');
  }

  StockRequest _parseStockRequest(Map m) {
    final lines = (m['lines'] is List ? m['lines'] as List : const [])
        .whereType<Map>()
        .map((l) => StockRequestLine(
              itemId: _str(l, 'item_id'),
              quantity: _str(l, 'quantity', '0'),
              unitPrice: l['unit_price']?.toString(),
              lineTotal: l['line_total']?.toString(),
              lotNo: l['lot_no']?.toString(),
              expiryDate: l['expiry_date']?.toString(),
              unit: l['unit']?.toString(),
              conversionRate: l['conversion_rate']?.toString(),
              itemName: l['item_name']?.toString() ?? l['name']?.toString(),
            ))
        .toList();
    final maker = _str(m, 'maker_id');
    final sourceId = m['source_id']?.toString();
    final destId = m['dest_id']?.toString();
    return StockRequest(
      id: _str(m, 'id'),
      kind: _kind(_str(m, 'kind')),
      status: _status(_str(m, 'status', 'draft')),
      version: (m['version'] is int)
          ? m['version'] as int
          : int.tryParse(_str(m, 'version', '1')) ?? 1,
      createdBy: maker,
      createdByName: _str(m, 'maker_name', maker),
      locationId: sourceId ?? destId ?? '',
      items: lines,
      reason: _str(m, 'reason'),
      createdAt: _date(m, 'created_at'),
      approvedBy: m['approved_by']?.toString(),
      approvedByName: m['approved_by_name']?.toString(),
      rejectReason: m['reject_reason']?.toString(),
      returnReason: m['return_reason']?.toString(),
      destinationLocationId: destId,
      supplier: m['supplier']?.toString(),
      supplierName: m['supplier_name']?.toString() ?? m['supplier']?.toString(),
      invoiceNo: m['invoice_no']?.toString(),
      subKind: m['sub_kind']?.toString(),
      receivedAt: m['received_at'] != null ? _date(m, 'received_at') : null,
    );
  }

  @override
  Future<StockRequest> submitStockRequest(String id) async {
    final res = _parseStockRequest(await _post(
      '/inventory/requests/$id/submit',
      {},
      extraHeaders: {'Idempotency-Key': _idemKey()},
    ));
    _approvalStreamCtrl.add('new_request:$id:kho');
    return res;
  }

  @override
  Future<StockRequest> approveStockRequest(String id,
      {String? supervisorPin}) async {
    final res = _parseStockRequest(await _post(
      '/inventory/requests/$id/approve',
      {if (supervisorPin != null) 'supervisor_pin': supervisorPin},
      extraHeaders: {'Idempotency-Key': _idemKey()},
    ));
    _approvalStreamCtrl.add('processed:$id');
    return res;
  }

  @override
  Future<StockRequest> rejectStockRequest(String id, String reason) async {
    final res = _parseStockRequest(await _post(
      '/inventory/requests/$id/reject',
      {'reason': reason},
      extraHeaders: {'Idempotency-Key': _idemKey()},
    ));
    _approvalStreamCtrl.add('processed:$id');
    return res;
  }

  @override
  Future<StockRequest> returnStockRequest(String id,
      {required String reason}) async {
    final res = _parseStockRequest(await _post(
      '/inventory/requests/$id/return',
      {'reason': reason},
      extraHeaders: {'Idempotency-Key': _idemKey()},
    ));
    _approvalStreamCtrl.add('processed:$id');
    return res;
  }

  // ---- cash-sim ----

  @override
  Future<List<Cashbox>> getCashboxes() async {
    final body = await _get('/cash-sim/boxes');
    return _asList(body, 'boxes')
        .whereType<Map>()
        .map((m) => Cashbox(
              id: _str(m, 'id'),
              code: _str(m, 'code'),
              name: _str(m, 'name'),
              openingBalance: _str(m, 'opening_balance', '0'),
            ))
        .toList();
  }

  @override
  Future<Cashbox> createCashbox({
    required String code,
    required String name,
    String currency = 'VND',
    String openingBalance = '0.00',
  }) async {
    final body = await _post('/cash-sim/boxes', {
      'code': code,
      'name': name,
      'currency': currency,
      'opening_balance': openingBalance,
    });
    return Cashbox(
      id: _str(body, 'id'),
      code: _str(body, 'code', code),
      name: _str(body, 'name', name),
      openingBalance: _str(body, 'opening_balance', openingBalance),
    );
  }

  @override
  Future<Cashbox> updateCashbox({
    required String id,
    String? name,
    bool? active,
  }) async {
    // CHỈ gửi metadata. Tuyệt đối KHÔNG gửi field số dư
    // (`balance`/`amount`/`opening_balance`): backend trả 422
    // DIRECT_BALANCE_WRITE_FORBIDDEN — số dư chỉ đổi qua phiếu (journal).
    final body = await _put('/cash-sim/boxes/$id', {
      if (name != null) 'name': name,
      if (active != null) 'active': active,
    });
    return Cashbox(
      id: _str(body, 'id', id),
      code: _str(body, 'code'),
      name: _str(body, 'name'),
      openingBalance: _str(body, 'balance', _str(body, 'opening_balance', '0')),
    );
  }

  @override
  Future<CashRequest> createCashAdjustmentRequest({
    required String cashboxId,
    required String amount,
    required bool increase,
    String? reason,
  }) async {
    // Contract backend (backend/app/api/routes/cash_sim.py):
    //  - `adjustment`     = bút toán điều chỉnh RA quỹ (chi) -> giảm số dư.
    //  - `adjustment_in`  = bút toán điều chỉnh VÀO quỹ (thu) -> tăng số dư.
    //  - `receipt`        = dòng tiền VÀO quỹ THƯỜNG (nạp quỹ của cashier).
    //
    // Không được dùng `receipt` cho chiều TĂNG của phiếu điều chỉnh: `receipt`
    // là nghiệp vụ thu tiền thường, còn `adjustment_in` là **bút toán điều chỉnh
    // số dư** -> bắt buộc có `cash:post_adjustment` ngay từ lúc TẠO phiếu
    // (backend: `_ADJUSTMENT_IN_KINDS` / `_FINANCIAL_ADJUSTMENT_KINDS`).
    // Gửi `receipt` ở đây làm mất phân quyền chiều tăng: một phiếu điều chỉnh
    // bị ghi nhận thành phiếu thu tiền thường.
    final kind = increase ? 'adjustment_in' : 'adjustment';
    final res = await _post(
      '/cash-sim/requests',
      {
        'kind': kind,
        'cashbox_id': cashboxId,
        'amount': amount,
        'currency': 'VND',
        'reason': reason ?? '',
      },
      extraHeaders: {'Idempotency-Key': _idemKey()},
    );
    return _parseCashRequest(res);
  }

  @override
  Future<void> deleteCashbox(String id) async {
    await _delete('/cash-sim/boxes/$id');
  }

  @override
  Future<List<CashBalance>> getCashBalances() async {
    final body = await _get('/cash-sim/balances');
    return _asList(body, 'balances')
        .whereType<Map>()
        .map((m) => CashBalance(
              cashboxId: _str(m, 'cashbox_id'),
              amount: _str(m, 'amount', '0'),
              currency: _str(m, 'currency', 'VND'),
            ))
        .toList();
  }

  @override
  Future<List<JournalEntry>> getJournals() async {
    final body = await _get('/cash-sim/journals');
    return _asList(body, 'journals')
        .whereType<Map>()
        .map((m) => JournalEntry(
              id: _str(m, 'id'),
              cashboxId: _str(m, 'cashbox_id'),
              kind: _str(m, 'kind', 'receipt'),
              amount: _str(m, 'amount', '0'),
              currency: _str(m, 'currency', 'VND'),
              reason: _str(m, 'reason', _str(m, 'correlation_id')),
              createdAt: _date(m, 'posted_at'),
            ))
        .toList();
  }

  CashRequest _parseCashRequest(Map m) {
    final maker = _str(m, 'maker_id');
    return CashRequest(
      id: _str(m, 'id'),
      kind: _kind(_str(m, 'kind')),
      status: _status(_str(m, 'status', 'draft')),
      version: (m['version'] is int)
          ? m['version'] as int
          : int.tryParse(_str(m, 'version', '1')) ?? 1,
      createdBy: maker,
      createdByName: _str(m, 'maker_name', maker),
      cashboxId: _str(m, 'cashbox_id'),
      amount: _str(m, 'amount', '0'),
      currency: _str(m, 'currency', 'VND'),
      reason: _str(m, 'reason'),
      createdAt: _date(m, 'created_at'),
      approvedBy: m['approved_by']?.toString(),
      approvedByName: m['approved_by_name']?.toString(),
      rejectReason: m['reject_reason']?.toString(),
      returnReason: m['return_reason']?.toString(),
    );
  }

  @override
  Future<List<CashRequest>> getCashRequests() async {
    final body = await _get('/cash-sim/requests');
    return _asList(body, 'requests')
        .whereType<Map>()
        .map(_parseCashRequest)
        .toList();
  }

  @override
  Future<CashRequest> createCashRequest({
    required String cashboxId,
    required RequestKind kind,
    required String amount,
    String? reason,
  }) async {
    final res = await _post(
      '/cash-sim/requests',
      {
        'kind': kind == RequestKind.payment ? 'payment' : 'receipt',
        'cashbox_id': cashboxId,
        'amount': amount,
        'currency': 'VND',
        'reason': reason ?? '',
      },
      extraHeaders: {'Idempotency-Key': _idemKey()},
    );
    return _parseCashRequest(res);
  }

  @override
  Future<void> deleteCashRequest(String id) async =>
      _delete('/cash-sim/requests/$id');

  @override
  Future<CashRequest> submitCashRequest(String id) async {
    final res = _parseCashRequest(await _post(
      '/cash-sim/requests/$id/submit',
      {},
      extraHeaders: {'Idempotency-Key': _idemKey()},
    ));
    _approvalStreamCtrl.add('new_request:$id:quỹ');
    return res;
  }

  @override
  Future<CashRequest> approveCashRequest(String id,
      {String? supervisorPin}) async {
    final res = _parseCashRequest(await _post(
      '/cash-sim/requests/$id/approve',
      {if (supervisorPin != null) 'supervisor_pin': supervisorPin},
      extraHeaders: {'Idempotency-Key': _idemKey()},
    ));
    _approvalStreamCtrl.add('processed:$id');
    return res;
  }

  @override
  Future<CashRequest> rejectCashRequest(String id, String reason) async {
    final res = _parseCashRequest(await _post(
      '/cash-sim/requests/$id/reject',
      {'reason': reason},
      extraHeaders: {'Idempotency-Key': _idemKey()},
    ));
    _approvalStreamCtrl.add('processed:$id');
    return res;
  }

  @override
  Future<CashRequest> returnCashRequest(String id,
      {required String reason}) async {
    final res = _parseCashRequest(await _post(
      '/cash-sim/requests/$id/return',
      {'reason': reason},
      extraHeaders: {'Idempotency-Key': _idemKey()},
    ));
    _approvalStreamCtrl.add('processed:$id');
    return res;
  }

  // ---- approvals ----

  @override
  Future<List<ApprovalItem>> getApprovalInbox() async {
    try {
      final body = await _get('/approvals/inbox');
      return _asList(body, 'approvals').whereType<Map>().map((m) {
        final id = _str(m, 'id');
        return ApprovalItem(
          id: id,
          kind: _str(m, 'kind'),
          maker: _str(m, 'maker'),
          impact: _str(m, 'impact', _str(m, 'status')),
          detail: _str(m, 'detail', id),
          approvalDetail: m['approval_detail'] is Map
              ? Map<String, dynamic>.from(m['approval_detail'] as Map)
              : (m['approval_detail'] is String
                  ? _decodeMap(m['approval_detail'] as String)
                  : null),
        );
      }).toList();
    } on ApiException catch (e) {
      if (e.code == 'HTTP_403' ||
          e.code == 'FORBIDDEN' ||
          e.message.contains('quyền')) {
        return const <ApprovalItem>[];
      }
      rethrow;
    }
  }

  Map<String, dynamic>? _decodeMap(String source) {
    try {
      final decoded = json.decode(source);
      return decoded is Map ? Map<String, dynamic>.from(decoded) : null;
    } on FormatException {
      return null;
    }
  }

  String _assessmentAmount(ApprovalItem item) {
    final structuredQuantity = item.approvalDetail?['total_quantity'];
    if (structuredQuantity != null) return structuredQuantity.toString();
    final raw = item.impact;
    final decimalMatch = RegExp(r'-?[\d,.]+').firstMatch(raw);
    if (decimalMatch == null) return raw;
    var amount = decimalMatch.group(0)!;
    if (amount.contains('.') && amount.contains(',')) {
      amount = amount.replaceAll(',', '');
    } else if (amount.contains(',')) {
      amount = amount.replaceAll(',', '.');
    }
    return amount;
  }

  @override
  Future<AiRiskAssessment> assessApprovalItem(ApprovalItem item) async {
    try {
      final structuredKind = item.approvalDetail?['kind']?.toString();
      final res = await _post('/ai/assess-request', {
        'request_id': item.id,
        'kind': structuredKind ?? item.kind,
        'amount_or_qty': _assessmentAmount(item),
        'maker': item.maker,
        'reason': item.detail,
      });
      return AiRiskAssessment.fromJson(res);
    } catch (error) {
      if (error is ApiException &&
          (error.code == 'AI_UNAVAILABLE' ||
              error.code == 'UPSTREAM_NOT_CONFIGURED')) {
        // Backend đã trả lời rõ AI chưa sẵn sàng — không dùng điểm yếu giả
        // lập; màn hình duyệt sẽ hiện trạng thái "chưa thẩm định" trung thực.
        rethrow;
      }
      final isCash = item.kind.toLowerCase() == 'cash' ||
          item.kind.toLowerCase().contains('quỹ');
      var rawImpact = item.impact;
      final decimalMatch =
          RegExp(r'[\.,]\d{1,2}(?:\s|[a-zA-Z]|$)').firstMatch(rawImpact);
      if (decimalMatch != null) {
        rawImpact = rawImpact.substring(0, decimalMatch.start);
      }
      final digits = rawImpact.replaceAll(RegExp(r'[^\d]'), '');
      final val = int.tryParse(digits) ?? 0;
      final isHigh = (isCash && val >= 500000000) || (!isCash && val >= 50);
      return AiRiskAssessment(
        requestId: item.id,
        riskLevel: isHigh ? 'high' : 'low',
        riskScore: isHigh ? 88 : 20,
        summary: 'Thẩm định ngoại tuyến cho phiếu ${item.id}',
        flaggedRules: isHigh
            ? ['Giao dịch vượt hạn mức kiểm soát kép (≥ 500 triệu VND)']
            : [],
        recommendations: ['Kiểm tra đối chiếu chứng từ gốc và xác nhận của quản lý'],
        auditStamp: 'offline-audit-stamp-${item.id}',
        assessmentSource: 'offline_fallback',
      );
    }
  }

  // ---- health (public, không cần auth) ----

  @override
  Future<HealthStatus> getHealth() async {
    final sw = Stopwatch()..start();
    try {
      final resp = await _client.get(
        _uri('/health/live'),
        headers: {'Content-Type': 'application/json'},
      ).timeout(const Duration(seconds: 10));
      sw.stop();
      if (resp.statusCode < 200 || resp.statusCode >= 300) {
        return HealthStatus(
          alive: false,
          version: '?',
          latencyMs: sw.elapsedMilliseconds,
          error: 'HTTP ${resp.statusCode}',
        );
      }
      final decoded = json.decode(resp.body);
      final version =
          decoded is Map ? (decoded['version']?.toString() ?? '?') : '?';
      return HealthStatus(
        alive: true,
        version: version,
        latencyMs: sw.elapsedMilliseconds,
      );
    } catch (e) {
      sw.stop();
      return HealthStatus(
        alive: false,
        version: '?',
        latencyMs: sw.elapsedMilliseconds,
        error: '$e',
      );
    }
  }

  // ---- activity ----

  @override
  Future<List<ActivityEvent>> getActivity({String? cursor}) async {
    final body =
        await _get('/activity', {if (cursor != null) 'cursor': cursor});
    return _asList(body, 'events')
        .whereType<Map>()
        .map((m) => ActivityEvent(
              id: _str(m, 'id'),
              occurredAt: _date(m, 'occurred_at'),
              subjectId: _str(m, 'subject_id'),
              status: _str(m, 'status'),
              messageKey: _str(m, 'message_key', _str(m, 'status')),
              processed: m['processed'] is int ? m['processed'] as int : null,
              total: m['total'] is int ? m['total'] as int : null,
            ))
        .toList();
  }

  // ---- integrations / reconciliations / reports ----

  String _idemKey() =>
      'idem-${DateTime.now().microsecondsSinceEpoch}-${identityHashCode(this)}';

  StagingPreview _parseStagingPreview(Map<String, dynamic> body) {
    final rows = _asList(body, 'rows').whereType<Map>().map((r) {
      final rawData = r['data'] is Map
          ? (r['data'] as Map).map((k, v) => MapEntry(k.toString(), v))
          : <String, dynamic>{};
      final rawErrors = (r['errors'] is List ? r['errors'] as List : const [])
          .map((e) => e.toString())
          .toList();
      return StagingRow(
        rowIndex: r['row_index'] is int ? r['row_index'] as int : 0,
        sourceRowKey: _str(r, 'source_row_key'),
        data: rawData,
        valid: r['valid'] == true,
        errors: rawErrors,
      );
    }).toList();
    return StagingPreview(
      runId: _str(body, 'run_id'),
      validCount: body['valid_count'] is int ? body['valid_count'] as int : 0,
      invalidCount:
          body['invalid_count'] is int ? body['invalid_count'] as int : 0,
      deduplicated: body['deduplicated'] == true,
      mappingVersion:
          body['mapping_version'] is int ? body['mapping_version'] as int : 1,
      rows: rows,
    );
  }

  @override
  Future<List<IntegrationConnection>> getConnections() async {
    final body = await _get('/integrations/connections');
    return _asList(body, 'connections')
        .whereType<Map>()
        .map((m) => IntegrationConnection(
              id: _str(m, 'id'),
              name: _str(m, 'name'),
              endpoint: _str(m, 'type'),
              status: _str(m, 'status', 'connected'),
              lastTestedAt: _date(m, 'last_tested_at'),
              lastError: _str(m, 'last_error', ''),
            ))
        .toList();
  }

  @override
  Future<IntegrationConnection> createConnection({
    required String name,
    required String type,
    String? endpoint,
    Map<String, dynamic>? config,
  }) async {
    final body = await _post(
      '/integrations/connections',
      {
        'name': name,
        'type': type,
        'status': 'connected',
        'config': config ?? (endpoint != null ? {'endpoint': endpoint} : {}),
      },
      extraHeaders: {'Idempotency-Key': _idemKey()},
    );
    return IntegrationConnection(
      id: _str(body, 'id'),
      name: _str(body, 'name'),
      endpoint: _str(body, 'type'),
      status: _str(body, 'status', 'connected'),
      lastTestedAt: _date(body, 'last_tested_at'),
      lastError: _str(body, 'last_error', ''),
    );
  }

  @override
  Future<IntegrationConnection> updateConnection({
    required String id,
    String? name,
    String? endpoint,
    String? status,
  }) async {
    final payload = <String, dynamic>{};
    if (name != null) payload['name'] = name;
    if (status != null) payload['status'] = status;
    if (endpoint != null) payload['config'] = {'endpoint': endpoint};
    final body = await _put('/integrations/connections/$id', payload);
    return IntegrationConnection(
      id: _str(body, 'id'),
      name: _str(body, 'name'),
      endpoint: _str(body, 'type'),
      status: _str(body, 'status', 'connected'),
      lastTestedAt: _date(body, 'last_tested_at'),
      lastError: _str(body, 'last_error', ''),
    );
  }

  @override
  Future<void> deleteConnection(String id) async =>
      _delete('/integrations/connections/$id');

  @override
  Future<Map<String, dynamic>> testConnection(String id) async {
    final body = await _post('/integrations/connections/$id/test', {});
    return body;
  }

  @override
  Future<List<IntegrationRun>> getIntegrationRuns() async {
    final body = await _get('/integrations/runs');
    return _asList(body, 'runs')
        .whereType<Map>()
        .map((m) => IntegrationRun(
              id: _str(m, 'id'),
              connectionId: _str(m, 'connection_id'),
              status: _str(m, 'status'),
              phase: _str(m, 'phase', 'pending'),
              startedAt: _date(m, 'created_at'),
              processed:
                  m['valid_count'] is int ? m['valid_count'] as int : null,
              errorCount:
                  m['invalid_count'] is int ? m['invalid_count'] as int : null,
              total: (m['valid_count'] is int && m['invalid_count'] is int)
                  ? (m['valid_count'] as int) + (m['invalid_count'] as int)
                  : null,
              error: _str(m, 'error', ''),
              endedAt: _date(m, 'finished_at'),
            ))
        .toList();
  }

  @override
  Future<StagingPreview> uploadImportFile({
    required String filename,
    required List<int> bytes,
    required String type,
  }) async {
    final req = http.MultipartRequest('POST', _uri('/integrations/uploads'));
    final headers = await _headers();
    headers.remove('Content-Type');
    headers['Idempotency-Key'] = _idemKey();
    req.headers.addAll(headers);
    req.fields['type'] = type;
    req.files.add(
      http.MultipartFile.fromBytes('file', bytes, filename: filename),
    );
    final streamed = await _client.send(req);
    final resp = await http.Response.fromStream(streamed);
    if (resp.statusCode < 200 || resp.statusCode >= 300) {
      _throwEnvelope(resp);
    }
    final decoded = json.decode(resp.body) as Map<String, dynamic>;
    return _parseStagingPreview(decoded);
  }

  @override
  Future<StagingPreview> fetchGoogleSheet({
    required String sheetId,
    String tab = 'Sheet1',
  }) async {
    final body = await _post(
      '/integrations/google-sheets/fetch',
      {'sheet_id': sheetId, 'tab': tab},
      extraHeaders: {'Idempotency-Key': _idemKey()},
    );
    return _parseStagingPreview(body);
  }

  @override
  Future<StagingPreview> getRunPreview(String runId) async {
    final body = await _get('/integrations/runs/$runId/preview');
    return _parseStagingPreview(body as Map<String, dynamic>);
  }

  @override
  Future<ConfirmRunResult> confirmRun(String runId) async {
    final body = await _post(
      '/integrations/runs/$runId/confirm',
      {},
      extraHeaders: {'Idempotency-Key': _idemKey()},
    );
    final drafts =
        _asList(body, 'draft_requests').map((e) => e.toString()).toList();
    return ConfirmRunResult(
      runId: _str(body, 'run_id', runId),
      status: _str(body, 'status', 'confirmed'),
      draftRequests: drafts,
    );
  }

  ReconciliationRun _parseReconciliation(Map m) {
    final rawEx = m['exceptions'] is List
        ? m['exceptions'] as List
        : _asList(m, 'exceptions_json');
    return ReconciliationRun(
      id: _str(m, 'id'),
      status: _str(m, 'status'),
      scope: _str(m, 'scope'),
      startedAt: _date(m, 'created_at'),
      exceptions: rawEx.map((e) => e.toString()).toList(),
      exceptionCount: int.tryParse(_str(m, 'exception_count')) ?? 0,
      openExceptionCount: int.tryParse(_str(m, 'open_exception_count')) ?? 0,
      autoFixed: _str(m, 'auto_fixed') == 'true',
    );
  }

  @override
  Future<List<ReconciliationRun>> getReconciliations() async {
    final body = await _get('/reconciliations');
    final list = _asList(body, 'runs').isNotEmpty
        ? _asList(body, 'runs')
        : _asList(body, 'reconciliations');
    return list.whereType<Map>().map(_parseReconciliation).toList();
  }

  @override
  Future<ReconciliationRun> runReconciliation({String scope = 'cash'}) async {
    final body = await _post(
      '/reconciliations',
      {'scope': scope},
      extraHeaders: {'Idempotency-Key': _idemKey()},
    );
    return _parseReconciliation(body);
  }

  List<InventoryBucket> _parseInventoryBuckets(dynamic body) {
    return _asList(body, 'buckets')
        .whereType<Map>()
        .map((m) => InventoryBucket(
              bucket: _str(m, 'bucket'),
              inboundQty: _str(m, 'inbound_qty', '0'),
              outboundQty: _str(m, 'outbound_qty', '0'),
              netQty: _str(m, 'net_qty', '0'),
              receiptCount:
                  m['receipt_count'] is int ? m['receipt_count'] as int : 0,
              issueCount: m['issue_count'] is int ? m['issue_count'] as int : 0,
            ))
        .toList();
  }

  List<CashflowBucket> _parseCashflowBuckets(dynamic body) {
    return _asList(body, 'buckets')
        .whereType<Map>()
        .map((m) => CashflowBucket(
              bucket: _str(m, 'bucket'),
              totalIn: _str(m, 'total_in', '0'),
              totalOut: _str(m, 'total_out', '0'),
              net: _str(m, 'net', '0'),
              journalCount:
                  m['journal_count'] is int ? m['journal_count'] as int : 0,
            ))
        .toList();
  }

  @override
  Future<List<InventoryBucket>> getInventoryDaily({
    String? dateFrom,
    String? dateTo,
  }) async {
    final body = await _get('/reports/inventory-daily', {
      if (dateFrom != null) 'date_from': dateFrom,
      if (dateTo != null) 'date_to': dateTo,
    });
    return _parseInventoryBuckets(body);
  }

  @override
  Future<List<InventoryBucket>> getInventoryMonthly({
    String? dateFrom,
    String? dateTo,
  }) async {
    final body = await _get('/reports/inventory-monthly', {
      if (dateFrom != null) 'date_from': dateFrom,
      if (dateTo != null) 'date_to': dateTo,
    });
    return _parseInventoryBuckets(body);
  }

  @override
  Future<List<CashflowBucket>> getCashflowDaily({
    String? dateFrom,
    String? dateTo,
  }) async {
    final body = await _get('/reports/cashflow-daily', {
      if (dateFrom != null) 'date_from': dateFrom,
      if (dateTo != null) 'date_to': dateTo,
    });
    return _parseCashflowBuckets(body);
  }

  @override
  Future<List<CashflowBucket>> getCashflowMonthly({
    String? dateFrom,
    String? dateTo,
  }) async {
    final body = await _get('/reports/cashflow-monthly', {
      if (dateFrom != null) 'date_from': dateFrom,
      if (dateTo != null) 'date_to': dateTo,
    });
    return _parseCashflowBuckets(body);
  }

  @override
  Future<List<StagnationItem>> getStagnation({
    int watchDays = 30,
    int stagnantDays = 60,
    int criticalDays = 90,
  }) async {
    final body = await _get('/reports/stagnation', {
      'watch_days': '$watchDays',
      'stagnant_days': '$stagnantDays',
      'critical_days': '$criticalDays',
    });
    return _asList(body, 'items')
        .whereType<Map>()
        .map((m) => StagnationItem(
              itemId: _str(m, 'item_id'),
              sku: _str(m, 'sku'),
              name: _str(m, 'name'),
              quantity: _str(m, 'quantity', '0'),
              daysSinceLastIssue: m['days_since_last_issue'] is int
                  ? m['days_since_last_issue'] as int
                  : null,
              severity: _str(m, 'severity', 'normal'),
            ))
        .toList();
  }

  @override
  Future<List<ExpiryAlertItem>> getExpiryAlerts({int days = 7}) async {
    final body = await _get('/inventory/expiry-alerts', {'days': '$days'});
    return _asList(body, 'alerts')
        .whereType<Map>()
        .map((m) => ExpiryAlertItem.fromJson(Map<String, dynamic>.from(m)))
        .toList();
  }

  @override
  Future<List<ConsumptionTopItem>> getConsumptionTop({
    String? dateFrom,
    String? dateTo,
    int limit = 10,
  }) async {
    final params = <String, String>{
      'limit': '$limit',
      if (dateFrom != null) 'date_from': dateFrom,
      if (dateTo != null) 'date_to': dateTo,
    };
    final body = await _get('/reports/consumption-top', params);
    return _asList(body, 'items')
        .whereType<Map>()
        .map((m) => ConsumptionTopItem.fromJson(Map<String, dynamic>.from(m)))
        .toList();
  }

  @override
  Future<List<ShiftHistoryItem>> getShiftHistory({
    String? dateFrom,
    String? dateTo,
    String? shiftCode,
  }) async {
    final params = <String, String>{
      if (dateFrom != null) 'date_from': dateFrom,
      if (dateTo != null) 'date_to': dateTo,
      if (shiftCode != null) 'shift_code': shiftCode,
    };
    final body = await _get('/reports/shift-history', params);
    return _asList(body, 'shifts')
        .whereType<Map>()
        .map((m) => ShiftHistoryItem.fromJson(Map<String, dynamic>.from(m)))
        .toList();
  }

  // =========================================================================
  // Admin IAM (Phase 1)
  // =========================================================================

  @override
  Future<List<BranchDto>> getBranches() async {
    final body = await _get('/admin/branches');
    return _asList(body, 'branches')
        .whereType<Map<String, dynamic>>()
        .map(BranchDto.fromJson)
        .toList();
  }

  @override
  Future<List<RoleDto>> getRoles() async {
    final body = await _get('/admin/roles');
    return _asList(body, 'roles')
        .whereType<Map<String, dynamic>>()
        .map(RoleDto.fromJson)
        .toList();
  }

  @override
  Future<List<EmployeeUserDto>> getEmployees({
    String? search,
    String? branchId,
    String? role,
    String? status,
  }) async {
    final query = <String, String>{};
    if (search != null && search.isNotEmpty) query['search'] = search;
    if (branchId != null && branchId.isNotEmpty) query['branch_id'] = branchId;
    if (role != null && role.isNotEmpty) query['role'] = role;
    if (status != null && status.isNotEmpty) query['status'] = status;
    final body = await _get('/admin/users', query.isEmpty ? null : query);
    return _asList(body, 'users')
        .whereType<Map<String, dynamic>>()
        .map(EmployeeUserDto.fromJson)
        .toList();
  }

  @override
  Future<EmployeeUserDto> createEmployee({
    required String username,
    required String displayName,
    String? email,
    String? phoneNumber,
    String? branchId,
    List<String> roles = const ['staff'],
    List<Map<String, dynamic>> scopes = const [],
    String onboardingMethod = 'temporary_password',
  }) async {
    final payload = <String, dynamic>{
      'username': username,
      'display_name': displayName,
      'email': email,
      'phone_number': phoneNumber,
      'branch_id': branchId,
      'roles': roles,
      'scopes': scopes,
      'onboarding_method': onboardingMethod,
    };
    final body = await _post('/admin/users', payload, extraHeaders: _idem());
    final userMap = Map<String, dynamic>.from(body['user'] as Map<String, dynamic>? ?? body);
    userMap['last_invite_link'] = body['invite_link'];
    userMap['last_invite_token'] = body['invite_token'];
    userMap['last_invite_email_sent'] = body['invite_email_sent'];
    userMap['last_email_delivery_message'] = body['email_delivery_message'];
    userMap['last_temporary_password'] = body['temporary_password'];
    return EmployeeUserDto.fromJson(userMap);
  }

  @override
  Future<EmployeeUserDto> updateEmployeeStatus(
    String userId,
    String status, {
    String? reason,
  }) async {
    final body = await _post(
      '/admin/users/$userId/status',
      {'status': status, 'reason': reason},
      extraHeaders: _idem(),
    );
    final userMap = body['user'] as Map<String, dynamic>? ?? body;
    return EmployeeUserDto.fromJson(userMap);
  }

  @override
  Future<EmployeeUserDto> updateEmployeeRoles(
      String userId, List<String> roles) async {
    final body = await _put(
      '/admin/users/$userId/roles',
      {'roles': roles},
      extraHeaders: _idem(),
    );
    final userMap = body['user'] as Map<String, dynamic>? ?? body;
    return EmployeeUserDto.fromJson(userMap);
  }

  @override
  Future<EmployeeUserDto> updateEmployeeScopes(
    String userId,
    List<Map<String, dynamic>> scopes,
  ) async {
    final body = await _put(
      '/admin/users/$userId/scopes',
      {'scopes': scopes},
      extraHeaders: _idem(),
    );
    final userMap = body['user'] as Map<String, dynamic>? ?? body;
    return EmployeeUserDto.fromJson(userMap);
  }

  @override
  Future<void> revokeEmployeeSessions(String userId) async {
    await _post('/admin/users/$userId/sessions/revoke', {},
        extraHeaders: _idem());
  }

  @override
  Future<String> resetEmployeePassword(String userId) async {
    final body = await _post('/admin/users/$userId/reset-password', {},
        extraHeaders: _idem());
    return body['temporary_password'] as String? ?? '';
  }

  @override
  Future<String> reinviteEmployee(String userId) async {
    final body =
        await _post('/admin/users/$userId/invite', {}, extraHeaders: _idem());
    return body['invite_token'] as String? ?? '';
  }

  // =========================================================================
  // ETL Pipeline (Phase 2)
  // =========================================================================

  @override
  Future<List<EtlConnectionDto>> getEtlConnections({String? branchId}) async {
    final query = branchId != null ? {'branch_id': branchId} : null;
    final body = await _get('/etl/connections', query);
    return _asList(body, 'connections')
        .whereType<Map<String, dynamic>>()
        .map(EtlConnectionDto.fromJson)
        .toList();
  }

  @override
  Future<EtlConnectionDto> createEtlConnection({
    required String name,
    required String type,
    String? secretRef,
    List<String>? allowlistSheets,
    String? branchId,
  }) async {
    final body = await _post('/etl/connections', {
      'name': name,
      'type': type,
      'secret_ref': secretRef,
      'allowlist_sheets': allowlistSheets,
      'branch_id': branchId,
    });
    return EtlConnectionDto.fromJson(body);
  }

  @override
  Future<List<EtlPipelineDto>> getEtlPipelines({
    String? target,
    String? branchId,
  }) async {
    final query = <String, String>{};
    if (target != null && target.isNotEmpty) query['target'] = target;
    if (branchId != null && branchId.isNotEmpty) query['branch_id'] = branchId;
    final body = await _get('/etl/pipelines', query.isEmpty ? null : query);
    return _asList(body, 'pipelines')
        .whereType<Map<String, dynamic>>()
        .map(EtlPipelineDto.fromJson)
        .toList();
  }

  @override
  Future<EtlPipelineDto> createEtlPipeline({
    required String name,
    required String target,
    required String connectionId,
    String? branchId,
    String? locationId,
    String? destinationLocationId,
    String? scheduleCron,
  }) async {
    final body = await _post('/etl/pipelines', {
      'name': name,
      'target': target,
      'connection_id': connectionId,
      'branch_id': branchId,
      'location_id': locationId,
      'destination_location_id': destinationLocationId,
      'schedule_cron': scheduleCron,
    });
    return EtlPipelineDto.fromJson(body);
  }

  @override
  Future<List<EtlMappingVersionDto>> getEtlMappingVersions(
      String pipelineId) async {
    final body = await _get('/etl/pipelines/$pipelineId/mapping-versions');
    return _asList(body, 'mapping_versions')
        .whereType<Map<String, dynamic>>()
        .map(EtlMappingVersionDto.fromJson)
        .toList();
  }

  @override
  Future<EtlMappingVersionDto> createEtlMappingVersion(
    String pipelineId, {
    required List<Map<String, dynamic>> mappingRules,
    String duplicatePolicy = 'reject',
  }) async {
    final body = await _post('/etl/pipelines/$pipelineId/mapping-versions', {
      'mapping_rules': mappingRules,
      'duplicate_policy': duplicatePolicy,
    });
    return EtlMappingVersionDto.fromJson(body);
  }

  @override
  Future<EtlMappingVersionDto> publishEtlMappingVersion(
    String pipelineId,
    String versionId,
  ) async {
    final body = await _post(
      '/etl/pipelines/$pipelineId/mapping-versions/$versionId/publish',
      {},
    );
    return EtlMappingVersionDto.fromJson(body);
  }

  @override
  Future<EtlRunDto> triggerEtlRun(
    String pipelineId, {
    List<Map<String, dynamic>>? rawRows,
    List<int>? fileBytes,
    String? filename,
    String? externalEventId,
  }) async {
    if (fileBytes != null && fileBytes.isNotEmpty) {
      final request = http.MultipartRequest(
          'POST', _uri('/etl/pipelines/$pipelineId/runs'));
      final token = await _tokenProvider?.call();
      if (token != null && token.isNotEmpty) {
        request.headers['Authorization'] = 'Bearer $token';
      }
      request.files.add(http.MultipartFile.fromBytes(
        'file',
        fileBytes,
        filename: filename ?? 'upload.csv',
      ));
      final streamed = await _client.send(request);
      final resp = await http.Response.fromStream(streamed);
      if (resp.statusCode < 200 || resp.statusCode >= 300) {
        _throwEnvelope(resp);
      }
      return EtlRunDto.fromJson(json.decode(resp.body) as Map<String, dynamic>);
    }

    final body = await _post('/etl/pipelines/$pipelineId/runs', {
      'raw_rows': rawRows ?? [],
      'external_event_id': externalEventId,
    });
    return EtlRunDto.fromJson(body);
  }

  @override
  Future<List<EtlRunDto>> getEtlRuns({
    String? pipelineId,
    String? status,
  }) async {
    final query = <String, String>{};
    if (pipelineId != null && pipelineId.isNotEmpty) {
      query['pipeline_id'] = pipelineId;
    }
    if (status != null && status.isNotEmpty) query['status'] = status;
    final body = await _get('/etl/runs', query.isEmpty ? null : query);
    return _asList(body, 'runs')
        .whereType<Map<String, dynamic>>()
        .map(EtlRunDto.fromJson)
        .toList();
  }

  @override
  Future<EtlRunDto> getEtlRun(String runId) async {
    final body = await _get('/etl/runs/$runId');
    return EtlRunDto.fromJson(body as Map<String, dynamic>);
  }

  @override
  Future<Map<String, dynamic>> getEtlRunRows(
    String runId, {
    bool? valid,
    String? search,
    int page = 1,
    int pageSize = 50,
  }) async {
    final query = <String, String>{
      'page': '$page',
      'page_size': '$pageSize',
    };
    if (valid != null) query['valid'] = '$valid';
    if (search != null && search.isNotEmpty) query['search'] = search;
    final body =
        await _get('/etl/runs/$runId/rows', query) as Map<String, dynamic>;
    final rowsList = (body['rows'] as List?)
            ?.whereType<Map<String, dynamic>>()
            .map(EtlRunRowDto.fromJson)
            .toList() ??
        <EtlRunRowDto>[];
    return {
      'total': body['total'] as int? ?? 0,
      'page': body['page'] as int? ?? 1,
      'page_size': body['page_size'] as int? ?? 50,
      'rows': rowsList,
    };
  }

  @override
  Future<EtlRunDto> reviewEtlRun(
    String runId, {
    required String decision,
    String? note,
  }) async {
    final body = await _post('/etl/runs/$runId/review', {
      'decision': decision,
      'note': note,
    });
    return EtlRunDto.fromJson(body);
  }

  @override
  Future<Map<String, dynamic>> postEtlRun(String runId) async {
    return await _post('/etl/runs/$runId/post', {});
  }

  @override
  Future<String> getEtlErrorReport(String runId) async {
    final headers = await _headers();
    final resp = await _client.get(
        _uri('/etl/runs/$runId/error-report', {'format': 'csv'}),
        headers: headers);
    if (resp.statusCode < 200 || resp.statusCode >= 300) {
      _throwEnvelope(resp);
    }
    return resp.body;
  }

  @override
  Future<DashboardSummaryDto> getDashboardSummary({bool canApprove = false}) async {
    try {
      final res = await _get('/dashboard/summary');
      if (res is Map) {
        final locs = _asList(res, 'locations')
            .whereType<Map>()
            .map((m) => InventoryLocation(
                  id: _str(m, 'id'),
                  code: _str(m, 'code'),
                  name: _str(m, 'name'),
                ))
            .toList();

        final items = _asList(res, 'items')
            .whereType<Map>()
            .map((m) => InventoryItem(
                  id: _str(m, 'id'),
                  sku: _str(m, 'sku'),
                  name: _str(m, 'name'),
                  unit: _str(m, 'unit'),
                  trackedSerial: m['tracked_serial'] == true,
                  category: _nullableStr(m, 'category'),
                  packaging: _nullableStr(m, 'packaging'),
                ))
            .toList();

        final balances = _asList(res, 'balances')
            .whereType<Map>()
            .map((m) => StockBalance(
                  locationId: _str(m, 'location_id'),
                  itemId: _str(m, 'item_id'),
                  quantity: _str(m, 'quantity', '0'),
                  reservedQuantity: _str(m, 'reserved_quantity', '0'),
                  availableQuantity: m['available_quantity']?.toString(),
                ))
            .toList();

        final assets = _asList(res, 'assets')
            .whereType<Map>()
            .map((m) => AssetRecord(
                  id: m['id']?.toString(),
                  serial: _str(m, 'serial'),
                  itemId: _str(m, 'item_id'),
                  locationId: _str(m, 'location_id'),
                  status: _assetStatus(_str(m, 'status')),
                  assignee: m['assignee']?.toString() ?? m['assignee_demo']?.toString(),
                ))
            .toList();

        final stockRequests = _asList(res, 'stock_requests')
            .whereType<Map>()
            .map(_parseStockRequest)
            .toList();

        final inbox = canApprove
            ? _asList(res, 'inbox').whereType<Map>().map((m) {
                final id = _str(m, 'id');
                return ApprovalItem(
                  id: id,
                  kind: _str(m, 'kind'),
                  maker: _str(m, 'maker'),
                  impact: _str(m, 'impact', _str(m, 'status')),
                  detail: _str(m, 'detail', id),
                  approvalDetail: m['approval_detail'] is Map
                      ? Map<String, dynamic>.from(m['approval_detail'] as Map)
                      : (m['approval_detail'] is String
                          ? _decodeMap(m['approval_detail'] as String)
                          : null),
                );
              }).toList()
            : <ApprovalItem>[];

        final cashBalances = _asList(res, 'cash_balances')
            .whereType<Map>()
            .map((m) => CashBalance(
                  cashboxId: _str(m, 'cashbox_id'),
                  amount: _str(m, 'amount', '0'),
                  currency: _str(m, 'currency', 'VND'),
                ))
            .toList();

        final cashboxes = _asList(res, 'cashboxes')
            .whereType<Map>()
            .map((m) => Cashbox(
                  id: _str(m, 'id'),
                  code: _str(m, 'code'),
                  name: _str(m, 'name'),
                  openingBalance: _str(m, 'opening_balance', '0'),
                ))
            .toList();

        final lowStockAlerts = _asList(res, 'low_stock_alerts')
            .whereType<Map>()
            .map((m) => LowStockAlertItem(
                  locationId: _str(m, 'location_id'),
                  locationCode: _str(m, 'location_code', 'N/A'),
                  locationName: _str(m, 'location_name', 'N/A'),
                  itemId: _str(m, 'item_id'),
                  sku: _str(m, 'sku', 'N/A'),
                  itemName: _str(m, 'item_name', 'N/A'),
                  unit: _str(m, 'unit', 'đơn vị'),
                  currentQty: _str(m, 'current_qty', '0'),
                  minQty: _str(m, 'min_qty', '0'),
                  maxQty: m['max_qty']?.toString(),
                  status: _str(m, 'status', 'low'),
                  deficit: _str(m, 'deficit', '0'),
                  suggestedAction: _str(m, 'suggested_action', ''),
                ))
            .toList();

        final recList = _asList(res, 'reconciliations');
        final reconciliations = recList.whereType<Map>().map(_parseReconciliation).toList();

        return DashboardSummaryDto(
          locations: locs,
          items: items,
          balances: balances,
          assets: assets,
          stockRequests: stockRequests,
          inbox: inbox,
          cashBalances: cashBalances,
          cashboxes: cashboxes,
          lowStockAlerts: lowStockAlerts,
          reconciliations: reconciliations,
        );
      }
    } catch (_) {
      // Graceful fallback to individual calls if server endpoint is unavailable
    }

    final results = await Future.wait([
      getLocations().catchError((_) => <InventoryLocation>[]),
      getItems().catchError((_) => <InventoryItem>[]),
      getBalances().catchError((_) => <StockBalance>[]),
      getAssets().catchError((_) => <AssetRecord>[]),
      getStockRequests().catchError((_) => <StockRequest>[]),
      canApprove
          ? getApprovalInbox().catchError((_) => <ApprovalItem>[])
          : Future.value(<ApprovalItem>[]),
      getCashBalances().catchError((_) => <CashBalance>[]),
      getCashboxes().catchError((_) => <Cashbox>[]),
      getLowStockAlerts().catchError((_) => <LowStockAlertItem>[]),
      getReconciliations().catchError((_) => <ReconciliationRun>[]),
    ]);

    return DashboardSummaryDto(
      locations: results[0] as List<InventoryLocation>,
      items: results[1] as List<InventoryItem>,
      balances: results[2] as List<StockBalance>,
      assets: results[3] as List<AssetRecord>,
      stockRequests: results[4] as List<StockRequest>,
      inbox: results[5] as List<ApprovalItem>,
      cashBalances: results[6] as List<CashBalance>,
      cashboxes: results[7] as List<Cashbox>,
      lowStockAlerts: results[8] as List<LowStockAlertItem>,
      reconciliations: results[9] as List<ReconciliationRun>,
    );
  }
}
