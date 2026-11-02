import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:kho_tra_sua/src/app/app_shell.dart';
import 'package:kho_tra_sua/src/data/repositories/fake_repository.dart';
import 'package:kho_tra_sua/src/features/sync/export_dialog.dart';

void main() {
  testWidgets('ExportDialog renders dataset options and handles format switching', (tester) async {
    final fakeRepo = FakeBankOpsRepository(latency: Duration.zero);

    await tester.pumpWidget(
      MaterialApp(
        home: RepositoryScope(
          repository: fakeRepo,
          child: const Scaffold(
            body: ExportDialog(
              initialDataset: 'catalog',
            ),
          ),
        ),
      ),
    );

    await tester.pumpAndSettle();

    // Verify title and labels
    expect(find.text('Đồng bộ & Xuất Dữ Liệu'), findsOneWidget);
    expect(find.text('1. Chọn dữ liệu cần xuất:'), findsOneWidget);
    expect(find.text('2. Chọn đích đến / định dạng:'), findsOneWidget);

    // Default is Excel (.xlsx)
    expect(find.text('Tải file XLSX'), findsOneWidget);

    // Switch to CSV
    await tester.tap(find.text('CSV (BOM)'));
    await tester.pumpAndSettle();
    expect(find.text('Tải file CSV'), findsOneWidget);

    // Switch to Google Sheets
    await tester.tap(find.text('Google Sheets'));
    await tester.pumpAndSettle();
    expect(find.text('Đường dẫn Google Sheet đích:'), findsOneWidget);

    final syncBtn = find.text('Đẩy lên Google Sheet');
    expect(syncBtn, findsOneWidget);
    await tester.ensureVisible(syncBtn);
    await tester.tap(syncBtn);
    await tester.pumpAndSettle();

    // Should display success banner
    expect(find.text('Đồng bộ hoàn tất! Nhấp để mở:'), findsOneWidget);
    expect(find.text('Mở Sheet'), findsOneWidget);
  });
}
