// ignore_for_file: lines_longer_than_80_chars
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:kho_tra_sua/src/app/app_shell.dart';
import 'package:kho_tra_sua/src/core/theme/app_theme.dart';
import 'package:kho_tra_sua/src/data/repositories/fake_repository.dart';
import 'package:kho_tra_sua/src/features/requests/requests_screen.dart';

/// Helper: pump the RequestsScreen with StockRequestDialog pre-opened.
Future<void> pumpStockDialog(
  WidgetTester tester, {
  Duration latency = Duration.zero,
}) async {
  tester.view
    ..physicalSize = const Size(1100, 720)
    ..devicePixelRatio = 1.0;
  addTearDown(tester.view.resetPhysicalSize);

  final repo = FakeBankOpsRepository(latency: latency);
  await tester.pumpWidget(
    RepositoryScope(
      repository: repo,
      child: MaterialApp(
        theme: AppTheme.light(),
        home: const Scaffold(
          body: RequestsScreen(initialOpenCreateStock: true),
        ),
      ),
    ),
  );
  await tester.pumpAndSettle();
}

void main() {
  // ---------------------------------------------------------------------------
  // Test 1 – Phiếu nhập đa dòng: thêm dòng và tính tổng tiền
  // ---------------------------------------------------------------------------
  testWidgets(
    'multiline_receipt_adds_lines_and_calculates_total',
    (WidgetTester tester) async {
      await pumpStockDialog(tester);

      // Dialog phải hiện tiêu đề đúng
      expect(find.text('Tạo Phiếu Kho Mới'), findsOneWidget);

      // Dòng đầu tiên đã có sẵn – qty input với key legacy
      expect(find.byKey(const Key('stock-qty-input')), findsOneWidget);

      // Nhập số lượng = 2 cho dòng 0
      await tester.enterText(find.byKey(const Key('stock-qty-input')), '2');
      await tester.pump();

      // Nhập đơn giá = 50000 cho dòng 0
      await tester.enterText(
          find.byKey(const Key('stock-price-input')), '50000');
      await tester.pump();

      // Tổng tiền phải là 100,000 (hiện trong widget key 'stock-dialog-total-amount')
      final totalWidget = find.byKey(const Key('stock-dialog-total-amount'));
      expect(totalWidget, findsOneWidget);
      final totalText = (tester.widget(totalWidget) as Text).data ?? '';
      // AppFormat.money chèn dấu chấm phân cách: "100.000" hoặc "100,000"
      expect(
        totalText.contains('100'),
        isTrue,
        reason: 'Tổng tiền phải chứa "100" (= 2 × 50000), thực tế: $totalText',
      );

      // Bấm thêm dòng nguyên liệu
      await tester.tap(find.byKey(const Key('stock-dialog-add-line-btn')));
      await tester.pumpAndSettle();

      // Dòng thứ hai phải xuất hiện (key stock-qty-input-1)
      expect(find.byKey(const Key('stock-qty-input-1')), findsOneWidget);
    },
  );

  // ---------------------------------------------------------------------------
  // Test 2 – Xuất hủy (spoilage) bắt buộc phải có lý do
  // ---------------------------------------------------------------------------
  testWidgets(
    'spoilage_outbound_requires_reason',
    (WidgetTester tester) async {
      await pumpStockDialog(tester);

      // Chuyển sang tab Xuất kho bằng SegmentedButton
      final kindToggle = find.byKey(const Key('stock-dialog-kind-toggle'));
      expect(kindToggle, findsOneWidget);

      // Tap vào segment "Xuất Kho" – segment thứ 2 trong SegmentedButton
      await tester.tap(find.text('Xuất Kho (Issue)'));
      await tester.pumpAndSettle();

      // Chọn loại Hủy / Hao hụt (spoilage chip)
      await tester.tap(find.byKey(const Key('outbound-subkind-spoilage')));
      await tester.pumpAndSettle();

      // Xóa trắng trường lý do để test validation
      await tester.enterText(find.byKey(const Key('stock-reason-input')), '');
      await tester.pump();

      // Bấm Lưu phiếu → phải báo lỗi "bắt buộc"
      await tester.tap(find.byKey(const Key('stock-dialog-save-btn')));
      await tester.pumpAndSettle();

      expect(
        find.textContaining('bắt buộc'),
        findsOneWidget,
        reason:
            'Phải có thông báo lỗi chứa "bắt buộc" khi spoilage thiếu lý do',
      );
    },
  );

  // ---------------------------------------------------------------------------
  // Test 3 – Xuất chuyển kho (transfer) hiện dropdown kho đích
  // ---------------------------------------------------------------------------
  testWidgets(
    'transfer_outbound_shows_destination_dropdown',
    (WidgetTester tester) async {
      await pumpStockDialog(tester);

      // Chuyển sang Xuất kho
      await tester.tap(find.text('Xuất Kho (Issue)'));
      await tester.pumpAndSettle();

      // Chọn loại Chuyển kho (transfer chip)
      await tester.tap(find.byKey(const Key('outbound-subkind-transfer')));
      await tester.pumpAndSettle();

      // Dropdown kho đích phải hiện ra (key 'stock-location-dropdown')
      expect(
        find.byKey(const Key('stock-location-dropdown')),
        findsOneWidget,
        reason:
            'Phải hiện dropdown kho đích khi chọn loại xuất chuyển kho (transfer)',
      );
    },
  );

  // ---------------------------------------------------------------------------
  // Test 4 – Submit phiếu nhập thành công, không hiện lỗi
  // ---------------------------------------------------------------------------
  testWidgets(
    'submit_receipt_creates_request_shows_no_error',
    (WidgetTester tester) async {
      await pumpStockDialog(tester);

      // Đảm bảo đang ở tab Nhập hàng (mặc định)
      expect(find.text('Tạo Phiếu Kho Mới'), findsOneWidget);

      // Điền lý do tùy ý (field đã có text mặc định; ghi đè để chắc)
      await tester.enterText(
        find.byKey(const Key('stock-reason-input')),
        'Nhập hàng từ nhà cung cấp',
      );
      await tester.pump();

      // Bấm Lưu
      await tester.tap(find.byKey(const Key('stock-dialog-save-btn')));
      await tester.pumpAndSettle();

      // Dialog đã đóng, không có text "Lỗi" trên màn hình
      expect(
        find.textContaining('Lỗi'),
        findsNothing,
        reason: 'Không được hiện lỗi khi phiếu nhập hợp lệ đã được tạo',
      );
    },
  );

  // ---------------------------------------------------------------------------
  // Test 5 – Quick increment stepper buttons and quick reason chips
  // ---------------------------------------------------------------------------
  testWidgets(
    'quick_stepper_and_reason_chips_update_inputs',
    (WidgetTester tester) async {
      await pumpStockDialog(tester);

      // Verify quick presets +1, +5, +10 are visible
      expect(find.text('+5'), findsOneWidget);
      expect(find.text('+10'), findsOneWidget);

      // Tap +5 to increase quantity
      await tester.tap(find.text('+5'));
      await tester.pump();

      // Quantity input now should reflect 5 (0 default + 5)
      final qtyFinder = find.byKey(const Key('stock-qty-input'));
      final textField = tester.widget<TextField>(qtyFinder);
      expect(textField.controller?.text, '5');

      // Verify quick reason chips
      final reasonChip = find.text('Nhập nguyên liệu định kỳ từ nhà cung cấp');
      expect(reasonChip, findsOneWidget);
      await tester.tap(reasonChip);
      await tester.pump();

      final reasonFinder = find.byKey(const Key('stock-reason-input'));
      final reasonField = tester.widget<TextField>(reasonFinder);
      expect(reasonField.controller?.text, 'Nhập nguyên liệu định kỳ từ nhà cung cấp');
    },
  );
}
