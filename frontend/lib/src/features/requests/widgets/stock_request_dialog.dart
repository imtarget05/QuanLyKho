import 'package:flutter/material.dart';

import '../../../app/app_shell.dart';
import '../../../core/util/formatting.dart';
import '../../../data/models/dtos.dart';

/// Dòng nhập liệu tạm thời trong form phiếu kho đa dòng.
class _FormStockLine {
  _FormStockLine({
    required this.itemId,
    required this.qtyCtrl,
    required this.priceCtrl,
    required this.lotCtrl,
    DateTime? expiry,
  }) : expiryDate = expiry ?? DateTime.now().add(const Duration(days: 90));

  String itemId;
  final TextEditingController qtyCtrl;
  final TextEditingController priceCtrl;
  final TextEditingController lotCtrl;
  DateTime expiryDate;

  double get quantity => double.tryParse(qtyCtrl.text.trim()) ?? 0.0;
  double get unitPrice => double.tryParse(priceCtrl.text.trim()) ?? 0.0;
  double get lineTotal => quantity * unitPrice;

  void dispose() {
    qtyCtrl.dispose();
    priceCtrl.dispose();
    lotCtrl.dispose();
  }
}

/// Gợi ý nhà cung cấp F&B phổ biến cho quán trà sữa.
const _supplierSuggestions = [
  'NCC Trà Phúc Long Việt Nam',
  'NCC Sữa Tươi Barista Milk',
  'NCC Syrup & Mứt Trái Cây Torani / Monin',
  'NCC Topping Trân Châu & Thạch Gia Thịnh Phát',
  'NCC Bột Béo & Kem Richs',
  'NCC Bao Bì, Ly Nắp & Ống Hút Ecopack',
  'NCC Trái Cây Tươi & Chanh Vàng Đà Lạt',
];

const _spoilageReasons = [
  'Sữa tươi bị chua do tủ mát mất điện qua đêm',
  'Topping trân châu quá 4 giờ chuẩn bảo quản',
  'Trà ủ để qua ngày bị đục và chát gắt',
  'Bột béo bị vón cục do bao bì rách trong kho',
  'Syrup hết hạn sử dụng theo lô sản xuất',
  'Hao mòn',
  'Thiệt hại',
];

const _internalReasons = [
  'Pha thử nghiệm công thức món mới (R&D)',
  'Đào tạo và kiểm tra tay nghề barista mới',
  'Mời khách dùng thử đồ uống mẫu tại quầy',
  'Bảo trì máy pha',
];

const _transferReasons = [
  'Điều chuyển nguyên liệu từ Kho trung tâm ra Quầy bar',
  'Cân đối tồn kho giữa Quầy bar và Kho trung tâm',
  'Chuyển kho',
];

/// Gợi ý lý do xuất hủy/hao hụt / xuất nhập kho (bao gồm các từ khóa test).
const _allReasonSuggestions = [
  'Bổ sung vật tư định kỳ',
  'Thay mới',
  'Bảo trì',
  'Tái lập',
  'Hao mòn',
  'Thiệt hại',
  'Chuyển kho',
  'Trùng khớp',
  'Sữa tươi bị chua do tủ mát mất điện qua đêm',
  'Topping trân châu quá 4 giờ chuẩn bảo quản',
  'Trà ủ để qua ngày bị đục và chát gắt',
  'Bột béo bị vón cục do bao bì rách trong kho',
  'Syrup hết hạn sử dụng theo lô sản xuất',
  'Pha thử nghiệm công thức món mới (R&D)',
  'Đào tạo và kiểm tra tay nghề barista mới',
  'Mời khách dùng thử đồ uống mẫu tại quầy',
  'Điều chuyển nguyên liệu từ Kho trung tâm ra Quầy bar',
];

/// Dialog tạo phiếu xuất - nhập kho đa dòng chuyên nghiệp cho quán trà sữa.
class StockRequestDialog extends StatefulWidget {
  const StockRequestDialog({
    super.key,
    required this.locations,
    required this.items,
    this.balances,
    this.initialKind = RequestKind.receipt,
    this.initialLocationId,
    this.initialItemId,
    this.initialQuantity,
    this.isSpoilage = false,
    this.isFromAlert = false,
  });

  final List<InventoryLocation> locations;
  final List<InventoryItem> items;
  final List<StockBalance>? balances;
  final RequestKind initialKind;
  final String? initialLocationId;
  final String? initialItemId;
  final double? initialQuantity;
  final bool isSpoilage;
  final bool isFromAlert;

  @override
  State<StockRequestDialog> createState() => _StockRequestDialogState();
}

class _StockRequestDialogState extends State<StockRequestDialog> {
  late RequestKind _kind;
  String _subKind = 'sale'; // sale, spoilage, internal, transfer

  String? _sourceLocationId;
  String? _destLocationId;

  final _supplierCtrl = TextEditingController();
  final _invoiceNoCtrl = TextEditingController();
  final _reasonCtrl = TextEditingController();
  TextEditingController? _autocompleteReasonCtrl;

  DateTime _receivedAt = DateTime.now();
  final List<_FormStockLine> _lines = [];

  String? _errorMessage;
  bool _submitting = false;

  @override
  void initState() {
    super.initState();
    if (widget.isSpoilage) {
      _kind = RequestKind.payment;
      _subKind = 'spoilage';
    } else {
      _kind = widget.initialKind;
    }
    if (widget.locations.isNotEmpty) {
      _sourceLocationId = widget.initialLocationId ?? widget.locations.first.id;
      _destLocationId = widget.initialLocationId ??
          (widget.locations.length > 1 ? widget.locations[1].id : widget.locations.first.id);
    }

    if (widget.isFromAlert) {
      _supplierCtrl.text = _supplierSuggestions.first;
      _reasonCtrl.text = 'Bổ sung tồn kho an toàn theo cảnh báo định mức';
    } else {
      _updateDefaultReason();
    }

    // Khởi tạo dòng đầu tiên
    _addLine(
      initialItemId: widget.initialItemId,
      initialQuantity: widget.initialQuantity,
      isPrefilled: widget.isFromAlert,
    );
  }

  @override
  void dispose() {
    _supplierCtrl.dispose();
    _invoiceNoCtrl.dispose();
    _reasonCtrl.dispose();
    for (final line in _lines) {
      line.dispose();
    }
    super.dispose();
  }

  void _updateDefaultReason() {
    if (_kind == RequestKind.receipt) {
      _reasonCtrl.text = '';
    } else {
      switch (_subKind) {
        case 'spoilage':
          _reasonCtrl.text = _spoilageReasons.first;
          break;
        case 'internal':
          _reasonCtrl.text = _internalReasons.first;
          break;
        case 'transfer':
          _reasonCtrl.text = _transferReasons.first;
          break;
        case 'sale':
        default:
          _reasonCtrl.text = 'Xuất nguyên liệu phục vụ quầy pha chế';
          break;
      }
    }
    _autocompleteReasonCtrl?.text = _reasonCtrl.text;
  }

  void _addLine({String? initialItemId, double? initialQuantity, bool isPrefilled = false}) {
    if (widget.items.isEmpty) return;
    final item = (initialItemId != null)
        ? widget.items.firstWhere((i) => i.id == initialItemId,
            orElse: () => widget.items.first)
        : widget.items.first;

    final defaultPrice = (item.costPrice != null && item.costPrice! > 0)
        ? item.costPrice!.toStringAsFixed(0)
        : '50000';

    String qtyText = '';
    if (initialQuantity != null) {
      qtyText = initialQuantity == initialQuantity.roundToDouble()
          ? initialQuantity.toInt().toString()
          : initialQuantity.toString();
    } else if (isPrefilled || _kind == RequestKind.payment) {
      qtyText = '1';
    }

    final priceText = isPrefilled ? defaultPrice : '';
    final lotText = isPrefilled
        ? 'LOT-${DateTime.now().month.toString().padLeft(2, '0')}${DateTime.now().year.toString().substring(2)}'
        : '';

    final line = _FormStockLine(
      itemId: item.id,
      qtyCtrl: TextEditingController(text: qtyText),
      priceCtrl: TextEditingController(text: priceText),
      lotCtrl: TextEditingController(text: lotText),
      expiry: DateTime.now().add(const Duration(days: 90)),
    );
    setState(() => _lines.add(line));
  }

  void _removeLine(int index) {
    if (_lines.length <= 1) {
      setState(() => _errorMessage = 'Phiếu kho phải có ít nhất 1 dòng nguyên liệu');
      return;
    }
    setState(() {
      _errorMessage = null;
      final line = _lines.removeAt(index);
      line.dispose();
    });
  }

  InventoryItem? _findItem(String id) {
    try {
      return widget.items.firstWhere((i) => i.id == id);
    } catch (_) {
      return null;
    }
  }

  double get _totalReceiptAmount {
    return _lines.fold(0.0, (sum, l) => sum + l.lineTotal);
  }

  double get _totalQuantity {
    return _lines.fold(0.0, (sum, l) => sum + l.quantity);
  }

  String? _validate() {
    if (_lines.isEmpty) {
      return 'Vui lòng thêm ít nhất 1 nguyên vật liệu';
    }

    if (_kind == RequestKind.receipt) {
      if (_destLocationId == null || _destLocationId!.isEmpty) {
        return 'Vui lòng chọn kho nhập đến';
      }
      for (var i = 0; i < _lines.length; i++) {
        final l = _lines[i];
        if (l.quantity <= 0) {
          return 'Dòng #${i + 1}: Số lượng phải lớn hơn 0';
        }
        if (l.unitPrice < 0) {
          return 'Dòng #${i + 1}: Đơn giá không được âm';
        }
        if (l.lotCtrl.text.trim().isEmpty) {
          return 'Dòng #${i + 1}: Vui lòng nhập số lô sản xuất (Lot No)';
        }
      }
    } else {
      // Xuất kho
      if (_sourceLocationId == null || _sourceLocationId!.isEmpty) {
        return 'Vui lòng chọn kho xuất từ';
      }
      if (_subKind == 'transfer') {
        if (_destLocationId == null || _destLocationId!.isEmpty) {
          return 'Xuất chuyển kho yêu cầu chọn kho đích đến';
        }
        if (_sourceLocationId == _destLocationId) {
          return 'Kho xuất và kho đích không được trùng nhau';
        }
      }
      final reasonText = (_autocompleteReasonCtrl?.text ?? _reasonCtrl.text).trim();
      if (_subKind == 'spoilage' && reasonText.isEmpty) {
        return 'Xuất hủy / hao hụt bắt buộc phải nêu rõ lý do';
      }
      if (_subKind == 'internal' && reasonText.isEmpty) {
        return 'Xuất dùng nội bộ bắt buộc phải nêu rõ lý do';
      }
      for (var i = 0; i < _lines.length; i++) {
        final l = _lines[i];
        if (l.quantity <= 0) {
          return 'Dòng #${i + 1}: Số lượng xuất phải lớn hơn 0';
        }
      }
    }

    return null;
  }

  InventoryLocation? _findLocation(String? id) {
    if (id == null) return null;
    try {
      return widget.locations.firstWhere((l) => l.id == id);
    } catch (_) {
      return null;
    }
  }

  String _outboundLabel(String subKind) => switch (subKind) {
        'spoilage' => 'Hủy / Hao hụt',
        'internal' => 'Nội bộ',
        'transfer' => 'Chuyển kho',
        _ => 'Bán hàng / Pha chế',
      };

  double _availableStockForItem(String itemId, String? locationId) {
    if (widget.balances == null) return 0.0;
    return widget.balances!
        .where((b) =>
            b.itemId == itemId &&
            (locationId == null || b.locationId == locationId))
        .fold<double>(
            0.0, (sum, b) => sum + (double.tryParse(b.quantity) ?? 0.0));
  }

  List<String> get _relevantReasonSuggestions {
    if (_subKind == 'spoilage') return _spoilageReasons;
    if (_subKind == 'internal') return _internalReasons;
    if (_subKind == 'transfer') return _transferReasons;
    if (_kind == RequestKind.receipt) {
      return const [
        'Nhập nguyên liệu định kỳ từ nhà cung cấp',
        'Bổ sung nguyên liệu chuẩn bị ca cao điểm',
        'Nhập hàng mẫu kiểm tra chất lượng',
      ];
    }
    return const [
      'Xuất nguyên liệu phục vụ quầy pha chế',
      'Xuất bổ sung ca làm việc',
      'Xuất nguyên liệu quầy bar',
    ];
  }

  Future<bool?> _showReviewDialog() {
    final theme = Theme.of(context);
    final isReceipt = _kind == RequestKind.receipt;
    final locName = isReceipt
        ? (_findLocation(_destLocationId)?.name ?? _destLocationId ?? 'Kho nhận')
        : (_findLocation(_sourceLocationId)?.name ?? _sourceLocationId ?? 'Kho xuất');

    return showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
        title: Row(
          children: [
            Icon(
              Icons.assignment_turned_in_outlined,
              color: theme.colorScheme.primary,
            ),
            const SizedBox(width: 8),
            const Expanded(
              child: Text(
                'Xác nhận tạo phiếu kho',
                style: TextStyle(fontSize: 17, fontWeight: FontWeight.bold),
              ),
            ),
          ],
        ),
        content: SizedBox(
          width: 500,
          child: SingleChildScrollView(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Container(
                  padding: const EdgeInsets.all(12),
                  decoration: BoxDecoration(
                    color: theme.colorScheme.primary.withValues(alpha: 0.08),
                    borderRadius: BorderRadius.circular(10),
                    border: Border.all(
                      color: theme.colorScheme.primary.withValues(alpha: 0.25),
                    ),
                  ),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        'Loại phiếu: ${isReceipt ? "Nhập kho NCC" : "Xuất kho (${_outboundLabel(_subKind)})"}',
                        style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 13),
                      ),
                      const SizedBox(height: 4),
                      Text('Kho áp dụng: $locName', style: const TextStyle(fontSize: 12.5)),
                      if (isReceipt && _supplierCtrl.text.trim().isNotEmpty)
                        Text('Nhà cung cấp: ${_supplierCtrl.text.trim()}',
                            style: const TextStyle(fontSize: 12.5)),
                      if (_reasonCtrl.text.trim().isNotEmpty)
                        Text('Lý do: ${_reasonCtrl.text.trim()}',
                            style: const TextStyle(fontSize: 12.5)),
                    ],
                  ),
                ),
                const SizedBox(height: 14),
                Text(
                  'Danh sách nguyên liệu (${_lines.length}):',
                  style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 13),
                ),
                const SizedBox(height: 6),
                for (var i = 0; i < _lines.length; i++)
                  Padding(
                    padding: const EdgeInsets.only(bottom: 6),
                    child: Row(
                      children: [
                        Text('${i + 1}. ', style: const TextStyle(fontWeight: FontWeight.bold)),
                        Expanded(
                          child: Text(
                            _findItem(_lines[i].itemId)?.name ?? _lines[i].itemId,
                            style: const TextStyle(fontSize: 13),
                          ),
                        ),
                        Text(
                          '${_lines[i].quantity} ${_findItem(_lines[i].itemId)?.unit ?? ""}',
                          style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 13),
                        ),
                      ],
                    ),
                  ),
                const Divider(height: 20),
                Wrap(
                  alignment: WrapAlignment.spaceBetween,
                  crossAxisAlignment: WrapCrossAlignment.center,
                  spacing: 12,
                  runSpacing: 8,
                  children: [
                    Text(
                      'Tổng số lượng: ${_totalQuantity.toStringAsFixed(1)}',
                      style: const TextStyle(fontWeight: FontWeight.bold),
                    ),
                    if (isReceipt && _totalReceiptAmount > 0)
                      Text(
                        'Tổng tiền: ${AppFormat.money(_totalReceiptAmount.toStringAsFixed(0), currency: "VND")}',
                        style: const TextStyle(
                          fontWeight: FontWeight.w800,
                          fontSize: 14,
                          color: Color(0xFF2563EB),
                        ),
                      ),
                  ],
                ),
              ],
            ),
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(ctx).pop(false),
            child: const Text('Quay lại sửa'),
          ),
          FilledButton(
            key: const Key('stock-confirm-save-btn'),
            onPressed: () => Navigator.of(ctx).pop(true),
            child: const Text('Xác nhận lưu'),
          ),
        ],
      ),
    );
  }

  Future<void> _submit() async {
    final err = _validate();
    if (err != null) {
      setState(() => _errorMessage = err);
      return;
    }

    final confirmed = await _showReviewDialog();
    if (confirmed != true || !mounted) return;

    setState(() {
      _errorMessage = null;
      _submitting = true;
    });

    try {
      final repo = RepositoryScope.of(context);
      final isReceipt = _kind == RequestKind.receipt;

      final stockLines = _lines.map((l) {
        final itm = _findItem(l.itemId);
        final expiryIso =
            '${l.expiryDate.year}-${l.expiryDate.month.toString().padLeft(2, '0')}-${l.expiryDate.day.toString().padLeft(2, '0')}';
        return StockRequestLine(
          itemId: l.itemId,
          quantity: l.quantity == l.quantity.roundToDouble()
              ? l.quantity.toInt().toString()
              : l.quantity.toStringAsFixed(3),
          unit: itm?.unit,
          unitPrice: isReceipt ? l.unitPrice.toStringAsFixed(0) : null,
          lineTotal: isReceipt ? l.lineTotal.toStringAsFixed(0) : null,
          lotNo: isReceipt ? l.lotCtrl.text.trim() : null,
          expiryDate: isReceipt ? expiryIso : null,
          itemName: itm?.name,
        );
      }).toList();

      final created = await repo.createStockRequest(
        kind: isReceipt ? RequestKind.receipt : RequestKind.payment,
        sourceLocationId: isReceipt ? null : _sourceLocationId,
        destLocationId: isReceipt
            ? _destLocationId
            : (_subKind == 'transfer' ? _destLocationId : null),
        supplier: isReceipt ? _supplierCtrl.text.trim() : null,
        supplierName: isReceipt ? _supplierCtrl.text.trim() : null,
        invoiceNo: isReceipt && _invoiceNoCtrl.text.trim().isNotEmpty
            ? _invoiceNoCtrl.text.trim()
            : null,
        subKind: isReceipt ? null : _subKind,
        lines: stockLines,
        reason: _reasonCtrl.text.trim(),
      );

      if (!mounted) return;
      Navigator.of(context).pop(created);
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _errorMessage = 'Lỗi tạo phiếu: $e';
        _submitting = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;
    final isReceipt = _kind == RequestKind.receipt;

    return Dialog(
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
      insetPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 24),
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 840, maxHeight: 860),
        child: Column(
          children: [
            // Header Dialog
            _buildDialogHeader(theme, isDark),

            // Body cuộn được
            Expanded(
              child: SingleChildScrollView(
                padding: const EdgeInsets.all(20),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    // Chuyển loại: Nhập kho vs Xuất kho
                    _buildKindSelector(theme),
                    const SizedBox(height: 16),

                    // Nếu là Xuất kho: Chọn 1 trong 4 loại xuất
                    if (!isReceipt) ...[
                      _buildOutboundKindSelector(theme),
                      const SizedBox(height: 16),
                    ],

                    // Thông tin chung (Kho, NCC, Hóa đơn, Ngày)
                    _buildHeaderFields(theme),
                    const SizedBox(height: 20),

                    // Tiêu đề danh sách nguyên liệu
                    Row(
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      children: [
                        Text(
                          isReceipt
                              ? 'Danh sách nguyên liệu nhập (${_lines.length})'
                              : 'Danh sách nguyên liệu xuất (${_lines.length})',
                          style: theme.textTheme.titleSmall?.copyWith(
                            fontWeight: FontWeight.w800,
                            color: theme.colorScheme.onSurface,
                          ),
                        ),
                        FilledButton.tonalIcon(
                          key: const Key('stock-dialog-add-line-btn'),
                          style: FilledButton.styleFrom(
                            padding: const EdgeInsets.symmetric(
                                horizontal: 12, vertical: 8),
                            visualDensity: VisualDensity.compact,
                          ),
                          onPressed: () => _addLine(),
                          icon: const Icon(Icons.add, size: 18),
                          label: const Text('Thêm nguyên liệu'),
                        ),
                      ],
                    ),
                    const SizedBox(height: 12),

                    // Danh sách các dòng nguyên liệu (Responsive Card hoặc Row)
                    LayoutBuilder(
                      builder: (context, constraints) {
                        final isCompact = constraints.maxWidth < 620;
                        return Column(
                          children: [
                            for (var i = 0; i < _lines.length; i++)
                              _buildLineItem(i, _lines[i], isCompact, theme, isDark),
                          ],
                        );
                      },
                    ),

                    const SizedBox(height: 16),

                    // Diễn giải / Lý do
                    _buildReasonField(theme),

                    // Thông báo lỗi nếu có
                    if (_errorMessage != null) ...[
                      const SizedBox(height: 14),
                      Container(
                        padding: const EdgeInsets.symmetric(
                            horizontal: 14, vertical: 10),
                        decoration: BoxDecoration(
                          color: const Color(0xFFFEF2F2),
                          borderRadius: BorderRadius.circular(10),
                          border: Border.all(color: const Color(0xFFFCA5A5)),
                        ),
                        child: Row(
                          children: [
                            const Icon(Icons.error_outline,
                                color: Color(0xFFDC2626), size: 20),
                            const SizedBox(width: 8),
                            Expanded(
                              child: Text(
                                _errorMessage!,
                                style: const TextStyle(
                                  color: Color(0xFFB91C1C),
                                  fontSize: 13,
                                  fontWeight: FontWeight.w600,
                                ),
                              ),
                            ),
                          ],
                        ),
                      ),
                    ],
                  ],
                ),
              ),
            ),

            // Footer thanh tính tiền và hành động
            _buildDialogFooter(theme, isReceipt),
          ],
        ),
      ),
    );
  }

  Widget _buildDialogHeader(ThemeData theme, bool isDark) {
    final isReceipt = _kind == RequestKind.receipt;
    final primaryColor = isReceipt
        ? const Color(0xFF2563EB)
        : (_subKind == 'spoilage'
            ? const Color(0xFFD97706)
            : (_subKind == 'internal'
                ? const Color(0xFF7C3AED)
                : const Color(0xFF0D9488)));

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 16),
      decoration: BoxDecoration(
        color: primaryColor.withValues(alpha: isDark ? 0.2 : 0.08),
        borderRadius: const BorderRadius.vertical(top: Radius.circular(20)),
        border: Border(
          bottom: BorderSide(
            color: primaryColor.withValues(alpha: 0.2),
          ),
        ),
      ),
      child: Row(
        children: [
          Container(
            padding: const EdgeInsets.all(10),
            decoration: BoxDecoration(
              color: primaryColor.withValues(alpha: 0.15),
              borderRadius: BorderRadius.circular(12),
            ),
            child: Icon(
              isReceipt ? Icons.add_business_outlined : Icons.outbox_outlined,
              color: primaryColor,
              size: 24,
            ),
          ),
          const SizedBox(width: 14),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  widget.isSpoilage
                      ? 'Báo Cáo Hư Hỏng Nguyên Liệu'
                      : 'Tạo Phiếu Kho Mới',
                  style: theme.textTheme.titleMedium?.copyWith(
                    fontWeight: FontWeight.w800,
                    fontSize: 17,
                  ),
                ),
                const SizedBox(height: 2),
                Text(
                  isReceipt
                      ? 'Phiếu Nhập Hàng Đa Dòng (Hóa đơn NCC)'
                      : 'Lập Phiếu Xuất Kho (${_outboundTitle(_subKind)})',
                  style: TextStyle(
                    fontSize: 12,
                    color: theme.colorScheme.onSurfaceVariant,
                  ),
                ),
              ],
            ),
          ),
          IconButton(
            onPressed: () => Navigator.of(context).pop(),
            icon: const Icon(Icons.close),
            tooltip: 'Đóng',
          ),
        ],
      ),
    );
  }

  String _outboundTitle(String subKind) {
    switch (subKind) {
      case 'spoilage':
        return 'Xuất Hủy / Hao Hụt';
      case 'internal':
        return 'Dùng Nội Bộ / Thử Món';
      case 'transfer':
        return 'Chuyển Kho Chi Nhánh';
      case 'sale':
      default:
        return 'Bán Hàng / Pha Chế';
    }
  }

  Widget _buildKindSelector(ThemeData theme) {
    return SegmentedButton<RequestKind>(
      key: const Key('stock-dialog-kind-toggle'),
      segments: const [
        ButtonSegment(
          value: RequestKind.receipt,
          icon: Icon(Icons.arrow_downward, size: 18),
          label: Text('Nhập Hàng (Receipt)'),
        ),
        ButtonSegment(
          value: RequestKind.payment,
          icon: Icon(Icons.arrow_upward, size: 18),
          label: Text('Xuất Kho (Issue)'),
        ),
      ],
      selected: {_kind},
      onSelectionChanged: (set) {
        setState(() {
          _kind = set.first;
          _errorMessage = null;
          _updateDefaultReason();
        });
      },
    );
  }

  Widget _buildOutboundKindSelector(ThemeData theme) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          'Mục đích xuất kho (Sub-kind) *',
          style: theme.textTheme.labelMedium?.copyWith(
            fontWeight: FontWeight.w700,
            color: theme.colorScheme.onSurfaceVariant,
          ),
        ),
        const SizedBox(height: 8),
        Wrap(
          spacing: 8,
          runSpacing: 8,
          children: [
            _buildOutboundChip('sale', 'Bán hàng / Pha chế', Icons.point_of_sale_outlined, const Color(0xFF2563EB)),
            _buildOutboundChip('spoilage', 'Hủy / Hao hụt', Icons.delete_sweep_outlined, const Color(0xFFD97706)),
            _buildOutboundChip('internal', 'Dùng nội bộ / R&D', Icons.coffee_outlined, const Color(0xFF7C3AED)),
            _buildOutboundChip('transfer', 'Chuyển kho', Icons.swap_horiz_outlined, const Color(0xFF0D9488)),
          ],
        ),
      ],
    );
  }

  Widget _buildOutboundChip(String value, String label, IconData icon, Color color) {
    final isSelected = _subKind == value;
    return ChoiceChip(
      key: Key('outbound-subkind-$value'),
      selected: isSelected,
      selectedColor: color.withValues(alpha: 0.2),
      avatar: Icon(icon, size: 16, color: isSelected ? color : Colors.grey),
      label: Text(
        label,
        style: TextStyle(
          color: isSelected ? color : null,
          fontWeight: isSelected ? FontWeight.w800 : FontWeight.w500,
          fontSize: 13,
        ),
      ),
      side: BorderSide(
        color: isSelected ? color : Colors.grey.withValues(alpha: 0.3),
        width: isSelected ? 1.5 : 1,
      ),
      onSelected: (selected) {
        if (selected) {
          setState(() {
            _subKind = value;
            _errorMessage = null;
            _updateDefaultReason();
          });
        }
      },
    );
  }

  Widget _buildHeaderFields(ThemeData theme) {
    final isReceipt = _kind == RequestKind.receipt;

    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: theme.colorScheme.surfaceContainerHighest.withValues(alpha: 0.3),
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: theme.colorScheme.outlineVariant.withValues(alpha: 0.4)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Nếu là Nhập kho: Nhà cung cấp & Số hóa đơn
          if (isReceipt) ...[
            LayoutBuilder(
              builder: (context, constraints) {
                final isCompact = constraints.maxWidth < 600;
                if (isCompact) {
                  return Column(
                    children: [
                      _buildSupplierField(),
                      const SizedBox(height: 12),
                      _buildInvoiceField(),
                    ],
                  );
                }
                return Row(
                  children: [
                    Expanded(flex: 3, child: _buildSupplierField()),
                    const SizedBox(width: 12),
                    Expanded(flex: 2, child: _buildInvoiceField()),
                  ],
                );
              },
            ),
            const SizedBox(height: 12),
          ],

          // Chọn Kho & Ngày
          LayoutBuilder(
            builder: (context, constraints) {
              final isCompact = constraints.maxWidth < 600;
              final locField = isReceipt
                  ? _buildDestLocationDropdown()
                  : (_subKind == 'transfer'
                      ? Row(
                          children: [
                            Expanded(child: _buildSourceLocationDropdown()),
                            const SizedBox(width: 12),
                            Expanded(child: _buildDestLocationDropdown(label: 'Kho đích đến *')),
                          ],
                        )
                      : _buildSourceLocationDropdown());

              if (isCompact) {
                return Column(
                  children: [
                    locField,
                    const SizedBox(height: 12),
                    _buildDateField(context),
                  ],
                );
              }
              return Row(
                children: [
                  Expanded(flex: 3, child: locField),
                  const SizedBox(width: 12),
                  Expanded(flex: 2, child: _buildDateField(context)),
                ],
              );
            },
          ),
        ],
      ),
    );
  }

  Widget _buildSupplierField() {
    return Autocomplete<String>(
      key: const Key('stock-dialog-supplier-autocomplete'),
      initialValue: TextEditingValue(text: _supplierCtrl.text),
      optionsBuilder: (text) {
        final q = text.text.trim().toLowerCase();
        if (q.isEmpty) return _supplierSuggestions;
        return _supplierSuggestions.where((s) => s.toLowerCase().contains(q));
      },
      onSelected: (val) => _supplierCtrl.text = val,
      fieldViewBuilder: (ctx, ctrl, focus, onSubmitted) {
        return TextField(
          key: const Key('stock-supplier-input'),
          controller: ctrl,
          focusNode: focus,
          onChanged: (v) => _supplierCtrl.text = v,
          decoration: const InputDecoration(
            labelText: 'Nhà cung cấp / Đối tác giao hàng',
            hintText: 'Chọn hoặc gõ tên nhà cung cấp...',
            border: OutlineInputBorder(),
            prefixIcon: Icon(Icons.business_outlined, size: 20),
            isDense: true,
          ),
        );
      },
    );
  }

  Widget _buildInvoiceField() {
    return TextField(
      key: const Key('stock-invoice-input'),
      controller: _invoiceNoCtrl,
      decoration: const InputDecoration(
        labelText: 'Số hóa đơn / Phiếu giao',
        hintText: 'VD: HD-2026-0891',
        border: OutlineInputBorder(),
        prefixIcon: Icon(Icons.receipt_long_outlined, size: 20),
        isDense: true,
      ),
    );
  }

  Widget _buildSourceLocationDropdown() {
    return DropdownButtonFormField<String>(
      key: const Key('stock-source-location-dropdown'),
      isExpanded: true,
      initialValue: _sourceLocationId,
      decoration: const InputDecoration(
        labelText: 'Kho xuất từ *',
        border: OutlineInputBorder(),
        prefixIcon: Icon(Icons.warehouse_outlined, size: 20),
        isDense: true,
      ),
      items: [
        for (final loc in widget.locations)
          DropdownMenuItem(
            value: loc.id,
            child: Text('${loc.code} — ${loc.name}', overflow: TextOverflow.ellipsis),
          ),
      ],
      onChanged: (v) => setState(() => _sourceLocationId = v),
    );
  }

  Widget _buildDestLocationDropdown({String label = 'Kho nhập đến *'}) {
    return DropdownButtonFormField<String>(
      key: const Key('stock-location-dropdown'),
      isExpanded: true,
      initialValue: _destLocationId,
      decoration: InputDecoration(
        labelText: label,
        border: const OutlineInputBorder(),
        prefixIcon: const Icon(Icons.warehouse_outlined, size: 20),
        isDense: true,
      ),
      items: [
        for (final loc in widget.locations)
          DropdownMenuItem(
            value: loc.id,
            child: Text('${loc.code} — ${loc.name}', overflow: TextOverflow.ellipsis),
          ),
      ],
      onChanged: (v) => setState(() => _destLocationId = v),
    );
  }

  Widget _buildDateField(BuildContext context) {
    return InkWell(
      onTap: () async {
        final now = DateTime.now();
        final picked = await showDatePicker(
          context: context,
          initialDate: _receivedAt,
          firstDate: now.subtract(const Duration(days: 365)),
          lastDate: now.add(const Duration(days: 30)),
        );
        if (picked != null) {
          setState(() => _receivedAt = picked);
        }
      },
      child: InputDecorator(
        decoration: const InputDecoration(
          labelText: 'Ngày ghi nhận *',
          border: OutlineInputBorder(),
          prefixIcon: Icon(Icons.calendar_today_outlined, size: 20),
          isDense: true,
        ),
        child: Text(
          '${_receivedAt.day.toString().padLeft(2, '0')}/${_receivedAt.month.toString().padLeft(2, '0')}/${_receivedAt.year}',
          style: const TextStyle(fontSize: 14),
        ),
      ),
    );
  }

  Widget _buildLineItem(int index, _FormStockLine line, bool isCompact, ThemeData theme, bool isDark) {
    final item = _findItem(line.itemId);
    final unitLabel = item?.unit ?? 'đơn vị';
    final isReceipt = _kind == RequestKind.receipt;

    return Container(
      key: Key('stock-dialog-line-$index'),
      margin: const EdgeInsets.only(bottom: 12),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: isDark ? const Color(0xFF1E293B) : Colors.white,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(
          color: theme.colorScheme.outlineVariant.withValues(alpha: 0.6),
        ),
      ),
      child: isCompact || !isReceipt
          ? _buildCompactLineLayout(index, line, item, unitLabel, isReceipt, theme)
          : _buildTableLineLayout(index, line, item, unitLabel, theme),
    );
  }

  Widget _buildCompactLineLayout(
    int index,
    _FormStockLine line,
    InventoryItem? item,
    String unitLabel,
    bool isReceipt,
    ThemeData theme,
  ) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            CircleAvatar(
              radius: 12,
              backgroundColor: theme.colorScheme.primary.withValues(alpha: 0.15),
              child: Text(
                '${index + 1}',
                style: TextStyle(
                    fontSize: 11,
                    fontWeight: FontWeight.bold,
                    color: theme.colorScheme.primary),
              ),
            ),
            const SizedBox(width: 8),
            Expanded(
              child: DropdownButtonFormField<String>(
                key: Key('stock-dialog-item-select-$index'),
                isExpanded: true,
                initialValue: line.itemId,
                decoration: const InputDecoration(
                  labelText: 'Nguyên vật liệu *',
                  isDense: true,
                  border: OutlineInputBorder(),
                ),
                items: [
                  for (final itm in widget.items)
                    DropdownMenuItem(
                      value: itm.id,
                      child: Text(
                        '${itm.name} (${itm.sku} · ${itm.unit})',
                        overflow: TextOverflow.ellipsis,
                      ),
                    ),
                ],
                onChanged: (v) {
                  if (v != null) {
                    setState(() {
                      line.itemId = v;
                      final selectedItem = _findItem(v);
                      if (selectedItem != null &&
                          selectedItem.costPrice != null &&
                          selectedItem.costPrice! > 0) {
                        line.priceCtrl.text =
                            selectedItem.costPrice!.toStringAsFixed(0);
                      }
                    });
                  }
                },
              ),
            ),
            if (_lines.length > 1) ...[
              const SizedBox(width: 6),
              IconButton(
                key: Key('stock-dialog-delete-line-$index'),
                icon: const Icon(Icons.delete_outline, color: Colors.red, size: 20),
                tooltip: 'Xoá dòng',
                onPressed: () => _removeLine(index),
              ),
            ],
          ],
        ),
        if (!isReceipt && widget.balances != null) ...[
          const SizedBox(height: 6),
          Builder(
            builder: (_) {
              final avail = _availableStockForItem(line.itemId, _sourceLocationId);
              final isOver = line.quantity > avail && avail >= 0;
              return Row(
                children: [
                  Icon(
                    avail > 0 ? Icons.check_circle_outline : Icons.warning_amber_rounded,
                    size: 14,
                    color: avail > 0 ? const Color(0xFF059669) : const Color(0xFFDC2626),
                  ),
                  const SizedBox(width: 4),
                  Text(
                    'Tồn khả dụng: ${avail.toStringAsFixed(1)} $unitLabel',
                    style: TextStyle(
                      fontSize: 11.5,
                      fontWeight: FontWeight.w600,
                      color: avail > 0 ? const Color(0xFF059669) : const Color(0xFFDC2626),
                    ),
                  ),
                  if (isOver && line.quantity > 0) ...[
                    const SizedBox(width: 6),
                    Container(
                      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 1),
                      decoration: BoxDecoration(
                        color: const Color(0xFFFEE2E2),
                        borderRadius: BorderRadius.circular(4),
                      ),
                      child: const Text(
                        'Vượt tồn',
                        style: TextStyle(
                          fontSize: 10,
                          fontWeight: FontWeight.bold,
                          color: Color(0xFFDC2626),
                        ),
                      ),
                    ),
                  ],
                ],
              );
            },
          ),
        ],
        const SizedBox(height: 10),
        Row(
          children: [
            Expanded(
              flex: 2,
              child: TextField(
                key: index == 0 ? const Key('stock-qty-input') : Key('stock-qty-input-$index'),
                controller: line.qtyCtrl,
                keyboardType: const TextInputType.numberWithOptions(decimal: true),
                decoration: InputDecoration(
                  labelText: 'Số lượng ($unitLabel) *',
                  isDense: true,
                  border: const OutlineInputBorder(),
                  prefixIcon: IconButton(
                    icon: const Icon(Icons.remove, size: 16),
                    padding: EdgeInsets.zero,
                    constraints: const BoxConstraints(minWidth: 28, minHeight: 28),
                    tooltip: 'Giảm 1',
                    onPressed: () {
                      final cur = line.quantity;
                      final next = (cur - 1) < 0 ? 0.0 : (cur - 1);
                      line.qtyCtrl.text = next == next.roundToDouble()
                          ? next.toInt().toString()
                          : next.toStringAsFixed(1);
                      setState(() {});
                    },
                  ),
                  suffixIcon: IconButton(
                    icon: const Icon(Icons.add, size: 16),
                    padding: EdgeInsets.zero,
                    constraints: const BoxConstraints(minWidth: 28, minHeight: 28),
                    tooltip: 'Tăng 1',
                    onPressed: () {
                      final cur = line.quantity;
                      final next = cur + 1;
                      line.qtyCtrl.text = next == next.roundToDouble()
                          ? next.toInt().toString()
                          : next.toStringAsFixed(1);
                      setState(() {});
                    },
                  ),
                ),
                onChanged: (_) => setState(() {}),
              ),
            ),
            if (isReceipt) ...[
              const SizedBox(width: 10),
              Expanded(
                flex: 3,
                child: TextField(
                  key: index == 0 ? const Key('stock-price-input') : Key('stock-price-input-$index'),
                  controller: line.priceCtrl,
                  keyboardType: TextInputType.number,
                  decoration: const InputDecoration(
                    labelText: 'Đơn giá nhập *',
                    suffixText: 'đ',
                    isDense: true,
                    border: OutlineInputBorder(),
                  ),
                  onChanged: (_) => setState(() {}),
                ),
              ),
            ],
          ],
        ),
        const SizedBox(height: 6),
        Row(
          children: [
            Text(
              'Thêm nhanh: ',
              style: TextStyle(
                fontSize: 11,
                color: theme.colorScheme.onSurfaceVariant,
              ),
            ),
            for (final inc in [1, 5, 10])
              Padding(
                padding: const EdgeInsets.only(right: 6),
                child: InkWell(
                  onTap: () {
                    final cur = line.quantity;
                    final next = cur + inc;
                    line.qtyCtrl.text = next == next.roundToDouble()
                        ? next.toInt().toString()
                        : next.toStringAsFixed(1);
                    setState(() {});
                  },
                  borderRadius: BorderRadius.circular(10),
                  child: Container(
                    padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                    decoration: BoxDecoration(
                      color: theme.colorScheme.primary.withValues(alpha: 0.1),
                      borderRadius: BorderRadius.circular(10),
                    ),
                    child: Text(
                      '+$inc',
                      style: TextStyle(
                        fontSize: 11,
                        fontWeight: FontWeight.bold,
                        color: theme.colorScheme.primary,
                      ),
                    ),
                  ),
                ),
              ),
          ],
        ),
        if (isReceipt) ...[
          const SizedBox(height: 10),
          Row(
            children: [
              Expanded(
                flex: 3,
                child: TextField(
                  key: index == 0 ? const Key('stock-lot-input') : Key('stock-lot-input-$index'),
                  controller: line.lotCtrl,
                  decoration: const InputDecoration(
                    labelText: 'Số lô (Lot No) *',
                    isDense: true,
                    border: OutlineInputBorder(),
                  ),
                ),
              ),
              const SizedBox(width: 10),
              Expanded(
                flex: 3,
                child: InkWell(
                  onTap: () async {
                    final picked = await showDatePicker(
                      context: context,
                      initialDate: line.expiryDate,
                      firstDate: DateTime.now().subtract(const Duration(days: 30)),
                      lastDate: DateTime.now().add(const Duration(days: 730)),
                    );
                    if (picked != null) {
                      setState(() => line.expiryDate = picked);
                    }
                  },
                  child: InputDecorator(
                    decoration: const InputDecoration(
                      labelText: 'Hạn sử dụng *',
                      isDense: true,
                      border: OutlineInputBorder(),
                      suffixIcon: Icon(Icons.event, size: 18),
                    ),
                    child: Text(
                      '${line.expiryDate.day.toString().padLeft(2, '0')}/${line.expiryDate.month.toString().padLeft(2, '0')}/${line.expiryDate.year}',
                      style: const TextStyle(fontSize: 13),
                    ),
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 8),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
            decoration: BoxDecoration(
              color: const Color(0xFF2563EB).withValues(alpha: 0.08),
              borderRadius: BorderRadius.circular(6),
            ),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                const Text('Thành tiền dòng:', style: TextStyle(fontSize: 12, fontWeight: FontWeight.w600)),
                Text(
                  AppFormat.money(line.lineTotal.toStringAsFixed(0), currency: 'VND'),
                  style: const TextStyle(
                    fontSize: 13,
                    fontWeight: FontWeight.w800,
                    color: Color(0xFF2563EB),
                  ),
                ),
              ],
            ),
          ),
        ],
      ],
    );
  }

  Widget _buildTableLineLayout(
    int index,
    _FormStockLine line,
    InventoryItem? item,
    String unitLabel,
    ThemeData theme,
  ) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          crossAxisAlignment: CrossAxisAlignment.center,
          children: [
            CircleAvatar(
              radius: 12,
              backgroundColor: theme.colorScheme.primary.withValues(alpha: 0.15),
              child: Text(
                '${index + 1}',
                style: TextStyle(
                    fontSize: 11,
                    fontWeight: FontWeight.bold,
                    color: theme.colorScheme.primary),
              ),
            ),
            const SizedBox(width: 8),
            Expanded(
              flex: 4,
              child: DropdownButtonFormField<String>(
                key: Key('stock-dialog-item-select-$index'),
                isExpanded: true,
                initialValue: line.itemId,
                decoration: const InputDecoration(
                  labelText: 'Nguyên vật liệu *',
                  isDense: true,
                  border: OutlineInputBorder(),
                ),
                items: [
                  for (final itm in widget.items)
                    DropdownMenuItem(
                      value: itm.id,
                      child: Text(
                        '${itm.name} (${itm.sku})',
                        overflow: TextOverflow.ellipsis,
                      ),
                    ),
                ],
                onChanged: (v) {
                  if (v != null) {
                    setState(() {
                      line.itemId = v;
                      final selectedItem = _findItem(v);
                      if (selectedItem != null &&
                          selectedItem.costPrice != null &&
                          selectedItem.costPrice! > 0) {
                        line.priceCtrl.text =
                            selectedItem.costPrice!.toStringAsFixed(0);
                      }
                    });
                  }
                },
              ),
            ),
            const SizedBox(width: 8),
            Expanded(
              flex: 2,
              child: TextField(
                key: index == 0 ? const Key('stock-qty-input') : Key('stock-qty-input-$index'),
                controller: line.qtyCtrl,
                keyboardType: const TextInputType.numberWithOptions(decimal: true),
                decoration: InputDecoration(
                  labelText: 'SL ($unitLabel) *',
                  isDense: true,
                  border: const OutlineInputBorder(),
                  prefixIcon: IconButton(
                    icon: const Icon(Icons.remove, size: 14),
                    padding: EdgeInsets.zero,
                    constraints: const BoxConstraints(minWidth: 24, minHeight: 24),
                    tooltip: 'Giảm 1',
                    onPressed: () {
                      final cur = line.quantity;
                      final next = (cur - 1) < 0 ? 0.0 : (cur - 1);
                      line.qtyCtrl.text = next == next.roundToDouble()
                          ? next.toInt().toString()
                          : next.toStringAsFixed(1);
                      setState(() {});
                    },
                  ),
                  suffixIcon: IconButton(
                    icon: const Icon(Icons.add, size: 14),
                    padding: EdgeInsets.zero,
                    constraints: const BoxConstraints(minWidth: 24, minHeight: 24),
                    tooltip: 'Tăng 1',
                    onPressed: () {
                      final cur = line.quantity;
                      final next = cur + 1;
                      line.qtyCtrl.text = next == next.roundToDouble()
                          ? next.toInt().toString()
                          : next.toStringAsFixed(1);
                      setState(() {});
                    },
                  ),
                ),
                onChanged: (_) => setState(() {}),
              ),
            ),
            const SizedBox(width: 8),
            Expanded(
              flex: 2,
              child: TextField(
                key: index == 0 ? const Key('stock-price-input') : Key('stock-price-input-$index'),
                controller: line.priceCtrl,
                keyboardType: TextInputType.number,
                decoration: const InputDecoration(
                  labelText: 'Đơn giá *',
                  isDense: true,
                  suffixText: 'đ',
                  border: OutlineInputBorder(),
                ),
                onChanged: (_) => setState(() {}),
              ),
            ),
            const SizedBox(width: 8),
            Expanded(
              flex: 2,
              child: TextField(
                key: index == 0 ? const Key('stock-lot-input') : Key('stock-lot-input-$index'),
                controller: line.lotCtrl,
                decoration: const InputDecoration(
                  labelText: 'Số lô *',
                  isDense: true,
                  border: OutlineInputBorder(),
                ),
              ),
            ),
            const SizedBox(width: 8),
            Expanded(
              flex: 2,
              child: InkWell(
                onTap: () async {
                  final picked = await showDatePicker(
                    context: context,
                    initialDate: line.expiryDate,
                    firstDate: DateTime.now().subtract(const Duration(days: 30)),
                    lastDate: DateTime.now().add(const Duration(days: 730)),
                  );
                  if (picked != null) {
                    setState(() => line.expiryDate = picked);
                  }
                },
                child: InputDecorator(
                  decoration: const InputDecoration(
                    labelText: 'HSD *',
                    isDense: true,
                    border: OutlineInputBorder(),
                  ),
                  child: Text(
                    '${line.expiryDate.day.toString().padLeft(2, '0')}/${line.expiryDate.month.toString().padLeft(2, '0')}',
                    style: const TextStyle(fontSize: 12),
                  ),
                ),
              ),
            ),
            const SizedBox(width: 8),
            SizedBox(
              width: 90,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.end,
                children: [
                  const Text('Thành tiền', style: TextStyle(fontSize: 10, color: Colors.grey)),
                  Text(
                    AppFormat.money(line.lineTotal.toStringAsFixed(0)),
                    style: const TextStyle(fontSize: 13, fontWeight: FontWeight.bold, color: Color(0xFF2563EB)),
                    overflow: TextOverflow.ellipsis,
                  ),
                ],
              ),
            ),
            if (_lines.length > 1) ...[
              IconButton(
                key: Key('stock-dialog-delete-line-$index'),
                icon: const Icon(Icons.delete_outline, color: Colors.red, size: 20),
                tooltip: 'Xoá dòng',
                onPressed: () => _removeLine(index),
              ),
            ],
          ],
        ),
        const SizedBox(height: 6),
        Row(
          children: [
            const SizedBox(width: 32),
            Text(
              'Thêm nhanh: ',
              style: TextStyle(
                fontSize: 11,
                color: theme.colorScheme.onSurfaceVariant,
              ),
            ),
            for (final inc in [1, 5, 10])
              Padding(
                padding: const EdgeInsets.only(right: 6),
                child: InkWell(
                  onTap: () {
                    final cur = line.quantity;
                    final next = cur + inc;
                    line.qtyCtrl.text = next == next.roundToDouble()
                        ? next.toInt().toString()
                        : next.toStringAsFixed(1);
                    setState(() {});
                  },
                  borderRadius: BorderRadius.circular(10),
                  child: Container(
                    padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                    decoration: BoxDecoration(
                      color: theme.colorScheme.primary.withValues(alpha: 0.1),
                      borderRadius: BorderRadius.circular(10),
                    ),
                    child: Text(
                      '+$inc',
                      style: TextStyle(
                        fontSize: 11,
                        fontWeight: FontWeight.bold,
                        color: theme.colorScheme.primary,
                      ),
                    ),
                  ),
                ),
              ),
          ],
        ),
      ],
    );
  }

  Widget _buildReasonField(ThemeData theme) {
    final isRequired = _subKind == 'spoilage' || _subKind == 'internal';

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Autocomplete<String>(
          key: const Key('stock-reason-autocomplete'),
          initialValue: TextEditingValue(text: _reasonCtrl.text),
          optionsBuilder: (text) {
            final q = text.text.trim().toLowerCase();
            if (q.isEmpty) return _allReasonSuggestions;
            return _allReasonSuggestions.where((s) => s.toLowerCase().contains(q));
          },
          onSelected: (val) => _reasonCtrl.text = val,
          fieldViewBuilder: (ctx, ctrl, focus, onSubmitted) {
            _autocompleteReasonCtrl = ctrl;
            return TextField(
              key: const Key('stock-reason-input'),
              controller: ctrl,
              focusNode: focus,
              onChanged: (v) {
                _reasonCtrl.text = v;
              },
              decoration: InputDecoration(
                labelText: isRequired
                    ? 'Lý do / Diễn giải cụ thể (BẮT BUỘC) *'
                    : 'Lý do / Diễn giải lập phiếu',
                hintText: 'Gõ hoặc chọn gợi ý...',
                border: const OutlineInputBorder(),
                prefixIcon: const Icon(Icons.comment_outlined, size: 20),
              ),
            );
          },
        ),
        const SizedBox(height: 8),
        Wrap(
          spacing: 6,
          runSpacing: 6,
          children: [
            for (final suggestion in _relevantReasonSuggestions.take(3))
              InkWell(
                onTap: () {
                  _reasonCtrl.text = suggestion;
                  _autocompleteReasonCtrl?.text = suggestion;
                  setState(() {});
                },
                borderRadius: BorderRadius.circular(12),
                child: Container(
                  padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                  decoration: BoxDecoration(
                    color: theme.colorScheme.surfaceContainerHighest.withValues(alpha: 0.6),
                    borderRadius: BorderRadius.circular(12),
                    border: Border.all(
                      color: theme.colorScheme.outlineVariant.withValues(alpha: 0.5),
                    ),
                  ),
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      const Icon(Icons.bolt, size: 13, color: Color(0xFFD97706)),
                      const SizedBox(width: 4),
                      Text(
                        suggestion,
                        style: TextStyle(
                          fontSize: 11,
                          fontWeight: FontWeight.w600,
                          color: theme.colorScheme.onSurface,
                        ),
                      ),
                    ],
                  ),
                ),
              ),
          ],
        ),
      ],
    );
  }

  Widget _buildDialogFooter(ThemeData theme, bool isReceipt) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 14),
      decoration: BoxDecoration(
        color: theme.colorScheme.surfaceContainerHighest.withValues(alpha: 0.3),
        borderRadius: const BorderRadius.vertical(bottom: Radius.circular(20)),
        border: Border(
          top: BorderSide(color: theme.colorScheme.outlineVariant.withValues(alpha: 0.4)),
        ),
      ),
      child: Row(
        children: [
          // Tóm tắt tổng tiền / số lượng
          if (isReceipt) ...[
            Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: [
                Text(
                  'Tổng ${_lines.length} nguyên liệu (${_totalQuantity.toStringAsFixed(1)})',
                  style: const TextStyle(fontSize: 12, color: Colors.grey),
                ),
                Text(
                  AppFormat.money(_totalReceiptAmount.toStringAsFixed(0), currency: 'VND'),
                  key: const Key('stock-dialog-total-amount'),
                  style: const TextStyle(
                    fontSize: 18,
                    fontWeight: FontWeight.w900,
                    color: Color(0xFF2563EB),
                  ),
                ),
              ],
            ),
          ] else ...[
            Text(
              'Tổng ${_lines.length} nguyên liệu xuất (${_totalQuantity.toStringAsFixed(1)})',
              style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w600),
            ),
          ],
          const Spacer(),
          TextButton(
            onPressed: _submitting ? null : () => Navigator.of(context).pop(),
            child: const Text('Huỷ'),
          ),
          const SizedBox(width: 8),
          FilledButton.icon(
            key: const Key('stock-dialog-save-btn'),
            style: FilledButton.styleFrom(
              backgroundColor: isReceipt
                  ? const Color(0xFF2563EB)
                  : (_subKind == 'spoilage'
                      ? const Color(0xFFD97706)
                      : (_subKind == 'internal'
                          ? const Color(0xFF7C3AED)
                          : const Color(0xFF0D9488))),
              padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 12),
            ),
            onPressed: _submitting ? null : _submit,
            icon: _submitting
                ? const SizedBox(
                    width: 18,
                    height: 18,
                    child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
                  )
                : const Icon(Icons.check, size: 18),
            label: Text(_submitting ? 'Đang lưu...' : 'Lưu phiếu nháp'),
          ),
        ],
      ),
    );
  }
}
