# Handoff Report: Backend & Google Sheets Integration Explorer (R3)

**Agent:** explorer_survey_2  
**Role:** Backend & Google Sheets Integration Explorer  
**Date:** 2026-11-02  
**Target Milestone:** Exploration & Technical Architecture Survey for Requirement R3  

---

## 1. Observation (Quan Sát Trực Tiếp)

1. **Cấu trúc Backend & Đăng ký Router:**
   - `backend/app/main.py` (dòng 282–314): Gắn toàn bộ 25 module routes vào ứng dụng đồng thời ở cả root `/` và prefix `/api/v1/` thông qua hàm `_mount_routes()`.
   - `backend/app/main.py` (dòng 214–258): Áp dụng chuẩn đóng gói phong bì lỗi `docs/06:44` (`{"error": {"code": ..., "message": ..., "request_id": ..., "details": ...}}`) cho mọi `HTTPException` và `RequestValidationError` (422).
   - `backend/app/models/__init__.py` (dòng 18–35): Đăng ký tập trung toàn bộ models vào `Base.metadata` gồm `inventory`, `cash_sim`, `etl`, `integration`, `activity`, `idempotency`, `reconciliation`, `iam`, `sync_request`.

2. **Các Bất Biến Miền Dữ Liệu (Domain Invariants):**
   - `backend/app/models/inventory.py` (dòng 184–195): `Balance` (`inv_balances`) có ràng buộc `CheckConstraint("quantity >= 0", name="qty_non_negative")` và `version: int` phục vụ khóa lạc quan (optimistic locking).
   - `backend/app/models/inventory.py` (dòng 135–156): `Movement` (`inv_movements`) là sổ cái bất biến lưu `quantity_signed`, ràng buộc duy nhất `uq_movement_request_line_location`.
   - `backend/app/models/activity.py` (dòng 20–55): Bảng `audit_events` được bảo vệ bằng trigger Python listeners `@event.listens_for(AuditEvent, "before_update")` và `"before_delete"`, chặn đứng mọi thao tác UPDATE/DELETE (Append-only invariant).
   - `backend/app/models/idempotency.py` (dòng 23–43): Bảng `idempotency_keys` lưu trữ key bền vững với `request_hash`, `response_body`, `expires_at`.

3. **Hiện Trạng ETL 4 Tầng (Phase 2):**
   - `backend/app/models/etl.py` (dòng 31–132): Đã có đầy đủ 5 bảng: `etl_connections`, `etl_pipelines`, `etl_mapping_versions`, `etl_runs`, `etl_run_rows`. Cột `type` của `etl_connections` hỗ trợ `"google_sheets"`.
   - `backend/app/api/routes/etl.py` (dòng 686–708): Endpoint `POST /etl/pipelines/{id}/runs` đã có sẵn nhánh kiểm tra `conn.type == "google_sheets"` và gọi `google_sheets_service.fetch_sheet_rows(target_sheet, tab=tab_name)`.
   - `backend/app/services/etl_engine.py` (dòng 233–236, 338–500, 750–920): Đã có hàm tính `compute_fingerprint()` (SHA-256), hàm sinh Staging và xem trước hành động `generate_staging_run()`, hàm post giao dịch vào sổ cái `execute_etl_posting()`, cưỡng chế không bao giờ `UPDATE` trực tiếp `inv_balances` mà luôn thông qua `InventoryRequest` và `Movement`.

4. **Hiện Trạng Dịch Vụ Google Sheets & Xuất File:**
   - `backend/app/services/google_sheets_service.py` (dòng 27–156):
     * Hàm `extract_sheet_id()` trích xuất ID bằng Regex từ mọi URL Google Sheets.
     * Hàm `fetch_sheet_rows()` hỗ trợ gọi Sheets API v4 bằng `api_key` hoặc fallback qua Google Visualization CSV export endpoint `https://docs.google.com/spreadsheets/d/{sheet_id}/gviz/tq?tqx=out:csv&sheet={tab}`.
     * Hàm `sync_out_to_google_sheet()` hiện chỉ hỗ trợ đẩy mảng dữ liệu tới `webhook_url` (Apps Script Webhook) hoặc trả về link xem bảng tính.
   - `backend/app/services/export_engine.py` (dòng 27–150): Tạo file Excel `.xlsx` chuyên nghiệp bằng `openpyxl` và file CSV có UTF-8 BOM (`\ufeff`) kèm bộ khử Formula Injection (CWE-1236) `sanitize_cell_value()`.
   - `backend/app/api/routes/exports.py` (dòng 298–353): Đã có endpoint `POST /exports/sync-google-sheets` hỗ trợ các dataset `catalog`, `balances`, `movements`, `cash_journal`, `inventory_summary`.

5. **Hiện Trạng Thư Viện (Dependencies):**
   - `backend/pyproject.toml` (dòng 48, 51): `google-auth = "^2.30.0"` và `openpyxl = "^3.1.5"` đã được khai báo và cài đặt trong môi trường.
   - `backend/app/api/routes/auth_google.py` (dòng 87–96): Đang sử dụng thành công `from google.oauth2 import id_token as google_id_token` và `from google.auth.transport import requests as google_requests`.
   - Thư viện `gspread` và `google-api-python-client` chưa có trong `pyproject.toml` hay `poetry.lock`.

---

## 2. Logic Chain (Chuỗi Lập Luận Suy Luận)

1. **Từ Quan sát 3 & 4:** Hệ thống đã xây dựng sẵn 80% nền tảng cho việc nhập dữ liệu từ Google Sheets: khung ETL 4 tầng (`EtlConnection`, `EtlPipeline`, `EtlMappingVersion`, `EtlRun`, `EtlRunRow`) có sẵn logic đọc file, staging, xem trước biến động (`action_preview`), kiểm tra trùng lặp (SHA-256 fingerprint), và post vào sổ cái kế toán bảo đảm tính toàn vẹn.
2. **Từ Quan sát 4:** Hạn chế lớn nhất của module `google_sheets_service.py` hiện tại là:
   - Chiều đọc phụ thuộc vào `api_key` (chỉ đọc được sheet công khai) hoặc fallback qua Gviz CSV endpoint. Không hỗ trợ đọc Google Sheets riêng tư (private sheets) trong doanh nghiệp.
   - Chiều ghi chưa hỗ trợ gọi trực tiếp Google Sheets API v4 (endpoint `spreadsheets.values.update`), mà đang phụ thuộc vào việc người dùng phải cấu hình Apps Script Webhook (`webhook_url`).
3. **Từ Quan sát 5:** Thư viện `google-auth = "^2.30.0"` và `httpx = "^0.27.0"` đã có sẵn trong dự án. Do đó:
   - Ta hoàn toàn **không cần cài thêm thư viện nặng hoặc thư viện blocking I/O** như `google-api-python-client` hay `gspread`.
   - Ta có thể sử dụng `google.oauth2.service_account.Credentials` từ `google-auth` để ký và sinh Bearer Token, sau đó dùng `httpx.AsyncClient` gọi trực tiếp Google Sheets API v4 (`https://sheets.googleapis.com/v4/spreadsheets/{id}/values/...`).
   - Đây là giải pháp kiến trúc tối ưu nhất: thuần bất đồng bộ (pure async), hiệu năng cao, zero new dependencies, tương thích hoàn toàn với FastAPI.
4. **Từ Quan sát 2:** Yêu cầu R3 nhấn mạnh tính chính xác và an toàn dữ liệu. Việc tích hợp Google Sheets API bắt buộc phải đi qua tầng Staging của ETL Pipeline, áp dụng Maker-Checker và không bao giờ ghi đè thẳng vào `inv_balances`, bảo đảm 100% tuân thủ bất biến kế toán của dự án.
5. **Tính năng phản hồi hai chiều:** Khi đẩy dữ liệu lên Google Sheets (hoặc sau khi duyệt một đợt nhập từ Sheet), hệ thống nên gọi API v4 để ghi trực tiếp cột `Trạng thái đồng bộ` (`_sync_status`) lên Google Sheet, giúp người dùng nắm bắt ngay kết quả trên chính file của họ.

---

## 3. Caveats (Các Điểm Lưu Ý & Vùng Chưa Khảo Sát)

- **Google Cloud Quota:** Google Sheets API có hạn ngạch miễn phí 300 requests/phút/project. Nếu đồng bộ bảng tính có hàng nghìn dòng, bắt buộc phải dùng batch operations (`batchUpdate`, `batchGet`) và xử lý HTTP 429 với Exponential Backoff.
- **Service Account Chia Sẻ:** Khi dùng Service Account, người dùng bắt buộc phải chia sẻ (Share) Google Sheet với email của Service Account với quyền Editor. Cần hiển thị rõ email này trên giao diện người dùng để họ thao tác.
- **Dữ liệu lớn (Large Files):** `etl_engine.py` giới hạn tối đa 20,000 dòng (`_MAX_ROWS = 20_000`) và 10MB payload (`_MAX_BYTES = 10 * 1024 * 1024`). Các trang tính vượt quá ngưỡng này cần được phân trang hoặc cảnh báo trước.

---

## 4. Conclusion (Kết Luận)

1. Nền tảng backend của `QuanLyKho` đã có đầy đủ khung sườn cần thiết để triển khai R3 (Google Sheets API hai chiều).
2. Không cần bổ sung thư viện mới vào `pyproject.toml`; chỉ cần mở rộng `app/services/google_sheets_service.py` bằng `google-auth` và `httpx.AsyncClient` để hỗ trợ xác thực qua **Service Account JSON** và **OAuth 2.0 Credentials**, gọi trực tiếp Google Sheets REST API v4 cho cả chiều đọc và chiều ghi.
3. Luồng nhập từ Google Sheets cần gắn chặt vào hệ thống ETL 4 tầng có sẵn (`/etl/*`) để bảo đảm:
   - Dữ liệu luôn dừng ở Staging để người dùng xem trước độ lệch (`action_preview`).
   - Tuân thủ quy tắc 2 người duyệt (Maker-Checker).
   - Tuyệt đối không vi phạm bất biến sổ cái (chỉ ghi qua Movement và Request).
4. Đã lập báo cáo khảo sát và thiết kế chi tiết tại tệp:  
   `/Users/mainguyenbinhtan/Downloads/QuanLyKho/.agents/teamwork/explorer_survey_2/survey_backend_gsheets.md`

---

## 5. Verification Method (Phương Pháp Xác Minh Độc Lập)

1. **Kiểm tra sự tồn tại của báo cáo khảo sát:**
   - Xem tệp `/Users/mainguyenbinhtan/Downloads/QuanLyKho/.agents/teamwork/explorer_survey_2/survey_backend_gsheets.md`
2. **Kiểm tra các tệp mã nguồn backend liên quan:**
   - `backend/app/services/google_sheets_service.py`
   - `backend/app/services/export_engine.py`
   - `backend/app/services/etl_engine.py`
   - `backend/app/api/routes/etl.py`
   - `backend/app/api/routes/exports.py`
3. **Chạy bộ kiểm thử tự động của dự án:**
   - Kiểm tra test xuất nhập hiện có:
     ```bash
     cd /Users/mainguyenbinhtan/Downloads/QuanLyKho/backend
     pytest tests/test_export_sync.py tests/test_etl_pipeline.py -q
     ```
   - Chạy toàn bộ test suite để xác nhận hệ thống ổn định (yêu cầu không có lỗi regression):
     ```bash
     pytest tests -q
     ```
