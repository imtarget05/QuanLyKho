import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart' show rootBundle;
import 'package:pdf/pdf.dart';
import 'package:pdf/widgets.dart' as pw;
import 'package:shared_preferences/shared_preferences.dart';

import '../../app/app_shell.dart';
import '../../core/i18n/app_i18n.dart';
import '../../core/offline/offline_ui.dart';
import '../../core/offline/stocktake_outbox.dart';
import '../../core/sync/data_sync_controller.dart';
import '../../core/util/formatting.dart';
import '../../core/util/role_visibility.dart';
import '../../core/util/report_share.dart';
import '../../core/util/error_text.dart';
import '../../core/widgets/app_toast.dart';
import '../../core/widgets/state_views.dart';
import '../../data/models/dtos.dart';
import '../../data/repositories/bankops_repository.dart';
import 'shift_stocktake_desk.dart';
import 'import_items_dialog.dart';

/// Chế độ hiển thị của màn hình Kho và Ca làm việc.
enum InventoryTabMode {
  all,
  stock,
  shiftWork,
}

/// Màn quản lý nguyên vật liệu và ca làm việc cho quán trà sữa.
class InventoryScreen extends StatefulWidget {
  const InventoryScreen({
    super.key,
    this.mode = InventoryTabMode.all,
    this.onNavigate,
    this.onCreateStockRequest,
    this.initialCategory,
    this.initialStockFilter,
    this.initialViewMode,
    this.initialLocationId,
    this.initialSearchQuery,
    this.initialItemId,
  });

  final InventoryTabMode mode;
  final ValueChanged<int>? onNavigate;
  final void Function({String? locationId, String? itemId, double? suggestedQty})? onCreateStockRequest;
  final String? initialCategory;
  final String? initialStockFilter;
  final String? initialViewMode;
  final String? initialLocationId;
  final String? initialSearchQuery;
  final String? initialItemId;

  @override
  State<InventoryScreen> createState() => _InventoryScreenState();
}

class _InventoryScreenState extends State<InventoryScreen> {
  Future<_InventoryData>? _future;
  DataSyncController? _syncController;
  bool _isSelectionMode = false;
  final Set<String> _selectedItemIds = {};
  String _searchQuery = '';
  String _selectedCategory = 'Tất cả';
  String _stockFilter = 'all';
  String _stocktakeStatusFilter = 'all';
  String _sheetViewMode = 'sheet';
  bool _revealPrices = true;
  bool _alertsExpanded = true;
  String? _alertLocationFilter;
  SharedPreferences? _prefs;

  @override
  void initState() {
    super.initState();
    SharedPreferences.getInstance().then((p) {
      if (mounted) setState(() => _prefs = p);
    }).catchError((_) {});
    if (widget.initialCategory != null) {
      _selectedCategory = widget.initialCategory!;
    }
    if (widget.initialStockFilter != null) {
      _stockFilter = widget.initialStockFilter!;
    }
    if (widget.initialViewMode != null) {
      _sheetViewMode = widget.initialViewMode!;
    }
    if (widget.initialSearchQuery != null && widget.initialSearchQuery!.isNotEmpty) {
      _searchQuery = widget.initialSearchQuery!;
    }
  }

  @override
  void didUpdateWidget(InventoryScreen oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.initialCategory != null &&
        widget.initialCategory != oldWidget.initialCategory) {
      _selectedCategory = widget.initialCategory!;
    }
    if (widget.initialStockFilter != null &&
        widget.initialStockFilter != oldWidget.initialStockFilter) {
      _stockFilter = widget.initialStockFilter!;
    }
    if (widget.initialViewMode != null &&
        widget.initialViewMode != oldWidget.initialViewMode) {
      _sheetViewMode = widget.initialViewMode!;
    }
    if (widget.initialSearchQuery != null &&
        widget.initialSearchQuery != oldWidget.initialSearchQuery) {
      _searchQuery = widget.initialSearchQuery!;
    }
  }

  double _stockForItem(String itemId, List<StockBalance> balances) {
    return balances
        .where((b) => b.itemId == itemId)
        .fold<double>(0.0, (sum, b) => sum + (double.tryParse(b.quantity) ?? 0.0));
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
    final last = _syncController?.lastEvent;
    if (last == null ||
        last.topic == SyncTopic.inventory ||
        last.topic == SyncTopic.stocktake ||
        last.topic == SyncTopic.requests ||
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
    setState(() {
      _future = _load(repo);
    });
  }

  Future<bool> _queueStocktake(BankOpsRepository repo, String kind,
      Map<String, dynamic> payload, String idempotencyKey) async {
    final user = SessionScope.maybeOf(context)?.user;
    if (user == null) throw StateError('Cần đăng nhập để đồng bộ kiểm kê');
    // AppShell mirrors the signed-in session into OfflineHub on login. When
    // this screen runs without the shell (deep link, widget tests), adopt the
    // session identity on first use; a hub already bound to a DIFFERENT user
    // still throws, so a stale screen can never queue under someone else's
    // outbox identity.
    if (OfflineHub.instance.currentUserId == null) {
      OfflineHub.instance.currentUserId = user.id;
      OfflineHub.instance.currentBranch = user.branch;
    }
    if (OfflineHub.instance.currentUserId != user.id ||
        OfflineHub.instance.currentBranch != user.branch) {
      throw StateError('Phiên đăng nhập đã thay đổi; mở lại ca kiểm kê');
    }
    await StocktakeOutbox.shared.bindIdentity(user.id, user.branch);
    if (!mounted || OfflineHub.instance.currentUserId != user.id ||
        OfflineHub.instance.currentBranch != user.branch) {
      throw StateError('Phiên đăng nhập đã thay đổi; mở lại ca kiểm kê');
    }
    await StocktakeOutbox.shared.enqueue(kind, payload, idempotencyKey);
    return StocktakeOutbox.shared.tryFlush(
      repository: repo, currentUserId: user.id, currentBranch: user.branch,
    );
  }

  String _slugSku(String name) {
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

  Future<void> _showCreateItemDialog() async {
    final skuCtrl = TextEditingController();
    final nameCtrl = TextEditingController();
    final unitCtrl = TextEditingController(text: 'gói');
    final categoryCtrl = TextEditingController(text: 'Nhóm Trà');
    final packagingCtrl = TextEditingController();
    final costPriceCtrl = TextEditingController();
    final sellingPriceCtrl = TextEditingController();
    final minStockCtrl = TextEditingController(text: '10');
    final sessionUser = SessionScope.maybeOf(context)?.user;
    final isAdmin = RoleVisibility.isAdminUser(sessionUser);

    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, setDlgState) => AlertDialog(
          shape:
              RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
          title: const Row(
            children: [
              Icon(Icons.inventory_2_outlined, color: Color(0xFF2563EB)),
              SizedBox(width: 8),
              Text('Thêm mặt hàng mới',
                  style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
            ],
          ),
          content: SingleChildScrollView(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                TextField(
                  controller: skuCtrl,
                  decoration: const InputDecoration(
                    labelText: 'Mã SKU (tự sinh nếu để trống)',
                    hintText: 'Ví dụ: TRA-OLONG-500G',
                    border: OutlineInputBorder(),
                  ),
                ),
                const SizedBox(height: 14),
                TextField(
                  controller: nameCtrl,
                  decoration: const InputDecoration(
                    labelText: 'Tên nguyên vật liệu / Sản phẩm *',
                    hintText: 'Ví dụ: Trà Ô Long Nướng Đặc Biệt',
                    border: OutlineInputBorder(),
                  ),
                ),
                const SizedBox(height: 14),
                Row(
                  children: [
                    Expanded(
                      child: TextField(
                        controller: unitCtrl,
                        decoration: const InputDecoration(
                          labelText: 'Đơn Vị Tính *',
                          hintText: 'gói / hộp / kg',
                          border: OutlineInputBorder(),
                        ),
                      ),
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: TextField(
                        controller: minStockCtrl,
                        keyboardType: TextInputType.number,
                        decoration: const InputDecoration(
                          labelText: 'Định mức tồn Min',
                          hintText: 'VD: 10',
                          border: OutlineInputBorder(),
                        ),
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 14),
                Row(
                  children: [
                    Expanded(
                      child: TextField(
                        controller: categoryCtrl,
                        decoration: const InputDecoration(
                          labelText: 'Nhóm sản phẩm',
                          hintText: 'Nhóm Trà / Topping...',
                          border: OutlineInputBorder(),
                        ),
                      ),
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: TextField(
                        controller: packagingCtrl,
                        decoration: const InputDecoration(
                          labelText: 'Quy cách đóng gói',
                          hintText: '500g/gói',
                          border: OutlineInputBorder(),
                        ),
                      ),
                    ),
                  ],
                ),
                if (isAdmin) ...[
                  const SizedBox(height: 14),
                  Row(
                    children: [
                      Expanded(
                        child: TextField(
                          controller: costPriceCtrl,
                          keyboardType: TextInputType.number,
                          decoration: const InputDecoration(
                            labelText: 'Giá vốn (Admin)',
                            hintText: 'VD: 85000',
                            suffixText: 'đ',
                            border: OutlineInputBorder(),
                          ),
                        ),
                      ),
                      const SizedBox(width: 12),
                      Expanded(
                        child: TextField(
                          controller: sellingPriceCtrl,
                          keyboardType: TextInputType.number,
                          decoration: const InputDecoration(
                            labelText: 'Giá bán (Admin)',
                            hintText: 'VD: 125000',
                            suffixText: 'đ',
                            border: OutlineInputBorder(),
                          ),
                        ),
                      ),
                    ],
                  ),
                ],
              ],
            ),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.of(ctx).pop(false),
              child: const Text('Hủy'),
            ),
            FilledButton(
              onPressed: () {
                final name = nameCtrl.text.trim();
                if (name.isEmpty) return;
                if (skuCtrl.text.trim().isEmpty) {
                  skuCtrl.text = _slugSku(name);
                }
                Navigator.of(ctx).pop(true);
              },
              child: const Text('Thêm mới'),
            ),
          ],
        ),
      ),
    );

    if (ok == true && mounted) {
      final finalName = nameCtrl.text.trim();
      final finalSku = (skuCtrl.text.trim().isEmpty ? _slugSku(finalName) : skuCtrl.text.trim()).toUpperCase();
      try {
        final repo = RepositoryScope.of(context);
        await repo.createItem(
          sku: finalSku,
          name: finalName,
          unit: unitCtrl.text.trim().isEmpty ? 'gói' : unitCtrl.text.trim(),
          trackedSerial: false,
          category: categoryCtrl.text.trim().isEmpty ? 'Nguyên liệu' : categoryCtrl.text.trim(),
          packaging: packagingCtrl.text.trim().isNotEmpty ? packagingCtrl.text.trim() : null,
          costPrice: isAdmin ? double.tryParse(costPriceCtrl.text.replaceAll(',', '').trim()) : null,
          sellingPrice: isAdmin ? double.tryParse(sellingPriceCtrl.text.replaceAll(',', '').trim()) : null,
          minStock: double.tryParse(minStockCtrl.text.replaceAll(',', '').trim()),
        );
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
              content: Text(
                  'Đã thêm mặt hàng "$finalName" ($finalSku) thành công!'),
              behavior: SnackBarBehavior.floating,
            ),
          );
          _refresh();
        }
      } catch (e) {
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
                content: Text('Lỗi: ${friendlyError(e)}'),
                backgroundColor: Colors.red),
          );
        }
      }
    }
  }

  Future<void> _showImportItemsDialog(List<InventoryItem> existingItems) async {
    final repo = RepositoryScope.of(context);
    final result = await showDialog<BatchItemImportResult>(
      context: context,
      builder: (ctx) => RepositoryScope(
        repository: repo,
        child: ImportItemsDialog(
          existingItems: existingItems,
          repository: repo,
        ),
      ),
    );

    if (result != null && mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            'Đã nhập thành công ${result.createdCount} mặt hàng vào kho!'
            '${result.skippedCount > 0 ? " (Bỏ qua ${result.skippedCount} món đã có)" : ""}',
          ),
          backgroundColor: const Color(0xFF059669),
          behavior: SnackBarBehavior.floating,
        ),
      );
      _refresh();
    }
  }

  Future<void> _showEditItemDialog(InventoryItem item) async {
    final nameCtrl = TextEditingController(text: item.name);
    final unitCtrl = TextEditingController(text: item.unit);
    final categoryCtrl = TextEditingController(text: item.category ?? '');
    final packagingCtrl = TextEditingController(text: item.packaging ?? '');
    final costPriceCtrl = TextEditingController(
      text: item.costPrice != null ? item.costPrice!.toStringAsFixed(0) : '',
    );
    final sellingPriceCtrl = TextEditingController(
      text: item.sellingPrice != null ? item.sellingPrice!.toStringAsFixed(0) : '',
    );
    final minStockCtrl = TextEditingController(
      text: item.minStock != null ? item.minStock!.toStringAsFixed(0) : '',
    );
    final sessionUser = SessionScope.maybeOf(context)?.user;
    final isAdmin = RoleVisibility.isAdminUser(sessionUser);

    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
        title: Row(
          children: [
            const Icon(Icons.edit_outlined, color: Color(0xFF2563EB)),
            const SizedBox(width: 8),
            Text('Sửa: ${item.sku}',
                style:
                    const TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
          ],
        ),
        content: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              TextField(
                controller: nameCtrl,
                decoration: const InputDecoration(
                  labelText: 'Tên nguyên vật liệu / Sản phẩm *',
                  border: OutlineInputBorder(),
                ),
              ),
              const SizedBox(height: 14),
              Row(
                children: [
                  Expanded(
                    child: TextField(
                      controller: unitCtrl,
                      decoration: const InputDecoration(
                        labelText: 'Đơn Vị Tính',
                        border: OutlineInputBorder(),
                      ),
                    ),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: TextField(
                      controller: minStockCtrl,
                      keyboardType: TextInputType.number,
                      decoration: const InputDecoration(
                        labelText: 'Định mức tồn Min',
                        border: OutlineInputBorder(),
                      ),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 14),
              Row(
                children: [
                  Expanded(
                    child: TextField(
                      controller: categoryCtrl,
                      decoration: const InputDecoration(
                        labelText: 'Nhóm nguyên liệu',
                        border: OutlineInputBorder(),
                      ),
                    ),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: TextField(
                      controller: packagingCtrl,
                      decoration: const InputDecoration(
                        labelText: 'Quy cách đóng gói',
                        border: OutlineInputBorder(),
                      ),
                    ),
                  ),
                ],
              ),
              if (isAdmin) ...[
                const SizedBox(height: 14),
                Row(
                  children: [
                    Expanded(
                      child: TextField(
                        controller: costPriceCtrl,
                        keyboardType: TextInputType.number,
                        decoration: const InputDecoration(
                          labelText: 'Giá vốn (Admin)',
                          suffixText: 'đ',
                          border: OutlineInputBorder(),
                        ),
                      ),
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: TextField(
                        controller: sellingPriceCtrl,
                        keyboardType: TextInputType.number,
                        decoration: const InputDecoration(
                          labelText: 'Giá bán (Admin)',
                          suffixText: 'đ',
                          border: OutlineInputBorder(),
                        ),
                      ),
                    ),
                  ],
                ),
              ],
            ],
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(ctx).pop(false),
            child: const Text('Hủy'),
          ),
          FilledButton(
            onPressed: () => Navigator.of(ctx).pop(true),
            child: const Text('Lưu thay đổi'),
          ),
        ],
      ),
    );

    if (ok == true && mounted) {
      try {
        final repo = RepositoryScope.of(context);
        await repo.updateItem(
          id: item.id,
          name: nameCtrl.text.trim(),
          unit: unitCtrl.text.trim(),
          category: categoryCtrl.text.trim(),
          packaging: packagingCtrl.text.trim(),
          costPrice: isAdmin
              ? double.tryParse(costPriceCtrl.text.replaceAll(',', '').trim())
              : item.costPrice,
          sellingPrice: isAdmin
              ? double.tryParse(sellingPriceCtrl.text.replaceAll(',', '').trim())
              : item.sellingPrice,
          minStock: double.tryParse(minStockCtrl.text.replaceAll(',', '').trim()),
        );
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(
                content: Text('Đã cập nhật thông tin mặt hàng!'),
                behavior: SnackBarBehavior.floating),
          );
          _refresh();
        }
      } catch (e) {
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
                content: Text('Lỗi: ${friendlyError(e)}'),
                backgroundColor: Colors.red),
          );
        }
      }
    }
  }

  void _toggleSelectionMode() {
    setState(() {
      _isSelectionMode = !_isSelectionMode;
      _selectedItemIds.clear();
    });
  }

  void _toggleItemSelection(String itemId) {
    setState(() {
      if (_selectedItemIds.contains(itemId)) {
        _selectedItemIds.remove(itemId);
      } else {
        _selectedItemIds.add(itemId);
      }
    });
  }

  void _selectAllItems(List<InventoryItem> items) {
    setState(() {
      _selectedItemIds.addAll(items.map((i) => i.id));
    });
  }

  void _clearSelection() {
    setState(() {
      _selectedItemIds.clear();
    });
  }

  void _showItemDetailSheet(
    BuildContext context,
    InventoryItem item,
    _InventoryData data, {
    required bool isAdmin,
  }) {
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;
    final totalStock = _stockForItem(item.id, data.balances);
    final minStock = item.minStock;
    final bool isOutOfStock = totalStock <= 0;
    final bool isLowStock =
        !isOutOfStock && minStock != null && totalStock <= minStock;

    // Balances per location
    final itemBalances =
        data.balances.where((b) => b.itemId == item.id).toList();

    showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (ctx) {
        return Container(
          decoration: BoxDecoration(
            color: isDark ? const Color(0xFF0F172A) : Colors.white,
            borderRadius: const BorderRadius.vertical(top: Radius.circular(24)),
            boxShadow: [
              BoxShadow(
                color: Colors.black.withValues(alpha: 0.2),
                blurRadius: 20,
                offset: const Offset(0, -4),
              ),
            ],
          ),
          padding: EdgeInsets.only(
            left: 20,
            right: 20,
            top: 16,
            bottom: MediaQuery.paddingOf(ctx).bottom + 20,
          ),
          child: SingleChildScrollView(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: [
                Center(
                  child: Container(
                    width: 40,
                    height: 4,
                    decoration: BoxDecoration(
                      color: isDark
                          ? const Color(0xFF334155)
                          : const Color(0xFFCBD5E1),
                      borderRadius: BorderRadius.circular(2),
                    ),
                  ),
                ),
                const SizedBox(height: 16),
                Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Container(
                      padding: const EdgeInsets.all(12),
                      decoration: BoxDecoration(
                        color: const Color(0xFF2563EB).withValues(alpha: 0.1),
                        borderRadius: BorderRadius.circular(12),
                      ),
                      child: const Icon(
                        Icons.inventory_2_outlined,
                        color: Color(0xFF2563EB),
                        size: 28,
                      ),
                    ),
                    const SizedBox(width: 14),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            item.name,
                            style: theme.textTheme.titleMedium?.copyWith(
                              fontWeight: FontWeight.w800,
                              fontSize: 17,
                            ),
                          ),
                          const SizedBox(height: 4),
                          Wrap(
                            spacing: 8,
                            runSpacing: 4,
                            crossAxisAlignment: WrapCrossAlignment.center,
                            children: [
                              Container(
                                padding: const EdgeInsets.symmetric(
                                    horizontal: 6, vertical: 2),
                                decoration: BoxDecoration(
                                  color: isDark
                                      ? Colors.white10
                                      : const Color(0xFFF1F5F9),
                                  borderRadius: BorderRadius.circular(4),
                                  border: Border.all(
                                    color: isDark
                                        ? const Color(0xFF475569)
                                        : const Color(0xFFCBD5E1),
                                  ),
                                ),
                                child: Text(
                                  item.sku,
                                  style: const TextStyle(
                                    fontFamily: 'monospace',
                                    fontWeight: FontWeight.w700,
                                    fontSize: 11,
                                    color: Color(0xFF2563EB),
                                  ),
                                ),
                              ),
                              if (item.category != null &&
                                  item.category!.isNotEmpty)
                                Container(
                                  padding: const EdgeInsets.symmetric(
                                      horizontal: 6, vertical: 2),
                                  decoration: BoxDecoration(
                                    color: const Color(0xFF0891B2)
                                        .withValues(alpha: 0.1),
                                    borderRadius: BorderRadius.circular(4),
                                  ),
                                  child: Text(
                                    item.category!,
                                    style: const TextStyle(
                                      fontWeight: FontWeight.w600,
                                      fontSize: 11,
                                      color: Color(0xFF0891B2),
                                    ),
                                  ),
                                ),
                              if (item.packaging != null &&
                                  item.packaging!.isNotEmpty)
                                Text(
                                  item.packaging!,
                                  style: TextStyle(
                                    fontSize: 12,
                                    color: theme.colorScheme.onSurfaceVariant,
                                  ),
                                ),
                            ],
                          ),
                        ],
                      ),
                    ),
                    IconButton(
                      icon: const Icon(Icons.close_rounded),
                      onPressed: () => Navigator.pop(ctx),
                    ),
                  ],
                ),
                const SizedBox(height: 16),
                const Divider(),
                const SizedBox(height: 12),

                // Vị trí lưu kho & Tồn kho thực tế
                Text(
                  'VỊ TRÍ LƯU KHO & TỒN KHẢ DỤNG',
                  style: TextStyle(
                    fontSize: 11,
                    fontWeight: FontWeight.w800,
                    letterSpacing: 0.5,
                    color: theme.colorScheme.onSurfaceVariant,
                  ),
                ),
                const SizedBox(height: 8),
                Container(
                  padding: const EdgeInsets.all(12),
                  decoration: BoxDecoration(
                    color: isDark
                        ? const Color(0xFF1E293B)
                        : const Color(0xFFF8FAFC),
                    borderRadius: BorderRadius.circular(12),
                    border: Border.all(
                      color: isDark
                          ? const Color(0xFF334155)
                          : const Color(0xFFE2E8F0),
                    ),
                  ),
                  child: Column(
                    children: [
                      Row(
                        mainAxisAlignment: MainAxisAlignment.spaceBetween,
                        children: [
                          const Text(
                            'Tổng Tồn Hiện Tại',
                            style: TextStyle(
                                fontWeight: FontWeight.w700, fontSize: 13),
                          ),
                          Container(
                            padding: const EdgeInsets.symmetric(
                                horizontal: 8, vertical: 3),
                            decoration: BoxDecoration(
                              color: isOutOfStock
                                  ? const Color(0xFFEF4444)
                                      .withValues(alpha: 0.1)
                                  : (isLowStock
                                      ? const Color(0xFFD97706)
                                          .withValues(alpha: 0.1)
                                      : const Color(0xFF059669)
                                          .withValues(alpha: 0.1)),
                              borderRadius: BorderRadius.circular(6),
                            ),
                            child: Text(
                              '${AppFormat.number(totalStock.toString())} ${item.unit}',
                              style: TextStyle(
                                fontWeight: FontWeight.w800,
                                fontSize: 14,
                                color: isOutOfStock
                                    ? const Color(0xFFEF4444)
                                    : (isLowStock
                                        ? const Color(0xFFD97706)
                                        : const Color(0xFF059669)),
                              ),
                            ),
                          ),
                        ],
                      ),
                      if (item.minStock != null) ...[
                        const SizedBox(height: 8),
                        Row(
                          mainAxisAlignment: MainAxisAlignment.spaceBetween,
                          children: [
                            Text(
                              'Định Mức Tồn Tối Thiểu (Min)',
                              style: TextStyle(
                                fontSize: 12,
                                color: theme.colorScheme.onSurfaceVariant,
                              ),
                            ),
                            Text(
                              '${AppFormat.number(item.minStock!.toString())} ${item.unit}',
                              style: const TextStyle(
                                  fontWeight: FontWeight.w600, fontSize: 12),
                            ),
                          ],
                        ),
                      ],
                      const Padding(
                        padding: EdgeInsets.symmetric(vertical: 8),
                        child: Divider(height: 1),
                      ),
                      // Từng địa điểm
                      if (itemBalances.isEmpty)
                        Padding(
                          padding: const EdgeInsets.symmetric(vertical: 4),
                          child: Text(
                            'Chưa có dữ liệu tồn tại từng vị trí kho',
                            style: TextStyle(
                              fontSize: 12,
                              color: theme.colorScheme.onSurfaceVariant,
                            ),
                          ),
                        )
                      else
                        ...itemBalances.map((bal) {
                          final loc = data.locations.firstWhere(
                            (l) => l.id == bal.locationId,
                            orElse: () => InventoryLocation(
                              id: bal.locationId,
                              code: bal.locationId,
                              name: bal.locationId,
                            ),
                          );
                          final qty = double.tryParse(bal.quantity) ?? 0.0;
                          final locNameLower = loc.name.toLowerCase();
                          final isCooler = locNameLower.contains('mát') ||
                              loc.code.toLowerCase().contains('cool');
                          final isBar = locNameLower.contains('bar') ||
                              loc.code.toLowerCase().contains('bar');
                          return Padding(
                            padding: const EdgeInsets.symmetric(vertical: 4),
                            child: Row(
                              children: [
                                Icon(
                                  isCooler
                                      ? Icons.ac_unit_rounded
                                      : (isBar
                                          ? Icons.local_bar_rounded
                                          : Icons.warehouse_rounded),
                                  size: 16,
                                  color: const Color(0xFF2563EB),
                                ),
                                const SizedBox(width: 8),
                                Expanded(
                                  child: Text(
                                    loc.name,
                                    style: const TextStyle(fontSize: 12.5),
                                  ),
                                ),
                                Text(
                                  '${AppFormat.number(qty.toString())} ${item.unit}',
                                  style: const TextStyle(
                                    fontWeight: FontWeight.w700,
                                    fontSize: 12.5,
                                  ),
                                ),
                              ],
                            ),
                          );
                        }),
                    ],
                  ),
                ),
                const SizedBox(height: 16),

                // Giá & Tài chính
                Text(
                  'THÔNG TIN TÀI CHÍNH & GIÁ',
                  style: TextStyle(
                    fontSize: 11,
                    fontWeight: FontWeight.w800,
                    letterSpacing: 0.5,
                    color: theme.colorScheme.onSurfaceVariant,
                  ),
                ),
                const SizedBox(height: 8),
                Container(
                  padding: const EdgeInsets.all(12),
                  decoration: BoxDecoration(
                    color: isDark
                        ? const Color(0xFF1E293B)
                        : const Color(0xFFF8FAFC),
                    borderRadius: BorderRadius.circular(12),
                    border: Border.all(
                      color: isDark
                          ? const Color(0xFF334155)
                          : const Color(0xFFE2E8F0),
                    ),
                  ),
                  child: (!isAdmin || !_revealPrices)
                      ? Row(
                          children: [
                            const Icon(Icons.lock_outline_rounded,
                                size: 18, color: Colors.grey),
                            const SizedBox(width: 8),
                            Expanded(
                              child: Text(
                                !isAdmin
                                    ? 'Chỉ tài khoản Quản trị viên (Admin) mới có quyền xem thông tin tài chính & giá vốn/giá bán.'
                                    : 'Giá đang ở chế độ ẩn. Bật "Đang ẩn giá" trên bộ lọc để xem.',
                                style: TextStyle(
                                  fontSize: 12,
                                  color: theme.colorScheme.onSurfaceVariant,
                                ),
                              ),
                            ),
                          ],
                        )
                      : Column(
                          children: [
                            Row(
                              mainAxisAlignment: MainAxisAlignment.spaceBetween,
                              children: [
                                const Text('Giá Bán:',
                                    style: TextStyle(
                                        fontSize: 12.5,
                                        fontWeight: FontWeight.w600)),
                                Text(
                                  item.sellingPrice != null
                                      ? AppFormat.money(item.sellingPrice!.toStringAsFixed(0), currency: '₫')
                                      : 'Chưa thiết lập',
                                  style: const TextStyle(
                                    fontWeight: FontWeight.w800,
                                    fontSize: 13,
                                    color: Color(0xFF0284C7),
                                  ),
                                ),
                              ],
                            ),
                            const SizedBox(height: 6),
                            Row(
                              mainAxisAlignment: MainAxisAlignment.spaceBetween,
                              children: [
                                const Text('Giá Vốn (Cost):',
                                    style: TextStyle(
                                        fontSize: 12.5,
                                        fontWeight: FontWeight.w600)),
                                Text(
                                  item.costPrice != null
                                      ? AppFormat.money(item.costPrice!.toStringAsFixed(0), currency: '₫')
                                      : 'Chưa thiết lập',
                                  style: const TextStyle(
                                    fontWeight: FontWeight.w700,
                                    fontSize: 13,
                                    color: Color(0xFF059669),
                                  ),
                                ),
                              ],
                            ),
                            if (item.costPrice != null &&
                                item.sellingPrice != null &&
                                item.sellingPrice! > 0) ...[
                              const SizedBox(height: 6),
                              Row(
                                mainAxisAlignment:
                                    MainAxisAlignment.spaceBetween,
                                children: [
                                  const Text('Biên Lợi Nhuận Gộp:',
                                      style: TextStyle(
                                          fontSize: 12.5, color: Colors.grey)),
                                  Text(
                                    '${((item.sellingPrice! - item.costPrice!) / item.sellingPrice! * 100).toStringAsFixed(1)}% (${AppFormat.money((item.sellingPrice! - item.costPrice!).toStringAsFixed(0), currency: '₫')})',
                                    style: const TextStyle(
                                      fontWeight: FontWeight.w700,
                                      fontSize: 12.5,
                                      color: Color(0xFFD97706),
                                    ),
                                  ),
                                ],
                              ),
                            ],
                            if (item.costPrice != null) ...[
                              const Padding(
                                padding: EdgeInsets.symmetric(vertical: 6),
                                child: Divider(height: 1),
                              ),
                              Row(
                                mainAxisAlignment:
                                    MainAxisAlignment.spaceBetween,
                                children: [
                                  const Text('Định Giá Tồn Hiện Tại:',
                                      style: TextStyle(
                                          fontSize: 12.5,
                                          fontWeight: FontWeight.bold)),
                                  Text(
                                    AppFormat.money((totalStock * item.costPrice!).toStringAsFixed(0), currency: '₫'),
                                    style: const TextStyle(
                                      fontWeight: FontWeight.w900,
                                      fontSize: 13.5,
                                      color: Color(0xFF2563EB),
                                    ),
                                  ),
                                ],
                              ),
                            ],
                          ],
                        ),
                ),
                const SizedBox(height: 20),

                // Thao tác Action Buttons
                Row(
                  children: [
                    if (isAdmin) ...[
                      Expanded(
                        child: OutlinedButton.icon(
                          onPressed: () {
                            Navigator.pop(ctx);
                            _showSetStockLevelDialog(
                              item,
                              data.locations,
                              data.stockLevels,
                            );
                          },
                          icon: const Icon(Icons.tune_outlined, size: 16),
                          label: const Text('Cài Định Mức'),
                        ),
                      ),
                      const SizedBox(width: 10),
                      Expanded(
                        child: FilledButton.icon(
                          onPressed: () {
                            Navigator.pop(ctx);
                            _showEditItemDialog(item);
                          },
                          icon: const Icon(Icons.edit_outlined, size: 16),
                          label: const Text('Sửa & Đổi Giá'),
                          style: FilledButton.styleFrom(
                            backgroundColor: const Color(0xFF2563EB),
                          ),
                        ),
                      ),
                    ] else
                      Expanded(
                        child: OutlinedButton(
                          onPressed: () => Navigator.pop(ctx),
                          child: const Text('Đóng'),
                        ),
                      ),
                  ],
                ),
              ],
            ),
          ),
        );
      },
    );
  }

  Future<void> _confirmDeleteItem(InventoryItem item, [List<StockBalance>? balances]) async {
    // Check if item has remaining stock
    double totalStock = 0;
    if (balances != null) {
      totalStock = balances
          .where((b) => b.itemId == item.id)
          .fold<double>(0, (sum, b) => sum + (double.tryParse(b.quantity) ?? 0));
    }

    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
        title: const Row(
          children: [
            Icon(Icons.warning_amber_rounded, color: Colors.red),
            SizedBox(width: 8),
            Expanded(
              child: Text('Xác nhận xóa mặt hàng',
                  style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
            ),
          ],
        ),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
                'Bạn có chắc chắn muốn xóa mặt hàng "${item.name}" (SKU: ${item.sku}) không?'),
            if (totalStock > 0) ...[
              const SizedBox(height: 12),
              Container(
                padding: const EdgeInsets.all(10),
                decoration: BoxDecoration(
                  color: Colors.amber.withValues(alpha: 0.15),
                  borderRadius: BorderRadius.circular(8),
                  border: Border.all(color: Colors.amber.shade700),
                ),
                child: Row(
                  children: [
                    const Icon(Icons.info_outline, size: 18, color: Colors.orange),
                    const SizedBox(width: 8),
                    Expanded(
                      child: Text(
                        'Cảnh báo: Mặt hàng đang còn tồn kho (${AppFormat.intFormat(totalStock.round())} ${item.unit}).',
                        style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w600),
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(ctx).pop(false),
            child: const Text('Hủy'),
          ),
          FilledButton(
            key: Key('btn-confirm-delete-${item.sku}'),
            style: FilledButton.styleFrom(backgroundColor: Colors.red),
            onPressed: () => Navigator.of(ctx).pop(true),
            child: const Text('Xác nhận xóa'),
          ),
        ],
      ),
    );

    if (ok == true && mounted) {
      try {
        final repo = RepositoryScope.of(context);
        await repo.deleteItem(item.id);
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
                content: Text('Đã xóa mặt hàng "${item.name}"!'),
                behavior: SnackBarBehavior.floating),
          );
          _refresh();
        }
      } catch (e) {
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
                content: Text('Lỗi: ${friendlyError(e)}'),
                backgroundColor: Colors.red),
          );
        }
      }
    }
  }

  Future<void> _confirmDeleteItemsBatch(
      List<InventoryItem> allItems, List<StockBalance> balances) async {
    final selectedItems =
        allItems.where((i) => _selectedItemIds.contains(i.id)).toList();
    if (selectedItems.isEmpty) return;

    // Check if any selected item has stock > 0
    final itemsWithStock = <String>[];
    for (final item in selectedItems) {
      final totalQty = balances
          .where((b) => b.itemId == item.id)
          .fold<double>(0, (sum, b) => sum + (double.tryParse(b.quantity) ?? 0));
      if (totalQty > 0) {
        itemsWithStock.add(
            '${item.name} (${AppFormat.intFormat(totalQty.round())} ${item.unit})');
      }
    }

    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
        title: const Row(
          children: [
            Icon(Icons.warning_amber_rounded, color: Colors.red),
            SizedBox(width: 8),
            Expanded(
              child: Text('Xác nhận xóa hàng loạt',
                  style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
            ),
          ],
        ),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
                'Bạn có chắc chắn muốn xóa ${selectedItems.length} mặt hàng đã chọn không?'),
            if (itemsWithStock.isNotEmpty) ...[
              const SizedBox(height: 12),
              Container(
                padding: const EdgeInsets.all(10),
                decoration: BoxDecoration(
                  color: Colors.amber.withValues(alpha: 0.15),
                  borderRadius: BorderRadius.circular(8),
                  border: Border.all(color: Colors.amber.shade700),
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Row(
                      children: [
                        Icon(Icons.info_outline, size: 16, color: Colors.orange),
                        SizedBox(width: 6),
                        Text('Lưu ý mặt hàng còn tồn kho:',
                            style: TextStyle(
                                fontSize: 12, fontWeight: FontWeight.bold)),
                      ],
                    ),
                    const SizedBox(height: 4),
                    for (final s in itemsWithStock.take(5))
                      Text('• $s', style: const TextStyle(fontSize: 11.5)),
                    if (itemsWithStock.length > 5)
                      Text(
                          '... và ${itemsWithStock.length - 5} mặt hàng khác',
                          style: const TextStyle(
                              fontSize: 11, fontStyle: FontStyle.italic)),
                  ],
                ),
              ),
            ],
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(ctx).pop(false),
            child: const Text('Hủy'),
          ),
          FilledButton(
            key: const Key('btn-confirm-batch-delete'),
            style: FilledButton.styleFrom(backgroundColor: Colors.red),
            onPressed: () => Navigator.of(ctx).pop(true),
            child: Text('Xác nhận xóa (${selectedItems.length})'),
          ),
        ],
      ),
    );

    if (ok == true && mounted) {
      try {
        final repo = RepositoryScope.of(context);
        await repo.deleteItemsBatch(selectedItems.map((i) => i.id).toList());
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
              content:
                  Text('Đã xóa thành công ${selectedItems.length} mặt hàng!'),
              behavior: SnackBarBehavior.floating,
              backgroundColor: const Color(0xFF059669),
            ),
          );
          setState(() {
            _selectedItemIds.clear();
            _isSelectionMode = false;
          });
          _refresh();
        }
      } catch (e) {
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
              content: Text('Lỗi xóa mặt hàng: ${friendlyError(e)}'),
              backgroundColor: Colors.red,
            ),
          );
        }
      }
    }
  }

  // ignore: unused_element
  Future<void> _showAssetLifecycleDialog(
      AssetRecord asset, _InventoryData data) async {
    final repo = RepositoryScope.of(context);
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;

    final loc = data.locations.cast<InventoryLocation?>().firstWhere(
          (l) => l?.id == asset.locationId,
          orElse: () => null,
        );
    final itm = data.items.cast<InventoryItem?>().firstWhere(
          (it) => it?.id == asset.itemId,
          orElse: () => null,
        );

    showDialog<void>(
      context: context,
      builder: (ctx) {
        return StatefulBuilder(
          builder: (ctx, setDlgState) {
            return FutureBuilder<List<AssetLogItem>>(
              future: repo.getAssetHistory(asset.id ?? asset.serial),
              builder: (ctx, snapshot) {
                return AlertDialog(
                  shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(16)),
                  title: Row(
                    children: [
                      Container(
                        padding: const EdgeInsets.all(8),
                        decoration: BoxDecoration(
                          color:
                              const Color(0xFF7C3AED).withValues(alpha: 0.12),
                          borderRadius: BorderRadius.circular(8),
                        ),
                        child: const Icon(Icons.qr_code_2_rounded,
                            color: Color(0xFF7C3AED), size: 22),
                      ),
                      const SizedBox(width: 10),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              'Vòng Đời & Bàn Giao: ${asset.serial}',
                              style: const TextStyle(
                                  fontSize: 16, fontWeight: FontWeight.bold),
                            ),
                            Text(
                              '${itm?.name ?? "Vật tư"} • Kho hiện tại: ${loc?.name ?? asset.locationId}',
                              style: TextStyle(
                                  fontSize: 12,
                                  color: theme.colorScheme.onSurfaceVariant),
                            ),
                          ],
                        ),
                      ),
                    ],
                  ),
                  content: SizedBox(
                    width: 600,
                    height: 440,
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        // Summary card
                        Container(
                          padding: const EdgeInsets.all(12),
                          decoration: BoxDecoration(
                            color: isDark
                                ? const Color(0xFF1E293B)
                                : const Color(0xFFF8FAFC),
                            borderRadius: BorderRadius.circular(10),
                            border: Border.all(
                                color: theme.colorScheme.outlineVariant
                                    .withValues(alpha: 0.5)),
                          ),
                          child: Row(
                            mainAxisAlignment: MainAxisAlignment.spaceBetween,
                            children: [
                              Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  const Text('Người phụ trách',
                                      style: TextStyle(
                                          fontSize: 11, color: Colors.grey)),
                                  const SizedBox(height: 2),
                                  Text(
                                    asset.assignee ?? 'Chưa bàn giao',
                                    style: const TextStyle(
                                        fontWeight: FontWeight.w700,
                                        fontSize: 13),
                                  ),
                                ],
                              ),
                              Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  const Text('Trạng thái',
                                      style: TextStyle(
                                          fontSize: 11, color: Colors.grey)),
                                  const SizedBox(height: 2),
                                  Container(
                                    padding: const EdgeInsets.symmetric(
                                        horizontal: 8, vertical: 2),
                                    decoration: BoxDecoration(
                                      color: const Color(0xFF10B981)
                                          .withValues(alpha: 0.15),
                                      borderRadius: BorderRadius.circular(4),
                                    ),
                                    child: Text(
                                      asset.status.name.toUpperCase(),
                                      style: const TextStyle(
                                        color: Color(0xFF059669),
                                        fontSize: 11,
                                        fontWeight: FontWeight.w800,
                                      ),
                                    ),
                                  ),
                                ],
                              ),
                              FilledButton.icon(
                                key: const Key('btn-open-handover-dialog'),
                                onPressed: () async {
                                  final done =
                                      await _showHandoverDialog(asset, data);
                                  if (done == true) {
                                    setDlgState(() {});
                                    _refresh();
                                  }
                                },
                                icon: const Icon(Icons.handshake_outlined,
                                    size: 16),
                                label: const Text('Bàn giao nguyên liệu'),
                                style: FilledButton.styleFrom(
                                  backgroundColor: const Color(0xFF7C3AED),
                                  padding: const EdgeInsets.symmetric(
                                      horizontal: 12, vertical: 8),
                                ),
                              ),
                            ],
                          ),
                        ),
                        const SizedBox(height: 16),
                        const Text(
                          'Sổ Nhật Ký Vòng Đời & Luân Chuyển',
                          style: TextStyle(
                              fontWeight: FontWeight.w800, fontSize: 13),
                        ),
                        const SizedBox(height: 8),
                        Expanded(
                          child: snapshot.connectionState !=
                                  ConnectionState.done
                              ? const Center(child: CircularProgressIndicator())
                              : (snapshot.data == null ||
                                      snapshot.data!.isEmpty)
                                  ? const Center(
                                      child: Text(
                                          'Chưa có lịch sử luân chuyển cho nguyên liệu này.'))
                                  : ListView.separated(
                                      itemCount: snapshot.data!.length,
                                      separatorBuilder: (_, __) =>
                                          const Divider(height: 12),
                                      itemBuilder: (ctx, idx) {
                                        final log = snapshot.data![idx];
                                        return Row(
                                          crossAxisAlignment:
                                              CrossAxisAlignment.start,
                                          children: [
                                            Container(
                                              padding: const EdgeInsets.all(6),
                                              decoration: BoxDecoration(
                                                color: const Color(0xFF7C3AED)
                                                    .withValues(alpha: 0.1),
                                                shape: BoxShape.circle,
                                              ),
                                              child: const Icon(Icons.timeline,
                                                  size: 14,
                                                  color: Color(0xFF7C3AED)),
                                            ),
                                            const SizedBox(width: 10),
                                            Expanded(
                                              child: Column(
                                                crossAxisAlignment:
                                                    CrossAxisAlignment.start,
                                                children: [
                                                  Row(
                                                    mainAxisAlignment:
                                                        MainAxisAlignment
                                                            .spaceBetween,
                                                    children: [
                                                      Text(
                                                        log.statusBefore != null
                                                            ? '${log.statusBefore} → ${log.statusAfter}'
                                                            : log.statusAfter,
                                                        style: const TextStyle(
                                                            fontWeight:
                                                                FontWeight.w700,
                                                            fontSize: 12.5),
                                                      ),
                                                      Text(
                                                        AppFormat.dateTime(
                                                            log.createdAt),
                                                        style: const TextStyle(
                                                            fontSize: 11,
                                                            color: Colors.grey),
                                                      ),
                                                    ],
                                                  ),
                                                  if (log.toLocationName !=
                                                          null ||
                                                      log.toAssignee !=
                                                          null) ...[
                                                    const SizedBox(height: 2),
                                                    Text(
                                                      'Kho: ${log.toLocationName ?? "N/A"}${log.toAssignee != null ? " • Người nhận: ${log.toAssignee}" : ""}',
                                                      style: TextStyle(
                                                          fontSize: 11.5,
                                                          color: theme
                                                              .colorScheme
                                                              .onSurfaceVariant),
                                                    ),
                                                  ],
                                                  if (log.notes != null &&
                                                      log.notes!
                                                          .isNotEmpty) ...[
                                                    const SizedBox(height: 2),
                                                    Text(
                                                      'Ghi chú: ${log.notes}',
                                                      style: const TextStyle(
                                                          fontSize: 11.5,
                                                          fontStyle:
                                                              FontStyle.italic,
                                                          color: Colors.grey),
                                                    ),
                                                  ],
                                                  if (log.actorName !=
                                                      null) ...[
                                                    const SizedBox(height: 1),
                                                    Text(
                                                      'Thực hiện bởi: ${log.actorName}',
                                                      style: const TextStyle(
                                                          fontSize: 10.5,
                                                          color: Colors.grey),
                                                    ),
                                                  ],
                                                ],
                                              ),
                                            ),
                                          ],
                                        );
                                      },
                                    ),
                        ),
                      ],
                    ),
                  ),
                  actions: [
                    TextButton(
                      onPressed: () => Navigator.of(ctx).pop(),
                      child: const Text('Đóng'),
                    ),
                  ],
                );
              },
            );
          },
        );
      },
    );
  }

  Future<bool?> _showHandoverDialog(
      AssetRecord asset, _InventoryData data) async {
    final repo = RepositoryScope.of(context);
    String? toLocId = asset.locationId;
    final assigneeCtrl = TextEditingController(text: asset.assignee ?? '');
    final notesCtrl = TextEditingController();
    String newStatus = asset.status.name;

    return showDialog<bool>(
      context: context,
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, setDlgState) => AlertDialog(
          shape:
              RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
          title: Text('Bàn Giao / Luân Chuyển: ${asset.serial}'),
          content: SingleChildScrollView(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                DropdownButtonFormField<String>(
                  key: const Key('handover-location-dropdown'),
                  isExpanded: true,
                  initialValue: toLocId,
                  decoration: const InputDecoration(
                      labelText: 'Kho / Vị trí đích',
                      border: OutlineInputBorder()),
                  items: [
                    for (final loc in data.locations)
                      DropdownMenuItem(
                          value: loc.id,
                          child: Text('${loc.code} — ${loc.name}')),
                  ],
                  onChanged: (v) => setDlgState(() => toLocId = v),
                ),
                const SizedBox(height: 12),
                TextField(
                  key: const Key('handover-assignee-input'),
                  controller: assigneeCtrl,
                  decoration: const InputDecoration(
                    labelText: 'Nhân viên tiếp nhận / Pha chế *',
                    hintText: 'Nhập tên hoặc mã nhân viên',
                    border: OutlineInputBorder(),
                  ),
                ),
                const SizedBox(height: 12),
                DropdownButtonFormField<String>(
                  key: const Key('handover-status-dropdown'),
                  isExpanded: true,
                  initialValue: newStatus,
                  decoration: const InputDecoration(
                      labelText: 'Trạng thái sau bàn giao',
                      border: OutlineInputBorder()),
                  items: const [
                    DropdownMenuItem(
                        value: 'available',
                        child: Text('available (Trong kho/Khả dụng)')),
                    DropdownMenuItem(
                        value: 'inUse',
                        child: Text('inUse (Đang sử dụng/Đã bàn giao)')),
                    DropdownMenuItem(
                        value: 'maintenance',
                        child: Text('maintenance (Kiểm kê/Bảo trì)')),
                    DropdownMenuItem(
                        value: 'disposed',
                        child: Text('disposed (Hủy/Mất/Thu hồi)')),
                  ],
                  onChanged: (v) =>
                      setDlgState(() => newStatus = v ?? newStatus),
                ),
                const SizedBox(height: 12),
                TextField(
                  key: const Key('handover-notes-input'),
                  controller: notesCtrl,
                  maxLines: 2,
                  decoration: const InputDecoration(
                    labelText: 'Nội dung biên bản bàn giao / Ghi chú',
                    hintText: 'Bàn giao công cụ / nguyên liệu cho nhân viên...',
                    border: OutlineInputBorder(),
                  ),
                ),
              ],
            ),
          ),
          actions: [
            TextButton(
                onPressed: () => Navigator.of(ctx).pop(false),
                child: const Text('Huỷ')),
            FilledButton(
              key: const Key('handover-confirm-btn'),
              style: FilledButton.styleFrom(
                  backgroundColor: const Color(0xFF7C3AED)),
              onPressed: () async {
                try {
                  await repo.handoverAsset(
                    asset.id ?? asset.serial,
                    toLocationId: toLocId,
                    toAssignee: assigneeCtrl.text.trim().isNotEmpty
                        ? assigneeCtrl.text.trim()
                        : null,
                    status: newStatus,
                    notes: notesCtrl.text.trim().isNotEmpty
                        ? notesCtrl.text.trim()
                        : null,
                  );
                  if (ctx.mounted) Navigator.of(ctx).pop(true);
                  if (mounted) {
                    AppToast.success(
                        context, 'Bàn giao nguyên liệu thành công!');
                  }
                } catch (e) {
                  if (mounted) {
                    AppToast.error(
                        context, 'Lỗi bàn giao: ${friendlyError(e)}');
                  }
                }
              },
              child: const Text('Xác nhận bàn giao'),
            ),
          ],
        ),
      ),
    );
  }

  Future<void> _showSetStockLevelDialog(
    InventoryItem item,
    List<InventoryLocation> locations,
    List<StockLevelItem> stockLevels,
  ) async {
    if (locations.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
            content: Text('Chưa có kho lưu trữ để thiết lập định mức.')),
      );
      return;
    }

    String selectedLocId = locations.first.id;
    final existingLevel = stockLevels.cast<StockLevelItem?>().firstWhere(
          (l) => l?.itemId == item.id && l?.locationId == selectedLocId,
          orElse: () => null,
        );

    final minCtrl = TextEditingController(text: existingLevel?.minQty ?? '10');
    final maxCtrl = TextEditingController(text: existingLevel?.maxQty ?? '100');

    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, setDlgState) {
          return AlertDialog(
            shape:
                RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
            title: Row(
              children: [
                const Icon(Icons.tune_rounded, color: Color(0xFF2563EB)),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    'Định Mức Tồn: ${item.name}',
                    style: const TextStyle(
                        fontSize: 16, fontWeight: FontWeight.bold),
                    overflow: TextOverflow.ellipsis,
                  ),
                ),
              ],
            ),
            content: SingleChildScrollView(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text('Chọn Kho Lưu Trữ:',
                      style:
                          TextStyle(fontSize: 13, fontWeight: FontWeight.w600)),
                  const SizedBox(height: 6),
                  DropdownButtonFormField<String>(
                    initialValue: selectedLocId,
                    isExpanded: true,
                    decoration: const InputDecoration(
                        border: OutlineInputBorder(),
                        contentPadding:
                            EdgeInsets.symmetric(horizontal: 12, vertical: 10)),
                    items: locations
                        .map((l) => DropdownMenuItem(
                            value: l.id, child: Text('${l.code} - ${l.name}')))
                        .toList(),
                    onChanged: (val) {
                      if (val != null) {
                        setDlgState(() {
                          selectedLocId = val;
                          final lvl =
                              stockLevels.cast<StockLevelItem?>().firstWhere(
                                    (l) =>
                                        l?.itemId == item.id &&
                                        l?.locationId == selectedLocId,
                                    orElse: () => null,
                                  );
                          minCtrl.text = lvl?.minQty ?? '10';
                          maxCtrl.text = lvl?.maxQty ?? '100';
                        });
                      }
                    },
                  ),
                  const SizedBox(height: 16),
                  TextField(
                    controller: minCtrl,
                    keyboardType: TextInputType.number,
                    decoration: InputDecoration(
                      labelText: 'Định mức tối thiểu (Min Qty) *',
                      helperText: 'Cảnh báo thiếu khi tồn kho < mức này',
                      suffixText: item.unit,
                      border: const OutlineInputBorder(),
                    ),
                  ),
                  const SizedBox(height: 16),
                  TextField(
                    controller: maxCtrl,
                    keyboardType: TextInputType.number,
                    decoration: InputDecoration(
                      labelText: 'Định mức tối đa (Max Qty)',
                      helperText: 'Giới hạn lưu trữ an toàn của kho',
                      suffixText: item.unit,
                      border: const OutlineInputBorder(),
                    ),
                  ),
                ],
              ),
            ),
            actions: [
              TextButton(
                  onPressed: () => Navigator.of(ctx).pop(false),
                  child: const Text('Hủy')),
              FilledButton(
                style: FilledButton.styleFrom(
                    backgroundColor: const Color(0xFF2563EB)),
                onPressed: () => Navigator.of(ctx).pop(true),
                child: const Text('Lưu Định Mức'),
              ),
            ],
          );
        },
      ),
    );

    if (ok == true && mounted) {
      try {
        final repo = RepositoryScope.of(context);
        await repo.putStockLevel(
          locationId: selectedLocId,
          itemId: item.id,
          minQty: minCtrl.text.trim(),
          maxQty: maxCtrl.text.trim().isNotEmpty ? maxCtrl.text.trim() : null,
        );
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(
                content: Text('Đã cập nhật định mức tồn kho an toàn!'),
                behavior: SnackBarBehavior.floating),
          );
          _refresh();
        }
      } catch (e) {
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
                content: Text('Lỗi: ${friendlyError(e)}'),
                backgroundColor: Colors.red),
          );
        }
      }
    }
  }

  Future<void> _showCreateStocktakeDialog(
      List<InventoryLocation> locations) async {
    if (locations.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Chưa có kho để mở đợt kiểm kê.')),
      );
      return;
    }
    String selectedLocId = locations.first.id;
    String selectedShift = 'morning';
    final noteCtrl = TextEditingController(text: 'Chốt tồn theo ca');

    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
        title: const Row(
          children: [
            Icon(Icons.fact_check_outlined, color: Color(0xFF0891B2)),
            SizedBox(width: 8),
            Text('Mở Đợt Kiểm Kê Mới',
                style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
          ],
        ),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text('Kho thực hiện kiểm kê *:',
                style: TextStyle(fontSize: 13, fontWeight: FontWeight.w600)),
            const SizedBox(height: 6),
            DropdownButtonFormField<String>(
              initialValue: selectedLocId,
              isExpanded: true,
              decoration: const InputDecoration(
                  border: OutlineInputBorder(),
                  contentPadding:
                      EdgeInsets.symmetric(horizontal: 12, vertical: 10)),
              items: locations
                  .map((l) => DropdownMenuItem(
                      value: l.id, child: Text('${l.code} - ${l.name}')))
                  .toList(),
              onChanged: (val) {
                if (val != null) selectedLocId = val;
              },
            ),
            const SizedBox(height: 16),
            DropdownButtonFormField<String>(
              initialValue: selectedShift,
              decoration: const InputDecoration(
                labelText: 'Ca làm việc',
                border: OutlineInputBorder(),
              ),
              items: const [
                DropdownMenuItem(
                    value: 'morning', child: Text('Ca Sáng 07:30 – 15:00')),
                DropdownMenuItem(
                    value: 'afternoon', child: Text('Ca Chiều 15:00 – 23:00')),
                DropdownMenuItem(
                    value: 'split', child: Text('Ca Lỡ ngày 07:30 – 18:00')),
              ],
              onChanged: (value) => selectedShift = value ?? 'morning',
            ),
            const SizedBox(height: 16),
            TextField(
              controller: noteCtrl,
              decoration: const InputDecoration(
                labelText: 'Ghi chú chốt ca',
                hintText: 'VD: Chốt tồn cuối Ca Sáng',
                border: OutlineInputBorder(),
              ),
            ),
          ],
        ),
        actions: [
          TextButton(
              onPressed: () => Navigator.of(ctx).pop(false),
              child: const Text('Hủy')),
          FilledButton(
            style: FilledButton.styleFrom(
                backgroundColor: const Color(0xFF0891B2)),
            onPressed: () => Navigator.of(ctx).pop(true),
            child: const Text('Bắt Đầu Kiểm Kê'),
          ),
        ],
      ),
    );

    if (ok == true && mounted) {
      try {
        final repo = RepositoryScope.of(context);
        final synced = await _queueStocktake(repo, 'create_stocktake', {
          'location_id': selectedLocId,
          'note': noteCtrl.text.trim().isNotEmpty ? noteCtrl.text.trim() : null,
          'shift_code': selectedShift,
          'business_date': DateTime.now().toIso8601String().substring(0, 10),
        }, 'create-${DateTime.now().microsecondsSinceEpoch}');
        OfflineHub.instance.addQueued();
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
                content: Text(synced ? 'Đã mở phiên chốt tồn theo ca!'
                    : StocktakeOutbox.shared.hasConflict
                        ? 'Ca đã mở hoặc dữ liệu xung đột. Cần kiểm tra trước khi thử lại.'
                        : 'Yêu cầu mở ca đã lưu trên thiết bị và sẽ đồng bộ khi có mạng.'),
                behavior: SnackBarBehavior.floating),
          );
          _refresh();
        }
      } catch (e) {
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
                content: Text('Lỗi: ${friendlyError(e)}'),
                backgroundColor: Colors.red),
          );
        }
      }
    }
  }

  Future<void> _showStocktakeDetailDialog(
    StocktakeItem stocktake,
    List<InventoryItem> items,
    List<InventoryLocation> locations, {
    List<StockLevelItem>? stockLevels,
  }) async {
    final loc = locations.cast<InventoryLocation?>().firstWhere(
          (l) => l?.id == stocktake.locationId,
          orElse: () => null,
        );
    final locName =
        loc != null ? '${loc.code} - ${loc.name}' : stocktake.locationId;
    final canEdit = stocktake.status == 'open';
    final canApprove = stocktake.status == 'submitted';

    // Map existing counted lines or initialize (with offline draft support)
    final countCtrls = <String, TextEditingController>{};
    final usedCtrls = <String, TextEditingController>{};
    final reasonCtrls = <String, TextEditingController>{};

    Map<String, dynamic>? localDraft;
    bool hasRestoredDraft = false;
    try {
      final draftRaw = _prefs?.getString('stocktake_draft_${stocktake.id}');
      if (draftRaw != null && draftRaw.isNotEmpty) {
        localDraft = jsonDecode(draftRaw) as Map<String, dynamic>?;
      }
    } catch (_) {}

    final draftUsed = (localDraft?['used'] as Map<String, dynamic>?) ?? {};
    final draftCount = (localDraft?['counted'] as Map<String, dynamic>?) ?? {};
    final draftReason = (localDraft?['reason'] as Map<String, dynamic>?) ?? {};

    for (final it in items) {
      final existingLine =
          stocktake.lines.cast<StocktakeLineItem?>().firstWhere(
                (l) => l?.itemId == it.id,
                orElse: () => null,
              );
      String initialUsed = existingLine != null ? existingLine.usedQty : '0';
      String initialCount = existingLine != null ? existingLine.countedQty : (existingLine?.bookQty ?? '0');
      String initialReason = existingLine?.reason ?? '';

      if (canEdit && localDraft != null) {
        if (draftUsed[it.id] != null) {
          initialUsed = draftUsed[it.id].toString();
          hasRestoredDraft = true;
        }
        if (draftCount[it.id] != null) {
          initialCount = draftCount[it.id].toString();
          hasRestoredDraft = true;
        }
        if (draftReason[it.id] != null) {
          initialReason = draftReason[it.id].toString();
        }
      }

      usedCtrls[it.id] = TextEditingController(text: initialUsed);
      countCtrls[it.id] = TextEditingController(text: initialCount);
      reasonCtrls[it.id] = TextEditingController(text: initialReason);
    }

    Future<void> persistLocalDraft() async {
      final prefs = _prefs;
      if (prefs == null) return;
      try {
        final draftData = {
          'stocktake_id': stocktake.id,
          'saved_at': DateTime.now().toIso8601String(),
          'used': {for (final it in items) it.id: usedCtrls[it.id]?.text.trim() ?? '0'},
          'counted': {for (final it in items) it.id: countCtrls[it.id]?.text.trim() ?? '0'},
          'reason': {for (final it in items) it.id: reasonCtrls[it.id]?.text.trim() ?? ''},
        };
        await prefs.setString('stocktake_draft_${stocktake.id}', jsonEncode(draftData));
      } catch (_) {}
    }

    await showDialog(
      context: context,
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, setDlgState) {
          return AlertDialog(
            shape:
                RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
            title: Row(
              children: [
                const Icon(Icons.fact_check, color: Color(0xFF0891B2)),
                const SizedBox(width: 8),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        '${stocktake.shiftCode == 'morning' ? 'Ca Sáng 07:30 – 15:00' : stocktake.shiftCode == 'afternoon' ? 'Ca Chiều 15:00 – 23:00' : stocktake.shiftCode == 'split' ? 'Ca Lỡ ngày 07:30 – 18:00' : 'Kiểm Kê Kho'}: $locName',
                        style: const TextStyle(
                            fontSize: 16, fontWeight: FontWeight.bold),
                      ),
                      Text(
                        'Trạng thái: ${stocktake.status == 'open' ? 'Đang kiểm đếm (Open)' : (stocktake.status == 'submitted' ? 'Chờ quản lý duyệt (Submitted)' : 'Đã đóng & Điều chỉnh (Closed)')}',
                        style: TextStyle(
                          fontSize: 12,
                          color: stocktake.status == 'open'
                              ? Colors.blue
                              : (stocktake.status == 'submitted'
                                  ? Colors.orange
                                  : Colors.green),
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                    ],
                  ),
                ),
                IconButton(
                  tooltip: 'In Phiếu Ca',
                  icon: const Icon(Icons.print_outlined, color: Color(0xFF0891B2)),
                  onPressed: () async {
                    await ReportShare.printPdf(
                      context,
                      filename:
                          'phieu_kiem_ke_${stocktake.shiftCode}_${stocktake.id.substring(0, 8)}.pdf',
                      build: () => _generateStocktakePdf(
                        stocktake,
                        items,
                        locName,
                        countCtrls,
                        usedCtrls,
                        reasonCtrls,
                      ),
                    );
                  },
                ),
              ],
            ),
            content: Builder(builder: (dialogCtx) {
              final isNarrow = MediaQuery.sizeOf(dialogCtx).width < 768;
              final draftBanner = hasRestoredDraft
                  ? Container(
                      padding: const EdgeInsets.all(10),
                      margin: const EdgeInsets.only(bottom: 12),
                      decoration: BoxDecoration(
                        color: const Color(0xFF0284C7).withValues(alpha: 0.12),
                        borderRadius: BorderRadius.circular(8),
                        border: Border.all(
                            color: const Color(0xFF0284C7).withValues(alpha: 0.3)),
                      ),
                      child: const Row(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Icon(
                            Icons.offline_pin_outlined,
                            color: Color(0xFF0284C7),
                            size: 18,
                          ),
                          SizedBox(width: 8),
                          Text(
                            'Đã khôi phục số liệu kiểm đếm từ bản nháp ngoại tuyến trên thiết bị.',
                            style: TextStyle(
                              fontWeight: FontWeight.w600,
                              fontSize: 12,
                              color: Color(0xFF0369A1),
                            ),
                          ),
                        ],
                      ),
                    )
                  : null;

              final lockedBanner = !canEdit
                  ? Container(
                      padding: const EdgeInsets.all(10),
                      margin: const EdgeInsets.only(bottom: 12),
                      decoration: BoxDecoration(
                        color: (stocktake.status == 'submitted'
                                ? Colors.orange
                                : Colors.green)
                            .withValues(alpha: 0.12),
                        borderRadius: BorderRadius.circular(8),
                        border: Border.all(
                            color: (stocktake.status == 'submitted'
                                    ? Colors.orange
                                    : Colors.green)
                                .withValues(alpha: 0.3)),
                      ),
                      child: Row(
                        children: [
                          Icon(
                            stocktake.status == 'submitted'
                                ? Icons.hourglass_top
                                : Icons.lock_outline,
                            color: stocktake.status == 'submitted'
                                ? Colors.orange[800]
                                : Colors.green[800],
                            size: 18,
                          ),
                          const SizedBox(width: 8),
                          Expanded(
                            child: Text(
                              stocktake.status == 'submitted'
                                  ? 'Ca kiểm kê đang chờ quản lý phê duyệt. Dữ liệu đã khóa để đảm bảo tính toàn vẹn.'
                                  : 'Phiên kiểm kê đã đóng sổ & đối soát hoàn tất.',
                              style: TextStyle(
                                fontWeight: FontWeight.w600,
                                color: stocktake.status == 'submitted'
                                    ? Colors.orange[900]
                                    : Colors.green[900],
                                fontSize: 12.5,
                              ),
                            ),
                          ),
                        ],
                      ),
                    )
                  : null;

              final noteWidget = (stocktake.note != null && stocktake.note!.isNotEmpty)
                  ? Padding(
                      padding: const EdgeInsets.only(bottom: 12),
                      child: Text('Ghi chú: ${stocktake.note}',
                          style: const TextStyle(fontStyle: FontStyle.italic)),
                    )
                  : null;

              final formulaWidget = Padding(
                padding: const EdgeInsets.only(bottom: 12),
                child: Text(
                  'Công thức SRS: Còn lại cuối ca = Tồn đầu ca + Nhập − Sử dụng. Độ lệch = Kiểm thực tế − Còn lại cuối ca.',
                  style: TextStyle(
                      fontSize: 12,
                      fontWeight: FontWeight.w600,
                      color: Theme.of(context).colorScheme.primary),
                ),
              );

              final adjustmentWidget = stocktake.adjustmentRequestId != null
                  ? Container(
                      padding: const EdgeInsets.all(10),
                      margin: const EdgeInsets.only(bottom: 12),
                      decoration: BoxDecoration(
                        color: Colors.green.withValues(alpha: 0.1),
                        borderRadius: BorderRadius.circular(8),
                        border: Border.all(color: Colors.green.withValues(alpha: 0.3)),
                      ),
                      child: Row(
                        children: [
                          const Icon(Icons.check_circle, color: Colors.green, size: 18),
                          const SizedBox(width: 8),
                          Expanded(
                            child: Text(
                              'Đã sinh phiếu điều chỉnh kho tự động: #${stocktake.adjustmentRequestId}',
                              style: const TextStyle(
                                  fontWeight: FontWeight.w600,
                                  color: Colors.green,
                                  fontSize: 13),
                            ),
                          ),
                        ],
                      ),
                    )
                  : null;

              if (isNarrow) {
                return SizedBox(
                  width: double.maxFinite,
                  height: 520,
                  child: ListView(
                    children: [
                      if (draftBanner != null) draftBanner,
                      if (lockedBanner != null) lockedBanner,
                      if (noteWidget != null) noteWidget,
                      formulaWidget,
                      if (adjustmentWidget != null) adjustmentWidget,
                      for (var idx = 0; idx < items.length; idx++) ...[
                        _buildStocktakeMobileCard(
                          index: idx,
                          stocktake: stocktake,
                          item: items[idx],
                          canEdit: canEdit,
                          usedCtrl: usedCtrls[items[idx].id]!,
                          countCtrl: countCtrls[items[idx].id]!,
                          reasonCtrl: reasonCtrls[items[idx].id]!,
                          stockLevels: stockLevels,
                          onChanged: () {
                            persistLocalDraft();
                            setDlgState(() {});
                          },
                          theme: Theme.of(context),
                          isDark: Theme.of(context).brightness == Brightness.dark,
                        ),
                        const SizedBox(height: 10),
                      ],
                    ],
                  ),
                );
              }

              return SizedBox(
                width: 1100,
                height: 520,
                child: SingleChildScrollView(
                  scrollDirection: Axis.vertical,
                  child: SingleChildScrollView(
                    scrollDirection: Axis.horizontal,
                    child: ConstrainedBox(
                      constraints: const BoxConstraints(minWidth: 1050),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          if (draftBanner != null) draftBanner,
                          if (lockedBanner != null) lockedBanner,
                          if (noteWidget != null) noteWidget,
                          formulaWidget,
                          if (adjustmentWidget != null) adjustmentWidget,
                          Table(
                            columnWidths: const {
                              0: FixedColumnWidth(45), // STT
                              1: FixedColumnWidth(175), // Nguyên liệu
                              2: FixedColumnWidth(65), // ĐVT
                              3: FixedColumnWidth(80), // Tồn đầu
                              4: FixedColumnWidth(70), // Nhập
                              5: FixedColumnWidth(140), // Sử dụng (+/-)
                              6: FixedColumnWidth(95), // Còn lại cuối ca
                              7: FixedColumnWidth(140), // Kiểm thực tế (+/-)
                              8: FixedColumnWidth(85), // Độ lệch
                              9: FixedColumnWidth(155), // Trạng thái & Lý do
                            },
                            border: TableBorder.all(
                                color: Colors.grey.withValues(alpha: 0.2)),
                            children: [
                              TableRow(
                                decoration: BoxDecoration(
                                    color: Colors.grey.withValues(alpha: 0.1)),
                                children: const [
                                  Padding(
                                      padding: EdgeInsets.all(8),
                                      child: Text('STT',
                                          textAlign: TextAlign.center,
                                          style: TextStyle(
                                              fontWeight: FontWeight.bold,
                                              fontSize: 12))),
                                  Padding(
                                      padding: EdgeInsets.all(8),
                                      child: Text('Nguyên liệu',
                                          style: TextStyle(
                                              fontWeight: FontWeight.bold,
                                              fontSize: 12))),
                                  Padding(
                                      padding: EdgeInsets.all(8),
                                      child: Text('ĐVT',
                                          textAlign: TextAlign.center,
                                          style: TextStyle(
                                              fontWeight: FontWeight.bold,
                                              fontSize: 12))),
                                  Padding(
                                      padding: EdgeInsets.all(8),
                                      child: Text('Tồn đầu',
                                          textAlign: TextAlign.right,
                                          style: TextStyle(
                                              fontWeight: FontWeight.bold,
                                              fontSize: 12))),
                                  Padding(
                                      padding: EdgeInsets.all(8),
                                      child: Text('Nhập',
                                          textAlign: TextAlign.right,
                                          style: TextStyle(
                                              fontWeight: FontWeight.bold,
                                              fontSize: 12))),
                                  Padding(
                                      padding: EdgeInsets.all(8),
                                      child: Text('Sử dụng (+/-)',
                                          textAlign: TextAlign.center,
                                          style: TextStyle(
                                              fontWeight: FontWeight.bold,
                                              fontSize: 12))),
                                  Padding(
                                      padding: EdgeInsets.all(8),
                                      child: Text('Còn lại',
                                          textAlign: TextAlign.right,
                                          style: TextStyle(
                                              fontWeight: FontWeight.bold,
                                              fontSize: 12))),
                                  Padding(
                                      padding: EdgeInsets.all(8),
                                      child: Text('Kiểm thực tế (+/-)',
                                          textAlign: TextAlign.center,
                                          style: TextStyle(
                                              fontWeight: FontWeight.bold,
                                              fontSize: 12))),
                                  Padding(
                                      padding: EdgeInsets.all(8),
                                      child: Text('Độ lệch',
                                          textAlign: TextAlign.right,
                                          style: TextStyle(
                                              fontWeight: FontWeight.bold,
                                              fontSize: 12))),
                                  Padding(
                                      padding: EdgeInsets.all(8),
                                      child: Text('Trạng thái & Lý do',
                                          style: TextStyle(
                                              fontWeight: FontWeight.bold,
                                              fontSize: 12))),
                                ],
                              ),
                              for (var idx = 0; idx < items.length; idx++)
                                _buildStocktakeRow(
                                  index: idx,
                                  stocktake: stocktake,
                                  item: items[idx],
                                  canEdit: canEdit,
                                  usedCtrl: usedCtrls[items[idx].id]!,
                                  countCtrl: countCtrls[items[idx].id]!,
                                  reasonCtrl: reasonCtrls[items[idx].id]!,
                                  stockLevels: stockLevels,
                                  onChanged: () {
                                    persistLocalDraft();
                                    setDlgState(() {});
                                  },
                                ),
                            ],
                          ),
                        ],
                      ),
                    ),
                  ),
                ),
              );
            }),
            actions: [
              TextButton(
                  onPressed: () => Navigator.of(ctx).pop(),
                  child: const Text('Đóng')),
              if (canEdit) ...[
                OutlinedButton(
                  onPressed: () async {
                    final messenger = ScaffoldMessenger.of(context);
                    final navigator = Navigator.of(ctx);
                    final repo = RepositoryScope.of(context);
                    await persistLocalDraft();
                    final linesPayload = items.map((it) {
                      final existingLine = stocktake.lines
                          .cast<StocktakeLineItem?>()
                          .firstWhere(
                            (l) => l?.itemId == it.id,
                            orElse: () => null,
                          );
                      final opening = double.tryParse(existingLine?.openingQty ?? '') ??
                          (double.tryParse(existingLine?.bookQty ?? '') ?? 0.0);
                      final received = double.tryParse(existingLine?.receivedQty ?? '') ?? 0.0;
                      final used = double.tryParse(usedCtrls[it.id]?.text.trim() ?? '0') ?? 0.0;
                      final counted = double.tryParse(countCtrls[it.id]?.text.trim() ?? '0') ?? 0.0;
                      return {
                        'item_id': it.id,
                        'opening_qty': opening.toString(),
                        'received_qty': received.toString(),
                        'used_qty': used.toString(),
                        'counted_qty': counted.toString(),
                        'reason': reasonCtrls[it.id]?.text.trim() ?? '',
                      };
                    }).toList();
                    try {
                      final synced = await _queueStocktake(repo, 'submit_lines', {
                        'stocktake_id': stocktake.id,
                        'lines': linesPayload,
                        'expected_version': stocktake.version,
                      }, '${stocktake.id}-${DateTime.now().microsecondsSinceEpoch}');
                      if (synced) {
                        await _prefs?.remove('stocktake_draft_${stocktake.id}');
                      }
                      OfflineHub.instance.addQueued();
                      if (mounted) {
                        messenger.showSnackBar(SnackBar(
                          content: Text(synced ? 'Đã lưu số kiểm đếm thực tế!'
                              : StocktakeOutbox.shared.hasConflict
                                  ? 'Dữ liệu trên máy chủ đã thay đổi. Cần xử lý xung đột kiểm kê.'
                                  : 'Số đếm đã lưu trên thiết bị và sẽ đồng bộ khi có mạng.'),
                          behavior: SnackBarBehavior.floating,
                        ));
                        navigator.pop();
                        _refresh();
                      }
                    } catch (e) {
                      if (mounted) {
                        messenger.showSnackBar(SnackBar(
                          content: Text('Không lưu được số đếm: ${friendlyError(e)}'),
                          backgroundColor: Colors.red,
                        ));
                      }
                    }
                  },
                  child: const Text('Lưu Số Đếm'),
                ),
                FilledButton(
                  style: FilledButton.styleFrom(
                      backgroundColor: const Color(0xFF2563EB)),
                  onPressed: () async {
                    final messenger = ScaffoldMessenger.of(context);
                    final navigator = Navigator.of(ctx);
                    final repo = RepositoryScope.of(context);
                    await persistLocalDraft();
                    final linesPayload = items.map((it) {
                      final existingLine = stocktake.lines
                          .cast<StocktakeLineItem?>()
                          .firstWhere(
                            (l) => l?.itemId == it.id,
                            orElse: () => null,
                          );
                      final opening = double.tryParse(existingLine?.openingQty ?? '') ??
                          (double.tryParse(existingLine?.bookQty ?? '') ?? 0.0);
                      final received = double.tryParse(existingLine?.receivedQty ?? '') ?? 0.0;
                      final used = double.tryParse(usedCtrls[it.id]?.text.trim() ?? '0') ?? 0.0;
                      final counted = double.tryParse(countCtrls[it.id]?.text.trim() ?? '0') ?? 0.0;
                      return {
                        'item_id': it.id,
                        'opening_qty': opening.toString(),
                        'received_qty': received.toString(),
                        'used_qty': used.toString(),
                        'counted_qty': counted.toString(),
                        'reason': reasonCtrls[it.id]?.text.trim() ?? '',
                      };
                    }).toList();
                    try {
                      final synced = await _queueStocktake(repo, 'submit_stocktake', {
                        'stocktake_id': stocktake.id,
                        'lines': linesPayload,
                        'expected_version': stocktake.version,
                      }, '${stocktake.id}-submit-${DateTime.now().microsecondsSinceEpoch}');
                      if (synced) {
                        await _prefs?.remove('stocktake_draft_${stocktake.id}');
                      }
                      OfflineHub.instance.addQueued();
                      if (mounted) {
                        messenger.showSnackBar(SnackBar(
                          content: Text(synced ? 'Đã gửi kiểm kê sang người phê duyệt!'
                              : StocktakeOutbox.shared.hasConflict
                                  ? 'Dữ liệu trên máy chủ đã thay đổi. Cần xử lý xung đột kiểm kê.'
                                  : 'Bản kiểm kê đã lưu trên thiết bị và sẽ đồng bộ khi có mạng.'),
                          behavior: SnackBarBehavior.floating,
                        ));
                        navigator.pop();
                        _refresh();
                      }
                    } catch (e) {
                      if (mounted) {
                        messenger.showSnackBar(SnackBar(
                          content: Text('Không lưu được bản kiểm kê: ${friendlyError(e)}'),
                          backgroundColor: Colors.red,
                        ));
                      }
                    }
                  },
                  child: const Text('Gửi Duyệt Đối Soát'),
                ),
              ],
              if (canApprove) ...[
                FilledButton(
                  style: FilledButton.styleFrom(
                      backgroundColor: const Color(0xFF059669)),
                  onPressed: () async {
                    final messenger = ScaffoldMessenger.of(context);
                    final navigator = Navigator.of(ctx);
                    try {
                      final repo = RepositoryScope.of(context);
                      await repo.approveStocktake(stocktake.id);
                      if (mounted) {
                        messenger.showSnackBar(
                          const SnackBar(
                            content: Text(
                                'Đã phê duyệt kiểm kê & tự động sinh phiếu điều chỉnh!'),
                            behavior: SnackBarBehavior.floating,
                            backgroundColor: Color(0xFF059669),
                          ),
                        );
                        navigator.pop();
                        _refresh();
                      }
                    } catch (e) {
                      if (mounted) {
                        messenger.showSnackBar(
                          SnackBar(
                              content: Text('Lỗi: ${friendlyError(e)}'),
                              backgroundColor: Colors.red),
                        );
                      }
                    }
                  },
                  child: const Text('Phê Duyệt & Sinh Phiếu Điều Chỉnh'),
                ),
              ],
            ],
          );
        },
      ),
    );
  }

  Future<List<int>> _generateStocktakePdf(
    StocktakeItem stocktake,
    List<InventoryItem> items,
    String locName,
    Map<String, TextEditingController> countCtrls,
    Map<String, TextEditingController> usedCtrls,
    Map<String, TextEditingController> reasonCtrls,
  ) async {
    final doc = pw.Document();
    pw.Font? font;
    try {
      font = pw.Font.ttf(await rootBundle.load('assets/fonts/Roboto-Regular.ttf'));
    } catch (_) {}

    final shiftTitle = stocktake.shiftCode == 'morning'
        ? 'Ca Sáng (07:30 - 15:00)'
        : (stocktake.shiftCode == 'afternoon'
            ? 'Ca Chiều (15:00 - 23:00)'
            : (stocktake.shiftCode == 'split' ? 'Ca Lỡ (07:30 - 18:00)' : 'Kiểm Kê Kho'));

    doc.addPage(
      pw.MultiPage(
        pageFormat: PdfPageFormat.a4,
        margin: const pw.EdgeInsets.all(28),
        theme: font != null ? pw.ThemeData.withFont(base: font, bold: font) : null,
        build: (pw.Context context) {
          return [
            pw.Header(
              level: 0,
              child: pw.Row(
                mainAxisAlignment: pw.MainAxisAlignment.spaceBetween,
                children: [
                  pw.Column(
                    crossAxisAlignment: pw.CrossAxisAlignment.start,
                    children: [
                      pw.Text('KHO TRÀ SỮA · BIÊN BẢN KIỂM KÊ THEO CA',
                          style: pw.TextStyle(fontSize: 16, fontWeight: pw.FontWeight.bold)),
                      pw.SizedBox(height: 4),
                      pw.Text('$shiftTitle | Vị trí: $locName',
                          style: const pw.TextStyle(fontSize: 11, color: PdfColors.grey700)),
                    ],
                  ),
                  pw.Column(
                    crossAxisAlignment: pw.CrossAxisAlignment.end,
                    children: [
                      pw.Text(
                          'Mã: ${stocktake.id.length >= 8 ? stocktake.id.substring(0, 8).toUpperCase() : stocktake.id}',
                          style: pw.TextStyle(fontSize: 10, fontWeight: pw.FontWeight.bold)),
                      pw.Text('Trạng thái: ${stocktake.status.toUpperCase()}',
                          style: const pw.TextStyle(fontSize: 9, color: PdfColors.grey600)),
                    ],
                  ),
                ],
              ),
            ),
            pw.SizedBox(height: 12),
            pw.TableHelper.fromTextArray(
              headers: [
                'STT',
                'Nguyên liệu',
                'ĐVT',
                'Tồn đầu',
                'Nhập',
                'Sử dụng',
                'Còn lại',
                'Kiểm thực tế',
                'Độ lệch',
                'Ghi chú'
              ],
              headerStyle: pw.TextStyle(fontSize: 9, fontWeight: pw.FontWeight.bold),
              cellStyle: const pw.TextStyle(fontSize: 8),
              headerDecoration: const pw.BoxDecoration(color: PdfColors.grey200),
              data: [
                for (var i = 0; i < items.length; i++) ...[
                  () {
                    final it = items[i];
                    final existingLine = stocktake.lines.cast<StocktakeLineItem?>().firstWhere(
                          (l) => l?.itemId == it.id,
                          orElse: () => null,
                        );
                    final opening = double.tryParse(existingLine?.openingQty ?? '') ??
                        (double.tryParse(existingLine?.bookQty ?? '') ?? 0.0);
                    final received = double.tryParse(existingLine?.receivedQty ?? '') ?? 0.0;
                    final used = double.tryParse(usedCtrls[it.id]?.text.trim() ?? '0') ?? 0.0;
                    final counted = double.tryParse(countCtrls[it.id]?.text.trim() ?? '0') ?? 0.0;
                    final theoretical = opening + received - used;
                    final variance = counted - theoretical;
                    final reason = reasonCtrls[it.id]?.text.trim() ?? '';
                    return [
                      '${i + 1}',
                      it.name,
                      it.unit,
                      opening.toStringAsFixed(1),
                      received.toStringAsFixed(1),
                      used.toStringAsFixed(1),
                      theoretical.toStringAsFixed(1),
                      counted.toStringAsFixed(1),
                      variance == 0
                          ? '0'
                          : (variance > 0
                              ? '+${variance.toStringAsFixed(1)}'
                              : variance.toStringAsFixed(1)),
                      reason,
                    ];
                  }(),
                ],
              ],
            ),
            pw.SizedBox(height: 24),
            pw.Row(
              mainAxisAlignment: pw.MainAxisAlignment.spaceAround,
              children: [
                pw.Column(
                  children: [
                    pw.Text('NGƯỜI KIỂM KÊ (TRƯỞNG CA)',
                        style: pw.TextStyle(fontWeight: pw.FontWeight.bold, fontSize: 10)),
                    pw.SizedBox(height: 35),
                    pw.Text('(Ký và ghi rõ họ tên)',
                        style: const pw.TextStyle(fontSize: 8, color: PdfColors.grey600)),
                  ],
                ),
                pw.Column(
                  children: [
                    pw.Text('QUẢN LÝ CỬA HÀNG / CHỦ QUÁN',
                        style: pw.TextStyle(fontWeight: pw.FontWeight.bold, fontSize: 10)),
                    pw.SizedBox(height: 35),
                    pw.Text('(Ký duyệt đối soát)',
                        style: const pw.TextStyle(fontSize: 8, color: PdfColors.grey600)),
                  ],
                ),
              ],
            ),
          ];
        },
      ),
    );

    return doc.save();
  }

  TableRow _buildStocktakeRow({
    required int index,
    required StocktakeItem stocktake,
    required InventoryItem item,
    required bool canEdit,
    required TextEditingController usedCtrl,
    required TextEditingController countCtrl,
    required TextEditingController reasonCtrl,
    List<StockLevelItem>? stockLevels,
    required VoidCallback onChanged,
  }) {
    final line = stocktake.lines.cast<StocktakeLineItem?>().firstWhere(
          (l) => l?.itemId == item.id,
          orElse: () => null,
        );
    final opening = double.tryParse(line?.openingQty ?? '') ??
        (double.tryParse(line?.bookQty ?? '') ?? 0.0);
    final received = double.tryParse(line?.receivedQty ?? '') ?? 0.0;
    final used = double.tryParse(usedCtrl.text.trim()) ?? 0.0;
    final remaining = opening + received - used;
    final counted = double.tryParse(countCtrl.text.trim()) ?? 0.0;
    final diff = counted - remaining;

    Color diffColor = Colors.grey;
    if (diff > 0.001) diffColor = const Color(0xFF15803D);
    if (diff < -0.001) diffColor = const Color(0xFFDC2626);

    final statusText = diff.abs() < 0.001
        ? '🟢 Khớp'
        : (diff > 0 ? '🟡 Thừa' : '🔴 Thiếu');
    final statusColor = diff.abs() < 0.001
        ? const Color(0xFF15803D)
        : (diff > 0 ? const Color(0xFFB45309) : const Color(0xFFDC2626));
    final statusBg = statusColor.withValues(alpha: 0.12);

    final stockLevel = stockLevels?.cast<StockLevelItem?>().firstWhere(
          (sl) => sl?.itemId == item.id,
          orElse: () => null,
        );
    final minQty = double.tryParse(stockLevel?.minQty ?? '') ?? 0.0;
    final isLowStock = minQty > 0 && counted <= minQty;

    String formatQty(double val) =>
        val == val.roundToDouble() ? val.toInt().toString() : val.toStringAsFixed(1);

    return TableRow(
      children: [
        // 0: STT
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 8),
          child: Text(
            '${index + 1}',
            textAlign: TextAlign.center,
            style: const TextStyle(fontSize: 12, color: Colors.grey),
          ),
        ),
        // 1: Nguyên liệu
        Padding(
          padding: const EdgeInsets.all(8),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(item.name,
                  style: const TextStyle(
                      fontWeight: FontWeight.w700, fontSize: 13)),
              Text(item.sku,
                  style: const TextStyle(color: Colors.grey, fontSize: 11)),
            ],
          ),
        ),
        // 2: ĐVT
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 8),
          child: Text(
            item.unit,
            textAlign: TextAlign.center,
            style: const TextStyle(fontSize: 12),
          ),
        ),
        // 3: Tồn đầu
        Padding(
          padding: const EdgeInsets.all(8),
          child: Text(
            formatQty(opening),
            textAlign: TextAlign.right,
            style: const TextStyle(fontSize: 12.5, fontWeight: FontWeight.w600),
          ),
        ),
        // 4: Nhập
        Padding(
          padding: const EdgeInsets.all(8),
          child: Text(
            formatQty(received),
            textAlign: TextAlign.right,
            style: const TextStyle(fontSize: 12.5, fontWeight: FontWeight.w600),
          ),
        ),
        // 5: Sử dụng (+/-)
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 4),
          child: _buildQtyTouchField(
            controller: usedCtrl,
            canEdit: canEdit,
            onChanged: onChanged,
          ),
        ),
        // 6: Còn lại cuối ca
        Padding(
          padding: const EdgeInsets.all(8),
          child: Text(
            formatQty(remaining),
            textAlign: TextAlign.right,
            style: const TextStyle(
              fontSize: 13,
              fontWeight: FontWeight.w800,
              color: Color(0xFF2563EB),
            ),
          ),
        ),
        // 7: Kiểm thực tế (+/-)
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 4),
          child: _buildQtyTouchField(
            controller: countCtrl,
            canEdit: canEdit,
            onChanged: onChanged,
          ),
        ),
        // 8: Độ lệch
        Padding(
          padding: const EdgeInsets.all(8),
          child: Text(
            '${diff > 0.001 ? "+" : ""}${formatQty(diff)}',
            textAlign: TextAlign.right,
            style: TextStyle(
                fontWeight: FontWeight.w800, color: diffColor, fontSize: 13),
          ),
        ),
        // 9: Trạng thái & Lý do
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 4),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                    decoration: BoxDecoration(
                      color: statusBg,
                      borderRadius: BorderRadius.circular(4),
                    ),
                    child: Text(
                      statusText,
                      style: TextStyle(
                        color: statusColor,
                        fontSize: 10.5,
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                  ),
                  if (isLowStock) ...[
                    const SizedBox(width: 4),
                    Container(
                      padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 2),
                      decoration: BoxDecoration(
                        color: const Color(0xFFDC2626).withValues(alpha: 0.15),
                        borderRadius: BorderRadius.circular(4),
                      ),
                      child: const Text(
                        '≤ Min',
                        style: TextStyle(
                          color: Color(0xFFDC2626),
                          fontSize: 9.5,
                          fontWeight: FontWeight.bold,
                        ),
                      ),
                    ),
                  ],
                ],
              ),
              const SizedBox(height: 4),
              if (canEdit)
                SizedBox(
                  height: 32,
                  child: TextField(
                    controller: reasonCtrl,
                    style: const TextStyle(fontSize: 11),
                    decoration: const InputDecoration(
                      hintText: 'Lý do lệch...',
                      contentPadding:
                          EdgeInsets.symmetric(horizontal: 6, vertical: 4),
                      border: OutlineInputBorder(),
                      isDense: true,
                    ),
                  ),
                )
              else
                Text(
                  reasonCtrl.text.isNotEmpty ? reasonCtrl.text : '—',
                  style: const TextStyle(fontSize: 11, fontStyle: FontStyle.italic),
                ),
            ],
          ),
        ),
      ],
    );
  }

  Widget _buildMetricCol(String label, String value, {Color? color}) {
    return Column(
      children: [
        Text(label,
            style: const TextStyle(fontSize: 10.5, color: Colors.grey)),
        const SizedBox(height: 2),
        Text(
          value,
          style: TextStyle(
            fontSize: 12.5,
            fontWeight: FontWeight.w700,
            color: color,
          ),
        ),
      ],
    );
  }

  Widget _buildStocktakeMobileCard({
    required int index,
    required StocktakeItem stocktake,
    required InventoryItem item,
    required bool canEdit,
    required TextEditingController usedCtrl,
    required TextEditingController countCtrl,
    required TextEditingController reasonCtrl,
    List<StockLevelItem>? stockLevels,
    required VoidCallback onChanged,
    required ThemeData theme,
    required bool isDark,
  }) {
    final line = stocktake.lines.cast<StocktakeLineItem?>().firstWhere(
          (l) => l?.itemId == item.id,
          orElse: () => null,
        );
    final opening = double.tryParse(line?.openingQty ?? '') ??
        (double.tryParse(line?.bookQty ?? '') ?? 0.0);
    final received = double.tryParse(line?.receivedQty ?? '') ?? 0.0;
    final used = double.tryParse(usedCtrl.text.trim()) ?? 0.0;
    final remaining = opening + received - used;
    final counted = double.tryParse(countCtrl.text.trim()) ?? 0.0;
    final diff = counted - remaining;

    String formatQty(double val) => val == val.roundToDouble()
        ? val.toInt().toString()
        : val.toStringAsFixed(1);

    final statusText = diff.abs() < 0.001
        ? '🟢 Khớp'
        : (diff > 0
            ? '🟡 Thừa: +${formatQty(diff)}'
            : '🔴 Thiếu: ${formatQty(diff)}');
    final statusColor = diff.abs() < 0.001
        ? const Color(0xFF15803D)
        : (diff > 0 ? const Color(0xFFB45309) : const Color(0xFFDC2626));
    final statusBg = statusColor.withValues(alpha: 0.12);

    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: isDark ? const Color(0xFF1E293B) : Colors.white,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: Colors.grey.withValues(alpha: 0.2)),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.03),
            blurRadius: 4,
            offset: const Offset(0, 2),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                decoration: BoxDecoration(
                  color: theme.colorScheme.primary.withValues(alpha: 0.1),
                  borderRadius: BorderRadius.circular(4),
                ),
                child: Text(
                  '#${index + 1}',
                  style: TextStyle(
                    fontSize: 11,
                    fontWeight: FontWeight.bold,
                    color: theme.colorScheme.primary,
                  ),
                ),
              ),
              const SizedBox(width: 8),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      item.name,
                      style: const TextStyle(
                          fontWeight: FontWeight.w700, fontSize: 13.5),
                    ),
                    Text(
                      item.sku,
                      style: const TextStyle(color: Colors.grey, fontSize: 11),
                    ),
                  ],
                ),
              ),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                decoration: BoxDecoration(
                  color: Colors.grey.withValues(alpha: 0.12),
                  borderRadius: BorderRadius.circular(6),
                ),
                child: Text(
                  item.unit,
                  style: const TextStyle(
                      fontSize: 11, fontWeight: FontWeight.w600),
                ),
              ),
            ],
          ),
          const SizedBox(height: 10),
          Container(
            padding: const EdgeInsets.all(8),
            decoration: BoxDecoration(
              color: isDark ? const Color(0xFF0F172A) : const Color(0xFFF8FAFC),
              borderRadius: BorderRadius.circular(8),
            ),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.spaceAround,
              children: [
                _buildMetricCol('Tồn đầu', formatQty(opening)),
                _buildMetricCol('Nhập', formatQty(received)),
                canEdit
                    ? Column(
                        children: [
                          const Text('Sử dụng',
                              style:
                                  TextStyle(fontSize: 10, color: Colors.grey)),
                          const SizedBox(height: 2),
                          _buildQtyTouchField(
                            controller: usedCtrl,
                            canEdit: canEdit,
                            onChanged: onChanged,
                            itemName: item.name,
                            fieldLabel: 'Sử dụng',
                          ),
                        ],
                      )
                    : _buildMetricCol('Sử dụng', formatQty(used)),
                _buildMetricCol('Còn lại', formatQty(remaining),
                    color: const Color(0xFF2563EB)),
              ],
            ),
          ),
          const SizedBox(height: 10),
          Row(
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      'Kiểm thực tế (${item.unit}):',
                      style: const TextStyle(
                          fontSize: 12, fontWeight: FontWeight.bold),
                    ),
                    const SizedBox(height: 4),
                    _buildQtyTouchField(
                      controller: countCtrl,
                      canEdit: canEdit,
                      onChanged: onChanged,
                      itemName: item.name,
                      fieldLabel: 'Kiểm thực tế',
                      isProminent: true,
                    ),
                  ],
                ),
              ),
              const SizedBox(width: 12),
              Column(
                crossAxisAlignment: CrossAxisAlignment.end,
                children: [
                  const Text('Độ lệch:',
                      style: TextStyle(fontSize: 11, color: Colors.grey)),
                  const SizedBox(height: 4),
                  Container(
                    padding: const EdgeInsets.symmetric(
                        horizontal: 8, vertical: 4),
                    decoration: BoxDecoration(
                      color: statusBg,
                      borderRadius: BorderRadius.circular(6),
                    ),
                    child: Text(
                      statusText,
                      style: TextStyle(
                        color: statusColor,
                        fontWeight: FontWeight.bold,
                        fontSize: 12,
                      ),
                    ),
                  ),
                ],
              ),
            ],
          ),
          if (canEdit && diff.abs() > 0.001) ...[
            const SizedBox(height: 8),
            TextField(
              controller: reasonCtrl,
              style: const TextStyle(fontSize: 12),
              decoration: InputDecoration(
                labelText: 'Lý do chênh lệch (${item.name})',
                hintText: 'Nhập nguyên nhân thừa/thiếu...',
                contentPadding:
                    const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
                border: const OutlineInputBorder(),
                isDense: true,
              ),
            ),
          ],
        ],
      ),
    );
  }

  Widget _buildQtyTouchField({
    required TextEditingController controller,
    required bool canEdit,
    required VoidCallback onChanged,
    String? itemName,
    String? fieldLabel,
    bool isProminent = false,
  }) {
    if (!canEdit) {
      return Center(
        child: Text(
          controller.text.isEmpty ? '0' : controller.text,
          style: const TextStyle(fontSize: 13, fontWeight: FontWeight.bold),
        ),
      );
    }
    final name = itemName ?? 'nguyên liệu';
    final label = fieldLabel ?? 'Số lượng';
    final buttonPadding = isProminent ? 8.0 : 4.0;
    final iconSize = isProminent ? 18.0 : 13.0;
    final boxWidth = isProminent ? 64.0 : 48.0;
    final boxHeight = isProminent ? 38.0 : 32.0;

    return Row(
      mainAxisSize: MainAxisSize.min,
      mainAxisAlignment: MainAxisAlignment.center,
      children: [
        Semantics(
          label: 'Giảm $label cho $name',
          button: true,
          child: Tooltip(
            message: 'Giảm 1 ($name)',
            child: InkWell(
              onTap: () {
                final cur = double.tryParse(controller.text.trim()) ?? 0.0;
                if (cur > 0) {
                  final next = cur - 1;
                  controller.text = next == next.roundToDouble()
                      ? next.toInt().toString()
                      : next.toStringAsFixed(1);
                  onChanged();
                }
              },
              borderRadius: BorderRadius.circular(6),
              child: Container(
                padding: EdgeInsets.all(buttonPadding),
                decoration: BoxDecoration(
                  border: Border.all(color: Colors.grey.withValues(alpha: 0.4)),
                  borderRadius: BorderRadius.circular(6),
                ),
                child: Icon(Icons.remove, size: iconSize),
              ),
            ),
          ),
        ),
        const SizedBox(width: 4),
        SizedBox(
          width: boxWidth,
          height: boxHeight,
          child: Semantics(
            label: '$label cho $name',
            child: TextField(
              controller: controller,
              keyboardType: const TextInputType.numberWithOptions(decimal: true),
              textAlign: TextAlign.center,
              style: TextStyle(
                fontSize: isProminent ? 14 : 12,
                fontWeight: FontWeight.w700,
              ),
              onChanged: (_) => onChanged(),
              decoration: InputDecoration(
                contentPadding: const EdgeInsets.symmetric(horizontal: 2, vertical: 4),
                border: const OutlineInputBorder(),
                isDense: true,
                hintText: '0',
                labelText: isProminent ? label : null,
              ),
            ),
          ),
        ),
        const SizedBox(width: 4),
        Semantics(
          label: 'Tăng $label cho $name',
          button: true,
          child: Tooltip(
            message: 'Tăng 1 ($name)',
            child: InkWell(
              onTap: () {
                final cur = double.tryParse(controller.text.trim()) ?? 0.0;
                final next = cur + 1;
                controller.text = next == next.roundToDouble()
                    ? next.toInt().toString()
                    : next.toStringAsFixed(1);
                onChanged();
              },
              borderRadius: BorderRadius.circular(6),
              child: Container(
                padding: EdgeInsets.all(buttonPadding),
                decoration: BoxDecoration(
                  border: Border.all(color: Colors.grey.withValues(alpha: 0.4)),
                  borderRadius: BorderRadius.circular(6),
                ),
                child: Icon(Icons.add, size: iconSize),
              ),
            ),
          ),
        ),
      ],
    );
  }

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<_InventoryData>(
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
        final sessionUser = SessionScope.maybeOf(context)?.user;
        final userRoles = RoleVisibility.rolesOf(sessionUser);
        final canManageCatalog = RoleVisibility.canManageCatalog(userRoles);
        final isAdmin = RoleVisibility.isAdminUser(sessionUser);
        final theme = Theme.of(context);
        final isDark = theme.brightness == Brightness.dark;

        final totalQuantity = data.balances.fold<double>(
          0,
          (sum, b) => sum + (double.tryParse(b.quantity) ?? 0),
        );

        final isShiftOnly = widget.mode == InventoryTabMode.shiftWork;
        final isStockOnly = widget.mode == InventoryTabMode.stock;

        final headerTitle = isShiftOnly
            ? context.tr('inventory_title_shift')
            : context.tr('inventory_title_stock');
        final headerSubtitle = isShiftOnly
            ? context.tr('inventory_subtitle_shift')
            : context.tr('inventory_subtitle_stock');

        final headerActions = <Widget>[
          if (isShiftOnly)
            FilledButton.icon(
              key: const Key('btn-open-shift-stocktake'),
              onPressed: () => _showCreateStocktakeDialog(data.locations),
              icon: const Icon(Icons.add_task_rounded, size: 18),
              label: Text(context.tr('inventory_btn_new_stocktake')),
              style: FilledButton.styleFrom(
                backgroundColor: const Color(0xFF0891B2),
                shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(10)),
              ),
            )
          else ...[
            if (canManageCatalog) ...[
              OutlinedButton.icon(
                key: const Key('btn-add-item'),
                onPressed: () => _showCreateItemDialog(),
                icon: const Icon(Icons.add_box_outlined, size: 18),
                label: Text(context.tr('inventory_btn_add_item')),
                style: OutlinedButton.styleFrom(
                  shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(10)),
                ),
              ),
              OutlinedButton.icon(
                key: const Key('btn-import-items'),
                onPressed: () => _showImportItemsDialog(data.items),
                icon: const Icon(Icons.upload_file_outlined, size: 18),
                label: Text(context.tr('inventory_btn_import_items')),
                style: OutlinedButton.styleFrom(
                  foregroundColor: const Color(0xFF059669),
                  side: const BorderSide(color: Color(0xFF059669)),
                  shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(10)),
                ),
              ),
            ],
            FilledButton.icon(
              key: const Key('btn-create-stock-request'),
              onPressed: () {
                if (widget.onCreateStockRequest != null) {
                  widget.onCreateStockRequest!();
                } else if (widget.onNavigate != null) {
                  widget.onNavigate!(3);
                }
              },
              icon: const Icon(Icons.add, size: 18),
              label: Text(context.tr('inventory_btn_create_stock_req')),
              style: FilledButton.styleFrom(
                backgroundColor: const Color(0xFF2563EB),
                shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(10)),
              ),
            ),
          ],
        ];

        final List<Widget> kpiCards;
        if (isShiftOnly) {
          final pendingCount = data.stocktakes
              .where((s) => s.status == 'submitted' || s.status == 'open')
              .length;
          final approvedCount = data.stocktakes
              .where((s) =>
                  s.status == 'approved' ||
                  s.status == 'completed' ||
                  s.status == 'closed')
              .length;
          final discrepancyCount = data.stocktakes
              .where((s) =>
                  s.discrepancyCount > 0 ||
                  (s.note?.toLowerCase().contains('lệch') ?? false))
              .length;

          kpiCards = [
            _buildKpiCard(
              context,
              title: context.isVietnamese ? 'TỔNG ĐỢT' : 'TOTAL SESSIONS',
              value: '${data.stocktakes.length} ${context.isVietnamese ? 'đợt' : 'sessions'}',
              subtitle: context.isVietnamese
                  ? 'Đã lập trong hệ thống'
                  : 'Recorded in system',
              icon: Icons.checklist_rounded,
              color: const Color(0xFF0891B2),
              isSelected: _stocktakeStatusFilter == 'all',
              onTap: () => setState(() => _stocktakeStatusFilter = 'all'),
            ),
            _buildKpiCard(
              context,
              title: context.tr('inventory_kpi_shift_pending'),
              value: '$pendingCount ${context.isVietnamese ? 'phiếu' : 'vouchers'}',
              subtitle: context.isVietnamese
                  ? 'Chờ quản lý đối soát'
                  : 'Awaiting review',
              icon: Icons.pending_actions_rounded,
              color: const Color(0xFFF59E0B),
              isSelected: _stocktakeStatusFilter == 'pending',
              onTap: () => setState(() => _stocktakeStatusFilter = 'pending'),
            ),
            _buildKpiCard(
              context,
              title: context.tr('inventory_kpi_shift_approved'),
              value: '$approvedCount ${context.isVietnamese ? 'phiếu' : 'vouchers'}',
              subtitle: context.isVietnamese
                  ? 'Khớp số liệu tồn kho'
                  : 'Matched inventory balance',
              icon: Icons.verified_rounded,
              color: const Color(0xFF059669),
              isSelected: _stocktakeStatusFilter == 'approved',
              onTap: () => setState(() => _stocktakeStatusFilter = 'approved'),
            ),
            _buildKpiCard(
              context,
              title: context.tr('inventory_kpi_shift_discrepancy'),
              value: '$discrepancyCount ${context.isVietnamese ? 'ca' : 'shifts'}',
              subtitle: context.isVietnamese
                  ? 'Cần giải trình số liệu'
                  : 'Explanation required',
              icon: Icons.warning_amber_rounded,
              color: const Color(0xFFEF4444),
              isSelected: _stocktakeStatusFilter == 'discrepancy',
              onTap: () => setState(() => _stocktakeStatusFilter = 'discrepancy'),
            ),
          ];
        } else {
          double totalValuation = 0.0;
          for (final item in data.items) {
            final stock = _stockForItem(item.id, data.balances);
            final cost = item.costPrice ?? 0.0;
            totalValuation += stock * cost;
          }
          final lowStockCount = data.lowStockAlerts.length;

          kpiCards = [
            _buildKpiCard(
              context,
              title: context.tr('inventory_kpi_total_stock'),
              value: '${AppFormat.intFormat(totalQuantity.round())} ${context.isVietnamese ? 'đơn vị' : 'units'}',
              subtitle: context.isVietnamese
                  ? 'Định mức khả dụng an toàn'
                  : 'Safe stock quota',
              icon: Icons.inventory_2_rounded,
              color: const Color(0xFF2563EB),
            ),
            _buildKpiCard(
              context,
              title: context.tr('inventory_kpi_total_sku'),
              value: '${data.items.length} ${context.isVietnamese ? 'mặt hàng' : 'items'}',
              subtitle: context.isVietnamese
                  ? 'Đang quản lý trong kho'
                  : 'Active warehouse items',
              icon: Icons.category_rounded,
              color: const Color(0xFF0891B2),
            ),
            _buildKpiCard(
              context,
              title: context.tr('inventory_kpi_stock_alerts'),
              value: '$lowStockCount ${context.isVietnamese ? 'mặt hàng' : 'items'}',
              subtitle: lowStockCount > 0
                  ? (context.isVietnamese
                      ? 'Dưới định mức tối thiểu'
                      : 'Below safety threshold')
                  : (context.isVietnamese
                      ? 'Tất cả đạt định mức an toàn'
                      : 'All items at safe levels'),
              icon: lowStockCount > 0
                  ? Icons.warning_amber_rounded
                  : Icons.check_circle_outline_rounded,
              color: lowStockCount > 0
                  ? const Color(0xFFDC2626)
                  : const Color(0xFF059669),
            ),
            _buildKpiCard(
              context,
              title: context.tr('inventory_kpi_total_valuation'),
              value: isAdmin
                  ? AppFormat.money(totalValuation.toStringAsFixed(0), currency: '₫')
                  : '••••••',
              subtitle: isAdmin
                  ? (context.isVietnamese
                      ? 'Định giá vốn tồn hiện tại'
                      : 'Current inventory valuation')
                  : (context.isVietnamese
                      ? 'Bảo mật (Chỉ Admin)'
                      : 'Restricted (Admin only)'),
              icon: isAdmin
                  ? Icons.account_balance_wallet_rounded
                  : Icons.lock_outline_rounded,
              color: isAdmin ? const Color(0xFF059669) : Colors.grey,
            ),
          ];
        }

        Widget buildHeader(bool isCompact) {
          return isCompact
              ? Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      headerTitle,
                      style: theme.textTheme.headlineSmall?.copyWith(
                        fontWeight: FontWeight.w900,
                        letterSpacing: -0.5,
                      ),
                    ),
                    const SizedBox(height: 4),
                    Text(
                      headerSubtitle,
                      style: TextStyle(
                        color: theme.colorScheme.onSurfaceVariant,
                        fontSize: 13,
                      ),
                    ),
                    if (headerActions.isNotEmpty) ...[
                      const SizedBox(height: 14),
                      Wrap(
                        spacing: 10,
                        runSpacing: 8,
                        children: headerActions,
                      ),
                    ],
                  ],
                )
              : Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            headerTitle,
                            style: theme.textTheme.headlineSmall?.copyWith(
                              fontWeight: FontWeight.w900,
                              letterSpacing: -0.5,
                            ),
                          ),
                          const SizedBox(height: 4),
                          Text(
                            headerSubtitle,
                            style: TextStyle(
                              color: theme.colorScheme.onSurfaceVariant,
                              fontSize: 13,
                            ),
                          ),
                        ],
                      ),
                    ),
                    if (headerActions.isNotEmpty) ...[
                      const SizedBox(width: 16),
                      Wrap(
                        spacing: 10,
                        runSpacing: 8,
                        children: headerActions,
                      ),
                    ],
                  ],
                );
        }

        Widget buildKpis(bool isWideKpis) {
          return !isWideKpis
              ? Column(
                  children: [
                    IntrinsicHeight(
                      child: Row(
                        crossAxisAlignment: CrossAxisAlignment.stretch,
                        children: [
                          Expanded(child: kpiCards[0]),
                          const SizedBox(width: 12),
                          Expanded(child: kpiCards[1]),
                        ],
                      ),
                    ),
                    const SizedBox(height: 12),
                    IntrinsicHeight(
                      child: Row(
                        crossAxisAlignment: CrossAxisAlignment.stretch,
                        children: [
                          Expanded(child: kpiCards[2]),
                          const SizedBox(width: 12),
                          Expanded(child: kpiCards[3]),
                        ],
                      ),
                    ),
                  ],
                )
              : IntrinsicHeight(
                  child: Row(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      Expanded(child: kpiCards[0]),
                      const SizedBox(width: 14),
                      Expanded(child: kpiCards[1]),
                      const SizedBox(width: 14),
                      Expanded(child: kpiCards[2]),
                      const SizedBox(width: 14),
                      Expanded(child: kpiCards[3]),
                    ],
                  ),
                );
        }

        return RefreshIndicator(
          onRefresh: _refresh,
          child: LayoutBuilder(
            builder: (context, constraints) {
              final isCompact = constraints.maxWidth < 960;
              final isWideKpis = constraints.maxWidth >= 1080;

              return ListView(
                padding: const EdgeInsets.all(20),
                children: [
                  buildHeader(isCompact),
                  const SizedBox(height: 20),

              if (!isShiftOnly && data.lowStockAlerts.isNotEmpty) ...[
                _buildLowStockAlertBanner(context, data.lowStockAlerts),
                const SizedBox(height: 20),
              ],

              if (!isShiftOnly && data.expiryAlerts.isNotEmpty) ...[
                _buildExpiryAlertBanner(context, data.expiryAlerts),
                const SizedBox(height: 20),
              ],

                  buildKpis(isWideKpis),
                  const SizedBox(height: 24),

              if (!isShiftOnly) ...[
                Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    Expanded(
                      child: Text(
                        'Danh mục mặt hàng',
                        style: theme.textTheme.titleMedium
                            ?.copyWith(fontWeight: FontWeight.w700),
                      ),
                    ),
                    const SizedBox(width: 8),
                    if (canManageCatalog && data.items.isNotEmpty)
                      if (!_isSelectionMode)
                        OutlinedButton.icon(
                          key: const Key('btn-toggle-batch-select'),
                          icon: const Icon(Icons.checklist_rounded, size: 16),
                          label: const Text('Chọn nhiều'),
                          style: OutlinedButton.styleFrom(
                            visualDensity: VisualDensity.compact,
                            shape: RoundedRectangleBorder(
                              borderRadius: BorderRadius.circular(8),
                            ),
                          ),
                          onPressed: _toggleSelectionMode,
                        )
                      else
                        TextButton.icon(
                          key: const Key('btn-close-batch-select'),
                          icon: const Icon(Icons.close, size: 16),
                          label: const Text('Hủy chọn'),
                          style: TextButton.styleFrom(
                            visualDensity: VisualDensity.compact,
                          ),
                          onPressed: _toggleSelectionMode,
                        ),
                  ],
                ),
                const SizedBox(height: 8),

                if (_isSelectionMode && data.items.isNotEmpty) ...[
                  Container(
                    margin: const EdgeInsets.only(bottom: 12),
                    padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
                    decoration: BoxDecoration(
                      color: const Color(0xFF2563EB).withValues(alpha: 0.08),
                      borderRadius: BorderRadius.circular(12),
                      border: Border.all(
                        color: const Color(0xFF2563EB).withValues(alpha: 0.25),
                      ),
                    ),
                    child: Wrap(
                      spacing: 12,
                      runSpacing: 8,
                      alignment: WrapAlignment.spaceBetween,
                      crossAxisAlignment: WrapCrossAlignment.center,
                      children: [
                        Row(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            Checkbox(
                              key: const Key('checkbox-select-all'),
                              value: _selectedItemIds.length == data.items.length && data.items.isNotEmpty,
                              onChanged: (val) {
                                if (val == true) {
                                  _selectAllItems(data.items);
                                } else {
                                  _clearSelection();
                                }
                              },
                            ),
                            const SizedBox(width: 4),
                            Text(
                              'Đã chọn ${_selectedItemIds.length}/${data.items.length}',
                              style: const TextStyle(
                                fontWeight: FontWeight.w700,
                                fontSize: 13,
                              ),
                            ),
                          ],
                        ),
                        Wrap(
                          spacing: 8,
                          runSpacing: 6,
                          children: [
                            TextButton(
                              key: const Key('btn-select-all-items'),
                              onPressed: () => _selectAllItems(data.items),
                              child: const Text('Chọn tất cả', style: TextStyle(fontSize: 12.5)),
                            ),
                            TextButton(
                              key: const Key('btn-clear-selection'),
                              onPressed: _clearSelection,
                              child: const Text('Bỏ chọn', style: TextStyle(fontSize: 12.5)),
                            ),
                            FilledButton.icon(
                              key: const Key('btn-batch-delete-confirm'),
                              style: FilledButton.styleFrom(
                                backgroundColor: Colors.red,
                                visualDensity: VisualDensity.compact,
                                shape: RoundedRectangleBorder(
                                  borderRadius: BorderRadius.circular(8),
                                ),
                              ),
                              icon: const Icon(Icons.delete_outline, size: 16),
                              label: Text(
                                _selectedItemIds.isEmpty
                                    ? 'Xóa đã chọn'
                                    : 'Xóa (${_selectedItemIds.length})',
                                style: const TextStyle(fontWeight: FontWeight.bold),
                              ),
                              onPressed: _selectedItemIds.isEmpty
                                  ? null
                                  : () => _confirmDeleteItemsBatch(data.items, data.balances),
                            ),
                          ],
                        ),
                      ],
                    ),
                  ),
                ],

              if (data.items.isEmpty)
                Card(
                  child: Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 28),
                    child: Center(
                      child: Column(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Icon(
                            Icons.inventory_2_outlined,
                            size: 48,
                            color: theme.colorScheme.onSurfaceVariant.withValues(alpha: 0.5),
                          ),
                          const SizedBox(height: 12),
                          Text(
                            'Chưa có mặt hàng nào trong kho',
                            style: theme.textTheme.titleSmall?.copyWith(
                              fontWeight: FontWeight.w700,
                            ),
                          ),
                          const SizedBox(height: 6),
                          Text(
                            canManageCatalog
                                ? 'Bạn có thể import nhanh 19 mặt hàng mẫu chuẩn quán trà sữa hoặc thêm thủ công từng món.'
                                : 'Người quản lý kho có thể thêm mặt hàng hoặc import danh mục nguyên vật liệu.',
                            textAlign: TextAlign.center,
                            style: TextStyle(
                              fontSize: 13,
                              color: theme.colorScheme.onSurfaceVariant,
                            ),
                          ),
                          if (canManageCatalog) ...[
                            const SizedBox(height: 16),
                            Wrap(
                              spacing: 12,
                              runSpacing: 10,
                              alignment: WrapAlignment.center,
                              children: [
                                FilledButton.icon(
                                  key: const Key('btn-empty-import-sample'),
                                  onPressed: () => _showImportItemsDialog(data.items),
                                  icon: const Icon(Icons.download_for_offline_outlined, size: 18),
                                  label: const Text('Import 19 mẫu Trà Sữa / File'),
                                  style: FilledButton.styleFrom(
                                    backgroundColor: const Color(0xFF059669),
                                    shape: RoundedRectangleBorder(
                                      borderRadius: BorderRadius.circular(10),
                                    ),
                                  ),
                                ),
                                OutlinedButton.icon(
                                  key: const Key('btn-empty-add-item'),
                                  onPressed: () => _showCreateItemDialog(),
                                  icon: const Icon(Icons.add, size: 18),
                                  label: const Text('Thêm thủ công'),
                                  style: OutlinedButton.styleFrom(
                                    shape: RoundedRectangleBorder(
                                      borderRadius: BorderRadius.circular(10),
                                    ),
                                  ),
                                ),
                              ],
                            ),
                          ],
                        ],
                      ),
                    ),
                  ),
                )
              else ...[
                _buildGoogleSheetTable(
                  context,
                  data,
                  isAdmin: isAdmin,
                  canManageCatalog: canManageCatalog,
                  isCompact: isCompact,
                  theme: theme,
                  isDark: isDark,
                ),
                const SizedBox(height: 24),
              ],
            ],
            if (!isStockOnly) ...[
              _buildStocktakesSection(context, data),
            ],
          ],
        );
      },
    ),
  );
},
);
  }

  Widget _buildGoogleSheetTable(
    BuildContext context,
    _InventoryData data, {
    required bool isAdmin,
    required bool canManageCatalog,
    required bool isCompact,
    required ThemeData theme,
    required bool isDark,
  }) {
    // 1. Collect Categories
    final categories = <String>['Tất cả'];
    for (final it in data.items) {
      final c = it.category?.trim();
      if (c != null && c.isNotEmpty && !categories.contains(c)) {
        categories.add(c);
      }
    }

    // 2. Filter items
    final filteredItems = data.items.where((item) {
      if (_searchQuery.trim().isNotEmpty) {
        final q = _searchQuery.trim().toLowerCase();
        final matchName = item.name.toLowerCase().contains(q);
        final matchSku = item.sku.toLowerCase().contains(q);
        final matchCat = (item.category ?? '').toLowerCase().contains(q);
        if (!matchName && !matchSku && !matchCat) return false;
      }
      if (_selectedCategory != 'Tất cả') {
        if ((item.category ?? '') != _selectedCategory) return false;
      }
      final stock = _stockForItem(item.id, data.balances);
      final minStock = item.minStock ?? 0.0;
      if (_stockFilter == 'low' && (stock > minStock || stock == 0)) return false;
      if (_stockFilter == 'out' && stock > 0) return false;
      return true;
    }).toList();

    // Thanh công cụ tìm kiếm và bộ lọc kiểu Bảng Tính
    final filterBar = Container(
      margin: const EdgeInsets.only(bottom: 12),
      padding: EdgeInsets.symmetric(
        horizontal: isCompact ? 10 : 14,
        vertical: isCompact ? 8 : 10,
      ),
      decoration: BoxDecoration(
        color: isDark ? const Color(0xFF1E293B) : const Color(0xFFF8FAFC),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(
          color: isDark ? const Color(0xFF334155) : const Color(0xFFE2E8F0),
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            children: [
              Expanded(
                child: SizedBox(
                  height: 38,
                  child: TextField(
                    decoration: InputDecoration(
                      hintText: 'Tìm SKU, tên sản phẩm...',
                      hintStyle: TextStyle(
                        fontSize: 12.5,
                        color: isDark
                            ? const Color(0xFF94A3B8)
                            : const Color(0xFF64748B),
                      ),
                      prefixIcon: const Icon(Icons.search, size: 18),
                      suffixIcon: _searchQuery.isNotEmpty
                          ? IconButton(
                              icon: const Icon(Icons.clear, size: 16),
                              onPressed: () =>
                                  setState(() => _searchQuery = ''),
                            )
                          : null,
                      contentPadding: const EdgeInsets.symmetric(
                          horizontal: 10, vertical: 0),
                      border: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(8),
                        borderSide: BorderSide(
                          color: isDark
                              ? const Color(0xFF475569)
                              : const Color(0xFFCBD5E1),
                        ),
                      ),
                      enabledBorder: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(8),
                        borderSide: BorderSide(
                          color: isDark
                              ? const Color(0xFF334155)
                              : const Color(0xFFCBD5E1),
                        ),
                      ),
                    ),
                    onChanged: (val) => setState(() => _searchQuery = val),
                  ),
                ),
              ),
              const SizedBox(width: 8),
              Container(
                height: 38,
                padding: const EdgeInsets.symmetric(horizontal: 10),
                decoration: BoxDecoration(
                  color: isDark ? const Color(0xFF0F172A) : Colors.white,
                  borderRadius: BorderRadius.circular(8),
                  border: Border.all(
                    color: isDark
                        ? const Color(0xFF334155)
                        : const Color(0xFFCBD5E1),
                  ),
                ),
                child: DropdownButtonHideUnderline(
                  child: DropdownButton<String>(
                    value: categories.contains(_selectedCategory)
                        ? _selectedCategory
                        : 'Tất cả',
                    icon: const Icon(Icons.arrow_drop_down, size: 20),
                    style: TextStyle(
                      fontSize: 12.5,
                      fontWeight: FontWeight.w600,
                      color: isDark ? Colors.white : const Color(0xFF1E293B),
                    ),
                    dropdownColor:
                        isDark ? const Color(0xFF1E293B) : Colors.white,
                    items: categories.map((c) {
                      return DropdownMenuItem(
                        value: c,
                        child: Text(c == 'Tất cả'
                            ? (context.isVietnamese ? 'Tất cả nhóm' : 'All Categories')
                            : c),
                      );
                    }).toList(),
                    onChanged: (val) {
                      if (val != null) {
                        setState(() => _selectedCategory = val);
                      }
                    },
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 8),
          SingleChildScrollView(
            scrollDirection: Axis.horizontal,
            child: Row(
              children: [
                _buildFilterChip('all',
                    '${context.isVietnamese ? 'Tất cả' : 'All'} (${data.items.length})', isDark),
                const SizedBox(width: 6),
                _buildFilterChip(
                    'low',
                    context.isVietnamese ? 'Cảnh báo ít tồn' : 'Low Stock',
                    isDark,
                    color: const Color(0xFFD97706)),
                const SizedBox(width: 6),
                _buildFilterChip(
                    'out',
                    context.isVietnamese ? 'Hết hàng' : 'Out of Stock',
                    isDark,
                    color: const Color(0xFFEF4444)),
                if (isAdmin) ...[
                  const SizedBox(width: 8),
                  ActionChip(
                    avatar: Icon(
                      _revealPrices
                          ? Icons.visibility_outlined
                          : Icons.visibility_off_outlined,
                      size: 14,
                      color: _revealPrices ? const Color(0xFF0284C7) : null,
                    ),
                    label: Text(
                      _revealPrices
                          ? (context.isVietnamese ? 'Đang hiện giá' : 'Prices Visible')
                          : (context.isVietnamese ? 'Đang ẩn giá' : 'Prices Hidden'),
                      style: TextStyle(
                        fontSize: 11,
                        fontWeight: FontWeight.bold,
                        color: _revealPrices ? const Color(0xFF0284C7) : null,
                      ),
                    ),
                    onPressed: () => setState(() {
                      _revealPrices = !_revealPrices;
                    }),
                  ),
                ],
                if (isCompact) ...[
                  const SizedBox(width: 10),
                  ActionChip(
                    avatar: Icon(
                      _sheetViewMode == 'sheet'
                          ? Icons.view_agenda_outlined
                          : Icons.table_chart_outlined,
                      size: 14,
                    ),
                    label: Text(
                      _sheetViewMode == 'sheet'
                          ? (context.isVietnamese ? 'Xem dạng Thẻ' : 'Card View')
                          : (context.isVietnamese ? 'Bảng Google Sheets' : 'Google Sheets View'),
                      style: const TextStyle(fontSize: 11, fontWeight: FontWeight.bold),
                    ),
                    onPressed: () => setState(() {
                      _sheetViewMode = _sheetViewMode == 'sheet' ? 'list' : 'sheet';
                    }),
                  ),
                ],
              ],
            ),
          ),
        ],
      ),
    );

    final emptyFilterPlaceholder = Container(
      width: double.infinity,
      padding: const EdgeInsets.symmetric(vertical: 36),
      alignment: Alignment.center,
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(
            Icons.search_off_rounded,
            size: 36,
            color: isDark ? const Color(0xFF64748B) : const Color(0xFF94A3B8),
          ),
          const SizedBox(height: 8),
          Text(
            'Không tìm thấy mặt hàng nào phù hợp',
            style: TextStyle(
              fontWeight: FontWeight.w600,
              fontSize: 13,
              color: isDark ? const Color(0xFF94A3B8) : const Color(0xFF64748B),
            ),
          ),
          const SizedBox(height: 6),
          TextButton(
            onPressed: () => setState(() {
              _searchQuery = '';
              _selectedCategory = 'Tất cả';
              _stockFilter = 'all';
            }),
            child: const Text('Đặt lại bộ lọc'),
          ),
        ],
      ),
    );

    // Nếu màn hình di động (isCompact < 960px) VÀ người dùng chọn 'list': Hiển thị dạng thẻ
    if (isCompact && _sheetViewMode == 'list') {
      return Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          filterBar,
          if (filteredItems.isEmpty)
            emptyFilterPlaceholder
          else
            Card(
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(14),
                side: BorderSide(
                  color: isDark
                      ? const Color(0xFF334155)
                      : const Color(0xFFE2E8F0),
                ),
              ),
              child: ListView.separated(
                shrinkWrap: true,
                physics: const NeverScrollableScrollPhysics(),
                itemCount: filteredItems.length,
                separatorBuilder: (_, __) => Divider(
                  height: 1,
                  color: isDark
                      ? const Color(0xFF1E293B)
                      : const Color(0xFFF1F5F9),
                ),
                itemBuilder: (context, i) {
                  final item = filteredItems[i];
                  final stock = _stockForItem(item.id, data.balances);
                  final isSelected = _selectedItemIds.contains(item.id);
                  final isOutOfStock = stock <= 0;
                  final isLowStock = !isOutOfStock &&
                      item.minStock != null &&
                      stock <= item.minStock!;

                  return ListTile(
                    contentPadding:
                        const EdgeInsets.symmetric(horizontal: 14, vertical: 4),
                    leading: _isSelectionMode
                        ? Checkbox(
                            key: Key('checkbox-item-${item.sku}'),
                            value: isSelected,
                            onChanged: (_) => _toggleItemSelection(item.id),
                          )
                        : null,
                    onTap: _isSelectionMode
                        ? () => _toggleItemSelection(item.id)
                        : () => _showItemDetailSheet(context, item, data,
                            isAdmin: isAdmin),
                    title: Row(
                      children: [
                        Expanded(
                          child: Text(
                            item.name,
                            style: const TextStyle(
                                fontWeight: FontWeight.w700, fontSize: 13.5),
                          ),
                        ),
                        Container(
                          padding: const EdgeInsets.symmetric(
                              horizontal: 6, vertical: 1.5),
                          decoration: BoxDecoration(
                            color: isOutOfStock
                                ? (isDark
                                    ? const Color(0xFF451A1A)
                                    : const Color(0xFFFEE2E2))
                                : (isLowStock
                                    ? (isDark
                                        ? const Color(0xFF452205)
                                        : const Color(0xFFFEF3C7))
                                    : (isDark
                                        ? const Color(0xFF064E3B)
                                        : const Color(0xFFD1FAE5))),
                            borderRadius: BorderRadius.circular(4),
                          ),
                          child: Text(
                            isOutOfStock
                                ? 'Hết hàng'
                                : (isLowStock ? 'Sắp hết' : 'Đủ hàng'),
                            style: TextStyle(
                              fontSize: 10,
                              fontWeight: FontWeight.w700,
                              color: isOutOfStock
                                  ? const Color(0xFFEF4444)
                                  : (isLowStock
                                      ? const Color(0xFFD97706)
                                      : const Color(0xFF059669)),
                            ),
                          ),
                        ),
                      ],
                    ),
                    subtitle: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        const SizedBox(height: 2),
                        Text(
                          '${item.sku} · ${item.category ?? 'Chưa phân nhóm'} · ${item.unit}${item.packaging != null ? " · ${item.packaging}" : ""}',
                          style: TextStyle(
                              fontSize: 12,
                              color: theme.colorScheme.onSurfaceVariant),
                        ),
                        const SizedBox(height: 4),
                        Wrap(
                          spacing: 12,
                          runSpacing: 4,
                          crossAxisAlignment: WrapCrossAlignment.center,
                          children: [
                            Text(
                              'Tồn: ${AppFormat.number(stock.toString())} ${item.unit}',
                              style: TextStyle(
                                fontSize: 12,
                                fontWeight: FontWeight.w700,
                                color: isOutOfStock
                                    ? const Color(0xFFEF4444)
                                    : (isLowStock
                                        ? const Color(0xFFD97706)
                                        : const Color(0xFF059669)),
                              ),
                            ),
                            if (item.minStock != null)
                              Text(
                                'Min: ${AppFormat.number(item.minStock!.toString())}',
                                style: TextStyle(
                                    fontSize: 12,
                                    color: theme.colorScheme.onSurfaceVariant),
                              ),
                            Row(
                              mainAxisSize: MainAxisSize.min,
                              children: [
                                Text('Giá bán: ',
                                    style: TextStyle(
                                        fontSize: 12,
                                        color:
                                            theme.colorScheme.onSurfaceVariant)),
                                if (isAdmin && _revealPrices)
                                  Text(
                                    item.sellingPrice != null
                                        ? AppFormat.money(item.sellingPrice!.toStringAsFixed(0), currency: '₫')
                                        : '—',
                                    style: const TextStyle(
                                        fontSize: 12,
                                        fontWeight: FontWeight.w700,
                                        color: Color(0xFF0284C7)),
                                  )
                                else
                                  Tooltip(
                                    message: isAdmin
                                        ? 'Đang ẩn giá'
                                        : 'Chỉ Admin mới có quyền xem giá',
                                    child: Row(
                                      mainAxisSize: MainAxisSize.min,
                                      children: [
                                        Icon(Icons.lock_outline,
                                            size: 12,
                                            color: theme.colorScheme.outline),
                                        const SizedBox(width: 2),
                                        Text('••••••',
                                            style: TextStyle(
                                                fontSize: 11,
                                                letterSpacing: 1,
                                                color: theme.colorScheme.outline,
                                                fontWeight: FontWeight.bold)),
                                      ],
                                    ),
                                  ),
                              ],
                            ),
                          ],
                        ),
                      ],
                    ),
                    trailing: canManageCatalog
                        ? (_isSelectionMode
                            ? null
                            : PopupMenuButton<String>(
                                key: Key('menu-item-${item.sku}'),
                                icon: const Icon(Icons.more_vert, size: 20),
                                shape: RoundedRectangleBorder(
                                  borderRadius: BorderRadius.circular(10),
                                ),
                                itemBuilder: (ctx) => [
                                  const PopupMenuItem(
                                    value: 'levels',
                                    child: Row(
                                      children: [
                                        Icon(Icons.tune_outlined,
                                            size: 16,
                                            color: Color(0xFF2563EB)),
                                        SizedBox(width: 8),
                                        Text('Định mức tồn'),
                                      ],
                                    ),
                                  ),
                                  const PopupMenuItem(
                                    value: 'edit',
                                    child: Row(
                                      children: [
                                        Icon(Icons.edit_outlined, size: 16),
                                        SizedBox(width: 8),
                                        Text('Sửa thông tin'),
                                      ],
                                    ),
                                  ),
                                  PopupMenuItem(
                                    key: Key('btn-delete-item-${item.sku}'),
                                    value: 'delete',
                                    child: const Row(
                                      children: [
                                        Icon(Icons.delete_outline,
                                            size: 16, color: Colors.red),
                                        SizedBox(width: 8),
                                        Text('Xóa mặt hàng',
                                            style:
                                                TextStyle(color: Colors.red)),
                                      ],
                                    ),
                                  ),
                                ],
                                onSelected: (val) {
                                  if (val == 'levels') {
                                    _showSetStockLevelDialog(
                                        item,
                                        data.locations,
                                        data.stockLevels);
                                  } else if (val == 'edit') {
                                    _showEditItemDialog(item);
                                  } else if (val == 'delete') {
                                    _confirmDeleteItem(
                                        item, data.balances);
                                  }
                                },
                              ))
                        : null,
                  );
                },
              ),
            ),
        ],
      );
    }

    // Màn hình rộng (Desktop / Tablet >= 960px): Bảng tính Google Sheet chuyên nghiệp
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        filterBar,
        Container(
          decoration: BoxDecoration(
            color: isDark ? const Color(0xFF0F172A) : Colors.white,
            borderRadius: BorderRadius.circular(12),
            border: Border.all(
              color: isDark ? const Color(0xFF334155) : const Color(0xFFCBD5E1),
            ),
            boxShadow: [
              BoxShadow(
                color: Colors.black.withValues(alpha: 0.03),
                blurRadius: 8,
                offset: const Offset(0, 2),
              ),
            ],
          ),
          clipBehavior: Clip.antiAlias,
          child: SingleChildScrollView(
            scrollDirection: Axis.horizontal,
            child: ConstrainedBox(
              constraints: const BoxConstraints(minWidth: 1060),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  // Hàng Tiêu Đề Cột (Google Sheet Header)
                  Container(
                    height: 42,
                    decoration: BoxDecoration(
                      color: isDark
                          ? const Color(0xFF1E293B)
                          : const Color(0xFFF1F5F9),
                      border: Border(
                        bottom: BorderSide(
                          color: isDark
                              ? const Color(0xFF334155)
                              : const Color(0xFFCBD5E1),
                          width: 1.5,
                        ),
                      ),
                    ),
                    child: Row(
                      children: [
                        _buildHeaderCell('STT',
                            width: 44, align: TextAlign.center, isDark: isDark),
                        _buildHeaderCell('MÃ SKU', width: 95, isDark: isDark),
                        _buildHeaderCell('TÊN NGUYÊN LIỆU / SP',
                            width: 200, isDark: isDark),
                        _buildHeaderCell('NHÓM', width: 110, isDark: isDark),
                        _buildHeaderCell('ĐVT',
                            width: 60, align: TextAlign.center, isDark: isDark),
                        _buildHeaderCell('TỒN KHẢ DỤNG',
                            width: 105, align: TextAlign.right, isDark: isDark),
                        _buildHeaderCell('TỒN MIN',
                            width: 80, align: TextAlign.right, isDark: isDark),
                        _buildHeaderCell(
                          (isAdmin && _revealPrices)
                              ? 'GIÁ BÁN'
                              : 'GIÁ BÁN (🔒)',
                          width: 105,
                          align: TextAlign.right,
                          isDark: isDark,
                        ),
                        _buildHeaderCell(
                          (isAdmin && _revealPrices)
                              ? 'GIÁ VỐN'
                              : 'GIÁ VỐN (🔒)',
                          width: 105,
                          align: TextAlign.right,
                          isDark: isDark,
                        ),
                        _buildHeaderCell('TRẠNG THÁI',
                            width: 95, align: TextAlign.center, isDark: isDark),
                        _buildHeaderCell('THAO TÁC',
                            width: 120, align: TextAlign.center, isDark: isDark),
                      ],
                    ),
                  ),

                  // Danh sách các dòng dữ liệu
                  if (filteredItems.isEmpty)
                    emptyFilterPlaceholder
                  else
                    for (int i = 0; i < filteredItems.length; i++)
                      _buildDataRow(
                        context,
                        filteredItems[i],
                        data,
                        index: i,
                        isAdmin: isAdmin,
                        canManageCatalog: canManageCatalog,
                        isCompact: isCompact,
                        theme: theme,
                        isDark: isDark,
                      ),
                ],
              ),
            ),
          ),
        ),
      ],
    );
  }

  Widget _buildHeaderCell(
    String title, {
    required double width,
    TextAlign align = TextAlign.left,
    required bool isDark,
  }) {
    return Container(
      width: width,
      height: 42,
      padding: const EdgeInsets.symmetric(horizontal: 8),
      alignment: align == TextAlign.center
          ? Alignment.center
          : (align == TextAlign.right
              ? Alignment.centerRight
              : Alignment.centerLeft),
      decoration: BoxDecoration(
        border: Border(
          right: BorderSide(
            color: isDark ? const Color(0xFF334155) : const Color(0xFFE2E8F0),
            width: 1,
          ),
        ),
      ),
      child: Text(
        title,
        maxLines: 1,
        overflow: TextOverflow.ellipsis,
        style: TextStyle(
          fontSize: 11,
          fontWeight: FontWeight.w800,
          letterSpacing: 0.3,
          color: isDark ? const Color(0xFF94A3B8) : const Color(0xFF475569),
        ),
      ),
    );
  }

  Widget _buildDataRow(
    BuildContext context,
    InventoryItem item,
    _InventoryData data, {
    required int index,
    required bool isAdmin,
    required bool canManageCatalog,
    required bool isCompact,
    required ThemeData theme,
    required bool isDark,
  }) {
    final stock = _stockForItem(item.id, data.balances);
    final minStock = item.minStock;
    final isSelected = _selectedItemIds.contains(item.id);

    // Row zebra background
    final rowBg = isSelected
        ? (isDark
            ? const Color(0xFF1E3A8A).withValues(alpha: 0.3)
            : const Color(0xFFEFF6FF))
        : (index.isEven
            ? (isDark ? const Color(0xFF0F172A) : Colors.white)
            : (isDark
                ? const Color(0xFF1E293B).withValues(alpha: 0.35)
                : const Color(0xFFF8FAFC)));

    // Stock status
    final bool isOutOfStock = stock <= 0;
    final bool isLowStock = !isOutOfStock && minStock != null && stock <= minStock;

    return InkWell(
      onTap: _isSelectionMode
          ? () => _toggleItemSelection(item.id)
          : () => _showItemDetailSheet(context, item, data, isAdmin: isAdmin),
      child: Container(
        height: 52,
        decoration: BoxDecoration(
          color: rowBg,
          border: Border(
            bottom: BorderSide(
              color: isDark ? const Color(0xFF1E293B) : const Color(0xFFE2E8F0),
              width: 1,
            ),
          ),
        ),
        child: Row(
          children: [
            // STT hoặc Checkbox
            Container(
              width: 44,
              height: 52,
              alignment: Alignment.center,
              decoration: BoxDecoration(
                border: Border(
                  right: BorderSide(
                    color: isDark
                        ? const Color(0xFF1E293B)
                        : const Color(0xFFE2E8F0),
                  ),
                ),
              ),
              child: _isSelectionMode
                  ? Checkbox(
                      key: Key('checkbox-item-${item.sku}'),
                      value: isSelected,
                      onChanged: (_) => _toggleItemSelection(item.id),
                    )
                  : Text(
                      '${index + 1}',
                      style: TextStyle(
                        fontSize: 12,
                        fontWeight: FontWeight.w700,
                        color: isDark
                            ? const Color(0xFF94A3B8)
                            : const Color(0xFF64748B),
                      ),
                    ),
            ),

            // Mã SKU
            Container(
              width: 95,
              height: 52,
              padding: const EdgeInsets.symmetric(horizontal: 6),
              alignment: Alignment.centerLeft,
              decoration: BoxDecoration(
                border: Border(
                  right: BorderSide(
                    color: isDark
                        ? const Color(0xFF1E293B)
                        : const Color(0xFFE2E8F0),
                  ),
                ),
              ),
              child: Container(
                padding:
                    const EdgeInsets.symmetric(horizontal: 5, vertical: 2.5),
                decoration: BoxDecoration(
                  color: isDark ? Colors.white10 : const Color(0xFFF1F5F9),
                  borderRadius: BorderRadius.circular(4),
                  border: Border.all(
                    color: isDark
                        ? const Color(0xFF475569)
                        : const Color(0xFFCBD5E1),
                  ),
                ),
                child: Text(
                  item.sku,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(
                    fontFamily: 'monospace',
                    fontWeight: FontWeight.w700,
                    fontSize: 11,
                    color: isDark
                        ? const Color(0xFF93C5FD)
                        : const Color(0xFF1D4ED8),
                  ),
                ),
              ),
            ),

            // TÊN NGUYÊN LIỆU / SP
            Container(
              width: 200,
              height: 52,
              padding: const EdgeInsets.symmetric(horizontal: 10),
              alignment: Alignment.centerLeft,
              decoration: BoxDecoration(
                border: Border(
                  right: BorderSide(
                    color: isDark
                        ? const Color(0xFF1E293B)
                        : const Color(0xFFE2E8F0),
                  ),
                ),
              ),
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    item.name,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(
                      fontWeight: FontWeight.w600,
                      fontSize: 13,
                    ),
                  ),
                  if (item.packaging != null && item.packaging!.isNotEmpty)
                    Text(
                      item.packaging!,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(
                        fontSize: 11,
                        color: theme.colorScheme.onSurfaceVariant,
                      ),
                    ),
                ],
              ),
            ),

            // NHÓM
            Container(
              width: 110,
              height: 52,
              padding: const EdgeInsets.symmetric(horizontal: 10),
              alignment: Alignment.centerLeft,
              decoration: BoxDecoration(
                border: Border(
                  right: BorderSide(
                    color: isDark
                        ? const Color(0xFF1E293B)
                        : const Color(0xFFE2E8F0),
                  ),
                ),
              ),
              child: Text(
                item.category ?? 'Chưa phân nhóm',
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: TextStyle(
                  fontSize: 12,
                  color: isDark
                      ? const Color(0xFFCBD5E1)
                      : const Color(0xFF475569),
                ),
              ),
            ),

            // ĐVT
            Container(
              width: 60,
              height: 52,
              alignment: Alignment.center,
              decoration: BoxDecoration(
                border: Border(
                  right: BorderSide(
                    color: isDark
                        ? const Color(0xFF1E293B)
                        : const Color(0xFFE2E8F0),
                  ),
                ),
              ),
              child: Text(
                item.unit,
                style: const TextStyle(
                  fontSize: 12.5,
                  fontWeight: FontWeight.w500,
                ),
              ),
            ),

            // TỒN KHẢ DỤNG
            Container(
              width: 105,
              height: 52,
              padding: const EdgeInsets.symmetric(horizontal: 10),
              alignment: Alignment.centerRight,
              decoration: BoxDecoration(
                border: Border(
                  right: BorderSide(
                    color: isDark
                        ? const Color(0xFF1E293B)
                        : const Color(0xFFE2E8F0),
                  ),
                ),
              ),
              child: Text(
                '${AppFormat.number(stock.toString())} ${item.unit}',
                style: TextStyle(
                  fontWeight: FontWeight.w800,
                  fontSize: 12.5,
                  color: isOutOfStock
                      ? const Color(0xFFEF4444)
                      : (isLowStock
                          ? const Color(0xFFD97706)
                          : const Color(0xFF059669)),
                ),
              ),
            ),

            // TỒN MIN
            Container(
              width: 80,
              height: 52,
              padding: const EdgeInsets.symmetric(horizontal: 10),
              alignment: Alignment.centerRight,
              decoration: BoxDecoration(
                border: Border(
                  right: BorderSide(
                    color: isDark
                        ? const Color(0xFF1E293B)
                        : const Color(0xFFE2E8F0),
                  ),
                ),
              ),
              child: Text(
                minStock != null ? AppFormat.number(minStock.toString()) : '—',
                style: TextStyle(
                  fontSize: 12,
                  color: isDark
                      ? const Color(0xFF94A3B8)
                      : const Color(0xFF64748B),
                ),
              ),
            ),

            // GIÁ BÁN (Admin Only)
            Container(
              width: 105,
              height: 52,
              padding: const EdgeInsets.symmetric(horizontal: 10),
              alignment: Alignment.centerRight,
              decoration: BoxDecoration(
                border: Border(
                  right: BorderSide(
                    color: isDark
                        ? const Color(0xFF1E293B)
                        : const Color(0xFFE2E8F0),
                  ),
                ),
              ),
              child: (isAdmin && _revealPrices)
                  ? (item.sellingPrice != null
                      ? Text(
                          AppFormat.money(item.sellingPrice!.toStringAsFixed(0), currency: '₫'),
                          style: const TextStyle(
                            fontWeight: FontWeight.w700,
                            fontSize: 12,
                            color: Color(0xFF0284C7),
                          ),
                        )
                      : TextButton(
                          onPressed: () => _showEditItemDialog(item),
                          style: TextButton.styleFrom(
                            padding: EdgeInsets.zero,
                            minimumSize: const Size(50, 30),
                            tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                          ),
                          child: const Text(
                            '+ Thêm giá',
                            style: TextStyle(
                              fontSize: 11,
                              fontWeight: FontWeight.w600,
                              color: Color(0xFF0284C7),
                            ),
                          ),
                        ))
                  : Tooltip(
                      message: isAdmin
                          ? 'Đang ẩn giá'
                          : 'Chỉ Admin mới có quyền xem giá',
                      child: Text(
                        '••••••',
                        style: TextStyle(
                          letterSpacing: 1.5,
                          fontWeight: FontWeight.w700,
                          fontSize: 12,
                          color: isDark
                              ? const Color(0xFF64748B)
                              : const Color(0xFF94A3B8),
                        ),
                      ),
                    ),
            ),

            // GIÁ VỐN (Admin Only)
            Container(
              width: 105,
              height: 52,
              padding: const EdgeInsets.symmetric(horizontal: 10),
              alignment: Alignment.centerRight,
              decoration: BoxDecoration(
                border: Border(
                  right: BorderSide(
                    color: isDark
                        ? const Color(0xFF1E293B)
                        : const Color(0xFFE2E8F0),
                  ),
                ),
              ),
              child: (isAdmin && _revealPrices)
                  ? (item.costPrice != null
                      ? Text(
                          AppFormat.money(item.costPrice!.toStringAsFixed(0), currency: '₫'),
                          style: TextStyle(
                            fontWeight: FontWeight.w600,
                            fontSize: 12,
                            color: isDark
                                ? const Color(0xFFCBD5E1)
                                : const Color(0xFF475569),
                          ),
                        )
                      : TextButton(
                          onPressed: () => _showEditItemDialog(item),
                          style: TextButton.styleFrom(
                            padding: EdgeInsets.zero,
                            minimumSize: const Size(50, 30),
                            tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                          ),
                          child: const Text(
                            '+ Thêm giá',
                            style: TextStyle(
                              fontSize: 11,
                              fontWeight: FontWeight.w600,
                              color: Color(0xFF0891B2),
                            ),
                          ),
                        ))
                  : Tooltip(
                      message: isAdmin
                          ? 'Đang ẩn giá'
                          : 'Chỉ Admin mới có quyền xem giá',
                      child: Text(
                        '••••••',
                        style: TextStyle(
                          letterSpacing: 1.5,
                          fontWeight: FontWeight.w700,
                          fontSize: 12,
                          color: isDark
                              ? const Color(0xFF64748B)
                              : const Color(0xFF94A3B8),
                        ),
                      ),
                    ),
            ),

            // TRẠNG THÁI
            Container(
              width: 95,
              height: 52,
              alignment: Alignment.center,
              decoration: BoxDecoration(
                border: Border(
                  right: BorderSide(
                    color: isDark
                        ? const Color(0xFF1E293B)
                        : const Color(0xFFE2E8F0),
                  ),
                ),
              ),
              child: Container(
                padding:
                    const EdgeInsets.symmetric(horizontal: 6, vertical: 3),
                decoration: BoxDecoration(
                  color: isOutOfStock
                      ? (isDark
                          ? const Color(0xFF451A1A)
                          : const Color(0xFFFEE2E2))
                      : (isLowStock
                          ? (isDark
                              ? const Color(0xFF452205)
                              : const Color(0xFFFEF3C7))
                          : (isDark
                              ? const Color(0xFF064E3B)
                              : const Color(0xFFD1FAE5))),
                  borderRadius: BorderRadius.circular(6),
                ),
                child: Text(
                  isOutOfStock
                      ? 'Hết hàng'
                      : (isLowStock ? 'Sắp hết' : 'Đủ hàng'),
                  style: TextStyle(
                    fontSize: 11,
                    fontWeight: FontWeight.w700,
                    color: isOutOfStock
                        ? const Color(0xFFEF4444)
                        : (isLowStock
                            ? const Color(0xFFD97706)
                            : const Color(0xFF059669)),
                  ),
                ),
              ),
            ),

            // THAO TÁC
            Container(
              width: 120,
              height: 52,
              alignment: Alignment.center,
              child: canManageCatalog
                  ? (_isSelectionMode
                      ? null
                      : Row(
                          mainAxisSize: MainAxisSize.min,
                          mainAxisAlignment: MainAxisAlignment.center,
                          children: [
                            IconButton(
                              padding: EdgeInsets.zero,
                              constraints: const BoxConstraints(
                                  minWidth: 32, minHeight: 32),
                              iconSize: 18,
                              visualDensity: VisualDensity.compact,
                              tooltip: 'Định mức tồn (Min / Max)',
                              icon: const Icon(Icons.tune_outlined,
                                  size: 18, color: Color(0xFF2563EB)),
                              onPressed: () => _showSetStockLevelDialog(
                                  item, data.locations, data.stockLevels),
                            ),
                            IconButton(
                              key: Key('btn-edit-item-${item.sku}'),
                              padding: EdgeInsets.zero,
                              constraints: const BoxConstraints(
                                  minWidth: 32, minHeight: 32),
                              iconSize: 18,
                              visualDensity: VisualDensity.compact,
                              tooltip: 'Sửa mặt hàng',
                              icon: const Icon(Icons.edit_outlined, size: 18),
                              onPressed: () => _showEditItemDialog(item),
                            ),
                            IconButton(
                              key: Key('btn-delete-item-${item.sku}'),
                              padding: EdgeInsets.zero,
                              constraints: const BoxConstraints(
                                  minWidth: 32, minHeight: 32),
                              iconSize: 18,
                              visualDensity: VisualDensity.compact,
                              tooltip: 'Xóa mặt hàng',
                              icon: const Icon(Icons.delete_outline,
                                  size: 18, color: Colors.red),
                              onPressed: () =>
                                  _confirmDeleteItem(item, data.balances),
                            ),
                          ],
                        ))
                  : null,
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildFilterChip(String value, String label, bool isDark,
      {Color? color}) {
    final isSelected = _stockFilter == value;
    final activeColor = color ?? const Color(0xFF2563EB);
    return InkWell(
      onTap: () => setState(() => _stockFilter = value),
      borderRadius: BorderRadius.circular(20),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
        decoration: BoxDecoration(
          color: isSelected
              ? activeColor.withValues(alpha: isDark ? 0.25 : 0.12)
              : (isDark ? const Color(0xFF0F172A) : Colors.white),
          borderRadius: BorderRadius.circular(20),
          border: Border.all(
            color: isSelected
                ? activeColor
                : (isDark
                    ? const Color(0xFF334155)
                    : const Color(0xFFCBD5E1)),
            width: isSelected ? 1.5 : 1,
          ),
        ),
        child: Text(
          label,
          style: TextStyle(
            fontSize: 12,
            fontWeight: isSelected ? FontWeight.w700 : FontWeight.w500,
            color: isSelected
                ? activeColor
                : (isDark
                    ? const Color(0xFF94A3B8)
                    : const Color(0xFF64748B)),
          ),
        ),
      ),
    );
  }

  Widget _buildLowStockAlertBanner(
      BuildContext context, List<LowStockAlertItem> alerts) {
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;

    final uniqueItems = alerts.map((a) => a.itemId).toSet().length;
    final emptyCount = alerts.where((a) => a.status == 'empty').length;
    final lowCount = alerts.where((a) => a.status != 'empty').length;

    final locationMap = <String, String>{};
    final locationCounts = <String, int>{};
    for (final a in alerts) {
      locationMap[a.locationId] = a.locationName;
      locationCounts[a.locationId] = (locationCounts[a.locationId] ?? 0) + 1;
    }

    final filteredAlerts = _alertLocationFilter == null
        ? alerts
        : alerts.where((a) => a.locationId == _alertLocationFilter).toList();

    final isNarrow = MediaQuery.sizeOf(context).width < 700;

    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: isDark ? const Color(0xFF451A1A) : const Color(0xFFFEF2F2),
        borderRadius: BorderRadius.circular(16),
        border:
            Border.all(color: const Color(0xFFEF4444).withValues(alpha: 0.3)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (isNarrow) ...[
            Row(
              children: [
                Container(
                  padding: const EdgeInsets.all(8),
                  decoration: BoxDecoration(
                    color: const Color(0xFFEF4444).withValues(alpha: 0.15),
                    shape: BoxShape.circle,
                  ),
                  child: const Icon(Icons.warning_amber_rounded,
                      color: Color(0xFFDC2626), size: 20),
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: Text(
                    'Cảnh Báo Thiếu Tồn Kho Định Mức (${alerts.length} cảnh báo · $uniqueItems nguyên liệu)',
                    style: const TextStyle(
                        fontWeight: FontWeight.w800,
                        fontSize: 13.5,
                        color: Color(0xFFDC2626)),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 6),
            Text(
              '$emptyCount hết hàng, $lowCount sắp thiếu qua ${locationMap.length} kho.',
              style: TextStyle(
                  fontSize: 12,
                  color: theme.colorScheme.onSurfaceVariant),
            ),
            const SizedBox(height: 8),
            Align(
              alignment: Alignment.centerLeft,
              child: FilledButton.tonalIcon(
                key: const Key('btn-toggle-stock-alerts'),
                onPressed: () =>
                    setState(() => _alertsExpanded = !_alertsExpanded),
                icon: Icon(_alertsExpanded ? Icons.expand_less : Icons.expand_more,
                    size: 16),
                label: Text(_alertsExpanded
                    ? 'Thu gọn'
                    : 'Xem chi tiết (${alerts.length})'),
                style: FilledButton.styleFrom(
                  visualDensity: VisualDensity.compact,
                  padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                ),
              ),
            ),
          ] else ...[
            Row(
              children: [
                Container(
                  padding: const EdgeInsets.all(8),
                  decoration: BoxDecoration(
                    color: const Color(0xFFEF4444).withValues(alpha: 0.15),
                    shape: BoxShape.circle,
                  ),
                  child: const Icon(Icons.warning_amber_rounded,
                      color: Color(0xFFDC2626), size: 20),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        'Cảnh Báo Thiếu Tồn Kho Định Mức (${alerts.length} cảnh báo · $uniqueItems nguyên liệu)',
                        style: const TextStyle(
                            fontWeight: FontWeight.w800,
                            fontSize: 15,
                            color: Color(0xFFDC2626)),
                      ),
                      Text(
                        '$emptyCount hết hàng, $lowCount sắp thiếu qua ${locationMap.length} kho. Bấm để xem chi tiết hoặc thu gọn.',
                        style: TextStyle(
                            fontSize: 12,
                            color: theme.colorScheme.onSurfaceVariant),
                      ),
                    ],
                  ),
                ),
                const SizedBox(width: 8),
                FilledButton.tonalIcon(
                  key: const Key('btn-toggle-stock-alerts'),
                  onPressed: () =>
                      setState(() => _alertsExpanded = !_alertsExpanded),
                  icon: Icon(_alertsExpanded ? Icons.expand_less : Icons.expand_more,
                      size: 18),
                  label: Text(_alertsExpanded
                      ? 'Thu gọn'
                      : 'Xem chi tiết (${alerts.length})'),
                  style: FilledButton.styleFrom(
                    visualDensity: VisualDensity.compact,
                    padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
                  ),
                ),
              ],
            ),
          ],
          if (!_alertsExpanded) ...[
            const SizedBox(height: 10),
            Wrap(
              spacing: 8,
              runSpacing: 6,
              children: [
                Container(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                  decoration: BoxDecoration(
                    color: Colors.red.withValues(alpha: 0.12),
                    borderRadius: BorderRadius.circular(6),
                  ),
                  child: Text(
                    '🔴 $emptyCount hết hàng',
                    style: const TextStyle(
                        fontSize: 11.5,
                        fontWeight: FontWeight.bold,
                        color: Colors.red),
                  ),
                ),
                Container(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                  decoration: BoxDecoration(
                    color: Colors.orange.withValues(alpha: 0.12),
                    borderRadius: BorderRadius.circular(6),
                  ),
                  child: Text(
                    '🟡 $lowCount sắp thiếu',
                    style: const TextStyle(
                        fontSize: 11.5,
                        fontWeight: FontWeight.bold,
                        color: Colors.orange),
                  ),
                ),
                for (final entry in locationMap.entries)
                  Container(
                    padding:
                        const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                    decoration: BoxDecoration(
                      color: Colors.grey.withValues(alpha: 0.1),
                      borderRadius: BorderRadius.circular(6),
                    ),
                    child: Text(
                      '${entry.value}: ${locationCounts[entry.key]}',
                      style: const TextStyle(fontSize: 11.5),
                    ),
                  ),
              ],
            ),
          ] else ...[
            const SizedBox(height: 12),
            Wrap(
              spacing: 8,
              runSpacing: 6,
              children: [
                ChoiceChip(
                  label: Text('Tất cả kho (${alerts.length})'),
                  selected: _alertLocationFilter == null,
                  onSelected: (_) =>
                      setState(() => _alertLocationFilter = null),
                ),
                for (final entry in locationMap.entries)
                  ChoiceChip(
                    label: Text('${entry.value} (${locationCounts[entry.key]})'),
                    selected: _alertLocationFilter == entry.key,
                    onSelected: (_) =>
                        setState(() => _alertLocationFilter = entry.key),
                  ),
              ],
            ),
            const SizedBox(height: 12),
            Column(
              children: filteredAlerts.map((al) {
                final isEmpty = al.status == 'empty';
                final isNarrow = MediaQuery.sizeOf(context).width < 700;

                final supplementButton = FilledButton.tonal(
                  onPressed: () {
                    if (widget.onCreateStockRequest != null) {
                      final defVal = double.tryParse(al.deficit);
                      widget.onCreateStockRequest!(
                        locationId: al.locationId,
                        itemId: al.itemId,
                        suggestedQty: (defVal != null && defVal > 0) ? defVal : null,
                      );
                    } else if (widget.onNavigate != null) {
                      widget.onNavigate!(3);
                    }
                  },
                  style: FilledButton.styleFrom(
                    visualDensity: VisualDensity.compact,
                    shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(8)),
                  ),
                  child: const Text('Bổ Sung Ngay',
                      style: TextStyle(fontSize: 12)),
                );

                if (isNarrow) {
                  return Container(
                    margin: const EdgeInsets.only(bottom: 8),
                    padding: const EdgeInsets.all(12),
                    decoration: BoxDecoration(
                      color: isDark ? const Color(0xFF2D1515) : Colors.white,
                      borderRadius: BorderRadius.circular(10),
                      border: Border.all(color: Colors.red.withValues(alpha: 0.2)),
                    ),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Wrap(
                          alignment: WrapAlignment.spaceBetween,
                          crossAxisAlignment: WrapCrossAlignment.center,
                          spacing: 8,
                          runSpacing: 6,
                          children: [
                            Container(
                              padding: const EdgeInsets.symmetric(
                                  horizontal: 8, vertical: 3),
                              decoration: BoxDecoration(
                                color: isEmpty ? Colors.red : Colors.orange,
                                borderRadius: BorderRadius.circular(6),
                              ),
                              child: Text(
                                isEmpty ? 'HẾT HÀNG' : 'SẮP THIẾU',
                                style: const TextStyle(
                                    color: Colors.white,
                                    fontSize: 10,
                                    fontWeight: FontWeight.bold),
                              ),
                            ),
                            supplementButton,
                          ],
                        ),
                        const SizedBox(height: 8),
                        Text('${al.itemName} (${al.sku})',
                            style: const TextStyle(
                                fontWeight: FontWeight.bold, fontSize: 13)),
                        const SizedBox(height: 2),
                        Text(
                          'Kho: ${al.locationName} • Tồn: ${al.currentQty} ${al.unit} / Định mức: ${al.minQty} (Thiếu: ${al.deficit})',
                          style: TextStyle(
                              fontSize: 12,
                              color: theme.colorScheme.onSurfaceVariant),
                        ),
                      ],
                    ),
                  );
                }

                return Container(
                  margin: const EdgeInsets.only(bottom: 8),
                  padding: const EdgeInsets.all(12),
                  decoration: BoxDecoration(
                    color: isDark ? const Color(0xFF2D1515) : Colors.white,
                    borderRadius: BorderRadius.circular(10),
                    border: Border.all(color: Colors.red.withValues(alpha: 0.2)),
                  ),
                  child: Row(
                    children: [
                      Container(
                        padding: const EdgeInsets.symmetric(
                            horizontal: 8, vertical: 3),
                        decoration: BoxDecoration(
                          color: isEmpty ? Colors.red : Colors.orange,
                          borderRadius: BorderRadius.circular(6),
                        ),
                        child: Text(
                          isEmpty ? 'HẾT HÀNG' : 'SẮP THIẾU',
                          style: const TextStyle(
                              color: Colors.white,
                              fontSize: 10,
                              fontWeight: FontWeight.bold),
                        ),
                      ),
                      const SizedBox(width: 10),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text('${al.itemName} (${al.sku})',
                                style: const TextStyle(
                                    fontWeight: FontWeight.bold, fontSize: 13)),
                            Text(
                              'Kho: ${al.locationName} • Tồn: ${al.currentQty} ${al.unit} / Định mức: ${al.minQty} (Thiếu: ${al.deficit})',
                              style: TextStyle(
                                  fontSize: 12,
                                  color: theme.colorScheme.onSurfaceVariant),
                            ),
                          ],
                        ),
                      ),
                      supplementButton,
                    ],
                  ),
                );
              }).toList(),
            ),
          ],
        ],
      ),
    );
  }

  Widget _buildStocktakesSection(BuildContext context, _InventoryData data) {
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;

    final isShiftOnly = widget.mode == InventoryTabMode.shiftWork;
    final isCompact = MediaQuery.sizeOf(context).width < 960;
    final header = isCompact
        ? Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                context.tr('inventory_stocktake_section_title'),
                style: theme.textTheme.titleMedium?.copyWith(
                  fontWeight: FontWeight.w800,
                ),
              ),
              const SizedBox(height: 2),
              Text(
                context.tr('inventory_stocktake_section_sub'),
                style: TextStyle(
                    fontSize: 12, color: theme.colorScheme.onSurfaceVariant),
              ),
              if (!isShiftOnly) ...[
                const SizedBox(height: 10),
                FilledButton.icon(
                  onPressed: () => _showCreateStocktakeDialog(data.locations),
                  icon: const Icon(Icons.add_task_rounded, size: 16),
                  label: Text(context.tr('inventory_btn_new_stocktake')),
                  style: FilledButton.styleFrom(
                    backgroundColor: const Color(0xFF0891B2),
                    shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(10)),
                  ),
                ),
              ],
            ],
          )
        : Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      context.tr('inventory_stocktake_section_title'),
                      style: theme.textTheme.titleMedium?.copyWith(
                        fontWeight: FontWeight.w800,
                      ),
                    ),
                    const SizedBox(height: 2),
                    Text(
                      context.tr('inventory_stocktake_section_sub'),
                      style: TextStyle(
                          fontSize: 12,
                          color: theme.colorScheme.onSurfaceVariant),
                    ),
                  ],
                ),
              ),
              if (!isShiftOnly) ...[
                const SizedBox(width: 12),
                FilledButton.icon(
                  onPressed: () => _showCreateStocktakeDialog(data.locations),
                  icon: const Icon(Icons.add_task_rounded, size: 16),
                  label: Text(context.tr('inventory_btn_new_stocktake')),
                  style: FilledButton.styleFrom(
                    backgroundColor: const Color(0xFF0891B2),
                    shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(10)),
                  ),
                ),
              ],
            ],
          );

    final filteredStocktakes = data.stocktakes.where((st) {
      if (_stocktakeStatusFilter == 'pending') {
        return st.status == 'submitted' || st.status == 'open';
      }
      if (_stocktakeStatusFilter == 'approved') {
        return st.status == 'approved' ||
            st.status == 'completed' ||
            st.status == 'closed';
      }
      if (_stocktakeStatusFilter == 'discrepancy') {
        return st.discrepancyCount > 0 ||
            (st.note?.toLowerCase().contains('lệch') ?? false);
      }
      return true;
    }).toList();

    final isVi = context.isVietnamese;
    final String emptyMessage;
    if (_stocktakeStatusFilter == 'pending') {
      emptyMessage = isVi
          ? 'Không có đợt kiểm kê nào đang chờ duyệt.'
          : 'No stocktake sessions awaiting review.';
    } else if (_stocktakeStatusFilter == 'approved') {
      emptyMessage = isVi
          ? 'Không có đợt kiểm kê nào đã duyệt.'
          : 'No approved stocktake sessions found.';
    } else if (_stocktakeStatusFilter == 'discrepancy') {
      emptyMessage = isVi
          ? 'Tuyệt vời! Không có đợt kiểm kê nào bị lệch số liệu.'
          : 'Great! No stocktake sessions with variances.';
    } else {
      emptyMessage = isVi
          ? 'Chưa có đợt kiểm kê nào. Bấm "Mở Đợt Kiểm Kê Mới" để bắt đầu kiểm kê.'
          : 'No stocktake sessions recorded. Click "New Stocktake" to begin.';
    }

    String filterBadgeLabel;
    Color filterBadgeColor;
    IconData filterBadgeIcon;
    if (_stocktakeStatusFilter == 'pending') {
      filterBadgeLabel = isVi ? 'Chờ Quản lý duyệt' : 'Pending Review';
      filterBadgeColor = const Color(0xFFF59E0B);
      filterBadgeIcon = Icons.pending_actions_rounded;
    } else if (_stocktakeStatusFilter == 'approved') {
      filterBadgeLabel = isVi ? 'Đã duyệt / Hoàn tất' : 'Approved & Closed';
      filterBadgeColor = const Color(0xFF059669);
      filterBadgeIcon = Icons.verified_rounded;
    } else if (_stocktakeStatusFilter == 'discrepancy') {
      filterBadgeLabel = isVi ? 'Có chênh lệch' : 'Variance / Discrepancy';
      filterBadgeColor = const Color(0xFFEF4444);
      filterBadgeIcon = Icons.warning_amber_rounded;
    } else {
      filterBadgeLabel = isVi ? 'Tất cả các đợt' : 'All Sessions';
      filterBadgeColor = const Color(0xFF0891B2);
      filterBadgeIcon = Icons.checklist_rounded;
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        header,
        const SizedBox(height: 12),
        SingleChildScrollView(
          scrollDirection: Axis.horizontal,
          child: Container(
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
            decoration: BoxDecoration(
              color: filterBadgeColor.withValues(alpha: 0.1),
              borderRadius: BorderRadius.circular(8),
              border: Border.all(color: filterBadgeColor.withValues(alpha: 0.3)),
            ),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(filterBadgeIcon, size: 14, color: filterBadgeColor),
                const SizedBox(width: 6),
                Text(
                  '${isVi ? 'Đang lọc' : 'Showing'}: $filterBadgeLabel (${filteredStocktakes.length})',
                  style: TextStyle(
                    fontSize: 12,
                    fontWeight: FontWeight.w700,
                    color: filterBadgeColor,
                  ),
                ),
                if (_stocktakeStatusFilter != 'all') ...[
                  const SizedBox(width: 8),
                  InkWell(
                    onTap: () => setState(() => _stocktakeStatusFilter = 'all'),
                    child: Icon(Icons.close_rounded, size: 14, color: filterBadgeColor),
                  ),
                ],
              ],
            ),
          ),
        ),
        const SizedBox(height: 12),
        Container(
          decoration: BoxDecoration(
            color: isDark ? const Color(0xFF1E293B) : Colors.white,
            borderRadius: BorderRadius.circular(16),
            border: Border.all(
              color: theme.colorScheme.outlineVariant.withValues(alpha: 0.5),
            ),
          ),
          child: filteredStocktakes.isEmpty
              ? Padding(
                  padding: const EdgeInsets.all(32),
                  child: Center(
                    child: Text(
                      emptyMessage,
                      textAlign: TextAlign.center,
                    ),
                  ),
                )
              : ListView.separated(
                  shrinkWrap: true,
                  physics: const NeverScrollableScrollPhysics(),
                  itemCount: filteredStocktakes.length,
                  separatorBuilder: (_, __) => const Divider(height: 1),
                  itemBuilder: (context, i) {
                    final st = filteredStocktakes[i];
                    final loc =
                        data.locations.cast<InventoryLocation?>().firstWhere(
                              (l) => l?.id == st.locationId,
                              orElse: () => null,
                            );
                    final locName = loc != null
                        ? '${loc.code} — ${loc.name}'
                        : st.locationId;

                    Color badgeColor;
                    String statusText;
                    if (st.status == 'open') {
                      badgeColor = const Color(0xFF2563EB);
                      statusText = isVi
                          ? 'Đang kiểm đếm (Open)'
                          : 'In Progress (Open)';
                    } else if (st.status == 'submitted') {
                      badgeColor = const Color(0xFFD97706);
                      statusText = isVi
                          ? 'Chờ Quản lý duyệt (Submitted)'
                          : 'Awaiting Review (Submitted)';
                    } else {
                      badgeColor = const Color(0xFF059669);
                      statusText = isVi
                          ? 'Đã hoàn tất (Closed)'
                          : 'Completed (Closed)';
                    }

                    final contentColumn = Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Wrap(
                          spacing: 8,
                          runSpacing: 4,
                          crossAxisAlignment: WrapCrossAlignment.center,
                          children: [
                            Text(
                              '${isVi ? 'Kho' : 'Location'}: $locName',
                              style: const TextStyle(
                                  fontWeight: FontWeight.bold,
                                  fontSize: 14),
                            ),
                            Container(
                              padding: const EdgeInsets.symmetric(
                                  horizontal: 8, vertical: 2),
                              decoration: BoxDecoration(
                                color: badgeColor.withValues(alpha: 0.12),
                                borderRadius: BorderRadius.circular(4),
                              ),
                              child: Text(
                                statusText,
                                style: TextStyle(
                                    color: badgeColor,
                                    fontSize: 11,
                                    fontWeight: FontWeight.bold),
                              ),
                            ),
                          ],
                        ),
                        const SizedBox(height: 4),
                        Text(
                          '${isVi ? 'Ghi chú' : 'Note'}: ${st.note ?? (isVi ? "Kiểm kê kho" : "Inventory stocktake")} • ${isVi ? 'Ngày tạo' : 'Created'}: ${st.createdAt.toLocal().toString().substring(0, 16)}',
                          style: TextStyle(
                              fontSize: 12,
                              color: theme.colorScheme.onSurfaceVariant),
                        ),
                        if (st.adjustmentRequestId != null)
                          Padding(
                            padding: const EdgeInsets.only(top: 4),
                            child: Text(
                              '${isVi ? '⚡ Phiếu điều chỉnh tự động' : '⚡ Auto adjustment request'}: #${st.adjustmentRequestId}',
                              style: const TextStyle(
                                  fontSize: 11,
                                  fontWeight: FontWeight.bold,
                                  color: Color(0xFF059669)),
                            ),
                          ),
                      ],
                    );

                    final actionBtn = OutlinedButton.icon(
                      onPressed: () => _showStocktakeDetailDialog(
                          st, data.items, data.locations,
                          stockLevels: data.stockLevels),
                      icon: const Icon(Icons.edit_note_rounded, size: 16),
                      label: Text(st.status == 'open'
                          ? (isVi ? 'Nhập Số Đếm' : 'Enter Count')
                          : (isVi ? 'Xem Chi Tiết' : 'View Details')),
                      style: OutlinedButton.styleFrom(
                        shape: RoundedRectangleBorder(
                            borderRadius: BorderRadius.circular(8)),
                      ),
                    );

                    return Padding(
                      padding: const EdgeInsets.symmetric(
                          horizontal: 16, vertical: 14),
                      child: isCompact
                          ? Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Row(
                                  crossAxisAlignment: CrossAxisAlignment.start,
                                  children: [
                                    Container(
                                      padding: const EdgeInsets.all(10),
                                      decoration: BoxDecoration(
                                        color: badgeColor.withValues(alpha: 0.1),
                                        borderRadius: BorderRadius.circular(10),
                                      ),
                                      child: Icon(Icons.assignment_outlined,
                                          size: 20, color: badgeColor),
                                    ),
                                    const SizedBox(width: 12),
                                    Expanded(child: contentColumn),
                                  ],
                                ),
                                const SizedBox(height: 10),
                                Align(
                                  alignment: Alignment.centerRight,
                                  child: actionBtn,
                                ),
                              ],
                            )
                          : Row(
                              children: [
                                Container(
                                  padding: const EdgeInsets.all(10),
                                  decoration: BoxDecoration(
                                    color: badgeColor.withValues(alpha: 0.1),
                                    borderRadius: BorderRadius.circular(10),
                                  ),
                                  child: Icon(Icons.assignment_outlined,
                                      size: 20, color: badgeColor),
                                ),
                                const SizedBox(width: 16),
                                Expanded(child: contentColumn),
                                const SizedBox(width: 12),
                                actionBtn,
                              ],
                            ),
                    );
                  },
                ),
        ),
        const SizedBox(height: 20),
        _buildShiftStocktakeDesk(data),
      ],
    );
  }

  Widget _buildShiftStocktakeDesk(_InventoryData data) {
    final activeStocktake = data.stocktakes.cast<StocktakeItem?>().firstWhere(
          (stocktake) => stocktake?.status == 'open',
          orElse: () => null,
        );
    final lines = data.items.map((item) {
      final balance = data.balances.cast<StockBalance?>().firstWhere(
            (value) => value?.itemId == item.id,
            orElse: () => null,
          );
      final savedLine =
          activeStocktake?.lines.cast<StocktakeLineItem?>().firstWhere(
                (value) => value?.itemId == item.id,
                orElse: () => null,
              );
      final opening = balance?.qtyNumber ?? 0;
      return ShiftStocktakeLine(
        name: item.name,
        unit: item.unit,
        openingQty: opening,
        receivedQty: 0,
        usedQty: double.tryParse(savedLine?.usedQty ?? '') ?? 0,
        countedQty: double.tryParse(savedLine?.countedQty ?? '') ?? opening,
        reason: savedLine?.reason ?? '',
      );
    }).toList();

    return ShiftStocktakeDesk(
      lines: lines,
      filterOnlyDiscrepancy: _stocktakeStatusFilter == 'discrepancy',
      onStartShiftStocktake: () {
        if (activeStocktake != null) {
          _showStocktakeDetailDialog(
            activeStocktake,
            data.items,
            data.locations,
            stockLevels: data.stockLevels,
          );
        } else {
          _showCreateStocktakeDialog(data.locations);
        }
      },
    );
  }

  Widget _buildExpiryAlertBanner(
      BuildContext context, List<ExpiryAlertItem> alerts) {
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;
    final isVi = context.isVietnamese;

    final criticalCount = alerts.where((a) => a.daysLeft <= 0).length;

    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: isDark ? const Color(0xFF3B2010) : const Color(0xFFFFFBEB),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(
          color: criticalCount > 0
              ? const Color(0xFFEF4444).withValues(alpha: 0.4)
              : const Color(0xFFF59E0B).withValues(alpha: 0.4),
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
                  color: (criticalCount > 0 ? Colors.red : Colors.amber)
                      .withValues(alpha: 0.15),
                  shape: BoxShape.circle,
                ),
                child: Icon(
                  criticalCount > 0
                      ? Icons.warning_rounded
                      : Icons.schedule_rounded,
                  color: criticalCount > 0
                      ? const Color(0xFFDC2626)
                      : const Color(0xFFD97706),
                  size: 20,
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      isVi
                          ? 'Cảnh Báo Hạn Sử Dụng Nguyên Liệu (${alerts.length} lô hàng cận/hết date)'
                          : 'Ingredient Expiry Alerts (${alerts.length} near/expired batches)',
                      style: TextStyle(
                        fontWeight: FontWeight.w800,
                        fontSize: 15,
                        color: criticalCount > 0
                            ? const Color(0xFFDC2626)
                            : const Color(0xFFB45309),
                      ),
                    ),
                    Text(
                      isVi
                          ? 'Kiểm tra và ưu tiên xuất pha chế trước (FEFO) hoặc lập phiếu hủy hỏng nếu đã hết hạn.'
                          : 'Verify and prioritize FEFO usage, or create a disposal request if expired.',
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
          const SizedBox(height: 12),
          Column(
            children: alerts.map((al) {
              final isExpired = al.daysLeft <= 0;
              final isWarning = al.daysLeft <= 3 && !isExpired;
              final isNarrow = MediaQuery.sizeOf(context).width < 700;

              final badgeColor = isExpired
                  ? const Color(0xFFDC2626)
                  : (isWarning
                      ? const Color(0xFFD97706)
                      : const Color(0xFF2563EB));
              final badgeText = isExpired
                  ? (al.daysLeft == 0
                      ? (isVi ? 'HẾT HẠN HÔM NAY' : 'EXPIRES TODAY')
                      : (isVi ? 'QUÁ HẠN ${-al.daysLeft} NGÀY' : 'EXPIRED ${-al.daysLeft} DAYS AGO'))
                  : (isWarning
                      ? (isVi ? 'CẬN DATE (CÒN ${al.daysLeft} NGÀY)' : 'NEAR EXPIRY (${al.daysLeft} DAYS LEFT)')
                      : (isVi ? 'THEO DÕI (CÒN ${al.daysLeft} NGÀY)' : 'WATCHLIST (${al.daysLeft} DAYS LEFT)'));

              if (isNarrow) {
                return Container(
                  margin: const EdgeInsets.only(bottom: 8),
                  padding: const EdgeInsets.all(12),
                  decoration: BoxDecoration(
                    color: isDark ? const Color(0xFF291B12) : Colors.white,
                    borderRadius: BorderRadius.circular(10),
                    border: Border.all(
                      color: badgeColor.withValues(alpha: 0.25),
                    ),
                  ),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Wrap(
                        alignment: WrapAlignment.spaceBetween,
                        crossAxisAlignment: WrapCrossAlignment.center,
                        spacing: 8,
                        runSpacing: 6,
                        children: [
                          Container(
                            padding: const EdgeInsets.symmetric(
                                horizontal: 8, vertical: 3),
                            decoration: BoxDecoration(
                              color: badgeColor,
                              borderRadius: BorderRadius.circular(6),
                            ),
                            child: Text(
                              badgeText,
                              style: const TextStyle(
                                color: Colors.white,
                                fontSize: 10,
                                fontWeight: FontWeight.bold,
                              ),
                            ),
                          ),
                          if (isWarning)
                            Container(
                              padding: const EdgeInsets.symmetric(
                                  horizontal: 8, vertical: 4),
                              decoration: BoxDecoration(
                                color: const Color(0xFFF59E0B)
                                    .withValues(alpha: 0.12),
                                borderRadius: BorderRadius.circular(6),
                              ),
                              child: Text(
                                isVi ? 'Ưu tiên dùng' : 'Use First',
                                style: const TextStyle(
                                  fontSize: 11,
                                  fontWeight: FontWeight.bold,
                                  color: Color(0xFFB45309),
                                ),
                              ),
                            ),
                        ],
                      ),
                      const SizedBox(height: 8),
                      Text(
                        '${al.itemName} (${al.sku})',
                        style: const TextStyle(
                            fontWeight: FontWeight.bold, fontSize: 13),
                      ),
                      const SizedBox(height: 2),
                      Text(
                        '${isVi ? 'Lô' : 'Lot'}: ${al.lotNo ?? "N/A"} • ${isVi ? 'HSD' : 'Exp'}: ${al.expiryDate} • ${isVi ? 'Số lượng' : 'Qty'}: ${al.quantity} ${al.unit}',
                        style: TextStyle(
                          fontSize: 12,
                          color: theme.colorScheme.onSurfaceVariant,
                        ),
                      ),
                      if (isExpired) ...[
                        const SizedBox(height: 8),
                        Align(
                          alignment: Alignment.centerRight,
                          child: FilledButton.tonal(
                            onPressed: () {
                              if (widget.onCreateStockRequest != null) {
                                widget.onCreateStockRequest!(
                                  itemId: al.itemId,
                                  suggestedQty: double.tryParse(al.quantity),
                                );
                              } else if (widget.onNavigate != null) {
                                widget.onNavigate!(3);
                              }
                            },
                            style: FilledButton.styleFrom(
                              visualDensity: VisualDensity.compact,
                              backgroundColor: const Color(0xFFDC2626)
                                  .withValues(alpha: 0.15),
                              shape: RoundedRectangleBorder(
                                  borderRadius: BorderRadius.circular(8)),
                            ),
                            child: Text(isVi ? 'Lập Phiếu Hủy' : 'Create Disposal',
                                style: const TextStyle(
                                    fontSize: 12,
                                    color: Color(0xFFDC2626),
                                    fontWeight: FontWeight.bold)),
                          ),
                        ),
                      ],
                    ],
                  ),
                );
              }

              return Container(
                margin: const EdgeInsets.only(bottom: 8),
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(
                  color: isDark ? const Color(0xFF291B12) : Colors.white,
                  borderRadius: BorderRadius.circular(10),
                  border: Border.all(
                    color: badgeColor.withValues(alpha: 0.25),
                  ),
                ),
                child: Row(
                  children: [
                    Container(
                      padding: const EdgeInsets.symmetric(
                          horizontal: 8, vertical: 3),
                      decoration: BoxDecoration(
                        color: badgeColor,
                        borderRadius: BorderRadius.circular(6),
                      ),
                      child: Text(
                        badgeText,
                        style: const TextStyle(
                          color: Colors.white,
                          fontSize: 10,
                          fontWeight: FontWeight.bold,
                        ),
                      ),
                    ),
                    const SizedBox(width: 10),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            '${al.itemName} (${al.sku})',
                            style: const TextStyle(
                                fontWeight: FontWeight.bold, fontSize: 13),
                          ),
                          Text(
                            '${isVi ? 'Lô' : 'Lot'}: ${al.lotNo ?? "N/A"} • ${isVi ? 'HSD' : 'Exp'}: ${al.expiryDate} • ${isVi ? 'Số lượng' : 'Qty'}: ${al.quantity} ${al.unit}',
                            style: TextStyle(
                              fontSize: 12,
                              color: theme.colorScheme.onSurfaceVariant,
                            ),
                          ),
                        ],
                      ),
                    ),
                    if (isExpired)
                      FilledButton.tonal(
                        onPressed: () {
                          if (widget.onCreateStockRequest != null) {
                            widget.onCreateStockRequest!(
                              itemId: al.itemId,
                              suggestedQty: double.tryParse(al.quantity),
                            );
                          } else if (widget.onNavigate != null) {
                            widget.onNavigate!(3);
                          }
                        },
                        style: FilledButton.styleFrom(
                          visualDensity: VisualDensity.compact,
                          backgroundColor:
                              const Color(0xFFDC2626).withValues(alpha: 0.15),
                          shape: RoundedRectangleBorder(
                              borderRadius: BorderRadius.circular(8)),
                        ),
                        child: Text(isVi ? 'Lập Phiếu Hủy' : 'Create Disposal',
                            style: const TextStyle(
                                fontSize: 12,
                                color: Color(0xFFDC2626),
                                fontWeight: FontWeight.bold)),
                      )
                    else if (isWarning)
                      Container(
                        padding: const EdgeInsets.symmetric(
                            horizontal: 8, vertical: 4),
                        decoration: BoxDecoration(
                          color:
                              const Color(0xFFF59E0B).withValues(alpha: 0.12),
                          borderRadius: BorderRadius.circular(6),
                        ),
                        child: Text(
                          isVi ? 'Ưu tiên dùng' : 'Use First',
                          style: const TextStyle(
                            fontSize: 11,
                            fontWeight: FontWeight.bold,
                            color: Color(0xFFB45309),
                          ),
                        ),
                      ),
                  ],
                ),
              );
            }).toList(),
          ),
        ],
      ),
    );
  }

  Widget _buildKpiCard(
    BuildContext context, {
    required String title,
    required String value,
    required String subtitle,
    required IconData icon,
    required Color color,
    VoidCallback? onTap,
    bool isSelected = false,
  }) {
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;

    final cardContent = Container(
      constraints: const BoxConstraints(minHeight: 110),
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: isSelected
            ? color.withValues(alpha: isDark ? 0.2 : 0.08)
            : (isDark ? const Color(0xFF1E293B) : Colors.white),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(
          color: isSelected
              ? color
              : theme.colorScheme.outlineVariant.withValues(alpha: 0.5),
          width: isSelected ? 2.0 : 1.0,
        ),
        boxShadow: isSelected
            ? [
                BoxShadow(
                  color: color.withValues(alpha: 0.15),
                  blurRadius: 8,
                  offset: const Offset(0, 2),
                ),
              ]
            : null,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Expanded(
                child: FittedBox(
                  fit: BoxFit.scaleDown,
                  alignment: Alignment.centerLeft,
                  child: Text(
                    title,
                    maxLines: 1,
                    style: TextStyle(
                      fontSize: 10.5,
                      fontWeight: FontWeight.w800,
                      color: isSelected ? color : theme.colorScheme.onSurfaceVariant,
                      letterSpacing: 0.5,
                    ),
                  ),
                ),
              ),
              const SizedBox(width: 4),
              Container(
                padding: const EdgeInsets.all(6),
                decoration: BoxDecoration(
                  color: color.withValues(alpha: isSelected ? 0.25 : 0.12),
                  borderRadius: BorderRadius.circular(8),
                ),
                child: Icon(
                  isSelected ? Icons.check_circle_rounded : icon,
                  size: 16,
                  color: color,
                ),
              ),
            ],
          ),
          const SizedBox(height: 8),
          FittedBox(
            fit: BoxFit.scaleDown,
            alignment: Alignment.centerLeft,
            child: Text(
              value,
              style: TextStyle(
                fontSize: 18,
                fontWeight: FontWeight.w900,
                letterSpacing: -0.5,
                color: isSelected ? color : null,
              ),
            ),
          ),
          const SizedBox(height: 4),
          Text(
            isSelected ? '✓ $subtitle' : subtitle,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: TextStyle(
              fontSize: 11,
              fontWeight: isSelected ? FontWeight.w700 : FontWeight.normal,
              color: isSelected ? color : theme.colorScheme.onSurfaceVariant,
            ),
          ),
        ],
      ),
    );

    if (onTap != null) {
      return Material(
        color: Colors.transparent,
        borderRadius: BorderRadius.circular(16),
        child: InkWell(
          borderRadius: BorderRadius.circular(16),
          onTap: onTap,
          child: cardContent,
        ),
      );
    }
    return cardContent;
  }

  Future<_InventoryData> _load(BankOpsRepository repo) async {
    final results = await Future.wait([
      repo.getLocations(),
      repo.getItems(),
      repo.getBalances(),
      repo.getAssets(),
      repo.getLowStockAlerts(),
      repo.getStocktakes(),
      repo.getStockLevels(),
      repo.getExpiryAlerts(days: 7),
    ]);
    return _InventoryData(
      locations: results[0] as List<InventoryLocation>,
      items: results[1] as List<InventoryItem>,
      balances: results[2] as List<StockBalance>,
      assets: results[3] as List<AssetRecord>,
      lowStockAlerts: results[4] as List<LowStockAlertItem>,
      stocktakes: results[5] as List<StocktakeItem>,
      stockLevels: results[6] as List<StockLevelItem>,
      expiryAlerts: results[7] as List<ExpiryAlertItem>,
    );
  }
}

class _InventoryData {
  const _InventoryData({
    required this.locations,
    required this.items,
    required this.balances,
    required this.assets,
    required this.lowStockAlerts,
    required this.stocktakes,
    required this.stockLevels,
    this.expiryAlerts = const [],
  });

  final List<InventoryLocation> locations;
  final List<InventoryItem> items;
  final List<StockBalance> balances;
  final List<AssetRecord> assets;
  final List<LowStockAlertItem> lowStockAlerts;
  final List<StocktakeItem> stocktakes;
  final List<StockLevelItem> stockLevels;
  final List<ExpiryAlertItem> expiryAlerts;
}
