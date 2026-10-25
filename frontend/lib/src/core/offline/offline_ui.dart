/// Nút online/offline + banner "Ngoại tuyến - sẽ đồng bộ" (SRS §4.2).
///
/// Hub duy nhất điều khiển trạng thái mạng và danh sách tác vụ đang chờ
/// đồng bộ. Cập nhật từ các màn/tương tác; khi online, các tác vụ trong
/// [StocktakeOutbox] được flush lại kịp thời.
library;

import 'package:flutter/material.dart';
import 'dart:async';

import '../i18n/app_i18n.dart';
import '../../data/repositories/bankops_repository.dart';
import 'stocktake_outbox.dart';

/// Trạng thái của OfflineHub.
class _OfflineState {
  _OfflineState();

  bool offline = false;
  int pending = 0;
  int failed = 0;
}

/// Hub duy nhất (singleton) điều khiển trạng thái mạng + outbox UI.
class OfflineHub {
  OfflineHub._();

  static final OfflineHub instance = OfflineHub._();

  final List<VoidCallback> _listeners = [];
  final _state = _OfflineState();
  BankOpsRepository? repository;
  String? currentUserId;
  String? currentBranch;
  VoidCallback? onSynced;
  Timer? _retryTimer;
  int _legacyCount = 0;
  Timer Function(Duration, void Function()) retryTimerFactory = Timer.new;

  bool get offline => _state.offline;
  int get pending => _state.pending;
  int get failed => _state.failed;
  int get legacyCount => _legacyCount;
  List<OutBoxEntry> get queue => StocktakeOutbox.shared.queue;
  bool get hasPending =>
      _state.pending > 0 || StocktakeOutbox.shared.hasPending;

  /// Địa chỉ health-check của backend, dùng khi flush outbound (offline). Có thể
  /// cập nhật từ [AppShell] khi biết API_BASE_URL (mặc định localhost:8000).
  String pingUrl = 'http://localhost:8000/health/live';

  void listen(void Function() fn) {
    _listeners.add(fn);
  }

  void unlisten(void Function() fn) {
    _listeners.remove(fn);
  }

  void _notify() {
    for (final fn in _listeners) {
      fn();
    }
  }

  /// Gọi khi thiết bị mất kết nối (ví dụ HttpClient trả lỗi khi flush).
  void markOffline() {
    _retryTimer?.cancel();
    _retryTimer = null;
    if (!_state.offline) {
      _state.offline = true;
      _state.pending = StocktakeOutbox.shared.hasPending ? 1 : 0;
      _notify();
    }
  }

  /// Gọi khi thiết bị quay lại kết nối.
  void markOnline() {
    if (_state.offline) {
      _state.offline = false;
      _state.pending = 0;
      _state.failed = 0;
      // Auto-flush outbox when connection restores to sync pending stocktake data
      if (StocktakeOutbox.shared.hasPending) {
        _state.pending = 1; // show sync in progress
        _notify();
        flushNow(force: true);
      } else {
        _notify();
      }
    }
    _scheduleRetry();
  }

  void cancelRetry() {
    _retryTimer?.cancel();
    _retryTimer = null;
  }

  void _scheduleRetry() {
    cancelRetry();
    if (_state.offline || repository == null || currentUserId == null) return;
    final retryAt = StocktakeOutbox.shared.nextRetryAtMs;
    if (retryAt == null) return;
    final waitMs = retryAt - DateTime.now().millisecondsSinceEpoch;
    final delay = Duration(milliseconds: waitMs > 1000 ? waitMs : 1000);
    _retryTimer = retryTimerFactory(delay, () {
      _retryTimer = null;
      flushNow();
    });
  }

  Future<void> refreshLegacy() async {
    _legacyCount = (await StocktakeOutbox.shared.legacyDrafts()).length;
    _notify();
  }

  Future<int> claimLegacy() async {
    final userId = currentUserId;
    if (userId == null) throw StateError('Cần đăng nhập để khôi phục kiểm kê');
    final imported = await StocktakeOutbox.shared.claimLegacyDrafts(
        currentUserId: userId, currentBranch: currentBranch, confirmed: true);
    await refreshLegacy();
    addQueued();
    await flushNow(force: true);
    return imported;
  }

  /// Tác vụ trong queue thất bại khi flush -> đếm + giữ ở pending.
  void recordFailed() {
    _state.failed++;
    _state.pending = StocktakeOutbox.shared.hasPending ? 1 : 0;
    _notify();
  }

  /// Tạo tác vụ offline mới trong queue (gọi từ repository khi submit bị lỗi mạng).
  void addQueued() {
    _state.pending = StocktakeOutbox.shared.hasPending ? 1 : 0;
    _state.failed = StocktakeOutbox.shared.hasConflict ? 1 : 0;
    _notify();
    _scheduleRetry();
  }

  /// Flush toàn bộ queue ngay (dùng khi người dùng bấm "Thử lại").
  Future<void> flushNow({bool force = false}) async {
    final repo = repository;
    final userId = currentUserId;
    if (repo == null || userId == null || !StocktakeOutbox.shared.hasPending) return;
    try {
      final synced = await StocktakeOutbox.shared.tryFlush(
        repository: repo, currentUserId: userId,
        currentBranch: currentBranch, force: force,
      );
      if (synced) onSynced?.call();
    } finally {
      _state.pending = StocktakeOutbox.shared.hasPending ? 1 : 0;
      _state.failed = StocktakeOutbox.shared.hasConflict ? 1 : 0;
      _notify();
      _scheduleRetry();
    }
  }

  Future<void> discardConflicts() async {
    await StocktakeOutbox.shared.discardConflicts();
    _state.pending = StocktakeOutbox.shared.hasPending ? 1 : 0;
    _state.failed = 0;
    _notify();
  }
}

/// Banner hiển thị khi mạng yếu/mất kết nối; cung cấp nút "Thử lại".
class OfflineBanner extends StatelessWidget {
  const OfflineBanner({super.key, this.pending = 0});

  final int pending;

  @override
  Widget build(BuildContext context) {
    final legacyCount = OfflineHub.instance.legacyCount;
    if (pending <= 0 && legacyCount <= 0) return const SizedBox.shrink();

    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;
    final color = isDark ? const Color(0xFF7C3AED) : const Color(0xFF2563EB);

    return AnimatedOpacity(
      opacity: 1.0,
      duration: const Duration(milliseconds: 250),
      child: Container(
        width: double.infinity,
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
        decoration: BoxDecoration(
          color: color.withValues(alpha: 0.12),
          borderRadius: BorderRadius.circular(12),
          border: Border.all(color: color.withValues(alpha: 0.5)),
        ),
        child: Row(
          children: [
            const Icon(Icons.cloud_off_outlined, color: Colors.orangeAccent),
            const SizedBox(width: 10),
            Expanded(
              child: Text(
                legacyCount > 0
                    ? (context.isVietnamese
                        ? 'Có $legacyCount bản kiểm kê từ phiên bản cũ cần xác nhận chủ sở hữu.'
                        : '$legacyCount legacy stocktake drafts need owner confirmation.')
                    : OfflineHub.instance.failed > 0
                    ? (context.isVietnamese
                        ? 'Kiểm kê có xung đột; cần kiểm tra dữ liệu trước khi gửi lại'
                        : 'Stocktake conflict needs review before retry')
                    : StocktakeOutbox.shared.requiresReauth
                        ? (context.isVietnamese
                            ? 'Phiên đăng nhập hết hạn. Đăng nhập lại rồi thử đồng bộ kiểm kê.'
                            : 'Session expired. Sign in again to sync stocktake.')
                        : StocktakeOutbox.shared.rateLimited
                            ? (context.isVietnamese
                                ? 'Máy chủ đang giới hạn truy cập; kiểm kê sẽ được gửi lại sau.'
                                : 'Rate limited. Stocktake will retry later.')
                    : (context.isVietnamese
                        ? 'Ngoại tuyến - sẽ đồng bộ khi kết nối lại'
                        : 'Offline - will synchronize when connection restores'),
                style: TextStyle(
                    color: isDark ? Colors.white70 : Colors.black87,
                    fontSize: 13),
              ),
            ),
            if (legacyCount > 0)
              FilledButton.icon(
                onPressed: () => _recoverLegacy(context),
                icon: const Icon(Icons.inventory_2_outlined, size: 16),
                label: Text(context.isVietnamese ? 'Khôi phục' : 'Recover'),
              )
            else if (pending > 0)
              FilledButton.icon(
                onPressed: () => OfflineHub.instance.failed > 0
                    ? _resolveConflict(context)
                    : _retry(context, pending),
                icon: const Icon(Icons.refresh, size: 16),
                label: Text(OfflineHub.instance.failed > 0
                    ? (context.isVietnamese ? 'Xử lý' : 'Review')
                    : (context.isVietnamese
                        ? 'Thử lại ($pending)'
                        : 'Retry ($pending)')),
              )
            else
              const SizedBox(width: 24),
          ],
        ),
      ),
    );
  }

  static void _retry(BuildContext context, int pending) {
    OfflineHub.instance.flushNow(force: true);
    if (context.mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            context.isVietnamese
                ? 'Đang thử gửi lại $pending ca đồng bộ...'
                : 'Retrying sync for $pending sessions...',
          ),
        ),
      );
    }
  }

  static Future<void> _recoverLegacy(BuildContext context) async {
    try {
      final drafts = await StocktakeOutbox.shared.legacyDrafts();
      if (!context.mounted || drafts.isEmpty) return;
      final owner = OfflineHub.instance.currentUserId;
      final branch = OfflineHub.instance.currentBranch;
      if (owner == null) return;
      final canImport = drafts.every((draft) => draft.canImport);
      final confirmed = await showDialog<bool>(
        context: context,
        builder: (dialog) => AlertDialog(
          title: const Text('Khôi phục kiểm kê cũ'),
          content: SingleChildScrollView(
            child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('Dữ liệu này chưa gắn tài khoản. Chỉ nhập nếu bạn xác nhận các ca dưới đây thuộc tài khoản $owner, chi nhánh ${branch ?? "mặc định"}.'),
                const SizedBox(height: 12),
                for (final draft in drafts)
                  Text('• ${draft.kind} · ${draft.stocktakeId ?? "ca mới"} · ${draft.lineCount} dòng${draft.canImport ? "" : " (cần đối chiếu thủ công)"}'),
                if (!canImport) ...[
                  const SizedBox(height: 12),
                  const Text('Có lệnh cũ không hỗ trợ nhập tự động. Dữ liệu gốc vẫn được giữ trên thiết bị.'),
                ],
              ],
            ),
          ),
          actions: [
            TextButton(onPressed: () => Navigator.pop(dialog, false), child: const Text('Giữ lại')),
            FilledButton(
              onPressed: canImport ? () => Navigator.pop(dialog, true) : null,
              child: const Text('Xác nhận sở hữu và nhập'),
            ),
          ],
        ),
      );
      if (confirmed != true) return;
      if (owner != OfflineHub.instance.currentUserId ||
          branch != OfflineHub.instance.currentBranch) {
        throw StateError('Phiên đăng nhập đã thay đổi');
      }
      final imported = await OfflineHub.instance.claimLegacy();
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(
          content: Text('Đã nhập $imported lệnh kiểm kê cũ; đang đồng bộ.'),
        ));
      }
    } catch (error) {
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(
          content: Text('Chưa thể khôi phục: $error'),
        ));
      }
    }
  }

  static Future<void> _resolveConflict(BuildContext context) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (dialog) => AlertDialog(
        title: const Text('Xung đột kiểm kê'),
        content: const Text('Máy chủ đã thay đổi số liệu. Bản nháp đếm trên thiết bị vẫn được giữ. Bỏ tác vụ đồng bộ cũ để mở lại ca và đối chiếu trước khi gửi?'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(dialog, false), child: const Text('Giữ lại')),
          FilledButton(onPressed: () => Navigator.pop(dialog, true), child: const Text('Bỏ tác vụ cũ')),
        ],
      ),
    );
    if (confirmed == true) await OfflineHub.instance.discardConflicts();
  }
}
