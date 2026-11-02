import 'package:flutter/material.dart';

import '../../app/app_shell.dart';
import '../../core/util/error_text.dart';
import '../../core/util/web_helpers.dart';
import '../../core/widgets/app_toast.dart';

/// Modal xuất dữ liệu ra file Excel (.xlsx), CSV hoặc đồng bộ trực tiếp ra Google Sheets.
class ExportDialog extends StatefulWidget {
  const ExportDialog({
    super.key,
    this.initialDataset = 'catalog',
    this.locationId,
    this.locationName,
  });

  final String initialDataset;
  final String? locationId;
  final String? locationName;

  static Future<void> show(
    BuildContext context, {
    String initialDataset = 'catalog',
    String? locationId,
    String? locationName,
  }) {
    return showDialog<void>(
      context: context,
      barrierDismissible: true,
      builder: (ctx) => ExportDialog(
        initialDataset: initialDataset,
        locationId: locationId,
        locationName: locationName,
      ),
    );
  }

  @override
  State<ExportDialog> createState() => _ExportDialogState();
}

class _ExportDialogState extends State<ExportDialog> {
  late String _dataset;
  String _targetFormat = 'xlsx'; // 'xlsx', 'csv', 'gsheets'

  final _sheetUrlCtrl = TextEditingController(
    text: 'https://docs.google.com/spreadsheets/d/1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms/edit',
  );
  final _sheetTabCtrl = TextEditingController(text: 'Sheet1');

  bool _busy = false;
  String? _syncSuccessUrl;

  @override
  void initState() {
    super.initState();
    _dataset = widget.initialDataset;
  }

  @override
  void dispose() {
    _sheetUrlCtrl.dispose();
    _sheetTabCtrl.dispose();
    super.dispose();
  }

  Future<void> _handleDownload() async {
    final repo = RepositoryScope.maybeOf(context);
    if (repo == null) return;

    setState(() {
      _busy = true;
      _syncSuccessUrl = null;
    });

    try {
      final params = <String, dynamic>{};
      if (widget.locationId != null) {
        params['location_id'] = widget.locationId;
      }

      final bytes = await repo.downloadExportFile(
        dataset: _dataset,
        format: _targetFormat,
        params: params,
      );

      final ext = _targetFormat == 'csv' ? 'csv' : 'xlsx';
      final timestamp = DateTime.now().millisecondsSinceEpoch;
      final filename = '${_dataset}_$timestamp.$ext';

      downloadFile(bytes, filename);

      if (mounted) {
        AppToast.success(context, 'Đã kết xuất dữ liệu và tải file $filename thành công!');
        Navigator.of(context).pop();
      }
    } catch (e) {
      if (mounted) {
        AppToast.error(context, 'Lỗi xuất file: ${friendlyError(e)}');
      }
    } finally {
      if (mounted) {
        setState(() => _busy = false);
      }
    }
  }

  Future<void> _handleSyncGoogleSheets() async {
    final repo = RepositoryScope.maybeOf(context);
    if (repo == null) return;

    final sheetUrl = _sheetUrlCtrl.text.trim();
    if (sheetUrl.isEmpty) {
      AppToast.error(context, 'Vui lòng nhập đường dẫn Google Sheet');
      return;
    }

    setState(() {
      _busy = true;
      _syncSuccessUrl = null;
    });

    try {
      final params = <String, dynamic>{};
      if (widget.locationId != null) {
        params['location_id'] = widget.locationId;
      }

      final res = await repo.syncToGoogleSheets(
        dataset: _dataset,
        sheetUrlOrId: sheetUrl,
        tab: _sheetTabCtrl.text.trim().isEmpty ? 'Sheet1' : _sheetTabCtrl.text.trim(),
        params: params,
      );

      final returnedUrl = res['sheet_url'] as String? ?? sheetUrl;
      final rowCount = res['rows_count'] ?? 0;

      if (mounted) {
        setState(() {
          _syncSuccessUrl = returnedUrl;
        });
        AppToast.success(context, 'Đã đồng bộ thành công $rowCount dòng lên Google Sheet!');
      }
    } catch (e) {
      if (mounted) {
        AppToast.error(context, 'Lỗi đồng bộ Google Sheets: ${friendlyError(e)}');
      }
    } finally {
      if (mounted) {
        setState(() => _busy = false);
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Dialog(
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 540),
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              // Header
              Row(
                children: [
                  Container(
                    padding: const EdgeInsets.all(10),
                    decoration: BoxDecoration(
                      color: theme.colorScheme.primary.withValues(alpha: 0.12),
                      borderRadius: BorderRadius.circular(10),
                    ),
                    child: Icon(
                      Icons.sync_alt_rounded,
                      color: theme.colorScheme.primary,
                      size: 24,
                    ),
                  ),
                  const SizedBox(width: 14),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          'Đồng bộ & Xuất Dữ Liệu',
                          style: theme.textTheme.titleMedium?.copyWith(
                            fontWeight: FontWeight.bold,
                          ),
                        ),
                        Text(
                          'Kết xuất ra Excel, CSV hoặc đồng bộ sang Google Sheets',
                          style: theme.textTheme.bodySmall?.copyWith(
                            color: theme.colorScheme.onSurfaceVariant,
                          ),
                        ),
                      ],
                    ),
                  ),
                  IconButton(
                    icon: const Icon(Icons.close_rounded),
                    onPressed: () => Navigator.of(context).pop(),
                  ),
                ],
              ),
              const SizedBox(height: 20),

              // Dataset selection
              Text(
                '1. Chọn dữ liệu cần xuất:',
                style: theme.textTheme.labelLarge?.copyWith(fontWeight: FontWeight.w600),
              ),
              const SizedBox(height: 8),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 12),
                decoration: BoxDecoration(
                  border: Border.all(color: theme.colorScheme.outlineVariant),
                  borderRadius: BorderRadius.circular(8),
                ),
                child: DropdownButtonHideUnderline(
                  child: DropdownButton<String>(
                    value: _dataset,
                    isExpanded: true,
                    items: const [
                      DropdownMenuItem(value: 'catalog', child: Text('Danh mục hàng hoá & nguyên liệu')),
                      DropdownMenuItem(value: 'balances', child: Text('Báo cáo tồn kho thực tế')),
                      DropdownMenuItem(value: 'movements', child: Text('Sổ biến động kho (Movements)')),
                      DropdownMenuItem(value: 'inventory_summary', child: Text('Tổng hợp Nhập - Xuất - Tồn')),
                      DropdownMenuItem(value: 'cash_journal', child: Text('Sổ quỹ & Nhật ký thu chi')),
                    ],
                    onChanged: (val) {
                      if (val != null) setState(() => _dataset = val);
                    },
                  ),
                ),
              ),
              if (widget.locationName != null) ...[
                const SizedBox(height: 6),
                Text(
                  'Kho lọc: ${widget.locationName}',
                  style: theme.textTheme.bodySmall?.copyWith(color: theme.colorScheme.primary),
                ),
              ],
              const SizedBox(height: 18),

              // Target Format
              Text(
                '2. Chọn đích đến / định dạng:',
                style: theme.textTheme.labelLarge?.copyWith(fontWeight: FontWeight.w600),
              ),
              const SizedBox(height: 8),
              SegmentedButton<String>(
                segments: const [
                  ButtonSegment(
                    value: 'xlsx',
                    label: Text('Excel (.xlsx)'),
                    icon: Icon(Icons.table_chart_outlined, size: 18),
                  ),
                  ButtonSegment(
                    value: 'csv',
                    label: Text('CSV (BOM)'),
                    icon: Icon(Icons.description_outlined, size: 18),
                  ),
                  ButtonSegment(
                    value: 'gsheets',
                    label: Text('Google Sheets'),
                    icon: Icon(Icons.cloud_upload_outlined, size: 18),
                  ),
                ],
                selected: {_targetFormat},
                onSelectionChanged: (set) {
                  setState(() {
                    _targetFormat = set.first;
                    _syncSuccessUrl = null;
                  });
                },
              ),
              const SizedBox(height: 16),

              // Google Sheets Options
              if (_targetFormat == 'gsheets') ...[
                Container(
                  padding: const EdgeInsets.all(14),
                  decoration: BoxDecoration(
                    color: theme.colorScheme.surfaceContainerHighest.withValues(alpha: 0.5),
                    borderRadius: BorderRadius.circular(10),
                    border: Border.all(color: theme.colorScheme.outlineVariant),
                  ),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        'Đường dẫn Google Sheet đích:',
                        style: theme.textTheme.bodySmall?.copyWith(fontWeight: FontWeight.w600),
                      ),
                      const SizedBox(height: 6),
                      TextField(
                        controller: _sheetUrlCtrl,
                        decoration: const InputDecoration(
                          hintText: 'https://docs.google.com/spreadsheets/d/...',
                          isDense: true,
                          border: OutlineInputBorder(),
                          prefixIcon: Icon(Icons.link_rounded, size: 20),
                        ),
                      ),
                      const SizedBox(height: 10),
                      Row(
                        children: [
                          Expanded(
                            child: TextField(
                              controller: _sheetTabCtrl,
                              decoration: const InputDecoration(
                                labelText: 'Tên tab',
                                hintText: 'Sheet1',
                                isDense: true,
                                border: OutlineInputBorder(),
                              ),
                            ),
                          ),
                        ],
                      ),
                      const SizedBox(height: 6),
                      Text(
                        'Đảm bảo Sheet đã bật quyền "Bất kỳ ai có đường link đều có thể xem/chỉnh sửa" hoặc kết nối qua Service Account.',
                        style: theme.textTheme.bodySmall?.copyWith(
                          fontSize: 11,
                          color: theme.colorScheme.onSurfaceVariant,
                        ),
                      ),
                    ],
                  ),
                ),
                if (_syncSuccessUrl != null) ...[
                  const SizedBox(height: 12),
                  Container(
                    padding: const EdgeInsets.all(12),
                    decoration: BoxDecoration(
                      color: const Color(0xFFECFDF5),
                      borderRadius: BorderRadius.circular(8),
                      border: Border.all(color: const Color(0xFF10B981)),
                    ),
                    child: Row(
                      children: [
                        const Icon(Icons.check_circle_rounded, color: Color(0xFF059669), size: 20),
                        const SizedBox(width: 8),
                        const Expanded(
                          child: Text(
                            'Đồng bộ hoàn tất! Nhấp để mở:',
                            style: TextStyle(color: Color(0xFF065F46), fontWeight: FontWeight.w600),
                          ),
                        ),
                        TextButton.icon(
                          icon: const Icon(Icons.open_in_new_rounded, size: 16),
                          label: const Text('Mở Sheet'),
                          onPressed: () => openWebUrl(_syncSuccessUrl!),
                        ),
                      ],
                    ),
                  ),
                ],
              ],

              const SizedBox(height: 24),

              // Action buttons
              Row(
                mainAxisAlignment: MainAxisAlignment.end,
                children: [
                  TextButton(
                    onPressed: _busy ? null : () => Navigator.of(context).pop(),
                    child: const Text('Đóng'),
                  ),
                  const SizedBox(width: 10),
                  if (_targetFormat == 'gsheets')
                    FilledButton.icon(
                      icon: _busy
                          ? const SizedBox(
                              width: 16,
                              height: 16,
                              child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
                            )
                          : const Icon(Icons.cloud_upload_outlined, size: 18),
                      label: Text(_busy ? 'Đang đồng bộ...' : 'Đẩy lên Google Sheet'),
                      onPressed: _busy ? null : _handleSyncGoogleSheets,
                    )
                  else
                    FilledButton.icon(
                      icon: _busy
                          ? const SizedBox(
                              width: 16,
                              height: 16,
                              child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
                            )
                          : const Icon(Icons.download_rounded, size: 18),
                      label: Text(_busy ? 'Đang kết xuất...' : 'Tải file ${_targetFormat.toUpperCase()}'),
                      onPressed: _busy ? null : _handleDownload,
                    ),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }
}
