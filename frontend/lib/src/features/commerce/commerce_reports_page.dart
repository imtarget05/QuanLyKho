import 'dart:math' as math;

import 'package:fl_chart/fl_chart.dart';
import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import '../../core/util/csv_export.dart';
import 'commerce_memory_store.dart';

class CommerceReportsPage extends StatefulWidget {
  const CommerceReportsPage({super.key, required this.store});
  final CommerceMemoryStore store;

  @override
  State<CommerceReportsPage> createState() => _CommerceReportsPageState();
}

class _CommerceReportsPageState extends State<CommerceReportsPage> {
  static const _ink = Color(0xFF20271F);
  static const _muted = Color(0xFF778078);
  static const _green = Color(0xFF287A59);
  static const _purple = Color(0xFF7955C8);
  static const _periods = ['7 ngày qua', '30 ngày qua', 'Năm nay', 'Tùy chỉnh'];
  String _period = 'Năm nay';
  DateTimeRange? _customRange;
  final _money =
      NumberFormat.currency(locale: 'vi_VN', symbol: '₫', decimalDigits: 0);
  final _number = NumberFormat('#,##0.##', 'vi_VN');

  DateTimeRange get _range {
    final now = DateTime.now();
    if (_period == 'Tùy chỉnh' && _customRange != null) return _customRange!;
    if (_period == '7 ngày qua')
      return DateTimeRange(
          start: DateTime(now.year, now.month, now.day)
              .subtract(const Duration(days: 6)),
          end: now);
    if (_period == '30 ngày qua')
      return DateTimeRange(
          start: DateTime(now.year, now.month, now.day)
              .subtract(const Duration(days: 29)),
          end: now);
    return DateTimeRange(start: DateTime(now.year), end: now);
  }

  List<CommerceOrder> get _sales => widget.store.confirmedSales
      .where((o) =>
          !o.createdAt.isBefore(_range.start) &&
          !o.createdAt.isAfter(_range.end.add(const Duration(days: 1))))
      .toList();
  int get _revenue => _sales.fold(0, (sum, o) => sum + o.total);
  int get _cost => _sales.fold(
      0, (sum, o) => sum + o.lines.fold(0, (s, l) => s + l.costAmount));
  int get _profit => _revenue - _cost;

  Future<void> _chooseRange() async {
    final now = DateTime.now();
    final selected = await showDateRangePicker(
        context: context,
        firstDate: DateTime(now.year - 5),
        lastDate: now,
        initialDateRange: _customRange ?? _range);
    if (selected != null && mounted)
      setState(() {
        _customRange = selected;
        _period = 'Tùy chỉnh';
      });
  }

  @override
  Widget build(BuildContext context) {
    final products = widget.store.products;
    final inventoryCategories = <String, double>{};
    for (final p in products) {
      inventoryCategories[p.category] =
          (inventoryCategories[p.category] ?? 0) + p.stock * p.cost;
    }
    final categories = inventoryCategories.entries.toList()
      ..sort((a, b) => b.value.compareTo(a.value));
    final sold = <String, double>{};
    final customers = <String, int>{};
    for (final order in _sales) {
      customers[order.partyName] =
          (customers[order.partyName] ?? 0) + order.total;
      for (final line in order.lines) {
        sold[line.name] = (sold[line.name] ?? 0) + line.quantity;
      }
    }
    final topProducts = sold.entries.toList()
      ..sort((a, b) => b.value.compareTo(a.value));
    final topCustomers = customers.entries.toList()
      ..sort((a, b) => b.value.compareTo(a.value));
    final warnings = products.where((p) => p.stock <= p.minimum).toList()
      ..sort((a, b) => (a.stock - a.minimum).compareTo(b.stock - b.minimum));
    final compact = MediaQuery.sizeOf(context).width < 900;
    final rangeLabel =
        '${DateFormat('dd/MM/yyyy').format(_range.start)} – ${DateFormat('dd/MM/yyyy').format(_range.end)}';
    return SingleChildScrollView(
      padding:
          EdgeInsets.fromLTRB(compact ? 16 : 28, 22, compact ? 16 : 28, 32),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Expanded(
              child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                const Text('Báo cáo & phân tích',
                    style: TextStyle(
                        fontSize: 25,
                        fontWeight: FontWeight.w800,
                        color: _ink,
                        letterSpacing: -.5)),
                const SizedBox(height: 5),
                Text('Nắm nhanh doanh thu, lợi nhuận và tình hình kho.',
                    style: TextStyle(color: _muted, fontSize: 13)),
              ])),
          if (!compact) _exportButton(),
        ]),
        const SizedBox(height: 20),
        Wrap(
            spacing: 8,
            runSpacing: 8,
            crossAxisAlignment: WrapCrossAlignment.center,
            children: [
              for (final period in _periods)
                ChoiceChip(
                    label: Text(period),
                    selected: _period == period,
                    onSelected: (_) => period == 'Tùy chỉnh'
                        ? _chooseRange()
                        : setState(() => _period = period)),
              Container(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 11, vertical: 9),
                  decoration: BoxDecoration(
                      color: Colors.white,
                      borderRadius: BorderRadius.circular(10),
                      border: Border.all(color: const Color(0xFFE8EBE7))),
                  child: Row(mainAxisSize: MainAxisSize.min, children: [
                    const Icon(Icons.calendar_month_outlined,
                        size: 16, color: _muted),
                    const SizedBox(width: 7),
                    Text(rangeLabel,
                        style: const TextStyle(
                            color: _ink,
                            fontSize: 12,
                            fontWeight: FontWeight.w600))
                  ])),
              if (compact) _exportButton(),
            ]),
        const SizedBox(height: 18),
        LayoutBuilder(builder: (context, box) {
          final cols = box.maxWidth > 1000
              ? 4
              : box.maxWidth > 340
                  ? 2
                  : 1;
          final cards = [
            _Metric(
                'Doanh thu thuần',
                _money.format(_revenue),
                Icons.payments_outlined,
                _green,
                '${_sales.length} đơn hoàn tất'),
            _Metric(
                'Lợi nhuận gộp',
                _money.format(_profit),
                Icons.trending_up_rounded,
                _purple,
                'Biên lợi nhuận ${_revenue == 0 ? '0' : (_profit * 100 / _revenue).toStringAsFixed(1)}%'),
            _Metric(
                'Số đơn bán',
                _number.format(_sales.length),
                Icons.receipt_long_outlined,
                const Color(0xFFCE8C39),
                'Trong khoảng thời gian đã chọn'),
            _Metric(
                'Công nợ phải thu',
                _money.format(widget.store.receivableTotal),
                Icons.account_balance_wallet_outlined,
                const Color(0xFF4C83AA),
                'Tất cả đơn chưa thu đủ'),
            _Metric(
                'Giá vốn đã bán',
                _money.format(_cost),
                Icons.inventory_2_outlined,
                const Color(0xFF68806D),
                'Theo giá vốn từng sản phẩm'),
            _Metric(
                'Giá trị tồn kho',
                _money.format(widget.store.inventoryValue.round()),
                Icons.warehouse_outlined,
                const Color(0xFF567D92),
                '${products.length} mặt hàng'),
            _Metric(
                'Công nợ phải trả',
                _money.format(widget.store.payableTotal),
                Icons.call_made_rounded,
                const Color(0xFF9D6B63),
                'Đơn nhập chưa thanh toán đủ'),
            _Metric(
                'Cần nhập hàng',
                '${widget.store.lowStockCount}',
                Icons.warning_amber_rounded,
                const Color(0xFFC47448),
                'Sản phẩm chạm mức tồn tối thiểu'),
          ];
          final gap = 12.0;
          final width = (box.maxWidth - gap * (cols - 1)) / cols;
          return Wrap(spacing: gap, runSpacing: gap, children: [
            for (final card in cards)
              SizedBox(width: width, child: _metricCard(card))
          ]);
        }),
        const SizedBox(height: 16),
        LayoutBuilder(builder: (context, box) {
          final chart = _panel(
              'Doanh thu, giá vốn & lợi nhuận',
              'Theo thời gian đã chọn',
              SizedBox(height: 245, child: _trendChart()));
          final mix = _panel(
              'Cơ cấu giá trị tồn kho',
              '${categories.length} nhóm hàng',
              SizedBox(height: 245, child: _inventoryChart(categories)));
          if (box.maxWidth < 760)
            return Column(children: [chart, const SizedBox(height: 14), mix]);
          return Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Expanded(flex: 7, child: chart),
            const SizedBox(width: 14),
            Expanded(flex: 4, child: mix)
          ]);
        }),
        const SizedBox(height: 14),
        LayoutBuilder(builder: (context, box) {
          final productsPanel = _panel(
              'Top sản phẩm bán chạy',
              'Số lượng đã bán',
              _ranking(
                  topProducts
                      .take(5)
                      .map((e) => (e.key, _number.format(e.value), e.value))
                      .toList(),
                  const Color(0xFF7955C8)));
          final customersPanel = _panel(
              'Top khách hàng',
              'Theo doanh thu',
              _ranking(
                  topCustomers
                      .take(5)
                      .map((e) =>
                          (e.key, _money.format(e.value), e.value.toDouble()))
                      .toList(),
                  _green));
          final warningPanel = _panel(
              'Cảnh báo tồn kho',
              '${warnings.length} sản phẩm cần chú ý',
              _warningList(warnings.take(5).toList()));
          if (box.maxWidth < 900)
            return Column(children: [
              productsPanel,
              const SizedBox(height: 14),
              customersPanel,
              const SizedBox(height: 14),
              warningPanel
            ]);
          return Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Expanded(child: productsPanel),
            const SizedBox(width: 14),
            Expanded(child: customersPanel),
            const SizedBox(width: 14),
            Expanded(child: warningPanel)
          ]);
        }),
        const SizedBox(height: 14),
        _panel('Hoạt động gần đây', 'Đơn bán và nhập kho mới nhất',
            _recentActivity()),
      ]),
    );
  }

  Widget _exportButton() => OutlinedButton.icon(
      onPressed: () => CsvExport.copyToClipboard(context,
          label: 'Báo cáo bán hàng',
          headers: const [
            'Mã đơn',
            'Ngày',
            'Khách hàng',
            'Doanh thu',
            'Đã thanh toán',
            'Lợi nhuận gộp'
          ],
          rows: _sales
              .map((o) => [
                    o.code,
                    DateFormat('dd/MM/yyyy').format(o.createdAt),
                    o.partyName,
                    o.total,
                    o.paid,
                    o.total - o.lines.fold(0, (s, l) => s + l.costAmount)
                  ])
              .toList()),
      icon: const Icon(Icons.download_outlined, size: 17),
      label: const Text('Xuất CSV'),
      style: OutlinedButton.styleFrom(
          foregroundColor: _ink,
          side: const BorderSide(color: Color(0xFFE2E6E1)),
          shape:
              RoundedRectangleBorder(borderRadius: BorderRadius.circular(10))));

  Widget _metricCard(_Metric metric) => Container(
      padding: const EdgeInsets.all(16),
      decoration: _decoration(),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          Expanded(
              child: Text(metric.label,
                  style: const TextStyle(
                      color: _muted,
                      fontSize: 12,
                      fontWeight: FontWeight.w600))),
          Container(
              width: 32,
              height: 32,
              decoration: BoxDecoration(
                  color: metric.color.withOpacity(.10),
                  borderRadius: BorderRadius.circular(10)),
              child: Icon(metric.icon, size: 17, color: metric.color))
        ]),
        const SizedBox(height: 13),
        FittedBox(
            alignment: Alignment.centerLeft,
            fit: BoxFit.scaleDown,
            child: Text(metric.value,
                style: const TextStyle(
                    fontSize: 21,
                    fontWeight: FontWeight.w800,
                    color: _ink,
                    letterSpacing: -.5))),
        const SizedBox(height: 5),
        Text(metric.detail,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: const TextStyle(color: _muted, fontSize: 10))
      ]));

  Widget _panel(String title, String subtitle, Widget child) => Container(
      width: double.infinity,
      padding: const EdgeInsets.all(18),
      decoration: _decoration(),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(title,
            style: const TextStyle(
                fontWeight: FontWeight.w700, fontSize: 14, color: _ink)),
        const SizedBox(height: 4),
        Text(subtitle, style: const TextStyle(color: _muted, fontSize: 11)),
        const SizedBox(height: 17),
        child
      ]));

  Widget _trendChart() {
    final buckets = _chartBuckets();
    if (_sales.isEmpty)
      return _empty('Chưa có dữ liệu bán hàng trong khoảng này.');
    final maxY = buckets
        .map((e) => math.max(e.revenue, math.max(e.cost, e.profit)))
        .fold<double>(0, (a, b) => math.max(a, b).toDouble());
    final step = maxY <= 0 ? 1.0 : maxY / 4;
    return BarChart(BarChartData(
        maxY: maxY <= 0 ? 1 : maxY * 1.2,
        barTouchData: BarTouchData(enabled: true),
        gridData: FlGridData(
            show: true,
            drawVerticalLine: false,
            getDrawingHorizontalLine: (_) =>
                const FlLine(color: Color(0xFFEFF1ED), strokeWidth: 1)),
        borderData: FlBorderData(show: false),
        titlesData: FlTitlesData(
          topTitles:
              const AxisTitles(sideTitles: SideTitles(showTitles: false)),
          rightTitles:
              const AxisTitles(sideTitles: SideTitles(showTitles: false)),
          leftTitles: AxisTitles(
              sideTitles: SideTitles(
                  showTitles: true,
                  reservedSize: 46,
                  interval: step,
                  getTitlesWidget: (v, _) => Text(_axisMoney(v),
                      style: const TextStyle(fontSize: 9, color: _muted)))),
          bottomTitles: AxisTitles(
              sideTitles: SideTitles(
                  showTitles: true,
                  reservedSize: 28,
                  getTitlesWidget: (v, _) {
                    final i = v.toInt();
                    if (i < 0 || i >= buckets.length)
                      return const SizedBox.shrink();
                    return Padding(
                        padding: const EdgeInsets.only(top: 7),
                        child: Text(buckets[i].label,
                            style:
                                const TextStyle(fontSize: 9, color: _muted)));
                  })),
        ),
        barGroups: [
          for (var i = 0; i < buckets.length; i++)
            BarChartGroupData(x: i, barsSpace: 3, barRods: [
              BarChartRodData(
                  toY: buckets[i].revenue.toDouble(),
                  color: _purple,
                  width: 7,
                  borderRadius: BorderRadius.circular(3)),
              BarChartRodData(
                  toY: buckets[i].cost.toDouble(),
                  color: const Color(0xFF9BC9AC),
                  width: 7,
                  borderRadius: BorderRadius.circular(3)),
              BarChartRodData(
                  toY: buckets[i].profit.toDouble(),
                  color: const Color(0xFFE9B36C),
                  width: 7,
                  borderRadius: BorderRadius.circular(3))
            ])
        ],
        groupsSpace: 14));
  }

  List<_Bucket> _chartBuckets() {
    final range = _range;
    final days = range.end.difference(range.start).inDays + 1;
    final months = _period == 'Năm nay' || days > 180;
    final weekly = !months && days > 10;
    final count = months
        ? 12
        : weekly
            ? (days + 6) ~/ 7
            : days;
    final start = months
        ? DateTime(range.start.year, 1)
        : DateTime(range.start.year, range.start.month, range.start.day);
    final buckets = List.generate(count, (i) {
      final date = months
          ? DateTime(start.year, i + 1)
          : start.add(Duration(days: i * (weekly ? 7 : 1)));
      return _Bucket(
          months
              ? 'T${date.month}'
              : weekly
                  ? '${DateFormat('dd/MM').format(date)}+'
                  : const [
                      'CN',
                      'T2',
                      'T3',
                      'T4',
                      'T5',
                      'T6',
                      'T7'
                    ][date.weekday % 7],
          date);
    });
    for (final sale in _sales) {
      final daysFromStart = DateTime(
        sale.createdAt.year,
        sale.createdAt.month,
        sale.createdAt.day,
      ).difference(start).inDays;
      final i = months
          ? sale.createdAt.month - 1
          : weekly
              ? daysFromStart ~/ 7
              : daysFromStart;
      if (i >= 0 && i < buckets.length) {
        buckets[i].revenue += sale.total.toDouble();
        buckets[i].cost +=
            sale.lines.fold<int>(0, (s, l) => s + l.costAmount).toDouble();
        buckets[i].profit +=
            (sale.total - sale.lines.fold<int>(0, (s, l) => s + l.costAmount))
                .toDouble();
      }
    }
    return buckets;
  }

  String _axisMoney(double value) => value >= 1000000
      ? '${(value / 1000000).toStringAsFixed(0)}tr'
      : '${(value / 1000).toStringAsFixed(0)}k';

  Widget _inventoryChart(List<MapEntry<String, double>> categories) {
    final total = categories.fold<double>(0, (s, e) => s + e.value);
    if (total <= 0) return _empty('Chưa có dữ liệu tồn kho.');
    const colors = [
      _purple,
      _green,
      Color(0xFFE1A34E),
      Color(0xFF4D91A7),
      Color(0xFFD87558),
      Color(0xFF8D9B73)
    ];
    return Row(children: [
      SizedBox(
          width: 118,
          height: 118,
          child: PieChart(
              PieChartData(centerSpaceRadius: 32, sectionsSpace: 3, sections: [
            for (var i = 0; i < categories.length; i++)
              PieChartSectionData(
                  value: categories[i].value,
                  color: colors[i % colors.length],
                  radius: 21,
                  showTitle: false)
          ]))),
      const SizedBox(width: 13),
      Expanded(
          child:
              Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        for (var i = 0; i < math.min(5, categories.length); i++)
          Padding(
              padding: const EdgeInsets.only(bottom: 9),
              child: Row(children: [
                Container(
                    width: 8,
                    height: 8,
                    decoration: BoxDecoration(
                        color: colors[i % colors.length],
                        shape: BoxShape.circle)),
                const SizedBox(width: 7),
                Expanded(
                    child: Text(categories[i].key,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: const TextStyle(fontSize: 10, color: _ink))),
                Text('${(categories[i].value * 100 / total).round()}%',
                    style: const TextStyle(
                        fontSize: 10, fontWeight: FontWeight.w700, color: _ink))
              ]))
      ]))
    ]);
  }

  Widget _ranking(List<(String, String, double)> rows, Color color) {
    if (rows.isEmpty) return _empty('Chưa có dữ liệu trong khoảng này.');
    final max = rows.first.$3 <= 0 ? 1.0 : rows.first.$3;
    return Column(children: [
      for (var i = 0; i < rows.length; i++)
        Padding(
            padding: const EdgeInsets.only(bottom: 12),
            child: Column(children: [
              Row(children: [
                Container(
                    width: 22,
                    height: 22,
                    alignment: Alignment.center,
                    decoration: BoxDecoration(
                        color: i == 0
                            ? color.withOpacity(.12)
                            : const Color(0xFFF3F4F2),
                        shape: BoxShape.circle),
                    child: Text('${i + 1}',
                        style: TextStyle(
                            fontSize: 10,
                            fontWeight: FontWeight.w700,
                            color: i == 0 ? color : _muted))),
                const SizedBox(width: 8),
                Expanded(
                    child: Text(rows[i].$1,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: const TextStyle(
                            fontSize: 11,
                            fontWeight: FontWeight.w600,
                            color: _ink))),
                Text(rows[i].$2,
                    style: const TextStyle(
                        fontSize: 10, fontWeight: FontWeight.w700, color: _ink))
              ]),
              const SizedBox(height: 6),
              ClipRRect(
                  borderRadius: BorderRadius.circular(5),
                  child: LinearProgressIndicator(
                      value: rows[i].$3 / max,
                      minHeight: 4,
                      color: color,
                      backgroundColor: const Color(0xFFF0F1EF)))
            ]))
    ]);
  }

  Widget _warningList(List<CommerceProduct> warnings) {
    if (warnings.isEmpty) return _empty('Tồn kho đang ở mức an toàn.');
    return Column(children: [
      for (final p in warnings)
        Padding(
            padding: const EdgeInsets.only(bottom: 12),
            child: Row(children: [
              Container(
                  width: 30,
                  height: 30,
                  alignment: Alignment.center,
                  decoration: BoxDecoration(
                      color: const Color(0xFFFFF4E9),
                      borderRadius: BorderRadius.circular(8)),
                  child: const Icon(Icons.inventory_2_outlined,
                      size: 15, color: Color(0xFFC47448))),
              const SizedBox(width: 8),
              Expanded(
                  child: Text(p.name,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(
                          fontSize: 10,
                          fontWeight: FontWeight.w600,
                          color: _ink))),
              Text('${_number.format(p.stock)} / ${_number.format(p.minimum)}',
                  style: const TextStyle(fontSize: 9, color: _muted))
            ]))
    ]);
  }

  Widget _recentActivity() {
    final orders = [...widget.store.sales, ...widget.store.purchases]
      ..sort((a, b) => b.createdAt.compareTo(a.createdAt));
    if (orders.isEmpty)
      return _empty(
          'Chưa có hoạt động. Các giao dịch mới sẽ hiển thị tại đây.');
    return Column(children: [
      for (final o in orders.take(5))
        Padding(
            padding: const EdgeInsets.only(bottom: 11),
            child: Row(children: [
              Container(
                  width: 30,
                  height: 30,
                  alignment: Alignment.center,
                  decoration: BoxDecoration(
                      color: o.kind == 'sale'
                          ? const Color(0xFFE9F4EC)
                          : const Color(0xFFF1ECFA),
                      borderRadius: BorderRadius.circular(9)),
                  child: Icon(
                      o.kind == 'sale'
                          ? Icons.north_east_rounded
                          : Icons.south_west_rounded,
                      size: 15,
                      color: o.kind == 'sale' ? _green : _purple)),
              const SizedBox(width: 10),
              Expanded(
                  child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                    Text(
                        '${o.kind == 'sale' ? 'Bán hàng' : 'Nhập hàng'} · ${o.partyName}',
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: const TextStyle(
                            fontWeight: FontWeight.w600,
                            fontSize: 11,
                            color: _ink)),
                    const SizedBox(height: 3),
                    Text(
                        '${o.code} · ${DateFormat('dd/MM/yyyy').format(o.createdAt)}',
                        style: const TextStyle(color: _muted, fontSize: 9))
                  ])),
              Text(_money.format(o.total),
                  style: const TextStyle(
                      fontWeight: FontWeight.w700, fontSize: 11, color: _ink))
            ]))
    ]);
  }

  Widget _empty(String message) => SizedBox(
      height: 190,
      child: Center(
          child: Padding(
              padding: const EdgeInsets.all(12),
              child: Text(message,
                  textAlign: TextAlign.center,
                  style: const TextStyle(color: _muted, fontSize: 11)))));
  BoxDecoration _decoration() => BoxDecoration(
          color: Colors.white,
          borderRadius: BorderRadius.circular(15),
          border: Border.all(color: const Color(0xFFE9ECE8)),
          boxShadow: const [
            BoxShadow(
                color: Color(0x080D2012), blurRadius: 15, offset: Offset(0, 4))
          ]);
}

class _Metric {
  const _Metric(this.label, this.value, this.icon, this.color, this.detail);
  final String label, value, detail;
  final IconData icon;
  final Color color;
}

class _Bucket {
  _Bucket(this.label, this.date);
  final String label;
  final DateTime date;
  double revenue = 0, cost = 0, profit = 0;
}
