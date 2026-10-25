import 'package:flutter/services.dart';
import 'package:pdf/pdf.dart';
import 'package:pdf/widgets.dart' as pw;

import '../../data/models/dtos.dart';
import 'formatting.dart';

/// In chứng từ kho & quỹ thành PDF chuẩn nghiệp vụ kinh doanh Việt Nam (A4).
///
/// Hỗ trợ in:
/// - Mẫu 01-VT: Phiếu Nhập Kho (TT 200/2014/TT-BTC)
/// - Mẫu 02-VT: Phiếu Xuất Kho (TT 200/2014/TT-BTC)
/// - Mẫu 03-VT: Phiếu Điều Chuyển Kho Nội Bộ
/// - Mẫu 01-TT: Phiếu Thu Tiền Mặt
/// - Mẫu 02-TT: Phiếu Chi Tiền Mặt
/// - Mẫu 05-VT: Biên Bản Kiểm Kê Vật Tư & Bàn Giao Ca
class ApprovalPdf {
  const ApprovalPdf._();

  static Future<List<int>> encode(
    ApprovalItem item, {
    AiRiskAssessment? assessment,
    List<String>? auditWarnings,
  }) async {
    final doc = pw.Document();
    final font =
        pw.Font.ttf(await rootBundle.load('assets/fonts/Roboto-Regular.ttf'));

    final kindLower = item.kind.toLowerCase();
    final isCash = kindLower.contains('cash') ||
        kindLower == 'deposit' ||
        kindLower == 'withdraw' ||
        kindLower == 'quy';
    final isCashIn = isCash &&
        (kindLower.contains('deposit') ||
            kindLower.contains('in') ||
            kindLower.contains('thu'));
    final isStocktake = kindLower.contains('stocktake') ||
        kindLower.contains('kiem') ||
        kindLower.contains('adjustment');
    final isInbound = kindLower.contains('inbound') ||
        kindLower.contains('nhap') ||
        kindLower.contains('receipt');
    final isTransfer = kindLower.contains('transfer') ||
        kindLower.contains('chuyen');

    // Mẫu số và tiêu đề chứng từ chuẩn BTC
    String formCode;
    String voucherTitle;
    if (isCash) {
      if (isCashIn) {
        formCode = 'Mẫu số: 01 - TT\n(Ban hành theo TT số 200/2014/TT-BTC)';
        voucherTitle = 'PHIẾU THU TIỀN MẶT';
      } else {
        formCode = 'Mẫu số: 02 - TT\n(Ban hành theo TT số 200/2014/TT-BTC)';
        voucherTitle = 'PHIẾU CHI TIỀN MẶT';
      }
    } else if (isStocktake) {
      formCode = 'Mẫu số: 05 - VT\n(Ban hành theo TT số 200/2014/TT-BTC)';
      voucherTitle = 'BIÊN BẢN KIỂM KÊ KHO & BÀN GIAO CA';
    } else if (isInbound) {
      formCode = 'Mẫu số: 01 - VT\n(Ban hành theo TT số 200/2014/TT-BTC)';
      voucherTitle = 'PHIẾU NHẬP KHO';
    } else if (isTransfer) {
      formCode = 'Mẫu số: 03 - VT\n(Ban hành theo TT số 200/2014/TT-BTC)';
      voucherTitle = 'PHIẾU ĐIỀU CHUYỂN KHO NỘI BỘ';
    } else {
      formCode = 'Mẫu số: 02 - VT\n(Ban hành theo TT số 200/2014/TT-BTC)';
      voucherTitle = 'PHIẾU XUẤT KHO';
    }

    final now = DateTime.now();
    final dateFormatted =
        'Ngày ${now.day.toString().padLeft(2, '0')} tháng ${now.month.toString().padLeft(2, '0')} năm ${now.year}';

    final lines = _parseLines(item, isCash);

    doc.addPage(
      pw.Page(
        pageFormat: PdfPageFormat.a4,
        margin: const pw.EdgeInsets.all(32),
        theme: pw.ThemeData.withFont(base: font, bold: font, italic: font),
        build: (context) => pw.Column(
          crossAxisAlignment: pw.CrossAxisAlignment.start,
          children: [
            // Header doanh nghiệp & Mẫu số BTC
            pw.Row(
              mainAxisAlignment: pw.MainAxisAlignment.spaceBetween,
              crossAxisAlignment: pw.CrossAxisAlignment.start,
              children: [
                pw.Column(
                  crossAxisAlignment: pw.CrossAxisAlignment.start,
                  children: [
                    pw.Text(
                      'HỆ THỐNG CỬA HÀNG TRÀ SỮA & F&B QUẢN LÝ KHO',
                      style: pw.TextStyle(
                        fontSize: 10,
                        fontWeight: pw.FontWeight.bold,
                        color: PdfColors.blue900,
                      ),
                    ),
                    pw.SizedBox(height: 2),
                    pw.Text(
                      'Bộ phận: Kho Vận & Quầy Pha Chế Chi Nhánh',
                      style: const pw.TextStyle(
                          fontSize: 8.5, color: PdfColors.grey800),
                    ),
                    pw.Text(
                      'Địa chỉ: Vận hành Chi nhánh Trung tâm',
                      style: const pw.TextStyle(
                          fontSize: 8, color: PdfColors.grey600),
                    ),
                  ],
                ),
                pw.Column(
                  crossAxisAlignment: pw.CrossAxisAlignment.end,
                  children: [
                    pw.Text(
                      formCode,
                      textAlign: pw.TextAlign.right,
                      style: pw.TextStyle(
                        fontSize: 8,
                        fontWeight: pw.FontWeight.bold,
                        color: PdfColors.grey800,
                      ),
                    ),
                    pw.SizedBox(height: 2),
                    pw.Text(
                      'Số chứng từ: ${item.id}',
                      style: pw.TextStyle(
                        fontSize: 8.5,
                        fontWeight: pw.FontWeight.bold,
                        color: PdfColors.blue900,
                      ),
                    ),
                  ],
                ),
              ],
            ),
            pw.SizedBox(height: 12),
            pw.Divider(thickness: 1, color: PdfColors.blue900),
            pw.SizedBox(height: 8),

            // Tiêu đề chứng từ
            pw.Center(
              child: pw.Column(
                children: [
                  pw.Text(
                    voucherTitle,
                    style: pw.TextStyle(
                      fontSize: 16,
                      fontWeight: pw.FontWeight.bold,
                      color: PdfColors.black,
                    ),
                  ),
                  pw.SizedBox(height: 3),
                  pw.Text(
                    dateFormatted,
                    style: pw.TextStyle(
                      fontSize: 9,
                      fontStyle: pw.FontStyle.italic,
                      color: PdfColors.grey700,
                    ),
                  ),
                ],
              ),
            ),
            pw.SizedBox(height: 12),

            // Thông tin chi tiết chứng từ
            _infoRow('Họ và tên người lập phiếu:', item.maker),
            _infoRow(
              isCash
                  ? (isCashIn ? 'Người nộp tiền:' : 'Người nhận tiền:')
                  : (isInbound
                      ? 'Người giao hàng / Nhà cung cấp:'
                      : 'Người nhận hàng / Bộ phận:'),
              item.maker,
            ),
            _infoRow(
              'Lý do / Nội dung chứng từ:',
              item.detail.isEmpty
                  ? 'Phục vụ hoạt động kinh doanh nguyên vật liệu chi nhánh'
                  : item.detail,
            ),
            _infoRow(
              isCash ? 'Két quỹ thực hiện:' : 'Địa điểm kho hàng:',
              isCash
                  ? 'Két Quỹ Tiền Mặt Hoạt Động Cửa Hàng'
                  : 'Kho Tổng Nguyên Vật Liệu Pha Chế Trung Tâm',
            ),
            _infoRow(
              'Trạng thái phê duyệt:',
              item.status == 'approved' ? 'ĐÃ PHÊ DUYỆT' : 'CHỜ PHÊ DUYỆT',
            ),
            pw.SizedBox(height: 10),

            // Bảng kê chi tiết hàng hóa
            pw.Text(
              'CHI TIẾT MẶT HÀNG / KHOẢN MỤC CHỨNG TỪ:',
              style: pw.TextStyle(
                fontSize: 9,
                fontWeight: pw.FontWeight.bold,
                color: PdfColors.blue900,
              ),
            ),
            pw.SizedBox(height: 4),
            pw.Table(
              border:
                  pw.TableBorder.all(color: PdfColors.grey400, width: 0.5),
              columnWidths: {
                0: const pw.FixedColumnWidth(28),
                1: const pw.FlexColumnWidth(3),
                2: const pw.FlexColumnWidth(1.2),
                3: const pw.FlexColumnWidth(1),
                4: const pw.FlexColumnWidth(1.4),
                5: const pw.FlexColumnWidth(1.6),
              },
              children: [
                pw.TableRow(
                  decoration: const pw.BoxDecoration(color: PdfColors.grey100),
                  children: [
                    _tableCell('STT', align: pw.TextAlign.center, bold: true),
                    _tableCell(
                        isCash
                            ? 'Nội dung khoản thu/chi'
                            : 'Tên, nhãn hiệu, quy cách vật tư',
                        bold: true),
                    _tableCell(isCash ? 'Loại quỹ' : 'Mã VT', bold: true),
                    _tableCell(isCash ? 'Tiền tệ' : 'ĐVT',
                        align: pw.TextAlign.center, bold: true),
                    _tableCell('Số lượng / Số tiền',
                        align: pw.TextAlign.right, bold: true),
                    _tableCell('Ghi chú', bold: true),
                  ],
                ),
                ...lines.asMap().entries.map((entry) {
                  final idx = entry.key + 1;
                  final line = entry.value;
                  return pw.TableRow(
                    children: [
                      _tableCell('$idx', align: pw.TextAlign.center),
                      _tableCell(line.name),
                      _tableCell(line.sku),
                      _tableCell(line.unit, align: pw.TextAlign.center),
                      _tableCell(line.qty,
                          align: pw.TextAlign.right, bold: true),
                      _tableCell(line.note),
                    ],
                  );
                }),
              ],
            ),
            pw.SizedBox(height: 8),
            pw.Container(
              padding: const pw.EdgeInsets.symmetric(
                  horizontal: 10, vertical: 6),
              decoration: pw.BoxDecoration(
                color: PdfColors.grey100,
                border:
                    pw.Border.all(color: PdfColors.grey300, width: 0.5),
                borderRadius:
                    const pw.BorderRadius.all(pw.Radius.circular(4)),
              ),
              child: pw.Row(
                mainAxisAlignment: pw.MainAxisAlignment.spaceBetween,
                children: [
                  pw.Text(
                    'Tổng cộng quy mô / Giá trị chứng từ:',
                    style: pw.TextStyle(
                        fontSize: 9, fontWeight: pw.FontWeight.bold),
                  ),
                  pw.Text(
                    item.impact,
                    style: pw.TextStyle(
                      fontSize: 10,
                      fontWeight: pw.FontWeight.bold,
                      color: PdfColors.blue900,
                    ),
                  ),
                ],
              ),
            ),
            pw.SizedBox(height: 4),
            pw.Text(
              'Số chứng từ gốc kèm theo: 01 bộ chứng từ lưu trữ sổ sách kế toán.',
              style: pw.TextStyle(
                  fontSize: 7.5,
                  fontStyle: pw.FontStyle.italic,
                  color: PdfColors.grey700),
            ),

            pw.Spacer(),

            // Chữ ký 4 bên chuẩn mực kế toán Việt Nam
            pw.Divider(thickness: 0.5, color: PdfColors.grey400),
            pw.SizedBox(height: 6),
            pw.Row(
              mainAxisAlignment: pw.MainAxisAlignment.spaceBetween,
              crossAxisAlignment: pw.CrossAxisAlignment.start,
              children: [
                _signatureColumn(
                    'NGƯỜI LẬP PHIẾU', '(Ký, ghi rõ họ tên)', item.maker),
                _signatureColumn(
                  isCash
                      ? 'NGƯỜI NỘP / NHẬN'
                      : (isInbound ? 'NGƯỜI GIAO HÀNG' : 'NGƯỜI NHẬN HÀNG'),
                  '(Ký, ghi rõ họ tên)',
                  '',
                ),
                _signatureColumn(
                  isCash ? 'THỦ QUỸ' : 'THỦ KHO',
                  '(Ký, ghi rõ họ tên)',
                  '',
                ),
                _signatureColumn(
                  'QUẢN LÝ / NGƯỜI PHÊ DUYỆT',
                  '(Ký, ghi rõ họ tên)',
                  item.status == 'approved' ? 'Đã duyệt' : '',
                ),
              ],
            ),
            pw.SizedBox(height: 12),
            pw.Divider(thickness: 0.5, color: PdfColors.grey300),
            pw.Row(
              mainAxisAlignment: pw.MainAxisAlignment.spaceBetween,
              children: [
                pw.Text(
                  'Hệ thống QuanLyKho · Chứng từ điện tử chuẩn quy định.',
                  style:
                      const pw.TextStyle(fontSize: 7, color: PdfColors.grey600),
                ),
                pw.Text(
                  'Thời gian in: ${AppFormat.dateTime(now)}',
                  style:
                      const pw.TextStyle(fontSize: 7, color: PdfColors.grey600),
                ),
              ],
            ),
          ],
        ),
      ),
    );
    return doc.save();
  }

  static pw.Widget _infoRow(String label, String value) {
    return pw.Padding(
      padding: const pw.EdgeInsets.only(bottom: 3.5),
      child: pw.Row(
        crossAxisAlignment: pw.CrossAxisAlignment.start,
        children: [
          pw.SizedBox(
            width: 175,
            child: pw.Text(
              label,
              style: const pw.TextStyle(
                fontSize: 8.5,
                color: PdfColors.grey800,
              ),
            ),
          ),
          pw.Expanded(
            child: pw.Text(
              value,
              style: pw.TextStyle(
                fontSize: 9,
                fontWeight: pw.FontWeight.bold,
                color: PdfColors.black,
              ),
            ),
          ),
        ],
      ),
    );
  }

  static pw.Widget _tableCell(
    String text, {
    pw.TextAlign align = pw.TextAlign.left,
    bool bold = false,
  }) {
    return pw.Padding(
      padding: const pw.EdgeInsets.symmetric(horizontal: 5, vertical: 4),
      child: pw.Text(
        text,
        textAlign: align,
        style: pw.TextStyle(
          fontSize: 7.5,
          fontWeight: bold ? pw.FontWeight.bold : pw.FontWeight.normal,
        ),
      ),
    );
  }

  static pw.Widget _signatureColumn(
      String title, String subtitle, String signerName) {
    return pw.Expanded(
      child: pw.Column(
        children: [
          pw.Text(
            title,
            textAlign: pw.TextAlign.center,
            style: pw.TextStyle(
              fontSize: 8,
              fontWeight: pw.FontWeight.bold,
              color: PdfColors.blue900,
            ),
          ),
          pw.SizedBox(height: 2),
          pw.Text(
            subtitle,
            textAlign: pw.TextAlign.center,
            style: const pw.TextStyle(fontSize: 6.5, color: PdfColors.grey600),
          ),
          pw.SizedBox(height: 38),
          if (signerName.isNotEmpty)
            pw.Text(
              signerName,
              textAlign: pw.TextAlign.center,
              style: pw.TextStyle(
                fontSize: 8,
                fontWeight: pw.FontWeight.bold,
                color: PdfColors.black,
              ),
            ),
        ],
      ),
    );
  }

  static List<_VoucherLine> _parseLines(ApprovalItem item, bool isCash) {
    final list = <_VoucherLine>[];

    // Kiểm tra nếu detail có danh sách dòng dạng 'SKU: QTY UNIT, ...'
    if (item.detail.contains(':') && item.detail.contains(',')) {
      final parts = item.detail.split(',');
      for (final p in parts) {
        final trimmed = p.trim();
        if (trimmed.isEmpty) continue;
        final sub = trimmed.split(':');
        if (sub.length == 2) {
          final sku = sub[0].trim();
          final rest = sub[1].trim().split(' ');
          final qty = rest.isNotEmpty ? rest[0] : '1';
          final unit = rest.length > 1 ? rest.sublist(1).join(' ') : 'đơn vị';
          list.add(_VoucherLine(
            name: 'Nguyên liệu: $sku',
            sku: sku,
            unit: unit,
            qty: qty,
            note: 'Đúng quy chuẩn',
          ));
        }
      }
    } else if (item.detail.contains(':')) {
      final sub = item.detail.split(':');
      if (sub.length == 2) {
        final sku = sub[0].trim();
        final rest = sub[1].trim().split(' ');
        final qty = rest.isNotEmpty ? rest[0] : '1';
        final unit = rest.length > 1 ? rest.sublist(1).join(' ') : 'đơn vị';
        list.add(_VoucherLine(
          name: 'Nguyên liệu: $sku',
          sku: sku,
          unit: unit,
          qty: qty,
          note: 'Đúng quy chuẩn',
        ));
      }
    }

    if (list.isEmpty) {
      list.add(_VoucherLine(
        name: isCash
            ? (item.detail.isNotEmpty ? item.detail : 'Giao dịch thu/chi két quỹ tiền mặt')
            : (item.detail.isNotEmpty ? item.detail : 'Nguyên vật liệu theo chứng từ'),
        sku: isCash ? 'QUY-TM' : item.kind.toUpperCase(),
        unit: isCash ? 'VND' : 'Lô / Đợt',
        qty: item.impact,
        note: 'Theo phê duyệt hợp lệ',
      ));
    }
    return list;
  }
}

class _VoucherLine {
  const _VoucherLine({
    required this.name,
    required this.sku,
    required this.unit,
    required this.qty,
    required this.note,
  });

  final String name;
  final String sku;
  final String unit;
  final String qty;
  final String note;
}

/// Bỏ dấu tiếng Việt để in bằng font PDF built-in (WinAnsi).
class VnAscii {
  const VnAscii._();

  static const _map = {
    'à': 'a', 'á': 'a', 'ạ': 'a', 'ả': 'a', 'ã': 'a',
    'â': 'a', 'ầ': 'a', 'ấ': 'a', 'ậ': 'a', 'ẩ': 'a', 'ẫ': 'a',
    'ă': 'a', 'ằ': 'a', 'ắ': 'a', 'ặ': 'a', 'ẳ': 'a', 'ẵ': 'a',
    'è': 'e', 'é': 'e', 'ẹ': 'e', 'ẻ': 'e', 'ẽ': 'e',
    'ê': 'e', 'ề': 'e', 'ế': 'e', 'ệ': 'e', 'ể': 'e', 'ễ': 'e',
    'ì': 'i', 'í': 'i', 'ị': 'i', 'ỉ': 'i', 'ĩ': 'i',
    'ò': 'o', 'ó': 'o', 'ọ': 'o', 'ỏ': 'o', 'õ': 'o',
    'ô': 'o', 'ồ': 'o', 'ố': 'o', 'ộ': 'o', 'ổ': 'o', 'ỗ': 'o',
    'ơ': 'o', 'ờ': 'o', 'ớ': 'o', 'ợ': 'o', 'ở': 'o', 'ỡ': 'o',
    'ù': 'u', 'ú': 'u', 'ụ': 'u', 'ủ': 'u', 'ũ': 'u',
    'ư': 'u', 'ừ': 'u', 'ứ': 'u', 'ự': 'u', 'ử': 'u', 'ữ': 'u',
    'ỳ': 'y', 'ý': 'y', 'ỵ': 'y', 'ỷ': 'y', 'ỹ': 'y',
    'đ': 'd',
    'À': 'A', 'Á': 'A', 'Ạ': 'A', 'Ả': 'A', 'Ã': 'A',
    'Â': 'A', 'Ầ': 'A', 'Ấ': 'A', 'Ậ': 'A', 'Ẩ': 'A', 'Ẫ': 'A',
    'Ă': 'A', 'Ằ': 'A', 'Ắ': 'A', 'Ặ': 'A', 'Ẳ': 'A', 'Ẵ': 'A',
    'È': 'E', 'É': 'E', 'Ẹ': 'E', 'Ẻ': 'E', 'Ẽ': 'E',
    'Ê': 'E', 'Ề': 'E', 'Ế': 'E', 'Ệ': 'E', 'Ể': 'E', 'Ễ': 'E',
    'Ì': 'I', 'Í': 'I', 'Ị': 'I', 'Ỉ': 'I', 'Ĩ': 'I',
    'Ò': 'O', 'Ó': 'O', 'Ọ': 'O', 'Ỏ': 'O', 'Õ': 'O',
    'Ô': 'O', 'Ồ': 'O', 'Ố': 'O', 'Ộ': 'O', 'Ổ': 'O', 'Ỗ': 'O',
    'Ơ': 'O', 'Ờ': 'O', 'Ớ': 'O', 'Ợ': 'O', 'Ở': 'O', 'Ỡ': 'O',
    'Ù': 'U', 'Ú': 'U', 'Ụ': 'U', 'Ủ': 'U', 'Ũ': 'U',
    'Ư': 'U', 'Ừ': 'U', 'Ứ': 'U', 'Ự': 'U', 'Ử': 'U', 'Ữ': 'U',
    'Ỳ': 'Y', 'Ý': 'Y', 'Ỵ': 'Y', 'Ỷ': 'Y', 'Ỹ': 'Y',
    'Đ': 'D',
    '—': '-', '–': '-',
  };

  static String strip(String input) {
    final buffer = StringBuffer();
    for (final rune in input.runes) {
      final ch = String.fromCharCode(rune);
      if (_map.containsKey(ch)) {
        buffer.write(_map[ch]);
      } else if (rune < 128) {
        buffer.write(ch);
      } else {
        buffer.write('?');
      }
    }
    return buffer.toString();
  }
}
