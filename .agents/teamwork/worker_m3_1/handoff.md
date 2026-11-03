# Handoff Report: Bi-Directional Google Sheets API Service (Milestone M3: F8, F9, F10)

**Worker:** worker_m3_1  
**Role:** Google Sheets Integration Worker (Milestone M3)  
**Date:** 2026-11-02  
**Target Milestone:** Milestone M3 (Bi-Directional Google Sheets API Service: F8, F9, F10) in project QuanLyKho  

---

## 1. Observation (Quan Sát Trực Tiếp)

1. **Kiến trúc ETL 4 tầng & Dịch vụ Google Sheets hiện có:**
   - Trong `backend/app/models/etl.py`, các model `EtlConnection`, `EtlPipeline`, `EtlMappingVersion`, `EtlRun`, và `EtlRunRow` đã định nghĩa sẵn. Cột `EtlConnection.type` hỗ trợ giá trị `"google_sheets"`, và `EtlConnection.allowlist_sheets` hỗ trợ danh sách Sheet ID được phép truy cập.
   - `backend/app/services/google_sheets_service.py` trước đây chỉ có logic regex `extract_sheet_id()` và fallback qua Google Visualization CSV endpoint (`gviz/tq?tqx=out:csv`), chưa hỗ trợ gọi trực tiếp Google Sheets REST API v4 bằng Service Account hoặc OAuth Bearer token.
   - Chiều ghi ra Google Sheets trước đây chỉ hỗ trợ Apps Script webhook (`webhook_url`), chưa có API client ghi đè ô hoặc cập nhật hàng loạt qua API v4.
   - `google-auth` (`^2.30.0`) và `httpx` (`^0.27.0`) đã có sẵn trong `backend/pyproject.toml`.

2. **Các Bất biến Miền Nghiệp vụ cốt lõi:**
   - `inv_balances` không bao giờ được phép `UPDATE` trực tiếp cột `quantity`. Mọi điều chỉnh tồn kho bắt buộc phải sinh `InventoryRequest` và ghi nhận sổ cái bất biến `inv_movements`.
   - Cơ chế Maker-Checker (Two-man rule): người kích hoạt ETL (runner) khi tự post phiếu điều chỉnh tồn (`single_admin_override`) sẽ để phiếu ở trạng thái `draft` (`run.status = "pending_approval"`, `movements_count = 0`), chờ người kiểm tra độc lập phê duyệt.
   - Tính lũy thừa & khử trùng lặp: `compute_fingerprint()` băm SHA-256 các dòng dữ liệu để ngăn chặn chạy trùng phiên ETL.
   - Phòng chống Spreadsheet Formula Injection (CWE-1236): Mọi ô bắt đầu bằng `=`, `+`, `-`, `@`, `\t`, `\r` mà không phải số thuần túy đều phải được tiếp đầu ngữ bằng ký tự `'`.

3. **Quyền sở hữu tệp (Write Ownership):**
   - Đã tuân thủ nghiêm ngặt chỉ sửa/tạo 3 tệp thuộc quyền sở hữu độc quyền của Worker:
     * `backend/app/services/google_sheets_service.py`
     * `backend/app/api/routes/etl.py`
     * `backend/tests/test_google_sheets_sync.py`

---

## 2. Logic Chain (Chuỗi Lập Luận & Triển Khai)

1. **Feature F8 - Pure Async Google Sheets API v4 Client (`google_sheets_service.py`):**
   - Thay vì phụ thuộc vào thư viện đồng bộ nặng nề như `gspread` hay `google-api-python-client`, giải pháp sử dụng `google.oauth2.service_account.Credentials` và `google.oauth2.credentials.Credentials` từ gói `google-auth` có sẵn.
   - Xây dựng hàm `get_authorization_header()`:
     * Hỗ trợ nhận Service Account JSON dạng `dict` hoặc chuỗi JSON, ký JWT và lấy token qua `await asyncio.to_thread(creds.refresh, GoogleAuthRequest())`, bảo đảm hoàn toàn không block event loop của FastAPI.
     * Hỗ trợ OAuth 2.0 Credentials (với `access_token` hoặc `refresh_token`).
     * Hỗ trợ trực tiếp chuỗi Bearer token.
   - Triển khai `fetch_sheet_values(sheet_id, range_name, credentials_info, api_key)`:
     * Gọi endpoint `GET https://sheets.googleapis.com/v4/spreadsheets/{id}/values/{range}`.
     * Trả về danh sách ma trận ô `list[list[Any]]`.
   - Triển khai `write_sheet_values(sheet_id, range_name, values, credentials_info, value_input_option)`:
     * Gọi endpoint `PUT https://sheets.googleapis.com/v4/spreadsheets/{id}/values/{range}?valueInputOption=USER_ENTERED`.
     * Tự động áp dụng bộ lọc formula injection (CWE-1236) lên từng ô dữ liệu.
   - Triển khai `batch_update_sheet_values(sheet_id, data, credentials_info, value_input_option)`:
     * Gọi endpoint `POST https://sheets.googleapis.com/v4/spreadsheets/{id}/values:batchUpdate`.
   - Xử lý giới hạn tốc độ (Rate Limit):
     * Hàm `_request_with_retry` tự động bắt mã lỗi HTTP 429 và 503, thực hiện Exponential Backoff có Jitter:
       $$\text{delay} = \min(10.0, \text{initial\_delay} \times 2^{\text{attempt} - 1}) + \text{uniform}(0.01, 0.05)$$
     * Tôn trọng header `Retry-After` nếu Google API trả về.
     * Ghi nhận quan sát hợp lệ qua `record_external_dependency("google_sheets", outcome)`.

2. **Feature F9 - Inbound Google Sheets Staging & 4-Layer ETL Integration (`etl.py`):**
   - Trong `trigger_run` (`POST /etl/pipelines/{id}/runs`):
     * Nếu kết nối là `google_sheets` hoặc người dùng gửi `sheet_url` / `sheet_id`:
     * Tự động trích xuất `credentials_info` từ payload, `conn.config_json`, hoặc `conn.secret_ref`.
     * Kiểm tra an ninh: nếu `conn.allowlist_sheets` được cấu hình, xác thực Sheet ID phải nằm trong allowlist, nếu không trả `403 SHEET_NOT_ALLOWED`.
     * Kéo dữ liệu bất đồng bộ qua `google_sheets_service.fetch_sheet_rows(...)`.
     * Băm dữ liệu bằng SHA-256 (`compute_fingerprint`), kiểm tra trùng lặp để bảo đảm tính lũy thừa.
     * Đưa dữ liệu vào bảng Staging (`EtlRunRow`) với `status = "staged"`, sinh bản xem trước biến động (`action_preview`) để người kiểm tra rà soát.
     * Khi post giao dịch: tuân thủ nghiêm ngặt bất biến sổ cái kép (sinh `InventoryRequest` và `Movement`, không update thô `inv_balances`).

3. **Feature F10 - Outbound Google Sheets Sync & Status Writeback (`google_sheets_service.py` & `etl.py`):**
   - Trong `sync_out_to_google_sheet`:
     * Bổ sung cột `_sync_status` ("Trạng thái đồng bộ") với giá trị mặc định dạng `SYNCED_YYYY-MM-DD HH:MM:SS`.
     * Khử toàn bộ Spreadsheet Formula Injection (CWE-1236) cho mọi giá trị trước khi gửi lên API.
     * Ghi dữ liệu trực tiếp lên tab của Google Sheet qua API v4 bằng Service Account / OAuth credentials.
   - Bổ sung hàm `writeback_sheet_status`:
     * Cập nhật trạng thái từng dòng (`✓ HỢP LỆ...` hoặc `✗ LỖI: ...`) trực tiếp vào cột chỉ định trên Google Sheet.
   - Bổ sung 2 endpoint trên router `/etl`:
     * `POST /etl/runs/{run_id}/writeback`: Cập nhật trạng thái của từng dòng trong Run ngược lại trang tính Google Sheet.
     * `POST /etl/export-google-sheets`: Cho phép xuất các bộ dữ liệu nghiệp vụ (`catalog`, `balances`, `movements`, `cash_journal`, `inventory_summary`) sang Google Sheet.

4. **Kiểm thử tự động toàn diện (`test_google_sheets_sync.py`):**
   - Xây dựng 13 test cases bao phủ đầy đủ:
     * Trích xuất Sheet ID và chuyển đổi chỉ số cột sang chữ cái (1->A, 26->Z, 27->AA, ...).
     * Sinh Authorization Header từ Service Account (kèm sinh RSA key thật), OAuth credentials, chuỗi Bearer token.
     * MockTransport kiểm thử `fetch_sheet_values`, `write_sheet_values`, `batch_update_sheet_values`.
     * Khử formula injection CWE-1236 (bảo vệ các ký tự `=`, `+`, `-`, `@`, `\t`, `\r`).
     * Thử lại exponential backoff khi gặp HTTP 429 và thành công ở lần thử tiếp theo.
     * Xử lý lỗi chuẩn mực HTTP 403 (Forbidden) và 404 (Not Found).
     * Luồng Inbound Google Sheets staging, tính fingerprint SHA-256, và khử trùng lặp.
     * Cơ chế allowlist_sheets chặn truy cập trang tính ngoài danh mục.
     * Ràng buộc Maker-Checker và bất biến sổ cái kho.
     * Ghi ngược trạng thái xử lý dòng (`writeback`) và xuất dữ liệu (`export-google-sheets`).

---

## 3. Caveats (Các Điểm Lưu Ý)

1. **Google Sheets API Quota:** Google áp dụng hạn ngạch 300 requests/phút/project. Module đã được trang bị cơ chế batching (`batch_update_sheet_values`) và Exponential Backoff có jitter để vận hành ổn định dưới tải cao.
2. **Quyền chia sẻ Google Sheet:** Khi sử dụng xác thực bằng Service Account, người quản lý trang tính bắt buộc phải chia sẻ (Share) Google Sheet với email của Service Account (`client_email`) và cấp quyền "Chỉnh sửa" (Editor) để thực hiện chiều ghi.
3. **Môi trường cơ sở dữ liệu kiểm thử:** Bộ test integration yêu cầu database PostgreSQL có tên chứa hậu tố `_test` (ví dụ `bankops_test`) để bảo vệ dữ liệu môi trường phát triển theo quy ước an toàn của dự án.

---

## 4. Conclusion (Kết Luận)

Milestone M3 đã được hoàn thiện 100% với chất lượng cao:
- **Feature F8 (Pure Async Google Sheets v4 API Client):** Đã hoàn thành trong `google_sheets_service.py` với zero heavy dependencies (`google-auth` + `httpx.AsyncClient`), hỗ trợ Service Account, OAuth, API key, và Exponential Backoff khi gặp HTTP 429/503.
- **Feature F9 (Inbound Staging & 4-Layer ETL Integration):** Đã tích hợp hoàn chỉnh vào `/etl/pipelines/{id}/runs`, tự động kéo dữ liệu từ Google Sheets, băm SHA-256 fingerprint, kiểm tra allowlist, đưa vào staging với maker-checker, và duy trì tuyệt đối bất biến sổ cái kho.
- **Feature F10 (Outbound Sync & Writeback):** Đã hỗ trợ xuất các bộ dữ liệu nghiệp vụ, tự động đính kèm `_sync_status`, khử injection CWE-1236, và cung cấp endpoint writeback trạng thái hai chiều lên từng dòng bảng tính.
- **Tuân thủ quy chuẩn & kiểm thử:** Toàn bộ 18 test trong `tests/test_google_sheets_sync.py` và `tests/test_etl_pipeline.py` đều vượt qua thành công (`18 passed, 0 failed`). Mã nguồn tuân thủ Ruff linting không có bất kỳ cảnh báo nào.

---

## 5. Verification Method (Phương Pháp Xác Minh Độc Lập)

Người thẩm định hoặc các agent kế tiếp có thể kiểm chứng độc lập theo các bước sau:

1. **Kiểm tra cú pháp và quy chuẩn mã nguồn (Ruff check):**
   ```bash
   cd /Users/mainguyenbinhtan/Downloads/QuanLyKho/backend
   poetry run ruff check app/services/google_sheets_service.py app/api/routes/etl.py tests/test_google_sheets_sync.py
   ```
   *Kết quả mong đợi:* `All checks passed!`

2. **Chạy bộ kiểm thử tự động của Milestone M3 kết hợp bộ kiểm thử ETL Pipeline:**
   ```bash
   cd /Users/mainguyenbinhtan/Downloads/QuanLyKho/backend
   DATABASE_URL="postgresql+psycopg2://bankops:bankops@127.0.0.1:5432/bankops_test" poetry run pytest tests/test_google_sheets_sync.py tests/test_etl_pipeline.py -v
   ```
   *Kết quả mong đợi:* `18 passed in ~7-12s` (toàn bộ 13 test của Google Sheets Sync + 5 test của ETL Pipeline đều đạt).

3. **Chạy kiểm thử kiểm tra xuất file (Export Sync):**
   ```bash
   cd /Users/mainguyenbinhtan/Downloads/QuanLyKho/backend
   DATABASE_URL="postgresql+psycopg2://bankops:bankops@127.0.0.1:5432/bankops_test" poetry run pytest tests/test_export_sync.py -v
   ```
   *Kết quả mong đợi:* `4 passed in ~0.7s`.
