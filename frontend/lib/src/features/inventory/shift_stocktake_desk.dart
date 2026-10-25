import 'package:flutter/material.dart';
import '../../core/i18n/app_i18n.dart';

/// Dòng đối soát cho quầy kiểm kê. Số lý thuyết luôn được tính từ luồng ca,
/// không lấy trực tiếp từ ô kiểm thực tế.
class ShiftStocktakeLine {
  const ShiftStocktakeLine({
    required this.name,
    required this.unit,
    required this.openingQty,
    required this.receivedQty,
    required this.usedQty,
    required this.countedQty,
    this.reason = '',
  });

  final String name;
  final String unit;
  final double openingQty;
  final double receivedQty;
  final double usedQty;
  final double countedQty;
  final String reason;

  double get theoreticalQty => openingQty + receivedQty - usedQty;
  double get varianceQty => countedQty - theoreticalQty;
  bool get hasVariance => varianceQty.abs() >= 0.001;
}

/// Khung thao tác nhanh cho ca làm việc tại quầy.
class ShiftStocktakeDesk extends StatefulWidget {
  const ShiftStocktakeDesk({
    super.key,
    required this.lines,
    this.onStartShiftStocktake,
    this.filterOnlyDiscrepancy = false,
  });

  final List<ShiftStocktakeLine> lines;
  final VoidCallback? onStartShiftStocktake;
  final bool filterOnlyDiscrepancy;

  @override
  State<ShiftStocktakeDesk> createState() => _ShiftStocktakeDeskState();
}

class _ShiftStocktakeDeskState extends State<ShiftStocktakeDesk> {
  var _shift = _Shift.morning;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isVi = context.isVietnamese;
    final effectiveLines = widget.filterOnlyDiscrepancy
        ? widget.lines.where((line) => line.hasVariance).toList()
        : widget.lines;
    final hasVariance = effectiveLines.any((line) => line.hasVariance);

    final deskTitle = isVi ? 'Quầy kiểm kê theo ca' : 'Shift Stocktake Desk';
    final openSessionBtn = isVi ? 'Mở phiên kiểm kê' : 'Open Stocktake Session';
    final varianceAlert = isVi
        ? 'Có chênh lệch cần đối soát trước khi chốt ca.'
        : 'Variance detected, review required before shift close.';
    final matchedAlert = isVi
        ? 'Số thực tế khớp sổ theo công thức cuối ca.'
        : 'Physical count matched book theoretical balance.';
    final formulaText = isVi
        ? 'Tồn lý thuyết = Tồn đầu + Nhập − Sử dụng. Độ lệch = Kiểm thực tế − Tồn lý thuyết.'
        : 'Theoretical = Opening + Inbound − Usage. Variance = Counted − Theoretical.';

    return Semantics(
      container: true,
      label: deskTitle,
      child: Container(
        decoration: BoxDecoration(
          color: theme.colorScheme.surface,
          borderRadius: BorderRadius.circular(16),
          border: Border.all(color: theme.colorScheme.outlineVariant),
        ),
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Wrap(
              alignment: WrapAlignment.spaceBetween,
              runSpacing: 12,
              spacing: 12,
              children: [
                Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(deskTitle,
                        style: theme.textTheme.titleMedium
                            ?.copyWith(fontWeight: FontWeight.w800)),
                    const SizedBox(height: 3),
                    Text(
                      '${_shift.title(context)} · ${_shift.hours}',
                      style: TextStyle(
                        fontSize: 12,
                        color: theme.colorScheme.onSurfaceVariant,
                      ),
                    ),
                  ],
                ),
                SizedBox(
                  height: 48,
                  child: FilledButton.icon(
                    onPressed: widget.onStartShiftStocktake,
                    icon: const Icon(Icons.playlist_add_check_outlined),
                    label: Text(openSessionBtn),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 16),
            _ShiftTabs(
              selected: _shift,
              onChanged: (value) => setState(() => _shift = value),
            ),
            const SizedBox(height: 12),
            Container(
              padding: const EdgeInsets.all(10),
              decoration: BoxDecoration(
                color: hasVariance
                    ? theme.colorScheme.errorContainer
                    : theme.colorScheme.primaryContainer,
                borderRadius: BorderRadius.circular(10),
              ),
              child: Row(
                children: [
                  Icon(
                    hasVariance
                        ? Icons.warning_amber_rounded
                        : Icons.check_circle_outline,
                    color: hasVariance
                        ? theme.colorScheme.onErrorContainer
                        : theme.colorScheme.onPrimaryContainer,
                  ),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Text(
                      hasVariance ? varianceAlert : matchedAlert,
                      style: TextStyle(
                        fontSize: 12,
                        fontWeight: FontWeight.w700,
                        color: hasVariance
                            ? theme.colorScheme.onErrorContainer
                            : theme.colorScheme.onPrimaryContainer,
                      ),
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 12),
            Text(
              formulaText,
              style: TextStyle(
                fontSize: 12,
                color: theme.colorScheme.onSurfaceVariant,
              ),
            ),
            const SizedBox(height: 12),
            if (widget.filterOnlyDiscrepancy && effectiveLines.isEmpty)
              Padding(
                padding: const EdgeInsets.all(24),
                child: Center(
                  child: Text(
                    isVi
                        ? 'Không có mặt hàng nào bị lệch trong ca trực này.'
                        : 'No ingredient variances found in this shift.',
                    style: TextStyle(color: theme.colorScheme.onSurfaceVariant),
                  ),
                ),
              )
            else
              _ReconciliationTable(lines: effectiveLines),
          ],
        ),
      ),
    );
  }
}

class _ShiftTabs extends StatelessWidget {
  const _ShiftTabs({required this.selected, required this.onChanged});

  final _Shift selected;
  final ValueChanged<_Shift> onChanged;

  @override
  Widget build(BuildContext context) => Wrap(
        spacing: 8,
        runSpacing: 8,
        children: _Shift.values
            .map(
              (shift) => ChoiceChip(
                label: Text('${shift.title(context)}\n${shift.hours}',
                    textAlign: TextAlign.center),
                selected: selected == shift,
                onSelected: (_) => onChanged(shift),
                showCheckmark: false,
                labelStyle: const TextStyle(fontWeight: FontWeight.w700),
              ),
            )
            .toList(),
      );
}

class _ReconciliationTable extends StatelessWidget {
  const _ReconciliationTable({required this.lines});

  final List<ShiftStocktakeLine> lines;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isVi = context.isVietnamese;
    const headerStyle = TextStyle(fontWeight: FontWeight.w800);
    return LayoutBuilder(
      builder: (context, constraints) {
        if (constraints.maxWidth < 640) {
          return Column(
            children: lines.map((line) => _buildCard(context, line)).toList(),
          );
        }
        return SingleChildScrollView(
          scrollDirection: Axis.horizontal,
          child: ConstrainedBox(
            constraints: BoxConstraints(
                minWidth:
                    constraints.maxWidth < 1080 ? 1080 : constraints.maxWidth),
            child: DataTable(
              headingRowColor: WidgetStatePropertyAll(
                  theme.colorScheme.surfaceContainerHighest),
              columns: [
                DataColumn(label: Text(isVi ? 'Nguyên liệu' : 'Ingredient', style: headerStyle)),
                DataColumn(label: Text(isVi ? 'ĐVT' : 'Unit', style: headerStyle)),
                DataColumn(
                    label: Text(isVi ? 'Tồn đầu' : 'Opening', style: headerStyle), numeric: true),
                DataColumn(
                    label: Text(isVi ? 'Nhập' : 'Inbound', style: headerStyle), numeric: true),
                DataColumn(
                    label: Text(isVi ? 'Sử dụng' : 'Usage', style: headerStyle), numeric: true),
                DataColumn(
                    label: Text(isVi ? 'Tồn lý thuyết' : 'Theoretical', style: headerStyle),
                    numeric: true),
                DataColumn(
                    label: Text(isVi ? 'Kiểm thực tế' : 'Physical Count', style: headerStyle),
                    numeric: true),
                DataColumn(
                    label: Text(isVi ? 'Độ lệch' : 'Variance', style: headerStyle), numeric: true),
                DataColumn(label: Text(isVi ? 'Trạng thái' : 'Status', style: headerStyle)),
                DataColumn(label: Text(isVi ? 'Lý do' : 'Reason', style: headerStyle)),
              ],
              rows: lines.map((line) => _row(context, line)).toList(),
            ),
          ),
        );
      },
    );
  }

  Widget _buildCard(BuildContext context, ShiftStocktakeLine line) {
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;
    final isVi = context.isVietnamese;
    final color = line.hasVariance
        ? Theme.of(context).colorScheme.error
        : const Color(0xFF15803D);
    final status = line.hasVariance
        ? (isVi ? 'Cần đối soát' : 'Review')
        : (isVi ? 'Khớp' : 'Matched');
    final diff = line.varianceQty;
    final diffPrefix = isVi ? 'Lệch' : 'Var';
    final diffText = '${diff > 0 ? '+' : ''}${_qty(diff)}';

    return Container(
      margin: const EdgeInsets.only(bottom: 10),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: isDark ? const Color(0xFF1E293B) : const Color(0xFFF8FAFC),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(
          color: line.hasVariance
              ? const Color(0xFFEF4444).withValues(alpha: 0.3)
              : theme.colorScheme.outlineVariant.withValues(alpha: 0.5),
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
                  line.name,
                  style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 14),
                  overflow: TextOverflow.ellipsis,
                ),
              ),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                decoration: BoxDecoration(
                  color: color.withValues(alpha: 0.12),
                  borderRadius: BorderRadius.circular(6),
                ),
                child: Text(
                  '$status ($diffPrefix $diffText ${line.unit})',
                  style: TextStyle(
                    color: color,
                    fontWeight: FontWeight.w800,
                    fontSize: 11,
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 8),
          Row(
            children: [
              Expanded(
                child: _buildMetricTile(
                  context,
                  isVi ? 'Tồn đầu' : 'Opening',
                  '${_qty(line.openingQty)} ${line.unit}',
                ),
              ),
              const SizedBox(width: 6),
              Expanded(
                child: _buildMetricTile(
                  context,
                  isVi ? 'Nhập/Dùng' : 'In/Out',
                  '+${_qty(line.receivedQty)}/-${_qty(line.usedQty)}',
                ),
              ),
              const SizedBox(width: 6),
              Expanded(
                child: _buildMetricTile(
                  context,
                  isVi ? 'Tồn lý thuyết' : 'Theoretical',
                  '${_qty(line.theoreticalQty)} ${line.unit}',
                  isHighlight: true,
                ),
              ),
              const SizedBox(width: 6),
              Expanded(
                child: _buildMetricTile(
                  context,
                  isVi ? 'Kiểm thực tế' : 'Counted',
                  '${_qty(line.countedQty)} ${line.unit}',
                  isHighlight: true,
                  color: color,
                ),
              ),
            ],
          ),
          if (line.reason.isNotEmpty) ...[
            const SizedBox(height: 6),
            Text(
              '${isVi ? "Lý do" : "Reason"}: ${line.reason}',
              style: TextStyle(
                fontSize: 11,
                fontStyle: FontStyle.italic,
                color: theme.colorScheme.onSurfaceVariant,
              ),
            ),
          ],
        ],
      ),
    );
  }

  Widget _buildMetricTile(BuildContext context, String label, String value,
      {bool isHighlight = false, Color? color}) {
    final theme = Theme.of(context);
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 5),
      decoration: BoxDecoration(
        color: theme.colorScheme.surface,
        borderRadius: BorderRadius.circular(6),
        border: Border.all(
          color: theme.colorScheme.outlineVariant.withValues(alpha: 0.4),
        ),
      ),
      child: Column(
        children: [
          Text(
            label,
            style: TextStyle(
              fontSize: 9.5,
              color: theme.colorScheme.onSurfaceVariant,
            ),
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
          ),
          const SizedBox(height: 2),
          Text(
            value,
            style: TextStyle(
              fontSize: 11,
              fontWeight: isHighlight ? FontWeight.w800 : FontWeight.w600,
              color: color,
            ),
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
          ),
        ],
      ),
    );
  }

  DataRow _row(BuildContext context, ShiftStocktakeLine line) {
    final isVi = context.isVietnamese;
    final color = line.hasVariance
        ? Theme.of(context).colorScheme.error
        : const Color(0xFF15803D);
    final status = line.hasVariance
        ? (isVi ? 'Cần đối soát' : 'Review')
        : (isVi ? 'Khớp' : 'Matched');
    final diff = line.varianceQty;
    final diffPrefix = isVi ? 'Lệch' : 'Var';
    final diffText = '${diff > 0 ? '+' : ''}${_qty(diff)}';
    return DataRow(cells: [
      DataCell(
          Text(line.name, style: const TextStyle(fontWeight: FontWeight.w700))),
      DataCell(Text(line.unit)),
      DataCell(Text(_qty(line.openingQty))),
      DataCell(Text(_qty(line.receivedQty))),
      DataCell(Text(_qty(line.usedQty))),
      DataCell(Text(_qty(line.theoreticalQty))),
      DataCell(Text(_qty(line.countedQty))),
      DataCell(Text('$diffPrefix $diffText',
          style: TextStyle(color: color, fontWeight: FontWeight.w800))),
      DataCell(Text(status,
          style: TextStyle(color: color, fontWeight: FontWeight.w800))),
      DataCell(Text(line.reason.isEmpty ? '—' : line.reason)),
    ]);
  }

  String _qty(double value) => value == value.roundToDouble()
      ? value.toInt().toString()
      : value.toStringAsFixed(2);
}

enum _Shift {
  morning('07:30 – 15:00'),
  afternoon('15:00 – 23:00'),
  split('07:30 – 18:00');

  const _Shift(this.hours);
  final String hours;

  String title(BuildContext context) {
    switch (this) {
      case _Shift.morning:
        return context.isVietnamese ? 'Ca Sáng' : 'Morning Shift';
      case _Shift.afternoon:
        return context.isVietnamese ? 'Ca Chiều' : 'Afternoon Shift';
      case _Shift.split:
        return context.isVietnamese ? 'Ca Lỡ' : 'Split Shift';
    }
  }
}
