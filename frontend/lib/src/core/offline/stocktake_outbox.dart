/// Durable stocktake commands. A health response is never a sync ACK.
library;

import 'dart:async';
import 'dart:convert';
import 'dart:math';
import 'package:crypto/crypto.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../../data/repositories/bankops_repository.dart';

enum OutBoxStatus { pending, sending, ok, failed }

/// Metadata for old, unowned drafts. The payload remains read-only until a
/// signed-in user explicitly claims it for their account and branch.
class LegacyStocktakeDraft {
  LegacyStocktakeDraft._(this.kind, this.stocktakeId, this.lineCount,
      this.canImport, this._index, this._originalKey, this._payload);

  final String kind;
  final String? stocktakeId;
  final int lineCount;
  final bool canImport;
  final int _index;
  final String _originalKey;
  final Map<String, dynamic> _payload;
}

class OutBoxEntry {
  OutBoxEntry(
      {required this.id,
      required this.kind,
      required this.payload,
      required this.idempotencyKey,
      required this.ownerUserId,
      this.ownerBranch,
      this.attempt = 0,
      this.status = OutBoxStatus.pending,
      this.phase = 0,
      this.retryAtMs,
      this.blockedReason});
  final String id;
  final String kind;
  final Map<String, dynamic> payload;
  final String idempotencyKey;
  final String ownerUserId;
  final String? ownerBranch;
  int attempt;
  OutBoxStatus status;
  int phase; // submit: 0=update lines; 1=submit
  int? retryAtMs;
  String? blockedReason;

  Map<String, dynamic> toJson() => {
        'id': id,
        'kind': kind,
        'payload': payload,
        'idempotencyKey': idempotencyKey,
        'ownerUserId': ownerUserId,
        'ownerBranch': ownerBranch,
        'attempt': attempt,
        'status': status.index,
        'phase': phase,
        'retryAtMs': retryAtMs,
        'blockedReason': blockedReason,
      };
  factory OutBoxEntry.fromJson(Map<String, dynamic> value) => OutBoxEntry(
        id: value['id'] as String,
        kind: value['kind'] as String,
        payload: Map<String, dynamic>.from(value['payload'] as Map),
        idempotencyKey: value['idempotencyKey'] as String,
        ownerUserId: value['ownerUserId'] as String,
        ownerBranch: value['ownerBranch'] as String?,
        attempt: value['attempt'] as int? ?? 0,
        status: OutBoxStatus.values[value['status'] as int? ?? 0],
        phase: value['phase'] as int? ?? 0,
        retryAtMs: value['retryAtMs'] as int?,
        blockedReason: value['blockedReason'] as String?,
      );
}

class StocktakeOutbox {
  StocktakeOutbox({String? ownerUserId, String? ownerBranch})
      : _ownerUserId = ownerUserId,
        _ownerBranch = ownerBranch;
  static final StocktakeOutbox shared = StocktakeOutbox();
  String? _ownerUserId;
  String? _ownerBranch;
  bool _loaded = false;
  int _identityEpoch = 0;
  Future<void> _mutationTail = Future<void>.value();
  Future<void> _persistenceTail = Future<void>.value();
  final List<OutBoxEntry> _queue = [];
  int? _flushingEpoch;

  Future<T> _exclusive<T>(Future<T> Function() operation) async {
    final preceding = _mutationTail;
    final done = Completer<void>();
    _mutationTail = done.future;
    await preceding;
    try {
      return await operation();
    } finally {
      done.complete();
    }
  }

  String get _storageKey {
    final owner = _ownerUserId;
    if (owner == null || owner.isEmpty) throw StateError('Chưa xác định tài khoản kiểm kê');
    final identity = base64Url.encode(utf8.encode('$owner|${_ownerBranch ?? ''}'));
    return 'queue_stocktake_v2_$identity';
  }

  String? get ownerUserId => _ownerUserId;

  Future<void> bindIdentity(String? userId, String? branch) =>
      _exclusive(() async {
        if (userId == _ownerUserId && branch == _ownerBranch && _loaded) return;
        if (userId != _ownerUserId || branch != _ownerBranch) {
          _identityEpoch++;
          _ownerUserId = userId;
          _ownerBranch = branch;
          _queue.clear();
          _loaded = false;
        }
        if (userId != null && userId.isNotEmpty) {
          await _restoreUnlocked();
        }
      });

  List<OutBoxEntry> get queue => List.unmodifiable(_queue);
  bool get hasPending => _queue.any((entry) => entry.status != OutBoxStatus.ok);
  bool get hasConflict =>
      _queue.any((entry) => entry.status == OutBoxStatus.failed);
  bool get requiresReauth =>
      _queue.any((entry) => entry.blockedReason == 'reauth');
  bool get rateLimited =>
      _queue.any((entry) => entry.blockedReason == 'rate_limit');
  int? get nextRetryAtMs {
    final times = _queue
        .where((entry) => entry.status == OutBoxStatus.pending &&
            entry.blockedReason != 'reauth' && entry.retryAtMs != null)
        .map((entry) => entry.retryAtMs!)
        .toList();
    if (times.isEmpty) return null;
    times.sort();
    return times.first;
  }

  /// Version 1 had no owner. Never merge or replay it during restore.
  Future<List<LegacyStocktakeDraft>> legacyDrafts() async {
    final prefs = await SharedPreferences.getInstance();
    final raw = prefs.getString('queue_stocktake_v1');
    if (raw == null || raw.isEmpty) return const [];
    final decoded = jsonDecode(raw);
    if (decoded is! List) throw const FormatException('Invalid legacy stocktake queue');
    final drafts = <LegacyStocktakeDraft>[];
    for (var index = 0; index < decoded.length; index++) {
      final row = decoded[index];
      if (row is! Map) throw const FormatException('Invalid legacy stocktake entry');
      final value = Map<String, dynamic>.from(row);
      if (value['status'] == OutBoxStatus.ok.index) continue;
      final payload = value['payload'] is Map
          ? Map<String, dynamic>.from(value['payload'] as Map)
          : <String, dynamic>{};
      final kind = value['kind']?.toString() ?? 'unknown';
      final stocktakeId = payload['stocktake_id']?.toString();
      final lines = payload['lines'];
      final canImport = kind == 'create_stocktake'
          ? payload['location_id'] is String &&
              (payload['location_id'] as String).isNotEmpty
          : {'submit_lines', 'submit_stocktake'}.contains(kind) &&
              stocktakeId != null && stocktakeId.isNotEmpty &&
              lines is List && lines.every((line) => line is Map);
      drafts.add(LegacyStocktakeDraft._(
          kind, stocktakeId, lines is List ? lines.length : 0, canImport,
          index, value['idempotencyKey']?.toString() ?? '', payload));
    }
    return drafts;
  }

  /// Copy V1 data only after the signed-in user confirms account ownership.
  /// The old queue is removed only after the new per-user queue is durable.
  Future<int> claimLegacyDrafts({required String currentUserId,
      String? currentBranch, required bool confirmed}) => _exclusive(() async {
    if (!confirmed || currentUserId != _ownerUserId ||
        currentBranch != _ownerBranch || currentUserId.isEmpty) {
      throw StateError('Cần xác nhận tài khoản và chi nhánh sở hữu bản kiểm kê cũ');
    }
    if (!_loaded) await _restoreUnlocked();
    final drafts = await legacyDrafts();
    if (drafts.any((draft) => !draft.canImport)) {
      throw StateError('Bản kiểm kê cũ có lệnh không hỗ trợ; dữ liệu gốc vẫn được giữ');
    }
    final imported = <OutBoxEntry>[];
    for (final draft in drafts) {
      final keySource = '${draft._index}|${draft._originalKey}|${draft.kind}';
      final key = 'legacy-${sha256.convert(utf8.encode(keySource)).toString().substring(0, 32)}';
      final duplicate = _queue.where((entry) => entry.idempotencyKey == key);
      if (duplicate.isNotEmpty) {
        if (duplicate.first.kind != draft.kind ||
            jsonEncode(duplicate.first.payload) != jsonEncode(draft._payload)) {
          throw StateError('Bản kiểm kê cũ trùng mã với dữ liệu khác');
        }
        continue;
      }
      if (draft.stocktakeId != null && _queue.any((entry) =>
          entry.payload['stocktake_id'] == draft.stocktakeId &&
          entry.status != OutBoxStatus.ok)) {
        throw StateError('Ca này đã có lệnh đồng bộ mới; cần đối chiếu trước khi nhập');
      }
      imported.add(OutBoxEntry(
          id: 'outbox-${DateTime.now().microsecondsSinceEpoch}-${Random.secure().nextInt(1 << 32)}',
          kind: draft.kind,
          payload: Map<String, dynamic>.from(draft._payload),
          idempotencyKey: key,
          ownerUserId: currentUserId,
          ownerBranch: currentBranch));
    }
    _queue.addAll(imported);
    try {
      await _save();
    } catch (_) {
      _queue.removeWhere(imported.contains);
      rethrow;
    }
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove('queue_stocktake_v1');
    await prefs.remove('queue_stocktake_v1_version');
    return imported.length;
  });

  /// Local count drafts remain intact; call only after user confirmation.
  Future<void> discardConflicts() => _exclusive(() async {
    final removed = _queue.where((entry) => entry.status == OutBoxStatus.failed).toList();
    _queue.removeWhere(removed.contains);
    try {
      await _save();
    } catch (_) {
      _queue.addAll(removed);
      rethrow;
    }
  });

  Future<void> restore() => _exclusive(() async {
    if (!_loaded) await _restoreUnlocked();
  });

  Future<void> _restoreUnlocked() async {
    final epoch = _identityEpoch;
    final key = _storageKey;
    final owner = _ownerUserId;
    final branch = _ownerBranch;
    final prefs = await SharedPreferences.getInstance();
    if (epoch != _identityEpoch) return;
    final stored = prefs.getString(key);
    _queue.clear();
    if (stored == null || stored.isEmpty) {
      _loaded = true;
      return;
    }
    for (final value in jsonDecode(stored) as List) {
      final entry =
          OutBoxEntry.fromJson(Map<String, dynamic>.from(value as Map));
      if (entry.ownerUserId != owner || entry.ownerBranch != branch) {
        throw StateError('Hàng đợi kiểm kê không thuộc tài khoản hiện tại');
      }
      if (entry.status == OutBoxStatus.sending) {
        entry.status = OutBoxStatus.pending;
      }
      _queue.add(entry);
    }
    _loaded = true;
  }

  Future<void> _save({int? expectedEpoch}) async {
    final epoch = _identityEpoch;
    if (expectedEpoch != null && epoch != expectedEpoch) {
      throw StateError('Tài khoản kiểm kê đã thay đổi');
    }
    final key = _storageKey;
    final data = jsonEncode(_queue.map((entry) => entry.toJson()).toList());
    final preceding = _persistenceTail;
    final done = Completer<void>();
    _persistenceTail = done.future;
    await preceding;
    try {
      if (epoch != _identityEpoch) {
        throw StateError('Tài khoản kiểm kê đã thay đổi');
      }
      final prefs = await SharedPreferences.getInstance();
      if (epoch != _identityEpoch || !await prefs.setString(key, data)) {
        throw StateError('Không lưu được hàng đợi kiểm kê');
      }
      if (epoch != _identityEpoch) {
        throw StateError('Tài khoản kiểm kê đã thay đổi');
      }
    } finally {
      done.complete();
    }
  }

  /// Persist before telling the user that an offline operation was saved.
  Future<void> enqueue(
      String kind, Map<String, dynamic> payload, String idempotencyKey) {
    final requestedOwner = _ownerUserId;
    final requestedBranch = _ownerBranch;
    return _exclusive(() async {
    if (requestedOwner != _ownerUserId || requestedBranch != _ownerBranch) {
      throw StateError('Tài khoản kiểm kê đã thay đổi');
    }
    if (!_loaded) await _restoreUnlocked();
    final epoch = _identityEpoch;
    final owner = _ownerUserId;
    if (owner == null || owner.isEmpty) throw StateError('Cần đăng nhập trước khi lưu kiểm kê');
    if (!{'create_stocktake', 'submit_lines', 'submit_stocktake'}
        .contains(kind)) {
      throw ArgumentError.value(kind, 'kind');
    }
    final duplicate =
        _queue.where((entry) => entry.idempotencyKey == idempotencyKey);
    if (duplicate.isNotEmpty) {
      if (duplicate.first.kind != kind ||
          jsonEncode(duplicate.first.payload) != jsonEncode(payload)) {
        throw StateError('Idempotency-Key đã dùng cho nội dung khác');
      }
      return;
    }
    if (kind == 'create_stocktake' &&
        _queue.any((entry) =>
            entry.kind == kind &&
            entry.status != OutBoxStatus.ok &&
            jsonEncode(entry.payload) == jsonEncode(payload))) {
      return;
    }
    final stocktakeId = payload['stocktake_id'];
    if (stocktakeId != null && _queue.any((entry) =>
        entry.payload['stocktake_id'] == stocktakeId &&
        entry.kind == 'submit_stocktake' && entry.status != OutBoxStatus.ok)) {
      throw StateError('Ca này đã có lệnh gửi duyệt đang chờ đồng bộ');
    }
    // Only an unsent count may be replaced by a newer complete count.
    final superseded = _queue
        .where((entry) =>
            entry.payload['stocktake_id'] == stocktakeId &&
            entry.kind == 'submit_lines' &&
            entry.status == OutBoxStatus.pending &&
            entry.attempt == 0 &&
            entry.phase == 0)
        .toList();
    if (stocktakeId != null && _queue.any((entry) =>
        entry.payload['stocktake_id'] == stocktakeId &&
        entry.kind == 'submit_lines' && entry.status != OutBoxStatus.ok &&
        !superseded.contains(entry))) {
      throw StateError('Ca này có số đếm đang đồng bộ; cần xử lý trước khi ghi tiếp');
    }
    if (kind != 'create_stocktake') _queue.removeWhere(superseded.contains);
    final entry = OutBoxEntry(
        id: 'outbox-${DateTime.now().microsecondsSinceEpoch}-${Random.secure().nextInt(1 << 32)}',
        kind: kind,
        payload: payload,
        idempotencyKey: idempotencyKey,
        ownerUserId: owner,
        ownerBranch: _ownerBranch);
    _queue.add(entry);
    try {
      await _save(expectedEpoch: epoch);
    } catch (_) {
      if (epoch == _identityEpoch) {
        _queue.remove(entry);
        _queue.addAll(superseded);
      }
      rethrow;
    }
    });
  }

  Future<bool> tryFlush({
    required BankOpsRepository repository,
    required String currentUserId,
    String? currentBranch,
    bool force = false,
  }) async {
    if (_flushingEpoch == _identityEpoch || _ownerUserId != currentUserId ||
        _ownerBranch != currentBranch) {
      return false;
    }
    if (!_loaded) {
      await restore();
    }
    if (_flushingEpoch == _identityEpoch ||
        _ownerUserId != currentUserId || _ownerBranch != currentBranch) {
      return false;
    }
    if (!hasPending) {
      return false;
    }
    final epoch = _identityEpoch;
    _flushingEpoch = epoch;
    try {
      final blockedShifts = <String>{};
      for (final entry in List<OutBoxEntry>.of(_queue)) {
        if (epoch != _identityEpoch || _ownerUserId != currentUserId ||
            _ownerBranch != currentBranch) {
          return false;
        }
        if (entry.ownerUserId != currentUserId ||
            entry.ownerBranch != currentBranch) {
          return false;
        }
        if (entry.status == OutBoxStatus.ok) {
          continue;
        }
        final shift = entry.payload['stocktake_id']?.toString() ?? entry.id;
        if (entry.status == OutBoxStatus.failed) {
          blockedShifts.add(shift);
          continue;
        }
        if (blockedShifts.contains(shift)) {
          continue;
        }
        if (!force && entry.retryAtMs != null &&
            entry.retryAtMs! > DateTime.now().millisecondsSinceEpoch) {
          continue;
        }
        entry.status = OutBoxStatus.sending;
        try {
          await _save(expectedEpoch: epoch);
        } catch (_) {
          if (epoch != _identityEpoch) return false;
          entry.status = OutBoxStatus.pending;
          rethrow;
        }
        try {
          await _send(entry, repository, () => epoch == _identityEpoch &&
              _ownerUserId == currentUserId && _ownerBranch == currentBranch);
          if (epoch != _identityEpoch) return false;
          entry.status = OutBoxStatus.ok;
          entry.retryAtMs = null;
          entry.blockedReason = null;
          await _save(expectedEpoch: epoch);
        } on ApiException catch (error) {
          if (epoch != _identityEpoch) return false;
          entry.attempt++;
          final auth = {'HTTP_401', 'UNAUTHENTICATED', 'UNAUTHORIZED',
              'TOKEN_EXPIRED', 'AUTH_EXPIRED'}.contains(error.code);
          final rateLimited = {'HTTP_429', 'RATE_LIMITED',
              'TOO_MANY_REQUESTS'}.contains(error.code);
          final transient = auth || rateLimited || error.code == 'NETWORK' ||
              error.code == 'DEPENDENCY_UNAVAILABLE' ||
              RegExp(r'^HTTP_5\d\d$').hasMatch(error.code);
          entry.status = transient ? OutBoxStatus.pending : OutBoxStatus.failed;
          entry.blockedReason = auth ? 'reauth' : rateLimited ? 'rate_limit' : null;
          if (transient) {
            final seconds = entry.attempt >= 5 ? 480 : 30 * (1 << (entry.attempt - 1));
            entry.retryAtMs = DateTime.now().millisecondsSinceEpoch + seconds * 1000;
          }
          await _save(expectedEpoch: epoch);
          if (transient) return false;
          blockedShifts.add(shift);
        } catch (_) {
          if (epoch != _identityEpoch) return false;
          entry.attempt++;
          entry.status = OutBoxStatus.pending;
          entry.retryAtMs = DateTime.now().millisecondsSinceEpoch + 30000;
          await _save(expectedEpoch: epoch);
          return false;
        }
      }
      return !hasPending;
    } finally {
      if (_flushingEpoch == epoch) _flushingEpoch = null;
    }
  }

  Future<void> _send(OutBoxEntry entry, BankOpsRepository repository,
      bool Function() isCurrentIdentity) async {
    final payload = entry.payload;
    if (!isCurrentIdentity()) throw StateError('Tài khoản đã thay đổi');
    if (entry.kind == 'create_stocktake') {
      await repository.createStocktake(
        locationId: payload['location_id'] as String,
        note: payload['note'] as String?,
        shiftCode: payload['shift_code'] as String?,
        businessDate: payload['business_date'] as String?,
        idempotencyKey: entry.idempotencyKey,
      );
      return;
    }
    final id = payload['stocktake_id'] as String?;
    if (id == null || id.isEmpty) throw StateError('Thiếu stocktake_id');
    final lines = (payload['lines'] as List)
        .map((line) => Map<String, dynamic>.from(line as Map))
        .toList();
    if (entry.phase == 0) {
      if (!isCurrentIdentity()) throw StateError('Tài khoản đã thay đổi');
      final updated = await repository.updateStocktakeLines(id, lines,
          idempotencyKey: '${entry.idempotencyKey}:lines',
          expectedVersion: payload['expected_version'] as int?);
      if (entry.kind == 'submit_lines') return;
      if (!isCurrentIdentity()) throw StateError('Tài khoản đã thay đổi');
      entry.phase = 1;
      entry.payload['expected_version'] = updated.version;
      await _save();
    }
    try {
      if (!isCurrentIdentity()) throw StateError('Tài khoản đã thay đổi');
      await repository.submitStocktake(id,
          idempotencyKey: '${entry.idempotencyKey}:submit',
          expectedVersion: entry.payload['expected_version'] as int?);
    } on ApiException catch (error) {
      // Handle VERSION_CONFLICT: fetch fresh version and allow retry
      if (error.code == 'VERSION_CONFLICT') {
        final current = await repository.getStocktake(id);
        if (!isCurrentIdentity()) throw StateError('Tài khoản đã thay đổi');
        entry.payload['expected_version'] = current.version;
        await _save();
        // Re-throw to let tryFlush mark as failed; caller can retry with fresh version
        rethrow;
      }
      if (error.code != 'STATE_CONFLICT') rethrow;
      final current = await repository.getStocktake(id);
      if (current.status != 'submitted' && current.status != 'closed') rethrow;
    }
  }
}
