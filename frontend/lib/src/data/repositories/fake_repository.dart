import 'dart:async';
import 'dart:convert';
import 'dart:math';

import '../models/dtos.dart';
import 'bankops_repository.dart';

part 'seed_data.dart';

/// Repository demo: đọc sample-data/ + mô phỏng latency và SSE trong bộ nhớ.
class FakeBankOpsRepository implements BankOpsRepository {
  FakeBankOpsRepository(
      {Random? random, Duration latency = const Duration(milliseconds: 350)})
      : _random = random ?? Random(7),
        _latency = latency;

  final Random _random;
  final Duration _latency;
  final _approvalStreamCtrl = StreamController<String>.broadcast();

  @override
  void dispose() {
    _approvalStreamCtrl.close();
  }

  @override
  Stream<String> get approvalNotifications => _approvalStreamCtrl.stream;

  Future<T> _delay<T>(T value) {
    if (_latency == Duration.zero) return Future.value(value);
    return Future<T>.delayed(
      _latency ~/ 2 +
          Duration(
              milliseconds: _random.nextInt(_latency.inMilliseconds ~/ 2 + 1)),
      () => value,
    );
  }

  // ---- users ----
  final _users = <AppUser>[];

  @override
  Future<HealthStatus> getHealth() => _delay(
        const HealthStatus(alive: true, version: '0.1.0', latencyMs: 0),
      );

  @override
  Future<List<AppUser>> loadUsers() async {
    if (_users.isEmpty) _users.addAll(_seedUsers());
    return _delay(List.of(_users));
  }

  @override
  Future<AppUser> login(String username) => _delay(_users.firstWhere(
      (u) => u.username == username,
      orElse: () => throw ApiException('NOT_FOUND', 'Không tìm thấy user')));

  @override
  Future<void> changePassword({
    required String oldPassword,
    required String newPassword,
  }) async {
    if (oldPassword.isEmpty) {
      throw ApiException('VALIDATION_ERROR', 'Mật khẩu cũ không được để trống');
    }
    if (newPassword.length < 6) {
      throw ApiException(
          'VALIDATION_ERROR', 'Mật khẩu mới phải có ít nhất 6 ký tự');
    }
    if (newPassword == oldPassword) {
      throw ApiException(
          'VALIDATION_ERROR', 'Mật khẩu mới không được trùng mật khẩu cũ');
    }
    await _delay(null);
  }

  String _supervisorPin = '123456';
  String get supervisorPin => _supervisorPin;

  @override
  Future<void> changePin({
    required String currentPassword,
    required String newPin,
  }) async {
    if (currentPassword.isEmpty) {
      throw ApiException(
          'VALIDATION_ERROR', 'Mật khẩu xác thực không được để trống');
    }
    if (!RegExp(r'^\d{6}$').hasMatch(newPin)) {
      throw ApiException(
          'VALIDATION_ERROR', 'Mã PIN mới phải gồm đúng 6 chữ số');
    }
    _supervisorPin = newPin;
    await _delay(null);
  }

  @override
  Future<PasswordResetResult> requestPasswordReset(String username) async {
    final clean = username.trim().toLowerCase();
    if (clean.isEmpty) {
      throw ApiException(
          'VALIDATION_ERROR', 'Tên đăng nhập không được để trống');
    }
    final allUsers = _users.isEmpty ? _seedUsers() : _users;
    final exists = allUsers.any((u) => u.username.toLowerCase() == clean);
    if (!exists) {
      throw ApiException(
          'NOT_FOUND', 'Không tìm thấy tài khoản với tên đăng nhập này.');
    }
    return _delay(PasswordResetResult(
      username: username.trim(),
      message: 'Mã xác thực OTP đã được tạo cho tài khoản ${username.trim()}.',
      otpDemo: '123456',
      expiresInSeconds: 900,
    ));
  }

  @override
  Future<void> resetPassword({
    required String username,
    required String otp,
    required String newPassword,
  }) async {
    if (otp.trim() != '123456') {
      throw ApiException(
          'BAD_REQUEST', 'Mã xác thực OTP không chính xác hoặc đã hết hạn.');
    }
    if (newPassword.length < 6) {
      throw ApiException(
          'VALIDATION_ERROR', 'Mật khẩu mới phải có ít nhất 6 ký tự.');
    }
    await _delay(null);
  }

  @override
  Future<AppUser> updateProfile({
    required String displayName,
    String? email,
    String? phoneNumber,
    String? branch,
    String? avatarUrl,
  }) async {
    if (displayName.trim().isEmpty) {
      throw ApiException('VALIDATION_ERROR', 'Họ và tên không được để trống.');
    }
    if (_users.isEmpty) _users.addAll(_seedUsers());
    final idx = _users.indexWhere((u) => u.username == 'demo_maker');
    final target = idx >= 0 ? _users[idx] : _users.first;
    final updated = target.copyWith(
      displayName: displayName.trim(),
      email: email?.trim(),
      phoneNumber: phoneNumber?.trim(),
      branch: branch?.trim(),
      avatarUrl: avatarUrl?.trim(),
    );
    if (idx >= 0) {
      _users[idx] = updated;
    }
    return _delay(updated);
  }

  // ---- inventory ----
  final _locations = <InventoryLocation>[];

  @override
  Future<List<InventoryLocation>> getLocations() async {
    if (_locations.isEmpty) _locations.addAll(_seedLocations());
    return _delay(List.of(_locations));
  }

  @override
  Future<InventoryLocation> createLocation({
    required String code,
    required String name,
    String? address,
  }) async {
    if (_locations.isEmpty) _locations.addAll(_seedLocations());
    final loc = InventoryLocation(
      id: 'loc-000${_locations.length + 1}',
      code: code,
      name: name,
    );
    _locations.add(loc);
    return _delay(loc);
  }

  @override
  Future<InventoryLocation> updateLocation({
    required String id,
    String? name,
  }) async {
    final idx = _locations.indexWhere((l) => l.id == id);
    if (idx < 0) throw ApiException('NOT_FOUND', 'Không tìm thấy điểm lưu trữ');
    final cur = _locations[idx];
    _locations[idx] = InventoryLocation(
      id: cur.id,
      code: cur.code,
      name: name ?? cur.name,
    );
    return _delay(_locations[idx]);
  }

  @override
  Future<void> deleteLocation(String id) async {
    _locations.removeWhere((l) => l.id == id);
    return _delay(null);
  }

  final _items = <InventoryItem>[];
  bool _itemsInitialized = false;

  void _ensureItemsInitialized() {
    if (!_itemsInitialized) {
      _itemsInitialized = true;
      _items.addAll(_seedItems());
    }
  }

  @override
  Future<List<InventoryItem>> getItems() async {
    _ensureItemsInitialized();
    return _delay(List.of(_items));
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
    _ensureItemsInitialized();
    final itm = InventoryItem(
      id: 'itm-000${_items.length + 1}',
      sku: sku,
      name: name,
      unit: unit,
      trackedSerial: trackedSerial,
      category: category,
      packaging: packaging,
      costPrice: costPrice,
      sellingPrice: sellingPrice,
      minStock: minStock,
    );
    _items.add(itm);
    return _delay(itm);
  }

  @override
  Future<BatchItemImportResult> createItemsBatch(
    List<Map<String, dynamic>> items,
  ) async {
    _ensureItemsInitialized();
    final existingSkus = _items.map((i) => i.sku.toUpperCase()).toSet();
    final createdList = <InventoryItem>[];
    var skipped = 0;

    for (final it in items) {
      final sku = (it['sku'] ?? '').toString().trim().toUpperCase();
      final name = (it['name'] ?? '').toString().trim();
      final unit = (it['unit'] ?? 'đơn vị').toString().trim();
      final category = it['category']?.toString();
      final packaging = it['packaging']?.toString();
      final trackedSerial = it['tracked_serial'] == true;
      final costPrice = it['cost_price'] is num ? (it['cost_price'] as num).toDouble() : null;
      final sellingPrice = it['selling_price'] is num ? (it['selling_price'] as num).toDouble() : null;
      final minStock = it['min_stock'] is num ? (it['min_stock'] as num).toDouble() : null;

      if (sku.isEmpty || name.isEmpty || existingSkus.contains(sku)) {
        skipped++;
        continue;
      }

      existingSkus.add(sku);
      final newItem = InventoryItem(
        id: 'itm-000${_items.length + 1}',
        sku: sku,
        name: name,
        unit: unit.isEmpty ? 'đơn vị' : unit,
        trackedSerial: trackedSerial,
        category: category,
        packaging: packaging,
        costPrice: costPrice,
        sellingPrice: sellingPrice,
        minStock: minStock,
      );
      _items.add(newItem);
      createdList.add(newItem);
    }

    return _delay(BatchItemImportResult(
      createdCount: createdList.length,
      skippedCount: skipped,
      items: createdList,
    ));
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
    final idx = _items.indexWhere((i) => i.id == id);
    if (idx < 0) throw ApiException('NOT_FOUND', 'Không tìm thấy vật tư');
    final cur = _items[idx];
    _items[idx] = InventoryItem(
      id: cur.id,
      sku: cur.sku,
      name: name ?? cur.name,
      unit: unit ?? cur.unit,
      trackedSerial: trackedSerial ?? cur.trackedSerial,
      category: category ?? cur.category,
      packaging: packaging ?? cur.packaging,
      costPrice: costPrice ?? cur.costPrice,
      sellingPrice: sellingPrice ?? cur.sellingPrice,
      minStock: minStock ?? cur.minStock,
    );
    return _delay(_items[idx]);
  }

  @override
  Future<void> deleteItem(String id) async {
    _ensureItemsInitialized();
    _items.removeWhere((i) => i.id == id);
    return _delay(null);
  }

  @override
  Future<void> deleteItemsBatch(List<String> itemIds) async {
    _ensureItemsInitialized();
    final idSet = itemIds.toSet();
    _items.removeWhere((i) => idSet.contains(i.id));
    return _delay(null);
  }

  final _balances = <StockBalance>[];
  bool _balancesInitialized = false;

  void _ensureBalancesInitialized() {
    if (!_balancesInitialized) {
      _balancesInitialized = true;
      _balances.addAll(_seedBalances());
    }
  }

  @override
  Future<List<StockBalance>> getBalances({String? locationId}) {
    _ensureBalancesInitialized();
    return _delay(_balances
        .where((b) => locationId == null || b.locationId == locationId)
        .toList());
  }

  @override
  Future<void> resetStoreData({bool keepCatalog = true}) async {
    _stockRequests.clear();
    _stocktakes.clear();
    _assetLogs.clear();
    _assets.clear();
    _events.clear();
    _cashRequests.clear();
    if (!keepCatalog) {
      _items.clear();
      _itemsInitialized = true;
      _balances.clear();
      _balancesInitialized = true;
    } else {
      _ensureBalancesInitialized();
      _balances.clear();
      _ensureItemsInitialized();
      for (final it in _items) {
        _balances.add(StockBalance(
          locationId: 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbb1',
          itemId: it.id,
          quantity: '0',
          reservedQuantity: '0',
          availableQuantity: '0',
        ));
      }
    }
    return _delay(null);
  }

  static AssetStatus _assetStatus(String raw) {
    for (final s in AssetStatus.values) {
      if (s.name == raw) return s;
    }
    return AssetStatus.available;
  }

  final _assets = <AssetRecord>[];
  final _assetLogs = <AssetLogItem>[];

  @override
  Future<List<AssetRecord>> getAssets({String? locationId}) {
    if (_assets.isEmpty) _assets.addAll(_seedAssets());
    return _delay(_assets
        .where((a) => locationId == null || a.locationId == locationId)
        .toList());
  }

  @override
  Future<List<AssetLogItem>> getAssetHistory(String assetId) async {
    if (_assets.isEmpty) _assets.addAll(_seedAssets());
    if (_assetLogs.isEmpty) _assetLogs.addAll(_seedAssetLogs());
    final asset = _assets.firstWhere(
      (a) => a.id == assetId || a.serial == assetId,
      orElse: () => _assets.first,
    );
    final logs = _assetLogs.where((l) => l.serial == asset.serial).toList();
    return _delay(logs);
  }

  @override
  Future<void> handoverAsset(
    String assetId, {
    String? toLocationId,
    String? toAssignee,
    String? status,
    String? notes,
  }) async {
    if (_assets.isEmpty) _assets.addAll(_seedAssets());
    if (_assetLogs.isEmpty) _assetLogs.addAll(_seedAssetLogs());
    final idx =
        _assets.indexWhere((a) => a.id == assetId || a.serial == assetId);
    if (idx < 0) throw ApiException('NOT_FOUND', 'Không tìm thấy nguyên liệu');
    final cur = _assets[idx];
    final newStatus = status != null ? _assetStatus(status) : cur.status;
    _assets[idx] = AssetRecord(
      id: cur.id,
      serial: cur.serial,
      itemId: cur.itemId,
      locationId: toLocationId ?? cur.locationId,
      status: newStatus,
      assignee: toAssignee ?? cur.assignee,
    );
    _assetLogs.insert(
      0,
      AssetLogItem(
        id: 'log-${_assetLogs.length + 1}',
        serial: cur.serial,
        fromLocationId: cur.locationId,
        toLocationId: toLocationId ?? cur.locationId,
        fromAssignee: cur.assignee,
        toAssignee: toAssignee ?? cur.assignee,
        statusBefore: cur.status.name,
        statusAfter: newStatus.name,
        actorName: 'Trần Văn Quản Lý',
        notes: notes,
        createdAt: DateTime.now().toUtc(),
      ),
    );
    return _delay(null);
  }

  @override
  Future<List<StockMovement>> getMovements({String? itemId}) =>
      _delay(_seedMovements()
          .where((m) => itemId == null || m.itemId == itemId)
          .toList());

  final _stockRequests = <StockRequest>[];
  final _stockLevels = <StockLevelItem>[];
  final _stocktakes = <StocktakeItem>[];

  void _ensureStockLevelsSeeded() {
    if (_stockLevels.isNotEmpty) return;
    const locId = 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbb1';
    _stockLevels.addAll([
      const StockLevelItem(
          id: 'sl-1',
          locationId: locId,
          itemId: 'cccccccc-cccc-4ccc-8ccc-ccccccccccc1',
          minQty: '30',
          maxQty: '300'),
      const StockLevelItem(
          id: 'sl-2',
          locationId: locId,
          itemId: 'cccccccc-cccc-4ccc-8ccc-ccccccccccc2',
          minQty: '20',
          maxQty: '200'),
      const StockLevelItem(
          id: 'sl-3',
          locationId: locId,
          itemId: 'cccccccc-cccc-4ccc-8ccc-ccccccccccc3',
          minQty: '20',
          maxQty: '200'),
      const StockLevelItem(
          id: 'sl-4',
          locationId: locId,
          itemId: 'cccccccc-cccc-4ccc-8ccc-ccccccccccc4',
          minQty: '15',
          maxQty: '100'),
      const StockLevelItem(
          id: 'sl-5',
          locationId: locId,
          itemId: 'cccccccc-cccc-4ccc-8ccc-ccccccccccc5',
          minQty: '24',
          maxQty: '150'),
      const StockLevelItem(
          id: 'sl-6',
          locationId: locId,
          itemId: 'cccccccc-cccc-4ccc-8ccc-cccccccccc19',
          minQty: '100',
          maxQty: '1000'),
      const StockLevelItem(
          id: 'sl-7',
          locationId: locId,
          itemId: 'cccccccc-cccc-4ccc-8ccc-cccccccccc20',
          minQty: '100',
          maxQty: '1000'),
      const StockLevelItem(
          id: 'sl-8',
          locationId: locId,
          itemId: 'cccccccc-cccc-4ccc-8ccc-cccccccccc21',
          minQty: '50',
          maxQty: '500'),
    ]);
  }

  void _ensureStocktakesSeeded() {
    if (_stocktakes.isNotEmpty) return;
    final today = DateTime.now().toIso8601String().substring(0, 10);
    final morningLines = [
      const StocktakeLineItem(
        id: 'stl-seed-1',
        itemId: 'cccccccc-cccc-4ccc-8ccc-ccccccccccc1',
        bookQty: '250',
        countedQty: '245',
        variance: '0',
        openingQty: '250',
        receivedQty: '0',
        usedQty: '5',
        theoreticalQty: '245',
        reason: 'Khớp định mức pha chế ca sáng',
      ),
      const StocktakeLineItem(
        id: 'stl-seed-2',
        itemId: 'cccccccc-cccc-4ccc-8ccc-ccccccccccc2',
        bookQty: '1000',
        countedQty: '992',
        variance: '0',
        openingQty: '1000',
        receivedQty: '0',
        usedQty: '8',
        theoreticalQty: '992',
        reason: 'Khớp định mức pha chế ca sáng',
      ),
      const StocktakeLineItem(
        id: 'stl-seed-3',
        itemId: 'cccccccc-cccc-4ccc-8ccc-ccccccccccc3',
        bookQty: '500',
        countedQty: '494',
        variance: '0',
        openingQty: '500',
        receivedQty: '0',
        usedQty: '6',
        theoreticalQty: '494',
        reason: 'Khớp định mức pha chế ca sáng',
      ),
      const StocktakeLineItem(
        id: 'stl-seed-4',
        itemId: 'cccccccc-cccc-4ccc-8ccc-cccccccccc19',
        bookQty: '200',
        countedQty: '168',
        variance: '-2',
        openingQty: '200',
        receivedQty: '0',
        usedQty: '30',
        theoreticalQty: '170',
        reason: 'Làm rơi vỡ 2 ly trong ca',
      ),
    ];
    _stocktakes.add(
      StocktakeItem(
        id: 'st-seed-morning',
        locationId: 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbb1',
        status: 'closed',
        note: 'Chốt tồn Ca Sáng (07:30 - 15:00)',
        makerId: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1',
        approverId: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa7',
        adjustmentRequestId: 'sr-adj-seed-01',
        createdAt: DateTime.now().subtract(const Duration(hours: 4)).toUtc(),
        completedAt: DateTime.now().subtract(const Duration(hours: 3)).toUtc(),
        lines: morningLines,
        shiftCode: 'morning',
        businessDate: today,
      ),
    );
  }

  @override
  Future<List<StockLevelItem>> getStockLevels(
      {String? locationId, String? itemId}) async {
    _ensureStockLevelsSeeded();
    return _delay(_stockLevels.where((l) {
      if (locationId != null && l.locationId != locationId) return false;
      if (itemId != null && l.itemId != itemId) return false;
      return true;
    }).toList());
  }

  @override
  Future<StockLevelItem> putStockLevel({
    required String locationId,
    required String itemId,
    required String minQty,
    String? maxQty,
  }) async {
    _ensureStockLevelsSeeded();
    final idx = _stockLevels
        .indexWhere((l) => l.locationId == locationId && l.itemId == itemId);
    final item = StockLevelItem(
      id: idx >= 0 ? _stockLevels[idx].id : 'sl-${_stockLevels.length + 1}',
      locationId: locationId,
      itemId: itemId,
      minQty: minQty,
      maxQty: maxQty,
    );
    if (idx >= 0) {
      _stockLevels[idx] = item;
    } else {
      _stockLevels.add(item);
    }
    return _delay(item);
  }

  @override
  Future<List<LowStockAlertItem>> getLowStockAlerts(
      {String? locationId}) async {
    _ensureStockLevelsSeeded();
    final alerts = <LowStockAlertItem>[];
    final balances = await getBalances(locationId: locationId);
    final items = await getItems();
    final locs = await getLocations();

    for (final level in _stockLevels) {
      if (locationId != null && level.locationId != locationId) continue;
      final bal = balances.firstWhere(
        (b) => b.locationId == level.locationId && b.itemId == level.itemId,
        orElse: () => StockBalance(
            locationId: level.locationId, itemId: level.itemId, quantity: '0'),
      );
      final cur = double.tryParse(bal.quantity) ?? 0.0;
      final min = double.tryParse(level.minQty) ?? 0.0;
      if (cur < min) {
        final loc = locs.firstWhere((l) => l.id == level.locationId,
            orElse: () => InventoryLocation(
                id: level.locationId, code: 'LOC', name: 'Kho'));
        final it = items.firstWhere((i) => i.id == level.itemId,
            orElse: () => InventoryItem(
                id: level.itemId,
                sku: 'ITEM',
                name: 'Mặt hàng',
                unit: 'cái',
                trackedSerial: false));
        final deficit = (min - cur).toStringAsFixed(0);
        alerts.add(LowStockAlertItem(
          locationId: level.locationId,
          locationCode: loc.code,
          locationName: loc.name,
          itemId: level.itemId,
          sku: it.sku,
          itemName: it.name,
          unit: it.unit,
          currentQty: cur.toStringAsFixed(0),
          minQty: level.minQty,
          maxQty: level.maxQty,
          status: cur <= 0 ? 'empty' : 'low',
          deficit: deficit,
          suggestedAction:
              'Bổ sung tối thiểu $deficit ${it.unit} cho kho ${loc.name}',
        ));
      }
    }
    return _delay(alerts);
  }

  @override
  Future<List<StocktakeItem>> getStocktakes({String? locationId}) async {
    _ensureStocktakesSeeded();
    return _delay(_stocktakes
        .where((s) => locationId == null || s.locationId == locationId)
        .toList());
  }

  @override
  Future<StocktakeItem> getStocktake(String id) async {
    _ensureStocktakesSeeded();
    final st = _stocktakes.firstWhere((s) => s.id == id,
        orElse: () =>
            throw ApiException('NOT_FOUND', 'Không tìm thấy đợt kiểm kê'));
    return _delay(st);
  }

  @override
  Future<StocktakeItem> createStocktake({
    required String locationId,
    String? note,
    String? shiftCode,
    String? businessDate,
    String? idempotencyKey,
  }) async {
    _ensureStocktakesSeeded();
    final items = await getItems();
    final balances = await getBalances(locationId: locationId);
    final balMap = {
      for (final b in balances) b.itemId: double.tryParse(b.quantity) ?? 0.0
    };

    final prevSt = _stocktakes.cast<StocktakeItem?>().firstWhere(
          (s) =>
              s != null &&
              s.locationId == locationId &&
              (s.status == 'submitted' || s.status == 'closed'),
          orElse: () => null,
        );
    final prevCounted = <String, double>{};
    if (prevSt != null) {
      for (final l in prevSt.lines) {
        prevCounted[l.itemId] = double.tryParse(l.countedQty) ?? 0.0;
      }
    }

    final lineItems = <StocktakeLineItem>[];
    for (var i = 0; i < items.length; i++) {
      final it = items[i];
      final opening = prevCounted[it.id] ?? balMap[it.id] ?? 0.0;
      final openingStr = opening == opening.roundToDouble()
          ? opening.toInt().toString()
          : opening.toStringAsFixed(1);
      lineItems.add(StocktakeLineItem(
        id: 'stl-new-$i',
        itemId: it.id,
        bookQty: openingStr,
        countedQty: openingStr,
        variance: '0',
        openingQty: openingStr,
        receivedQty: '0',
        usedQty: '0',
        theoreticalQty: openingStr,
        reason: '',
      ));
    }

    final st = StocktakeItem(
      id: 'st-${_stocktakes.length + 1}',
      locationId: locationId,
      status: 'open',
      note: note,
      makerId: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1',
      createdAt: DateTime.now().toUtc(),
      lines: lineItems,
      shiftCode: shiftCode,
      businessDate: businessDate ?? DateTime.now().toIso8601String().substring(0, 10),
    );
    _stocktakes.insert(0, st);
    return _delay(st);
  }

  @override
  Future<StocktakeItem> updateStocktakeLines(
      String id, List<Map<String, dynamic>> lines,
      {String? idempotencyKey, int? expectedVersion}) async {
    final idx = _stocktakes.indexWhere((s) => s.id == id);
    if (idx < 0) throw ApiException('NOT_FOUND', 'Không tìm thấy đợt kiểm kê');
    final st = _stocktakes[idx];
    if (expectedVersion != null && expectedVersion != st.version) {
      throw ApiException('VERSION_CONFLICT', 'Phiên kiểm kê đã thay đổi');
    }
    final balances = await getBalances(locationId: st.locationId);

    final lineItems = <StocktakeLineItem>[];
    for (var i = 0; i < lines.length; i++) {
      final l = lines[i];
      final itemId = l['item_id']?.toString() ?? '';
      final bal = balances.firstWhere((b) => b.itemId == itemId,
          orElse: () => StockBalance(
              locationId: st.locationId, itemId: itemId, quantity: '0'));
      final book = double.tryParse(bal.quantity) ?? 0.0;
      final opening =
          double.tryParse(l['opening_qty']?.toString() ?? '$book') ?? book;
      final received =
          double.tryParse(l['received_qty']?.toString() ?? '0') ?? 0.0;
      final used = double.tryParse(l['used_qty']?.toString() ?? '0') ?? 0.0;
      final theoretical = opening + received - used;
      final counted =
          double.tryParse(l['counted_qty']?.toString() ?? '0') ?? 0.0;
      final expected = st.shiftCode == null ? book : theoretical;
      final diff = counted - expected;
      lineItems.add(StocktakeLineItem(
        id: 'stl-$i',
        itemId: itemId,
        bookQty: expected.toStringAsFixed(0),
        countedQty: counted.toStringAsFixed(0),
        variance: diff.toStringAsFixed(0),
        openingQty: opening.toStringAsFixed(0),
        receivedQty: received.toStringAsFixed(0),
        usedQty: used.toStringAsFixed(0),
        theoreticalQty: theoretical.toStringAsFixed(0),
        reason: l['reason']?.toString(),
      ));
    }
    final updated = StocktakeItem(
      id: st.id,
      locationId: st.locationId,
      status: st.status,
      note: st.note,
      makerId: st.makerId,
      approverId: st.approverId,
      adjustmentRequestId: st.adjustmentRequestId,
      createdAt: st.createdAt,
      completedAt: st.completedAt,
      lines: lineItems,
      shiftCode: st.shiftCode,
      businessDate: st.businessDate,
      version: st.version + 1,
    );
    _stocktakes[idx] = updated;
    return _delay(updated);
  }

  @override
  Future<StocktakeItem> submitStocktake(String id,
      {String? idempotencyKey, int? expectedVersion}) async {
    final idx = _stocktakes.indexWhere((s) => s.id == id);
    if (idx < 0) throw ApiException('NOT_FOUND', 'Không tìm thấy đợt kiểm kê');
    final st = _stocktakes[idx];
    if (expectedVersion != null && expectedVersion != st.version) {
      throw ApiException('VERSION_CONFLICT', 'Phiên kiểm kê đã thay đổi');
    }
    final updated = StocktakeItem(
      id: st.id,
      locationId: st.locationId,
      status: 'submitted',
      note: st.note,
      makerId: st.makerId,
      approverId: st.approverId,
      adjustmentRequestId: st.adjustmentRequestId,
      createdAt: st.createdAt,
      completedAt: st.completedAt,
      lines: st.lines,
      shiftCode: st.shiftCode,
      businessDate: st.businessDate,
      version: st.version + 1,
    );
    _stocktakes[idx] = updated;
    return _delay(updated);
  }

  @override
  Future<StocktakeItem> approveStocktake(String id) async {
    final idx = _stocktakes.indexWhere((s) => s.id == id);
    if (idx < 0) throw ApiException('NOT_FOUND', 'Không tìm thấy đợt kiểm kê');
    final st = _stocktakes[idx];
    final hasVariance =
        st.lines.any((l) => (double.tryParse(l.variance) ?? 0.0) != 0.0);
    String? adjReqId;
    if (hasVariance) {
      adjReqId = 'sr-adj-${DateTime.now().millisecondsSinceEpoch}';
    }

    // Tự động cân bằng tồn kho thực tế vào sổ cái
    _ensureBalancesInitialized();
    for (final l in st.lines) {
      final counted = double.tryParse(l.countedQty) ?? 0.0;
      final countedStr = counted == counted.roundToDouble()
          ? counted.toInt().toString()
          : counted.toStringAsFixed(1);
      final bIdx = _balances.indexWhere(
          (b) => b.locationId == st.locationId && b.itemId == l.itemId);
      if (bIdx >= 0) {
        _balances[bIdx] = StockBalance(
          locationId: st.locationId,
          itemId: l.itemId,
          quantity: countedStr,
        );
      } else {
        _balances.add(StockBalance(
          locationId: st.locationId,
          itemId: l.itemId,
          quantity: countedStr,
        ));
      }
    }

    final updated = StocktakeItem(
      id: st.id,
      locationId: st.locationId,
      status: 'closed',
      note: st.note,
      makerId: st.makerId,
      approverId: 'u_checker',
      adjustmentRequestId: adjReqId,
      createdAt: st.createdAt,
      completedAt: DateTime.now().toUtc(),
      lines: st.lines,
      shiftCode: st.shiftCode,
      businessDate: st.businessDate,
      version: st.version + 1,
    );
    _stocktakes[idx] = updated;
    _approvalStreamCtrl.add('processed:$id');
    return _delay(updated);
  }

  @override
  Future<StocktakeItem> rejectStocktake(String id, {String? reason}) async {
    final idx = _stocktakes.indexWhere((s) => s.id == id);
    if (idx < 0) throw ApiException('NOT_FOUND', 'Không tìm thấy đợt kiểm kê');
    final st = _stocktakes[idx];
    final noteWithReason = '${st.note ?? ""} [Từ chối: ${reason ?? "Yêu cầu kiểm đếm lại"}]'.trim();
    final updated = StocktakeItem(
      id: st.id,
      locationId: st.locationId,
      status: 'open',
      note: noteWithReason,
      makerId: st.makerId,
      createdAt: st.createdAt,
      lines: st.lines,
      shiftCode: st.shiftCode,
      businessDate: st.businessDate,
      version: st.version + 1,
    );
    _stocktakes[idx] = updated;
    _approvalStreamCtrl.add('processed:$id');
    return _delay(updated);
  }

  @override
  Future<List<StockRequest>> getStockRequests() async {
    if (_stockRequests.isEmpty) _stockRequests.addAll(_seedStockRequests());
    return _delay(List.of(_stockRequests));
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
    if (_stockRequests.isEmpty) _stockRequests.addAll(_seedStockRequests());
    final nextNum = _stockRequests.fold<int>(0, (maxId, r) {
      final numPart = int.tryParse(r.id.replaceAll(RegExp(r'[^\d]'), '')) ?? 0;
      return numPart > maxId ? numPart : maxId;
    }) + 1;
    final created = StockRequest(
      id: 'sr-${nextNum.toString().padLeft(4, '0')}',
      kind: kind,
      status: RequestStatus.draft,
      version: 1,
      createdBy: '00000000-0000-4000-8000-000000000001',
      createdByName: 'Bình Tân (Chủ Quán / Admin)',
      locationId: sourceLocationId ??
          destLocationId ??
          'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbb1',
      items: lines,
      reason: reason ?? '',
      createdAt: DateTime.now().toUtc(),
      destinationLocationId: destLocationId,
      supplier: supplier ?? supplierName,
      supplierName: supplierName ?? supplier,
      invoiceNo: invoiceNo,
      subKind: subKind,
    );
    _stockRequests.insert(0, created);
    return _delay(created);
  }

  @override
  Future<void> deleteStockRequest(String id) async {
    final idx = _stockRequests.indexWhere((r) => r.id == id);
    if (idx < 0) throw ApiException('NOT_FOUND', 'Không tìm thấy phiếu');
    if (_stockRequests[idx].status != RequestStatus.draft) {
      throw ApiException(
          'CANNOT_DELETE', 'Chỉ có thể xoá phiếu ở trạng thái nháp');
    }
    _stockRequests.removeAt(idx);
    return _delay(null);
  }

  @override
  Future<StockRequest> submitStockRequest(String id) =>
      _transitionStock(id, RequestStatus.pending);

  @override
  Future<StockRequest> approveStockRequest(String id, {String? supervisorPin}) {
    if (supervisorPin != null && supervisorPin != _supervisorPin) {
      throw ApiException('FORBIDDEN', 'Mã PIN kiểm soát viên không đúng.');
    }
    return _transitionStock(id, RequestStatus.posted);
  }

  @override
  Future<StockRequest> rejectStockRequest(String id, String reason) =>
      _transitionStock(id, RequestStatus.rejected, reason: reason);

  @override
  Future<StockRequest> returnStockRequest(String id,
          {required String reason}) =>
      _transitionStock(id, RequestStatus.returned, reason: reason);

  Future<StockRequest> _transitionStock(String id, RequestStatus to,
      {String? reason}) async {
    final idx = _stockRequests.indexWhere((r) => r.id == id);
    if (idx < 0) throw ApiException('NOT_FOUND', 'Không tìm thấy phiếu');
    final r = _stockRequests[idx];
    if (r.status.isFinal) {
      throw ApiException('INVALID_STATE', 'Phiếu đã chốt trạng thái');
    }
    _stockRequests[idx] = _copyStock(r, to, reason: reason);
    if (to == RequestStatus.posted) {
      _ensureBalancesInitialized();
      final targetLoc = r.kind == RequestKind.receipt
          ? (r.destinationLocationId ?? r.locationId)
          : r.locationId;
      for (final line in r.items) {
        final qty = double.tryParse(line.quantity) ?? 0.0;
        final bIdx = _balances.indexWhere(
            (b) => b.locationId == targetLoc && b.itemId == line.itemId);
        if (bIdx >= 0) {
          final cur = double.tryParse(_balances[bIdx].quantity) ?? 0.0;
          final updated = r.kind == RequestKind.receipt ? cur + qty : cur - qty;
          final val = updated < 0 ? 0.0 : updated;
          final valStr = val == val.roundToDouble()
              ? val.toInt().toString()
              : val.toStringAsFixed(1);
          _balances[bIdx] = StockBalance(
            locationId: targetLoc,
            itemId: line.itemId,
            quantity: valStr,
          );
        } else if (r.kind == RequestKind.receipt) {
          final qtyStr = qty == qty.roundToDouble()
              ? qty.toInt().toString()
              : qty.toStringAsFixed(1);
          _balances.add(StockBalance(
            locationId: targetLoc,
            itemId: line.itemId,
            quantity: qtyStr,
          ));
        }

        // Nếu là chuyển kho, cộng tồn vào kho đích
        if (r.subKind == 'transfer' && r.destinationLocationId != null) {
          final dstLoc = r.destinationLocationId!;
          final dstIdx = _balances.indexWhere(
              (b) => b.locationId == dstLoc && b.itemId == line.itemId);
          if (dstIdx >= 0) {
            final curDst = double.tryParse(_balances[dstIdx].quantity) ?? 0.0;
            final updatedDst = curDst + qty;
            final valStr = updatedDst == updatedDst.roundToDouble()
                ? updatedDst.toInt().toString()
                : updatedDst.toStringAsFixed(1);
            _balances[dstIdx] = StockBalance(
              locationId: dstLoc,
              itemId: line.itemId,
              quantity: valStr,
            );
          } else {
            final qtyStr = qty == qty.roundToDouble()
                ? qty.toInt().toString()
                : qty.toStringAsFixed(1);
            _balances.add(StockBalance(
              locationId: dstLoc,
              itemId: line.itemId,
              quantity: qtyStr,
            ));
          }
        }

        // Cập nhật ca kiểm kê đang mở (nếu có)
        for (var i = 0; i < _stocktakes.length; i++) {
          final st = _stocktakes[i];
          if (st.status != 'open') continue;
          final isReceiptTarget = (r.kind == RequestKind.receipt && st.locationId == targetLoc) ||
              (r.subKind == 'transfer' && st.locationId == r.destinationLocationId);
          final isOutboundTarget = (r.kind == RequestKind.payment || r.kind == RequestKind.transfer)
              ? st.locationId == targetLoc
              : false;

          if (isReceiptTarget || isOutboundTarget) {
            final linesCopy = List<StocktakeLineItem>.from(st.lines);
            final lineIdx = linesCopy.indexWhere((stl) => stl.itemId == line.itemId);
            if (lineIdx >= 0) {
              final stl = linesCopy[lineIdx];
              final op = double.tryParse(stl.openingQty) ?? 0.0;
              var rec = double.tryParse(stl.receivedQty) ?? 0.0;
              var used = double.tryParse(stl.usedQty) ?? 0.0;
              final counted = double.tryParse(stl.countedQty) ?? 0.0;

              if (isReceiptTarget) {
                rec += qty;
              }
              if (isOutboundTarget) {
                used += qty;
              }

              final theo = op + rec - used;
              final recStr = rec == rec.roundToDouble() ? rec.toInt().toString() : rec.toStringAsFixed(1);
              final usedStr = used == used.roundToDouble() ? used.toInt().toString() : used.toStringAsFixed(1);
              final theoStr = theo == theo.roundToDouble() ? theo.toInt().toString() : theo.toStringAsFixed(1);
              final varVal = counted - theo;
              final varStr = varVal == varVal.roundToDouble() ? varVal.toInt().toString() : varVal.toStringAsFixed(1);
              linesCopy[lineIdx] = StocktakeLineItem(
                id: stl.id,
                itemId: stl.itemId,
                bookQty: theoStr,
                countedQty: stl.countedQty,
                variance: varStr,
                openingQty: stl.openingQty,
                receivedQty: recStr,
                usedQty: usedStr,
                theoreticalQty: theoStr,
                reason: stl.reason,
              );
              _stocktakes[i] = StocktakeItem(
                id: st.id,
                locationId: st.locationId,
                status: st.status,
                note: st.note,
                makerId: st.makerId,
                createdAt: st.createdAt,
                completedAt: st.completedAt,
                lines: linesCopy,
                shiftCode: st.shiftCode,
                businessDate: st.businessDate,
              );
            }
          }
        }
      }
    }
    if (to == RequestStatus.pending) {
      _approvalStreamCtrl.add('new_request:$id:kho');
    } else {
      _approvalStreamCtrl.add('processed:$id');
    }
    return _delay(_stockRequests[idx]);
  }

  StockRequest _copyStock(StockRequest r, RequestStatus to, {String? reason}) =>
      StockRequest(
        id: r.id,
        kind: r.kind,
        status: to,
        version: r.version + 1,
        createdBy: r.createdBy,
        createdByName: r.createdByName,
        locationId: r.locationId,
        items: r.items,
        reason: r.reason,
        createdAt: r.createdAt,
        approvedBy: to == RequestStatus.posted
            ? 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa2'
            : r.approvedBy,
        approvedByName: to == RequestStatus.posted
            ? 'Trần Văn Quản Lý'
            : r.approvedByName,
        rejectReason: to == RequestStatus.rejected
            ? (reason ?? r.rejectReason)
            : r.rejectReason,
        returnReason: to == RequestStatus.returned
            ? (reason ?? r.returnReason)
            : r.returnReason,
        destinationLocationId: r.destinationLocationId,
        supplier: r.supplier,
        supplierName: r.supplierName,
        invoiceNo: r.invoiceNo,
        subKind: r.subKind,
        receivedAt: r.receivedAt,
      );

  // ---- cash sim ----
  final _cashboxes = <Cashbox>[];

  @override
  Future<List<Cashbox>> getCashboxes() async {
    if (_cashboxes.isEmpty) _cashboxes.addAll(_seedCashboxes());
    return _delay(List.of(_cashboxes));
  }

  @override
  Future<Cashbox> createCashbox({
    required String code,
    required String name,
    String currency = 'VND',
    String openingBalance = '0.00',
  }) async {
    if (_cashboxes.isEmpty) _cashboxes.addAll(_seedCashboxes());
    final box = Cashbox(
      id: 'cb-000${_cashboxes.length + 1}',
      code: code,
      name: name,
      openingBalance: openingBalance,
    );
    _cashboxes.add(box);
    return _delay(box);
  }

  List<CashBalance>? _cashBalances;
  List<CashBalance> _getCashBalancesList() {
    return _cashBalances ??= List.of(_seedCashBalances());
  }

  @override
  Future<Cashbox> updateCashbox({
    required String id,
    String? name,
    bool? active,
  }) async {
    // KHÔNG có đường ghi số dư trực tiếp (giống backend 422
    // DIRECT_BALANCE_WRITE_FORBIDDEN): số dư chỉ đổi qua phiếu điều chỉnh.
    final idx = _cashboxes.indexWhere((b) => b.id == id);
    if (idx < 0) throw ApiException('NOT_FOUND', 'Không tìm thấy két sắt');
    final cur = _cashboxes[idx];
    _cashboxes[idx] = Cashbox(
      id: cur.id,
      code: cur.code,
      name: name ?? cur.name,
      openingBalance: cur.openingBalance,
    );
    return _delay(_cashboxes[idx]);
  }

  @override
  Future<CashRequest> createCashAdjustmentRequest({
    required String cashboxId,
    required String amount,
    required bool increase,
    String? reason,
  }) async {
    // Phiếu điều chỉnh luôn đi qua flow draft -> submit -> duyệt; số dư
    // KHÔNG đổi ngay khi tạo phiếu (giống backend).
    return createCashRequest(
      cashboxId: cashboxId,
      kind: increase ? RequestKind.receipt : RequestKind.adjustment,
      amount: amount,
      reason: reason,
    );
  }

  @override
  Future<void> deleteCashbox(String id) async {
    _cashboxes.removeWhere((b) => b.id == id);
    return _delay(null);
  }

  @override
  Future<List<CashBalance>> getCashBalances() => _delay(List.of(_getCashBalancesList()));

  List<JournalEntry>? _journals;

  List<JournalEntry> _getJournalsList() =>
      _journals ??= List.of(_seedJournals());

  @override
  Future<List<JournalEntry>> getJournals() => _delay(List.of(_getJournalsList()));

  final _cashRequests = <CashRequest>[];

  @override
  Future<List<CashRequest>> getCashRequests() async {
    if (_cashRequests.isEmpty) _cashRequests.addAll(_seedCashRequests());
    return _delay(List.of(_cashRequests));
  }

  @override
  Future<CashRequest> createCashRequest({
    required String cashboxId,
    required RequestKind kind,
    required String amount,
    String? reason,
  }) async {
    if (_cashRequests.isEmpty) _cashRequests.addAll(_seedCashRequests());
    final nextNum = _cashRequests.fold<int>(0, (maxId, r) {
      final numPart = int.tryParse(r.id.replaceAll(RegExp(r'[^\d]'), '')) ?? 0;
      return numPart > maxId ? numPart : maxId;
    }) + 1;
    final created = CashRequest(
      id: 'cr-${nextNum.toString().padLeft(4, '0')}',
      kind: kind,
      status: RequestStatus.draft,
      version: 1,
      cashboxId: cashboxId,
      amount: amount,
      currency: 'VND',
      reason: reason ?? '',
      createdBy: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1',
      createdByName: 'Nguyễn An (giả)',
      createdAt: DateTime.now().toUtc(),
    );
    _cashRequests.insert(0, created);
    return _delay(created);
  }

  @override
  Future<void> deleteCashRequest(String id) async {
    final idx = _cashRequests.indexWhere((r) => r.id == id);
    if (idx < 0) throw ApiException('NOT_FOUND', 'Không tìm thấy phiếu');
    if (_cashRequests[idx].status != RequestStatus.draft) {
      throw ApiException(
          'CANNOT_DELETE', 'Chỉ có thể xoá phiếu ở trạng thái nháp');
    }
    _cashRequests.removeAt(idx);
    return _delay(null);
  }

  @override
  Future<CashRequest> submitCashRequest(String id) =>
      _transitionCash(id, RequestStatus.pending);

  @override
  Future<CashRequest> approveCashRequest(String id, {String? supervisorPin}) async {
    if (supervisorPin != null && supervisorPin != _supervisorPin) {
      throw ApiException('FORBIDDEN', 'Mã PIN kiểm soát viên không đúng.');
    }
    final approved = await _transitionCash(id, RequestStatus.posted);
    // Số dư chỉ đổi khi phiếu ĐÃ ĐƯỢC DUYỆT (post journal) — giống backend.
    _postCashAdjustmentJournal(approved);
    return approved;
  }

  /// Post bút toán cho phiếu điều chỉnh đã duyệt (demo mode).
  ///
  /// - `kind=adjustment` -> bút toán RA quỹ (chi): số dư GIẢM.
  /// - `kind=receipt` kèm tiền tố điều chỉnh -> bút toán VÀO quỹ: số dư TĂNG.
  void _postCashAdjustmentJournal(CashRequest request) {
    final isAdjustment = request.kind == RequestKind.adjustment;
    final isIncrease =
        request.kind == RequestKind.receipt &&
        request.reason.startsWith(kCashAdjustmentReasonPrefix);
    if (!isAdjustment && !isIncrease) return;

    final amount = double.tryParse(request.amount) ?? 0;
    if (amount <= 0) return;

    final bals = _getCashBalancesList();
    final idx = bals.indexWhere((b) => b.cashboxId == request.cashboxId);
    final currency = idx >= 0 && bals[idx].currency.isNotEmpty
        ? bals[idx].currency
        : 'VND';
    final current = idx >= 0 ? (double.tryParse(bals[idx].amount) ?? 0) : 0;
    final next = isIncrease ? current + amount : current - amount;
    final entry = CashBalance(
      cashboxId: request.cashboxId,
      amount: next.toStringAsFixed(2),
      currency: currency,
    );
    if (idx >= 0) {
      bals[idx] = entry;
    } else {
      bals.add(entry);
    }

    _getJournalsList().insert(
      0,
      JournalEntry(
        id: 'je-${request.id}',
        cashboxId: request.cashboxId,
        kind: isIncrease ? 'receipt' : 'adjustment',
        amount: request.amount,
        currency: currency,
        reason: request.reason,
        createdAt: DateTime.now().toUtc(),
      ),
    );
  }

  @override
  Future<CashRequest> rejectCashRequest(String id, String reason) =>
      _transitionCash(id, RequestStatus.rejected, reason: reason);

  @override
  Future<CashRequest> returnCashRequest(String id, {required String reason}) =>
      _transitionCash(id, RequestStatus.returned, reason: reason);

  Future<CashRequest> _transitionCash(String id, RequestStatus to,
      {String? reason}) async {
    final idx = _cashRequests.indexWhere((r) => r.id == id);
    if (idx < 0) throw ApiException('NOT_FOUND', 'Không tìm thấy phiếu');
    final r = _cashRequests[idx];
    if (r.status.isFinal) {
      throw ApiException('INVALID_STATE', 'Phiếu đã chốt trạng thái');
    }
    _cashRequests[idx] = CashRequest(
      id: r.id,
      kind: r.kind,
      status: to,
      version: r.version + 1,
      cashboxId: r.cashboxId,
      amount: r.amount,
      currency: r.currency,
      reason: r.reason,
      createdBy: r.createdBy,
      createdByName: r.createdByName,
      createdAt: r.createdAt,
      approvedBy: to == RequestStatus.posted
          ? 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa2'
          : r.approvedBy,
      approvedByName: to == RequestStatus.posted
          ? 'Trần Văn Quản Lý'
          : r.approvedByName,
      rejectReason: to == RequestStatus.rejected
          ? (reason ?? r.rejectReason)
          : r.rejectReason,
      returnReason: to == RequestStatus.returned
          ? (reason ?? r.returnReason)
          : r.returnReason,
    );
    if (to == RequestStatus.pending) {
      _approvalStreamCtrl.add('new_request:$id:quỹ');
    } else {
      _approvalStreamCtrl.add('processed:$id');
    }
    return _delay(_cashRequests[idx]);
  }

  // ---- approvals / activity / integrations ----
  @override
  Future<List<ApprovalItem>> getApprovalInbox() async {
    if (_stockRequests.isEmpty) _stockRequests.addAll(_seedStockRequests());
    if (_cashRequests.isEmpty) _cashRequests.addAll(_seedCashRequests());
    final items = <ApprovalItem>[
      for (final r
          in _stockRequests.where((x) => x.status == RequestStatus.pending))
        ApprovalItem(
          id: r.id,
          kind: 'inventory',
          maker: r.createdByName,
          impact:
              'Kho (${r.kind.name}) · ${r.items.fold<num>(0, (total, line) => total + (num.tryParse(line.quantity) ?? 0))} đơn vị',
          detail: r.reason.isEmpty ? r.id : r.reason,
          approvalDetail: {
            'kind': r.kind.name,
            'total_quantity': r.items
                .fold<num>(0,
                    (total, line) => total + (num.tryParse(line.quantity) ?? 0))
                .toString(),
          },
        ),
      for (final r
          in _cashRequests.where((x) => x.status == RequestStatus.pending))
        ApprovalItem(
          id: r.id,
          kind: 'cash',
          maker: r.createdByName,
          impact:
              '${r.kind == RequestKind.payment ? '-' : '+'}${r.amount} ${r.currency}',
          detail: r.reason.isEmpty ? r.id : r.reason,
        ),
      for (final s
          in _stocktakes.where((x) => x.status == 'submitted'))
        ApprovalItem(
          id: s.id,
          kind: 'stocktake',
          maker: s.makerId == 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1'
              ? 'Nguyễn Thị Mai (Pha Chế)'
              : s.makerId,
          impact:
              'Kiểm kê ca · ${s.lines.where((l) => (double.tryParse(l.variance) ?? 0).abs() > 0.001).length} món lệch',
          detail: s.note?.isNotEmpty == true
              ? s.note!
              : 'Kiểm kê ca ngày ${s.businessDate ?? ""}',
          approvalDetail: {
            'kind': 'stocktake',
            'shift_code': s.shiftCode ?? '',
            'location_id': s.locationId,
            'variance_count': s.lines
                .where((l) => (double.tryParse(l.variance) ?? 0).abs() > 0.001)
                .length,
          },
        ),
    ];
    return _delay(items);
  }

  @override
  Future<AiRiskAssessment> assessApprovalItem(ApprovalItem item) async {
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

    String riskLevel = 'low';
    int riskScore = 20;
    final flagged = <String>[];
    final recs = <String>[];

    if (isCash) {
      if (val >= 500000000) {
        riskLevel = 'high';
        riskScore = 88;
        flagged.add(
            'Giá trị giao dịch vượt ngưỡng kiểm soát kép đặc biệt (≥ 500.000.000 VND).');
        flagged.add(
            'Bắt buộc xác thực mã PIN Kiểm soát viên (Supervisor PIN) và đóng dấu Audit Stamp SHA-256.');
        recs.add(
            'Kiểm đếm tiền mặt thực tế tại két và đối chiếu phiếu rút/nộp tiền gốc.');
        recs.add(
            'Yêu cầu xác nhận bàn giao tiền mặt giữa nhân viên và quản lý ca.');
      } else if (val >= 200000000) {
        riskLevel = 'medium';
        riskScore = 58;
        flagged.add(
            'Giao dịch giá trị trung bình lớn (200.000.000 - 500.000.000 VND).');
        recs.add(
            'Đối chiếu hóa đơn chứng từ bán hàng / nhập hàng trước khi duyệt.');
      } else {
        riskLevel = 'low';
        riskScore = 20;
        recs.add('Giao dịch trong hạn mức định mức thường lệ của quầy.');
      }
    } else {
      if (val >= 50) {
        riskLevel = 'high';
        riskScore = 85;
        flagged
            .add('Số lượng nhập/xuất nguyên liệu vượt hạn mức (≥ 50 đơn vị).');
        flagged.add(
            'Nguy cơ thất thoát hoặc hư hỏng nguyên liệu giá trị cao.');
        recs.add(
            'Kiểm tra hạn sử dụng (FEFO) và bao bì niêm phong trước khi nhận.');
      } else if (val >= 20) {
        riskLevel = 'medium';
        riskScore = 52;
        flagged.add('Số lượng nguyên liệu xuất kho trung bình (20 - 50 đơn vị).');
        recs.add('Kiểm tra kế hoạch nhập nguyên liệu định kỳ của cửa hàng.');
      } else {
        riskLevel = 'low';
        riskScore = 18;
        recs.add('Lệnh xuất nhập vật tư trong định mức ngày.');
      }
    }

    if (item.detail.trim().length < 5) {
      flagged.add(
          'Lý do giao dịch quá ngắn hoặc không nêu rõ mục đích (< 5 ký tự).');
      riskScore = min(98, riskScore + 15);
      if (riskLevel == 'low') riskLevel = 'medium';
      recs.add('Yêu cầu người tạo phiếu bổ sung diễn giải chi tiết mục đích nghiệp vụ.');
    }

    final stampSeed = '${item.id}:${item.maker}:${item.impact}:$riskScore';
    final stampBytes = utf8.encode(stampSeed);
    final auditStamp = stampBytes
        .map((b) => b.toRadixString(16).padLeft(2, '0'))
        .join()
        .padRight(64, '0')
        .substring(0, 64);

    final summary =
        'Đánh giá rủi ro: Mức độ ${riskLevel.toUpperCase()} ($riskScore/100) cho phiếu ${item.id}. '
        '${riskLevel == 'high' ? 'Cần quản lý ca kiểm tra trực tiếp.' : 'Đủ điều kiện xem xét phê duyệt.'}';

    return _delay(AiRiskAssessment(
      requestId: item.id,
      riskLevel: riskLevel,
      riskScore: riskScore,
      summary: summary,
      flaggedRules: flagged,
      recommendations: recs,
      auditStamp: auditStamp,
      assessmentSource: 'cloudflare',
    ));
  }

  final _events = <ActivityEvent>[];

  @override
  Future<List<ActivityEvent>> getActivity({String? cursor}) async {
    if (_events.isEmpty) _events.addAll(_seedActivity());
    return _delay(List.of(_events));
  }

  final _connections = <IntegrationConnection>[];

  @override
  Future<List<IntegrationConnection>> getConnections() async {
    if (_connections.isEmpty) _connections.addAll(_seedConnections());
    return _delay(List.of(_connections));
  }

  @override
  Future<IntegrationConnection> createConnection({
    required String name,
    required String type,
    String? endpoint,
    Map<String, dynamic>? config,
  }) async {
    if (_connections.isEmpty) _connections.addAll(_seedConnections());
    final conn = IntegrationConnection(
      id: 'conn-000${_connections.length + 1}',
      name: name,
      endpoint: endpoint ?? type,
      status: 'connected',
      lastTestedAt: null,
      lastError: null,
    );
    _connections.add(conn);
    return _delay(conn);
  }

  @override
  Future<IntegrationConnection> updateConnection({
    required String id,
    String? name,
    String? endpoint,
    String? status,
  }) async {
    final idx = _connections.indexWhere((c) => c.id == id);
    if (idx < 0) throw ApiException('NOT_FOUND', 'Không tìm thấy kết nối');
    final cur = _connections[idx];
    _connections[idx] = IntegrationConnection(
      id: cur.id,
      name: name ?? cur.name,
      endpoint: endpoint ?? cur.endpoint,
      status: status ?? cur.status,
      lastTestedAt: cur.lastTestedAt,
      lastError: cur.lastError,
    );
    return _delay(_connections[idx]);
  }

  @override
  Future<void> deleteConnection(String id) async {
    _connections.removeWhere((c) => c.id == id);
    return _delay(null);
  }

  @override
  Future<Map<String, dynamic>> testConnection(String id) async {
    return _delay({
      'success': true,
      'latency_ms': 45,
      'message': 'Kết nối hoạt động bình thường (mô phỏng)',
    });
  }

  final _runs = <IntegrationRun>[];
  final _stagingPreviews = <String, StagingPreview>{};

  @override
  Future<List<IntegrationRun>> getIntegrationRuns() async {
    if (_runs.isEmpty) _runs.addAll(_seedRuns());
    return _delay(List.of(_runs));
  }

  @override
  Future<StagingPreview> uploadImportFile({
    required String filename,
    required List<int> bytes,
    required String type,
  }) async {
    final text = utf8.decode(bytes, allowMalformed: true);
    final rawRows = <Map<String, dynamic>>[];
    if (type == 'json' || filename.toLowerCase().endsWith('.json')) {
      final decoded = json.decode(text);
      final list = decoded is Map && decoded['rows'] is List
          ? decoded['rows'] as List
          : (decoded is List ? decoded : const []);
      for (final item in list) {
        if (item is Map) {
          rawRows.add(item.map((k, v) => MapEntry(k.toString(), v)));
        }
      }
    } else {
      final lines = text
          .split(RegExp(r'\r?\n'))
          .where((l) => l.trim().isNotEmpty)
          .toList();
      if (lines.isNotEmpty) {
        final headers = lines.first.split(',').map((h) => h.trim()).toList();
        for (var i = 1; i < lines.length; i++) {
          final cells = lines[i].split(',').map((c) => c.trim()).toList();
          final row = <String, dynamic>{};
          for (var j = 0; j < headers.length && j < cells.length; j++) {
            row[headers[j]] = cells[j];
          }
          rawRows.add(row);
        }
      }
    }
    return _delay(_stageRows(rawRows));
  }

  @override
  Future<StagingPreview> fetchGoogleSheet({
    required String sheetId,
    String tab = 'Sheet1',
  }) async {
    if (sheetId.trim().length < 5) {
      throw ApiException('INVALID_SHEET_ID', 'sheet_id không hợp lệ');
    }
    final demoRows = <Map<String, dynamic>>[
      {
        'sku': 'TRA-DEN-SO9',
        'location_code': 'BAR-MAIN',
        'quantity': '15',
        'source_row_key': 'sheet-$sheetId-1',
      },
      {
        'sku': 'TRAN-CHAU-DEN',
        'location_code': 'KHO-TT',
        'quantity': '20',
        'source_row_key': 'sheet-$sheetId-2',
      },
    ];
    return _delay(_stageRows(demoRows));
  }

  StagingPreview _stageRows(List<Map<String, dynamic>> rawRows) {
    final validSkus = _seedItems().map((i) => i.sku).toSet();
    final validLocs = _seedLocations().map((l) => l.code).toSet();
    final staged = <StagingRow>[];
    var validCount = 0;
    var invalidCount = 0;
    for (var i = 0; i < rawRows.length; i++) {
      final r = rawRows[i];
      final errors = <String>[];
      final sku = (r['sku'] ?? r['item_sku'] ?? '').toString().trim();
      final loc = (r['location_code'] ?? r['location'] ?? '').toString().trim();
      final qty = double.tryParse((r['quantity'] ?? '').toString());
      if (sku.isEmpty) {
        errors.add('thiếu sku');
      } else if (!validSkus.contains(sku)) {
        errors.add("sku '$sku' không tồn tại");
      }
      if (loc.isEmpty) {
        errors.add('thiếu location_code');
      } else if (!validLocs.contains(loc)) {
        errors.add("location '$loc' không tồn tại");
      }
      if (qty == null || qty <= 0) {
        errors.add('quantity phải > 0');
      }
      final isValid = errors.isEmpty;
      if (isValid) {
        validCount++;
      } else {
        invalidCount++;
      }
      staged.add(StagingRow(
        rowIndex: i,
        sourceRowKey: (r['source_row_key'] ?? '$sku:$loc:$i').toString(),
        data: r,
        valid: isValid,
        errors: errors,
      ));
    }
    if (_runs.isEmpty) _runs.addAll(_seedRuns());
    final runId = 'ir-000${_runs.length + 1}';
    final preview = StagingPreview(
      runId: runId,
      validCount: validCount,
      invalidCount: invalidCount,
      rows: staged,
    );
    _stagingPreviews[runId] = preview;
    _runs.insert(
      0,
      IntegrationRun(
        id: runId,
        connectionId: 'ic-0001',
        status: 'staged',
        phase: 'staged',
        startedAt: DateTime.now().toUtc(),
        processed: validCount,
        errorCount: invalidCount,
        total: rawRows.length,
      ),
    );
    return preview;
  }

  @override
  Future<StagingPreview> getRunPreview(String runId) async {
    final preview = _stagingPreviews[runId];
    if (preview == null) {
      throw ApiException('NOT_FOUND', 'Không tìm thấy staging run $runId');
    }
    return _delay(preview);
  }

  @override
  Future<ConfirmRunResult> confirmRun(String runId) async {
    final preview = _stagingPreviews[runId];
    if (preview == null) {
      throw ApiException('NOT_FOUND', 'Không tìm thấy staging run $runId');
    }
    if (preview.invalidCount > 0) {
      throw ApiException(
        'CONFIRM_HAS_ERRORS',
        'Run còn ${preview.invalidCount} dòng lỗi — sửa nguồn rồi upload lại',
      );
    }
    if (preview.validCount == 0) {
      throw ApiException('CONFIRM_EMPTY', 'Run không có dòng hợp lệ');
    }
    if (_stockRequests.isEmpty) _stockRequests.addAll(_seedStockRequests());
    final draftId = 'sr-import-${_stockRequests.length + 1}';
    _stockRequests.insert(
      0,
      StockRequest(
        id: draftId,
        kind: RequestKind.receipt,
        status: RequestStatus.draft,
        version: 1,
        createdBy: '00000000-0000-4000-8000-000000000001',
        createdByName: 'Bình Tân (Chủ Quán / Admin)',
        locationId: 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbb1',
        items: const [
          StockRequestLine(
            itemId: 'cccccccc-cccc-4ccc-8ccc-ccccccccccc1',
            quantity: '10.000',
          ),
        ],
        reason: 'Import từ staging run $runId',
        createdAt: DateTime.now().toUtc(),
      ),
    );
    if (_events.isEmpty) _events.addAll(_seedActivity());
    _events.insert(
      0,
      ActivityEvent(
        id: 'ae-import-${_events.length + 1}',
        occurredAt: DateTime.now().toUtc(),
        subjectId: runId,
        status: 'confirmed',
        messageKey: 'integration.run.confirmed',
        processed: preview.validCount,
        total: preview.rows.length,
      ),
    );
    return _delay(ConfirmRunResult(
      runId: runId,
      status: 'confirmed',
      draftRequests: [draftId],
    ));
  }

  @override
  Future<List<ReconciliationRun>> getReconciliations() =>
      _delay(_seedReconciliations());

  @override
  Future<ReconciliationRun> runReconciliation({String scope = 'cash'}) =>
      _delay(
        ReconciliationRun(
          id: 'rc-$scope-001',
          status: 'matched',
          scope: scope,
          startedAt: DateTime.now().toUtc(),
          exceptions: const [],
        ),
      );

  // ---- reports ----
  @override
  Future<List<InventoryBucket>> getInventoryDaily({
    String? dateFrom,
    String? dateTo,
  }) =>
      _delay(_seedInventoryDaily());

  @override
  Future<List<InventoryBucket>> getInventoryMonthly({
    String? dateFrom,
    String? dateTo,
  }) =>
      _delay(_seedInventoryMonthly());

  @override
  Future<List<CashflowBucket>> getCashflowDaily({
    String? dateFrom,
    String? dateTo,
  }) =>
      _delay(_seedCashflowDaily());

  @override
  Future<List<CashflowBucket>> getCashflowMonthly({
    String? dateFrom,
    String? dateTo,
  }) =>
      _delay(_seedCashflowMonthly());

  @override
  Future<List<StagnationItem>> getStagnation({
    int watchDays = 30,
    int stagnantDays = 60,
    int criticalDays = 90,
  }) =>
      _delay(_seedStagnation());

  // =========================================================================
  // SRS Trà Sữa: Cảnh báo cận date & Báo cáo F&B
  // =========================================================================

  @override
  Future<List<ExpiryAlertItem>> getExpiryAlerts({int days = 7}) =>
      _delay([
        const ExpiryAlertItem(
          itemId: 'i-sua-tuoi-barista',
          sku: 'SUA-BARISTA-1L',
          itemName: 'Sữa tươi thanh trùng Barista 1L',
          unit: 'Hộp',
          lotNo: 'L2610-01',
          expiryDate: '2026-10-18',
          daysLeft: 2,
          quantity: '5',
          severity: 'warning',
          message: 'Lô L2610-01 Sữa tươi thanh trùng Barista 1L HSD 2026-10-18 (còn 2 ngày)',
        ),
        const ExpiryAlertItem(
          itemId: 'i-kem-cheese-anchor',
          sku: 'KEM-CHEESE-1KG',
          itemName: 'Kem phô mai tươi Anchor',
          unit: 'Hộp',
          lotNo: 'L2610-02',
          expiryDate: '2026-10-16',
          daysLeft: 0,
          quantity: '2',
          severity: 'critical',
          message: 'Lô L2610-02 Kem phô mai tươi Anchor HSD 2026-10-16 (Hết hạn hôm nay!)',
        ),
      ]);

  @override
  Future<List<ConsumptionTopItem>> getConsumptionTop({
    String? dateFrom,
    String? dateTo,
    int limit = 10,
  }) =>
      _delay([
        const ConsumptionTopItem(
          itemId: 'i-tra-den-phuc-long',
          sku: 'TRA-DEN-500G',
          name: 'Trà đen Phúc Long thượng hạng',
          unit: 'Gói',
          category: 'Trà & Cốt trà',
          usedQty: '48.5',
        ),
        const ConsumptionTopItem(
          itemId: 'i-sua-dac-ngoi-sao',
          sku: 'SUA-DAC-NG-SAO',
          name: 'Sữa đặc Ngôi Sao Phương Nam 1.28kg',
          unit: 'Hộp',
          category: 'Sữa & Bột béo',
          usedQty: '36.0',
        ),
        const ConsumptionTopItem(
          itemId: 'i-tran-chau-den-gia-thinh',
          sku: 'TC-DEN-GIA-THINH',
          name: 'Trân châu đen Gia Thịnh Phát 3kg',
          unit: 'Túi',
          category: 'Topping & Hạt',
          usedQty: '25.0',
        ),
        const ConsumptionTopItem(
          itemId: 'i-siro-dao-monin',
          sku: 'SIRO-DAO-MONIN',
          name: 'Siro đào Monin 700ml',
          unit: 'Chai',
          category: 'Siro & Đường',
          usedQty: '14.0',
        ),
      ]);

  @override
  Future<List<ShiftHistoryItem>> getShiftHistory({
    String? dateFrom,
    String? dateTo,
    String? shiftCode,
  }) =>
      _delay([
        const ShiftHistoryItem(
          id: 'st-shift-101',
          businessDate: '2026-10-15',
          shiftCode: 'morning',
          locationId: 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbb1',
          status: 'closed',
          maker: 'Nguyễn Văn Pha (Trưởng ca sáng)',
          lineCount: 8,
          varianceLines: 0,
          totalAbsVariance: '0.0',
          completedAt: '2026-10-15T15:05:00Z',
        ),
        const ShiftHistoryItem(
          id: 'st-shift-102',
          businessDate: '2026-10-15',
          shiftCode: 'afternoon',
          locationId: 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbb1',
          status: 'closed',
          maker: 'Trần Thị Ngon (Trưởng ca chiều)',
          lineCount: 8,
          varianceLines: 1,
          totalAbsVariance: '0.2',
          completedAt: '2026-10-15T23:10:00Z',
        ),
      ]);

  // =========================================================================
  // Admin IAM (Phase 1)
  // =========================================================================

  final List<BranchDto> _branches = [
    const BranchDto(
        id: 'br_q1',
        code: 'CH_QUAN_1',
        name: 'Cửa hàng Trà Sữa Quận 1 (Cửa hàng chính)',
        address: 'Quận 1, TP.HCM',
        active: true),
    const BranchDto(
        id: 'br_q3',
        code: 'CH_QUAN_3',
        name: 'Cửa hàng Trà Sữa Quận 3',
        address: 'Quận 3, TP.HCM',
        active: true),
    const BranchDto(
        id: 'br_bt',
        code: 'CH_BINH_THANH',
        name: 'Cửa hàng Trà Sữa Bình Thạnh',
        address: 'Bình Thạnh, TP.HCM',
        active: true),
  ];

  final List<RoleDto> _roles = [
    const RoleDto(
      code: 'admin',
      name: 'Chủ Quán / Quản Trị Viên (Admin)',
      capabilities: [
        'iam:admin',
        'admin:user_management',
        'admin',
        'inventory:manage_catalog',
        'inventory:approve_request',
        'inventory:view_balances',
        'cash:approve_request',
        'cash:view_balances',
      ],
    ),
    const RoleDto(
      code: 'staff',
      name: 'Nhân Viên Pha Chế / Quầy (Staff)',
      capabilities: [
        'inventory:create_request',
        'inventory:view_balances',
        'cash:create_request',
        'cash:view_balances',
      ],
    ),
    const RoleDto(
      code: 'approver',
      name: 'Quản Lý Cửa Hàng / Thủ Kho (Manager)',
      capabilities: [
        'inventory:approve_request',
        'inventory:manage_catalog',
        'inventory:view_balances',
        'cash:approve_request',
        'cash:view_balances',
      ],
    ),
    const RoleDto(
      code: 'auditor',
      name: 'Kiểm Soát Chất Lượng (Auditor)',
      capabilities: [
        'audit:view',
        'inventory:view_balances',
      ],
    ),
  ];

  final List<EmployeeUserDto> _employees = [
    const EmployeeUserDto(
      id: 'emp_1',
      username: 'tanmainguyenbinh',
      displayName: 'Bình Tân (Chủ Quán / Admin)',
      email: 'tanmainguyenbinh@gmail.com',
      status: 'active',
      roles: ['admin'],
      capabilities: [
        'iam:admin',
        'admin:user_management',
        'admin',
        'inventory:manage_catalog',
        'inventory:approve_request',
        'inventory:view_balances',
      ],
    ),
    const EmployeeUserDto(
      id: 'emp_2',
      username: 'staff_morning',
      displayName: 'Nguyễn Thị Mai (Pha Chế Ca Sáng)',
      email: 'mai.nguyen@khotrasua.vn',
      status: 'active',
      roles: ['staff'],
      capabilities: [
        'inventory:create_request',
        'inventory:view_balances',
        'cash:create_request',
        'cash:view_balances',
      ],
    ),
    const EmployeeUserDto(
      id: 'emp_3',
      username: 'manager_demo',
      displayName: 'Lê Hoàng Nam (Quản Lý Cửa Hàng)',
      email: 'nam.le@khotrasua.vn',
      status: 'active',
      roles: ['admin', 'approver', 'inventory_manager'],
      capabilities: [
        'iam:admin',
        'admin:user_management',
        'admin',
        'inventory:approve_request',
        'inventory:manage_catalog',
        'inventory:view_balances',
        'cash:approve_request',
      ],
    ),
  ];

  @override
  Future<List<BranchDto>> getBranches() => _delay(_branches);

  @override
  Future<List<RoleDto>> getRoles() => _delay(_roles);

  @override
  Future<List<EmployeeUserDto>> getEmployees({
    String? search,
    String? branchId,
    String? role,
    String? status,
  }) {
    var list = _employees;
    if (search != null && search.isNotEmpty) {
      list = list
          .where((e) =>
              e.username.contains(search) || e.displayName.contains(search))
          .toList();
    }
    if (status != null && status.isNotEmpty) {
      list = list.where((e) => e.status == status).toList();
    }
    return _delay(list);
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
  }) {
    final emp = EmployeeUserDto(
      id: 'emp_${DateTime.now().millisecondsSinceEpoch}',
      username: username,
      displayName: displayName,
      email: email,
      phoneNumber: phoneNumber,
      branchId: branchId,
      status: 'active',
      roles: roles,
      mustChangePassword: onboardingMethod == 'temporary_password',
      hasPendingInvite: onboardingMethod != 'temporary_password',
      lastInviteEmailSent: onboardingMethod == 'invite_email',
      lastInviteToken: onboardingMethod == 'invite_email' ? 'fake_invite_token_123' : null,
      lastInviteLink: onboardingMethod == 'invite_email' ? 'http://localhost:3000/accept-invite?token=fake_invite_token_123' : null,
    );
    _employees.add(emp);
    return _delay(emp);
  }

  @override
  Future<EmployeeUserDto> updateEmployeeStatus(
    String userId,
    String status, {
    String? reason,
  }) {
    final idx = _employees.indexWhere((e) => e.id == userId);
    if (idx >= 0) {
      final old = _employees[idx];
      final updated = EmployeeUserDto(
        id: old.id,
        username: old.username,
        displayName: old.displayName,
        email: old.email,
        phoneNumber: old.phoneNumber,
        status: status,
        branchId: old.branchId,
        branchName: old.branchName,
        roles: old.roles,
        capabilities: old.capabilities,
        mustChangePassword: old.mustChangePassword,
        hasPendingInvite: old.hasPendingInvite,
        inviteExpiresAt: old.inviteExpiresAt,
        authVersion: old.authVersion + 1,
        scopes: old.scopes,
      );
      _employees[idx] = updated;
      return _delay(updated);
    }
    throw ApiException('NOT_FOUND', 'Không tìm thấy nhân viên');
  }

  @override
  Future<EmployeeUserDto> updateEmployeeRoles(
      String userId, List<String> roles) {
    final idx = _employees.indexWhere((e) => e.id == userId);
    if (idx >= 0) {
      final old = _employees[idx];
      final updated = EmployeeUserDto(
        id: old.id,
        username: old.username,
        displayName: old.displayName,
        email: old.email,
        phoneNumber: old.phoneNumber,
        status: old.status,
        branchId: old.branchId,
        branchName: old.branchName,
        roles: roles,
        capabilities: old.capabilities,
        mustChangePassword: old.mustChangePassword,
        hasPendingInvite: old.hasPendingInvite,
        inviteExpiresAt: old.inviteExpiresAt,
        authVersion: old.authVersion + 1,
        scopes: old.scopes,
      );
      _employees[idx] = updated;
      return _delay(updated);
    }
    throw ApiException('NOT_FOUND', 'Không tìm thấy nhân viên');
  }

  @override
  Future<EmployeeUserDto> updateEmployeeScopes(
    String userId,
    List<Map<String, dynamic>> scopes,
  ) {
    final idx = _employees.indexWhere((e) => e.id == userId);
    if (idx >= 0) {
      return _delay(_employees[idx]);
    }
    throw ApiException('NOT_FOUND', 'Không tìm thấy nhân viên');
  }

  @override
  Future<void> revokeEmployeeSessions(String userId) => _delay(null);

  @override
  Future<String> resetEmployeePassword(String userId) =>
      _delay('BankOps#TEMP123!');

  @override
  Future<String> reinviteEmployee(String userId) =>
      _delay('inv_mock_token_123');

  // =========================================================================
  // ETL Pipeline (Phase 2)
  // =========================================================================

  final List<EtlConnectionDto> _etlConnections = [
    const EtlConnectionDto(
      id: 'conn_1',
      name: 'Nguồn Tệp Excel/CSV Kế toán Kho',
      type: 'csv',
      status: 'active',
    ),
  ];

  final List<EtlPipelineDto> _etlPipelines = [
    const EtlPipelineDto(
      id: 'pipe_1',
      name: 'Cân đối Tồn kho Quản trị & Điều chỉnh',
      target: 'balance_adjustment_admin',
      connectionId: 'conn_1',
      status: 'active',
    ),
  ];

  final List<EtlMappingVersionDto> _etlMappingVersions = [
    const EtlMappingVersionDto(
      id: 'mv_1',
      pipelineId: 'pipe_1',
      version: 1,
      status: 'published',
      mappingJson: [
        {
          'source_field': 'sku',
          'target_field': 'sku',
          'required': true,
          'transform': 'trim_upper'
        },
        {
          'source_field': 'target_quantity',
          'target_field': 'target_quantity',
          'required': false,
          'transform': 'to_float'
        },
        {
          'source_field': 'reason',
          'target_field': 'reason',
          'required': false,
          'transform': 'trim'
        },
      ],
      duplicatePolicy: 'reject',
    ),
  ];

  final List<EtlRunDto> _etlRuns = [
    const EtlRunDto(
      id: 'run_1',
      pipelineId: 'pipe_1',
      mappingVersionNum: 1,
      runnerId: 'emp_1',
      status: 'staged',
      progressPct: 100,
      totalRows: 10,
      validRows: 9,
      invalidRows: 1,
      sourceFingerprint: 'mock_fp_123',
    ),
  ];

  @override
  Future<List<EtlConnectionDto>> getEtlConnections({String? branchId}) =>
      _delay(_etlConnections);

  @override
  Future<EtlConnectionDto> createEtlConnection({
    required String name,
    required String type,
    String? secretRef,
    List<String>? allowlistSheets,
    String? branchId,
  }) {
    final conn = EtlConnectionDto(
      id: 'conn_${DateTime.now().millisecondsSinceEpoch}',
      name: name,
      type: type,
      status: 'active',
      secretRef: secretRef,
      allowlistSheets: allowlistSheets ?? const [],
      branchId: branchId,
    );
    _etlConnections.add(conn);
    return _delay(conn);
  }

  @override
  Future<List<EtlPipelineDto>> getEtlPipelines({
    String? target,
    String? branchId,
  }) {
    var list = _etlPipelines;
    if (target != null && target.isNotEmpty) {
      list = list.where((p) => p.target == target).toList();
    }
    return _delay(list);
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
  }) {
    final pipe = EtlPipelineDto(
      id: 'pipe_${DateTime.now().millisecondsSinceEpoch}',
      name: name,
      target: target,
      connectionId: connectionId,
      branchId: branchId,
      locationId: locationId,
      destinationLocationId: destinationLocationId,
      scheduleCron: scheduleCron,
      status: 'active',
    );
    _etlPipelines.add(pipe);
    return _delay(pipe);
  }

  @override
  Future<List<EtlMappingVersionDto>> getEtlMappingVersions(String pipelineId) =>
      _delay(_etlMappingVersions);

  @override
  Future<EtlMappingVersionDto> createEtlMappingVersion(
    String pipelineId, {
    required List<Map<String, dynamic>> mappingRules,
    String duplicatePolicy = 'reject',
  }) {
    final mv = EtlMappingVersionDto(
      id: 'mv_${DateTime.now().millisecondsSinceEpoch}',
      pipelineId: pipelineId,
      version: _etlMappingVersions.length + 1,
      status: 'draft',
      mappingJson: mappingRules,
      duplicatePolicy: duplicatePolicy,
    );
    _etlMappingVersions.add(mv);
    return _delay(mv);
  }

  @override
  Future<EtlMappingVersionDto> publishEtlMappingVersion(
    String pipelineId,
    String versionId,
  ) {
    final idx = _etlMappingVersions.indexWhere((m) => m.id == versionId);
    if (idx >= 0) {
      final old = _etlMappingVersions[idx];
      final pub = EtlMappingVersionDto(
        id: old.id,
        pipelineId: old.pipelineId,
        version: old.version,
        status: 'published',
        mappingJson: old.mappingJson,
        duplicatePolicy: old.duplicatePolicy,
        publishedAt: DateTime.now(),
      );
      _etlMappingVersions[idx] = pub;
      return _delay(pub);
    }
    throw ApiException('NOT_FOUND', 'Không tìm thấy mapping version');
  }

  @override
  Future<EtlRunDto> triggerEtlRun(
    String pipelineId, {
    List<Map<String, dynamic>>? rawRows,
    List<int>? fileBytes,
    String? filename,
    String? externalEventId,
  }) {
    final run = EtlRunDto(
      id: 'run_${DateTime.now().millisecondsSinceEpoch}',
      pipelineId: pipelineId,
      mappingVersionNum: 1,
      runnerId: 'emp_1',
      status: 'staged',
      progressPct: 100,
      totalRows: 5,
      validRows: 5,
      invalidRows: 0,
      sourceFingerprint: 'mock_fp_${DateTime.now().millisecondsSinceEpoch}',
    );
    _etlRuns.add(run);
    return _delay(run);
  }

  @override
  Future<List<EtlRunDto>> getEtlRuns({
    String? pipelineId,
    String? status,
  }) =>
      _delay(_etlRuns);

  @override
  Future<EtlRunDto> getEtlRun(String runId) {
    final run =
        _etlRuns.firstWhere((r) => r.id == runId, orElse: () => _etlRuns.first);
    return _delay(run);
  }

  @override
  Future<Map<String, dynamic>> getEtlRunRows(
    String runId, {
    bool? valid,
    String? search,
    int page = 1,
    int pageSize = 50,
  }) {
    final sampleRows = [
      const EtlRunRowDto(
        id: 'rr_1',
        runId: 'run_1',
        rowNumber: 1,
        sourceRowKey: 'IP15-128',
        rawDataJson: {'sku': 'IP15-128', 'target_quantity': 20},
        canonicalDataJson: {'sku': 'IP15-128', 'target_quantity': 20.0},
        valid: true,
        actionPreview: {
          'action': 'balance_adjustment',
          'sku': 'IP15-128',
          'current_quantity': 15.0,
          'target_quantity': 20.0,
          'delta_quantity': 5.0,
          'direction': 'increase',
        },
      ),
    ];
    return _delay({
      'total': sampleRows.length,
      'page': page,
      'page_size': pageSize,
      'rows': sampleRows,
    });
  }

  @override
  Future<EtlRunDto> reviewEtlRun(
    String runId, {
    required String decision,
    String? note,
  }) {
    final idx = _etlRuns.indexWhere((r) => r.id == runId);
    if (idx >= 0) {
      final old = _etlRuns[idx];
      final reviewed = EtlRunDto(
        id: old.id,
        pipelineId: old.pipelineId,
        mappingVersionNum: old.mappingVersionNum,
        runnerId: old.runnerId,
        status: decision == 'approved' ? 'reviewing' : 'rejected',
        progressPct: 100,
        totalRows: old.totalRows,
        validRows: old.validRows,
        invalidRows: old.invalidRows,
        sourceFingerprint: old.sourceFingerprint,
        reviewDecision: decision,
        reviewNote: note,
      );
      _etlRuns[idx] = reviewed;
      return _delay(reviewed);
    }
    throw ApiException('NOT_FOUND', 'Không tìm thấy run');
  }

  @override
  Future<Map<String, dynamic>> postEtlRun(String runId) {
    return _delay({
      'status': 'posted',
      'run_id': runId,
      'movements_count': 5,
      'single_admin_override': true
    });
  }

  @override
  Future<String> getEtlErrorReport(String runId) {
    return _delay(
        'Dòng,Mã SKU,Chi tiết lỗi\n2,ERR_SKU_999,SKU không tồn tại trong danh mục\n');
  }

  @override
  Future<DashboardSummaryDto> getDashboardSummary({bool canApprove = false}) async {
    final results = await Future.wait([
      getLocations(),
      getItems(),
      getBalances(),
      getAssets(),
      getStockRequests(),
      canApprove ? getApprovalInbox() : Future.value(<ApprovalItem>[]),
      getCashBalances(),
      getCashboxes(),
      getLowStockAlerts(),
      getReconciliations(),
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
