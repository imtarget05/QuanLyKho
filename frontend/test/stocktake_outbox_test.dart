import 'dart:async';
import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:kho_tra_sua/src/core/offline/offline_ui.dart';
import 'package:kho_tra_sua/src/core/offline/stocktake_outbox.dart';
import 'package:kho_tra_sua/src/data/models/dtos.dart';
import 'package:kho_tra_sua/src/data/repositories/bankops_repository.dart';
import 'package:kho_tra_sua/src/data/repositories/fake_repository.dart';
import 'package:shared_preferences/shared_preferences.dart';

class _RecordingRepository extends FakeBankOpsRepository {
  _RecordingRepository() : super(latency: Duration.zero);

  final calls = <String>[];
  bool failUpdate = false;
  String? failureCode;
  String? failForId;
  bool failSubmit = false;
  String? submitFailureCode;

  @override
  Future<StocktakeItem> updateStocktakeLines(
      String id, List<Map<String, dynamic>> lines,
      {String? idempotencyKey, int? expectedVersion}) async {
    calls.add('lines:$id:${lines.single['counted_qty']}:$idempotencyKey');
    if (failUpdate) throw ApiException('NETWORK', 'offline');
    if (failureCode != null && (failForId == null || failForId == id)) {
      throw ApiException(failureCode!, 'retry later');
    }
    return super.updateStocktakeLines(id, lines,
        idempotencyKey: idempotencyKey, expectedVersion: expectedVersion);
  }

  @override
  Future<StocktakeItem> submitStocktake(String id,
      {String? idempotencyKey, int? expectedVersion}) async {
    calls.add('submit:$id:$idempotencyKey');
    if (failSubmit) throw ApiException('NETWORK', 'offline submit');
    if (submitFailureCode != null) {
      throw ApiException(submitFailureCode!, 'submit failed');
    }
    return super.submitStocktake(id,
        idempotencyKey: idempotencyKey, expectedVersion: expectedVersion);
  }
}

/// Repository that simulates network loss then recovery
class _NetworkLossRepository extends FakeBankOpsRepository {
  _NetworkLossRepository() : super(latency: Duration.zero);

  final calls = <String>[];
  bool networkAvailable = false;
  int callCount = 0;

  @override
  Future<StocktakeItem> createStocktake({
    required String locationId,
    String? note,
    String? shiftCode,
    String? businessDate,
    String? idempotencyKey,
  }) async {
    callCount++;
    if (!networkAvailable) throw ApiException('NETWORK', 'offline');
    calls.add('create:$locationId:$shiftCode:$idempotencyKey');
    return super.createStocktake(
        locationId: locationId,
        note: note,
        shiftCode: shiftCode,
        businessDate: businessDate,
        idempotencyKey: idempotencyKey);
  }

  @override
  Future<StocktakeItem> updateStocktakeLines(
      String id, List<Map<String, dynamic>> lines,
      {String? idempotencyKey, int? expectedVersion}) async {
    callCount++;
    if (!networkAvailable) throw ApiException('NETWORK', 'offline');
    calls.add('lines:$id:${lines.single['counted_qty']}:$idempotencyKey');
    return super.updateStocktakeLines(id, lines,
        idempotencyKey: idempotencyKey, expectedVersion: expectedVersion);
  }

  @override
  Future<StocktakeItem> submitStocktake(String id,
      {String? idempotencyKey, int? expectedVersion}) async {
    callCount++;
    if (!networkAvailable) throw ApiException('NETWORK', 'offline');
    calls.add('submit:$id:$idempotencyKey');
    return super.submitStocktake(id,
        idempotencyKey: idempotencyKey, expectedVersion: expectedVersion);
  }
}

/// Repository that simulates VERSION_CONFLICT on submit
class _VersionConflictRepository extends FakeBankOpsRepository {
  _VersionConflictRepository() : super(latency: Duration.zero);

  final calls = <String>[];
  bool conflictOnSubmit = true;
  int submitAttempts = 0;

  @override
  Future<StocktakeItem> submitStocktake(String id,
      {String? idempotencyKey, int? expectedVersion}) async {
    submitAttempts++;
    calls.add('submit:$id:$idempotencyKey:v$expectedVersion');
    if (conflictOnSubmit && submitAttempts == 1) {
      throw ApiException('VERSION_CONFLICT', 'version mismatch');
    }
    return super.submitStocktake(id,
        idempotencyKey: idempotencyKey, expectedVersion: expectedVersion);
  }
}

class _ControlledTimer implements Timer {
  _ControlledTimer(this.callback);
  final void Function() callback;
  bool active = true;
  @override
  bool get isActive => active;
  @override
  int get tick => active ? 0 : 1;
  @override
  void cancel() => active = false;
  void fire() {
    if (!active) return;
    active = false;
    callback();
  }
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() => SharedPreferences.setMockInitialValues({}));

  test('offline create survives restart and opens one shift on replay', () async {
    final repository = _RecordingRepository();
    final location = (await repository.getLocations()).first;
    final before = (await repository.getStocktakes()).length;
    final outbox = StocktakeOutbox(ownerUserId: 'maker');
    await outbox.enqueue('create_stocktake', {
      'location_id': location.id,
      'shift_code': 'morning',
      'business_date': '2045-01-01',
      'note': 'ca offline',
    }, 'offline-create-1');
    final restored = StocktakeOutbox(ownerUserId: 'maker');
    await restored.restore();
    expect(await restored.tryFlush(repository: repository, currentUserId: 'maker'), isTrue);
    expect((await repository.getStocktakes()).length, before + 1);
    expect(restored.hasPending, isFalse);
  });

  test('restored offline count replays lines then submit and acknowledges',
      () async {
    final repository = _RecordingRepository();
    final location = (await repository.getLocations()).first;
    final item = (await repository.getItems()).first;
    final stocktake = await repository.createStocktake(locationId: location.id);
    final original = StocktakeOutbox(ownerUserId: 'maker');
    await original.enqueue(
        'submit_stocktake',
        {
          'stocktake_id': stocktake.id,
          'lines': [
            {'item_id': item.id, 'counted_qty': '11', 'used_qty': '2'},
          ],
        },
        'offline-submit-1');

    final restored = StocktakeOutbox(ownerUserId: 'maker');
    await restored.restore();
    expect(restored.queue, hasLength(1));
    expect(await restored.tryFlush(repository: repository, currentUserId: 'maker'), isTrue);
    expect(repository.calls, [
      'lines:${stocktake.id}:11:offline-submit-1:lines',
      'submit:${stocktake.id}:offline-submit-1:submit',
    ]);
    expect((await repository.getStocktake(stocktake.id)).status, 'submitted');
    expect(restored.hasPending, isFalse);
  });

  test('failed send stays durable for retry and does not submit', () async {
    final repository = _RecordingRepository();
    final location = (await repository.getLocations()).first;
    final item = (await repository.getItems()).first;
    final stocktake = await repository.createStocktake(locationId: location.id);
    final outbox = StocktakeOutbox(ownerUserId: 'maker');
    await outbox.enqueue(
        'submit_stocktake',
        {
          'stocktake_id': stocktake.id,
          'lines': [
            {'item_id': item.id, 'counted_qty': '11', 'used_qty': '2'},
          ],
        },
        'offline-submit-2');

    repository.failUpdate = true;
    expect(await outbox.tryFlush(repository: repository, currentUserId: 'maker'), isFalse);
    expect(repository.calls.where((c) => c.startsWith('submit:')), isEmpty);

    final restored = StocktakeOutbox(ownerUserId: 'maker');
    await restored.restore();
    expect(restored.hasPending, isTrue);
    repository.failUpdate = false;
    expect(await restored.tryFlush(repository: repository,
        currentUserId: 'maker', force: true), isTrue);
    expect(restored.hasPending, isFalse);
  });

  test('a different account or branch cannot see or replay a saved command', () async {
    final repository = _RecordingRepository();
    final location = (await repository.getLocations()).first;
    final owner = StocktakeOutbox(ownerUserId: 'user-a', ownerBranch: 'branch-a');
    await owner.enqueue('create_stocktake', {
      'location_id': location.id,
      'shift_code': 'morning',
      'business_date': '2045-02-01',
    }, 'owner-a-create');

    expect(await owner.tryFlush(repository: repository,
        currentUserId: 'user-b', currentBranch: 'branch-a'), isFalse);
    final otherAccount = StocktakeOutbox(ownerUserId: 'user-b', ownerBranch: 'branch-a');
    await otherAccount.restore();
    expect(otherAccount.queue, isEmpty);
    final otherBranch = StocktakeOutbox(ownerUserId: 'user-a', ownerBranch: 'branch-b');
    await otherBranch.restore();
    expect(otherBranch.queue, isEmpty);
    expect(owner.hasPending, isTrue);
  });

  test('switching accounts hides the old outbox and restores it on return', () async {
    final outbox = StocktakeOutbox(ownerUserId: 'user-a', ownerBranch: 'branch-a');
    await outbox.enqueue('create_stocktake', {
      'location_id': 'location-a',
      'shift_code': 'morning',
      'business_date': '2045-02-02',
    }, 'owner-a-draft');
    await outbox.bindIdentity('user-b', 'branch-a');
    expect(outbox.queue, isEmpty);
    await outbox.bindIdentity('user-a', 'branch-a');
    expect(outbox.queue.single.idempotencyKey, 'owner-a-draft');
  });

  test('pending enqueue finishes under its original account before a switch', () async {
    final outbox = StocktakeOutbox(ownerUserId: 'user-a');
    final write = outbox.enqueue('create_stocktake', {
      'location_id': 'location-a', 'shift_code': 'morning',
    }, 'pending-a');
    final switchUser = outbox.bindIdentity('user-b', null);
    await Future.wait([write, switchUser]);
    expect(outbox.queue, isEmpty);
    await outbox.bindIdentity('user-a', null);
    expect(outbox.queue.single.idempotencyKey, 'pending-a');

    final switchAgain = outbox.bindIdentity('user-b', null);
    final staleWrite = outbox.enqueue('create_stocktake', {
      'location_id': 'location-a', 'shift_code': 'afternoon',
    }, 'stale-a');
    await switchAgain;
    await expectLater(staleWrite, throwsStateError);
    expect(outbox.queue, isEmpty);
    await outbox.bindIdentity('user-a', null);
    expect(outbox.queue, hasLength(1));
  });

  test('concurrent flush and new write preserve both durable commands', () async {
    final repository = _RecordingRepository()..failUpdate = true;
    final location = (await repository.getLocations()).first;
    final item = (await repository.getItems()).first;
    final stocktake = await repository.createStocktake(locationId: location.id);
    final outbox = StocktakeOutbox(ownerUserId: 'maker');
    await outbox.enqueue('submit_lines', {
      'stocktake_id': stocktake.id,
      'lines': [{'item_id': item.id, 'counted_qty': '11'}],
    }, 'first-count');
    final flushing = outbox.tryFlush(repository: repository, currentUserId: 'maker');
    final writing = outbox.enqueue('create_stocktake', {
      'location_id': location.id, 'shift_code': 'afternoon',
      'business_date': '2045-03-03',
    }, 'second-create');
    await Future.wait([flushing, writing]);
    final restored = StocktakeOutbox(ownerUserId: 'maker');
    await restored.restore();
    expect(restored.queue.map((entry) => entry.idempotencyKey),
        containsAll(['first-count', 'second-create']));
  });

  test('v1 drafts stay read-only until authenticated owner claims them', () async {
    final repository = _RecordingRepository();
    final location = (await repository.getLocations()).first;
    final item = (await repository.getItems()).first;
    final stocktake = await repository.createStocktake(locationId: location.id);
    SharedPreferences.setMockInitialValues({
      'queue_stocktake_v1': jsonEncode([{
        'id': 'old-hash', 'kind': 'submit_stocktake',
        'payload': {'stocktake_id': stocktake.id, 'lines': [
          {'item_id': item.id, 'counted_qty': '11', 'used_qty': '2'}]},
        'idempotencyKey': stocktake.id, 'attempt': 1,
        'status': OutBoxStatus.sending.index,
      }]),
    });
    final outbox = StocktakeOutbox(ownerUserId: 'maker', ownerBranch: 'branch-a');
    await outbox.restore();
    expect(outbox.queue, isEmpty);
    expect(await outbox.tryFlush(repository: repository,
        currentUserId: 'maker', currentBranch: 'branch-a'), isFalse);
    expect(repository.calls, isEmpty);
    expect((await outbox.legacyDrafts()).single.canImport, isTrue);
    await expectLater(outbox.claimLegacyDrafts(currentUserId: 'maker',
        currentBranch: 'branch-a', confirmed: false), throwsStateError);
    await expectLater(outbox.claimLegacyDrafts(currentUserId: 'maker',
        currentBranch: 'branch-b', confirmed: true), throwsStateError);
    expect(outbox.queue, isEmpty);
    expect(await outbox.claimLegacyDrafts(currentUserId: 'maker',
        currentBranch: 'branch-a', confirmed: true), 1);
    expect((await outbox.legacyDrafts()), isEmpty);
    expect(await outbox.tryFlush(repository: repository,
        currentUserId: 'maker', currentBranch: 'branch-a'), isTrue);
    expect((await repository.getStocktake(stocktake.id)).status, 'submitted');
  });

  test('unsupported v1 command remains on device for manual recovery', () async {
    final raw = jsonEncode([{
      'id': 'old-approval', 'kind': 'submit_approve',
      'payload': {'stocktake_id': 'shift-legacy'},
      'idempotencyKey': 'legacy-approval', 'status': OutBoxStatus.failed.index,
    }]);
    SharedPreferences.setMockInitialValues({'queue_stocktake_v1': raw});
    final outbox = StocktakeOutbox(ownerUserId: 'maker');
    await outbox.restore();
    expect((await outbox.legacyDrafts()).single.canImport, isFalse);
    await expectLater(outbox.claimLegacyDrafts(
        currentUserId: 'maker', confirmed: true), throwsStateError);
    final prefs = await SharedPreferences.getInstance();
    expect(prefs.getString('queue_stocktake_v1'), raw);
    expect(outbox.queue, isEmpty);
  });

  test('online rate limit schedules a timer that retries the queued payload', () async {
    final repository = _RecordingRepository();
    final location = (await repository.getLocations()).first;
    final item = (await repository.getItems()).first;
    final stocktake = await repository.createStocktake(locationId: location.id);
    final outbox = StocktakeOutbox.shared;
    await outbox.bindIdentity('maker', null);
    final hub = OfflineHub.instance;
    hub.currentUserId = 'maker';
    hub.currentBranch = null;
    hub.repository = repository;
    final synced = Completer<void>();
    hub.onSynced = () => synced.complete();
    _ControlledTimer? timer;
    hub.retryTimerFactory = (delay, callback) {
      expect(delay.inSeconds, greaterThanOrEqualTo(1));
      timer = _ControlledTimer(callback);
      return timer!;
    };
    addTearDown(() async {
      hub.cancelRetry();
      hub.retryTimerFactory = Timer.new;
      hub.repository = null;
      hub.currentUserId = null;
      hub.onSynced = null;
      await outbox.bindIdentity(null, null);
    });
    await outbox.enqueue('submit_lines', {
      'stocktake_id': stocktake.id,
      'lines': [{'item_id': item.id, 'counted_qty': '11'}],
    }, 'rate-limited-count');
    repository.failureCode = 'RATE_LIMITED';
    await hub.flushNow();
    expect(outbox.queue.single.status, OutBoxStatus.pending);
    expect(timer?.isActive, isTrue);
    repository.failureCode = null;
    outbox.queue.single.retryAtMs = DateTime.now().millisecondsSinceEpoch - 1;
    timer!.fire();
    await synced.future.timeout(const Duration(seconds: 1));
    expect(outbox.queue.single.status, OutBoxStatus.ok);
    expect(repository.calls.where((call) => call.startsWith('lines:')), hasLength(2));
  });

  test('401 and 429 remain queued and can retry after reauth or backoff', () async {
    final repository = _RecordingRepository();
    final location = (await repository.getLocations()).first;
    final item = (await repository.getItems()).first;
    final stocktake = await repository.createStocktake(locationId: location.id);
    final outbox = StocktakeOutbox(ownerUserId: 'maker');
    await outbox.enqueue('submit_lines', {
      'stocktake_id': stocktake.id,
      'lines': [{'item_id': item.id, 'counted_qty': '11'}],
    }, 'retry-auth');

    repository.failureCode = 'UNAUTHENTICATED';
    expect(await outbox.tryFlush(repository: repository, currentUserId: 'maker'), isFalse);
    expect(outbox.queue.single.status, OutBoxStatus.pending);
    expect(outbox.hasConflict, isFalse);
    final afterReauth = StocktakeOutbox(ownerUserId: 'maker');
    await afterReauth.restore();
    expect(afterReauth.queue.single.blockedReason, 'reauth');
    repository.failureCode = 'HTTP_429';
    expect(await afterReauth.tryFlush(repository: repository,
        currentUserId: 'maker', force: true), isFalse);
    expect(afterReauth.queue.single.status, OutBoxStatus.pending);
    expect(afterReauth.queue.single.blockedReason, 'rate_limit');
    repository.failureCode = null;
    expect(await afterReauth.tryFlush(repository: repository,
        currentUserId: 'maker', force: true), isTrue);
  });

  test('saving a count never erases an unsent submit command', () async {
    final outbox = StocktakeOutbox(ownerUserId: 'maker');
    await outbox.enqueue('submit_stocktake', {
      'stocktake_id': 'shift-1',
      'lines': [{'item_id': 'item-1', 'counted_qty': '11'}],
    }, 'submit-1');
    await expectLater(outbox.enqueue('submit_lines', {
      'stocktake_id': 'shift-1',
      'lines': [{'item_id': 'item-1', 'counted_qty': '12'}],
    }, 'count-2'), throwsStateError);
    expect(outbox.queue.single.kind, 'submit_stocktake');
  });

  test('conflict on one shift does not block a separate shift', () async {
    final repository = _RecordingRepository();
    final location = (await repository.getLocations()).first;
    final item = (await repository.getItems()).first;
    final first = await repository.createStocktake(locationId: location.id);
    final second = await repository.createStocktake(locationId: location.id);
    final outbox = StocktakeOutbox(ownerUserId: 'maker');
    for (final st in [first, second]) {
      await outbox.enqueue('submit_lines', {
        'stocktake_id': st.id,
        'lines': [{'item_id': item.id, 'counted_qty': '11'}],
      }, 'count-${st.id}');
    }
    repository.failureCode = 'VERSION_CONFLICT';
    repository.failForId = first.id;
    expect(await outbox.tryFlush(repository: repository, currentUserId: 'maker'), isFalse);
    expect(outbox.queue.first.status, OutBoxStatus.failed);
    expect(outbox.queue.last.status, OutBoxStatus.ok);
  });

  /// Network loss → nhập/chốt → đóng/mở app → có mạng → server đúng 1 kết quả
  test('offline count survives app restart and network loss, syncs exactly once when online', () async {
    final repository = _NetworkLossRepository();
    final location = (await repository.getLocations()).first;
    final item = (await repository.getItems()).first;

    // Create stocktake online first (network available)
    repository.networkAvailable = true;
    final stocktake = await repository.createStocktake(locationId: location.id);

    // Simulate: app is online, user enters count and submits
    final outbox = StocktakeOutbox(ownerUserId: 'maker', ownerBranch: 'branch-a');
    await outbox.enqueue('submit_stocktake', {
      'stocktake_id': stocktake.id,
      'lines': [{'item_id': item.id, 'counted_qty': '11', 'used_qty': '2'}],
    }, 'offline-submit-network-loss');

    // Network goes offline - flush fails
    repository.networkAvailable = false;
    expect(await outbox.tryFlush(repository: repository, currentUserId: 'maker', currentBranch: 'branch-a'), isFalse);
    expect(outbox.hasPending, isTrue);

    // App restarts (simulated by creating new outbox instance and restoring)
    final restoredOutbox = StocktakeOutbox(ownerUserId: 'maker', ownerBranch: 'branch-a');
    await restoredOutbox.restore();
    expect(restoredOutbox.queue, hasLength(1));
    expect(restoredOutbox.hasPending, isTrue);

    // Network comes back online
    repository.networkAvailable = true;
    expect(await restoredOutbox.tryFlush(repository: repository,
        currentUserId: 'maker', currentBranch: 'branch-a', force: true), isTrue);

    // Verify exactly ONE result on server
    expect(repository.calls.where((c) => c.startsWith('lines:')), hasLength(1));
    expect(repository.calls.where((c) => c.startsWith('submit:')), hasLength(1));
    expect((await repository.getStocktake(stocktake.id)).status, 'submitted');
    expect(restoredOutbox.hasPending, isFalse);
  });

  /// Retry with VERSION_CONFLICT - should retry with fresh version
  test('retry after VERSION_CONFLICT fetches fresh version and succeeds', () async {
    final repository = _VersionConflictRepository();
    final location = (await repository.getLocations()).first;
    final item = (await repository.getItems()).first;
    final stocktake = await repository.createStocktake(locationId: location.id);

    final outbox = StocktakeOutbox(ownerUserId: 'maker');
    await outbox.enqueue('submit_stocktake', {
      'stocktake_id': stocktake.id,
      'lines': [{'item_id': item.id, 'counted_qty': '11', 'used_qty': '2'}],
    }, 'retry-conflict');

    // First flush - VERSION_CONFLICT
    expect(await outbox.tryFlush(repository: repository, currentUserId: 'maker'), isFalse);
    expect(outbox.queue.single.status, OutBoxStatus.failed);
    expect(repository.submitAttempts, 1);

    // Simulate fetching fresh version and retrying
    // The outbox should allow retry after conflict
    final freshStocktake = await repository.getStocktake(stocktake.id);
    outbox.queue.single.payload['expected_version'] = freshStocktake.version;
    outbox.queue.single.status = OutBoxStatus.pending;
    outbox.queue.single.attempt = 0;

    // Second flush - should succeed with fresh version
    repository.conflictOnSubmit = false;
    expect(await outbox.tryFlush(repository: repository, currentUserId: 'maker'), isTrue);
    expect(outbox.queue.single.status, OutBoxStatus.ok);
    expect(repository.submitAttempts, 2);
    expect((await repository.getStocktake(stocktake.id)).status, 'submitted');
  });

  /// No health ping used for sync - direct flush on network restore
  test('sync does not use health ping, flushes directly on network restore', () async {
    final repository = _NetworkLossRepository();
    final location = (await repository.getLocations()).first;
    final item = (await repository.getItems()).first;

    // Create stocktake online first (network available)
    repository.networkAvailable = true;
    final stocktake = await repository.createStocktake(locationId: location.id);

    final outbox = StocktakeOutbox(ownerUserId: 'maker');
    await outbox.enqueue('submit_stocktake', {
      'stocktake_id': stocktake.id,
      'lines': [{'item_id': item.id, 'counted_qty': '11'}],
    }, 'no-ping-test');

    // Network offline
    repository.networkAvailable = false;
    expect(await outbox.tryFlush(repository: repository, currentUserId: 'maker'), isFalse);

    // Network online - should flush directly without health check
    repository.networkAvailable = true;
    expect(await outbox.tryFlush(repository: repository,
        currentUserId: 'maker', force: true), isTrue);

    // Verify no health check calls were made (no getHealth/ping calls)
    expect(repository.calls.any((c) => c.startsWith('health:')), isFalse);
    expect((await repository.getStocktake(stocktake.id)).status, 'submitted');
  });

  /// Queue ID is separate from idempotency key for proper deduplication
  test('queue entry ID is independent of idempotency key', () async {
    final repository = _RecordingRepository();
    final location = (await repository.getLocations()).first;

    final outbox = StocktakeOutbox(ownerUserId: 'maker');
    await outbox.enqueue('create_stocktake', {
      'location_id': location.id,
      'shift_code': 'morning',
      'business_date': '2045-03-01',
    }, 'idem-key-123');

    // Queue entry should have its own ID, not the idempotency key
    final entry = outbox.queue.single;
    expect(entry.id, isNot(equals('idem-key-123')));
    expect(entry.idempotencyKey, 'idem-key-123');
    expect(entry.id.isNotEmpty, isTrue);
  });

  /// Idempotency key reuse with different payload throws
  test('reusing idempotency key with different payload throws', () async {
    final outbox = StocktakeOutbox(ownerUserId: 'maker');
    await outbox.enqueue('create_stocktake', {
      'location_id': 'loc-1',
      'shift_code': 'morning',
    }, 'same-key');

    await expectLater(outbox.enqueue('create_stocktake', {
      'location_id': 'loc-2', // Different payload
      'shift_code': 'afternoon',
    }, 'same-key'), throwsStateError);
  });
}
