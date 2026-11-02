import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:kho_tra_sua/src/features/commerce/commerce_memory_store.dart';
import 'package:kho_tra_sua/src/features/commerce/commerce_reports_page.dart';
import 'package:kho_tra_sua/src/features/commerce/commerce_workspace.dart';

void main() {
  testWidgets('CommerceReportsPage renders LenaKolia KPI deck, charts and ledger table', (tester) async {
    final store = CommerceMemoryStore.demo();
    await tester.binding.setSurfaceSize(const Size(1280, 900));

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: CommerceReportsPage(store: store),
        ),
      ),
    );
    await tester.pumpAndSettle();

    // Verify Title & Subtitle
    expect(find.text('Báo cáo Xuất Nhập Tồn NVL & TP'), findsOneWidget);
    expect(find.textContaining('Tổng hợp doanh thu, giá vốn, lợi nhuận gộp'), findsOneWidget);

    // Verify 6 Top KPIs
    expect(find.text('Doanh thu'), findsWidgets);
    expect(find.text('Tổng giá vốn (COGS)'), findsOneWidget);
    expect(find.text('Lợi nhuận gộp'), findsOneWidget);
    expect(find.text('Tỷ suất lợi nhuận'), findsOneWidget);
    expect(find.text('Số đơn phát sinh'), findsOneWidget);
    expect(find.text('Công nợ tồn đọng'), findsOneWidget);

    // Verify Chart Cards & P&L Statement Card
    expect(find.text('Doanh thu, COGS & Lợi nhuận'), findsOneWidget);
    expect(find.text('Cơ cấu Doanh thu'), findsOneWidget);
    expect(find.text('Xu hướng Lợi nhuận'), findsOneWidget);
    expect(find.text('Báo cáo Kết quả Kinh doanh Tổng hợp (P&L)'), findsOneWidget);

    // Scroll down to find the Inventory Ledger Table
    await tester.drag(find.byType(CommerceReportsPage), const Offset(0, -1200));
    await tester.pumpAndSettle();

    // Verify Inventory Ledger Table
    expect(find.text('Tồn kho hiện tại NVL & TP'), findsOneWidget);
    expect(find.text('Mã SKU'), findsOneWidget);
    expect(find.text('Tên sản phẩm / NVL'), findsOneWidget);
    expect(find.text('Xuất Excel (XLSX)'), findsOneWidget);
  });

  testWidgets('CommerceWorkspace renders Settings tab and allows navigating to it', (tester) async {
    final store = CommerceMemoryStore.demo();
    await tester.binding.setSurfaceSize(const Size(1280, 900));

    await tester.pumpWidget(
      MaterialApp(
        home: CommerceWorkspace(store: store),
      ),
    );
    await tester.pumpAndSettle();

    // Look for Cài đặt in sidebar
    expect(find.text('Cài đặt'), findsOneWidget);

    // Tap Cài đặt
    await tester.tap(find.text('Cài đặt'));
    await tester.pumpAndSettle();

    // Verify Settings Screen is loaded
    expect(find.text('Cài đặt hệ thống'), findsOneWidget);
    expect(find.text('Tài khoản & Bảo mật'), findsOneWidget);
    expect(find.text('Giao diện & Ngôn ngữ'), findsOneWidget);
    expect(find.text('Nhân sự & Phân quyền'), findsOneWidget);
    expect(find.text('Máy in & Hóa đơn'), findsOneWidget);
    expect(find.text('Quản trị hệ thống & Dữ liệu'), findsOneWidget);
  });
}
