import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';

import '../../app/app_shell.dart';
import '../../core/i18n/app_i18n.dart';
import '../../core/i18n/locale_controller.dart';
import '../../core/theme/app_theme.dart';
import '../../core/util/formatting.dart';
import '../../core/util/report_share.dart';
import '../../core/util/role_visibility.dart';
import '../../core/widgets/app_toast.dart';
import '../../core/util/approval_pdf.dart';
import '../../core/util/error_text.dart';
import '../../core/widgets/state_views.dart';
import '../../data/models/dtos.dart';
import '../../data/repositories/bankops_repository.dart';
import 'reports_filter.dart';
import 'widgets/cashflow_chart.dart';
import 'widgets/executive_kpi_deck.dart';
import 'widgets/inventory_chart.dart';
import 'widgets/meeting_notes_tab.dart';
import 'widgets/meeting_presentation_modal.dart';
import 'widgets/meeting_report_pdf.dart';
import 'widgets/stagnation_list.dart';

/// Màn báo cáo điều hành & giao ban cuộc họp — biểu đồ nhập/xuất kho, dòng tiền mô phỏng, cảnh báo tồn đọng, đối soát và công cụ thuyết trình.
class ReportsScreen extends StatefulWidget {
  const ReportsScreen({super.key});

  @override
  State<ReportsScreen> createState() => _ReportsScreenState();
}

class _ReportsScreenState extends State<ReportsScreen> {
  ReportGranularity _granularity = ReportGranularity.daily;
  DateTimeRange? _dateRange;
  Future<_ReportsData>? _future;
  bool _reconciling = false;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    final repo = RepositoryScope.of(context);
    _future ??= _load(repo);
  }

  void _reload() {
    final repo = RepositoryScope.of(context);
    setState(() {
      _future = _load(repo);
    });
  }

  Future<void> _runReconciliation(String scope) async {
    if (_reconciling) return;
    setState(() => _reconciling = true);
    try {
      await RepositoryScope.of(context).runReconciliation(scope: scope);
      _reload();
    } catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(
            content: Text('Không thể chạy đối soát: ${friendlyError(error)}')));
      }
    } finally {
      if (mounted) setState(() => _reconciling = false);
    }
  }

  Future<_ReportsData> _load(BankOpsRepository repo) async {
    final dateFrom = _dateRange?.start.toIso8601String();
    final dateTo = _dateRange?.end.toIso8601String();
    final invFuture = _granularity == ReportGranularity.daily
        ? repo.getInventoryDaily(dateFrom: dateFrom, dateTo: dateTo)
        : repo.getInventoryMonthly(dateFrom: dateFrom, dateTo: dateTo);
    final cashFuture = _granularity == ReportGranularity.daily
        ? repo.getCashflowDaily(dateFrom: dateFrom, dateTo: dateTo)
        : repo.getCashflowMonthly(dateFrom: dateFrom, dateTo: dateTo);

    final roles = RoleVisibility.rolesOf(SessionScope.maybeOf(context)?.user);
    final canViewReconciliation = roles.isEmpty ||
        roles.any((role) => const {
              'approver',
              'checker',
              'auditor',
              'cash_sim_operator'
            }.contains(role));
    final results = await Future.wait([
      invFuture,
      cashFuture,
      repo.getStagnation(),
      canViewReconciliation
          ? _loadReconciliations(repo)
          : Future.value(<ReconciliationRun>[]),
      repo.getConsumptionTop(),
      repo.getShiftHistory(),
    ]);

    // Validate cashflow data - ensure it's a proper list, default to empty if malformed
    final rawCashflow = results[1] as List?;
    final cashflowBuckets = rawCashflow?.whereType<CashflowBucket>().toList() ?? [];

    // Validate inventory data similarly
    final rawInventory = results[0] as List?;
    final inventoryBuckets = rawInventory?.whereType<InventoryBucket>().toList() ?? [];

    return _ReportsData(
      inventoryBuckets: inventoryBuckets,
      cashflowBuckets: cashflowBuckets,
      stagnationItems: results[2] as List<StagnationItem>,
      reconciliations: results[3] as List<ReconciliationRun>,
      consumptionTop: results[4] as List<ConsumptionTopItem>,
      shiftHistory: results[5] as List<ShiftHistoryItem>,
    );
  }

  Future<List<ReconciliationRun>> _loadReconciliations(
      BankOpsRepository repo) async {
    try {
      return await repo.getReconciliations();
    } on ApiException catch (error) {
      if (error.code == 'FORBIDDEN' || error.code == 'HTTP_403') return [];
      rethrow;
    }
  }

  @override
  Widget build(BuildContext context) {
    try {
      context.watch<LocaleController>();
    } catch (_) {
      try {
        context.watch<LocaleController?>();
      } catch (_) {}
    }
    return DefaultTabController(
      length: 7,
      child: FutureBuilder<_ReportsData>(
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
          final roles =
              RoleVisibility.rolesOf(SessionScope.maybeOf(context)?.user);
          final canRunReconciliation = roles.isEmpty ||
              roles.any((role) => const {
                    'approver',
                    'checker',
                    'cash_sim_operator'
                  }.contains(role));

          return NestedScrollView(
            headerSliverBuilder: (context, innerBoxIsScrolled) => [
              SliverToBoxAdapter(
                child: Padding(
                  padding: const EdgeInsets.fromLTRB(16, 16, 16, 8),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      // Tiêu đề & các nút hành động điều hành kinh doanh
                      Wrap(
                        spacing: 16,
                        runSpacing: 10,
                        alignment: WrapAlignment.spaceBetween,
                        crossAxisAlignment: WrapCrossAlignment.center,
                        children: [
                          Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(
                                context.tr('reports_title'),
                                style: Theme.of(context)
                                    .textTheme
                                    .headlineSmall
                                    ?.copyWith(
                                      fontWeight: FontWeight.bold,
                                    ),
                              ),
                              const SizedBox(height: 2),
                              Text(
                                context.tr('reports_subtitle'),
                                style: Theme.of(context)
                                    .textTheme
                                    .bodySmall
                                    ?.copyWith(
                                      color: Theme.of(context)
                                          .colorScheme
                                          .onSurfaceVariant,
                                    ),
                              ),
                            ],
                          ),
                          Wrap(
                            spacing: 8,
                            runSpacing: 6,
                            children: [
                              FilledButton.icon(
                                key: const Key('btn-print-meeting-pdf-header'),
                                onPressed: () {
                                  ReportShare.printPdf(
                                    context,
                                    filename: 'bao-cao-tong-hop-kinh-doanh.pdf',
                                    build: () => MeetingReportPdf.encode(
                                      inventoryBuckets: data.inventoryBuckets,
                                      cashflowBuckets: data.cashflowBuckets,
                                      stagnationItems: data.stagnationItems,
                                      reconciliations: data.reconciliations,
                                      granularity: _granularity,
                                      dateRange: _dateRange,
                                    ),
                                  );
                                },
                                icon: const Icon(Icons.picture_as_pdf_outlined,
                                    size: 18),
                                label: const Text('In Báo Cáo A4'),
                              ),
                              OutlinedButton.icon(
                                key: const Key('btn-print-vouchers-modal'),
                                onPressed: () => _showVoucherPrintModal(context, data),
                                icon: const Icon(Icons.receipt_long_outlined,
                                    size: 18),
                                label: const Text('Mẫu Phiếu In (BTC)'),
                              ),
                              OutlinedButton.icon(
                                key: const Key('btn-export-csv-reports'),
                                onPressed: () => _exportCsv(context, data),
                                icon: const Icon(Icons.table_view_outlined,
                                    size: 18),
                                label: const Text('Xuất CSV / Excel'),
                              ),
                            ],
                          ),
                        ],
                      ),
                      const SizedBox(height: 12),
                      ReportsFilter(
                        granularity: _granularity,
                        onGranularityChanged: (g) {
                          _granularity = g;
                          _reload();
                        },
                        dateRange: _dateRange,
                        onDateRangeChanged: (range) {
                          _dateRange = range;
                          _reload();
                        },
                      ),
                      const SizedBox(height: 12),
                      // Bộ chỉ số điều hành cốt lõi (Executive KPI Deck)
                      ExecutiveKpiDeck(
                        cashflowBuckets: data.cashflowBuckets,
                        inventoryBuckets: data.inventoryBuckets,
                        stagnationItems: data.stagnationItems,
                        reconciliations: data.reconciliations,
                      ),
                    ],
                  ),
                ),
              ),
              SliverToBoxAdapter(
                child: TabBar(
                  isScrollable: true,
                  tabs: [
                    Tab(
                        key: const Key('tab-reports-inventory'),
                        text: context.tr('reports_tab_inventory')),
                    Tab(
                        key: const Key('tab-reports-cashflow'),
                        text: context.tr('reports_tab_cashflow')),
                    Tab(
                        key: const Key('tab-reports-stagnation'),
                        text: context.tr('reports_tab_stagnation')),
                    Tab(
                        key: const Key('tab-reports-consumption-top'),
                        text: context.tr('reports_tab_consumption')),
                    Tab(
                        key: const Key('tab-reports-shift-history'),
                        text: context.tr('reports_tab_shift_history')),
                    Tab(
                        key: const Key('tab-reports-reconciliation'),
                        text: context.tr('reports_tab_reconciliation')),
                    Tab(
                        key: const Key('tab-reports-meeting-notes'),
                        text: context.tr('reports_tab_meeting_notes')),
                  ],
                ),
              ),
            ],
            body: TabBarView(
              children: [
                _InventoryXntTab(buckets: data.inventoryBuckets),
                SingleChildScrollView(
                  padding: const EdgeInsets.all(16),
                  child: CashflowChart(buckets: data.cashflowBuckets),
                ),
                SingleChildScrollView(
                  padding: const EdgeInsets.all(16),
                  child: StagnationList(items: data.stagnationItems),
                ),
                _ConsumptionTopTab(items: data.consumptionTop),
                _ShiftHistoryTab(items: data.shiftHistory),
                _ReconciliationTab(
                  runs: data.reconciliations,
                  canRun: canRunReconciliation,
                  busy: _reconciling,
                  onRun: _runReconciliation,
                ),
                MeetingNotesTab(
                  inventoryBuckets: data.inventoryBuckets,
                  cashflowBuckets: data.cashflowBuckets,
                  stagnationItems: data.stagnationItems,
                  reconciliations: data.reconciliations,
                  granularity: _granularity,
                  dateRange: _dateRange,
                  onOpenPresentation: () => MeetingPresentationModal.show(
                    context,
                    inventoryBuckets: data.inventoryBuckets,
                    cashflowBuckets: data.cashflowBuckets,
                    stagnationItems: data.stagnationItems,
                    reconciliations: data.reconciliations,
                    granularity: _granularity,
                    dateRange: _dateRange,
                  ),
                ),
              ],
            ),
          );
        },
      ),
    );
  }

  void _exportCsv(BuildContext context, _ReportsData data) {
    final sb = StringBuffer();
    sb.writeln('Ky,NhapKho_SoLuong,XuatKho_SoLuong,TonRong_SoLuong,SoPhieuNhap,SoPhieuXuat');
    for (final b in data.inventoryBuckets) {
      sb.writeln('${b.bucket},${b.inboundQty},${b.outboundQty},${b.netQty},${b.receiptCount},${b.issueCount}');
    }
    Clipboard.setData(ClipboardData(text: sb.toString()));
    AppToast.success(context, 'Đã sao chép dữ liệu CSV vào Clipboard (có thể dán trực tiếp vào Google Sheets / Excel).');
  }

  void _showVoucherPrintModal(BuildContext context, _ReportsData data) {
    showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
      ),
      builder: (ctx) {
        final theme = Theme.of(ctx);

        return SafeArea(
          child: Padding(
            padding: const EdgeInsets.fromLTRB(20, 16, 20, 24),
            child: SingleChildScrollView(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Center(
                    child: Container(
                      width: 40,
                      height: 4,
                      decoration: BoxDecoration(
                        color: theme.colorScheme.outlineVariant,
                        borderRadius: BorderRadius.circular(2),
                      ),
                    ),
                  ),
                  const SizedBox(height: 16),
                  Row(
                    children: [
                      Container(
                        padding: const EdgeInsets.all(8),
                        decoration: BoxDecoration(
                          color: theme.colorScheme.primary.withValues(alpha: 0.1),
                          borderRadius: BorderRadius.circular(10),
                        ),
                        child: Icon(Icons.receipt_long_rounded,
                            color: theme.colorScheme.primary, size: 22),
                      ),
                      const SizedBox(width: 12),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              'Trung Tâm In Chứng Từ & Biểu Mẫu',
                              style: theme.textTheme.titleMedium
                                  ?.copyWith(fontWeight: FontWeight.bold),
                            ),
                            Text(
                              'Định dạng chuẩn theo Thông tư 200/2014/TT-BTC',
                              style: TextStyle(
                                fontSize: 12,
                                color: theme.colorScheme.onSurfaceVariant,
                              ),
                            ),
                          ],
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 16),
                  _buildVoucherTile(
                    ctx,
                    title: 'Phiếu Nhập Kho (Mẫu 01-VT)',
                    subtitle: 'Chứng từ xác nhận nhập nguyên vật liệu vào kho',
                    icon: Icons.move_to_inbox_rounded,
                    color: const Color(0xFF059669),
                    onTap: () {
                      Navigator.pop(ctx);
                      ReportShare.printPdf(
                        context,
                        filename: 'phieu-nhap-kho-01-VT.pdf',
                        build: () => ApprovalPdf.encode(
                          ApprovalItem(
                            id: 'PNK-${DateTime.now().millisecondsSinceEpoch.toString().substring(7)}',
                            kind: 'inbound',
                            maker: SessionScope.maybeOf(context)?.user?.displayName ?? 'Thủ kho phụ trách',
                            impact: 'Nhập kho nguyên vật liệu',
                            detail: data.consumptionTop.isNotEmpty
                                ? data.consumptionTop.take(3).map((c) => '${c.sku}: 20 kg').join(', ')
                                : 'TRA-DEN: 20 kg, SUA-TUOI: 50 lit, TRAN-CHAU: 30 goi',
                            status: 'approved',
                          ),
                        ),
                      );
                    },
                  ),
                  _buildVoucherTile(
                    ctx,
                    title: 'Phiếu Xuất Kho (Mẫu 02-VT)',
                    subtitle: 'Chứng từ xuất nguyên liệu phục vụ quầy pha chế',
                    icon: Icons.outbox_rounded,
                    color: const Color(0xFF2563EB),
                    onTap: () {
                      Navigator.pop(ctx);
                      ReportShare.printPdf(
                        context,
                        filename: 'phieu-xuat-kho-02-VT.pdf',
                        build: () => ApprovalPdf.encode(
                          ApprovalItem(
                            id: 'PXK-${DateTime.now().millisecondsSinceEpoch.toString().substring(7)}',
                            kind: 'outbound',
                            maker: SessionScope.maybeOf(context)?.user?.displayName ?? 'Nhân viên quầy pha chế',
                            impact: 'Xuất quầy pha chế',
                            detail: data.consumptionTop.isNotEmpty
                                ? data.consumptionTop.take(3).map((c) => '${c.sku}: 10 kg').join(', ')
                                : 'TRA-DEN: 10 kg, SUA-TUOI: 30 lit, SIRO-DUONG: 15 chai',
                            status: 'approved',
                          ),
                        ),
                      );
                    },
                  ),
                  _buildVoucherTile(
                    ctx,
                    title: 'Phiếu Thu Tiền Mặt (Mẫu 01-TT)',
                    subtitle: 'Biên lai ghi nhận nguồn thu nộp vào két quỹ',
                    icon: Icons.add_circle_outline_rounded,
                    color: const Color(0xFF10B981),
                    onTap: () {
                      Navigator.pop(ctx);
                      ReportShare.printPdf(
                        context,
                        filename: 'phieu-thu-01-TT.pdf',
                        build: () => ApprovalPdf.encode(
                          ApprovalItem(
                            id: 'PT-${DateTime.now().millisecondsSinceEpoch.toString().substring(7)}',
                            kind: 'deposit',
                            maker: SessionScope.maybeOf(context)?.user?.displayName ?? 'Thủ quỹ cửa hàng',
                            impact: '2.500.000 VND',
                            detail: 'Thu tiền doanh thu bán lẻ ca trực',
                            status: 'approved',
                          ),
                        ),
                      );
                    },
                  ),
                  _buildVoucherTile(
                    ctx,
                    title: 'Phiếu Chi Tiền Mặt (Mẫu 02-TT)',
                    subtitle: 'Chứng từ thanh toán / tạm ứng chi tiền từ két',
                    icon: Icons.remove_circle_outline_rounded,
                    color: const Color(0xFFDC2626),
                    onTap: () {
                      Navigator.pop(ctx);
                      ReportShare.printPdf(
                        context,
                        filename: 'phieu-chi-02-TT.pdf',
                        build: () => ApprovalPdf.encode(
                          ApprovalItem(
                            id: 'PC-${DateTime.now().millisecondsSinceEpoch.toString().substring(7)}',
                            kind: 'withdraw',
                            maker: SessionScope.maybeOf(context)?.user?.displayName ?? 'Thủ quỹ cửa hàng',
                            impact: '500.000 VND',
                            detail: 'Chi mua phụ liệu phát sinh tại quán',
                            status: 'approved',
                          ),
                        ),
                      );
                    },
                  ),
                  _buildVoucherTile(
                    ctx,
                    title: 'Biên Bản Kiểm Kê Kho & Bàn Giao Ca (Mẫu 05-VT)',
                    subtitle: 'Biên bản đối chiếu tồn sổ sách và thực tế kiểm đếm',
                    icon: Icons.fact_check_outlined,
                    color: const Color(0xFF7C3AED),
                    onTap: () {
                      Navigator.pop(ctx);
                      ReportShare.printPdf(
                        context,
                        filename: 'bien-ban-kiem-ke-05-VT.pdf',
                        build: () => ApprovalPdf.encode(
                          ApprovalItem(
                            id: 'BBKK-${DateTime.now().millisecondsSinceEpoch.toString().substring(7)}',
                            kind: 'stocktake',
                            maker: SessionScope.maybeOf(context)?.user?.displayName ?? 'Trưởng ca kiểm đếm',
                            impact: 'Khớp 100% số lượng',
                            detail: 'Bàn giao ca trực sáng chiều - kho bảo đảm niêm phong',
                            status: 'approved',
                          ),
                        ),
                      );
                    },
                  ),
                ],
              ),
            ),
          ),
        );
      },
    );
  }

  Widget _buildVoucherTile(
    BuildContext context, {
    required String title,
    required String subtitle,
    required IconData icon,
    required Color color,
    required VoidCallback onTap,
  }) {
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;

    return Card(
      margin: const EdgeInsets.only(bottom: 8),
      elevation: 0,
      color: isDark ? const Color(0xFF1E293B) : Colors.white,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(12),
        side: BorderSide(
          color: theme.colorScheme.outlineVariant.withValues(alpha: 0.5),
        ),
      ),
      clipBehavior: Clip.antiAlias,
      child: ListTile(
        onTap: onTap,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
        leading: Container(
          padding: const EdgeInsets.all(8),
          decoration: BoxDecoration(
            color: color.withValues(alpha: 0.1),
            borderRadius: BorderRadius.circular(8),
          ),
          child: Icon(icon, color: color, size: 20),
        ),
        title: Text(
          title,
          style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 13),
        ),
        subtitle: Text(
          subtitle,
          style: TextStyle(fontSize: 11, color: theme.colorScheme.onSurfaceVariant),
        ),
        trailing: const Icon(Icons.print_outlined, size: 18),
      ),
    );
  }
}

class _InventoryXntTab extends StatelessWidget {
  const _InventoryXntTab({required this.buckets});

  final List<InventoryBucket> buckets;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;

    double totalIn = 0;
    double totalOut = 0;
    int totalReceipts = 0;
    int totalIssues = 0;
    for (final b in buckets) {
      totalIn += b.inboundValue;
      totalOut += b.outboundValue;
      totalReceipts += b.receiptCount;
      totalIssues += b.issueCount;
    }
    final net = totalIn - totalOut;

    return SingleChildScrollView(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Container(
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
                    Container(
                      padding: const EdgeInsets.all(8),
                      decoration: BoxDecoration(
                        color: const Color(0xFF2563EB).withValues(alpha: 0.1),
                        borderRadius: BorderRadius.circular(8),
                      ),
                      child: const Icon(Icons.inventory_2_rounded,
                          color: Color(0xFF2563EB), size: 20),
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            'Báo Cáo Tổng Hợp Xuất - Nhập - Tồn (XNT)',
                            style: theme.textTheme.titleMedium?.copyWith(
                              fontWeight: FontWeight.bold,
                            ),
                          ),
                          Text(
                            'Tổng hợp số lượng nguyên vật liệu nhập kho và xuất quầy pha chế trong kỳ',
                            style: TextStyle(
                              fontSize: 12,
                              color: theme.colorScheme.onSurfaceVariant,
                            ),
                          ),
                        ],
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 16),
                Row(
                  children: [
                    Expanded(
                      child: _buildMetricMini(
                        title: 'TỔNG LƯỢNG NHẬP',
                        value: '+${AppFormat.quantity(totalIn.toStringAsFixed(0))}',
                        sub: '$totalReceipts phiếu nhập',
                        color: const Color(0xFF059669),
                      ),
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: _buildMetricMini(
                        title: 'TỔNG LƯỢNG XUẤT',
                        value: '-${AppFormat.quantity(totalOut.toStringAsFixed(0))}',
                        sub: '$totalIssues phiếu xuất',
                        color: const Color(0xFFDC2626),
                      ),
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: _buildMetricMini(
                        title: 'TỒN RÒNG (NET)',
                        value:
                            '${net >= 0 ? '+' : ''}${AppFormat.quantity(net.toStringAsFixed(0))}',
                        sub: net >= 0 ? 'Tồn tăng' : 'Tồn giảm',
                        color: const Color(0xFF2563EB),
                      ),
                    ),
                  ],
                ),
              ],
            ),
          ),
          const SizedBox(height: 16),
          InventoryChart(buckets: buckets),
          const SizedBox(height: 16),
          if (buckets.isNotEmpty)
            Container(
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
                  Text(
                    'Chi Tiết Theo Kỳ Đối Soát',
                    style: theme.textTheme.titleSmall?.copyWith(
                      fontWeight: FontWeight.bold,
                    ),
                  ),
                  const SizedBox(height: 12),
                  SingleChildScrollView(
                    scrollDirection: Axis.horizontal,
                    child: DataTable(
                      headingRowColor: WidgetStateProperty.all(
                        isDark
                            ? const Color(0xFF334155)
                            : const Color(0xFFF8FAFC),
                      ),
                      columns: const [
                        DataColumn(label: Text('Kỳ đối soát')),
                        DataColumn(label: Text('Nhập kho')),
                        DataColumn(label: Text('Xuất quầy')),
                        DataColumn(label: Text('Tồn ròng (Net)')),
                        DataColumn(label: Text('Phiếu nhập')),
                        DataColumn(label: Text('Phiếu xuất')),
                      ],
                      rows: buckets.map((b) {
                        final inVal = b.inboundValue;
                        final outVal = b.outboundValue;
                        final netVal = inVal - outVal;
                        return DataRow(
                          cells: [
                            DataCell(Text('Kỳ: ${b.bucket}',
                                style: const TextStyle(
                                    fontWeight: FontWeight.w600))),
                            DataCell(Text('+${b.inboundQty}',
                                style:
                                    const TextStyle(color: Color(0xFF059669)))),
                            DataCell(Text('-${b.outboundQty}',
                                style:
                                    const TextStyle(color: Color(0xFFDC2626)))),
                            DataCell(Text(
                              '${netVal >= 0 ? '+' : ''}${b.netQty}',
                              style: TextStyle(
                                fontWeight: FontWeight.bold,
                                color: netVal >= 0
                                    ? const Color(0xFF2563EB)
                                    : const Color(0xFFDC2626),
                              ),
                            )),
                            DataCell(Text('${b.receiptCount}')),
                            DataCell(Text('${b.issueCount}')),
                          ],
                        );
                      }).toList(),
                    ),
                  ),
                ],
              ),
            ),
        ],
      ),
    );
  }

  Widget _buildMetricMini(
      {required String title,
      required String value,
      required String sub,
      required Color color}) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.08),
        borderRadius: BorderRadius.circular(10),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(title,
              style: TextStyle(
                  fontSize: 10, fontWeight: FontWeight.bold, color: color)),
          const SizedBox(height: 4),
          Text(value,
              style: TextStyle(
                  fontSize: 16, fontWeight: FontWeight.bold, color: color)),
          const SizedBox(height: 2),
          Text(sub,
              style:
                  const TextStyle(fontSize: 11, color: Color(0xFF64748B))),
        ],
      ),
    );
  }
}

class _ReconciliationTab extends StatelessWidget {
  const _ReconciliationTab(
      {required this.runs,
      required this.canRun,
      required this.busy,
      required this.onRun});

  final List<ReconciliationRun> runs;
  final bool canRun;
  final bool busy;
  final ValueChanged<String> onRun;

  @override
  Widget build(BuildContext context) {
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        if (canRun)
          Padding(
            padding: const EdgeInsets.only(bottom: 12),
            child: Wrap(spacing: 8, children: [
              OutlinedButton.icon(
                  onPressed: busy ? null : () => onRun('cash'),
                  icon: const Icon(Icons.savings_outlined),
                  label: const Text('Đối soát quỹ')),
              OutlinedButton.icon(
                  onPressed: busy ? null : () => onRun('inventory'),
                  icon: const Icon(Icons.inventory_2_outlined),
                  label: const Text('Đối soát kho')),
            ]),
          ),
        if (runs.isEmpty)
          const EmptyView(
            title: 'Chưa có lượt đối soát',
            subtitle:
                'Chạy đối soát để kiểm tra chênh lệch giữa giao dịch và số dư.',
            icon: Icons.balance_outlined,
          ),
        for (final r in runs)
          Card(
            child: ListTile(
              title: Text('${r.id} [${r.status}]'),
              subtitle: Text('Ngoại lệ: ${r.exceptions.join(', ')}'),
              trailing: Icon(
                r.exceptions.isEmpty
                    ? Icons.check_circle_outline
                    : Icons.error_outline,
                color: r.exceptions.isEmpty
                    ? context.statusColors.success
                    : context.statusColors.danger,
              ),
            ),
          ),
      ],
    );
  }
}

class _ConsumptionTopTab extends StatelessWidget {
  const _ConsumptionTopTab({required this.items});

  final List<ConsumptionTopItem> items;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;

    if (items.isEmpty) {
      return const Center(
        child: Padding(
          padding: EdgeInsets.all(32),
          child: Text('Chưa có dữ liệu tiêu hao nguyên liệu trong kỳ.'),
        ),
      );
    }

    final maxQty = items.fold<double>(
      0.0,
      (max, it) {
        final q = double.tryParse(it.usedQty) ?? 0.0;
        return q > max ? q : max;
      },
    );

    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        Container(
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
                  Container(
                    padding: const EdgeInsets.all(8),
                    decoration: BoxDecoration(
                      color: const Color(0xFF2563EB).withValues(alpha: 0.1),
                      borderRadius: BorderRadius.circular(8),
                    ),
                    child: const Icon(Icons.leaderboard_rounded,
                        color: Color(0xFF2563EB), size: 20),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          'Top Nguyên Liệu Tiêu Hao (SRS §3.5)',
                          style: theme.textTheme.titleMedium?.copyWith(
                            fontWeight: FontWeight.bold,
                          ),
                        ),
                        Text(
                          'Tổng hợp lượng sử dụng qua các ca kiểm kê và xuất kho pha chế',
                          style: TextStyle(
                            fontSize: 12,
                            color: theme.colorScheme.onSurfaceVariant,
                          ),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 16),
              ListView.separated(
                shrinkWrap: true,
                physics: const NeverScrollableScrollPhysics(),
                itemCount: items.length,
                separatorBuilder: (_, __) => const Divider(height: 16),
                itemBuilder: (context, idx) {
                  final it = items[idx];
                  final qty = double.tryParse(it.usedQty) ?? 0.0;
                  final ratio =
                      maxQty > 0 ? (qty / maxQty).clamp(0.0, 1.0) : 0.0;

                  Color rankColor = Colors.grey;
                  if (idx == 0) rankColor = const Color(0xFFEAB308); // Gold
                  if (idx == 1) rankColor = const Color(0xFF94A3B8); // Silver
                  if (idx == 2) rankColor = const Color(0xFFB45309); // Bronze

                  return Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        children: [
                          Container(
                            width: 28,
                            height: 28,
                            alignment: Alignment.center,
                            decoration: BoxDecoration(
                              color: rankColor.withValues(alpha: 0.15),
                              shape: BoxShape.circle,
                            ),
                            child: Text(
                              '#${idx + 1}',
                              style: TextStyle(
                                fontWeight: FontWeight.w900,
                                fontSize: 12,
                                color: rankColor,
                              ),
                            ),
                          ),
                          const SizedBox(width: 12),
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text(
                                  it.name,
                                  style: const TextStyle(
                                    fontWeight: FontWeight.w700,
                                    fontSize: 14,
                                  ),
                                ),
                                Text(
                                  'SKU: ${it.sku}${it.category != null ? " • ${it.category}" : ""}',
                                  style: TextStyle(
                                    fontSize: 11.5,
                                    color:
                                        theme.colorScheme.onSurfaceVariant,
                                  ),
                                ),
                              ],
                            ),
                          ),
                          Text(
                            '${it.usedQty} ${it.unit ?? ""}',
                            style: const TextStyle(
                              fontWeight: FontWeight.w800,
                              fontSize: 14,
                              color: Color(0xFF2563EB),
                            ),
                          ),
                        ],
                      ),
                      const SizedBox(height: 6),
                      ClipRRect(
                        borderRadius: BorderRadius.circular(4),
                        child: LinearProgressIndicator(
                          value: ratio,
                          minHeight: 6,
                          backgroundColor: theme.colorScheme.outlineVariant
                              .withValues(alpha: 0.3),
                          color: const Color(0xFF2563EB),
                        ),
                      ),
                    ],
                  );
                },
              ),
            ],
          ),
        ),
      ],
    );
  }
}

class _ShiftHistoryTab extends StatelessWidget {
  const _ShiftHistoryTab({required this.items});

  final List<ShiftHistoryItem> items;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;

    if (items.isEmpty) {
      return const Center(
        child: Padding(
          padding: EdgeInsets.all(32),
          child: Text('Chưa có lịch sử chốt ca nào được ghi nhận.'),
        ),
      );
    }

    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        Container(
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
                  Container(
                    padding: const EdgeInsets.all(8),
                    decoration: BoxDecoration(
                      color: const Color(0xFF059669).withValues(alpha: 0.1),
                      borderRadius: BorderRadius.circular(8),
                    ),
                    child: const Icon(Icons.history_rounded,
                        color: Color(0xFF059669), size: 20),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          'Lịch Sử Chốt Ca & Đối Soát Nhân Viên (SRS §3.5)',
                          style: theme.textTheme.titleMedium?.copyWith(
                            fontWeight: FontWeight.bold,
                          ),
                        ),
                        Text(
                          'Theo dõi trách nhiệm từng ca làm việc, tỷ lệ khớp và độ lệch kiểm đếm',
                          style: TextStyle(
                            fontSize: 12,
                            color: theme.colorScheme.onSurfaceVariant,
                          ),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 16),
              ListView.separated(
                shrinkWrap: true,
                physics: const NeverScrollableScrollPhysics(),
                itemCount: items.length,
                separatorBuilder: (_, __) => const Divider(height: 1),
                itemBuilder: (context, idx) {
                  final it = items[idx];
                  final hasVariance = it.varianceLines > 0;

                  Color badgeColor = const Color(0xFF059669);
                  String statusText = 'Khớp hoàn toàn';
                  if (it.status == 'open') {
                    badgeColor = const Color(0xFF2563EB);
                    statusText = 'Đang kiểm đếm';
                  } else if (it.status == 'submitted') {
                    badgeColor = const Color(0xFFD97706);
                    statusText = 'Chờ duyệt';
                  } else if (hasVariance) {
                    badgeColor = const Color(0xFFDC2626);
                    statusText = 'Lệch ${it.varianceLines} mục';
                  }

                  return Padding(
                    padding: const EdgeInsets.symmetric(vertical: 12),
                    child: Row(
                      children: [
                        Container(
                          padding: const EdgeInsets.all(10),
                          decoration: BoxDecoration(
                            color: badgeColor.withValues(alpha: 0.1),
                            borderRadius: BorderRadius.circular(10),
                          ),
                          child: Icon(
                            hasVariance
                                ? Icons.warning_amber_rounded
                                : Icons.verified_outlined,
                            size: 20,
                            color: badgeColor,
                          ),
                        ),
                        const SizedBox(width: 14),
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Row(
                                children: [
                                  Text(
                                    it.shiftName,
                                    style: const TextStyle(
                                      fontWeight: FontWeight.w700,
                                      fontSize: 13.5,
                                    ),
                                  ),
                                  const SizedBox(width: 8),
                                  Container(
                                    padding: const EdgeInsets.symmetric(
                                        horizontal: 7, vertical: 2),
                                    decoration: BoxDecoration(
                                      color:
                                          badgeColor.withValues(alpha: 0.12),
                                      borderRadius: BorderRadius.circular(4),
                                    ),
                                    child: Text(
                                      statusText,
                                      style: TextStyle(
                                        color: badgeColor,
                                        fontSize: 10.5,
                                        fontWeight: FontWeight.bold,
                                      ),
                                    ),
                                  ),
                                ],
                              ),
                              const SizedBox(height: 4),
                              Text(
                                'Nhân viên: ${it.maker} • Ngày: ${it.businessDate ?? "Hôm nay"} • Tổng mục: ${it.lineCount}${it.completedAt != null ? " • Hoàn tất: ${it.completedAt!.substring(11, 16)}" : ""}',
                                style: TextStyle(
                                  fontSize: 11.5,
                                  color:
                                      theme.colorScheme.onSurfaceVariant,
                                ),
                              ),
                            ],
                          ),
                        ),
                        Column(
                          crossAxisAlignment: CrossAxisAlignment.end,
                          children: [
                            Text(
                              'Độ lệch: ${it.totalAbsVariance}',
                              style: TextStyle(
                                fontWeight: FontWeight.w700,
                                fontSize: 13,
                                color: hasVariance
                                    ? const Color(0xFFDC2626)
                                    : const Color(0xFF059669),
                              ),
                            ),
                            Text(
                              hasVariance ? 'Cần giải trình' : 'Chuẩn ca',
                              style: TextStyle(
                                fontSize: 10.5,
                                color:
                                    theme.colorScheme.onSurfaceVariant,
                              ),
                            ),
                          ],
                        ),
                      ],
                    ),
                  );
                },
              ),
            ],
          ),
        ),
      ],
    );
  }
}

class _ReportsData {
  const _ReportsData({
    required this.inventoryBuckets,
    required this.cashflowBuckets,
    required this.stagnationItems,
    required this.reconciliations,
    this.consumptionTop = const [],
    this.shiftHistory = const [],
  });

  final List<InventoryBucket> inventoryBuckets;
  final List<CashflowBucket> cashflowBuckets;
  final List<StagnationItem> stagnationItems;
  final List<ReconciliationRun> reconciliations;
  final List<ConsumptionTopItem> consumptionTop;
  final List<ShiftHistoryItem> shiftHistory;
}
