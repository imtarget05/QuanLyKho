import 'package:flutter/material.dart' show DateTimeRange;
import 'package:flutter/services.dart';
import 'package:pdf/pdf.dart';
import 'package:pdf/widgets.dart' as pw;

import '../../../core/util/formatting.dart';
import '../../../data/models/dtos.dart';
import '../reports_filter.dart';

/// Tạo tài liệu PDF A4 báo cáo điều hành & xuất nhập tồn chuẩn văn bản nhà nước (Nghị định 30/2020/NĐ-CP).
/// Thiết kế 100% Trắng Đen (Monochrome), trang trọng, rõ ràng phục vụ in ấn trình ký và lưu trữ.
class MeetingReportPdf {
  const MeetingReportPdf._();

  static Future<List<int>> encode({
    required List<InventoryBucket> inventoryBuckets,
    required List<CashflowBucket> cashflowBuckets,
    required List<StagnationItem> stagnationItems,
    required List<ReconciliationRun> reconciliations,
    required ReportGranularity granularity,
    DateTimeRange? dateRange,
    String? staffAssessment,
    String? staffNotes,
  }) async {
    final doc = pw.Document();
    final font =
        pw.Font.ttf(await rootBundle.load('assets/fonts/Roboto-Regular.ttf'));

    // Tính tổng dòng tiền
    double totalIn = 0;
    double totalOut = 0;
    int totalJournals = 0;
    for (final b in cashflowBuckets) {
      totalIn += b.inValue;
      totalOut += b.outValue;
      totalJournals += b.journalCount;
    }
    final netCash = totalIn - totalOut;

    // Tính tổng kho
    double totalInbound = 0;
    double totalOutbound = 0;
    int totalReceipts = 0;
    int totalIssues = 0;
    for (final b in inventoryBuckets) {
      totalInbound += b.inboundValue;
      totalOutbound += b.outboundValue;
      totalReceipts += b.receiptCount;
      totalIssues += b.issueCount;
    }
    final netInventory = totalInbound - totalOutbound;

    // Phân tầng tồn đọng
    final critical =
        stagnationItems.where((i) => i.severity == 'critical').toList();

    // Đối soát
    final totalRuns = reconciliations.length;
    final cleanRuns = reconciliations.where((r) => r.exceptions.isEmpty).length;
    final matchRate = totalRuns > 0
        ? (cleanRuns / totalRuns * 100).toStringAsFixed(1)
        : '100.0';

    final periodStr = dateRange != null
        ? '${AppFormat.date(dateRange.start)} - ${AppFormat.date(dateRange.end)}'
        : (granularity == ReportGranularity.daily
            ? 'Tổng hợp ngày gần nhất'
            : 'Tổng hợp tháng hiện tại');

    final assessmentStr = staffAssessment ??
        (critical.isNotEmpty
            ? 'Cần rà soát mặt hàng chậm luân chuyển'
            : 'Vận hành đạt chuẩn - Số liệu cân đối');

    final now = DateTime.now();

    doc.addPage(
      pw.Page(
        pageFormat: PdfPageFormat.a4,
        margin: const pw.EdgeInsets.symmetric(horizontal: 36, vertical: 28),
        theme: pw.ThemeData.withFont(base: font, bold: font, italic: font),
        build: (context) => pw.Column(
          crossAxisAlignment: pw.CrossAxisAlignment.start,
          children: [
            // 1. Thể thức văn bản hành chính theo Nghị định 30/2020/NĐ-CP
            pw.Row(
              mainAxisAlignment: pw.MainAxisAlignment.spaceBetween,
              crossAxisAlignment: pw.CrossAxisAlignment.start,
              children: [
                pw.Column(
                  crossAxisAlignment: pw.CrossAxisAlignment.center,
                  children: [
                    pw.Text(
                      'CỬA HÀNG KHO TRÀ SỮA',
                      style: pw.TextStyle(
                        fontSize: 9.5,
                        fontWeight: pw.FontWeight.bold,
                        color: PdfColors.black,
                      ),
                    ),
                    pw.SizedBox(height: 2),
                    pw.Text(
                      'BỘ PHẬN KHO VẬN & SỔ QUỸ',
                      style: const pw.TextStyle(
                        fontSize: 8.5,
                        color: PdfColors.black,
                      ),
                    ),
                    pw.SizedBox(height: 2),
                    pw.Text(
                      'Số: ...... / BC-XNT-QUY',
                      style: const pw.TextStyle(
                        fontSize: 8,
                        color: PdfColors.black,
                      ),
                    ),
                    pw.Container(
                      width: 60,
                      height: 0.5,
                      color: PdfColors.black,
                      margin: const pw.EdgeInsets.only(top: 2),
                    ),
                  ],
                ),
                pw.Column(
                  crossAxisAlignment: pw.CrossAxisAlignment.center,
                  children: [
                    pw.Text(
                      'CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM',
                      style: pw.TextStyle(
                        fontSize: 9.5,
                        fontWeight: pw.FontWeight.bold,
                        color: PdfColors.black,
                      ),
                    ),
                    pw.SizedBox(height: 2),
                    pw.Text(
                      'Độc lập - Tự do - Hạnh phúc',
                      style: pw.TextStyle(
                        fontSize: 9,
                        fontWeight: pw.FontWeight.bold,
                        color: PdfColors.black,
                      ),
                    ),
                    pw.Container(
                      width: 90,
                      height: 0.8,
                      color: PdfColors.black,
                      margin: const pw.EdgeInsets.only(top: 2, bottom: 4),
                    ),
                    pw.Text(
                      '..., ngày ${now.day.toString().padLeft(2, '0')} tháng ${now.month.toString().padLeft(2, '0')} năm ${now.year}',
                      style: pw.TextStyle(
                        fontSize: 8,
                        fontStyle: pw.FontStyle.italic,
                        color: PdfColors.black,
                      ),
                    ),
                  ],
                ),
              ],
            ),
            pw.SizedBox(height: 14),

            // 2. Tiêu đề báo cáo trang trọng ở giữa trang
            pw.Center(
              child: pw.Column(
                children: [
                  pw.Text(
                    'BÁO CÁO TỔNG HỢP XUẤT NHẬP TỒN & SỔ QUỸ TIỀN MẶT',
                    style: pw.TextStyle(
                      fontSize: 12.5,
                      fontWeight: pw.FontWeight.bold,
                      color: PdfColors.black,
                    ),
                  ),
                  pw.SizedBox(height: 3),
                  pw.Text(
                    'Kỳ báo cáo: $periodStr',
                    style: pw.TextStyle(
                      fontSize: 8.5,
                      fontStyle: pw.FontStyle.italic,
                      color: PdfColors.black,
                    ),
                  ),
                  pw.SizedBox(height: 2),
                  pw.Text(
                    'Tình trạng vận hành: $assessmentStr',
                    style: pw.TextStyle(
                      fontSize: 8.5,
                      fontWeight: pw.FontWeight.bold,
                      color: PdfColors.black,
                    ),
                  ),
                ],
              ),
            ),
            pw.SizedBox(height: 12),

            // 3. Phần I: Bảng tổng hợp luân chuyển kho nguyên vật liệu
            pw.Text(
              'I. BẢNG TỔNG HỢP LUÂN CHUYỂN KHO NGUYÊN VẬT LIỆU',
              style: pw.TextStyle(
                fontSize: 9.5,
                fontWeight: pw.FontWeight.bold,
                color: PdfColors.black,
              ),
            ),
            pw.SizedBox(height: 4),
            pw.Table(
              border: pw.TableBorder.all(color: PdfColors.black, width: 0.5),
              children: [
                pw.TableRow(
                  decoration: const pw.BoxDecoration(color: PdfColors.grey200),
                  children: [
                    _cellHeader('STT', width: 24, align: pw.TextAlign.center),
                    _cellHeader('Chỉ tiêu luân chuyển kho'),
                    _cellHeader('Khối lượng / Số lượng', align: pw.TextAlign.right),
                    _cellHeader('Diễn giải chi tiết'),
                  ],
                ),
                pw.TableRow(
                  children: [
                    _cellText('1', align: pw.TextAlign.center),
                    _cellText('Tổng số phiếu nhập kho thực hiện'),
                    _cellText('$totalReceipts phiếu', align: pw.TextAlign.right, bold: true),
                    _cellText('Phiếu nhập kho đã hoàn tất đối soát'),
                  ],
                ),
                pw.TableRow(
                  children: [
                    _cellText('2', align: pw.TextAlign.center),
                    _cellText('Tổng số lượng nguyên vật liệu nhập'),
                    _cellText(
                      '${AppFormat.quantity(totalInbound.toStringAsFixed(0))} đơn vị',
                      align: pw.TextAlign.right,
                      bold: true,
                    ),
                    _cellText('Nhập kho từ nhà cung cấp / luân chuyển'),
                  ],
                ),
                pw.TableRow(
                  children: [
                    _cellText('3', align: pw.TextAlign.center),
                    _cellText('Tổng số phiếu xuất kho thực hiện'),
                    _cellText('$totalIssues phiếu', align: pw.TextAlign.right, bold: true),
                    _cellText('Phiếu xuất pha chế / tiêu hao ca trực'),
                  ],
                ),
                pw.TableRow(
                  children: [
                    _cellText('4', align: pw.TextAlign.center),
                    _cellText('Tổng số lượng nguyên vật liệu xuất'),
                    _cellText(
                      '${AppFormat.quantity(totalOutbound.toStringAsFixed(0))} đơn vị',
                      align: pw.TextAlign.right,
                      bold: true,
                    ),
                    _cellText('Đã trừ tồn kho theo định mức ca'),
                  ],
                ),
                pw.TableRow(
                  children: [
                    _cellText('5', align: pw.TextAlign.center),
                    _cellText('Biến động tồn kho ròng trong kỳ', bold: true),
                    _cellText(
                      '${AppFormat.quantity(netInventory.toStringAsFixed(0))} đơn vị',
                      align: pw.TextAlign.right,
                      bold: true,
                    ),
                    _cellText('Chênh lệch thuần nhập trừ xuất'),
                  ],
                ),
              ],
            ),
            pw.SizedBox(height: 10),

            // 4. Phần II: Bảng tổng hợp sổ quỹ tiền mặt
            pw.Text(
              'II. BẢNG TỔNG HỢP SỔ QUỸ & DÒNG TIỀN MẶT',
              style: pw.TextStyle(
                fontSize: 9.5,
                fontWeight: pw.FontWeight.bold,
                color: PdfColors.black,
              ),
            ),
            pw.SizedBox(height: 4),
            pw.Table(
              border: pw.TableBorder.all(color: PdfColors.black, width: 0.5),
              children: [
                pw.TableRow(
                  decoration: const pw.BoxDecoration(color: PdfColors.grey200),
                  children: [
                    _cellHeader('STT', width: 24, align: pw.TextAlign.center),
                    _cellHeader('Chỉ tiêu quỹ tiền mặt'),
                    _cellHeader('Số tiền (VND)', align: pw.TextAlign.right),
                    _cellHeader('Ghi chú / Trạng thái đối chiếu'),
                  ],
                ),
                pw.TableRow(
                  children: [
                    _cellText('1', align: pw.TextAlign.center),
                    _cellText('Tổng thu tiền mặt (Thu quỹ)'),
                    _cellText(AppFormat.money(totalIn.toStringAsFixed(0)),
                        align: pw.TextAlign.right, bold: true),
                    _cellText('Doanh thu bán hàng & nộp quỹ đầu ca'),
                  ],
                ),
                pw.TableRow(
                  children: [
                    _cellText('2', align: pw.TextAlign.center),
                    _cellText('Tổng chi tiền mặt (Chi quỹ)'),
                    _cellText(AppFormat.money(totalOut.toStringAsFixed(0)),
                        align: pw.TextAlign.right, bold: true),
                    _cellText('Chi mua gấp nguyên liệu & chi phí vận hành'),
                  ],
                ),
                pw.TableRow(
                  children: [
                    _cellText('3', align: pw.TextAlign.center),
                    _cellText('Dòng tiền thuần ròng (Net Cashflow)', bold: true),
                    _cellText(
                      AppFormat.money(netCash.toStringAsFixed(0)),
                      align: pw.TextAlign.right,
                      bold: true,
                    ),
                    _cellText(netCash >= 0 ? 'Thặng dư ngân quỹ' : 'Thâm hụt dòng tiền'),
                  ],
                ),
                pw.TableRow(
                  children: [
                    _cellText('4', align: pw.TextAlign.center),
                    _cellText('Tổng số lượng bút toán phát sinh'),
                    _cellText('$totalJournals bút toán',
                        align: pw.TextAlign.right, bold: true),
                    _cellText('Đã đối chiếu sổ cái két quầy'),
                  ],
                ),
              ],
            ),
            pw.SizedBox(height: 10),

            // 5. Phần III: Kết quả đối soát kiểm kê ca & Đề xuất
            pw.Text(
              'III. KẾT QUẢ ĐỐI SOÁT KIỂM KÊ CA & ĐỀ XUẤT ĐIỀU HÀNH',
              style: pw.TextStyle(
                fontSize: 9.5,
                fontWeight: pw.FontWeight.bold,
                color: PdfColors.black,
              ),
            ),
            pw.SizedBox(height: 4),
            pw.Table(
              border: pw.TableBorder.all(color: PdfColors.black, width: 0.5),
              children: [
                pw.TableRow(
                  children: [
                    pw.Padding(
                      padding: const pw.EdgeInsets.all(6),
                      child: pw.Column(
                        crossAxisAlignment: pw.CrossAxisAlignment.start,
                        children: [
                          pw.Text(
                            '1. Tỷ lệ đối soát chốt ca đạt chuẩn: $matchRate% ($cleanRuns/$totalRuns phiên kiểm đếm khớp 100% số lượng).',
                            style: const pw.TextStyle(fontSize: 8),
                          ),
                          pw.SizedBox(height: 2),
                          pw.Text(
                            critical.isNotEmpty
                                ? '2. Cảnh báo: Có ${critical.length} mặt hàng nguyên vật liệu tồn đọng lâu chưa xuất dùng. Đề nghị ưu tiên xuất dùng theo nguyên tắc FEFO.'
                                : '2. Quản lý kho: Tất cả nguyên vật liệu đều lưu chuyển đúng quy chuẩn hạn dùng.',
                            style: const pw.TextStyle(fontSize: 8),
                          ),
                          if (staffNotes != null && staffNotes.trim().isNotEmpty) ...[
                            pw.SizedBox(height: 2),
                            pw.Text(
                              '3. Ý kiến chỉ đạo từ quản lý: ${staffNotes.trim()}',
                              style: pw.TextStyle(fontSize: 8, fontStyle: pw.FontStyle.italic),
                            ),
                          ],
                        ],
                      ),
                    ),
                  ],
                ),
              ],
            ),

            pw.Spacer(),

            // 6. Phần Chữ ký 3 bên chuẩn hành chính doanh nghiệp
            pw.Row(
              mainAxisAlignment: pw.MainAxisAlignment.spaceBetween,
              crossAxisAlignment: pw.CrossAxisAlignment.start,
              children: [
                _signatureBlock('NGƯỜI LẬP BIỂU', '(Ký và ghi rõ họ tên)'),
                _signatureBlock('THỦ KHO / THỦ QUỸ', '(Ký và ghi rõ họ tên)'),
                _signatureBlock('CỬA HÀNG TRƯỞNG / CHỦ HỘ', '(Ký, đóng dấu và ghi rõ họ tên)'),
              ],
            ),
            pw.SizedBox(height: 6),
            pw.Center(
              child: pw.Text(
                'Biểu mẫu Báo cáo Xuất Nhập Tồn & Quỹ Tiền Mặt · Trích xuất từ hệ thống QuanLyKho',
                style: const pw.TextStyle(fontSize: 7, color: PdfColors.black),
              ),
            ),
          ],
        ),
      ),
    );

    return doc.save();
  }

  static pw.Widget _cellHeader(
    String text, {
    double? width,
    pw.TextAlign align = pw.TextAlign.left,
  }) {
    final widget = pw.Padding(
      padding: const pw.EdgeInsets.symmetric(horizontal: 5, vertical: 3.5),
      child: pw.Text(
        text,
        textAlign: align,
        style: pw.TextStyle(
          fontSize: 8,
          fontWeight: pw.FontWeight.bold,
          color: PdfColors.black,
        ),
      ),
    );
    if (width != null) {
      return pw.SizedBox(width: width, child: widget);
    }
    return widget;
  }

  static pw.Widget _cellText(
    String text, {
    bool bold = false,
    pw.TextAlign align = pw.TextAlign.left,
  }) {
    return pw.Padding(
      padding: const pw.EdgeInsets.symmetric(horizontal: 5, vertical: 3),
      child: pw.Text(
        text,
        textAlign: align,
        style: pw.TextStyle(
          fontSize: 7.5,
          fontWeight: bold ? pw.FontWeight.bold : pw.FontWeight.normal,
          color: PdfColors.black,
        ),
      ),
    );
  }

  static pw.Widget _signatureBlock(String title, String hint) {
    return pw.Container(
      width: 140,
      child: pw.Column(
        crossAxisAlignment: pw.CrossAxisAlignment.center,
        children: [
          pw.Text(
            title,
            textAlign: pw.TextAlign.center,
            style: pw.TextStyle(
              fontSize: 8.5,
              fontWeight: pw.FontWeight.bold,
              color: PdfColors.black,
            ),
          ),
          pw.SizedBox(height: 2),
          pw.Text(
            hint,
            style: pw.TextStyle(
              fontSize: 7,
              fontStyle: pw.FontStyle.italic,
              color: PdfColors.black,
            ),
          ),
          pw.SizedBox(height: 42),
        ],
      ),
    );
  }
}
