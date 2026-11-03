# Báo Cáo Khảo Sát Kỹ Thuật: Export Engine & Hạ Tầng Kiểm Thử (QuanLyKho)

**Người thực hiện**: Explorer Agent (`explorer_survey_3`)  
**Dự án**: QuanLyKho (Hệ thống Quản trị Kho Vận & Quỹ Mô Phỏng Core Banking)  
**Ngày khảo sát**: 2026-11-02  
**Mục tiêu**: Khảo sát chuyên sâu cơ chế kết xuất dữ liệu đa định dạng (R4: Excel, CSV, PDF) và hạ tầng kiểm thử (Unit, Integration, Acceptance) phục vụ lộ trình hoàn thiện R1, R2, R3, R4.

---

## 1. Tóm Tắt Khảo Sát (Executive Summary)

1. **Hiện trạng Module Export (Backend & Frontend)**:
   - Backend đã có sẵn module `app/api/routes/exports.py` và `app/services/export_engine.py` hỗ trợ kết xuất **Excel (.xlsx)** và **CSV (UTF-8 BOM)** cho 5 tập dữ liệu: *Catalog, Balances, Movements, Cash Journal, Inventory Summary*, cùng tính năng đẩy dữ liệu lên Google Sheets (`/exports/sync-google-sheets`).
   - Frontend đã có UI modal `ExportDialog` (`frontend/lib/src/features/sync/export_dialog.dart`), `CsvExport` (`csv_export.dart`), `ReportExcel` (`report_excel.dart`), và in chứng từ PDF mẫu BTC `ApprovalPdf` (`approval_pdf.dart`).
   - **Lỗ hổng hiện tại**: Backend **hoàn toàn chưa có xuất file PDF** (endpoint `/exports/*` regex chỉ cho phép `^(xlsx|csv)$`). Chưa có export cho các thực thể quan trọng: *Báo cáo đối soát (Reconciliation Runs & Exceptions)*, *Sổ nhật ký kiểm toán (Audit Events)*, và *Chứng từ phiếu thu/chi/nhập/xuất kho (Official Vouchers)*.
   - **Phát hiện lỗi mã hóa (Double-BOM Bug)**: `export_engine.generate_csv` đã chèn ký tự BOM `\ufeff`, sau đó `exports.py:79` lại encode bằng `"utf-8-sig"` khiến file CSV bị nhân đôi tiền tố BOM (`b'\xef\xbb\xbf\xef\xbb\xbf'`).

2. **Đánh giá Thư viện Xuất Dữ liệu (Excel, CSV, PDF)**:
   - **Excel**: `openpyxl==3.1.5` đã được cài đặt sẵn trong `backend/pyproject.toml`. Thư viện pure Python, hỗ trợ styling, border, font, auto column width. Hoạt động ổn định, không cần thêm `xlsxwriter`.
   - **CSV**: Sử dụng module built-in `csv` kết hợp sanitize công thức (CWE-1236) đã hoạt động tốt. Đối với tập dữ liệu lớn, cần nâng cấp sang cơ chế **StreamingResponse** để tránh OOM.
   - **PDF**: Đánh giá 3 ứng viên (`reportlab`, `fpdf2`, `weasyprint`). Do backend chạy container `python:3.11-slim`, **`fpdf2`** (pure Python, 0 C-dependencies) hoặc **`reportlab`** (pre-built wheels, Platypus table pagination) là lựa chọn tối ưu vượt trội so với `weasyprint` (quá nặng, đòi hỏi libcairo, libpango, gdk-pixbuf làm phình to image và chậm build).

3. **Hạ tầng Kiểm Thử (Testing Infrastructure)**:
   - Toàn bộ suite gồm 100 file test trong `backend/tests/`, đạt **387 passed, 8 skipped, 0 failed**.
   - Cơ chế DB test: **Tuyệt đối không dùng SQLite** cho integration test. `conftest.py:pytest_sessionstart` chặn đứng mọi DB không chứa hậu tố `_test`. Lệnh chuẩn: `make test-backend` khởi tạo container `postgres:16-alpine` trên cổng `5433` (tmpfs) rồi chạy `alembic upgrade head` + `pytest`.
   - Quy chuẩn đặc thù: `GET /inventory/balances` áp dụng keyset pagination (default 50, max 100), trong test bắt buộc dùng helper `fetch_all_balances()` từ `conftest.py` thay vì 1 GET đơn lẻ.

---

## 2. Khảo Sát Hiện Trạng Module Export

### 2.1 Backend Endpoints Hiện Hữu

Tập tin chính: `backend/app/api/routes/exports.py` (prefix `/exports`, tag `exports`):

| Endpoint | Method | Formats Hỗ Trợ | Tham số Lọc | Quyền Yêu Cầu (Capabilities) |
|---|---|---|---|---|
| `/exports/catalog` | GET | `xlsx`, `csv` | None | `_READ_CAPS` (inventory, cash, audit, admin) |
| `/exports/balances` | GET | `xlsx`, `csv` | `location_id` | Kiểm tra scope kho qua `get_accessible_location_ids` |
| `/exports/movements` | GET | `xlsx`, `csv` | `location_id`, `from_date`, `to_date` | Lọc theo location scope & khoảng thời gian ISO-8601 |
| `/exports/cash-journal` | GET | `xlsx`, `csv` | `from_date`, `to_date` | Kiểm tra capabilities thu chi / quỹ |
| `/exports/inventory-summary`| GET | `xlsx`, `csv` | `location_id`, `from_date`, `to_date` | Tổng hợp nhập/xuất/tồn theo ngày (bucket) |
| `/exports/sync-google-sheets`| POST | JSON payload | `sheet_url_or_id`, `tab`, `dataset` | Đẩy dataset lên Google Sheets qua REST API / Webhook |
| `/etl/runs/{id}/error-report`| GET | `csv`, `json` | None | Báo cáo chi tiết các bản ghi lỗi ETL |

### 2.2 Kiến Trúc Engine Hiện Tại (`backend/app/services/export_engine.py`)

- **Bảo mật Chống Formula Injection (CWE-1236)**:
  `sanitize_cell_value(val)` kiểm tra các ký tự kích hoạt công thức trên Excel / Google Sheets (`=`, `+`, `-`, `@`, `\t`, `\r`). Nếu không phải là số hợp lệ (`_NUMERIC_RE`), hàm tự động thêm tiền tố `'` để biến ô thành chuỗi thuần túy (Plain Text), ngăn chặn thực thi mã độc hoặc rò rỉ dữ liệu khi người dùng mở file bằng MS Excel.
- **Tạo File Excel (.xlsx)**:
  `generate_xlsx(rows, headers, title)`:
  - Dòng 1: Tiêu đề báo cáo (Font Calibri 14pt, Bold, Brand Classic Blue `#0F4C81`, merged cells).
  - Dòng 2: Metadata thời gian kết xuất (`dd/mm/yyyy hh:mm:ss`).
  - Dòng 3: Header bảng màu nền Classic Blue `#0F4C81`, chữ trắng, căn giữa.
  - Dòng 4 trở đi: Dữ liệu chi tiết, tự định dạng số (`#,##0` hoặc `#,##0.00`), ngày tháng (`yyyy-mm-dd hh:mm`).
  - Auto column width: Duyệt qua từng cột và tính toán `max(max_len + 4, 12)`.
- **Tạo File CSV**:
  `generate_csv(rows, headers)`:
  - Khởi tạo `io.StringIO()`.
  - Chèn mã UTF-8 BOM (`\ufeff`) ở đầu dòng.
  - Dùng `csv.writer` ghi header và các dòng dữ liệu đã qua sanitize.

### 2.3 Phát Hiện Lỗi: Vấn Đề Double-BOM trên CSV

Quan sát mã nguồn:
- Trong `backend/app/services/export_engine.py:133`:
  ```python
  output = io.StringIO()
  output.write("\ufeff")  # UTF-8 BOM ký tự Unicode
  ```
- Nhưng trong `backend/app/api/routes/exports.py:78-79`:
  ```python
  csv_content = export_engine.generate_csv(rows, headers)
  encoded = csv_content.encode("utf-8-sig")  # utf-8-sig tự động gắn thêm b'\xef\xbb\xbf'!
  ```
- **Hậu quả**: Khi encode bằng `"utf-8-sig"`, Python tự chèn thêm một BOM bytes `b'\xef\xbb\xbf'` vào trước nội dung vốn dĩ đã có ký tự `\ufeff`. Kết quả file nhị phân bắt đầu bằng `b'\xef\xbb\xbf\xef\xbb\xbf'`. Một số phần mềm phân tích CSV hoặc parser tự động sẽ báo lỗi `Invalid character` ở cột đầu tiên.
- **Giải pháp đề xuất**: Giữ nguyên `output.write("\ufeff")` trong engine và chỉ encode bằng `"utf-8"`, hoặc bỏ `output.write("\ufeff")` và để `"utf-8-sig"` thực hiện encode duy nhất một lần.

---

## 3. Đánh Giá & Lựa Chọn Thư Viện Xuất Dữ Liệu (Excel, CSV, PDF)

### 3.1 Excel (.xlsx)

| Thư viện | Tình trạng | Ưu điểm | Nhược điểm | Đánh giá / Khuyến nghị |
|---|---|---|---|---|
| **openpyxl** (3.1.5) | Đã cài (`pyproject.toml`) | Pure Python, hỗ trợ styling, màu sắc, border, font, format số, auto-width. Đã tích hợp sẵn trong codebase. | Tiêu tốn RAM khi tạo file > 50.000 dòng nếu không dùng chế độ `write_only=True`. | **Khuyến nghị giữ nguyên**. Đã đáp ứng hoàn hảo mọi yêu cầu nghiệp vụ hiện tại. |
| **xlsxwriter** | Chưa cài | Tốc độ ghi cực nhanh, có chế độ `constant_memory` tiết kiệm RAM tối đa. | Chỉ ghi (không đọc được), thêm 1 dependency vào `pyproject.toml`. | Chưa cần thiết trừ khi phát sinh nhu cầu xuất hàng trăm nghìn dòng liên tục. |

### 3.2 CSV

| Thư viện | Tình trạng | Ưu điểm | Nhược điểm | Đánh giá / Khuyến nghị |
|---|---|---|---|---|
| **Python built-in `csv`** | Sẵn có trong stdlib | 0 dependencies, tốc độ C-level, dễ dàng kết hợp generator để streaming qua HTTP. | Cần tự quản lý BOM và formula sanitization (hiện đã có trong `export_engine`). | **Khuyến nghị sử dụng chuẩn**. |
| **pandas** (2.2.0) | Đã cài | Mạnh về phân tích bảng dữ liệu lớn, chuyển đổi DataFrame sang CSV nhanh. | Khởi tạo DataFrame gây overhead bộ nhớ nếu chỉ cần serialize danh sách dict đơn giản. | Phù hợp cho module AI/ML/Forecasting hơn là endpoint xuất dữ liệu transactional. |

### 3.3 PDF (Đánh giá chuyên sâu tính khả thi trên Docker/FastAPI)

Hiện tại Backend chưa có thư viện tạo PDF. Cần bổ sung để đáp ứng **R4** (Multi-format Data Export: Excel, CSV, PDF).

| Tiêu chí | `fpdf2` | `reportlab` | `weasyprint` |
|---|---|---|---|
| **Kiến trúc & Ngôn ngữ** | Pure Python 100% | Python + C-extension nhẹ | Python + Pango/Cairo/GDK/libffi |
| **Footprint trên Docker** | **Siêu nhẹ (~1 MB)**, không cần bất kỳ gói hệ thống `apt-get` nào | **Nhẹ (~8 MB)**, có binary wheels manylinux, không cần cài thêm gói apt | **Rất nặng (+80 - 150 MB)**, bắt buộc `libcairo2`, `libpango-1.0-0`, `shared-mime-info`, `libgdk-pixbuf2.0-0` |
| **Tương thích `python:3.11-slim`** | **Hoàn hảo (100%)**, chạy ngay lập tức | **Rất tốt**, wheel cài đặt không lỗi | **Phải sửa `Dockerfile`**, thêm nhiều `apt-get install` làm chậm CI/CD |
| **Hỗ trợ Tiếng Việt (Unicode)** | Cực kỳ đơn giản: `pdf.add_font("Roboto", fname="font.ttf")` | Tốt: `pdfmetrics.registerFont(TTFont('Roboto', 'font.ttf'))` | Tự động theo fontconfig hệ thống |
| **Phân trang & Bảng biểu tự động** | Hỗ trợ table cơ bản, ngắt trang đơn giản | **Rất mạnh** nhờ Platypus `SimpleDocTemplate`, `Table`, tự lặp lại Header khi sang trang mới | Rất mạnh nhờ CSS paged media |
| **Tốc độ render** | **Cực nhanh (< 30ms / trang)** | **Nhanh (< 50ms / trang)** | Chậm (200ms - 800ms / trang), tốn CPU/RAM |
| **Rủi ro bảo mật (Attack Surface)** | Rất thấp (pure Python logic) | Rất thấp | Trung bình-Cao (render HTML/CSS, rủi ro SSRF nếu có resource external) |

#### Kết luận lựa chọn thư viện PDF:
- **Lựa chọn số 1**: **`reportlab`** hoặc **`fpdf2`**.
  - `reportlab` thích hợp nhất cho báo cáo bảng biểu nhiều trang (landscape A4 table) nhờ kiến trúc Flowables (`Table`, `Paragraph`) tự động tính toán ngắt trang và lặp lại dòng tiêu đề cột trên mỗi trang.
  - `fpdf2` thích hợp nhất nếu ưu tiên tính siêu nhẹ, pure-python không phụ thuộc nhị phân.
- Đã có sẵn file font Unicode Tiếng Việt trong dự án: `frontend/assets/fonts/Roboto-Regular.ttf`. Có thể sao chép hoặc trỏ đường dẫn font sang backend (hoặc bundle `Roboto-Regular.ttf` và `Roboto-Bold.ttf` vào thư mục assets của backend) để render dấu Tiếng Việt hoàn toàn không bị lỗi font.
- **Kiên quyết loại bỏ `weasyprint`**: Không phù hợp với container runtime tối giản `python:3.11-slim` và tiêu chí hiệu năng cao của FastAPI.

---

## 4. Phạm Vi Thực Thể Cần Hỗ Trợ Xuất Dữ Liệu (R4 Scope)

Hệ thống cần cung cấp xuất dữ liệu cho các nhóm thực thể sau:

### Nhóm 1: Các tập dữ liệu đã có (cần mở rộng định dạng PDF)
1. **Danh mục hàng hóa & nguyên liệu (`Item`)**:
   - Trường: Mã SKU, Tên hàng, ĐVT, Giá vốn, Giá bán, Tồn tối thiểu, Serial tracking, Trạng thái.
   - Định dạng: `.xlsx`, `.csv`, `.pdf` (Landscape A4 Catalog).
2. **Báo cáo tồn kho theo kho/vị trí (`Balance` + `Item` + `Location`)**:
   - Trường: SKU, Tên, ĐVT, Kho, Tồn thực tế, Giữ chỗ, Khả dụng, Giá vốn, Tổng giá trị tồn.
   - Định dạng: `.xlsx`, `.csv`, `.pdf` (Báo cáo tổng hợp kiểm kê kho).
3. **Sổ biến động kho / Ledger (`Movement` + `Item` + `Location`)**:
   - Trường: Thời gian ghi sổ, Phân loại nhập/xuất/chuyển, SKU, Tên hàng, Kho, Số lượng (+/-), Đơn giá, Thành tiền, Mã chứng từ.
   - Định dạng: `.xlsx`, `.csv`, `.pdf` (Sổ chi tiết vật tư hàng hóa).
4. **Sổ quỹ tiền mặt & Nhật ký thu chi (`CashJournal` + `CashRequest`)**:
   - Trường: Ngày hạch toán, Mã nhật ký, Mã phiếu, Loại thu/chi, Số tiền (VND), Trạng thái, Lý do.
   - Định dạng: `.xlsx`, `.csv`, `.pdf` (Sổ quỹ tiền mặt chi nhánh).
5. **Báo cáo tổng hợp Nhập - Xuất - Tồn (`Inventory Summary`)**:
   - Trường: Kỳ báo cáo (ngày/tháng), Tổng nhập, Tổng xuất, Biến động ròng, Số phiếu nhập, Số phiếu xuất.
   - Định dạng: `.xlsx`, `.csv`, `.pdf` (Bảng cân đối Nhập - Xuất - Tồn kỳ).

### Nhóm 2: Các tập dữ liệu mới cần bổ sung xuất dữ liệu
6. **Báo cáo đối soát chênh lệch (`ReconciliationReport`)**:
   - Căn cứ: `app/models/reconciliation.py` (`ReconciliationRun`, `ReconciliationException`).
   - Mục đích: Xuất biên bản đối soát giữa sổ cái (ledger) và read model (balances/cash).
   - Trường: Mã phiên đối soát, Phạm vi (inventory/cash), Thời gian, Đối tượng lệch (subject), Số liệu kỳ vọng (expected), Số liệu thực tế (actual), Chênh lệch (diff amount), Trạng thái xử lý (resolved).
   - Định dạng: `.xlsx`, `.csv`, `.pdf` (Biên bản đối soát định kỳ).
7. **Sổ nhật ký kiểm toán hệ thống (`AuditLog`)**:
   - Căn cứ: `app/models/activity.py` (`AuditEvent`).
   - Mục đích: Xuất log hoạt động phục vụ thanh tra/kiểm soát rủi ro độc lập (Maker-Checker, can thiệp quyền, đổi trạng thái).
   - Trường: Thời điểm, Người thực hiện (actor), Hành vi (action), Đối tượng tác động (subject), Mã yêu cầu (request_id), Dữ liệu trước/sau (hash/metadata).
   - Định dạng: `.xlsx`, `.csv`.
8. **In Chứng từ Nghiệp vụ Độc Lập (Single Voucher PDF)**:
   - Cung cấp endpoint: `GET /exports/vouchers/{request_id}/pdf`
   - Render trực tiếp chứng từ điện tử theo chuẩn biểu mẫu Bộ Tài Chính (Mẫu 01-VT Phiếu Nhập Kho, 02-VT Phiếu Xuất Kho, 01-TT Phiếu Thu, 02-TT Phiếu Chi) kèm 4 chữ ký (Người lập, Người giao/nhận, Thủ kho/Thủ quỹ, Kế toán/Quản lý phê duyệt).

---

## 5. Thiết Kế Kiến Trúc Export Engine Chuẩn

### 5.1 Kiến trúc luồng xử lý và Streaming Response

```text
[Client HTTP Request]
       │
       ▼
[FastAPI Route: /exports/{dataset}?format=xlsx|csv|pdf]
       │
       ├─► 1. Auth & Capability Verification (_verify_export_permission)
       ├─► 2. Scope Narrowing (Branch / Location Access Grants)
       ├─► 3. Query Execution (AsyncSession: Keyset pagination / yield_per)
       ├─► 4. Dataset Serializer (Chuẩn hóa Header & Row Values)
       │
       ▼
[Export Engine Format Adapter]
  ├── (format=csv)  ──► StreamingResponse(generator, media_type="text/csv")
  ├── (format=xlsx) ──► Response(openpyxl_bytes, media_type="vnd.openxmlformats...")
  └── (format=pdf)  ──► Response(reportlab_pdf_bytes, media_type="application/pdf")
```

### 5.2 Chuẩn Tiêu Đề HTTP (Headers & Content-Disposition)

Theo chuẩn RFC 6266 và RFC 5987 để hỗ trợ tên file Tiếng Việt trên mọi trình duyệt:
```python
filename_ascii = f"{dataset}_{timestamp}.{ext}"
filename_utf8 = f"{title_vietnamese}_{timestamp}.{ext}"

headers = {
    "Content-Disposition": f'attachment; filename="{filename_ascii}"; filename*=UTF-8\'\'{quote(filename_utf8)}',
    "Cache-Control": "no-cache, no-store, must-revalidate",
    "Pragma": "no-cache",
    "Expires": "0",
}
```

### 5.3 Hiệu Suất Bộ Nhớ & Xử Lý Dữ Liệu Lớn

1. **Với CSV**: Sử dụng `StreamingResponse` kết hợp `async generator` đọc theo từng batch (`yield_per(1000)`) từ PostgreSQL cursor, serialize từng dòng và `yield` chuỗi bytes về client ngay lập tức. Bộ nhớ RAM tiêu thụ luôn là hằng số $O(1)$, không phụ thuộc vào số lượng dòng dữ liệu ($1.000$ hay $1.000.000$ dòng).
2. **Với Excel (.xlsx)**: Đối với tập dữ liệu dưới 10.000 dòng, dùng workbook in-memory tiêu chuẩn. Nếu vượt quá 10.000 dòng, kích hoạt chế độ `openpyxl.Workbook(write_only=True)` để ghi tuần tự theo stream.
3. **Với PDF**: Giới hạn mặc định tối đa 1.000 dòng trên 1 báo cáo PDF (khoảng 30-40 trang A4 landscape). Nếu vượt quá giới hạn, khuyến cáo người dùng xuất Excel hoặc lọc khoảng ngày hẹp hơn để tránh tràn bộ nhớ trình tạo PDF.

---

## 6. Khảo Sát Hạ Tầng Kiểm Thử (Testing Infrastructure)

### 6.1 Cấu Trúc Suite & Fixtures Hiện Có (`backend/tests/`)

- Tổng cộng **100 file test** bao phủ toàn diện:
  - Unit tests cho schemas, models, services (`test_config_service.py`, `test_export_sync.py`, `test_email_service_templates.py`, `test_csv_export_injection.py`).
  - Integration tests với HTTP client mô phỏng quy trình Maker-Checker (`test_business_journey_full.py`, `test_phase1_stock_levels.py`, `test_cash_sim_money_path.py`).
  - Phân quyền & IAM Scopes (`test_iam_admin.py`, `test_b2_authorization_scope.py`, `test_milk_tea_rbac_uat.py`).
  - Báo cáo & Thống kê (`test_reports.py`).
  - Bảo mật & Secrets (`test_check_no_secrets.py`, `test_entrypoint_signing_key.py`, `test_anti_abuse_and_spam_prevention.py`).

### 6.2 Fixtures Cốt Lõi Trong `conftest.py`

1. **`pytest_sessionstart(session)`**:
   - Kiểm tra biến môi trường `DATABASE_URL`.
   - **Bắt buộc** tên database phải chứa chuỗi `_test` (ví dụ `bankops_test`).
   - Nếu phát hiện trỏ vào DB dev hoặc production, lập tức dừng chạy kiểm thử với `returncode=2` nhằm bảo vệ dữ liệu.
2. **`app` & `client`**:
   - `app`: Nạp FastAPI instance từ `app.main`, fail-fast nếu startup hook bị lỗi.
   - `client`: `fastapi.testclient.TestClient` khởi chạy toàn bộ middleware và dependency injection.
3. **`demo_mode`**:
   - Bật cờ `demo_mode=True` và ghi đè property `is_demo_mode` qua `monkeypatch` để đảm bảo test chạy ổn định với các tài khoản seed sẵn (`demo_maker`, `demo_checker`, `demo_admin`, `demo_auditor`).
4. **`reset_rate_limits`**:
   - Tự động dọn sạch từ điển rate-limit đăng nhập (`_login_failures.clear()`) trước và sau mỗi test để các ca kiểm thử không làm nghẽn nhau.
5. **`fetch_all_balances(client, headers, path="/inventory/balances", params=None)`**:
   - **Quy chuẩn sống còn**: `/inventory/balances` áp dụng keyset cursor pagination (`limit` tối đa 100, trả `next_cursor`). Helper này tự động lặp theo `next_cursor` cho đến khi gom đủ 100% dòng tồn kho.
6. **`open_shift(client, headers, location_id, shift_code)`**:
   - Tự động thử nghiệm các ngày kinh doanh trong tương lai để mở ca kiểm kê không bị đụng độ `409 SHIFT_ALREADY_OPEN` do dữ liệu tồn dư từ các lần chạy trước.

### 6.3 Môi Trường Database & Lệnh Chạy

1. **Docker Isolation**:
   `docker-compose.test.yml` chạy riêng PostgreSQL 16:
   ```yaml
   image: postgres:16-alpine
   environment:
     POSTGRES_DB: bankops_test
   tmpfs:
     - /var/lib/postgresql/data
   ```
   Dữ liệu nằm trên RAM (`tmpfs`), tự động xóa sạch khi teardown, không gây ô nhiễm môi trường dev.
2. **Lệnh thực thi**:
   ```bash
   make test-backend
   ```
   Hoặc chạy trực tiếp qua poetry/venv khi container test đang chạy:
   ```bash
   cd backend && DATABASE_URL="postgresql+psycopg2://bankops:bankops@127.0.0.1:5433/bankops_test" pytest tests -q
   ```
3. **Lệnh dọn dẹp dữ liệu**:
   Nếu chạy trên môi trường dev dùng chung, có thể chạy:
   ```bash
   cd backend && python -m app.reset_demo_db
   ```

---

## 7. Kế Hoạch & Thiết Kế Kiểm Thử Cho Các Yêu Cầu (R1, R2, R3, R4)

### 7.1 Kiểm thử Yêu Cầu R1: Cập nhật quyền Admin & Làm mới Giao diện (UI Refresh)

- **Mục tiêu**: Khi người dùng đang đăng nhập được gán quyền `admin`, hệ thống phát hiện và yêu cầu tải lại hoặc tự động refresh trang.
- **Cơ chế Backend cần test**:
  - Khi gọi `PUT /admin/users/{user_id}/roles` thêm role `admin`:
    1. Kiểm tra trường `user.auth_version` tăng lên $N+1$.
    2. Kiểm tra token cũ của user đó ngay lập tức bị từ chối với mã lỗi `401 UNAUTHORIZED` trên các request tiếp theo (`test_instant_session_revocation_invalidates_token`).
    3. Kiểm tra sự kiện SSE `approval_event_bus.publish` phát broadcast event (ví dụ `user_roles_updated` hoặc `iam.role_granted`) tới kênh SSE `/approvals/stream` hoặc `/events/stream`.
- **Cơ chế Frontend cần test**:
  - Test widget `AppShell` / `AuthController` khi nhận event SSE hoặc khi API trả về 401 do token hết hạn: hiển thị thông báo `AppToast.info` hoặc hộp thoại yêu cầu người dùng xác nhận làm mới phiên làm việc.
  - Test sau khi phiên làm việc được làm mới: menu Admin, các nút quản trị và route `/admin/*` mở khóa thành công.

### 7.2 Kiểm thử Yêu Cầu R2: Gửi Email Thông Báo Khi Cấp Quyền Admin

- **Mục tiêu**: Khi user được cấp quyền admin, gửi email thông báo chi tiết đến địa chỉ email của user; giao dịch DB vẫn thành công dù gửi email thất bại.
- **Cấu trúc Test Unit**:
  - Tạo file `backend/tests/test_admin_role_email.py`:
    1. `test_build_admin_role_granted_html_structure`: Kiểm tra template HTML chứa tên user, tên quản trị viên cấp quyền, thời điểm cấp, cảnh báo bảo mật ISO 27001, các quyền hạn mới.
    2. `test_build_admin_role_granted_escapes_xss`: Kiểm tra mọi trường dữ liệu đầu vào (tên, role) đều được escape chống XSS (CWE-79).
    3. `test_send_admin_role_granted_email_success`: Mock `_send_smtp_sync` trả về True, xác nhận trả về `EmailSendResult(True)`.
    4. `test_send_admin_role_granted_email_failure_resilient`: Mock SMTP ném ngoại lệ `smtplib.SMTPException` hoặc `ConnectionRefusedError`, xác nhận hàm bắt ngoại lệ an toàn, ghi log và trả về `EmailSendResult(False)` chứ không làm vỡ tiến trình.
- **Cấu trúc Test Integration**:
  - Trong `test_iam_admin.py`:
    1. Gọi `PUT /admin/users/{user_id}/roles` gán quyền `admin`.
    2. Mock `email_service.send_admin_role_granted_email`.
    3. Assert mock được gọi đúng 1 lần với địa chỉ email của user đích.
    4. Test khả năng chịu lỗi (Resilience Test): Giả lập email service chết hoàn toàn -> Assert endpoint `PUT /admin/users/{user_id}/roles` vẫn trả về `200 OK`, vai trò admin trong DB vẫn được lưu thành công (Fail-Open / Non-blocking notification).

### 7.3 Kiểm thử Yêu Cầu R3: Đồng Bộ Google Sheets (Google Sheets Sync)

- **Mục tiêu**: Kiểm thử tính năng đẩy/kéo dữ liệu giữa QuanLyKho và Google Sheets.
- **Nội dung kiểm thử**:
  - Kiểm tra parse Sheet ID từ các định dạng URL khác nhau (`edit#gid=0`, `/view`, `/pubhtml`, raw ID).
  - Kiểm tra serialize dữ liệu bảng tính khớp chuẩn định dạng 2D Array của Google Sheets API.
  - Kiểm tra xử lý lỗi khi URL không hợp lệ hoặc không có quyền truy cập.

### 7.4 Kiểm thử Yêu Cầu R4: Kết Xuất Dữ Liệu Đa Định Dạng (Excel, CSV, PDF)

- **Mục tiêu**: Xác thực toàn bộ các endpoint kết xuất dữ liệu hoạt động chính xác, an toàn, chuẩn font Tiếng Việt và không lỗi cú pháp.
- **Danh mục Ca Kiểm Thử**:
  1. **Định dạng Excel (.xlsx)**:
     - `GET /exports/{dataset}?format=xlsx` trả về HTTP 200, `media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"`.
     - Header `Content-Disposition` có thuộc tính `attachment; filename=...`.
     - Sử dụng `openpyxl.load_workbook` đọc lại nội dung: xác thực đúng tên sheet, dòng 1 là tiêu đề, dòng 3 là header, dữ liệu từ dòng 4, các ô số định dạng đúng.
  2. **Định dạng CSV**:
     - `GET /exports/{dataset}?format=csv` trả về HTTP 200, `media_type="text/csv; charset=utf-8"`.
     - Xác thực byte đầu tiên là UTF-8 BOM duy nhất (`b'\xef\xbb\xbf'`), không bị lỗi Double-BOM (`b'\xef\xbb\xbf\xef\xbb\xbf'`).
     - Xác thực chống formula injection: các ô chứa `=cmd`, `@SUM`, `+1`, `-1+1` đều được escape thành `'=...`.
  3. **Định dạng PDF**:
     - `GET /exports/{dataset}?format=pdf` trả về HTTP 200, `media_type="application/pdf"`.
     - Kiểm tra magic header PDF: bytes đầu tiên bắt đầu bằng `b'%PDF-'`.
     - Kiểm tra không phát sinh lỗi mã hóa ký tự tiếng Việt có dấu (`Đơn hàng, Báo cáo tồn kho, Nguyên vật liệu`).
  4. **Bảo mật & Phân quyền (Security & Scope Guards)**:
     - Gọi không có token hoặc token không có capability export -> HTTP 401 / 403.
     - Gọi với user bị giới hạn chi nhánh/kho -> Dữ liệu trả về chỉ chứa các dòng thuộc kho được phép truy cập (`get_accessible_location_ids`).
     - Gọi với `location_id` nằm ngoài phạm vi được cấp quyền -> HTTP 403 `SCOPE_FORBIDDEN`.

---

## 8. Khuyến Nghị Kỹ Thuật & Lộ Trình Triển Khai

1. **Sửa lỗi Double-BOM trong `exports.py`**:
   Điều chỉnh `_format_response` để chỉ mã hóa UTF-8 một lần duy nhất, tránh tình trạng file CSV có 2 lần BOM gây lỗi cho một số parser bên thứ ba.
2. **Bổ sung thư viện PDF vào `pyproject.toml`**:
   Thêm `reportlab = "^4.2.0"` (hoặc `fpdf2 = "^2.8.0"`) vào `[tool.poetry.dependencies]`. Cung cấp font `Roboto-Regular.ttf` và `Roboto-Bold.ttf` trong thư mục tài nguyên backend để in ấn Tiếng Việt chuẩn mực.
3. **Mở rộng Regex định dạng trên Router**:
   Cập nhật tham số format tại các endpoint:
   `format: str = Query("xlsx", pattern="^(xlsx|csv|pdf)$")`
4. **Bổ sung các hàm Serialize mới trong `export_engine.py`**:
   - `serialize_reconciliation_dataset(runs, exceptions)`
   - `serialize_audit_dataset(audit_events)`
   - `generate_pdf_table(rows, headers, title, orientation="landscape")`
   - `generate_voucher_pdf(request_data, lines, approvers)`
5. **Đồng bộ hóa Frontend UI**:
   - Cập nhật `ExportDialog` trong Flutter để thêm lựa chọn `PDF (.pdf)` trong `SegmentedButton`.
   - Bổ sung các tùy chọn xuất đối soát (Reconciliation) và lịch sử kiểm toán trong trang quản trị.

---
*Báo cáo được tổng hợp độc lập dựa trên khảo sát thực tế toàn bộ mã nguồn backend, frontend, cấu hình container và hệ thống kiểm thử tự động của dự án QuanLyKho.*
