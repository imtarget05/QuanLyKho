import 'dart:convert';
import 'package:excel/excel.dart' as xl;
import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../app/app_shell.dart';
import '../../core/util/error_text.dart';
import '../../data/models/dtos.dart';
import '../../data/repositories/bankops_repository.dart';

class SampleItemTemplate {
  final String sku;
  final String name;
  final String unit;
  final String category;
  final String packaging;

  const SampleItemTemplate({
    required this.sku,
    required this.name,
    required this.unit,
    required this.category,
    required this.packaging,
  });

  Map<String, dynamic> toMap() => {
        'sku': sku,
        'name': name,
        'unit': unit,
        'category': category,
        'packaging': packaging,
      };
}

const teaShopSampleItems = <SampleItemTemplate>[
  SampleItemTemplate(
    sku: 'TRA-DEN-SO9',
    name: 'Trà Đen Lộc Phát Số 9',
    unit: 'gói',
    category: 'Nhóm Trà',
    packaging: '500g/gói (Thùng 20 gói)',
  ),
  SampleItemTemplate(
    sku: 'TRA-LAI-500G',
    name: 'Trà Xanh Hoa Lài Thượng Hạng',
    unit: 'gói',
    category: 'Nhóm Trà',
    packaging: '500g/gói (Thùng 20 gói)',
  ),
  SampleItemTemplate(
    sku: 'TRA-OLONG-500G',
    name: 'Trà Ô Long Nướng Đặc Biệt',
    unit: 'gói',
    category: 'Nhóm Trà',
    packaging: '500g/gói (Thùng 20 gói)',
  ),
  SampleItemTemplate(
    sku: 'BOT-BEO-BONE',
    name: 'Bột Kem Béo B-One Thái Lan',
    unit: 'túi',
    category: 'Nhóm Bột & Sữa',
    packaging: '1kg/túi (Thùng 12 túi)',
  ),
  SampleItemTemplate(
    sku: 'SUA-TUOI-1L',
    name: 'Sữa Tươi Tiệt Trùng Barista Milk',
    unit: 'hộp',
    category: 'Nhóm Bột & Sữa',
    packaging: '1 Lít/hộp (Thùng 12 hộp)',
  ),
  SampleItemTemplate(
    sku: 'SUA-DAC-1KG',
    name: 'Sữa Đặc Ngọt Larosee',
    unit: 'túi',
    category: 'Nhóm Bột & Sữa',
    packaging: '1kg/túi (Thùng 12 túi)',
  ),
  SampleItemTemplate(
    sku: 'BOT-MATCHA-500G',
    name: 'Bột Trà Xanh Matcha Uji',
    unit: 'túi',
    category: 'Nhóm Bột & Sữa',
    packaging: '500g/túi',
  ),
  SampleItemTemplate(
    sku: 'KEM-BEOS-RICH',
    name: "Kem Béo Thực Vật Rich's Lùn",
    unit: 'hộp',
    category: 'Nhóm Bột & Sữa',
    packaging: '454ml/hộp (Thùng 24 hộp)',
  ),
  SampleItemTemplate(
    sku: 'KEM-CHEESE-ANCHOR',
    name: 'Kem Phô Mai Tươi Anchor Cream Cheese',
    unit: 'khối',
    category: 'Nhóm Bột & Sữa',
    packaging: '1kg/khối',
  ),
  SampleItemTemplate(
    sku: 'TRAN-CHAU-DEN',
    name: 'Trân Châu Đen Gia Uy',
    unit: 'gói',
    category: 'Topping',
    packaging: '1kg/gói (Thùng 20 gói)',
  ),
  SampleItemTemplate(
    sku: 'TRAN-CHAU-3Q',
    name: 'Trân Châu Trắng 3Q Sea Jelly',
    unit: 'túi',
    category: 'Topping',
    packaging: '2kg/túi (Thùng 6 túi)',
  ),
  SampleItemTemplate(
    sku: 'THACH-NHA-DAM',
    name: 'Thạch Nha Đam Giòn Aloka',
    unit: 'túi',
    category: 'Topping',
    packaging: '1kg/túi',
  ),
  SampleItemTemplate(
    sku: 'SYRUP-DAO-700ML',
    name: 'Syrup Đào Monin Chai Thủy Tinh',
    unit: 'chai',
    category: 'Syrup & Mứt',
    packaging: '700ml/chai',
  ),
  SampleItemTemplate(
    sku: 'SYRUP-VAI-700ML',
    name: 'Syrup Vải Golden Farm',
    unit: 'chai',
    category: 'Syrup & Mứt',
    packaging: '700ml/chai',
  ),
  SampleItemTemplate(
    sku: 'DUONG-NUOC-25KG',
    name: 'Đường Nước Hàn Quốc Daesang',
    unit: 'can',
    category: 'Đường & Hương liệu',
    packaging: '25kg/can',
  ),
  SampleItemTemplate(
    sku: 'LY-NHUA-500ML',
    name: 'Cốc Nhựa PP 500ml Dập Màng',
    unit: 'cây',
    category: 'Bao bì & Vật dụng',
    packaging: '50 cái/cây (Kiện 1000 cái)',
  ),
  SampleItemTemplate(
    sku: 'LY-NHUA-700ML',
    name: 'Cốc Nhựa PP 700ml Nắp Tim',
    unit: 'cây',
    category: 'Bao bì & Vật dụng',
    packaging: '50 cái/cây (Kiện 1000 cái)',
  ),
  SampleItemTemplate(
    sku: 'ONG-HUT-TRAN-CHAU',
    name: 'Ống Hút Trân Châu Bọc Màng Phi 12',
    unit: 'gói',
    category: 'Bao bì & Vật dụng',
    packaging: '100 cái/gói',
  ),
  SampleItemTemplate(
    sku: 'CUON-MANG-DAP',
    name: 'Cuộn Màng Dập Nắp Cốc Trà Sữa',
    unit: 'cuộn',
    category: 'Bao bì & Vật dụng',
    packaging: '2400 nắp/cuộn',
  ),
];

class ImportItemsDialog extends StatefulWidget {
  final List<InventoryItem> existingItems;
  final BankOpsRepository? repository;

  const ImportItemsDialog({
    super.key,
    required this.existingItems,
    this.repository,
  });

  @override
  State<ImportItemsDialog> createState() => _ImportItemsDialogState();
}

class _ImportItemsDialogState extends State<ImportItemsDialog>
    with SingleTickerProviderStateMixin {
  late TabController _tabController;
  late Set<String> _existingSkus;
  late Set<String> _selectedSampleSkus;

  final _textController = TextEditingController();
  List<Map<String, String>> _parsedCustomRows = [];
  bool _isLoading = false;
  String? _statusMessage;

  @override
  void initState() {
    super.initState();
    _tabController = TabController(length: 2, vsync: this);
    _existingSkus = widget.existingItems
        .map((i) => i.sku.trim().toUpperCase())
        .toSet();

    _selectedSampleSkus = teaShopSampleItems
        .where((item) => !_existingSkus.contains(item.sku.toUpperCase()))
        .map((item) => item.sku)
        .toSet();
  }

  @override
  void dispose() {
    _tabController.dispose();
    _textController.dispose();
    super.dispose();
  }

  String _generateSku(String name) {
    var s = name.trim().toLowerCase();
    const map = {
      'à|á|ạ|ả|ã|â|ầ|ấ|ậ|ẩ|ẫ|ă|ằ|ắ|ặ|ẳ|ẵ': 'a',
      'è|é|ẹ|ẻ|ẽ|ê|ề|ế|ệ|ể|ễ': 'e',
      'ì|í|ị|ỉ|ĩ': 'i',
      'ò|ó|ọ|ỏ|õ|ô|ồ|ố|ộ|ổ|ỗ|ơ|ờ|ớ|ợ|ở|ỡ': 'o',
      'ù|ú|ụ|ủ|ũ|ư|ừ|ứ|ự|ử|ữ': 'u',
      'ỳ|ý|ỵ|ỷ|ỹ': 'y',
      'đ': 'd',
    };
    for (final entry in map.entries) {
      s = s.replaceAll(RegExp(entry.key), entry.value);
    }
    s = s.replaceAll(RegExp(r'[^a-z0-9]+'), '-').replaceAll(RegExp(r'^-+|-+$'), '');
    if (s.isEmpty) {
      s = 'SP-${DateTime.now().millisecondsSinceEpoch % 100000}';
    }
    return s.toUpperCase();
  }

  void _parsePastedText(String raw) {
    final lines = raw.split(RegExp(r'\r?\n')).where((l) => l.trim().isNotEmpty).toList();
    if (lines.isEmpty) {
      setState(() => _parsedCustomRows = []);
      return;
    }

    final rows = <Map<String, String>>[];
    for (var i = 0; i < lines.length; i++) {
      final line = lines[i].trim();
      // Support comma, semicolon or tab delimiter
      List<String> parts;
      if (line.contains('\t')) {
        parts = line.split('\t');
      } else if (line.contains(';')) {
        parts = line.split(';');
      } else if (line.contains(',')) {
        parts = line.split(',');
      } else {
        parts = [line];
      }

      if (parts.isEmpty) continue;

      // Skip header row if detected (e.g. "SKU, Tên mặt hàng, ...")
      final firstCol = parts[0].trim().toLowerCase();
      if (i == 0 &&
          parts.length > 1 &&
          (firstCol == 'sku' ||
              firstCol == 'mã' ||
              firstCol == 'mã sku' ||
              firstCol == 'mã hàng' ||
              firstCol == 'code')) {
        continue;
      }

      String sku;
      String name;
      String unit = 'gói';
      String category = 'Nguyên liệu';
      String packaging = '';

      if (parts.length == 1) {
        // Single item line (e.g. "Trà đào" or "TRA-DAO-500G")
        final candidate = parts[0].trim();
        final isLikelySku = RegExp(r'^[A-Z0-9_\-]+$').hasMatch(candidate);
        if (isLikelySku) {
          sku = candidate.toUpperCase();
          name = candidate;
        } else {
          name = candidate;
          sku = _generateSku(candidate);
        }
      } else if (parts.length == 2) {
        final p0 = parts[0].trim();
        final p1 = parts[1].trim();
        final p0IsSku = RegExp(r'^[A-Z0-9_\-]+$').hasMatch(p0);
        if (p0IsSku) {
          sku = p0.toUpperCase();
          name = p1;
        } else {
          // e.g. "Trà đào, gói" or "Trà đào, Topping"
          name = p0;
          sku = _generateSku(p0);
          unit = p1.isNotEmpty ? p1 : 'gói';
        }
      } else {
        sku = parts[0].trim().toUpperCase();
        name = parts[1].trim();
        unit = parts.length > 2 && parts[2].trim().isNotEmpty ? parts[2].trim() : 'gói';
        category = parts.length > 3 && parts[3].trim().isNotEmpty ? parts[3].trim() : 'Nguyên liệu';
        packaging = parts.length > 4 ? parts[4].trim() : '';
      }

      if (sku.isEmpty && name.isNotEmpty) {
        sku = _generateSku(name);
      }
      if (name.isEmpty && sku.isNotEmpty) {
        name = sku;
      }

      if (sku.isNotEmpty && name.isNotEmpty) {
        rows.add({
          'sku': sku,
          'name': name,
          'unit': unit,
          'category': category,
          'packaging': packaging,
        });
      }
    }

    setState(() => _parsedCustomRows = rows);
  }

  Future<void> _pickFile() async {
    try {
      final result = await FilePicker.platform.pickFiles(
        type: FileType.custom,
        allowedExtensions: ['csv', 'xlsx', 'xls', 'txt', 'tsv'],
        withData: true,
      );
      if (result != null && result.files.isNotEmpty) {
        final file = result.files.single;
        final bytes = file.bytes;
        if (bytes != null) {
          final ext = (file.extension ?? '').toLowerCase();
          if (ext == 'xlsx' || ext == 'xls') {
            final excel = xl.Excel.decodeBytes(bytes);
            final sheetName = excel.tables.keys.firstOrNull;
            if (sheetName != null) {
              final table = excel.tables[sheetName];
              if (table != null) {
                final buffer = StringBuffer();
                for (final row in table.rows) {
                  final line = row.map((cell) => cell?.value?.toString() ?? '').join(',');
                  buffer.writeln(line);
                }
                final content = buffer.toString();
                _textController.text = content;
                _parsePastedText(content);
              }
            }
          } else {
            final content = utf8.decode(bytes, allowMalformed: true);
            _textController.text = content;
            _parsePastedText(content);
          }
        }
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Lỗi đọc file: $e'), backgroundColor: Colors.red),
        );
      }
    }
  }

  Future<void> _importFromGoogleSheets() async {
    final sheetUrlCtrl = TextEditingController(
      text: 'https://docs.google.com/spreadsheets/d/1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms/edit',
    );
    final tabCtrl = TextEditingController(text: 'Sheet1');

    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Row(
          children: [
            Icon(Icons.cloud_download_outlined, color: Color(0xFF0F4C81)),
            SizedBox(width: 8),
            Text('Đồng bộ từ Google Sheets'),
          ],
        ),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text('Nhập đường dẫn Google Sheet hoặc Sheet ID:'),
            const SizedBox(height: 8),
            TextField(
              controller: sheetUrlCtrl,
              decoration: const InputDecoration(
                hintText: 'https://docs.google.com/spreadsheets/d/...',
                border: OutlineInputBorder(),
                isDense: true,
              ),
            ),
            const SizedBox(height: 12),
            TextField(
              controller: tabCtrl,
              decoration: const InputDecoration(
                labelText: 'Tên trang tính (Tab)',
                border: OutlineInputBorder(),
                isDense: true,
              ),
            ),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(ctx).pop(false),
            child: const Text('Huỷ'),
          ),
          FilledButton(
            onPressed: () => Navigator.of(ctx).pop(true),
            child: const Text('Kéo dữ liệu'),
          ),
        ],
      ),
    );

    if (confirmed != true || !mounted) return;

    final repo = RepositoryScope.maybeOf(context);
    if (repo == null) return;

    setState(() => _isLoading = true);
    try {
      final preview = await repo.fetchGoogleSheetByUrl(
        sheetUrlOrId: sheetUrlCtrl.text.trim(),
        tab: tabCtrl.text.trim().isEmpty ? 'Sheet1' : tabCtrl.text.trim(),
      );

      final buffer = StringBuffer();
      buffer.writeln('sku,name,unit,category,packaging');
      for (final r in preview.rows) {
        final d = r.data;
        final sku = d['sku'] ?? d['Mã'] ?? d['SKU'] ?? '';
        final name = d['name'] ?? d['Tên'] ?? d['Tên hàng hoá'] ?? '';
        final unit = d['unit'] ?? d['ĐVT'] ?? 'đơn vị';
        final cat = d['category'] ?? d['Nhóm'] ?? 'Nguyên liệu';
        final pack = d['packaging'] ?? d['Quy cách'] ?? '';
        buffer.writeln('$sku,$name,$unit,$cat,$pack');
      }

      final content = buffer.toString();
      _textController.text = content;
      _parsePastedText(content);
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('Đã nạp ${preview.rows.length} dòng từ Google Sheet!'),
            backgroundColor: const Color(0xFF059669),
          ),
        );
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('Lỗi nạp Google Sheet: ${friendlyError(e)}'),
            backgroundColor: Colors.red,
          ),
        );
      }
    } finally {
      if (mounted) setState(() => _isLoading = false);
    }
  }

  void _copyTemplate() {
    const template =
        'sku,name,unit,category,packaging\n'
        'TRA-DEN-LOCPHAT,Trà Đen Lộc Phát,gói,Nhóm Trà,500g/gói\n'
        'BOT-BEO-BONE,Bột Kem Béo B-One,túi,Nhóm Bột & Sữa,1kg/túi\n'
        'TRAN-CHAU-3Q,Trân Châu Trắng 3Q,túi,Topping,2kg/túi';
    Clipboard.setData(const ClipboardData(text: template));
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(
        content: Text('Đã sao chép cấu trúc file mẫu CSV vào bộ nhớ tạm!'),
        behavior: SnackBarBehavior.floating,
      ),
    );
  }

  Future<void> _submitImport(List<Map<String, dynamic>> itemsToImport) async {
    if (itemsToImport.isEmpty) return;

    setState(() {
      _isLoading = true;
      _statusMessage = 'Đang nhập ${itemsToImport.length} mặt hàng...';
    });

    try {
      final repo = widget.repository ?? RepositoryScope.of(context);
      final res = await repo.createItemsBatch(itemsToImport);

      if (mounted) {
        Navigator.of(context).pop(res);
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _isLoading = false;
          _statusMessage = null;
        });
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('Lỗi nhập mặt hàng: ${friendlyError(e)}'),
            backgroundColor: Colors.red,
          ),
        );
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;

    return Dialog(
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
      insetPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 24),
      child: Container(
        width: 720,
        constraints: const BoxConstraints(maxWidth: 720, maxHeight: 720),
        child: Column(
          children: [
            // Header
            Padding(
              padding: const EdgeInsets.fromLTRB(20, 18, 16, 12),
              child: Row(
                children: [
                  Container(
                    padding: const EdgeInsets.all(8),
                    decoration: BoxDecoration(
                      color: const Color(0xFF059669).withValues(alpha: 0.12),
                      borderRadius: BorderRadius.circular(10),
                    ),
                    child: const Icon(
                      Icons.upload_file_rounded,
                      color: Color(0xFF059669),
                      size: 22,
                    ),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        const Text(
                          'Nhập Mặt Hàng Hàng Loạt',
                          style: TextStyle(
                            fontSize: 18,
                            fontWeight: FontWeight.w800,
                          ),
                        ),
                        Text(
                          'Nạp nhanh danh mục mẫu chuẩn hoặc tải lên từ Excel/CSV',
                          style: TextStyle(
                            fontSize: 12.5,
                            color: theme.colorScheme.onSurfaceVariant,
                          ),
                        ),
                      ],
                    ),
                  ),
                  IconButton(
                    icon: const Icon(Icons.close),
                    onPressed: _isLoading ? null : () => Navigator.of(context).pop(),
                  ),
                ],
              ),
            ),
            TabBar(
              controller: _tabController,
              labelColor: const Color(0xFF059669),
              indicatorColor: const Color(0xFF059669),
              tabs: const [
                Tab(
                  icon: Icon(Icons.auto_awesome_rounded, size: 18),
                  text: 'Danh mục mẫu Trà Sữa',
                ),
                Tab(
                  icon: Icon(Icons.description_outlined, size: 18),
                  text: 'Nhập File / Dán dữ liệu',
                ),
              ],
            ),
            if (_isLoading) ...[
              if (_statusMessage != null)
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 4),
                  child: Text(
                    _statusMessage!,
                    style: const TextStyle(
                      fontSize: 12,
                      color: Color(0xFF059669),
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                ),
              LinearProgressIndicator(
                backgroundColor: const Color(0xFF059669).withValues(alpha: 0.2),
                color: const Color(0xFF059669),
              ),
            ],
            Expanded(
              child: TabBarView(
                controller: _tabController,
                children: [
                  _buildSamplePresetTab(theme, isDark),
                  _buildCustomImportTab(theme, isDark),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildSamplePresetTab(ThemeData theme, bool isDark) {
    final availableSamples = teaShopSampleItems
        .where((i) => !_existingSkus.contains(i.sku.toUpperCase()))
        .toList();

    return Column(
      children: [
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 8),
          child: SizedBox(
            width: double.infinity,
            child: Wrap(
              alignment: WrapAlignment.spaceBetween,
              crossAxisAlignment: WrapCrossAlignment.center,
              spacing: 12,
              runSpacing: 6,
              children: [
                Text(
                  'Đã chọn ${_selectedSampleSkus.length}/${availableSamples.length} món mới',
                  style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 13),
                ),
                Wrap(
                  spacing: 8,
                  children: [
                    TextButton.icon(
                      onPressed: _isLoading
                          ? null
                          : () {
                              setState(() {
                                _selectedSampleSkus = availableSamples.map((i) => i.sku).toSet();
                              });
                            },
                      icon: const Icon(Icons.select_all, size: 16),
                      label: const Text('Chọn tất cả món mới', style: TextStyle(fontSize: 12)),
                    ),
                    TextButton(
                      onPressed: _isLoading
                          ? null
                          : () {
                              setState(() {
                                _selectedSampleSkus.clear();
                              });
                            },
                      child: const Text('Bỏ chọn', style: TextStyle(fontSize: 12)),
                    ),
                  ],
                ),
              ],
            ),
          ),
        ),
        const Divider(height: 1),
        Expanded(
          child: ListView.separated(
            padding: const EdgeInsets.symmetric(vertical: 6),
            itemCount: teaShopSampleItems.length,
            separatorBuilder: (_, __) => const Divider(height: 1, indent: 64),
            itemBuilder: (context, index) {
              final item = teaShopSampleItems[index];
              final isAlreadyInStock = _existingSkus.contains(item.sku.toUpperCase());
              final isChecked = _selectedSampleSkus.contains(item.sku);

              return CheckboxListTile(
                value: isAlreadyInStock ? true : isChecked,
                enabled: !isAlreadyInStock && !_isLoading,
                activeColor: isAlreadyInStock ? Colors.grey : const Color(0xFF059669),
                title: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Flexible(
                      child: Text(
                        item.name,
                        overflow: TextOverflow.ellipsis,
                        style: TextStyle(
                          fontWeight: FontWeight.w600,
                          fontSize: 13.5,
                          color: isAlreadyInStock ? theme.disabledColor : null,
                        ),
                      ),
                    ),
                    const SizedBox(width: 8),
                    Container(
                      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 1.5),
                      decoration: BoxDecoration(
                        color: theme.colorScheme.surfaceContainerHighest,
                        borderRadius: BorderRadius.circular(4),
                      ),
                      child: Text(
                        item.category,
                        style: TextStyle(fontSize: 10.5, color: theme.colorScheme.onSurfaceVariant),
                      ),
                    ),
                  ],
                ),
                subtitle: Text(
                  'SKU: ${item.sku} • ĐVT: ${item.unit} • ${item.packaging}'
                  '${isAlreadyInStock ? " • [Đã có trong kho]" : ""}',
                  style: TextStyle(
                    fontSize: 11.5,
                    color: isAlreadyInStock ? Colors.amber[800] : theme.colorScheme.onSurfaceVariant,
                    fontWeight: isAlreadyInStock ? FontWeight.w600 : FontWeight.normal,
                  ),
                ),
                onChanged: isAlreadyInStock
                    ? null
                    : (val) {
                        setState(() {
                          if (val == true) {
                            _selectedSampleSkus.add(item.sku);
                          } else {
                            _selectedSampleSkus.remove(item.sku);
                          }
                        });
                      },
              );
            },
          ),
        ),
        const Divider(height: 1),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
          child: SizedBox(
            width: double.infinity,
            child: Wrap(
              alignment: WrapAlignment.spaceBetween,
              crossAxisAlignment: WrapCrossAlignment.center,
              spacing: 12,
              runSpacing: 8,
              children: [
                Text(
                  'Tổng: ${teaShopSampleItems.length} mặt hàng mẫu',
                  style: TextStyle(fontSize: 12, color: theme.colorScheme.onSurfaceVariant),
                ),
                FilledButton.icon(
                  key: const Key('btn-confirm-import-sample'),
                  onPressed: _isLoading || _selectedSampleSkus.isEmpty
                      ? null
                      : () {
                          final toImport = teaShopSampleItems
                              .where((i) => _selectedSampleSkus.contains(i.sku))
                              .map((i) => i.toMap())
                              .toList();
                          _submitImport(toImport);
                        },
                  icon: const Icon(Icons.check_circle_outline, size: 18),
                  label: Text('Nhập ${_selectedSampleSkus.length} mặt hàng đã chọn'),
                  style: FilledButton.styleFrom(
                    backgroundColor: const Color(0xFF059669),
                    padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 12),
                    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
                  ),
                ),
              ],
            ),
          ),
        ),
      ],
    );
  }

  Widget _buildCustomImportTab(ThemeData theme, bool isDark) {
    final validRowsCount = _parsedCustomRows
        .where((r) => !_existingSkus.contains(r['sku']?.toUpperCase()))
        .length;
    final duplicateCount = _parsedCustomRows.length - validRowsCount;

    return SingleChildScrollView(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Wrap(
            spacing: 10,
            runSpacing: 10,
            children: [
              OutlinedButton.icon(
                onPressed: _isLoading ? null : _pickFile,
                icon: const Icon(Icons.folder_open_rounded, size: 18),
                label: const Text('Chọn file Excel (.xlsx) / CSV'),
                style: OutlinedButton.styleFrom(
                  padding: const EdgeInsets.symmetric(vertical: 12, horizontal: 16),
                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
                ),
              ),
              OutlinedButton.icon(
                onPressed: _isLoading ? null : _importFromGoogleSheets,
                icon: const Icon(Icons.cloud_download_outlined, size: 18, color: Color(0xFF0F4C81)),
                label: const Text('Đồng bộ từ Google Sheets'),
                style: OutlinedButton.styleFrom(
                  padding: const EdgeInsets.symmetric(vertical: 12, horizontal: 16),
                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
                ),
              ),
              OutlinedButton.icon(
                onPressed: _copyTemplate,
                icon: const Icon(Icons.copy_rounded, size: 16),
                label: const Text('Sao chép mẫu'),
                style: OutlinedButton.styleFrom(
                  padding: const EdgeInsets.symmetric(vertical: 12, horizontal: 14),
                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
                ),
              ),
            ],
          ),
          const SizedBox(height: 14),
          TextField(
            key: const Key('input-paste-csv'),
            controller: _textController,
            maxLines: 5,
            enabled: !_isLoading,
            onChanged: _parsePastedText,
            decoration: InputDecoration(
              labelText: 'Hoặc dán trực tiếp dữ liệu CSV / Bảng tính tại đây',
              hintText: 'Mã SKU,Tên mặt hàng,Đơn vị tính,Nhóm nguyên liệu,Quy cách\n'
                  'TRA-DEN-LOCPHAT,Trà Đen Lộc Phát,gói,Nhóm Trà,500g/gói\n'
                  'BOT-BEO-BONE,Bột Kem Béo B-One,túi,Nhóm Bột & Sữa,1kg/túi',
              border: OutlineInputBorder(borderRadius: BorderRadius.circular(10)),
              helperText: 'Hỗ trợ dấu phẩy (,), dấu chấm phẩy (;), hoặc Tab copy từ Excel.',
            ),
            style: const TextStyle(fontFamily: 'monospace', fontSize: 12.5),
          ),
          const SizedBox(height: 16),
          if (_parsedCustomRows.isNotEmpty) ...[
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Text(
                  'Xem trước: ${_parsedCustomRows.length} dòng ($validRowsCount hợp lệ, $duplicateCount đã có)',
                  style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 13),
                ),
                TextButton(
                  onPressed: () {
                    _textController.clear();
                    _parsePastedText('');
                  },
                  child: const Text('Xóa dữ liệu', style: TextStyle(fontSize: 12, color: Colors.red)),
                ),
              ],
            ),
            const SizedBox(height: 8),
            Container(
              constraints: const BoxConstraints(maxHeight: 180),
              decoration: BoxDecoration(
                border: Border.all(color: theme.colorScheme.outlineVariant),
                borderRadius: BorderRadius.circular(8),
              ),
              child: ListView.separated(
                shrinkWrap: true,
                itemCount: _parsedCustomRows.length,
                separatorBuilder: (_, __) => const Divider(height: 1),
                itemBuilder: (ctx, i) {
                  final row = _parsedCustomRows[i];
                  final isDup = _existingSkus.contains(row['sku']?.toUpperCase());
                  return ListTile(
                    dense: true,
                    title: Text('${row['name']} (${row['sku']})'),
                    subtitle: Text('ĐVT: ${row['unit']} • Nhóm: ${row['category']} • ${row['packaging']}'),
                    trailing: isDup
                        ? Container(
                            padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                            decoration: BoxDecoration(
                              color: Colors.amber.withValues(alpha: 0.15),
                              borderRadius: BorderRadius.circular(4),
                            ),
                            child: const Text('Đã có', style: TextStyle(color: Colors.amber, fontSize: 11)),
                          )
                        : Container(
                            padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                            decoration: BoxDecoration(
                              color: Colors.green.withValues(alpha: 0.15),
                              borderRadius: BorderRadius.circular(4),
                            ),
                            child: const Text('Hợp lệ', style: TextStyle(color: Colors.green, fontSize: 11)),
                          ),
                  );
                },
              ),
            ),
            const SizedBox(height: 16),
            Align(
              alignment: Alignment.centerRight,
              child: FilledButton.icon(
                key: const Key('btn-confirm-import-custom'),
                onPressed: _isLoading || validRowsCount == 0
                    ? null
                    : () {
                        final toImport = _parsedCustomRows
                            .where((r) => !_existingSkus.contains(r['sku']?.toUpperCase()))
                            .map((r) => {
                                  'sku': r['sku']!,
                                  'name': r['name']!,
                                  'unit': r['unit']!,
                                  'category': r['category'],
                                  'packaging': r['packaging'],
                                })
                            .toList();
                        _submitImport(toImport);
                      },
                icon: const Icon(Icons.check, size: 18),
                label: Text('Xác nhận nhập $validRowsCount mặt hàng mới'),
                style: FilledButton.styleFrom(
                  backgroundColor: const Color(0xFF059669),
                  padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 12),
                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
                ),
              ),
            ),
          ],
        ],
      ),
    );
  }
}
