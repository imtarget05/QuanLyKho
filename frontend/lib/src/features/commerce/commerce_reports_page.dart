import 'dart:math' as math;

import 'package:fl_chart/fl_chart.dart';
import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import '../../core/i18n/app_i18n.dart';
import '../../core/util/csv_export.dart';
import 'commerce_memory_store.dart';

/// Báo cáo xuất nhập tồn kho Nguyên Vật Liệu (NVL) & Thành Phẩm (TP) chuẩn LenaKolia ERP.
class CommerceReportsPage extends StatefulWidget {
  const CommerceReportsPage({super.key, required this.store});
  final CommerceMemoryStore store;

  @override
  State<CommerceReportsPage> createState() => _CommerceReportsPageState();
}

class _CommerceReportsPageState extends State<CommerceReportsPage> {
  static const _slate900 = Color(0xFF0F172A);
  static const _slate700 = Color(0xFF334155);
  static const _slate600 = Color(0xFF475569);
  static const _slate500 = Color(0xFF64748B);
  static const _border = Color(0xFFE2E8F0);
  static const _primary = Color(0xFF6366F1);
  static const _green = Color(0xFF10B981);
  static const _amber = Color(0xFFF59E0B);
  static const _rose = Color(0xFFF43F5E);
  static const _blue = Color(0xFF0EA5E9);

  static const _periods = [
    'Hôm nay',
    '7 ngày qua',
    '30 ngày qua',
    'Năm nay',
    'Tùy chỉnh'
  ];
  String _period = 'Năm nay';
  String _itemTypeFilter = 'Tất cả'; // Tất cả, NVL, TP
  DateTimeRange? _customRange;

  final _money =
      NumberFormat.currency(locale: 'vi_VN', symbol: '₫', decimalDigits: 0);
  final _number = NumberFormat('#,##0.##', 'vi_VN');

  DateTimeRange get _range {
    final now = DateTime.now();
    if (_period == 'Tùy chỉnh' && _customRange != null) return _customRange!;
    if (_period == 'Hôm nay') {
      final start = DateTime(now.year, now.month, now.day);
      return DateTimeRange(start: start, end: now);
    }
    if (_period == '7 ngày qua') {
      return DateTimeRange(
          start: DateTime(now.year, now.month, now.day)
              .subtract(const Duration(days: 6)),
          end: now);
    }
    if (_period == '30 ngày qua') {
      return DateTimeRange(
          start: DateTime(now.year, now.month, now.day)
              .subtract(const Duration(days: 29)),
          end: now);
    }
    return DateTimeRange(start: DateTime(now.year), end: now);
  }

  List<CommerceOrder> get _sales => widget.store.confirmedSales
      .where((o) =>
          !o.createdAt.isBefore(_range.start) &&
          !o.createdAt.isAfter(_range.end.add(const Duration(days: 1))))
      .toList();

  List<CommerceOrder> get _purchases => widget.store.purchases
      .where((o) =>
          o.state == CommerceOrderState.completed &&
          !o.createdAt.isBefore(_range.start) &&
          !o.createdAt.isAfter(_range.end.add(const Duration(days: 1))))
      .toList();

  int get _revenue => _sales.fold(0, (sum, o) => sum + o.subtotal - o.discount);
  int get _grossRevenue => _sales.fold(0, (sum, o) => sum + o.subtotal);
  int get _discounts => _sales.fold(0, (sum, o) => sum + o.discount);
  int get _cogs => _sales.fold(
      0, (sum, o) => sum + o.lines.fold(0, (s, l) => s + l.costAmount));
  int get _grossProfit => _revenue - _cogs;
  double get _profitMargin =>
      _revenue == 0 ? 0.0 : (_grossProfit * 100 / _revenue);

  Future<void> _chooseRange() async {
    final now = DateTime.now();
    final selected = await showDateRangePicker(
      context: context,
      firstDate: DateTime(now.year - 5),
      lastDate: now,
      initialDateRange: _customRange ?? _range,
      builder: (context, child) => Theme(
        data: Theme.of(context).copyWith(
          colorScheme: const ColorScheme.light(
            primary: _primary,
            onPrimary: Colors.white,
            onSurface: _slate900,
          ),
        ),
        child: child!,
      ),
    );
    if (selected != null && mounted) {
      setState(() {
        _customRange = selected;
        _period = 'Tùy chỉnh';
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final compact = MediaQuery.sizeOf(context).width < 800;
    final rangeLabel =
        '${DateFormat('dd/MM/yyyy').format(_range.start)} – ${DateFormat('dd/MM/yyyy').format(_range.end)}';

    return SingleChildScrollView(
      padding:
          EdgeInsets.fromLTRB(compact ? 14 : 28, 20, compact ? 14 : 28, 32),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Header Bar & Controls
          _buildTopBar(compact, rangeLabel),
          const SizedBox(height: 18),

          // 6 Top Metric KPI Deck (LenaKolia Style)
          _buildKpiDeck(compact),
          const SizedBox(height: 20),

          // 3 Charts Section: Multiaxis Bar, Donut Breakdown, Line Trend
          _buildChartsSection(compact),
          const SizedBox(height: 20),

          // P&L Statement Card (Báo cáo Kết quả Kinh doanh Tổng hợp)
          _buildPnlStatementCard(compact),
          const SizedBox(height: 20),

          // Comprehensive NVL & TP Inventory Ledger Table
          _buildInventoryLedgerTable(compact),
        ],
      ),
    );
  }

  Widget _buildTopBar(bool compact, String rangeLabel) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    context.tr('reports_lenakolia_title'),
                    style: const TextStyle(
                      fontSize: 22,
                      fontWeight: FontWeight.w800,
                      color: _slate900,
                      letterSpacing: -.5,
                    ),
                  ),
                  const SizedBox(height: 4),
                  Text(
                    context.tr('reports_lenakolia_subtitle'),
                    style: const TextStyle(fontSize: 12, color: _slate500),
                  ),
                ],
              ),
            ),
            if (!compact) _buildExportButtons(),
          ],
        ),
        const SizedBox(height: 16),
        Wrap(
          spacing: 8,
          runSpacing: 8,
          crossAxisAlignment: WrapCrossAlignment.center,
          children: [
            for (final p in _periods)
              ChoiceChip(
                label: Text(p == 'Hôm nay'
                    ? context.tr('orders_filter_today')
                    : p == '7 ngày qua'
                        ? context.tr('orders_filter_7d')
                        : p == '30 ngày qua'
                            ? context.tr('orders_filter_30d')
                            : p == 'Năm nay'
                                ? context.tr('reports_period_this_year')
                                : context.tr('reports_period_custom')),
                selected: _period == p,
                onSelected: (_) => p == 'Tùy chỉnh'
                    ? _chooseRange()
                    : setState(() => _period = p),
                selectedColor: const Color(0xFFEEF2FF),
                labelStyle: TextStyle(
                  fontSize: 11.5,
                  fontWeight: _period == p ? FontWeight.w700 : FontWeight.w500,
                  color: _period == p ? _primary : _slate700,
                ),
                side: BorderSide(
                  color: _period == p ? _primary : _border,
                ),
                shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(8)),
              ),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 7),
              decoration: BoxDecoration(
                color: Colors.white,
                borderRadius: BorderRadius.circular(8),
                border: Border.all(color: _border),
              ),
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  const Icon(Icons.calendar_today_outlined,
                      size: 14, color: _slate500),
                  const SizedBox(width: 6),
                  Text(
                    rangeLabel,
                    style: const TextStyle(
                      fontSize: 11.5,
                      fontWeight: FontWeight.w700,
                      color: _slate900,
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(width: 4),
            // Filter NVL / TP
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 2),
              decoration: BoxDecoration(
                color: Colors.white,
                borderRadius: BorderRadius.circular(8),
                border: Border.all(color: _border),
              ),
              child: DropdownButtonHideUnderline(
                child: DropdownButton<String>(
                  value: _itemTypeFilter,
                  isDense: true,
                  style: const TextStyle(
                      fontSize: 11.5,
                      fontWeight: FontWeight.w600,
                      color: _slate900),
                  items: [
                    DropdownMenuItem(
                        value: 'Tất cả', child: Text(context.tr('reports_cat_all'))),
                    DropdownMenuItem(
                        value: 'NVL', child: Text(context.tr('reports_cat_raw'))),
                    DropdownMenuItem(
                        value: 'TP', child: Text(context.tr('reports_cat_finished'))),
                  ],
                  onChanged: (val) {
                    if (val != null) setState(() => _itemTypeFilter = val);
                  },
                ),
              ),
            ),
            if (compact) _buildExportButtons(),
          ],
        ),
      ],
    );
  }

  Widget _buildExportButtons() {
    return Wrap(
      spacing: 8,
      children: [
        OutlinedButton.icon(
          onPressed: _exportExcel,
          icon: const Icon(Icons.table_chart_outlined, size: 16),
          label: Text(context.tr('reports_export_xlsx')),
          style: OutlinedButton.styleFrom(
            foregroundColor: _slate900,
            side: const BorderSide(color: _border),
            backgroundColor: Colors.white,
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 9),
            textStyle:
                const TextStyle(fontSize: 11.5, fontWeight: FontWeight.w700),
            shape:
                RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
          ),
        ),
      ],
    );
  }

  void _exportExcel() {
    final products = widget.store.products;
    final rows = <List<dynamic>>[];
    for (final p in products) {
      final type = _inventoryType(p.category);
      if (_itemTypeFilter != 'Tất cả' && type != _itemTypeFilter) continue;

      rows.add([
        p.sku,
        p.name,
        type,
        p.unit,
        p.stock,
        p.cost,
        (p.stock * p.cost).round(),
      ]);
    }

    CsvExport.copyToClipboard(
      context,
      label: 'Tồn kho hiện tại NVL & TP',
      headers: const [
        'Mã hàng',
        'Tên hàng',
        'Phân loại',
        'ĐVT',
        'Tồn hiện tại (SL)',
        'Đơn giá vốn',
        'Giá trị tồn hiện tại',
      ],
      rows: rows,
    );
  }

  String _inventoryType(String category) {
    final normalized = category.trim().toLowerCase();
    if (normalized.contains('nguyên liệu')) return 'NVL';
    if (normalized.contains('thành phẩm') || normalized.contains('thực phẩm')) {
      return 'TP';
    }
    return 'Khác';
  }

  Widget _buildKpiDeck(bool compact) {
    final kpis = [
      _KpiItem(
        title: 'Doanh thu',
        amount: _money.format(_revenue),
        icon: Icons.payments_rounded,
        color: _green,
        subtitle: '${_sales.length} đơn bán hoàn tất',
      ),
      _KpiItem(
        title: 'Tổng giá vốn (COGS)',
        amount: _money.format(_cogs),
        icon: Icons.inventory_2_rounded,
        color: _blue,
        subtitle: 'Giá vốn theo định mức kho',
      ),
      _KpiItem(
        title: 'Lợi nhuận gộp',
        amount: _money.format(_grossProfit),
        icon: Icons.trending_up_rounded,
        color: _primary,
        subtitle: 'Doanh thu - Giá vốn bán',
      ),
      _KpiItem(
        title: 'Tỷ suất lợi nhuận',
        amount: '${_profitMargin.toStringAsFixed(1)}%',
        icon: Icons.pie_chart_outline_rounded,
        color: _amber,
        subtitle: 'Biên LN gộp / Doanh thu',
      ),
      _KpiItem(
        title: 'Số đơn phát sinh',
        amount: '${_sales.length + _purchases.length}',
        icon: Icons.receipt_long_rounded,
        color: const Color(0xFF8B5CF6),
        subtitle: '${_sales.length} bán · ${_purchases.length} nhập',
      ),
      _KpiItem(
        title: 'Công nợ tồn đọng',
        amount: _money
            .format(widget.store.receivableTotal + widget.store.payableTotal),
        icon: Icons.account_balance_wallet_rounded,
        color: _rose,
        subtitle:
            'Thu: ${_money.format(widget.store.receivableTotal)} · Trả: ${_money.format(widget.store.payableTotal)}',
      ),
    ];

    return LayoutBuilder(builder: (context, constraints) {
      final cols = constraints.maxWidth >= 1050
          ? 6
          : constraints.maxWidth >= 720
              ? 3
              : 2;
      const gap = 12.0;
      final width = (constraints.maxWidth - gap * (cols - 1)) / cols;

      return Wrap(
        spacing: gap,
        runSpacing: gap,
        children: [
          for (final kpi in kpis)
            SizedBox(
              width: width,
              child: Container(
                padding:
                    const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
                decoration: BoxDecoration(
                  color: Colors.white,
                  borderRadius: BorderRadius.circular(12),
                  border: Border.all(color: _border),
                  boxShadow: const [
                    BoxShadow(
                        color: Color(0x05000000),
                        blurRadius: 4,
                        offset: Offset(0, 2))
                  ],
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Container(
                          padding: const EdgeInsets.all(6),
                          decoration: BoxDecoration(
                            color: kpi.color.withValues(alpha: 0.12),
                            borderRadius: BorderRadius.circular(8),
                          ),
                          child: Icon(kpi.icon, size: 16, color: kpi.color),
                        ),
                        const SizedBox(width: 8),
                        Expanded(
                          child: Text(
                            kpi.title,
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: const TextStyle(
                              fontSize: 11,
                              fontWeight: FontWeight.w600,
                              color: _slate600,
                            ),
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 10),
                    FittedBox(
                      fit: BoxFit.scaleDown,
                      alignment: Alignment.centerLeft,
                      child: Text(
                        kpi.amount,
                        style: const TextStyle(
                          fontSize: 17,
                          fontWeight: FontWeight.w800,
                          color: _slate900,
                          letterSpacing: -.3,
                        ),
                      ),
                    ),
                    const SizedBox(height: 4),
                    Text(
                      kpi.subtitle,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(fontSize: 10, color: _slate500),
                    ),
                  ],
                ),
              ),
            ),
        ],
      );
    });
  }

  Widget _buildChartsSection(bool compact) {
    return LayoutBuilder(builder: (context, constraints) {
      if (constraints.maxWidth < 950) {
        return Column(
          children: [
            _buildMultiaxisBarChartCard(),
            const SizedBox(height: 16),
            _buildRevenueDonutCard(),
            const SizedBox(height: 16),
            _buildProfitTrendLineCard(),
          ],
        );
      }

      return Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Expanded(flex: 5, child: _buildMultiaxisBarChartCard()),
          const SizedBox(width: 14),
          Expanded(flex: 3, child: _buildRevenueDonutCard()),
          const SizedBox(width: 14),
          Expanded(flex: 4, child: _buildProfitTrendLineCard()),
        ],
      );
    });
  }

  Widget _buildMultiaxisBarChartCard() {
    final buckets = _generateBuckets();
    final maxY = buckets.isEmpty
        ? 1.0
        : buckets
            .map((e) => math.max(e.revenue, math.max(e.cogs, e.profit)))
            .fold<double>(0, math.max);
    final safeMax = maxY <= 0 ? 1000000.0 : maxY * 1.25;

    return _cardWrapper(
      title: 'Doanh thu, COGS & Lợi nhuận',
      subtitle: 'So sánh cấu phần tài chính qua các chu kỳ',
      child: Column(
        children: [
          Row(
            children: [
              _legendDot(_primary, 'Doanh thu'),
              const SizedBox(width: 12),
              _legendDot(_blue, 'COGS (Giá vốn)'),
              const SizedBox(width: 12),
              _legendDot(_green, 'Lợi nhuận'),
            ],
          ),
          const SizedBox(height: 16),
          SizedBox(
            height: 220,
            child: BarChart(
              BarChartData(
                maxY: safeMax,
                barTouchData: BarTouchData(enabled: true),
                gridData: FlGridData(
                  show: true,
                  drawVerticalLine: false,
                  getDrawingHorizontalLine: (_) =>
                      const FlLine(color: Color(0xFFF1F5F9), strokeWidth: 1),
                ),
                borderData: FlBorderData(show: false),
                titlesData: FlTitlesData(
                  topTitles: const AxisTitles(
                      sideTitles: SideTitles(showTitles: false)),
                  rightTitles: const AxisTitles(
                      sideTitles: SideTitles(showTitles: false)),
                  leftTitles: AxisTitles(
                    sideTitles: SideTitles(
                      showTitles: true,
                      reservedSize: 42,
                      getTitlesWidget: (v, _) => Text(
                        _axisLabel(v),
                        style: const TextStyle(fontSize: 9, color: _slate500),
                      ),
                    ),
                  ),
                  bottomTitles: AxisTitles(
                    sideTitles: SideTitles(
                      showTitles: true,
                      reservedSize: 24,
                      getTitlesWidget: (v, _) {
                        final i = v.toInt();
                        if (i < 0 || i >= buckets.length)
                          return const SizedBox.shrink();
                        return Padding(
                          padding: const EdgeInsets.only(top: 6),
                          child: Text(
                            buckets[i].label,
                            style: const TextStyle(
                                fontSize: 9.5,
                                color: _slate700,
                                fontWeight: FontWeight.w600),
                          ),
                        );
                      },
                    ),
                  ),
                ),
                barGroups: [
                  for (var i = 0; i < buckets.length; i++)
                    BarChartGroupData(
                      x: i,
                      barsSpace: 3,
                      barRods: [
                        BarChartRodData(
                          toY: buckets[i].revenue,
                          color: _primary,
                          width: 8,
                          borderRadius: BorderRadius.circular(3),
                        ),
                        BarChartRodData(
                          toY: buckets[i].cogs,
                          color: _blue,
                          width: 8,
                          borderRadius: BorderRadius.circular(3),
                        ),
                        BarChartRodData(
                          toY: buckets[i].profit,
                          color: _green,
                          width: 8,
                          borderRadius: BorderRadius.circular(3),
                        ),
                      ],
                    ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildRevenueDonutCard() {
    // Phân bổ tỷ trọng nhóm: NVL vs Thành phẩm vs Khác
    double nvlSales = 0;
    double tpSales = 0;
    for (final order in _sales) {
      for (final line in order.lines) {
        final isNvl = line.name.toLowerCase().contains('trà') ||
            line.name.toLowerCase().contains('đường') ||
            line.name.toLowerCase().contains('sữa') ||
            line.name.toLowerCase().contains('topping');
        if (isNvl) {
          nvlSales += line.amount;
        } else {
          tpSales += line.amount;
        }
      }
    }
    final total = nvlSales + tpSales;
    final nvlPct = total <= 0 ? 0.0 : (nvlSales * 100 / total);
    final tpPct = total <= 0 ? 0.0 : (tpSales * 100 / total);

    return _cardWrapper(
      title: 'Cơ cấu Doanh thu',
      subtitle: 'Tỷ trọng đóng góp NVL vs Thành phẩm',
      child: Column(
        children: [
          SizedBox(
            height: 155,
            child: total <= 0
                ? const Center(
                    child: Text(
                      'Chưa có doanh thu trong kỳ.',
                      style: TextStyle(fontSize: 11, color: _slate500),
                    ),
                  )
                : PieChart(
                    PieChartData(
                      centerSpaceRadius: 38,
                      sectionsSpace: 4,
                      sections: [
                        PieChartSectionData(
                          value: nvlPct,
                          color: _amber,
                          radius: 20,
                          showTitle: false,
                        ),
                        PieChartSectionData(
                          value: tpPct,
                          color: _primary,
                          radius: 20,
                          showTitle: false,
                        ),
                      ],
                    ),
                  ),
          ),
          const SizedBox(height: 14),
          Wrap(
            alignment: WrapAlignment.center,
            spacing: 12,
            runSpacing: 8,
            children: [
              _donutLegend('NVL', _amber, '${nvlPct.toStringAsFixed(1)}%'),
              _donutLegend(
                  'Thành phẩm', _primary, '${tpPct.toStringAsFixed(1)}%'),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildProfitTrendLineCard() {
    final buckets = _generateBuckets();
    final spots = <FlSpot>[];
    for (var i = 0; i < buckets.length; i++) {
      spots.add(FlSpot(i.toDouble(), buckets[i].profit));
    }
    final maxY =
        spots.isEmpty ? 1.0 : spots.map((s) => s.y).fold<double>(0, math.max);

    return _cardWrapper(
      title: 'Xu hướng Lợi nhuận',
      subtitle: 'Biến thiên biên độ lợi nhuận ròng',
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              _legendDot(_green, 'Lợi nhuận ròng'),
              const Spacer(),
              Text(
                'Biên LN: ${_profitMargin.toStringAsFixed(1)}%',
                style: const TextStyle(
                    fontSize: 10, fontWeight: FontWeight.w700, color: _green),
              ),
            ],
          ),
          const SizedBox(height: 16),
          SizedBox(
            height: 220,
            child: LineChart(
              LineChartData(
                minY: 0,
                maxY: maxY <= 0 ? 1000000 : maxY * 1.25,
                gridData: FlGridData(
                  show: true,
                  drawVerticalLine: false,
                  getDrawingHorizontalLine: (_) =>
                      const FlLine(color: Color(0xFFF1F5F9), strokeWidth: 1),
                ),
                borderData: FlBorderData(show: false),
                titlesData: FlTitlesData(
                  topTitles: const AxisTitles(
                      sideTitles: SideTitles(showTitles: false)),
                  rightTitles: const AxisTitles(
                      sideTitles: SideTitles(showTitles: false)),
                  leftTitles: AxisTitles(
                    sideTitles: SideTitles(
                      showTitles: true,
                      reservedSize: 42,
                      getTitlesWidget: (v, _) => Text(
                        _axisLabel(v),
                        style: const TextStyle(fontSize: 9, color: _slate500),
                      ),
                    ),
                  ),
                  bottomTitles: AxisTitles(
                    sideTitles: SideTitles(
                      showTitles: true,
                      reservedSize: 24,
                      getTitlesWidget: (v, _) {
                        final i = v.toInt();
                        if (i < 0 || i >= buckets.length)
                          return const SizedBox.shrink();
                        return Padding(
                          padding: const EdgeInsets.only(top: 6),
                          child: Text(
                            buckets[i].label,
                            style: const TextStyle(
                                fontSize: 9.5,
                                color: _slate700,
                                fontWeight: FontWeight.w600),
                          ),
                        );
                      },
                    ),
                  ),
                ),
                lineBarsData: [
                  LineChartBarData(
                    spots: spots.isEmpty ? [const FlSpot(0, 0)] : spots,
                    isCurved: true,
                    color: _green,
                    barWidth: 3,
                    isStrokeCapRound: true,
                    dotData: FlDotData(
                      show: true,
                      getDotPainter: (spot, percent, barData, index) =>
                          FlDotCirclePainter(
                        radius: 4,
                        color: Colors.white,
                        strokeWidth: 2.5,
                        strokeColor: _green,
                      ),
                    ),
                    belowBarData: BarAreaData(
                      show: true,
                      color: _green.withValues(alpha: 0.08),
                    ),
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildPnlStatementCard(bool compact) {
    final grossRevenue = _grossRevenue;
    final discount = _discounts;
    final netRevenue = _revenue;
    final cogs = _cogs;
    final grossProfit = netRevenue - cogs;

    return _cardWrapper(
      title: 'Báo cáo Kết quả Kinh doanh Tổng hợp (P&L)',
      subtitle: 'Doanh thu thuần và lợi nhuận gộp từ phiếu bán đã hoàn tất',
      child: Column(
        children: [
          _pnlRow('1. Doanh thu bán hàng & cung cấp dịch vụ',
              _money.format(grossRevenue),
              isBold: true),
          _pnlRow('2. Các khoản giảm trừ doanh thu (Chiết khấu, giảm giá)',
              _money.format(discount)),
          _pnlRow('3. Doanh thu thuần về bán hàng & dịch vụ',
              _money.format(netRevenue),
              isHighlight: true),
          _pnlRow('4. Giá vốn hàng bán (COGS - Nguyên vật liệu & thành phẩm)',
              '- ${_money.format(cogs)}',
              color: _rose),
          _pnlRow('5. Lợi nhuận gộp về bán hàng', _money.format(grossProfit),
              isBold: true, color: _primary),
          const Divider(height: 20, color: _border),
          const Align(
            alignment: Alignment.centerLeft,
            child: Text(
              'Chưa có dữ liệu chi phí vận hành để tính EBIT.',
              style: TextStyle(fontSize: 11, color: _slate500),
            ),
          ),
        ],
      ),
    );
  }

  Widget _pnlRow(String label, String value,
      {bool isBold = false, bool isHighlight = false, Color? color}) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      decoration: BoxDecoration(
        color: isHighlight ? const Color(0xFFF8FAFC) : Colors.transparent,
        borderRadius: BorderRadius.circular(6),
      ),
      child: Row(
        children: [
          Expanded(
            child: Text(
              label,
              style: TextStyle(
                fontSize: 12,
                fontWeight: isBold ? FontWeight.w700 : FontWeight.w500,
                color: _slate900,
              ),
            ),
          ),
          Text(
            value,
            style: TextStyle(
              fontSize: 12.5,
              fontWeight: isBold ? FontWeight.w800 : FontWeight.w600,
              color: color ?? _slate900,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildInventoryLedgerTable(bool compact) {
    final products = widget.store.products;
    final filtered = products.where((p) {
      if (_itemTypeFilter == 'Tất cả') return true;
      return _inventoryType(p.category) == _itemTypeFilter;
    }).toList();

    return _cardWrapper(
      title: 'Tồn kho hiện tại NVL & TP',
      subtitle: 'Ảnh chụp số lượng và giá trị tồn theo giá vốn hiện tại',
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          SingleChildScrollView(
            scrollDirection: Axis.horizontal,
            child: DataTable(
              headingRowHeight: 40,
              dataRowMinHeight: 44,
              dataRowMaxHeight: 44,
              horizontalMargin: 12,
              columnSpacing: 18,
              headingRowColor: WidgetStateProperty.all(const Color(0xFFF8FAFC)),
              columns: const [
                DataColumn(
                    label: Text('Mã SKU',
                        style: TextStyle(
                            fontWeight: FontWeight.w700,
                            fontSize: 11,
                            color: _slate700))),
                DataColumn(
                    label: Text('Tên sản phẩm / NVL',
                        style: TextStyle(
                            fontWeight: FontWeight.w700,
                            fontSize: 11,
                            color: _slate700))),
                DataColumn(
                    label: Text('Loại',
                        style: TextStyle(
                            fontWeight: FontWeight.w700,
                            fontSize: 11,
                            color: _slate700))),
                DataColumn(
                    label: Text('Tồn hiện tại (SL)',
                        style: TextStyle(
                            fontWeight: FontWeight.w700,
                            fontSize: 11,
                            color: _slate700))),
                DataColumn(
                    label: Text('Đơn giá vốn',
                        style: TextStyle(
                            fontWeight: FontWeight.w700,
                            fontSize: 11,
                            color: _slate700))),
                DataColumn(
                    label: Text('Giá trị tồn hiện tại',
                        style: TextStyle(
                            fontWeight: FontWeight.w700,
                            fontSize: 11,
                            color: _slate700))),
              ],
              rows: [
                for (final p in filtered) ...[
                  () {
                    final type = _inventoryType(p.category);
                    final isNvl = type == 'NVL';
                    final closingQty = p.stock;
                    final closingVal = closingQty * p.cost;

                    return DataRow(
                      cells: [
                        DataCell(Text(p.sku,
                            style: const TextStyle(
                                fontSize: 11,
                                fontWeight: FontWeight.w600,
                                color: _primary))),
                        DataCell(Text(p.name,
                            style: const TextStyle(
                                fontSize: 11.5,
                                fontWeight: FontWeight.w600,
                                color: _slate900))),
                        DataCell(Container(
                          padding: const EdgeInsets.symmetric(
                              horizontal: 6, vertical: 2),
                          decoration: BoxDecoration(
                            color: isNvl
                                ? const Color(0xFFFEF3C7)
                                : const Color(0xFFEEF2FF),
                            borderRadius: BorderRadius.circular(4),
                          ),
                          child: Text(
                            type,
                            style: TextStyle(
                              fontSize: 9.5,
                              fontWeight: FontWeight.w700,
                              color: isNvl ? const Color(0xFFD97706) : _primary,
                            ),
                          ),
                        )),
                        DataCell(Text(_number.format(closingQty),
                            style: const TextStyle(
                                fontSize: 11, color: _slate700))),
                        DataCell(Text(_money.format(p.cost),
                            style: const TextStyle(
                                fontSize: 11, color: _slate700))),
                        DataCell(Text(_money.format(closingVal),
                            style: const TextStyle(
                                fontSize: 11.5,
                                fontWeight: FontWeight.w700,
                                color: _slate900))),
                      ],
                    );
                  }()
                ],
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _cardWrapper(
      {required String title,
      required String subtitle,
      required Widget child}) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: _border),
        boxShadow: const [
          BoxShadow(
              color: Color(0x06000000), blurRadius: 6, offset: Offset(0, 2))
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(title,
              style: const TextStyle(
                  fontSize: 14.5,
                  fontWeight: FontWeight.w800,
                  color: _slate900)),
          const SizedBox(height: 3),
          Text(subtitle,
              style: const TextStyle(fontSize: 11, color: _slate500)),
          const SizedBox(height: 16),
          child,
        ],
      ),
    );
  }

  Widget _legendDot(Color color, String label) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Container(
            width: 8,
            height: 8,
            decoration: BoxDecoration(color: color, shape: BoxShape.circle)),
        const SizedBox(width: 6),
        Text(label,
            style: const TextStyle(
                fontSize: 10.5, fontWeight: FontWeight.w600, color: _slate700)),
      ],
    );
  }

  Widget _donutLegend(String label, Color color, String pct) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Container(
            width: 10,
            height: 10,
            decoration: BoxDecoration(
                color: color, borderRadius: BorderRadius.circular(3))),
        const SizedBox(width: 7),
        Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(label,
                style: const TextStyle(
                    fontSize: 10.5,
                    fontWeight: FontWeight.w600,
                    color: _slate700)),
            Text(pct,
                style: const TextStyle(
                    fontSize: 12,
                    fontWeight: FontWeight.w800,
                    color: _slate900)),
          ],
        ),
      ],
    );
  }

  List<_ReportBucket> _generateBuckets() {
    final range = _range;
    final days = range.end.difference(range.start).inDays + 1;
    final months = _period == 'Năm nay' || days > 180;
    final count = months ? 12 : math.min(days, 7);

    final buckets = List.generate(count, (i) {
      final label = months ? 'T${i + 1}' : 'N${i + 1}';
      return _ReportBucket(label);
    });

    for (final sale in _sales) {
      final dayOffset = sale.createdAt.difference(range.start).inDays;
      final idx = months
          ? (sale.createdAt.month - 1)
          : days <= count
              ? dayOffset
              : (dayOffset * count / days).floor();
      if (idx >= 0 && idx < buckets.length) {
        final netRevenue = sale.subtotal - sale.discount;
        buckets[idx].revenue += netRevenue.toDouble();
        final cost =
            sale.lines.fold<int>(0, (s, l) => s + l.costAmount).toDouble();
        buckets[idx].cogs += cost;
        buckets[idx].profit += (netRevenue - cost);
      }
    }
    return buckets;
  }

  String _axisLabel(double value) {
    if (value >= 1000000) return '${(value / 1000000).toStringAsFixed(0)}tr';
    if (value >= 1000) return '${(value / 1000).toStringAsFixed(0)}k';
    return value.toStringAsFixed(0);
  }
}

class _KpiItem {
  const _KpiItem({
    required this.title,
    required this.amount,
    required this.icon,
    required this.color,
    required this.subtitle,
  });
  final String title;
  final String amount;
  final IconData icon;
  final Color color;
  final String subtitle;
}

class _ReportBucket {
  _ReportBucket(this.label);
  final String label;
  double revenue = 0;
  double cogs = 0;
  double profit = 0;
}
