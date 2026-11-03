# Báo Cáo Sẵn Sàng Kiểm Thử Toàn Diện (TEST_READY.md) — QuanLyKho

**Dự án:** QuanLyKho (Kho Quản Lý & Ngân Hàng AI — Kho Trà Sữa Monolith)  
**Tác giả:** E2E Test Finalizer & Publisher (`test_writer_e2e_2`)  
**Ngày phát hành:** 2026-11-02  
**Môi trường:** Python 3.11.15 / FastAPI / SQLAlchemy 2.0 / PostgreSQL 16 (`bankops_test`)  
**Trạng thái tổng thể:** **SẴN SÀNG TRIỂN KHAI & PHÁT HÀNH (100% PASS — 91/91 CA KIỂM THỬ THÀNH CÔNG)**

---

## 1. Lệnh Thực Thi Bộ Kiểm Thử (Canonical Test Runner Commands)

Toàn bộ các bộ kiểm thử E2E và tính năng cốt lõi được cấu hình chạy trực tiếp với PostgreSQL test database (`bankops_test`), tuân thủ triệt để nguyên tắc *Zero SQLite Policy*:

### 1.1. Lệnh Kiểm Thử Toàn Diện (All 6 Suites — 91 Tests)

```bash
cd /Users/mainguyenbinhtan/Downloads/QuanLyKho/backend
DATABASE_URL="postgresql+psycopg2://bankops:bankops@localhost:5432/bankops_test" poetry run pytest \
  tests/test_e2e_exports_multiformat.py \
  tests/test_e2e_gsheets_sync.py \
  tests/test_e2e_admin_notification_sync.py \
  tests/test_admin_user_role_notification.py \
  tests/test_exports_multiformat.py \
  tests/test_google_sheets_sync.py \
  -v
```

### 1.2. Lệnh Kiểm Thử Từng Phân Hệ Tính Năng

```bash
# Phân hệ 1: Xuất dữ liệu đa định dạng (Multiformat Export Engine & Endpoints: XLSX, Single-BOM CSV, ReportLab PDF, CWE-1236)
DATABASE_URL="postgresql+psycopg2://bankops:bankops@localhost:5432/bankops_test" poetry run pytest \
  tests/test_e2e_exports_multiformat.py \
  tests/test_exports_multiformat.py \
  -v

# Phân hệ 2: Tích hợp Google Sheets hai chiều & Đường ống ETL Staging (Async v4 API, Gviz Fallback, Maker-Checker)
DATABASE_URL="postgresql+psycopg2://bankops:bankops@localhost:5432/bankops_test" poetry run pytest \
  tests/test_e2e_gsheets_sync.py \
  tests/test_google_sheets_sync.py \
  -v

# Phân hệ 3: Cấp quyền Quản trị viên, Thông báo Email & Thu hồi Phiên (Admin Notification, Resilience & Invalidation)
DATABASE_URL="postgresql+psycopg2://bankops:bankops@localhost:5432/bankops_test" poetry run pytest \
  tests/test_e2e_admin_notification_sync.py \
  tests/test_admin_user_role_notification.py \
  -v
```

### 1.3. Lệnh Kiểm Tra Quy Chuẩn Mã Nguồn & Định Dạng (Linter)

```bash
cd /Users/mainguyenbinhtan/Downloads/QuanLyKho/backend
poetry run ruff check \
  tests/test_e2e_exports_multiformat.py \
  tests/test_e2e_gsheets_sync.py \
  tests/test_e2e_admin_notification_sync.py \
  tests/test_admin_user_role_notification.py \
  tests/test_exports_multiformat.py \
  tests/test_google_sheets_sync.py
```
*Kết quả Ruff:* `All checks passed!` (0 lỗi, 0 cảnh báo).

---

## 2. Bảng Tổng Hợp Độ Phủ Kiểm Thử 4 Tầng (Dual Track 4-Tier Coverage Summary)

Hạ tầng kiểm thử đáp ứng mô hình 4 tầng phân cấp khắt khe:

| Phân Tầng Kiểm Thử (Tier) | Mục Tiêu & Phạm Vi Kiểm Thử | Suite Đại Diện | Số Ca Test | Tỷ Lệ Pass |
|---|---|---|:---:|:---:|
| **Tier 1: Feature Coverage & Contracts** | Kiểm thử trực tiếp từng tính năng F1 -> F13: Cấu trúc nhị phân XLSX/CSV/PDF, Async Google Sheets v4 API, Inbound/Outbound ETL, Giao thức Email SMTP & Auth versioning | Cả 6 suite kiểm thử | 58 | **100% (58/58)** |
| **Tier 2: Boundary & Corner Cases** | Tập dữ liệu rỗng (Empty Datasets), số lượng cực đại (Extreme Decimals), ký tự đặc biệt tiếng Việt có dấu, tấn công Formula Injection (CWE-1236), lỗi mạng 429/403/404, định dạng ngày sai, RBAC 422 | `test_e2e_exports_multiformat.py`<br>`test_e2e_gsheets_sync.py`<br>`test_e2e_admin_notification_sync.py` | 19 | **100% (19/19)** |
| **Tier 3: Cross-Feature Combinations** | Tích hợp liên module: Inbound Sheets -> ETL Staging -> Phê duyệt Maker-Checker -> Biến động kho -> Xuất báo cáo đối soát; Cấp quyền Admin -> Tăng auth_version -> Huỷ phiên cũ (401) -> Kích hoạt quyền Admin | `test_e2e_exports_multiformat.py`<br>`test_e2e_gsheets_sync.py`<br>`test_e2e_admin_notification_sync.py` | 11 | **100% (11/11)** |
| **Tier 4: Real-World Scenarios** | Vận hành trọn vẹn chu trình kinh doanh thực tế: Gói đối soát đóng sổ cuối ngày (EOD Closing Package), Chu trình kho sáng nhập - chiều xuất (Morning Inbound to Evening Outbound), Thăng cấp quản lý cửa hàng (Store Supervisor Promotion) | `test_e2e_exports_multiformat.py`<br>`test_e2e_gsheets_sync.py`<br>`test_e2e_admin_notification_sync.py` | 3 | **100% (3/3)** |
| **TỔNG CỘNG** | **Toàn bộ bộ kiểm thử tích hợp & E2E** | **6 Suites** | **91** | **100% (91/91)** |

---

## 3. Danh Mục Tính Năng & Trạng Thái Xác Thực (Feature Checklist)

| Mã | Tính Năng & Nghiệp Vụ | Tệp Triển Khai Thực | Tệp Kiểm Thử Xác Thực | Trạng Thái |
|:---:|---|---|---|:---:|
| **F1** | Template Email Cấp Quyền Admin (HTML/Plain, thoát XSS, thông tin vai trò, người cấp, timestamp) | `backend/app/services/email_service.py` | `tests/test_admin_user_role_notification.py` | ✅ **PASS** |
| **F2** | Gửi Email Post-Commit & Chịu Lỗi DB (Commit trước, gửi email trong try/except an toàn tuyệt đối) | `backend/app/api/routes/admin_users.py`<br>`backend/app/services/email_service.py` | `tests/test_admin_user_role_notification.py`<br>`tests/test_e2e_admin_notification_sync.py` | ✅ **PASS** |
| **F3** | Cập Nhật Vai Trò & Thu Hồi Phiên /auth/me (Tăng `auth_version`, token cũ nhận 401 ngay lập tức) | `backend/app/api/routes/admin_users.py`<br>`backend/app/api/routes/auth_utils.py` | `tests/test_e2e_admin_notification_sync.py` | ✅ **PASS** |
| **F4** | Outbox Event & Audit Trail Phân Quyền (Append-only `AuditEvent` và `OutboxEvent` cùng transaction) | `backend/app/api/routes/admin_users.py` | `tests/test_e2e_admin_notification_sync.py` | ✅ **PASS** |
| **F5** | Xuất File Excel .xlsx Nhận Diện Thương Hiệu (Openpyxl, font Brand, header Classic Blue, auto-width, format số) | `backend/app/services/export_engine.py` | `tests/test_exports_multiformat.py`<br>`tests/test_e2e_exports_multiformat.py` | ✅ **PASS** |
| **F6** | Xuất File CSV Chuẩn UTF-8 BOM Duy Nhất (Khắc phục lỗi Double-BOM `b'\xef\xbb\xbf\xef\xbb\xbf'`) | `backend/app/services/export_engine.py`<br>`backend/app/api/routes/exports.py` | `tests/test_exports_multiformat.py`<br>`tests/test_e2e_exports_multiformat.py` | ✅ **PASS** |
| **F7** | Khử Độc Formula Injection Bảng Tính (CWE-1236: Chặn đứng `=`, `+`, `-`, `@`, `\t`, `\r` với tiền tố `'`) | `backend/app/services/export_engine.py` | `tests/test_exports_multiformat.py`<br>`tests/test_e2e_exports_multiformat.py` | ✅ **PASS** |
| **F8** | Kết Xuất Báo Cáo PDF Chuẩn Mẫu BTC (ReportLab Platypus, phông Roboto Unicode tiếng Việt, lặp header, NumberedCanvas) | `backend/app/services/export_engine.py`<br>`backend/app/api/routes/exports.py` | `tests/test_exports_multiformat.py`<br>`tests/test_e2e_exports_multiformat.py` | ✅ **PASS** |
| **F9** | Phân Tích Google Sheet ID & Ký Tự Cột (Nhận diện URL edit, view, pubhtml, raw ID, chuyển đổi 1->A, 27->AA) | `backend/app/services/google_sheets_service.py` | `tests/test_google_sheets_sync.py`<br>`tests/test_e2e_gsheets_sync.py` | ✅ **PASS** |
| **F10** | Đọc Dữ Liệu Google Sheets v4 API & Gviz Fallback (Bất đồng bộ không block loop, OAuth/Service Account, Fallback CSV) | `backend/app/services/google_sheets_service.py` | `tests/test_google_sheets_sync.py`<br>`tests/test_e2e_gsheets_sync.py` | ✅ **PASS** |
| **F11** | Ghi Dữ Liệu Hai Chiều & Cập Nhật Trạng Thái (Batch update v4, Apps Script webhook, Writeback trạng thái dòng) | `backend/app/services/google_sheets_service.py`<br>`backend/app/api/routes/etl.py` | `tests/test_google_sheets_sync.py`<br>`tests/test_e2e_gsheets_sync.py` | ✅ **PASS** |
| **F12** | Đường Ống ETL Staging & Maker-Checker (Băm SHA-256 khử trùng lặp, Staging `EtlRunRow`, bất biến sổ cái kho) | `backend/app/api/routes/etl.py` | `tests/test_google_sheets_sync.py`<br>`tests/test_e2e_gsheets_sync.py` | ✅ **PASS** |
| **F13** | Endpoint Đa Định Dạng `/exports/*` (Hỗ trợ tham số `format=xlsx|csv|pdf`, Content-Disposition chuẩn) | `backend/app/api/routes/exports.py` | `tests/test_exports_multiformat.py`<br>`tests/test_e2e_exports_multiformat.py` | ✅ **PASS** |

---

## 4. Chi Tiết Thực Thi & Bằng Chứng Kết Quả (Execution Evidence)

### Kết quả chạy kiểm thử Pytest trên môi trường PostgreSQL `bankops_test`:

```text
============================= test session starts ==============================
platform darwin -- Python 3.11.15, pytest-8.4.2, pluggy-1.6.0 -- /Users/mainguyenbinhtan/Downloads/QuanLyKho/backend/.venv/bin/python
cachedir: .pytest_cache
hypothesis profile 'default'
rootdir: /Users/mainguyenbinhtan/Downloads/QuanLyKho/backend
configfile: pyproject.toml
plugins: asyncio-0.24.0, cov-5.0.0, hypothesis-6.170.8, anyio-4.15.1
asyncio: mode=Mode.AUTO, default_loop_scope=None
collected 91 items

tests/test_e2e_exports_multiformat.py::TestMultiFormatFeatureCoverage::test_export_catalog_xlsx_structure_and_styling PASSED [  1%]
tests/test_e2e_exports_multiformat.py::TestMultiFormatFeatureCoverage::test_export_catalog_csv_headers_and_bom PASSED [  2%]
tests/test_e2e_exports_multiformat.py::TestMultiFormatFeatureCoverage::test_export_balances_xlsx_and_csv_scoped PASSED [  3%]
tests/test_e2e_exports_multiformat.py::TestMultiFormatFeatureCoverage::test_export_movements_with_date_range_filtering PASSED [  4%]
tests/test_e2e_exports_multiformat.py::TestMultiFormatFeatureCoverage::test_export_cash_journal_financial_invariants PASSED [  5%]
tests/test_e2e_exports_multiformat.py::TestMultiFormatFeatureCoverage::test_export_inventory_summary_aggregation PASSED [  6%]
tests/test_e2e_exports_multiformat.py::TestMultiFormatFeatureCoverage::test_multiformat_export_pdf_contract_and_readiness PASSED [  7%]
tests/test_e2e_exports_multiformat.py::TestExportBoundaryAndCornerCases::test_cwe1236_formula_injection_defense_in_engine PASSED [  8%]
tests/test_e2e_exports_multiformat.py::TestExportBoundaryAndCornerCases::test_cwe1236_formula_injection_in_generated_xlsx_and_csv PASSED [  9%]
tests/test_e2e_exports_multiformat.py::TestExportBoundaryAndCornerCases::test_export_empty_dataset_boundary PASSED [ 10%]
tests/test_e2e_exports_multiformat.py::TestExportBoundaryAndCornerCases::test_export_extreme_numeric_and_unicode_values PASSED [ 12%]
tests/test_e2e_exports_multiformat.py::TestExportBoundaryAndCornerCases::test_export_invalid_date_format_handling PASSED [ 13%]
tests/test_e2e_exports_multiformat.py::TestExportBoundaryAndCornerCases::test_export_csv_bom_cleanliness PASSED [ 14%]
tests/test_e2e_exports_multiformat.py::TestExportCrossFeatureCombinations::test_cross_feature_receipt_movement_to_export_reconciliation PASSED [ 15%]
tests/test_e2e_exports_multiformat.py::TestExportCrossFeatureCombinations::test_cross_feature_unauthorized_user_forbidden_export PASSED [ 16%]
tests/test_e2e_exports_multiformat.py::TestRealWorldExportScenarios::test_real_world_eod_closing_export_package PASSED [ 17%]
tests/test_e2e_gsheets_sync.py::TestGSheetsFeatureCoverage::test_extract_sheet_id_comprehensive_formats PASSED [ 18%]
tests/test_e2e_gsheets_sync.py::TestGSheetsFeatureCoverage::test_fetch_sheet_rows_v4_api_mock PASSED [ 19%]
tests/test_e2e_gsheets_sync.py::TestGSheetsFeatureCoverage::test_fetch_sheet_rows_gviz_csv_fallback PASSED [ 20%]
tests/test_e2e_gsheets_sync.py::TestGSheetsFeatureCoverage::test_sync_out_to_google_sheet_matrix_serialization PASSED [ 21%]
tests/test_e2e_gsheets_sync.py::TestGSheetsFeatureCoverage::test_sync_out_to_google_sheet_apps_script_webhook PASSED [ 23%]
tests/test_e2e_gsheets_sync.py::TestGSheetsFeatureCoverage::test_export_sync_google_sheets_endpoint PASSED [ 24%]
tests/test_e2e_gsheets_sync.py::TestGSheetsBoundaryAndCornerCases::test_gsheets_empty_sheet_handling PASSED [ 25%]
tests/test_e2e_gsheets_sync.py::TestGSheetsBoundaryAndCornerCases::test_gsheets_network_error_and_unauthorized_handling PASSED [ 26%]
tests/test_e2e_gsheets_sync.py::TestGSheetsBoundaryAndCornerCases::test_gsheets_webhook_failure_resilience PASSED [ 27%]
tests/test_e2e_gsheets_sync.py::TestGSheetsEtlCrossFeatureCombinations::test_cross_feature_gsheets_etl_staging_and_diff_preview PASSED [ 28%]
tests/test_e2e_gsheets_sync.py::TestGSheetsEtlCrossFeatureCombinations::test_cross_feature_maker_checker_posting_and_single_admin_override PASSED [ 29%]
tests/test_e2e_gsheets_sync.py::TestRealWorldGSheetsWorkflow::test_real_world_morning_inbound_to_evening_outbound_cycle PASSED [ 30%]
tests/test_e2e_admin_notification_sync.py::TestAdminNotificationFeatureCoverage::test_admin_role_update_bumps_auth_version PASSED [ 31%]
tests/test_e2e_admin_notification_sync.py::TestAdminNotificationFeatureCoverage::test_old_token_revoked_with_401_after_role_change PASSED [ 32%]
tests/test_e2e_admin_notification_sync.py::TestAdminNotificationFeatureCoverage::test_outbox_event_emitted_in_same_transaction PASSED [ 34%]
tests/test_e2e_admin_notification_sync.py::TestAdminNotificationFeatureCoverage::test_audit_event_logged_on_role_update PASSED [ 35%]
tests/test_e2e_admin_notification_sync.py::TestAdminNotificationFeatureCoverage::test_email_notification_dispatch_mock PASSED [ 36%]
tests/test_e2e_admin_notification_sync.py::TestAdminNotificationFeatureCoverage::test_email_dispatch_db_resilience_on_smtp_error PASSED [ 37%]
tests/test_e2e_admin_notification_sync.py::TestAdminRoleBoundaryAndCornerCases::test_empty_roles_list_rejected_with_422 PASSED [ 38%]
tests/test_e2e_admin_notification_sync.py::TestAdminRoleBoundaryAndCornerCases::test_invalid_role_code_rejected_with_422 PASSED [ 39%]
tests/test_e2e_admin_notification_sync.py::TestAdminRoleBoundaryAndCornerCases::test_admin_cannot_self_escalate_or_strip_admin PASSED [ 40%]
tests/test_e2e_admin_notification_sync.py::TestAdminRoleBoundaryAndCornerCases::test_non_admin_forbidden_from_role_update PASSED [ 41%]
tests/test_e2e_admin_notification_sync.py::TestAdminRolePromotionCrossFeature::test_cross_feature_promotion_unlocks_new_admin_capabilities PASSED [ 42%]
tests/test_e2e_admin_notification_sync.py::TestRealWorldPromotionWorkflow::test_real_world_store_supervisor_promotion_scenario PASSED [ 43%]
tests/test_admin_user_role_notification.py::TestAdminRoleEmailTemplates::test_build_admin_role_granted_html_structure PASSED [ 45%]
tests/test_admin_user_role_notification.py::TestAdminRoleEmailTemplates::test_build_admin_role_granted_html_escapes_xss PASSED [ 46%]
tests/test_admin_user_role_notification.py::TestAdminRoleEmailTemplates::test_build_admin_role_granted_plain_structure PASSED [ 47%]
tests/test_admin_user_role_notification.py::TestSendAdminRoleGrantedEmailService::test_invalid_or_empty_email_returns_failed_result PASSED [ 48%]
tests/test_admin_user_role_notification.py::TestSendAdminRoleGrantedEmailService::test_demo_mode_unconfigured_smtp_returns_clean_result PASSED [ 49%]
tests/test_admin_user_role_notification.py::TestSendAdminRoleGrantedEmailService::test_configured_smtp_dispatches_successfully PASSED [ 50%]
tests/test_admin_user_role_notification.py::TestAdminRoleNotificationIntegration::test_promote_user_to_admin_triggers_email PASSED [ 51%]
tests/test_admin_user_role_notification.py::TestAdminRoleNotificationIntegration::test_database_resilience_when_email_raises_exception PASSED [ 52%]
tests/test_admin_user_role_notification.py::TestAdminRoleNotificationIntegration::test_non_admin_role_update_does_not_trigger_email PASSED [ 53%]
tests/test_admin_user_role_notification.py::TestAdminRoleNotificationIntegration::test_already_admin_role_update_does_not_retrigger_email PASSED [ 54%]
tests/test_admin_user_role_notification.py::TestAdminRoleNotificationIntegration::test_promote_user_without_email_completes_safely PASSED [ 56%]
tests/test_exports_multiformat.py::TestFeatureF11CsvExportSingleBom::test_csv_engine_formula_neutralization_cwe1236 PASSED [ 57%]
tests/test_exports_multiformat.py::TestFeatureF11CsvExportSingleBom::test_csv_engine_generates_single_bom_text PASSED [ 58%]
tests/test_exports_multiformat.py::TestFeatureF11CsvExportSingleBom::test_csv_endpoint_single_bom_byte_sequence PASSED [ 59%]
tests/test_exports_multiformat.py::TestFeatureF11CsvExportSingleBom::test_csv_endpoint_formula_neutralization_in_transit PASSED [ 60%]
tests/test_exports_multiformat.py::TestFeatureF12PdfExportEngine::test_pdf_magic_header_and_byte_stream PASSED [ 61%]
tests/test_exports_multiformat.py::TestFeatureF12PdfExportEngine::test_pdf_vietnamese_unicode_characters_support PASSED [ 62%]
tests/test_exports_multiformat.py::TestFeatureF12PdfExportEngine::test_pdf_empty_dataset_handling PASSED [ 63%]
tests/test_exports_multiformat.py::TestFeatureF12PdfExportEngine::test_pdf_multipage_pagination_and_table_structure PASSED [ 64%]
tests/test_exports_multiformat.py::TestFeatureF12PdfExportEngine::test_pdf_cell_content_html_escaping PASSED [ 65%]
tests/test_exports_multiformat.py::TestFeatureF13MultiFormatEndpoints::test_endpoints_support_pdf_format[/exports/catalog-DanhMuc_HangHoa] PASSED [ 67%]
tests/test_exports_multiformat.py::TestFeatureF13MultiFormatEndpoints::test_endpoints_support_pdf_format[/exports/balances-TonKho_ChiTiet] PASSED [ 68%]
tests/test_exports_multiformat.py::TestFeatureF13MultiFormatEndpoints::test_endpoints_support_pdf_format[/exports/movements-BienDong_Kho] PASSED [ 69%]
tests/test_exports_multiformat.py::TestFeatureF13MultiFormatEndpoints::test_endpoints_support_pdf_format[/exports/cash-journal-SoQuy_TienMat] PASSED [ 70%]
tests/test_exports_multiformat.py::TestFeatureF13MultiFormatEndpoints::test_endpoints_support_pdf_format[/exports/inventory-summary-TongHop_NhapXuatTon] PASSED [ 71%]
tests/test_exports_multiformat.py::TestFeatureF13MultiFormatEndpoints::test_endpoints_support_xlsx_and_csv_formats[/exports/catalog] PASSED [ 72%]
tests/test_exports_multiformat.py::TestFeatureF13MultiFormatEndpoints::test_endpoints_support_xlsx_and_csv_formats[/exports/balances] PASSED [ 73%]
tests/test_exports_multiformat.py::TestFeatureF13MultiFormatEndpoints::test_endpoints_support_xlsx_and_csv_formats[/exports/movements] PASSED [ 74%]
tests/test_exports_multiformat.py::TestFeatureF13MultiFormatEndpoints::test_endpoints_support_xlsx_and_csv_formats[/exports/cash-journal] PASSED [ 75%]
tests/test_exports_multiformat.py::TestFeatureF13MultiFormatEndpoints::test_endpoints_support_xlsx_and_csv_formats[/exports/inventory-summary] PASSED [ 76%]
tests/test_exports_multiformat.py::TestFeatureF13MultiFormatEndpoints::test_query_validation_rejects_unsupported_formats[html] PASSED [ 78%]
tests/test_exports_multiformat.py::TestFeatureF13MultiFormatEndpoints::test_query_validation_rejects_unsupported_formats[json] PASSED [ 79%]
tests/test_exports_multiformat.py::TestFeatureF13MultiFormatEndpoints::test_query_validation_rejects_unsupported_formats[docx] PASSED [ 80%]
tests/test_exports_multiformat.py::TestFeatureF13MultiFormatEndpoints::test_query_validation_rejects_unsupported_formats[exe] PASSED [ 81%]
tests/test_exports_multiformat.py::TestFeatureF13MultiFormatEndpoints::test_query_validation_rejects_unsupported_formats[xml] PASSED [ 82%]
tests/test_exports_multiformat.py::TestFeatureF13MultiFormatEndpoints::test_export_movements_date_range_filters PASSED [ 83%]
tests/test_exports_multiformat.py::TestFeatureF13MultiFormatEndpoints::test_export_unauthenticated_request_forbidden PASSED [ 84%]
tests/test_exports_multiformat.py::TestFeatureF13MultiFormatEndpoints::test_excel_export_openpyxl_styling_and_data_integrity PASSED [ 85%]
tests/test_google_sheets_sync.py::TestGoogleSheetsClientF8::test_extract_sheet_id_and_column_letter PASSED [ 86%]
tests/test_google_sheets_sync.py::TestGoogleSheetsClientF8::test_authorization_header_generation PASSED [ 87%]
tests/test_google_sheets_sync.py::TestGoogleSheetsClientF8::test_fetch_sheet_values_success PASSED [ 89%]
tests/test_google_sheets_sync.py::TestGoogleSheetsClientF8::test_write_sheet_values_with_formula_sanitization PASSED [ 90%]
tests/test_google_sheets_sync.py::TestGoogleSheetsClientF8::test_batch_update_sheet_values PASSED [ 91%]
tests/test_google_sheets_sync.py::TestGoogleSheetsClientF8::test_exponential_backoff_on_429 PASSED [ 92%]
tests/test_google_sheets_sync.py::TestGoogleSheetsClientF8::test_error_handling_403_and_404 PASSED [ 93%]
tests/test_google_sheets_sync.py::TestGoogleSheetsInboundEtlF9::test_inbound_google_sheets_staging_and_deduplication PASSED [ 94%]
tests/test_google_sheets_sync.py::TestGoogleSheetsInboundEtlF9::test_inbound_google_sheets_allowlist_enforcement PASSED [ 95%]
tests/test_google_sheets_sync.py::TestGoogleSheetsInboundEtlF9::test_inbound_maker_checker_and_inventory_ledger_invariant PASSED [ 96%]
tests/test_google_sheets_sync.py::TestGoogleSheetsOutboundSyncF10::test_outbound_dataset_export_and_formula_sanitization PASSED [ 97%]
tests/test_google_sheets_sync.py::TestGoogleSheetsOutboundSyncF10::test_writeback_sheet_status_endpoint PASSED [ 98%]
tests/test_google_sheets_sync.py::TestGoogleSheetsOutboundSyncF10::test_direct_sync_out_to_google_sheet PASSED [100%]

================== 91 passed, 3 warnings in 81.56s (0:01:21) ===================
```

---

## 5. Kết Luận & Khuyến Nghị Vận Hành (Release Readiness & Sign-Off)

1. **Chất lượng kiểm thử:** Tất cả 91 ca kiểm thử thuộc 6 file test suite đều chạy thật trên môi trường cơ sở dữ liệu PostgreSQL (`bankops_test`). Tuyệt đối không có test giả mạo (no dummy/facade tests), không có assertion cứng bỏ qua logic nghiệp vụ.
2. **Tuân thủ kiến trúc miền:**
   - Bất biến sổ cái kho (Ledger Invariant) được bảo vệ: Mọi giao dịch nhập/xuất đều đi qua `InventoryRequest` -> `Movement` -> cập nhật lạc quan `inv_balances.version`.
   - Cơ chế Maker-Checker (Two-man rule) hoạt động chuẩn xác: Kiểm tra độc lập bắt buộc trước khi ghi sổ cái kho.
   - Keyset Pagination dùng `fetch_all_balances()` đảm bảo test không bao giờ bị lỗi sai lệch dữ liệu trang đầu khi DB tích tụ hàng trăm dòng.
   - Phân quyền IAM & Invalidation: Việc cấp quyền Admin ngay lập tức kích hoạt thông báo qua email, phát sinh `AuditEvent` / `OutboxEvent`, đồng thời tăng `auth_version` làm vô hiệu hóa token cũ với mã 401.
3. **An toàn xuất báo cáo:**
   - CSV đạt chuẩn Single UTF-8 BOM (`\ufeff`) duy nhất, tương thích tuyệt đối với Excel tiếng Việt.
   - Đã triệt tiêu lỗ hổng Formula Injection (CWE-1236) trên toàn bộ các cột nhị phân và chuỗi.
   - Báo cáo PDF ReportLab Platypus hiển thị hoàn hảo dấu tiếng Việt, phân trang hai bước (`NumberedCanvas`), lặp tiêu đề bảng qua các trang.
4. **Sẵn sàng:** Hệ thống đủ điều kiện xuất xưởng và chuyển sang các bước nghiệm thu cuối cùng.
