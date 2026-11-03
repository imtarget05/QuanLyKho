# Kiến Trúc Hạ Tầng Kiểm Thử E2E (TEST_INFRA.md) — QuanLyKho

**Dự án:** QuanLyKho (Kho Quản Lý & Ngân Hàng AI — Kho Trà Sữa Monolith)  
**Tác giả:** E2E Test Suite Architect & Writer (`test_writer_e2e_1`)  
**Ngày cập nhật:** 2026-11-02  
**Môi trường:** Python 3.11+ / FastAPI / SQLAlchemy 2.0 / PostgreSQL 16 (`bankops_test`) & Flutter 3.27+ / Dart 3.4+  

---

## 1. Triết Lý & Nguyên Tắc Kiểm Thử (Testing Philosophy & Guardrails)

Hệ thống `QuanLyKho` áp dụng kiến trúc **Modular Monolith Clean Architecture** kết hợp các chuẩn mực tài chính và ngân hàng khắt khe. Hạ tầng kiểm thử E2E được xây dựng dựa trên 5 nguyên tắc bất biến:

1. **Bất Biến Sổ Cái (Ledger Invariant - Append-only):**
   - Tuyệt đối không kiểm thử bằng cách cập nhật trực tiếp cột `quantity` trên bảng `inv_balances` (`UPDATE inv_balances SET quantity = ...`).
   - Mọi biến động tồn kho thực tế đều phải đi qua `InventoryRequest` -> phê duyệt -> sinh `Movement` và cập nhật `inv_balances` kèm khóa lạc quan `version`.
2. **Nguyên Tắc Kiểm Soát Kép (Maker-Checker Two-Man Rule):**
   - Người tạo giao dịch (Maker) không được tự phê duyệt giao dịch của chính mình (Checker), trừ trường hợp đặc biệt `single_admin_override` được cấp quyền kiểm toán rõ ràng.
3. **Phân Trang Keyset Con Trỏ Bắt Buộc (Keyset Cursor Pagination):**
   - Theo chuẩn `docs/06`, endpoint `GET /inventory/balances` trả dữ liệu phân trang con trỏ (mặc định 50 dòng, tối đa 100 dòng, trả `next_cursor`).
   - Mọi ca kiểm thử đọc số dư tồn kho **bắt buộc** dùng helper `fetch_all_balances(client, headers)` trong `conftest.py` để duyệt toàn bộ các trang, không bao giờ dùng một lệnh GET đơn lẻ nhằm tránh rủi ro "vô hình" dữ liệu trên database tích tụ.
4. **Cô Lập Môi Trường Database (Zero SQLite Policy):**
   - Tuyệt đối không dùng SQLite cho kiểm thử tích hợp (integration tests) do SQLite thiếu các tính năng PostgreSQL: khóa bi quan (`FOR UPDATE SKIP LOCKED`), kiểu JSONB, enum, composite foreign keys và concurrency.
   - `conftest.py:pytest_sessionstart` chặn đứng mọi kết nối database nếu tên database không chứa hậu tố `_test` (ví dụ: `bankops_test`).
5. **Chống Test Giả Mạo (No Facade Tests):**
   - Mọi test case phải kiểm thử logic nghiệp vụ thực, gọi endpoint thực, assert cấu trúc nhị phân thực (XLSX, CSV, PDF), kiểm tra database state thực.

---

## 2. Phương Pháp Luận Kiểm Thử 4 Tầng (Dual Track 4-Tier Methodology)

Bộ kiểm thử E2E được thiết kế theo mô hình 4 tầng phân cấp toàn diện:

```
┌────────────────────────────────────────────────────────────────────────┐
│ Tier 4: Real-World Scenarios (End-to-End Business Operations)          │
│ • Full Day Retail Tea Shop Operations                                  │
│ • Morning Inbound Sync -> Midday POS -> EOD Multi-Format Export        │
├────────────────────────────────────────────────────────────────────────┤
│ Tier 3: Cross-Feature Combinations                                     │
│ • GSheets Inbound -> ETL Staging -> Maker-Checker -> Export -> Audit   │
│ • Role Grant -> Outbox Event -> Token Invalidation -> UI Permission    │
├────────────────────────────────────────────────────────────────────────┤
│ Tier 2: Boundary & Corner Cases                                        │
│ • Empty Datasets, Large Payloads, Extreme Decimals, Special Chars     │
│ • Formula Injection Neutralization (CWE-1236: =, +, -, @, \t, \r)      │
├────────────────────────────────────────────────────────────────────────┤
│ Tier 1: Feature Coverage (F1 to F13)                                   │
│ • >= 5 Test Cases per Feature Domain                                   │
│ • Multi-format Export, Google Sheets Sync, Admin Notification, Viewport│
└────────────────────────────────────────────────────────────────────────┘
```

### 2.1. Phân Bổ Ca Kiểm Thử Theo Tính Năng (Feature Inventory Mapping)

| Mã Tính Năng | Mô Tả Nghiệp Vụ | Suite Phụ Trách | Số Ca Kiểm Thử |
|---|---|---|---|
| **F1** | Template Email Cấp Quyền Admin | `test_e2e_admin_notification_sync.py` | 5 ca (HTML structure, XSS escape, data placeholders, timestamp, branding) |
| **F2** | Gửi Email Post-Commit & Khả Năng Chịu Lỗi DB | `test_e2e_admin_notification_sync.py` | 5 ca (Commit first, SMTP error resilience, timeout safety, non-blocking notification) |
| **F3** | Cập Nhật Vai Trò & Thu Hồi Phiên /auth/me | `test_e2e_admin_notification_sync.py` | 5 ca (auth_version increment, old token 401 revocation, new token capability unlock) |
| **F4** | Outbox Event & Audit Trail Phân Quyền | `test_e2e_admin_notification_sync.py` | 5 ca (Transactional outbox, append-only audit event, self-demotion invariant guards) |
| **F5** | Xuất Dữ Liệu Excel .xlsx Chuẩn Nhận Diện | `test_e2e_exports_multiformat.py` | 6 ca (Catalog, Balances, Movements, Cash, Summary, styling & column width) |
| **F6** | Xuất File CSV Chuẩn UTF-8 BOM Duy Nhất | `test_e2e_exports_multiformat.py` | 5 ca (Single BOM `\ufeff`, no double BOM `\xef\xbb\xbf\xef\xbb\xbf`, comma escaping) |
| **F7** | Khử Độc Formula Injection Bảng Tính (CWE-1236) | `test_e2e_exports_multiformat.py` | 6 ca (=, +, -, @, \t, \r prefix `'` neutralization across all columns) |
| **F8** | Kết Xuất Báo Cáo PDF Chuẩn Bảng Biểu & Mẫu BTC | `test_e2e_exports_multiformat.py` | 5 ca (PDF magic bytes `%PDF-`, media type `application/pdf`, header disposition) |
| **F9** | Phân Tích Google Sheet ID Từ Mọi Dạng URL | `test_e2e_gsheets_sync.py` | 5 ca (Edit, View, Pubhtml, Raw ID, Error handling for invalid IDs) |
| **F10** | Đọc Dữ Liệu Google Sheets v4 API & Gviz Fallback | `test_e2e_gsheets_sync.py` | 5 ca (v4 values matrix parse, public CSV fallback, 403/404 handling, empty sheet) |
| **F11** | Đẩy Dữ Liệu Hai Chiều & Webhook Apps Script | `test_e2e_gsheets_sync.py` | 5 ca (2D array serialization, Apps Script webhook push, sheet URL response) |
| **F12** | Đường Ống ETL Staging & Phê Duyệt 2 Người | `test_e2e_gsheets_sync.py` | 6 ca (GSheets connection -> Staging -> Diff preview -> Maker-Checker posting) |
| **F13** | Kiểm Toán Giao Diện Di Động Đa Kích Thước | `mobile_viewport_audit_test.dart` | 8 ca (Viewports 375x667, 390x844, 414x896: title visibility, no overflow, dialogs) |

---

## 3. Bản Đồ Tệp Kiểm Thử (E2E Test File Registry)

Hệ thống bao gồm 4 bộ kiểm thử chuyên sâu:

```
QuanLyKho/
├── backend/tests/
│   ├── test_e2e_exports_multiformat.py         # Kết xuất đa định dạng (XLSX, CSV Single-BOM, PDF, CWE-1236)
│   ├── test_e2e_gsheets_sync.py               # Đồng bộ Google Sheets hai chiều, ETL Staging & Maker-Checker
│   └── test_e2e_admin_notification_sync.py     # Cập nhật quyền Admin, Outbox, Thu hồi token & Email Resilience
└── frontend/test/
    └── mobile_viewport_audit_test.dart        # Kiểm toán Mobile Viewports (375x667, 390x844, 414x896)
```

---

## 4. Hướng Dẫn Thiết Lập & Chạy Kiểm Thử (Execution Guide)

### 4.1. Chạy Backend Test Suites

```bash
# 1. Chuyển vào thư mục backend
cd /Users/mainguyenbinhtan/Downloads/QuanLyKho/backend

# 2. Chạy toàn bộ 3 suite E2E backend mới với PostgreSQL bankops_test
DATABASE_URL="postgresql+psycopg2://bankops:bankops@127.0.0.1:5432/bankops_test" poetry run pytest \
  tests/test_e2e_exports_multiformat.py \
  tests/test_e2e_gsheets_sync.py \
  tests/test_e2e_admin_notification_sync.py \
  -v

# 3. Chạy riêng từng suite cụ thể:
# Multi-format exports
DATABASE_URL="postgresql+psycopg2://bankops:bankops@127.0.0.1:5432/bankops_test" poetry run pytest tests/test_e2e_exports_multiformat.py -v

# Google Sheets Sync & ETL
DATABASE_URL="postgresql+psycopg2://bankops:bankops@127.0.0.1:5432/bankops_test" poetry run pytest tests/test_e2e_gsheets_sync.py -v

# Admin Role Notification & Invalidation
DATABASE_URL="postgresql+psycopg2://bankops:bankops@127.0.0.1:5432/bankops_test" poetry run pytest tests/test_e2e_admin_notification_sync.py -v
```

### 4.2. Chạy Frontend Mobile Viewport Audit

```bash
# 1. Chuyển vào thư mục frontend
cd /Users/mainguyenbinhtan/Downloads/QuanLyKho/frontend

# 2. Chạy kiểm toán responsive mobile viewports
flutter test test/mobile_viewport_audit_test.dart
```

---

## 5. Dấu Hiệu Nhận Biết & Quy Trình Báo Cáo Lỗi (Defect Escalation Protocol)

Tuân thủ nghiêm ngặt nguyên tắc **Test Writer chỉ viết/sửa code test, không tự ý sửa code sản phẩm**:

1. **Lỗi Double-BOM trên CSV (`b'\xef\xbb\xbf\xef\xbb\xbf'`):**
   - Hiện tượng: `export_engine.py` sinh BOM `\ufeff`, `exports.py` lại encode bằng `"utf-8-sig"`.
   - Hành vi test: Test ghi nhận và xác thực độ sạch của BOM; phát hiện lỗi được ghi trong báo cáo bàn giao `handoff.md` để triển khai bản vá cho implementer.
2. **Regex định dạng Export thiếu PDF (`^(xlsx|csv)$`):**
   - Hiện tượng: Endpoint `/exports/*` hiện tại chỉ chấp nhận `xlsx` hoặc `csv`.
   - Hành vi test: Test kiểm tra tính lũy tiến (progressive testability), kiểm thử trực tiếp engine tạo PDF và kiểm thử validation của router, sẵn sàng tự động pass khi implementer mở rộng regex sang `^(xlsx|csv|pdf)$`.
3. **Lệch Keyset Cursor Pagination:**
   - Mọi truy vấn tồn kho đều dùng `fetch_all_balances()` để đảm bảo tính ổn định kể cả khi database có hàng trăm dòng tồn kho tích tụ.
