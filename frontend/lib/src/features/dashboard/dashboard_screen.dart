import 'package:flutter/material.dart';

import '../../app/app_shell.dart';
import '../../core/i18n/app_i18n.dart';
import '../../core/sync/data_sync_controller.dart';
import '../../core/util/formatting.dart';
import '../../core/util/role_visibility.dart';
import '../../core/widgets/app_toast.dart';
import '../../core/widgets/state_views.dart';
import '../../data/models/dtos.dart';
import '../../data/repositories/bankops_repository.dart';
import '../cash/cash_adjustment.dart';
import '../cash/cash_screen.dart';
import 'dashboard_trust_metrics.dart';

typedef DashboardNavigateCallback = void Function(
  int index, {
  String? category,
  String? stockFilter,
  String? viewMode,
  String? locationId,
  bool autoOpenStock,
  bool autoOpenCash,
});

class DashboardScreen extends StatefulWidget {
  const DashboardScreen({super.key, this.onNavigate});

  /// Điều hướng sang tab AppShell (full index). `null` = chế độ xem tĩnh
  /// (test/widget độc lập): quick action hiện snackbar hướng dẫn như cũ.
  final DashboardNavigateCallback? onNavigate;

  @override
  State<DashboardScreen> createState() => _DashboardScreenState();
}

class _DashboardScreenState extends State<DashboardScreen> {
  static DashboardData? _cachedData;
  Future<DashboardData>? _future;
  DataSyncController? _syncController;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    final repo = RepositoryScope.of(context);
    final user = SessionScope.maybeOf(context)?.user;
    if (_cachedData != null) {
      _future = Future.value(_cachedData);
      _revalidateSilently(repo, user);
    } else {
      _future ??= _load(repo, user);
    }

    final sync = SyncScope.maybeOf(context);
    if (sync != _syncController) {
      _syncController?.removeListener(_onSyncUpdate);
      _syncController = sync;
      _syncController?.addListener(_onSyncUpdate);
    }
  }

  void _onSyncUpdate() {
    if (!mounted) return;
    final last = _syncController?.lastEvent;
    // Bỏ qua heartbeat_poll định kỳ để không làm giật/reset giao diện nếu không có sự kiện thay đổi
    if (last?.action == 'heartbeat_poll') {
      return;
    }
    if (last == null ||
        last.topic == SyncTopic.dashboard ||
        last.topic == SyncTopic.inventory ||
        last.topic == SyncTopic.stocktake ||
        last.topic == SyncTopic.approvals ||
        last.topic == SyncTopic.all) {
      _refresh();
    }
  }

  @override
  void dispose() {
    _syncController?.removeListener(_onSyncUpdate);
    super.dispose();
  }

  Future<void> _refresh() async {
    final repo = RepositoryScope.of(context);
    final user = SessionScope.maybeOf(context)?.user;
    setState(() {
      _future = _load(repo, user);
    });
  }

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<DashboardData>(
      future: _future,
      builder: (context, snapshot) {
        if (snapshot.hasError && !snapshot.hasData) {
          return Center(
            child: ErrorView(
              message: '${snapshot.error}',
              onRetry: _refresh,
            ),
          );
        }
        if (!snapshot.hasData) {
          return const Center(child: LoadingView());
        }
        final data = snapshot.data!;

        final width = MediaQuery.sizeOf(context).width;
        final isWide = width >= 1000;
        final user = SessionScope.maybeOf(context)?.user;
        final roles = RoleVisibility.rolesOf(user);
        final canApprove = RoleVisibility.canApprove(roles);

        return RefreshIndicator(
          onRefresh: _refresh,
          child: CustomScrollView(
            slivers: [
              SliverToBoxAdapter(
                child: _DashboardHeader(data: data, canApprove: canApprove),
              ),
              SliverPadding(
                padding: const EdgeInsets.fromLTRB(20, 16, 20, 16),
                sliver: SliverToBoxAdapter(
                  child: SummaryCard(
                    data: data,
                    onNavigate: widget.onNavigate,
                  ),
                ),
              ),
              if (data.lowStockAlerts.isNotEmpty)
                SliverPadding(
                  padding: const EdgeInsets.fromLTRB(20, 0, 20, 16),
                  sliver: SliverToBoxAdapter(
                    child: Container(
                      padding: const EdgeInsets.all(14),
                      decoration: BoxDecoration(
                        color: const Color(0xFFEF4444).withValues(alpha: 0.1),
                        borderRadius: BorderRadius.circular(12),
                        border: Border.all(
                            color:
                                const Color(0xFFEF4444).withValues(alpha: 0.3)),
                      ),
                      child: Row(
                        children: [
                          const Icon(Icons.warning_amber_rounded,
                              color: Color(0xFFDC2626), size: 22),
                          const SizedBox(width: 12),
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text(
                                  'Cảnh báo vận hành: ${data.lowStockAlerts.length} nguyên liệu đang thấp hơn định mức an toàn',
                                  style: const TextStyle(
                                      fontWeight: FontWeight.bold,
                                      fontSize: 13,
                                      color: Color(0xFFDC2626)),
                                ),
                                const SizedBox(height: 2),
                                Text(
                                  'Cần lập phiếu nhập hoặc chuyển kho bổ sung để bảo đảm giao dịch quầy không bị gián đoạn.',
                                  style: TextStyle(
                                      fontSize: 12,
                                      color: Theme.of(context)
                                          .colorScheme
                                          .onSurfaceVariant),
                                ),
                              ],
                            ),
                          ),
                          const SizedBox(width: 12),
                          FilledButton.tonal(
                            onPressed: () => widget.onNavigate?.call(1),
                            style: FilledButton.styleFrom(
                              backgroundColor: const Color(0xFFDC2626)
                                  .withValues(alpha: 0.15),
                              foregroundColor: const Color(0xFFDC2626),
                              visualDensity: VisualDensity.compact,
                            ),
                            child: const Text('Xem Chi Tiết Kho',
                                style: TextStyle(
                                    fontWeight: FontWeight.bold, fontSize: 12)),
                          ),
                        ],
                      ),
                    ),
                  ),
                ),
              SliverPadding(
                padding: const EdgeInsets.symmetric(horizontal: 20),
                sliver: SliverToBoxAdapter(
                  child: _buildCashboxDistribution(context, data),
                ),
              ),
              SliverPadding(
                padding: const EdgeInsets.fromLTRB(20, 16, 20, 0),
                sliver: SliverToBoxAdapter(
                  child: _buildQuickActions(context),
                ),
              ),
              SliverPadding(
                padding: const EdgeInsets.fromLTRB(20, 20, 20, 20),
                sliver: SliverToBoxAdapter(
                  child: isWide
                      ? Row(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Expanded(
                              flex: 6,
                              child: _buildInventoryBreakdown(context, data),
                            ),
                            const SizedBox(width: 20),
                            Expanded(
                              flex: 5,
                              child: canApprove
                                  ? _buildApprovalQueue(context, data)
                                  : _buildMakerRequestQueue(context, data),
                            ),
                          ],
                        )
                      : Column(
                          children: [
                            _buildInventoryBreakdown(context, data),
                            const SizedBox(height: 20),
                            canApprove
                                ? _buildApprovalQueue(context, data)
                                : _buildMakerRequestQueue(context, data),
                          ],
                        ),
                ),
              ),
              SliverPadding(
                padding: const EdgeInsets.fromLTRB(20, 0, 20, 32),
                sliver: DashboardKpiGrid(
                  data: data,
                  onNavigate: widget.onNavigate,
                ),
              ),
            ],
          ),
        );
      },
    );
  }

  Future<void> _showCashAdjustmentModal(
    Cashbox box,
    double currentAmount,
  ) async {
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;
    final amountCtrl = TextEditingController(
      text: currentAmount > 0 ? currentAmount.toStringAsFixed(0) : '',
    );
    final reasonCtrl = TextEditingController(
      text: 'Đối soát số dư thực tế quầy ca trực',
    );

    final updated = await showModalBottomSheet<bool>(
      context: context,
      isScrollControlled: true,
      backgroundColor: isDark ? const Color(0xFF1E293B) : Colors.white,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
      ),
      builder: (ctx) {
        return Padding(
          padding: EdgeInsets.only(
            left: 20,
            right: 20,
            top: 20,
            bottom: MediaQuery.of(ctx).viewInsets.bottom + 20,
          ),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  Row(
                    children: [
                      Container(
                        padding: const EdgeInsets.all(8),
                        decoration: BoxDecoration(
                          color: const Color(0xFF059669).withValues(alpha: 0.12),
                          borderRadius: BorderRadius.circular(10),
                        ),
                        child: const Icon(
                          Icons.tune_rounded,
                          color: Color(0xFF059669),
                          size: 20,
                        ),
                      ),
                      const SizedBox(width: 12),
                      Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          const Text(
                            'Kiểm Tra & Tùy Chỉnh Két / Quầy',
                            style: TextStyle(
                                fontSize: 16, fontWeight: FontWeight.w800),
                          ),
                          Text(
                            box.name,
                            style: TextStyle(
                              fontSize: 13,
                              color: theme.colorScheme.onSurfaceVariant,
                              fontWeight: FontWeight.w600,
                            ),
                          ),
                        ],
                      ),
                    ],
                  ),
                  IconButton(
                    icon: const Icon(Icons.close),
                    onPressed: () => Navigator.of(ctx).pop(false),
                  ),
                ],
              ),
              const SizedBox(height: 16),
              Container(
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(
                  color: isDark
                      ? const Color(0xFF0F172A)
                      : const Color(0xFFF1F5F9),
                  borderRadius: BorderRadius.circular(12),
                ),
                child: Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    Text(
                      'Số dư sổ sách hiện tại:',
                      style: TextStyle(
                          fontSize: 13,
                          color: theme.colorScheme.onSurfaceVariant),
                    ),
                    Text(
                      '${AppFormat.money(currentAmount.toStringAsFixed(0))} ₫',
                      style: const TextStyle(
                          fontSize: 14, fontWeight: FontWeight.w800),
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 16),
              TextField(
                controller: amountCtrl,
                keyboardType: TextInputType.number,
                decoration: const InputDecoration(
                  labelText: 'Số tiền kiểm đếm thực tế (VND)',
                  hintText: 'Nhập số tiền kiểm đếm...',
                  suffixText: '₫',
                  border: OutlineInputBorder(),
                  prefixIcon: Icon(Icons.payments_outlined),
                ),
              ),
              const SizedBox(height: 10),
              Wrap(
                spacing: 8,
                children: [
                  ActionChip(
                    label: const Text('+ 500.000 ₫',
                        style: TextStyle(fontSize: 11)),
                    onPressed: () {
                      final cur = double.tryParse(amountCtrl.text
                              .replaceAll('.', '')
                              .replaceAll(',', '')
                              .trim()) ??
                          0;
                      amountCtrl.text =
                          AppFormat.money((cur + 500000).toStringAsFixed(0));
                    },
                  ),
                  ActionChip(
                    label: const Text('+ 1.000.000 ₫',
                        style: TextStyle(fontSize: 11)),
                    onPressed: () {
                      final cur = double.tryParse(amountCtrl.text
                              .replaceAll('.', '')
                              .replaceAll(',', '')
                              .trim()) ??
                          0;
                      amountCtrl.text =
                          AppFormat.money((cur + 1000000).toStringAsFixed(0));
                    },
                  ),
                  ActionChip(
                    label: const Text('+ 2.000.000 ₫',
                        style: TextStyle(fontSize: 11)),
                    onPressed: () {
                      final cur = double.tryParse(amountCtrl.text
                              .replaceAll('.', '')
                              .replaceAll(',', '')
                              .trim()) ??
                          0;
                      amountCtrl.text =
                          AppFormat.money((cur + 2000000).toStringAsFixed(0));
                    },
                  ),
                ],
              ),
              const SizedBox(height: 14),
              TextField(
                controller: reasonCtrl,
                decoration: const InputDecoration(
                  labelText: 'Lý do / Nội dung kiểm tra',
                  hintText: 'VD: Bàn giao ca sáng, nộp tiền két...',
                  border: OutlineInputBorder(),
                  prefixIcon: Icon(Icons.edit_note_rounded),
                ),
              ),
              const SizedBox(height: 12),
              Container(
                padding: const EdgeInsets.all(10),
                decoration: BoxDecoration(
                  color: isDark
                      ? const Color(0xFF0F172A)
                      : const Color(0xFFFFF7ED),
                  borderRadius: BorderRadius.circular(10),
                  border: Border.all(
                      color: const Color(0xFFD97706).withValues(alpha: 0.35)),
                ),
                child: const Text(
                  'Số dư KHÔNG đổi ngay: hệ thống tạo phiếu điều chỉnh (journal) '
                  'và gửi duyệt. Số dư chỉ cập nhật sau khi quản lý phê duyệt.',
                  style: TextStyle(fontSize: 12),
                ),
              ),
              const SizedBox(height: 20),
              Row(
                children: [
                  Expanded(
                    child: OutlinedButton(
                      onPressed: () => Navigator.of(ctx).pop(false),
                      child: const Text('Hủy'),
                    ),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: FilledButton.icon(
                      icon: const Icon(Icons.check, size: 18),
                      label: const Text('Lưu & Cập nhật'),
                      onPressed: () => Navigator.of(ctx).pop(true),
                    ),
                  ),
                ],
              ),
            ],
          ),
        );
      },
    );

    if (updated == true && mounted) {
      final repo = RepositoryScope.of(context);
      final counted = parseVndAmount(amountCtrl.text);
      if (counted == null) {
        AppToast.error(context,
            'Vui lòng nhập số tiền kiểm đếm thực tế (VD: 2.000.000).');
        return;
      }
      final delta = counted - currentAmount;
      if (delta == 0) {
        AppToast.info(context,
            'Số dư đã khớp sổ sách — không cần tạo phiếu điều chỉnh.');
        return;
      }
      try {
        // Số dư KHÔNG ghi trực tiếp (backend chặn 422
        // DIRECT_BALANCE_WRITE_FORBIDDEN): tạo phiếu điều chỉnh + gửi duyệt.
        final created = await submitCashAdjustment(
          repo: repo,
          cashboxId: box.id,
          amount: delta.abs().toStringAsFixed(2),
          increase: delta > 0,
          reason: reasonCtrl.text.trim(),
        );
        if (!mounted) return;
        AppToast.success(context,
            'Đã tạo phiếu điều chỉnh ${created.id} — đang chờ duyệt. '
            'Số dư ${box.name} chỉ cập nhật sau khi quản lý phê duyệt.');
        _refresh();
      } catch (e) {
        if (!mounted) return;
        AppToast.error(context, cashAdjustmentErrorMessage(e));
      }
    }
  }

  Widget _buildCashboxDistribution(BuildContext context, DashboardData data) {
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;

    // Quyền ghi bút toán điều chỉnh tài chính (capability từ auth store).
    final canAdjustCash = RoleVisibility.canPostCashAdjustment(
      SessionScope.maybeOf(context)?.user,
    );

    final colors = [
      const Color(0xFF2563EB),
      const Color(0xFF059669),
      const Color(0xFF7C3AED),
      const Color(0xFFD97706),
      const Color(0xFF0891B2),
    ];

    final boxAmounts = <String, double>{};
    for (final b in data.cashBalances) {
      boxAmounts[b.cashboxId] = double.tryParse(b.amount) ?? 0;
    }

    final totalCash = boxAmounts.values.fold<double>(0, (sum, v) => sum + v);
    final hasCashSource = data.cashboxes.isNotEmpty;

    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: isDark ? const Color(0xFF1E293B) : Colors.white,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(
          color: theme.colorScheme.outlineVariant.withValues(alpha: 0.5),
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Expanded(
                child: Row(
                  children: [
                    Container(
                      padding: const EdgeInsets.all(8),
                      decoration: BoxDecoration(
                        color: const Color(0xFF059669).withValues(alpha: 0.12),
                        borderRadius: BorderRadius.circular(10),
                      ),
                      child: const Icon(
                        Icons.account_balance_wallet_rounded,
                        color: Color(0xFF059669),
                        size: 20,
                      ),
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            context.isVietnamese
                                ? 'Quỹ tiền mặt & Ca trực chi nhánh'
                                : 'Store Cash & Shift Safes',
                            style: theme.textTheme.titleMedium?.copyWith(
                              fontWeight: FontWeight.w800,
                            ),
                            overflow: TextOverflow.ellipsis,
                          ),
                          Text(
                            context.isVietnamese
                                ? 'Theo dõi số dư từng quầy POS, từng ca làm việc và két lưu trữ'
                                : 'Track POS register balance, active shifts, and storage safes',
                            style: TextStyle(
                              fontSize: 12,
                              color: theme.colorScheme.onSurfaceVariant,
                            ),
                            overflow: TextOverflow.ellipsis,
                          ),
                        ],
                      ),
                    ),
                  ],
                ),
              ),
              const SizedBox(width: 12),
              FilledButton.tonalIcon(
                icon: const Icon(Icons.account_balance_wallet_outlined, size: 16),
                label: const Text('Quản lý két'),
                style: FilledButton.styleFrom(
                  visualDensity: VisualDensity.compact,
                ),
                onPressed: () {
                  final repo = RepositoryScope.of(context);
                  Navigator.of(context).push(
                    MaterialPageRoute(
                      builder: (_) => Scaffold(
                        appBar: AppBar(
                            title: const Text('Quản Lý Két Sắt & Quỹ Tiền Mặt')),
                        body: RepositoryScope(
                          repository: repo,
                          child: const CashScreen(),
                        ),
                      ),
                    ),
                  );
                },
              ),
            ],
          ),
          const SizedBox(height: 18),
          if (!hasCashSource)
            const _DashboardEmptyState(
              icon: Icons.account_balance_wallet_outlined,
              title: 'Chưa có quỹ tiền mặt hoặc số dư để phân bổ',
              message:
                  'Thanh tỷ trọng sẽ xuất hiện sau khi mở ca trực và có số dư.',
            )
          else ...[
            ClipRRect(
              borderRadius: BorderRadius.circular(6),
              child: SizedBox(
                height: 10,
                child: totalCash > 0
                    ? Row(
                        children: [
                          for (int i = 0; i < data.cashboxes.length; i++) ...[
                            if ((boxAmounts[data.cashboxes[i].id] ?? 0) > 0)
                              Expanded(
                                flex: (((boxAmounts[data.cashboxes[i].id] ?? 0) /
                                            totalCash) *
                                        1000)
                                    .round()
                                    .clamp(1, 1000),
                                child:
                                    Container(color: colors[i % colors.length]),
                              ),
                          ],
                        ],
                      )
                    : Container(color: theme.colorScheme.outlineVariant),
              ),
            ),
            const SizedBox(height: 8),
            Text(
              totalCash > 0
                  ? 'Tổng số dư tiền mặt toàn quán: ${AppFormat.money(totalCash.toStringAsFixed(0))} ₫'
                  : 'Đã nhận dữ liệu ${data.cashboxes.length} quỹ, nhưng chưa phát sinh số dư.',
              style: TextStyle(
                  fontSize: 11,
                  fontWeight: FontWeight.w600,
                  color: theme.colorScheme.onSurfaceVariant),
            ),
            const SizedBox(height: 16),
            LayoutBuilder(
              builder: (context, constraints) {
                final isWide = constraints.maxWidth >= 1050;
                final items = [
                  for (int i = 0; i < data.cashboxes.length; i++) ...[
                    Builder(
                      builder: (context) {
                        final box = data.cashboxes[i];
                        final amt = boxAmounts[box.id] ?? 0;
                        final pct = totalCash > 0
                            ? (amt / totalCash * 100).toStringAsFixed(1)
                            : '0.0';
                        final color = colors[i % colors.length];

                        final isPos1 = box.code.contains('POS-01') ||
                            box.name.contains('01') ||
                            i == 0;
                        final isPos2 = box.code.contains('POS-02') ||
                            box.name.contains('02') ||
                            i == 1;

                        final shiftName = isPos1
                            ? 'Ca Sáng (06:30 – 14:30)'
                            : (isPos2
                                ? 'Ca Chiều (14:30 – 22:30)'
                                : 'Két Trung Tâm');
                        final cashierName = isPos1
                            ? 'Thu ngân: Nguyễn Thị Mai'
                            : (isPos2
                                ? 'Thu ngân: Lê Hoàng Nam'
                                : 'Quản lý giữ chìa');
                        final statusLabel = isPos1
                            ? 'Đang mở ca'
                            : (isPos2 ? 'Sẵn sàng ca chiều' : 'Két an toàn');
                        final statusColor = isPos1
                            ? const Color(0xFF059669)
                            : (isPos2
                                ? const Color(0xFF2563EB)
                                : const Color(0xFF7C3AED));

                        return Container(
                          decoration: BoxDecoration(
                            color: isDark
                                ? const Color(0xFF0F172A)
                                : const Color(0xFFF8FAFC),
                            borderRadius: BorderRadius.circular(14),
                            border: Border.all(
                              color: theme.colorScheme.outlineVariant
                                  .withValues(alpha: 0.4),
                            ),
                          ),
                          child: Padding(
                            padding: const EdgeInsets.all(14),
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Row(
                                  children: [
                                    Container(
                                      width: 10,
                                      height: 10,
                                      decoration: BoxDecoration(
                                        color: color,
                                        shape: BoxShape.circle,
                                      ),
                                    ),
                                    const SizedBox(width: 8),
                                    Expanded(
                                      child: Text(
                                        box.name,
                                        style: const TextStyle(
                                          fontWeight: FontWeight.w800,
                                          fontSize: 13,
                                        ),
                                        overflow: TextOverflow.ellipsis,
                                      ),
                                    ),
                                    Container(
                                      padding: const EdgeInsets.symmetric(
                                          horizontal: 6, vertical: 2),
                                      decoration: BoxDecoration(
                                        color: color.withValues(alpha: 0.12),
                                        borderRadius: BorderRadius.circular(6),
                                      ),
                                      child: Text(
                                        '$pct%',
                                        style: TextStyle(
                                          fontWeight: FontWeight.w800,
                                          fontSize: 11,
                                          color: color,
                                        ),
                                      ),
                                    ),
                                  ],
                                ),
                                const SizedBox(height: 6),
                                Row(
                                  children: [
                                    Container(
                                      padding: const EdgeInsets.symmetric(
                                          horizontal: 6, vertical: 2),
                                      decoration: BoxDecoration(
                                        color:
                                            statusColor.withValues(alpha: 0.1),
                                        borderRadius: BorderRadius.circular(4),
                                      ),
                                      child: Text(
                                        statusLabel,
                                        style: TextStyle(
                                          fontSize: 10,
                                          fontWeight: FontWeight.w700,
                                          color: statusColor,
                                        ),
                                      ),
                                    ),
                                    const SizedBox(width: 6),
                                    Expanded(
                                      child: Text(
                                        shiftName,
                                        style: TextStyle(
                                          fontSize: 11,
                                          color: theme
                                              .colorScheme.onSurfaceVariant,
                                        ),
                                        overflow: TextOverflow.ellipsis,
                                      ),
                                    ),
                                  ],
                                ),
                                const SizedBox(height: 4),
                                Text(
                                  cashierName,
                                  style: TextStyle(
                                    fontSize: 11.5,
                                    color: theme.colorScheme.onSurfaceVariant,
                                    fontWeight: FontWeight.w500,
                                  ),
                                  overflow: TextOverflow.ellipsis,
                                ),
                                const Divider(height: 16),
                                Row(
                                  mainAxisAlignment:
                                      MainAxisAlignment.spaceBetween,
                                  children: [
                                    Flexible(
                                      child: Text(
                                        'Tồn tiền mặt:',
                                        style: TextStyle(
                                          fontSize: 12,
                                          color:
                                              theme.colorScheme.onSurfaceVariant,
                                        ),
                                        overflow: TextOverflow.ellipsis,
                                      ),
                                    ),
                                    const SizedBox(width: 8),
                                    FittedBox(
                                      fit: BoxFit.scaleDown,
                                      child: Text(
                                        '${AppFormat.money(amt.toStringAsFixed(0))} ₫',
                                        style: const TextStyle(
                                          fontWeight: FontWeight.w900,
                                          fontSize: 14,
                                          color: Color(0xFF059669),
                                        ),
                                      ),
                                    ),
                                  ],
                                ),
                                const SizedBox(height: 10),
                                SizedBox(
                                  width: double.infinity,
                                  child: OutlinedButton.icon(
                                    key: Key('btn-adjust-cash-${box.code}'),
                                    icon: const Icon(Icons.tune_rounded,
                                        size: 14),
                                    label: const Text(
                                      'Kiểm tra & Tùy chỉnh',
                                      style: TextStyle(
                                          fontSize: 11.5,
                                          fontWeight: FontWeight.w700),
                                    ),
                                    style: OutlinedButton.styleFrom(
                                      visualDensity: VisualDensity.compact,
                                      shape: RoundedRectangleBorder(
                                        borderRadius: BorderRadius.circular(8),
                                      ),
                                    ),
                                    onPressed: canAdjustCash
                                        ? () => _showCashAdjustmentModal(box, amt)
                                        : null,
                                  ),
                                ),
                              ],
                            ),
                          ),
                        );
                      },
                    ),
                  ],
                ];

                if (isWide) {
                  return Row(
                    children: [
                      for (int i = 0; i < items.length; i++) ...[
                        Expanded(child: items[i]),
                        if (i < items.length - 1) const SizedBox(width: 12),
                      ],
                    ],
                  );
                }
                return Column(
                  children: [
                    for (int i = 0; i < items.length; i++) ...[
                      items[i],
                      if (i < items.length - 1) const SizedBox(height: 10),
                    ],
                  ],
                );
              },
            ),
          ],
        ],
      ),
    );
  }

  Widget _buildQuickActions(BuildContext context) {
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;

    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: isDark ? const Color(0xFF1E293B) : Colors.white,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(
          color: theme.colorScheme.outlineVariant.withValues(alpha: 0.5),
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Icon(Icons.bolt_rounded,
                  size: 20, color: Color(0xFFF59E0B)),
              const SizedBox(width: 8),
              Text(
                context.isVietnamese
                    ? 'Thao tác nhanh cho ca làm việc'
                    : 'Quick Shift Actions',
                style: theme.textTheme.titleSmall?.copyWith(
                  fontWeight: FontWeight.w700,
                ),
              ),
            ],
          ),
          const SizedBox(height: 12),
          Builder(
            builder: (context) {
              final roles = RoleVisibility.rolesOf(
                SessionScope.maybeOf(context)?.user,
              );
              final actions = <Widget>[
                if (RoleVisibility.canCreate(roles))
                  _actionButton(
                    context,
                    icon: Icons.savings_outlined,
                    label: context.isVietnamese
                        ? 'Tạo phiếu nhập'
                        : 'New stock receipt',
                    color: const Color(0xFF059669),
                    tabIndex: 3,
                    autoOpenStock: true,
                  ),
                _actionButton(
                  context,
                  icon: Icons.inventory_2_outlined,
                  label: context.isVietnamese ? 'Xem tồn kho' : 'View inventory',
                  color: const Color(0xFF2563EB),
                  tabIndex: 1,
                ),
                if (RoleVisibility.canApprove(roles))
                  _actionButton(
                    context,
                    icon: Icons.verified_outlined,
                    label: context.isVietnamese
                        ? 'Phê duyệt Kiểm Soát Kép'
                        : 'Dual-control approvals',
                    color: const Color(0xFF7C3AED),
                    tabIndex: 4,
                  )
                else
                  _actionButton(
                    context,
                    icon: Icons.receipt_long_outlined,
                    label: context.isVietnamese
                        ? 'Theo dõi Yêu cầu của tôi'
                        : 'My submitted requests',
                    color: const Color(0xFFD97706),
                    tabIndex: 3,
                  ),
                _actionButton(
                  context,
                  icon: Icons.sync_alt_outlined,
                  label: context.isVietnamese
                      ? 'Đối soát Sổ cái tức thì'
                      : 'Instant GL reconciliation',
                  color: const Color(0xFF0891B2),
                  tabIndex: 7,
                ),
              ];
              return Wrap(
                spacing: 12,
                runSpacing: 10,
                children: actions,
              );
            },
          ),
        ],
      ),
    );
  }

  Widget _actionButton(
    BuildContext context, {
    required IconData icon,
    required String label,
    required Color color,
    required int tabIndex,
    bool autoOpenStock = false,
  }) {
    final go = widget.onNavigate;
    final isDark = Theme.of(context).brightness == Brightness.dark;
    return OutlinedButton.icon(
      key: Key('quick-action-$tabIndex-${icon.codePoint}'),
      onPressed: () {
        if (go != null) {
          go(tabIndex, autoOpenStock: autoOpenStock);
          return;
        }
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            behavior: SnackBarBehavior.floating,
            content:
                Text('Vui lòng chuyển qua menu phân hệ để thao tác: $label'),
            duration: const Duration(seconds: 2),
          ),
        );
      },
      style: OutlinedButton.styleFrom(
        backgroundColor: color.withValues(alpha: isDark ? 0.12 : 0.05),
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
        side: BorderSide(color: color.withValues(alpha: 0.3)),
      ),
      icon: Icon(icon, size: 17, color: color),
      label: Text(
        label,
        style: TextStyle(
          fontWeight: FontWeight.w700,
          fontSize: 12.5,
          color: color,
        ),
      ),
    );
  }

  Widget _buildInventoryBreakdown(BuildContext context, DashboardData data) {
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;

    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: isDark ? const Color(0xFF1E293B) : Colors.white,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(
          color: theme.colorScheme.outlineVariant.withValues(alpha: 0.5),
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Expanded(
                child: Text(
                  'Danh mục nguyên liệu & trạng thái tồn kho',
                  style: theme.textTheme.titleMedium?.copyWith(
                    fontWeight: FontWeight.w800,
                  ),
                  overflow: TextOverflow.ellipsis,
                ),
              ),
              const SizedBox(width: 8),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                decoration: BoxDecoration(
                  color: const Color(0xFF2563EB).withValues(alpha: 0.1),
                  borderRadius: BorderRadius.circular(8),
                ),
                child: Text(
                  '${data.items.length} loại vật tư',
                  style: const TextStyle(
                    color: Color(0xFF2563EB),
                    fontSize: 11,
                    fontWeight: FontWeight.w700,
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 16),
          for (final item in data.items.take(4)) ...[
            InkWell(
              onTap: () => widget.onNavigate?.call(1),
              borderRadius: BorderRadius.circular(8),
              child: Padding(
                padding: const EdgeInsets.symmetric(vertical: 8, horizontal: 4),
                child: Row(
                  children: [
                    Container(
                      padding: const EdgeInsets.all(8),
                      decoration: BoxDecoration(
                        color: theme.colorScheme.surfaceContainerHighest,
                        borderRadius: BorderRadius.circular(8),
                      ),
                      child: const Icon(Icons.file_copy_outlined, size: 18),
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            item.name,
                            style: const TextStyle(
                                fontWeight: FontWeight.w700, fontSize: 13),
                          ),
                          Text(
                            'SKU: ${item.sku} • Đơn vị: ${item.unit} • Serial: ${item.trackedSerial ? "Có" : "Không"}',
                            style: TextStyle(
                              fontSize: 11,
                              color: theme.colorScheme.onSurfaceVariant,
                            ),
                          ),
                        ],
                      ),
                    ),
                    Container(
                      padding: const EdgeInsets.symmetric(
                          horizontal: 8, vertical: 3),
                      decoration: BoxDecoration(
                        color: const Color(0xFF10B981).withValues(alpha: 0.12),
                        borderRadius: BorderRadius.circular(6),
                      ),
                      child: const Text(
                        'Khả dụng',
                        style: TextStyle(
                          color: Color(0xFF059669),
                          fontSize: 11,
                          fontWeight: FontWeight.w700,
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ),
            const Divider(height: 1),
          ],
        ],
      ),
    );
  }

  Widget _buildApprovalQueue(BuildContext context, DashboardData data) {
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;

    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: isDark ? const Color(0xFF1E293B) : Colors.white,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(
          color: theme.colorScheme.outlineVariant.withValues(alpha: 0.5),
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Expanded(
                child: Text(
                  'Hộp Thư Phê Duyệt Yêu Cầu',
                  style: theme.textTheme.titleMedium?.copyWith(
                    fontWeight: FontWeight.w800,
                  ),
                  overflow: TextOverflow.ellipsis,
                ),
              ),
              const SizedBox(width: 8),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                decoration: BoxDecoration(
                  color: const Color(0xFFF59E0B).withValues(alpha: 0.15),
                  borderRadius: BorderRadius.circular(8),
                ),
                child: Text(
                  '${data.inbox.length} phiếu chờ',
                  style: const TextStyle(
                    color: Color(0xFFD97706),
                    fontSize: 11,
                    fontWeight: FontWeight.w700,
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 16),
          if (data.inbox.isEmpty)
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 24),
              child: Center(
                child: Column(
                  children: [
                    Icon(Icons.task_alt_rounded,
                        size: 36, color: Colors.green.shade400),
                    const SizedBox(height: 8),
                    const Text(
                      'Không có phiếu tồn đọng',
                      style: TextStyle(fontWeight: FontWeight.w600),
                    ),
                    Text(
                      'Tất cả giao dịch đã được kiểm duyệt hoàn tất.',
                      style: TextStyle(
                          fontSize: 11,
                          color: theme.colorScheme.onSurfaceVariant),
                    ),
                  ],
                ),
              ),
            )
          else
            for (final item in data.inbox.take(3)) ...[
              InkWell(
                onTap: () => widget.onNavigate?.call(4),
                borderRadius: BorderRadius.circular(8),
                child: Padding(
                  padding:
                      const EdgeInsets.symmetric(vertical: 8, horizontal: 4),
                  child: Row(
                    children: [
                      Container(
                        padding: const EdgeInsets.all(8),
                        decoration: BoxDecoration(
                          color: const Color(0xFFF59E0B).withValues(alpha: 0.1),
                          borderRadius: BorderRadius.circular(8),
                        ),
                        child: const Icon(
                          Icons.pending_actions_rounded,
                          color: Color(0xFFD97706),
                          size: 18,
                        ),
                      ),
                      const SizedBox(width: 12),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              'Phiếu ${item.id.length > 8 ? "${item.id.substring(0, 8)}…" : item.id} • ${item.kind}',
                              style: const TextStyle(
                                  fontWeight: FontWeight.w700, fontSize: 13),
                            ),
                            Text(
                              'Người lập: ${item.maker} • Tác động: ${item.impact}',
                              style: TextStyle(
                                fontSize: 11,
                                color: theme.colorScheme.onSurfaceVariant,
                              ),
                            ),
                          ],
                        ),
                      ),
                      Container(
                        padding: const EdgeInsets.symmetric(
                            horizontal: 8, vertical: 3),
                        decoration: BoxDecoration(
                          color:
                              const Color(0xFFF59E0B).withValues(alpha: 0.15),
                          borderRadius: BorderRadius.circular(6),
                        ),
                        child: const Text(
                          'Chờ duyệt',
                          style: TextStyle(
                            color: Color(0xFFB45309),
                            fontSize: 11,
                            fontWeight: FontWeight.w700,
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
              ),
              const Divider(height: 1),
            ],
        ],
      ),
    );
  }

  Widget _buildMakerRequestQueue(BuildContext context, DashboardData data) {
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;
    final myPending = data.stockRequests
        .where((r) => r.status == RequestStatus.pending)
        .toList();

    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: isDark ? const Color(0xFF1E293B) : Colors.white,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(
          color: theme.colorScheme.outlineVariant.withValues(alpha: 0.5),
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Expanded(
                child: Text(
                  'Yêu Cầu Của Bạn Đang Chờ Phê Duyệt',
                  style: theme.textTheme.titleMedium?.copyWith(
                    fontWeight: FontWeight.w800,
                  ),
                  overflow: TextOverflow.ellipsis,
                ),
              ),
              const SizedBox(width: 8),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                decoration: BoxDecoration(
                  color: (myPending.isNotEmpty
                          ? const Color(0xFFF59E0B)
                          : const Color(0xFF10B981))
                      .withValues(alpha: 0.15),
                  borderRadius: BorderRadius.circular(8),
                ),
                child: Text(
                  '${myPending.length} phiếu chờ duyệt',
                  style: TextStyle(
                    color: myPending.isNotEmpty
                        ? const Color(0xFFD97706)
                        : const Color(0xFF059669),
                    fontSize: 11,
                    fontWeight: FontWeight.w700,
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 16),
          if (myPending.isEmpty)
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 24),
              child: Center(
                child: Column(
                  children: [
                    Icon(Icons.task_alt_rounded,
                        size: 36, color: Colors.green.shade400),
                    const SizedBox(height: 8),
                    const Text(
                      'Tất cả yêu cầu đã được xử lý',
                      style: TextStyle(fontWeight: FontWeight.w600),
                    ),
                    const SizedBox(height: 4),
                    Text(
                      'Hiện không có phiếu nào đang chờ kiểm soát viên phê duyệt.',
                      style: TextStyle(
                          fontSize: 11,
                          color: theme.colorScheme.onSurfaceVariant),
                    ),
                    const SizedBox(height: 12),
                    FilledButton.tonalIcon(
                      onPressed: () => widget.onNavigate?.call(3),
                      icon: const Icon(Icons.add, size: 16),
                      label: const Text('Lập Yêu Cầu Mới',
                          style: TextStyle(
                              fontSize: 12, fontWeight: FontWeight.bold)),
                      style: FilledButton.styleFrom(
                          visualDensity: VisualDensity.compact),
                    ),
                  ],
                ),
              ),
            )
          else ...[
            for (final item in myPending.take(3)) ...[
              InkWell(
                onTap: () => widget.onNavigate?.call(3),
                borderRadius: BorderRadius.circular(8),
                child: Padding(
                  padding:
                      const EdgeInsets.symmetric(vertical: 8, horizontal: 4),
                  child: Row(
                    children: [
                      Container(
                        padding: const EdgeInsets.all(8),
                        decoration: BoxDecoration(
                          color: const Color(0xFF2563EB).withValues(alpha: 0.1),
                          borderRadius: BorderRadius.circular(8),
                        ),
                        child: const Icon(
                          Icons.assignment_turned_in_rounded,
                          color: Color(0xFF2563EB),
                          size: 18,
                        ),
                      ),
                      const SizedBox(width: 12),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              'Phiếu ${item.id.length > 8 ? "${item.id.substring(0, 8)}…" : item.id} • ${item.kind.name.toUpperCase()}',
                              style: const TextStyle(
                                  fontWeight: FontWeight.w700, fontSize: 13),
                            ),
                            Text(
                              item.reason.trim().isNotEmpty
                                  ? 'Lý do: ${item.reason}'
                                  : 'Số dòng: ${item.items.length} mặt hàng',
                              style: TextStyle(
                                fontSize: 11,
                                color: theme.colorScheme.onSurfaceVariant,
                              ),
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                            ),
                          ],
                        ),
                      ),
                      Container(
                        padding: const EdgeInsets.symmetric(
                            horizontal: 8, vertical: 3),
                        decoration: BoxDecoration(
                          color:
                              const Color(0xFFF59E0B).withValues(alpha: 0.15),
                          borderRadius: BorderRadius.circular(6),
                        ),
                        child: const Text(
                          'Chờ quản lý duyệt',
                          style: TextStyle(
                            color: Color(0xFFB45309),
                            fontSize: 11,
                            fontWeight: FontWeight.w700,
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
              ),
              const Divider(height: 1),
            ],
            const SizedBox(height: 8),
            Align(
              alignment: Alignment.centerRight,
              child: TextButton.icon(
                onPressed: () => widget.onNavigate?.call(3),
                icon: const Icon(Icons.arrow_forward_rounded, size: 14),
                label: const Text('Xem tất cả yêu cầu của tôi',
                    style:
                        TextStyle(fontSize: 12, fontWeight: FontWeight.bold)),
              ),
            ),
          ],
        ],
      ),
    );
  }

  Future<DashboardData> _load(BankOpsRepository repo, AppUser? user) async {
    final roles = RoleVisibility.rolesOf(user);
    final canApprove = RoleVisibility.canApprove(roles);

    final summaryDto = await repo.getDashboardSummary(canApprove: canApprove);
    final data = DashboardData.fromDto(summaryDto);
    _cachedData = data;
    return data;
  }

  Future<void> _revalidateSilently(BankOpsRepository repo, AppUser? user) async {
    try {
      final roles = RoleVisibility.rolesOf(user);
      final canApprove = RoleVisibility.canApprove(roles);
      final summaryDto = await repo.getDashboardSummary(canApprove: canApprove);
      final data = DashboardData.fromDto(summaryDto);
      _cachedData = data;
      if (mounted) {
        setState(() {
          _future = Future.value(data);
        });
      }
    } catch (_) {
      // Background revalidation silently ignored; cached data remains visible
    }
  }
}

class _DashboardHeader extends StatelessWidget {
  const _DashboardHeader({required this.data, this.canApprove = true});

  final DashboardData data;
  final bool canApprove;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;

    final screenWidth = MediaQuery.sizeOf(context).width;
    final isVeryNarrow = screenWidth < 420;

    final isVi = context.isVietnamese;

    return Container(
      width: double.infinity,
      padding: EdgeInsets.fromLTRB(isVeryNarrow ? 16 : 24, 20, isVeryNarrow ? 16 : 24, 16),
      decoration: BoxDecoration(
        color: isDark ? const Color(0xFF0F172A) : Colors.white,
        border: Border(
          bottom: BorderSide(
            color: theme.colorScheme.outlineVariant.withValues(alpha: 0.5),
          ),
        ),
      ),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  canApprove
                      ? (isVi ? 'Tổng quan vận hành' : 'Operations Overview')
                      : (isVi ? 'Bàn vận hành Giao dịch viên' : 'Operator Workspace'),
                  style: theme.textTheme.headlineSmall?.copyWith(
                    fontWeight: FontWeight.w900,
                    letterSpacing: -0.5,
                  ),
                  overflow: TextOverflow.ellipsis,
                ),
                const SizedBox(height: 4),
                Row(
                  children: [
                    const Icon(Icons.check_circle,
                        size: 14, color: Color(0xFF10B981)),
                    const SizedBox(width: 6),
                    Expanded(
                      child: Text(
                        isVi ? 'Kho đang hoạt động' : 'Active Store & Warehouse',
                        style: TextStyle(
                          fontSize: 12,
                          color: theme.colorScheme.onSurfaceVariant,
                          fontWeight: FontWeight.w500,
                        ),
                        overflow: TextOverflow.ellipsis,
                      ),
                    ),
                  ],
                ),
              ],
            ),
          ),
          const SizedBox(width: 12),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
            decoration: BoxDecoration(
              color: (canApprove
                      ? const Color(0xFF1E3A8A)
                      : const Color(0xFF059669))
                  .withValues(alpha: 0.1),
              borderRadius: BorderRadius.circular(10),
              border: Border.all(
                  color: (canApprove
                          ? const Color(0xFF1E3A8A)
                          : const Color(0xFF059669))
                      .withValues(alpha: 0.2)),
            ),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(canApprove ? Icons.security : Icons.account_balance,
                    size: 16,
                    color: canApprove
                        ? const Color(0xFF1E3A8A)
                        : const Color(0xFF059669)),
                if (!isVeryNarrow) ...[
                  const SizedBox(width: 6),
                  Text(
                    canApprove
                        ? (isVi
                            ? (screenWidth < 680 ? 'QUẢN LÝ DUYỆT' : 'QUY TRÌNH PHÊ DUYỆT')
                            : (screenWidth < 680 ? 'MANAGER' : 'APPROVAL WORKFLOW'))
                        : (isVi
                            ? (screenWidth < 680 ? 'NHÂN VIÊN CA' : 'NHÂN VIÊN CA TRỰC')
                            : (screenWidth < 680 ? 'OPERATOR' : 'SHIFT OPERATOR')),
                    style: TextStyle(
                      fontSize: 11,
                      fontWeight: FontWeight.w800,
                      color: canApprove
                          ? const Color(0xFF1E3A8A)
                          : const Color(0xFF059669),
                      letterSpacing: 0.5,
                    ),
                  ),
                ],
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class DashboardData {
  const DashboardData({
    required this.locations,
    required this.items,
    required this.balances,
    required this.assets,
    required this.stockRequests,
    required this.inbox,
    required this.cashBalances,
    required this.cashboxes,
    required this.lowStockAlerts,
    required this.reconciliations,
  });

  factory DashboardData.fromDto(DashboardSummaryDto dto) {
    return DashboardData(
      locations: dto.locations,
      items: dto.items,
      balances: dto.balances,
      assets: dto.assets,
      stockRequests: dto.stockRequests,
      inbox: dto.inbox,
      cashBalances: dto.cashBalances,
      cashboxes: dto.cashboxes,
      lowStockAlerts: dto.lowStockAlerts,
      reconciliations: dto.reconciliations,
    );
  }

  final List<InventoryLocation> locations;
  final List<InventoryItem> items;
  final List<StockBalance> balances;
  final List<AssetRecord> assets;
  final List<StockRequest> stockRequests;
  final List<ApprovalItem> inbox;
  final List<CashBalance> cashBalances;
  final List<Cashbox> cashboxes;
  final List<LowStockAlertItem> lowStockAlerts;
  final List<ReconciliationRun> reconciliations;

  DashboardTrustMetrics get trustMetrics => DashboardTrustMetrics.fromData(
        cashboxes: cashboxes,
        cashBalances: cashBalances,
        locations: locations,
        items: items,
        balances: balances,
        reconciliations: reconciliations,
      );
}

class SummaryCard extends StatelessWidget {
  const SummaryCard({super.key, required this.data, this.onNavigate});

  final DashboardData data;
  final DashboardNavigateCallback? onNavigate;

  @override
  Widget build(BuildContext context) {
    final roles = RoleVisibility.rolesOf(SessionScope.maybeOf(context)?.user);
    final canApprove = RoleVisibility.canApprove(roles);
    final pendingMyCount = data.stockRequests
        .where((r) => r.status == RequestStatus.pending)
        .length;
    final trust = data.trustMetrics;

    Color stateColor(DashboardDataTone tone, Color fallback) => switch (tone) {
          DashboardDataTone.good => const Color(0xFF059669),
          DashboardDataTone.warning => const Color(0xFFD97706),
          DashboardDataTone.neutral => fallback,
        };

    return LayoutBuilder(
      builder: (context, constraints) {
        final width = constraints.maxWidth;
        final cols = width >= 900 ? 4 : (width >= 520 ? 2 : 1);

        // Calculate totals
        final totalStockQty = data.balances.fold<double>(
          0,
          (sum, b) => sum + (double.tryParse(b.quantity) ?? 0),
        );

        final isVi = context.isVietnamese;
        final cards = [
          _buildExecutiveStatCard(
            context,
            key: const Key('kpi-cash-card'),
            tabIndex: 2,
            title: isVi ? 'CA LÀM VIỆC & ĐỐI SOÁT' : 'SHIFTS & RECONCILIATION',
            value: isVi ? '3 ca trực' : '3 shifts',
            subtext: isVi
                ? 'Ca Sáng · Ca Chiều · Ca Đêm • Kiểm kê định lượng'
                : 'Morning · Afternoon · Night • Shift Stocktake',
            icon: Icons.schedule_rounded,
            color: const Color(0xFF0891B2),
            badgeText: isVi ? 'Đang hoạt động' : 'Active',
            trendText: isVi
                ? 'Kiểm kê đầu ca, chốt tồn cuối ca và đối chiếu hao hụt'
                : 'Opening count, shift closing & variance audit',
            progressRatio: 1.0,
          ),
          _buildExecutiveStatCard(
            context,
            key: const Key('kpi-stock-card'),
            tabIndex: 1,
            title: isVi ? 'NGUYÊN LIỆU TỒN KHO' : 'INVENTORY INGREDIENTS',
            value: data.items.isEmpty || data.locations.isEmpty
                ? '—'
                : '${AppFormat.intFormat(totalStockQty.round())} ${isVi ? 'đơn vị' : 'units'}',
            subtext: data.lowStockAlerts.isNotEmpty
                ? (isVi
                    ? '⚠️ ${data.lowStockAlerts.length} mặt hàng dưới định mức'
                    : '⚠️ ${data.lowStockAlerts.length} items below quota')
                : (isVi
                    ? '${data.items.length} loại vật tư tại ${data.locations.length} kho'
                    : '${data.items.length} materials across ${data.locations.length} warehouses'),
            icon: Icons.inventory_2_rounded,
            color: data.lowStockAlerts.isNotEmpty
                ? const Color(0xFFDC2626)
                : stateColor(trust.stockState.tone, const Color(0xFF2563EB)),
            badgeText: data.lowStockAlerts.isNotEmpty
                ? (isVi ? 'Thiếu hàng' : 'Low Stock')
                : trust.stockState.label,
            trendText: data.lowStockAlerts.isNotEmpty
                ? (isVi
                    ? '${data.lowStockAlerts.length} mặt hàng dưới định mức'
                    : '${data.lowStockAlerts.length} items below minimum quota')
                : trust.stockCoverage == null
                    ? (isVi
                        ? 'Không hiển thị tiến độ khi chưa có danh mục/kho'
                        : 'No progress when catalog or warehouse is empty')
                    : (isVi
                        ? '${(trust.stockCoverage! * 100).round()}% tổ hợp kho–vật tư có bản ghi'
                        : '${(trust.stockCoverage! * 100).round()}% warehouse-item coverage recorded'),
            progressRatio: trust.stockCoverage,
          ),
          canApprove
              ? _buildExecutiveStatCard(
                  context,
                  key: const Key('kpi-inbox-card'),
                  tabIndex: 4,
                  title: isVi
                      ? 'HÀNG ĐỢI PHÊ DUYỆT YÊU CẦU'
                      : 'APPROVAL QUEUE',
                  value: '${data.inbox.length} ${isVi ? 'phiếu' : 'vouchers'}',
                  subtext: isVi
                      ? 'Cần quản lý xác nhận'
                      : 'Awaiting manager approval',
                  icon: Icons.fact_check_rounded,
                  color: data.inbox.isNotEmpty
                      ? const Color(0xFFD97706)
                      : const Color(0xFF059669),
                  badgeText: data.inbox.isNotEmpty
                      ? (isVi ? 'Cần xử lý' : 'Action needed')
                      : (isVi ? 'Đã duyệt hết' : 'All clear'),
                  trendText: data.inbox.isNotEmpty
                      ? '${data.inbox.length} ${isVi ? 'chờ' : 'pending'}'
                      : (isVi ? '0 tồn' : '0 pending'),
                  progressRatio: data.inbox.isNotEmpty ? 0.45 : 1.0,
                )
              : _buildExecutiveStatCard(
                  context,
                  key: const Key('kpi-inbox-card'),
                  tabIndex: 3,
                  title: isVi
                      ? 'YÊU CẦU ĐANG CHỜ DUYỆT'
                      : 'PENDING REQUESTS',
                  value: '$pendingMyCount ${isVi ? 'phiếu' : 'vouchers'}',
                  subtext: isVi
                      ? 'Đã gửi Kiểm soát viên chờ duyệt'
                      : 'Submitted for supervisor review',
                  icon: Icons.pending_actions_rounded,
                  color: pendingMyCount > 0
                      ? const Color(0xFFD97706)
                      : const Color(0xFF059669),
                  badgeText: pendingMyCount > 0
                      ? (isVi ? 'Đang duyệt' : 'In Review')
                      : (isVi ? 'Hoàn tất' : 'Completed'),
                  trendText: pendingMyCount > 0
                      ? '$pendingMyCount ${isVi ? 'chờ' : 'pending'}'
                      : (isVi ? '0 tồn' : '0 pending'),
                  progressRatio: pendingMyCount > 0 ? 0.45 : 1.0,
                ),
          _buildExecutiveStatCard(
            context,
            key: const Key('kpi-ledger-card'),
            tabIndex: 7,
            title: isVi ? 'ĐỐI SOÁT SỔ CÁI (GL)' : 'GENERAL LEDGER (GL) RECONCILIATION',
            value: trust.ledgerState.tone == DashboardDataTone.good
                ? (isVi ? 'Đã khớp' : 'Matched')
                : '—',
            subtext: data.reconciliations.isEmpty
                ? (isVi
                    ? 'Chưa có phiên đối soát để xác nhận số liệu'
                    : 'No reconciliation session to verify balances')
                : trust.ledgerState.tone == DashboardDataTone.warning
                    ? (isVi
                        ? 'Phát hiện ngoại lệ; cần kiểm tra trước khi xác nhận'
                        : 'Exceptions detected; review required')
                    : (isVi
                        ? 'Kết quả lấy từ phiên đối soát gần nhất'
                        : 'Result from latest reconciliation run'),
            icon: Icons.task_alt_rounded,
            color: stateColor(trust.ledgerState.tone, const Color(0xFF7C3AED)),
            badgeText: trust.ledgerState.label,
            trendText: data.reconciliations.isEmpty
                ? (isVi
                    ? 'Chưa có căn cứ tính tỷ lệ khớp'
                    : 'No baseline to calculate match rate')
                : (isVi ? 'Xem chi tiết phiên đối soát' : 'View reconciliation details'),
            progressRatio:
                trust.ledgerState.tone == DashboardDataTone.good ? 1 : null,
          ),
        ];

        if (cols == 4) {
          return Row(
            children: [
              for (int i = 0; i < cards.length; i++) ...[
                Expanded(child: cards[i]),
                if (i < cards.length - 1) const SizedBox(width: 14),
              ],
            ],
          );
        } else if (cols == 2) {
          return Column(
            children: [
              Row(
                children: [
                  Expanded(child: cards[0]),
                  const SizedBox(width: 14),
                  Expanded(child: cards[1]),
                ],
              ),
              const SizedBox(height: 14),
              Row(
                children: [
                  Expanded(child: cards[2]),
                  const SizedBox(width: 14),
                  Expanded(child: cards[3]),
                ],
              ),
            ],
          );
        }

        return Column(
          children: [
            for (int i = 0; i < cards.length; i++) ...[
              cards[i],
              if (i < cards.length - 1) const SizedBox(height: 12),
            ],
          ],
        );
      },
    );
  }

  Widget _buildExecutiveStatCard(
    BuildContext context, {
    Key? key,
    required int tabIndex,
    required String title,
    required String value,
    required String subtext,
    required IconData icon,
    required Color color,
    required String badgeText,
    String? trendText,
    double? progressRatio,
  }) {
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;

    final go = onNavigate;
    return InkWell(
      key: key,
      borderRadius: BorderRadius.circular(16),
      onTap: go == null ? null : () => go(tabIndex),
      child: Container(
        padding: const EdgeInsets.all(20),
        decoration: BoxDecoration(
          color: isDark ? const Color(0xFF1E293B) : Colors.white,
          borderRadius: BorderRadius.circular(16),
          border: Border.all(
            color: theme.colorScheme.outlineVariant.withValues(alpha: 0.5),
          ),
          boxShadow: [
            BoxShadow(
              color: Colors.black.withValues(alpha: isDark ? 0.2 : 0.04),
              blurRadius: 10,
              offset: const Offset(0, 4),
            ),
          ],
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Expanded(
                  child: Text(
                    title,
                    style: TextStyle(
                      fontSize: 11,
                      fontWeight: FontWeight.w700,
                      letterSpacing: 0.5,
                      color: theme.colorScheme.onSurfaceVariant,
                    ),
                    overflow: TextOverflow.ellipsis,
                  ),
                ),
                const SizedBox(width: 8),
                Container(
                  padding: const EdgeInsets.all(8),
                  decoration: BoxDecoration(
                    color: color.withValues(alpha: 0.12),
                    borderRadius: BorderRadius.circular(10),
                  ),
                  child: Icon(icon, size: 18, color: color),
                ),
              ],
            ),
            const SizedBox(height: 12),
            Text(
              value,
              style: const TextStyle(
                fontSize: 22,
                fontWeight: FontWeight.w900,
                letterSpacing: -0.5,
              ),
            ),
            const SizedBox(height: 6),
            Row(
              children: [
                Container(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                  decoration: BoxDecoration(
                    color: color.withValues(alpha: 0.1),
                    borderRadius: BorderRadius.circular(6),
                  ),
                  child: Text(
                    badgeText,
                    style: TextStyle(
                      fontSize: 10,
                      fontWeight: FontWeight.w700,
                      color: color,
                    ),
                  ),
                ),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    subtext,
                    style: TextStyle(
                      fontSize: 11,
                      color: theme.colorScheme.onSurfaceVariant,
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 12),
            if (progressRatio != null)
              ClipRRect(
                borderRadius: BorderRadius.circular(2),
                child: LinearProgressIndicator(
                  value: progressRatio,
                  backgroundColor: color.withValues(alpha: 0.1),
                  valueColor: AlwaysStoppedAnimation<Color>(color),
                  minHeight: 3.5,
                ),
              )
            else
              Container(
                height: 3.5,
                decoration: BoxDecoration(
                  color:
                      theme.colorScheme.outlineVariant.withValues(alpha: 0.6),
                  borderRadius: BorderRadius.circular(2),
                ),
              ),
          ],
        ),
      ),
    );
  }
}

class _DashboardEmptyState extends StatelessWidget {
  const _DashboardEmptyState({
    required this.icon,
    required this.title,
    required this.message,
  });

  final IconData icon;
  final String title;
  final String message;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Container(
      key: const Key('dashboard-empty-cash-distribution'),
      width: double.infinity,
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 18),
      decoration: BoxDecoration(
        color:
            theme.colorScheme.surfaceContainerHighest.withValues(alpha: 0.45),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: theme.colorScheme.outlineVariant),
      ),
      child: Row(
        children: [
          Icon(icon, color: theme.colorScheme.onSurfaceVariant),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(title,
                    style: const TextStyle(fontWeight: FontWeight.w800)),
                const SizedBox(height: 3),
                Text(
                  message,
                  style: TextStyle(
                      fontSize: 12, color: theme.colorScheme.onSurfaceVariant),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class DashboardKpiGrid extends StatelessWidget {
  const DashboardKpiGrid({super.key, required this.data, this.onNavigate});

  final DashboardData data;
  final DashboardNavigateCallback? onNavigate;

  @override
  Widget build(BuildContext context) {
    final width = MediaQuery.sizeOf(context).width;
    final crossCount = width >= 1100 ? 6 : (width >= 700 ? 3 : 2);
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;

    final roles = RoleVisibility.rolesOf(SessionScope.maybeOf(context)?.user);
    final canApprove = RoleVisibility.canApprove(roles);
    final approvedCount = data.stockRequests
        .where((r) => r.status == RequestStatus.approved)
        .length;

    final counts = [
      data.locations.length,
      data.items.length,
      data.balances.length,
      data.assets.length,
      data.stockRequests.length,
      canApprove ? data.inbox.length : approvedCount,
    ];

    final isVi = context.isVietnamese;
    final tiles = [
      _KpiTile(
          isVi ? 'Điểm lưu kho' : 'Stock Locations', Icons.warehouse_rounded, const Color(0xFF2563EB)),
      _KpiTile(
          isVi ? 'Chủng loại vật tư' : 'Categories', Icons.category_rounded, const Color(0xFF0891B2)),
      _KpiTile(
          isVi ? 'Bản ghi tồn kho' : 'Inventory Records', Icons.checklist_rounded, const Color(0xFF059669)),
      _KpiTile(
          isVi ? 'Mã nguyên liệu' : 'Material SKUs', Icons.qr_code_rounded, const Color(0xFF7C3AED)),
      _KpiTile(
          isVi ? 'Phiếu yêu cầu' : 'Requests', Icons.receipt_long_rounded, const Color(0xFFEA580C)),
      canApprove
          ? _KpiTile(
              isVi ? 'Hàng đợi duyệt' : 'Approval Queue', Icons.verified_rounded, const Color(0xFF16A34A))
          : _KpiTile(
              isVi ? 'Phiếu đã duyệt' : 'Approved Vouchers', Icons.verified_rounded, const Color(0xFF16A34A)),
    ];

    return SliverGrid(
      delegate: SliverChildBuilderDelegate(
        (context, index) {
          final tile = tiles[index];
          final count = counts[index];
          final go = onNavigate;
          return InkWell(
            key: Key('kpi-tile-$index'),
            borderRadius: BorderRadius.circular(14),
            onTap: go == null
                ? null
                : () {
                    switch (index) {
                      case 0:
                        go(1, locationId: 'all');
                        break;
                      case 1:
                        go(1, category: 'Nhóm Trà');
                        break;
                      case 2:
                        go(1, viewMode: 'sheet');
                        break;
                      case 3:
                        go(1, stockFilter: 'low');
                        break;
                      case 4:
                        go(3);
                        break;
                      case 5:
                        canApprove ? go(4) : go(3);
                        break;
                    }
                  },
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
              decoration: BoxDecoration(
                color: isDark ? const Color(0xFF1E293B) : Colors.white,
                borderRadius: BorderRadius.circular(14),
                border: Border.all(
                  color:
                      theme.colorScheme.outlineVariant.withValues(alpha: 0.5),
                ),
              ),
              child: FittedBox(
                fit: BoxFit.scaleDown,
                child: Column(
                  mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  Container(
                    padding: const EdgeInsets.all(8),
                    decoration: BoxDecoration(
                      color: tile.color.withValues(alpha: 0.1),
                      shape: BoxShape.circle,
                    ),
                    child: Icon(tile.icon, size: 20, color: tile.color),
                  ),
                  const SizedBox(height: 8),
                  Text(
                    '$count',
                    style: const TextStyle(
                      fontSize: 20,
                      fontWeight: FontWeight.w800,
                    ),
                  ),
                  const SizedBox(height: 2),
                  Text(
                    tile.label,
                    style: TextStyle(
                      fontSize: 11,
                      color: theme.colorScheme.onSurfaceVariant,
                      fontWeight: FontWeight.w500,
                    ),
                    textAlign: TextAlign.center,
                  ),
                ],
              ),
              ),
            ),
          );
        },
        childCount: 6,
      ),
      gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
        crossAxisCount: crossCount,
        crossAxisSpacing: 12,
        mainAxisSpacing: 12,
        childAspectRatio: 1.3,
      ),
    );
  }
}

class _KpiTile {
  final String label;
  final IconData icon;
  final Color color;

  const _KpiTile(this.label, this.icon, this.color);
}
