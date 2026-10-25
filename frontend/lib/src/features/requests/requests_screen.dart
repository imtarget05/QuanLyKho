import 'package:flutter/material.dart';

import '../../app/app_shell.dart';
import '../../core/i18n/app_i18n.dart';
import '../../core/sync/data_sync_controller.dart';
import '../../core/util/approval_pdf.dart';
import '../../core/util/formatting.dart';
import '../../core/util/report_share.dart';
import '../../core/widgets/app_toast.dart';
import '../../core/util/error_text.dart';
import '../../core/widgets/state_views.dart';
import '../../data/models/dtos.dart';
import '../../data/repositories/bankops_repository.dart';
import '../ai/ai_voucher_audit.dart';
import 'request_timeline.dart';
import 'widgets/denomination_breakdown_dialog.dart';
import 'widgets/stock_request_dialog.dart';

/// Màn yêu cầu — tạo mới và gửi duyệt phiếu kho (stock) + phiếu quỹ (cash).
class RequestsScreen extends StatefulWidget {
  const RequestsScreen({
    super.key,
    this.initialOpenCreateStock = false,
    this.initialOpenCreateCash = false,
    this.initialLocationId,
    this.initialItemId,
    this.initialQuantity,
    this.onInitialOpenHandled,
  });

  final bool initialOpenCreateStock;
  final bool initialOpenCreateCash;
  final String? initialLocationId;
  final String? initialItemId;
  final double? initialQuantity;
  final VoidCallback? onInitialOpenHandled;

  @override
  State<RequestsScreen> createState() => _RequestsScreenState();
}

class _RequestsScreenState extends State<RequestsScreen> {
  Future<_RequestsData>? _future;
  DataSyncController? _syncController;
  bool _busy = false;
  bool _handledInitialOpen = false;
  RequestStatus? _statusFilter;

  void _checkInitialOpen(_RequestsData data) {
    if (_handledInitialOpen) return;
    if (widget.initialOpenCreateStock) {
      _handledInitialOpen = true;
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted) {
          widget.onInitialOpenHandled?.call();
          _openCreateStockDialog(
            data,
            initialLocationId: widget.initialLocationId,
            initialItemId: widget.initialItemId,
            initialQuantity: widget.initialQuantity,
          );
        }
      });
    } else if (widget.initialOpenCreateCash) {
      _handledInitialOpen = true;
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted) {
          widget.onInitialOpenHandled?.call();
          _openCreateCashDialog(data);
        }
      });
    }
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    final repo = RepositoryScope.of(context);
    _future ??= _load(repo);

    final sync = SyncScope.maybeOf(context);
    if (sync != _syncController) {
      _syncController?.removeListener(_onSyncUpdate);
      _syncController = sync;
      _syncController?.addListener(_onSyncUpdate);
    }
  }

  void _onSyncUpdate() {
    if (!mounted) return;
    _reload();
  }

  @override
  void dispose() {
    _syncController?.removeListener(_onSyncUpdate);
    super.dispose();
  }

  void _reload() {
    final repo = RepositoryScope.of(context);
    setState(() {
      _future = _load(repo);
    });
  }

  void _showHistory(String requestId) {
    // Lấy repo TRƯỚC khi mở sheet: context trong bottom-sheet overlay
    // không còn nằm dưới RepositoryScope.
    final repo = RepositoryScope.of(context);
    showModalBottomSheet<void>(
      context: context,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(16)),
      ),
      builder: (_) => RequestTimeline(requestId: requestId, repo: repo),
    );
  }

  Future<void> _printCashWithAiCheck(CashRequest r) async {
    final audit = AiVoucherAuditor.checkCashRequest(r, null);
    final item = ApprovalItem(
      id: r.id,
      kind: 'Tiền mặt (${r.kind == RequestKind.receipt ? "Thu" : "Chi"})',
      maker: r.createdByName,
      impact: AppFormat.money(r.amount, currency: r.currency),
      detail: r.reason,
      status: r.status.name,
    );

    if (audit.hasErrors) {
      if (!mounted) return;
      final proceed = await AiVoucherAuditDialog.show(
        context,
        item: item,
        result: audit,
      );
      if (!proceed) {
        if (mounted) {
          AppToast.info(
              context, 'Đã hủy in để rà soát lại thông tin chứng từ.');
        }
        return;
      }
    } else {
      if (mounted) {
        AppToast.success(context,
            'AI kiểm tra: Chứng từ hợp lệ 100%, không phát hiện sai sót.');
      }
    }

    if (!mounted) return;
    await ReportShare.printPdf(
      context,
      filename: 'phieu-quy-${r.id}.pdf',
      build: () => ApprovalPdf.encode(
        item,
        auditWarnings: audit.hasErrors ? audit.warnings : null,
      ),
    );
  }

  Future<void> _printStockWithAiCheck(StockRequest r) async {
    final audit = AiVoucherAuditor.checkStockRequest(r, null);
    final totalQty = r.items.fold<double>(
      0,
      (sum, l) => sum + (double.tryParse(l.quantity) ?? 0),
    );
    final item = ApprovalItem(
      id: r.id,
      kind: 'Kho nguyên liệu (${r.kind.label})',
      maker: r.createdByName,
      impact: '${totalQty.toInt()} đơn vị nguyên liệu',
      detail: r.reason,
      status: r.status.name,
    );

    if (audit.hasErrors) {
      if (!mounted) return;
      final proceed = await AiVoucherAuditDialog.show(
        context,
        item: item,
        result: audit,
      );
      if (!proceed) {
        if (mounted) {
          AppToast.info(
              context, 'Đã hủy in để rà soát lại thông tin chứng từ.');
        }
        return;
      }
    } else {
      if (mounted) {
        AppToast.success(context,
            'AI kiểm tra: Chứng từ hợp lệ 100%, không phát hiện sai sót.');
      }
    }

    if (!mounted) return;
    await ReportShare.printPdf(
      context,
      filename: 'phieu-kho-${r.id}.pdf',
      build: () => ApprovalPdf.encode(
        item,
        auditWarnings: audit.hasErrors ? audit.warnings : null,
      ),
    );
  }

  Future<void> _submitStock(String id) async {
    final repo = RepositoryScope.of(context);
    setState(() => _busy = true);
    try {
      await repo.submitStockRequest(id);
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          backgroundColor: const Color(0xFF059669),
          behavior: SnackBarBehavior.floating,
          content: Text('Đã gửi duyệt thành công phiếu kho $id'),
        ),
      );
      _reload();
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          backgroundColor: const Color(0xFFB42318),
          behavior: SnackBarBehavior.floating,
          content: Text('Lỗi gửi duyệt: ${friendlyError(e)}'),
        ),
      );
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _submitCash(String id) async {
    final repo = RepositoryScope.of(context);
    setState(() => _busy = true);
    try {
      await repo.submitCashRequest(id);
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          backgroundColor: const Color(0xFF059669),
          behavior: SnackBarBehavior.floating,
          content: Text('Đã gửi duyệt thành công phiếu quỹ $id'),
        ),
      );
      _reload();
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          backgroundColor: const Color(0xFFB42318),
          behavior: SnackBarBehavior.floating,
          content: Text('Lỗi gửi duyệt: ${friendlyError(e)}'),
        ),
      );
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _deleteStock(String id) async {
    final repo = RepositoryScope.of(context);
    setState(() => _busy = true);
    try {
      await repo.deleteStockRequest(id);
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          backgroundColor: const Color(0xFF059669),
          behavior: SnackBarBehavior.floating,
          content: Text('Đã xoá phiếu kho nháp $id'),
        ),
      );
      _reload();
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          backgroundColor: const Color(0xFFB42318),
          behavior: SnackBarBehavior.floating,
          content: Text('Lỗi xoá phiếu: ${friendlyError(e)}'),
        ),
      );
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  static const List<String> _cashReasonSuggestions = [
    'Ghi nhận nguyên liệu đầu ca',
    'Chi chi phí vận hành',
    'Chi trả nhà cung cấp',
    'Thanh toán công việc',
    'Hoàn trả khách hàng',
    'Rút về két trung tâm',
    'Phụ cấp nhân sự',
    'Chi dự án',
  ];

  Future<void> _deleteCash(String id) async {
    final repo = RepositoryScope.of(context);
    setState(() => _busy = true);
    try {
      await repo.deleteCashRequest(id);
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          backgroundColor: const Color(0xFF059669),
          behavior: SnackBarBehavior.floating,
          content: Text('Đã xoá phiếu quỹ nháp $id'),
        ),
      );
      _reload();
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          backgroundColor: const Color(0xFFB42318),
          behavior: SnackBarBehavior.floating,
          content: Text('Lỗi xoá phiếu: ${friendlyError(e)}'),
        ),
      );
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _openCreateStockDialog(
    _RequestsData data, {
    RequestKind defaultKind = RequestKind.receipt,
    bool isSpoilage = false,
    String? initialLocationId,
    String? initialItemId,
    double? initialQuantity,
  }) async {
    if (data.locations.isEmpty || data.items.isEmpty) return;

    final created = await showDialog<StockRequest>(
      context: context,
      builder: (ctx) => StockRequestDialog(
        locations: data.locations,
        items: data.items,
        balances: data.balances,
        initialKind: defaultKind,
        isSpoilage: isSpoilage,
        initialLocationId: initialLocationId,
        initialItemId: initialItemId,
        initialQuantity: initialQuantity,
        isFromAlert: initialLocationId != null || initialItemId != null,
      ),
    );

    if (created == null || !mounted) return;

    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        backgroundColor: const Color(0xFF059669),
        behavior: SnackBarBehavior.floating,
        content: Text(isSpoilage
            ? 'Đã ghi nhận báo cáo hư hỏng #${created.id} chờ quản lý xác nhận!'
            : 'Đã tạo thành công phiếu kho ${created.id} (${created.items.length} nguyên liệu)'),
      ),
    );
    _reload();
  }

  void _showStockLinesSheet(StockRequest r, List<InventoryItem> items) {
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;

    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (ctx) => Container(
        constraints: BoxConstraints(
          maxHeight: MediaQuery.of(context).size.height * 0.75,
        ),
        decoration: BoxDecoration(
          color: isDark ? const Color(0xFF0F172A) : Colors.white,
          borderRadius: const BorderRadius.vertical(top: Radius.circular(20)),
        ),
        child: Column(
          children: [
            Container(
              margin: const EdgeInsets.only(top: 10, bottom: 8),
              width: 40,
              height: 4,
              decoration: BoxDecoration(
                color: Colors.grey.withValues(alpha: 0.4),
                borderRadius: BorderRadius.circular(2),
              ),
            ),
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 8),
              child: Row(
                children: [
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          'Chi tiết Phiếu kho #${r.id}',
                          style: theme.textTheme.titleMedium?.copyWith(
                            fontWeight: FontWeight.w800,
                          ),
                        ),
                        Text(
                          'Loại: ${r.subKindLabel} • ${r.items.length} dòng nguyên liệu'
                          '${r.invoiceNo != null ? " • HĐ: ${r.invoiceNo}" : ""}',
                          style: TextStyle(
                            fontSize: 12,
                            color: theme.colorScheme.onSurfaceVariant,
                          ),
                        ),
                      ],
                    ),
                  ),
                  IconButton(
                    icon: const Icon(Icons.close),
                    onPressed: () => Navigator.of(ctx).pop(),
                  ),
                ],
              ),
            ),
            const Divider(height: 1),
            Expanded(
              child: ListView.separated(
                padding: const EdgeInsets.all(16),
                itemCount: r.items.length,
                separatorBuilder: (_, __) => const Divider(height: 12),
                itemBuilder: (ctx, idx) {
                  final line = r.items[idx];
                  final itm = items.cast<InventoryItem?>().firstWhere(
                        (i) => i?.id == line.itemId,
                        orElse: () => null,
                      );
                  final name = line.itemName ?? itm?.name ?? line.itemId;
                  final sku = itm?.sku ?? '';
                  final unit = line.unit ?? itm?.unit ?? 'đơn vị';

                  return Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      CircleAvatar(
                        radius: 14,
                        backgroundColor:
                            theme.colorScheme.primary.withValues(alpha: 0.12),
                        child: Text(
                          '${idx + 1}',
                          style: TextStyle(
                            fontSize: 12,
                            fontWeight: FontWeight.bold,
                            color: theme.colorScheme.primary,
                          ),
                        ),
                      ),
                      const SizedBox(width: 12),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              name,
                              style: const TextStyle(
                                  fontWeight: FontWeight.w700, fontSize: 14),
                            ),
                            if (sku.isNotEmpty)
                              Text(
                                'SKU: $sku • ĐVT: $unit',
                                style: TextStyle(
                                  fontSize: 12,
                                  color: theme.colorScheme.onSurfaceVariant,
                                ),
                              ),
                            if (line.lotNo != null || line.expiryDate != null)
                              Padding(
                                padding: const EdgeInsets.only(top: 2),
                                child: Text(
                                  '${line.lotNo != null ? "Lô: ${line.lotNo}" : ""}'
                                  '${line.lotNo != null && line.expiryDate != null ? " • " : ""}'
                                  '${line.expiryDate != null ? "HSD: ${line.expiryDate}" : ""}',
                                  style: const TextStyle(
                                    fontSize: 11,
                                    color: Color(0xFFD97706),
                                    fontWeight: FontWeight.w600,
                                  ),
                                ),
                              ),
                          ],
                        ),
                      ),
                      Column(
                        crossAxisAlignment: CrossAxisAlignment.end,
                        children: [
                          Text(
                            '${line.quantity} $unit',
                            style: const TextStyle(
                                fontWeight: FontWeight.w700, fontSize: 14),
                          ),
                          if (line.unitPrice != null && line.unitPrice!.isNotEmpty)
                            Text(
                              '${AppFormat.money(line.unitPrice!)} đ / $unit',
                              style: TextStyle(
                                fontSize: 11,
                                color: theme.colorScheme.onSurfaceVariant,
                              ),
                            ),
                          if (line.totalAmount > 0)
                            Text(
                              AppFormat.money(line.totalAmount.toStringAsFixed(0),
                                  currency: 'VND'),
                              style: const TextStyle(
                                fontSize: 12,
                                fontWeight: FontWeight.w800,
                                color: Color(0xFF2563EB),
                              ),
                            ),
                        ],
                      ),
                    ],
                  );
                },
              ),
            ),
            if (r.totalCost > 0)
              Container(
                padding: const EdgeInsets.all(16),
                decoration: BoxDecoration(
                  color: isDark ? const Color(0xFF1E293B) : const Color(0xFFF8FAFC),
                  border: Border(
                    top: BorderSide(
                        color: theme.colorScheme.outlineVariant
                            .withValues(alpha: 0.5)),
                  ),
                ),
                child: Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    const Text(
                      'Tổng giá trị phiếu:',
                      style: TextStyle(fontWeight: FontWeight.w700, fontSize: 14),
                    ),
                    Text(
                      AppFormat.money(r.totalCost.toStringAsFixed(0),
                          currency: 'VND'),
                      style: const TextStyle(
                        fontSize: 18,
                        fontWeight: FontWeight.w900,
                        color: Color(0xFF2563EB),
                      ),
                    ),
                  ],
                ),
              ),
          ],
        ),
      ),
    );
  }

  Future<void> _openCreateCashDialog(_RequestsData data) async {
    if (data.cashboxes.isEmpty) return;
    final repo = RepositoryScope.of(context);
    RequestKind kind = RequestKind.receipt;
    String cashboxId = data.cashboxes.first.id;
    final amountCtrl = TextEditingController(text: '500000');
    final reasonCtrl =
        TextEditingController(text: _cashReasonSuggestions.first);
    final reasonFocus = FocusNode();
    Map<int, int>? denominationCounts;

    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, setDialogState) => AlertDialog(
          shape:
              RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
          title: const Text('Tạo Phiếu Nhập Nguyên Liệu'),
          content: SizedBox(
            width: 440,
            child: SingleChildScrollView(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  DropdownButtonFormField<RequestKind>(
                    key: const Key('cash-kind-dropdown'),
                    initialValue: kind,
                    decoration: const InputDecoration(
                      labelText: 'Loại giao dịch',
                      border: OutlineInputBorder(),
                    ),
                    items: const [
                      DropdownMenuItem(
                        value: RequestKind.receipt,
                        child: Text('Thu nộp quỹ (receipt)'),
                      ),
                      DropdownMenuItem(
                        value: RequestKind.payment,
                        child: Text('Chi xuất quỹ (payment)'),
                      ),
                    ],
                    onChanged: (v) {
                      if (v != null) setDialogState(() => kind = v);
                    },
                  ),
                  const SizedBox(height: 12),
                  DropdownButtonFormField<String>(
                    key: const Key('cash-box-dropdown'),
                    isExpanded: true,
                    initialValue: cashboxId,
                    decoration: const InputDecoration(
                      labelText: 'Két sắt chi nhánh',
                      border: OutlineInputBorder(),
                    ),
                    items: [
                      for (final box in data.cashboxes)
                        DropdownMenuItem(
                          value: box.id,
                          child: Text('${box.code} — ${box.name}'),
                        ),
                    ],
                    onChanged: (v) {
                      if (v != null) setDialogState(() => cashboxId = v);
                    },
                  ),
                  const SizedBox(height: 12),
                  Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Expanded(
                        child: TextField(
                          key: const Key('cash-amount-input'),
                          controller: amountCtrl,
                          decoration: InputDecoration(
                            labelText: 'Số tiền (VND)',
                            border: const OutlineInputBorder(),
                            helperText: amountCtrl.text.isNotEmpty
                                ? '${AppFormat.number(amountCtrl.text)} đ'
                                : null,
                          ),
                          keyboardType: TextInputType.number,
                          onChanged: (_) => setDialogState(() {}),
                        ),
                      ),
                      const SizedBox(width: 8),
                      Tooltip(
                        message: 'Mở Bảng kê kiểm đếm mệnh giá',
                        child: OutlinedButton.icon(
                          key: const Key('open-denomination-btn'),
                          style: OutlinedButton.styleFrom(
                            padding: const EdgeInsets.symmetric(
                                horizontal: 10, vertical: 15),
                            side: const BorderSide(color: Color(0xFF059669)),
                          ),
                          icon: const Icon(Icons.calculate_outlined,
                              color: Color(0xFF059669)),
                          label: const Text('Bảng kê',
                              style: TextStyle(
                                  color: Color(0xFF059669), fontSize: 13)),
                          onPressed: () async {
                            final res = await showDialog<DenominationResult>(
                              context: ctx,
                              builder: (_) => DenominationBreakdownDialog(
                                  initialCounts: denominationCounts),
                            );
                            if (res != null) {
                              denominationCounts = res.counts;
                              setDialogState(() {
                                amountCtrl.text = res.totalAmount.toString();
                                if (reasonCtrl.text.trim().isEmpty) {
                                  reasonCtrl.text = res.breakdownSummary;
                                } else if (!reasonCtrl.text
                                    .contains('Bảng kê:')) {
                                  reasonCtrl.text =
                                      '${reasonCtrl.text.trim()} · ${res.breakdownSummary}';
                                }
                              });
                            }
                          },
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 12),
                  Autocomplete<String>(
                    key: const Key('cash-reason-autocomplete'),
                    optionsBuilder: (TextEditingValue text) {
                      final query = text.text.trim();
                      if (query.isEmpty) return _cashReasonSuggestions;
                      return _cashReasonSuggestions.where(
                          (s) => s.toLowerCase().contains(query.toLowerCase()));
                    },
                    onSelected: (value) => reasonCtrl.text = value,
                    fieldViewBuilder: (ctx, ctrl, focus, onFieldSubmitted) {
                      return TextField(
                        key: const Key('cash-reason-input'),
                        controller: ctrl,
                        focusNode: focus,
                        decoration: const InputDecoration(
                          labelText: 'Diễn giải lý do nộp/rút quỹ',
                          hintText: 'Gõ hoặc chọn gợi ý...',
                          border: OutlineInputBorder(),
                        ),
                      );
                    },
                  ),
                ],
              ),
            ),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.of(ctx).pop(false),
              child: const Text('Huỷ'),
            ),
            FilledButton(
              key: const Key('cash-dialog-save-btn'),
              style: FilledButton.styleFrom(
                  backgroundColor: const Color(0xFF059669)),
              onPressed: () => Navigator.of(ctx).pop(true),
              child: const Text('Lưu phiếu nháp'),
            ),
          ],
        ),
      ),
    );
    reasonFocus.dispose();

    if (confirmed != true || !mounted) return;
    setState(() => _busy = true);
    try {
      final created = await repo.createCashRequest(
        cashboxId: cashboxId,
        kind: kind,
        amount:
            amountCtrl.text.trim().isEmpty ? '100000' : amountCtrl.text.trim(),
        reason: reasonCtrl.text.trim(),
      );
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          backgroundColor: const Color(0xFF059669),
          behavior: SnackBarBehavior.floating,
          content: Text('Đã tạo thành công phiếu quỹ ${created.id}'),
        ),
      );
      _reload();
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          backgroundColor: const Color(0xFFB42318),
          behavior: SnackBarBehavior.floating,
          content: Text('Lỗi tạo phiếu quỹ: ${friendlyError(e)}'),
        ),
      );
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<_RequestsData>(
      future: _future,
      builder: (context, snapshot) {
        if (snapshot.connectionState != ConnectionState.done) {
          return const Center(child: LoadingView());
        }
        if (snapshot.hasError) {
          return Center(
            child: ErrorView(
              message: '${snapshot.error}',
              onRetry: _reload,
            ),
          );
        }
        final data = snapshot.data!;
        _checkInitialOpen(data);
        final theme = Theme.of(context);
        final isDark = theme.brightness == Brightness.dark;

        return RefreshIndicator(
          onRefresh: () async => _reload(),
          child: ListView(
            padding: const EdgeInsets.all(20),
            children: [
              // Header
              LayoutBuilder(
                builder: (context, constraints) {
                  final isCompact = constraints.maxWidth < 900;
                  final titleWidget = Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        context.tr('requests_header_title'),
                        style: theme.textTheme.headlineSmall?.copyWith(
                          fontWeight: FontWeight.w900,
                          letterSpacing: -0.5,
                        ),
                      ),
                      const SizedBox(height: 4),
                      Text(
                        context.tr('requests_header_subtitle'),
                        style: TextStyle(
                          color: theme.colorScheme.onSurfaceVariant,
                          fontSize: 13,
                        ),
                      ),
                    ],
                  );

                  final buttonsWidget = Wrap(
                    spacing: 10,
                    runSpacing: 8,
                    children: [
                      FilledButton.icon(
                        key: const Key('btn-create-stock-request'),
                        onPressed:
                            _busy ? null : () => _openCreateStockDialog(data),
                        icon: const Icon(Icons.add_box_outlined, size: 18),
                        label: Text(context.isVietnamese
                            ? 'Nhập/Xuất kho'
                            : 'Stock In/Out'),
                        style: FilledButton.styleFrom(
                          backgroundColor: const Color(0xFF2563EB),
                          shape: RoundedRectangleBorder(
                              borderRadius: BorderRadius.circular(10)),
                        ),
                      ),
                      FilledButton.icon(
                        key: const Key('btn-create-spoilage-request'),
                        onPressed: _busy
                            ? null
                            : () => _openCreateStockDialog(
                                  data,
                                  defaultKind: RequestKind.payment,
                                  isSpoilage: true,
                                ),
                        icon: const Icon(Icons.broken_image_outlined, size: 18),
                        label: Text(context.isVietnamese
                            ? 'Báo cáo hư hỏng'
                            : 'Spoilage Report'),
                        style: FilledButton.styleFrom(
                          backgroundColor: const Color(0xFFD97706),
                          shape: RoundedRectangleBorder(
                              borderRadius: BorderRadius.circular(10)),
                        ),
                      ),
                      FilledButton.icon(
                        key: const Key('btn-create-cash-request'),
                        onPressed:
                            _busy ? null : () => _openCreateCashDialog(data),
                        icon: const Icon(Icons.payments_outlined, size: 18),
                        label: Text(context.isVietnamese
                            ? 'Tạo phiếu quỹ'
                            : 'Cash Voucher'),
                        style: FilledButton.styleFrom(
                          backgroundColor: const Color(0xFF059669),
                          shape: RoundedRectangleBorder(
                              borderRadius: BorderRadius.circular(10)),
                        ),
                      ),
                    ],
                  );

                  if (isCompact) {
                    return Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        titleWidget,
                        const SizedBox(height: 12),
                        buttonsWidget,
                      ],
                    );
                  }

                  return Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      Expanded(child: titleWidget),
                      const SizedBox(width: 16),
                      buttonsWidget,
                    ],
                  );
                },
              ),
              const SizedBox(height: 20),

              // Bộ lọc trạng thái
              SingleChildScrollView(
                scrollDirection: Axis.horizontal,
                child: Row(
                  children: [
                    FilterChip(
                      selected: _statusFilter == null,
                      label: Text(
                          '${context.tr('requests_filter_all')} (${data.stockRequests.length + data.cashRequests.length})'),
                      onSelected: (_) => setState(() => _statusFilter = null),
                    ),
                    const SizedBox(width: 8),
                    FilterChip(
                      selected: _statusFilter == RequestStatus.returned,
                      avatar: const Icon(Icons.assignment_return_outlined,
                          size: 16, color: Color(0xFFD97706)),
                      label: Text(
                        '${context.tr('requests_filter_rework')} (${data.stockRequests.where((r) => r.status == RequestStatus.returned).length + data.cashRequests.where((r) => r.status == RequestStatus.returned).length})',
                        style: TextStyle(
                          color: _statusFilter == RequestStatus.returned
                              ? null
                              : const Color(0xFFD97706),
                          fontWeight: FontWeight.w700,
                        ),
                      ),
                      onSelected: (_) => setState(
                          () => _statusFilter = RequestStatus.returned),
                    ),
                    const SizedBox(width: 8),
                    FilterChip(
                      selected: _statusFilter == RequestStatus.pending,
                      label: Text(
                          '${context.tr('requests_filter_pending')} (${data.stockRequests.where((r) => r.status == RequestStatus.pending).length + data.cashRequests.where((r) => r.status == RequestStatus.pending).length})'),
                      onSelected: (_) =>
                          setState(() => _statusFilter = RequestStatus.pending),
                    ),
                    const SizedBox(width: 8),
                    FilterChip(
                      selected: _statusFilter == RequestStatus.draft,
                      label: Text(
                          '${context.tr('requests_filter_draft')} (${data.stockRequests.where((r) => r.status == RequestStatus.draft).length + data.cashRequests.where((r) => r.status == RequestStatus.draft).length})'),
                      onSelected: (_) =>
                          setState(() => _statusFilter = RequestStatus.draft),
                    ),
                    const SizedBox(width: 8),
                    FilterChip(
                      selected: _statusFilter == RequestStatus.posted,
                      label: Text(
                          '${context.tr('requests_filter_posted')} (${data.stockRequests.where((r) => r.status == RequestStatus.posted).length + data.cashRequests.where((r) => r.status == RequestStatus.posted).length})'),
                      onSelected: (_) =>
                          setState(() => _statusFilter = RequestStatus.posted),
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 20),

              // Phiếu kho
              Wrap(
                alignment: WrapAlignment.spaceBetween,
                crossAxisAlignment: WrapCrossAlignment.center,
                spacing: 12,
                runSpacing: 4,
                children: [
                  Text(
                    '${context.tr('requests_section_stock')} (${_statusFilter == null ? data.stockRequests.length : data.stockRequests.where((r) => r.status == _statusFilter).length})',
                    style: theme.textTheme.titleMedium?.copyWith(
                      fontWeight: FontWeight.w800,
                    ),
                  ),
                  Text(
                    context.isVietnamese
                        ? 'Kiểm soát viên duyệt trước khi ghi nhận nhập/xuất'
                        : 'Requires supervisor approval before posting',
                    style: TextStyle(
                        fontSize: 12,
                        color: theme.colorScheme.onSurfaceVariant),
                  ),
                ],
              ),
              const SizedBox(height: 12),
              for (final r in (_statusFilter == null
                  ? data.stockRequests
                  : data.stockRequests
                      .where((r) => r.status == _statusFilter)
                      .toList()))
                Container(
                  key: Key('stock-request-card-${r.id}'),
                  margin: const EdgeInsets.only(bottom: 12),
                  decoration: BoxDecoration(
                    color: isDark ? const Color(0xFF1E293B) : Colors.white,
                    borderRadius: BorderRadius.circular(14),
                    border: Border.all(
                      color: theme.colorScheme.outlineVariant
                          .withValues(alpha: 0.5),
                    ),
                  ),
                  child: Padding(
                    padding: const EdgeInsets.all(16),
                    child: LayoutBuilder(
                      builder: (context, cardConstraints) {
                        final isCompact = cardConstraints.maxWidth < 640;

                        final iconWidget = Container(
                          padding: const EdgeInsets.all(10),
                          decoration: BoxDecoration(
                            color:
                                const Color(0xFF2563EB).withValues(alpha: 0.1),
                            borderRadius: BorderRadius.circular(10),
                          ),
                          child: const Icon(Icons.inventory_2_outlined,
                              color: Color(0xFF2563EB), size: 20),
                        );

                        final detailsWidget = Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Row(
                              children: [
                                Flexible(
                                  child: Text(
                                    'Phiếu kho ${r.id.length > 8 ? "${r.id.substring(0, 8)}…" : r.id}',
                                    style: const TextStyle(
                                        fontWeight: FontWeight.w700,
                                        fontSize: 14),
                                    overflow: TextOverflow.ellipsis,
                                  ),
                                ),
                                const SizedBox(width: 8),
                                _subKindChip(r.subKindLabel, r.subKind, r.kind),
                                const SizedBox(width: 6),
                                _statusChip(r.status),
                                const Spacer(),
                                IconButton(
                                  key: Key('btn-view-lines-${r.id}'),
                                  icon: const Icon(Icons.receipt_long_outlined,
                                      size: 20),
                                  tooltip: 'Xem dòng nguyên liệu (${r.items.length})',
                                  onPressed: () => _showStockLinesSheet(r, data.items),
                                ),
                                IconButton(
                                  key: Key('print-stock-${r.id}'),
                                  icon: const Icon(Icons.print_outlined,
                                      size: 20),
                                  tooltip: 'In phiếu ${r.id} (AI Kiểm Duyệt)',
                                  onPressed: () => _printStockWithAiCheck(r),
                                ),
                                IconButton(
                                  key: Key('request-history-stock-${r.id}'),
                                  icon: const Icon(Icons.history_outlined,
                                      size: 20),
                                  tooltip: 'Lịch sử phiếu ${r.id}',
                                  onPressed: () => _showHistory(r.id),
                                ),
                              ],
                            ),
                            const SizedBox(height: 4),
                            Text(
                              'Loại: ${r.kind.label} • Người lập: ${r.createdByName}'
                              '${r.supplierName != null && r.supplierName!.isNotEmpty ? " • NCC: ${r.supplierName}" : ""}'
                              '${r.invoiceNo != null && r.invoiceNo!.isNotEmpty ? " • Số HĐ: ${r.invoiceNo}" : ""}'
                              ' • Lý do: ${r.reason.isEmpty ? "Xuất nhập kho định kỳ" : r.reason}',
                              style: TextStyle(
                                fontSize: 12,
                                color: theme.colorScheme.onSurfaceVariant,
                              ),
                            ),
                            const SizedBox(height: 6),
                            InkWell(
                              key: Key('btn-view-lines-text-${r.id}'),
                              onTap: () => _showStockLinesSheet(r, data.items),
                              borderRadius: BorderRadius.circular(4),
                              child: Padding(
                                padding: const EdgeInsets.symmetric(vertical: 2),
                                child: Row(
                                  mainAxisSize: MainAxisSize.min,
                                  children: [
                                    Icon(
                                      Icons.inventory_2_outlined,
                                      size: 14,
                                      color: theme.colorScheme.primary,
                                    ),
                                    const SizedBox(width: 5),
                                    Flexible(
                                      child: Text(
                                        '${r.items.length} dòng nguyên liệu'
                                        '${r.totalCost > 0 ? " • Tổng tiền: ${AppFormat.money(r.totalCost.toStringAsFixed(0), currency: "VND")}" : ""}',
                                        overflow: TextOverflow.ellipsis,
                                        style: TextStyle(
                                          fontSize: 12,
                                          fontWeight: FontWeight.w600,
                                          color: theme.colorScheme.primary,
                                          decoration: TextDecoration.underline,
                                        ),
                                      ),
                                    ),
                                  ],
                                ),
                              ),
                            ),
                            if (r.status == RequestStatus.returned &&
                                (r.returnReason?.isNotEmpty ?? false)) ...[
                              const SizedBox(height: 8),
                              Container(
                                padding: const EdgeInsets.symmetric(
                                    horizontal: 10, vertical: 6),
                                decoration: BoxDecoration(
                                  color: const Color(0xFFFFFBEB),
                                  border: Border.all(
                                      color: const Color(0xFFFDE68A)),
                                  borderRadius: BorderRadius.circular(8),
                                ),
                                child: Row(
                                  children: [
                                    const Icon(
                                        Icons.assignment_return_outlined,
                                        size: 16,
                                        color: Color(0xFFD97706)),
                                    const SizedBox(width: 6),
                                    Expanded(
                                      child: Text(
                                        'Ý kiến người duyệt: ${r.returnReason}',
                                        style: const TextStyle(
                                          fontSize: 12,
                                          color: Color(0xFF92400E),
                                          fontWeight: FontWeight.w600,
                                        ),
                                      ),
                                    ),
                                  ],
                                ),
                              ),
                            ],
                          ],
                        );

                        final actionsWidget = r.status == RequestStatus.draft
                            ? Row(
                                mainAxisSize: MainAxisSize.min,
                                children: [
                                  IconButton(
                                    key: Key('btn-delete-stock-${r.id}'),
                                    icon: const Icon(Icons.delete_outline,
                                        color: Colors.red, size: 20),
                                    tooltip: 'Xoá phiếu nháp',
                                    onPressed:
                                        _busy ? null : () => _deleteStock(r.id),
                                  ),
                                  const SizedBox(width: 4),
                                  FilledButton.icon(
                                    key: Key('btn-submit-stock-${r.id}'),
                                    onPressed:
                                        _busy ? null : () => _submitStock(r.id),
                                    icon: const Icon(Icons.send_rounded,
                                        size: 16),
                                    label: Text(context.isVietnamese
                                        ? 'Gửi duyệt'
                                        : 'Submit for Approval'),
                                    style: FilledButton.styleFrom(
                                      backgroundColor:
                                          const Color(0xFF2563EB),
                                      shape: RoundedRectangleBorder(
                                          borderRadius:
                                              BorderRadius.circular(8)),
                                    ),
                                  ),
                                ],
                              )
                            : (r.status == RequestStatus.returned
                                ? FilledButton.icon(
                                    key: Key('btn-resubmit-stock-${r.id}'),
                                    onPressed: _busy
                                        ? null
                                        : () => _submitStock(r.id),
                                    icon: const Icon(Icons.refresh_rounded,
                                        size: 16),
                                    label: Text(context.isVietnamese
                                        ? 'Gửi duyệt lại'
                                        : 'Resubmit'),
                                    style: FilledButton.styleFrom(
                                      backgroundColor:
                                          const Color(0xFFD97706),
                                      shape: RoundedRectangleBorder(
                                          borderRadius:
                                              BorderRadius.circular(8)),
                                    ),
                                  )
                                : _statusBadge(r.status));

                        if (isCompact) {
                          return Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Row(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  iconWidget,
                                  const SizedBox(width: 12),
                                  Expanded(child: detailsWidget),
                                ],
                              ),
                              const SizedBox(height: 10),
                              Align(
                                alignment: Alignment.centerRight,
                                child: actionsWidget,
                              ),
                            ],
                          );
                        }

                        return Row(
                          children: [
                            iconWidget,
                            const SizedBox(width: 14),
                            Expanded(child: detailsWidget),
                            const SizedBox(width: 12),
                            actionsWidget,
                          ],
                        );
                      },
                    ),
                  ),
                ),
              const SizedBox(height: 24),

              // Phiếu quỹ
              Wrap(
                alignment: WrapAlignment.spaceBetween,
                crossAxisAlignment: WrapCrossAlignment.center,
                spacing: 12,
                runSpacing: 4,
                children: [
                  Text(
                    '${context.tr('requests_section_cash')} (${_statusFilter == null ? data.cashRequests.length : data.cashRequests.where((r) => r.status == _statusFilter).length})',
                    style: theme.textTheme.titleMedium?.copyWith(
                      fontWeight: FontWeight.w800,
                    ),
                  ),
                  Text(
                    context.isVietnamese
                        ? 'Ảnh hưởng số dư két sau khi được phê duyệt'
                        : 'Updates safe balance once approved',
                    style: TextStyle(
                        fontSize: 12,
                        color: theme.colorScheme.onSurfaceVariant),
                  ),
                ],
              ),
              const SizedBox(height: 12),
              for (final r in (_statusFilter == null
                  ? data.cashRequests
                  : data.cashRequests
                      .where((r) => r.status == _statusFilter)
                      .toList()))
                Container(
                  key: Key('cash-request-card-${r.id}'),
                  margin: const EdgeInsets.only(bottom: 12),
                  decoration: BoxDecoration(
                    color: isDark ? const Color(0xFF1E293B) : Colors.white,
                    borderRadius: BorderRadius.circular(14),
                    border: Border.all(
                      color: theme.colorScheme.outlineVariant
                          .withValues(alpha: 0.5),
                    ),
                  ),
                  child: Padding(
                    padding: const EdgeInsets.all(16),
                    child: LayoutBuilder(
                      builder: (context, cardConstraints) {
                        final isCompact = cardConstraints.maxWidth < 640;

                        final iconWidget = Container(
                          padding: const EdgeInsets.all(10),
                          decoration: BoxDecoration(
                            color:
                                const Color(0xFF059669).withValues(alpha: 0.1),
                            borderRadius: BorderRadius.circular(10),
                          ),
                          child: const Icon(Icons.savings_outlined,
                              color: Color(0xFF059669), size: 20),
                        );

                        final detailsWidget = Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Row(
                              children: [
                                Flexible(
                                  child: Text(
                                    'Phiếu quỹ ${r.id.length > 8 ? "${r.id.substring(0, 8)}…" : r.id}',
                                    style: const TextStyle(
                                        fontWeight: FontWeight.w700,
                                        fontSize: 14),
                                    overflow: TextOverflow.ellipsis,
                                  ),
                                ),
                                const SizedBox(width: 8),
                                _statusChip(r.status),
                                const Spacer(),
                                IconButton(
                                  key: Key('print-cash-${r.id}'),
                                  icon: const Icon(Icons.print_outlined,
                                      size: 20),
                                  tooltip: 'In phiếu ${r.id} (AI Kiểm Duyệt)',
                                  onPressed: () => _printCashWithAiCheck(r),
                                ),
                                IconButton(
                                  key: Key('request-history-cash-${r.id}'),
                                  icon: const Icon(Icons.history_outlined,
                                      size: 20),
                                  tooltip: 'Lịch sử phiếu ${r.id}',
                                  onPressed: () => _showHistory(r.id),
                                ),
                              ],
                            ),
                            const SizedBox(height: 4),
                            Text(
                              'Số tiền: ${AppFormat.money(r.amount, currency: r.currency)} • Người lập: ${r.createdByName} • Lý do: ${r.reason.isEmpty ? "Giao dịch quỹ thường kỳ" : r.reason}',
                              style: TextStyle(
                                fontSize: 12,
                                color: theme.colorScheme.onSurfaceVariant,
                              ),
                            ),
                            if (r.status == RequestStatus.returned &&
                                (r.returnReason?.isNotEmpty ?? false)) ...[
                              const SizedBox(height: 8),
                              Container(
                                padding: const EdgeInsets.symmetric(
                                    horizontal: 10, vertical: 6),
                                decoration: BoxDecoration(
                                  color: const Color(0xFFFFFBEB),
                                  border: Border.all(
                                      color: const Color(0xFFFDE68A)),
                                  borderRadius: BorderRadius.circular(8),
                                ),
                                child: Row(
                                  children: [
                                    const Icon(
                                        Icons.assignment_return_outlined,
                                        size: 16,
                                        color: Color(0xFFD97706)),
                                    const SizedBox(width: 6),
                                    Expanded(
                                      child: Text(
                                        'Ý kiến người duyệt: ${r.returnReason}',
                                        style: const TextStyle(
                                          fontSize: 12,
                                          color: Color(0xFF92400E),
                                          fontWeight: FontWeight.w600,
                                        ),
                                      ),
                                    ),
                                  ],
                                ),
                              ),
                            ],
                          ],
                        );

                        final actionsWidget = r.status == RequestStatus.draft
                            ? Row(
                                mainAxisSize: MainAxisSize.min,
                                children: [
                                  IconButton(
                                    key: Key('btn-delete-cash-${r.id}'),
                                    icon: const Icon(Icons.delete_outline,
                                        color: Colors.red, size: 20),
                                    tooltip: 'Xoá phiếu nháp',
                                    onPressed:
                                        _busy ? null : () => _deleteCash(r.id),
                                  ),
                                  const SizedBox(width: 4),
                                  FilledButton.icon(
                                    key: Key('btn-submit-cash-${r.id}'),
                                    onPressed:
                                        _busy ? null : () => _submitCash(r.id),
                                    icon: const Icon(Icons.send_rounded,
                                        size: 16),
                                    label: Text(context.isVietnamese
                                        ? 'Gửi duyệt'
                                        : 'Submit for Approval'),
                                    style: FilledButton.styleFrom(
                                      backgroundColor:
                                          const Color(0xFF059669),
                                      shape: RoundedRectangleBorder(
                                          borderRadius:
                                              BorderRadius.circular(8)),
                                    ),
                                  ),
                                ],
                              )
                            : (r.status == RequestStatus.returned
                                ? FilledButton.icon(
                                    key: Key('btn-resubmit-cash-${r.id}'),
                                    onPressed: _busy
                                        ? null
                                        : () => _submitCash(r.id),
                                    icon: const Icon(Icons.refresh_rounded,
                                        size: 16),
                                    label: Text(context.isVietnamese
                                        ? 'Gửi duyệt lại'
                                        : 'Resubmit'),
                                    style: FilledButton.styleFrom(
                                      backgroundColor:
                                          const Color(0xFFD97706),
                                      shape: RoundedRectangleBorder(
                                          borderRadius:
                                              BorderRadius.circular(8)),
                                    ),
                                  )
                                : _statusBadge(r.status));

                        if (isCompact) {
                          return Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Row(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  iconWidget,
                                  const SizedBox(width: 12),
                                  Expanded(child: detailsWidget),
                                ],
                              ),
                              const SizedBox(height: 10),
                              Align(
                                alignment: Alignment.centerRight,
                                child: actionsWidget,
                              ),
                            ],
                          );
                        }

                        return Row(
                          children: [
                            iconWidget,
                            const SizedBox(width: 14),
                            Expanded(child: detailsWidget),
                            const SizedBox(width: 12),
                            actionsWidget,
                          ],
                        );
                      },
                    ),
                  ),
                ),
            ],
          ),
        );
      },
    );
  }

  Widget _subKindChip(String label, String? subKind, RequestKind kind) {
    Color bg;
    Color fg;
    switch (subKind) {
      case 'spoilage':
        bg = const Color(0xFFFEE2E2);
        fg = const Color(0xFF991B1B);
        break;
      case 'internal':
        bg = const Color(0xFFFEF3C7);
        fg = const Color(0xFF92400E);
        break;
      case 'transfer':
        bg = const Color(0xFFEDE9FE);
        fg = const Color(0xFF6D28D9);
        break;
      case 'sale':
        bg = const Color(0xFFDCFCE7);
        fg = const Color(0xFF166534);
        break;
      default:
        if (kind == RequestKind.receipt) {
          bg = const Color(0xFFDBEAFE);
          fg = const Color(0xFF1D4ED8);
        } else {
          bg = const Color(0xFFF1F5F9);
          fg = const Color(0xFF334155);
        }
    }
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 2),
      decoration: BoxDecoration(
        color: bg,
        borderRadius: BorderRadius.circular(6),
      ),
      child: Text(
        label,
        style: TextStyle(
          color: fg,
          fontSize: 10.5,
          fontWeight: FontWeight.w700,
        ),
      ),
    );
  }

  Widget _statusChip(RequestStatus status) {
    Color bg;
    Color fg;
    String text;

    switch (status) {
      case RequestStatus.draft:
        bg = const Color(0xFFF1F5F9);
        fg = const Color(0xFF475467);
        text = 'Bản nháp';
        break;
      case RequestStatus.pending:
        bg = const Color(0xFFFEF3C7);
        fg = const Color(0xFFB45309);
        text = 'Chờ duyệt';
        break;
      case RequestStatus.returned:
        bg = const Color(0xFFFEF3C7);
        fg = const Color(0xFFD97706);
        text = 'Cần chỉnh sửa';
        break;
      case RequestStatus.approved:
        bg = const Color(0xFFD1FAE5);
        fg = const Color(0xFF065F46);
        text = 'Đã duyệt';
        break;
      case RequestStatus.posted:
        bg = const Color(0xFFCCFBF1);
        fg = const Color(0xFF0F766E);
        text = 'Đã ghi sổ';
        break;
      case RequestStatus.rejected:
        bg = const Color(0xFFFEE2E2);
        fg = const Color(0xFF991B1B);
        text = 'Bị từ chối';
        break;
      default:
        bg = const Color(0xFFF1F5F9);
        fg = const Color(0xFF475467);
        text = status.name;
    }

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 2),
      decoration: BoxDecoration(
        color: bg,
        borderRadius: BorderRadius.circular(6),
      ),
      child: Text(
        text,
        style: TextStyle(
          color: fg,
          fontSize: 10.5,
          fontWeight: FontWeight.w700,
        ),
      ),
    );
  }

  Widget _statusBadge(RequestStatus status) {
    Color bg = const Color(0xFF64748B).withValues(alpha: 0.12);
    Color fg = const Color(0xFF475467);
    String label = switch (status) {
      RequestStatus.draft => 'BẢN NHÁP',
      RequestStatus.pending => 'CHỜ DUYỆT',
      RequestStatus.returned => 'CẦN SỬA',
      RequestStatus.approved => 'ĐÃ DUYỆT',
      RequestStatus.posted => 'ĐÃ GHI SỔ',
      RequestStatus.rejected => 'TỪ CHỐI',
      RequestStatus.cancelled => 'ĐÃ HỦY',
    };
    if (status == RequestStatus.posted || status == RequestStatus.approved) {
      bg = const Color(0xFF059669).withValues(alpha: 0.12);
      fg = const Color(0xFF059669);
    } else if (status == RequestStatus.returned) {
      bg = const Color(0xFFD97706).withValues(alpha: 0.12);
      fg = const Color(0xFFD97706);
    } else if (status == RequestStatus.rejected) {
      bg = const Color(0xFFDC2626).withValues(alpha: 0.12);
      fg = const Color(0xFFDC2626);
    }
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
      decoration: BoxDecoration(
        color: bg,
        borderRadius: BorderRadius.circular(8),
      ),
      child: Text(
        label,
        style: TextStyle(
          fontSize: 11,
          fontWeight: FontWeight.w800,
          color: fg,
        ),
      ),
    );
  }

  Future<_RequestsData> _load(BankOpsRepository repo) async {
    final results = await Future.wait([
      repo.getStockRequests(),
      repo.getCashRequests(),
      repo.getLocations(),
      repo.getItems(),
      repo.getCashboxes(),
      repo.getBalances().catchError((_) => <StockBalance>[]),
    ]);
    return _RequestsData(
      stockRequests: results[0] as List<StockRequest>,
      cashRequests: results[1] as List<CashRequest>,
      locations: results[2] as List<InventoryLocation>,
      items: results[3] as List<InventoryItem>,
      cashboxes: results[4] as List<Cashbox>,
      balances: results[5] as List<StockBalance>,
    );
  }
}

class _RequestsData {
  const _RequestsData({
    required this.stockRequests,
    required this.cashRequests,
    required this.locations,
    required this.items,
    required this.cashboxes,
    this.balances = const [],
  });

  final List<StockRequest> stockRequests;
  final List<CashRequest> cashRequests;
  final List<InventoryLocation> locations;
  final List<InventoryItem> items;
  final List<Cashbox> cashboxes;
  final List<StockBalance> balances;
}
