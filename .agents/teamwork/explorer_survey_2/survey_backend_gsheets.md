# Báo Cáo Khảo Sát Kiến Trúc Backend & Thiết Kế Tích Hợp Google Sheets API Hai Chiều (R3)
**Dự án:** QuanLyKho (Kho Quản Lý & Ngân Hàng AI — Kho Trà Sữa Monolith)  
**Tác giả:** Explorer Agent (Backend & Google Sheets Integration Explorer)  
**Ngày lập:** 2026-11-02  
**Môi trường:** Python 3.11+ / FastAPI / SQLAlchemy 2.0 / Alembic / PostgreSQL 16 / Poetry  

---

## 1. Tóm Tắt Tổng Quan (Executive Summary)

Khảo sát toàn diện hệ thống backend của `QuanLyKho` cho thấy:
1. **Kiến trúc cốt lõi vững chắc:** Ứng dụng tuân thủ mô hình Modular Monolith Clean Architecture kết hợp các nguyên lý tài chính khắt khe (Double-entry Ledger Invariant, Append-only Audit, Outbox Pattern, Maker-Checker Two-Man Rule, Keyset Pagination).
2. **Hạ tầng ETL 4 tầng (Phase 2) đã sẵn sàng:** Hệ thống đã có sẵn khung ETL 4 lớp gồm `Connection` -> `Pipeline` -> `MappingVersion` -> `Run` -> `Review/Post` (`app/models/etl.py`, `app/api/routes/etl.py`, `app/services/etl_engine.py`). Mọi luồng nhập dữ liệu từ bên ngoài đều bị chặn ở tầng **Staging** (`EtlRunRow`), tính toán bản xem trước biến động (`action_preview`), kiểm tra trùng lặp qua dấu vân tay băm SHA-256, và chỉ được ghi vào sổ cái (Ledger) sau khi có phê duyệt độc lập.
3. **Hiện trạng tích hợp Google Sheets:** 
   - Đã có module sơ khai `app/services/google_sheets_service.py` hỗ trợ trích xuất Sheet ID, đọc dữ liệu qua API v4 (kèm API key) hoặc fallback qua Google Visualization CSV endpoint (`gviz/tq?tqx=out:csv`).
   - Chiều ghi ra Google Sheets hiện mới chỉ hỗ trợ bắn webhook sang Google Apps Script (`sync_out_to_google_sheet`) hoặc tạo file Excel/CSV tải về (`app/services/export_engine.py`).
4. **Khoảng trống cần hoàn thiện cho R3:**
   - Chưa hỗ trợ xác thực bằng **Service Account JSON** hoặc **OAuth 2.0 credentials** cho Google Sheets API v4 để đọc/ghi trực tiếp vào Google Sheets riêng tư (private sheets) mà không cần webhook Apps Script.
   - Thư viện `google-auth = "^2.30.0"` đã có sẵn trong `pyproject.toml`, nhưng chưa có client helper bất đồng bộ hoàn chỉnh cho Google Sheets v4 REST API để đọc/ghi hai chiều, cập nhật trạng thái đồng bộ trực tiếp lên từng dòng của Sheet.
   - Cần chuẩn hóa cấu trúc mẫu bảng tính (Sheet Templates) và cơ chế phản hồi trạng thái đồng bộ (Sync status feedback / In-sheet error marking).

---

## 2. Cấu Trúc Ứng Dụng Backend & Vòng Đời Request

### 2.1. Cấu trúc thư mục `backend/app/`
```
backend/app/
├── main.py                     # App factory, CORS, exception handlers, dual-mount routes (/ & /api/v1)
├── config.py                   # Pydantic BaseSettings, env vars, OAuth client IDs, sheet keys
├── database.py                 # Async engine (asyncpg), AsyncSessionmaker, get_db dependency
├── worker.py                   # Durable background worker, FOR UPDATE SKIP LOCKED job leasing, Outbox dispatcher
├── reset_demo_db.py            # Clean reset script
├── seed.py                     # Demo data seed script
├── api/
│   ├── routes/                 # 25 domain route controllers
│   │   ├── etl.py              # 4-layer ETL pipeline routes (CRUD connections, pipelines, runs, review, post)
│   │   ├── exports.py          # Data export routes (Excel .xlsx, CSV, Google Sheets sync out)
│   │   ├── integrations.py     # Legacy Integration hub & sandbox routes
│   │   ├── inventory.py        # Core inventory routes (items, balances, requests, stocktakes, movements)
│   │   ├── cash_sim.py         # Cash simulation routes (boxes, requests, journals, entries)
│   │   ├── auth.py             # IAM login, profile, tokens
│   │   ├── auth_google.py      # Google Sign-in ID token verification (google-auth)
│   │   ├── auth_utils.py       # JWT creation, capability checks, location/branch scoping
│   │   ├── reconciliations.py  # Discrepancy detection & reconciliation runs
│   │   ├── reports.py          # Financial & operational reporting
│   │   ├── sync_requests.py    # Staged sync requests with maker-checker approval
│   │   └── ...
│   ├── errors.py               # Custom AppError with status codes and structured codes
│   ├── observability.py        # Prometheus counters, OpenTelemetry tracing & dependency records
│   ├── pagination.py           # Keyset cursor pagination (limit default 50, max 100)
│   └── structured_logging.py   # JSON logging format
├── db/
│   ├── base.py                 # SQLAlchemy Base, TimestampMixin, utc_now helper
├── models/
│   ├── __init__.py             # Model registry ensuring full Base.metadata for Alembic
│   ├── inventory.py            # Items, Balances, Movements, Requests, Stocktakes, Locations
│   ├── cash_sim.py             # CashBoxes, CashRequests, CashJournals, CashEntries, Balances
│   ├── etl.py                  # EtlConnection, EtlPipeline, EtlMappingVersion, EtlRun, EtlRunRow
│   ├── integration.py          # IntegrationConnection, IntegrationRun, IntegrationStagingRow
│   ├── activity.py             # AuditEvent (append-only), OutboxEvent, Job, ActivityEvent
│   ├── idempotency.py          # IdempotencyKey durable store
│   ├── reconciliation.py       # ReconciliationRun, ReconciliationException
│   ├── iam.py                  # User, Role, Capability, UserRole, RoleCapability
│   └── sync_request.py         # SyncRequest
└── services/
    ├── etl_engine.py           # Multi-format parsing, fingerprinting, canonicalization, staging, posting
    ├── google_sheets_service.py# Sheet ID parser, v4 API read, Gviz CSV read, Apps Script webhook push
    ├── export_engine.py        # Openpyxl XLSX generation, CSV generation (CWE-1236 safe), serializers
    ├── idempotency.py          # Idempotency middleware & cache
    └── email_service.py        # SMTP / Gmail email dispatch
```

### 2.2. Vòng đời Request & Quy chuẩn Kỹ thuật
- **Dual Routing:** Tất cả các router đều được gắn đồng thời ở gốc `/` và tiền tố `/api/v1/` trong `app/main.py`. Cả hai dạng URL đều hợp lệ.
- **Envelope lỗi chuẩn hóa (`docs/06:44`):** Mọi lỗi HTTP, ngoại lệ xác thực Pydantic (422) và ngoại lệ nội bộ (500) đều được đóng gói theo định dạng nhất quán:
  ```json
  {
    "error": {
      "code": "VALIDATION_ERROR",
      "message": "Thông báo lỗi thân thiện",
      "request_id": "c1f7a8b9...",
      "details": { ... }
    }
  }
  ```
- **Xử lý số học chính xác (`Decimal`):** Toàn bộ số lượng và số tiền đều xử lý qua `Decimal` với hàm `_to_decimal()`, cấm chuyển đổi qua `float` trung gian để triệt tiêu lỗi lệch số làm tròn tài chính.
- **Bảo vệ chống Spreadsheet Formula Injection (CWE-1236):** Toàn bộ dữ liệu xuất ra CSV hoặc Excel đều đi qua bộ lọc `sanitize_cell_value()` / `_csv_safe()`. Bất kỳ chuỗi nào bắt đầu bằng các ký tự công thức (`=`, `+`, `-`, `@`, `\t`, `\r`) mà không phải số thuần túy đều được tự động thêm dấu `'` ở đầu ô.

---

## 3. Khảo Sát Mô Hình Dữ Liệu & Ràng Buộc Miền Nghiệp Vụ

### 3.1. Phân hệ Kho & Quản lý Tồn kho (`app/models/inventory.py`)
| Tên Model | Tên Bảng | Khóa chính / Duy nhất | Ràng buộc nghiệp vụ quan trọng |
|---|---|---|---|
| `Item` | `inv_items` | `id` (UUID) / `sku` (Unique) | Danh mục nguyên vật liệu pha chế trà sữa. Cột: `sku`, `name`, `unit`, `category`, `packaging`, `cost_price` (Numeric 14,2), `selling_price` (Numeric 15,2), `min_stock` (Numeric 12,2), `tracked_serial` (bool), `active` (bool). |
| `Location` | `inv_locations` | `id` (UUID) / `code` (Unique) | Kho hàng hoặc vị trí lưu trữ (`BAR-MAIN`, `STORAGE-COOL`, `STORAGE-DRY`, `KHO-TT`). Có liên kết `branch_id`. |
| `Balance` | `inv_balances` | Composite PK (`location_id`, `item_id`) | Số dư tồn kho thời gian thực. **Ràng buộc:** `quantity >= 0` (`qty_non_negative`). Có `reserved_quantity` và optimistic locking `version`. **Bất biến số 1:** Không bao giờ được phép `UPDATE` trực tiếp cột `quantity` mà không sinh `Movement`! |
| `InventoryRequest` | `inv_requests` | `id` (UUID) | Phiếu yêu cầu kho: `kind` (`receipt`, `issue`, `transfer`, `adjustment`), `status` (`draft`, `submitted`, `approved`, `rejected`, `posted`), `maker_id`, `approver_id`, `source_id`, `dest_id`, `version`. |
| `InventoryRequestLine`| `inv_request_lines` | `id` (UUID) | Chi tiết dòng phiếu: `quantity > 0` (`qty_positive`), `direction IN ('increase', 'decrease')`, `unit_price`, `lot_no`, `expiry_date`. |
| `Movement` | `inv_movements` | `id` (UUID) | Sổ cái biến động kho bất biến (Append-only). Cột: `quantity_signed` (âm hoặc dương), `posted_at`, `sub_kind`, `unit_cost`, `cost_amount`. Ràng buộc duy nhất `(request_id, line_id, location_id)`. |
| `LotMovement` & `LotBalance` | `inv_lot_movements`, `inv_lot_balances` | `id` (UUID) | Quản lý theo số lô và hạn sử dụng (FEFO). |
| `StockLevel` | `inv_stock_levels` | `id` (UUID) | Định mức tồn kho an toàn tại từng kho: `(location_id, item_id)` là Unique. Có `min_qty`, `max_qty`. |

### 3.2. Phân hệ Quỹ & Tiền mặt Mô phỏng (`app/models/cash_sim.py`)
| Tên Model | Tên Bảng | Khóa chính / Duy nhất | Ràng buộc nghiệp vụ quan trọng |
|---|---|---|---|
| `CashBox` | `cash_boxes` | `id` (UUID) / `code` (Unique) | Sổ quỹ tiền mặt (VD: Quỹ quầy pha chế, Quỹ kho trung tâm). |
| `CashRequest` | `cash_requests` | `id` (UUID) | Phiếu thu/chi: `amount > 0` (`amount_positive`), `kind` (`receipt`, `payment`, `adjustment`), `idempotency_key` (Unique). |
| `CashJournal` | `cash_journals` | `id` (UUID) / `request_id` (Unique) | Sổ nhật ký ghi sổ giao dịch quỹ. Có `correlation_id`, `reversal_of`. |
| `CashEntry` | `cash_entries` | `id` (UUID) | Bút toán kép tài chính (Double-entry): `debit >= 0 AND credit >= 0`, `(debit > 0 AND credit = 0) OR (credit > 0 AND debit = 0)`. Tổng nợ bằng tổng có. |
| `CashBalance` | `cash_balances` | `cashbox_id` (PK) | Số dư tiền mặt hiện tại: `amount >= 0` (`amount_non_negative`). |

### 3.3. Phân hệ ETL Pipeline 4 Tầng (`app/models/etl.py`)
| Tên Model | Tên Bảng | Vai trò & Đặc điểm kỹ thuật |
|---|---|---|
| `EtlConnection` | `etl_connections` | Cấu hình nguồn dữ liệu: `type` (`csv`, `json`, `xlsx`, `google_sheets`), `status`, `secret_ref`, `allowlist_sheets` (JSON array các Sheet ID/dải ô được phép), `config_json` (chứa `sheet_id`, `tab`, `service_account_ref`...). |
| `EtlPipeline` | `etl_pipelines` | Định nghĩa đường ống ETL gắn với mục tiêu nghiệp vụ (`target`): `catalog_upsert`, `inventory_receipt`, `inventory_issue`, `inventory_transfer`, `stocktake`, `balance_adjustment_admin`. Gắn với `branch_id`, `location_id`, `destination_location_id`. |
| `EtlMappingVersion` | `etl_mapping_versions` | Phiên bản ánh xạ cột nguồn -> cột đích. `mapping_json`: danh sách `{source_field, target_field, required, transform, default}`. `duplicate_policy`: `reject`, `skip`, `overwrite`. Khóa duy nhất `(pipeline_id, version)`. |
| `EtlRun` | `etl_runs` | Một phiên thực thi ETL cụ thể. Lưu `source_fingerprint` (SHA-256) chống chạy trùng lặp, `status` (`staged`, `reviewing`, `posted`, `rejected`, `failed`), đếm `total_rows`, `valid_rows`, `invalid_rows`. |
| `EtlRunRow` | `etl_run_rows` | Lưu trữ từng dòng ở tầng trung gian (Staging). Chứa `raw_data_json`, `canonical_data_json`, cờ `valid`, `errors_json` (mảng lỗi chi tiết), và `action_preview` (so sánh trước/sau khi post). |

### 3.4. Phân hệ Giám sát, Bất biến & Kiểm toán (`app/models/activity.py`, `idempotency.py`)
- **Append-only Audit Log (`AuditEvent`):** Bảng `audit_events` được bảo vệ bằng SQLAlchemy Event Listeners (`before_update`, `before_delete`). Bất kỳ hành vi sửa hoặc xóa log kiểm toán nào đều kích hoạt `DBAPIError` và bị chặn đứng ở mức engine DB.
- **Transactional Outbox (`OutboxEvent`):** Được thêm vào DB trong cùng một transaction với nghiệp vụ chính, bảo đảm tin cậy 100% khi bắn sự kiện cho background worker xử lý.
- **Bền vững Idempotency (`IdempotencyKey`):** Lưu trữ key, request hash, status code và response body trong bảng PostgreSQL `idempotency_keys` với cơ chế `INSERT ... ON CONFLICT DO NOTHING`, bảo đảm an toàn qua các lần restart server hoặc khi chạy multi-replica.

---

## 4. Đánh Giá Hiện Trạng ETL & Xuất Nhập File

### 4.1. Cơ chế Import hiện có
Trong file `backend/app/api/routes/etl.py` và `backend/app/services/etl_engine.py`:
1. Endpoint `POST /etl/pipelines/{id}/runs`:
   - Chấp nhận tệp đính kèm `multipart/form-data` (CSV, JSON, XLSX).
   - Hoặc JSON payload chứa `raw_rows` hoặc `sheet_url` / `sheet_id` / `tab`.
   - Nếu `connection.type == "google_sheets"`, hệ thống tự động đọc cấu hình `sheet_url`/`sheet_id` và gọi `google_sheets_service.fetch_sheet_rows()`.
2. Kiểm tra tính trùng lặp qua Fingerprint:
   - Dữ liệu thô được tính mã băm SHA-256 chuẩn hóa (`compute_fingerprint`). Nếu tìm thấy một `EtlRun` cùng fingerprint ở trạng thái `staged`, `reviewing` hoặc `posted`, hệ thống trả về ngay phiên chạy đó mà không tạo thêm bản ghi trùng.
3. Sinh bản ghi Staging và Bản xem trước (`action_preview`):
   - Không ghi đè trực tiếp vào bảng chính.
   - Đối với `catalog_upsert`: so sánh SKU xem sẽ tạo mới (`create`) hay cập nhật (`update`).
   - Đối với `balance_adjustment_admin`: tra cứu tồn kho hiện tại, tính toán độ lệch (`delta_quantity`), hướng điều chỉnh (`increase` / `decrease`), kiểm tra tồn âm.
   - Đối với `inventory_receipt` / `inventory_issue`: kiểm tra sự tồn tại của SKU, số lượng dương, số dư hiện có.
4. Cơ chế Phê duyệt 2 người (Maker-Checker):
   - Runner (người kích hoạt ETL) không thể tự phê duyệt phiếu điều chỉnh tồn của chính mình, trừ trường hợp đặc biệt `single_admin_override` được cấp quyền kiểm toán rõ ràng (`etl:post_balance`).
5. Post giao dịch vào sổ cái (`execute_etl_posting`):
   - Mọi biến động số lượng đều tạo `InventoryRequest` và `Movement`. Tuyệt đối không có lệnh `UPDATE inv_balances SET quantity = ...` độc lập.

### 4.2. Cơ chế Export hiện có
Trong file `backend/app/api/routes/exports.py` và `backend/app/services/export_engine.py`:
- Xuất file Excel (`.xlsx`): Sử dụng `openpyxl`, áp dụng theme màu chuẩn nhận diện (Brand Classic Blue `#0F4C81`), tự động tính độ rộng cột, định dạng số thập phân, phân cách hàng nghìn và ngày tháng chuẩn.
- Xuất file CSV: Sử dụng mã hóa UTF-8 với ký tự BOM (`\ufeff`) giúp Microsoft Excel mở file tiếng Việt mà không bao giờ bị lỗi font (mojibake).
- Chống tấn công Formula Injection (CWE-1236): Xử lý toàn diện các ký tự nguy hiểm (`=`, `+`, `-`, `@`, `\t`, `\r`).
- Hỗ trợ các bộ dữ liệu nghiệp vụ: `catalog`, `balances`, `movements`, `cash_journal`, `inventory_summary`.

---

## 5. Thiết Kế Chi Tiết Tích Hợp Google Sheets API Hai Chiều (R3)

### 5.1. Phân Tích Thư Viện & Quản Lý Phụ Thuộc (Dependencies)

#### Khảo sát hiện trạng trong `pyproject.toml` và `poetry.lock`:
- Đã có:
  * `google-auth = "^2.30.0"` (thư viện chính thức của Google để xử lý xác thực, Service Account, OAuth2 credentials).
  * `httpx = "^0.27.0"` (thư viện HTTP client bất đồng bộ Async/Await tiêu chuẩn).
  * `requests = "^2.31.0"` (HTTP client đồng bộ).
  * `openpyxl = "^3.1.5"` (xử lý Excel).
- Chưa có:
  * `gspread` (wrapper đồng bộ của bên thứ ba).
  * `google-api-python-client` (SDK chính thức của Google, nhưng là đồng bộ dạng blocking I/O).

#### Lựa chọn kiến trúc tối ưu:
| Giải pháp | Ưu điểm | Nhược điểm | Đánh giá kiến trúc |
|---|---|---|---|
| **Phương án 1: Dùng `google-auth` + `httpx.AsyncClient` gọi REST API v4** | - **Không cần thêm thư viện bên ngoài mới**.<br>- 100% Native Asynchronous, không block event loop của FastAPI.<br>- Kiểm soát chính xác payload, header, timeout và retry.<br>- Tiết kiệm RAM và kích thước Docker container. | Phải tự xây dựng một vài helper nhỏ để wrap các endpoint của Google Sheets API v4. | **KHUYẾN NGHỊ CAO NHẤT (Kiến trúc sạch & chuẩn async)** |
| **Phương án 2: Thêm `gspread = "^6.1.0"`** | Cú pháp ngắn gọn, dễ dùng cho code scripting đơn giản. | - Là thư viện đồng bộ (synchronous blocking). Khi chạy trong FastAPI async endpoint bắt buộc phải dùng `asyncio.to_thread` hoặc `run_in_threadpool`, tiêu tốn threadpool của server.<br>- Phụ thuộc thêm gói bên thứ ba. | Phương án dự phòng nếu cần thao tác phức tạp về format ô. |
| **Phương án 3: Thêm `google-api-python-client = "^2.130.0"`** | SDK chính hãng Google, đầy đủ tính năng. | Rất nặng nề (~50MB package), blocking I/O, thời gian khởi động chậm. | Không khuyến nghị. |

=> **Kết luận:** Tận dụng tối đa `google-auth` đã có trong dự án kết hợp với `httpx.AsyncClient` để tạo service Google Sheets API v4 bất đồng bộ, hiệu năng cao, không làm tắc nghẽn FastAPI event loop.

---

### 5.2. Kiến Trúc Xác Thực & Quản Lý Thông Số Bí Mật (Credentials Management)

Hệ thống cần hỗ trợ 3 chế độ xác thực linh hoạt:

```
                         ┌──────────────────────────────────────────────┐
                         │   Google Sheets Service Auth Strategy        │
                         └──────────────────────┬───────────────────────┘
                                                │
         ┌──────────────────────────────────────┼──────────────────────────────────────┐
         ▼                                      ▼                                      ▼
┌──────────────────┐                  ┌──────────────────┐                  ┌──────────────────┐
│  Mode 1: SA JSON │                  │   Mode 2: OAuth2 │                  │ Mode 3: API Key  │
│ (Service Account)│                  │  (User Delegated)│                  │  (Public / Read) │
├──────────────────┤                  ├──────────────────┤                  ├──────────────────┤
│• Dành cho hệ thống│                  │• Dành cho cá nhân│                  │• Dành cho sheet  │
│  tự động, batch, │                  │  kết nối Drive   │                  │  công khai       │
│  cron export.    │                  │  của riêng mình. │                  │  (Viewer link).  │
│• Quyền: Đọc/Ghi  │                  │• Quyền: Đọc/Ghi  │                  │• Quyền: Chỉ đọc  │
└──────────────────┘                  └──────────────────┘                  └──────────────────┘
```

#### 1. Service Account JSON (Chế độ tự động hóa cấp doanh nghiệp):
- **Cơ chế:** Google Cloud IAM Service Account có email dạng `quanlykho-sync@project-id.iam.gserviceaccount.com`. Người dùng chỉ cần ấn nút "Chia sẻ" (Share) trên Google Sheet và cấp quyền "Người chỉnh sửa" (Editor) cho email này.
- **Cấu hình & Lưu trữ an toàn:**
  * *Biến môi trường toàn cục:* `GOOGLE_SHEETS_SERVICE_ACCOUNT_JSON` (chuỗi JSON thô hoặc base64).
  * *Hoặc tệp đường dẫn:* `GOOGLE_APPLICATION_CREDENTIALS=/path/to/sa-credentials.json`.
  * *Cấu hình theo từng Connection:* Lưu trong trường `secret_ref` của bảng `etl_connections` (VD: `vault://google/sa-kho-tong` hoặc `env://GOOGLE_SHEETS_SA_JSON`), không lưu khóa riêng tư (private_key) dưới dạng văn bản thuần (plaintext) trong database.
- **Xác thực token:** Sử dụng `google.oauth2.service_account.Credentials.from_service_account_info(...)` với scope:
  - `https://www.googleapis.com/auth/spreadsheets`
  - `https://www.googleapis.com/auth/drive.file`

#### 2. User OAuth 2.0 Credentials (Chế độ ủy quyền cá nhân):
- **Cơ chế:** Tận dụng hạ tầng Google OAuth hiện có (`app/api/routes/auth_google.py`).
- **Mở rộng:** Bổ sung flow xin cấp quyền Google Sheets/Drive scope. Lưu trữ `refresh_token` đã mã hóa trong cấu hình tích hợp của người dùng. Khi hết hạn, server tự động dùng `google.oauth2.credentials.Credentials` để lấy `access_token` mới mà không yêu cầu người dùng đăng nhập lại.

#### 3. API Key & Google Visualization Fallback (Chế độ tiện dụng công khai):
- Dành cho các Google Sheet đã bật tính năng "Bất kỳ ai có đường liên kết đều có thể xem" (Anyone with the link can view). Đọc dữ liệu cực nhanh qua Google Visualization CSV endpoint (`gviz/tq?tqx=out:csv`), hoàn toàn không yêu cầu cấu hình tài khoản phức tạp.

---

### 5.3. Thiết Kế Mẫu Bảng Tính (Sheet Templates) & Ánh Xạ Dữ Liệu (Data Mapping)

Để người dùng dễ sử dụng trên Google Sheets, hệ thống thiết kế các mẫu tab chuẩn hóa với tiêu đề tiếng Việt có dấu (hoặc tiếng Anh không dấu tương đương):

#### Template 1: Danh mục Hàng hóa & Nguyên liệu (`catalog_upsert`)
Tab name: `DanhMuc_SanPham` hoặc `Catalog`
| Tên cột tiếng Việt (Google Sheets) | Trường đích (DB) | Kiểu dữ liệu | Bắt buộc | Quy tắc biến đổi & Kiểm tra |
|---|---|---|---|---|
| Mã SKU | `sku` | String(128) | **Có** | `trim_upper`, Duy nhất, không chứa khoảng trắng lạ |
| Tên hàng hoá / Nguyên liệu | `name` | String(256) | **Có** | `trim`, Tối thiểu 2 ký tự |
| Đơn vị tính | `unit` | String(32) | **Có** | `trim_lower` (vd: gói, kg, hộp, chai, ly) |
| Nhóm / Danh mục | `category` | String(128) | Không | Phân loại: Nhóm Trà, Nhóm Sữa, Topping, Bao bì... |
| Quy cách đóng gói | `packaging` | String(256) | Không | Vd: 500g/gói, Thùng 20 gói |
| Giá vốn (VNĐ) | `cost_price` | Numeric(14,2) | Không | `to_decimal`, >= 0 |
| Giá bán (VNĐ) | `selling_price` | Numeric(15,2) | Không | `to_decimal`, >= 0 |
| Tồn tối thiểu | `min_stock` | Numeric(12,2) | Không | `to_decimal`, >= 0, cảnh báo khi chạm ngưỡng |
| Quản lý Serial/Lô | `tracked_serial` | Boolean | Không | `to_bool` (Có/Không, 1/0, True/False) |
| Đang kinh doanh | `active` | Boolean | Không | `to_bool` (Mặc định: True) |
| *Trạng thái đồng bộ (Hệ thống ghi)* | `_sync_status` | String | Output | Hệ thống phản hồi: `HỢP LỆ`, `ĐÃ CẬP NHẬT`, hoặc `LỖI: ...` |

#### Template 2: Điều chỉnh Tồn kho & Kiểm kê (`balance_adjustment_admin` / `stocktake`)
Tab name: `DieuChinh_TonKho` hoặc `Stock_Adjustment`
| Tên cột tiếng Việt (Google Sheets) | Trường đích (DB) | Kiểu dữ liệu | Bắt buộc | Quy tắc biến đổi & Kiểm tra |
|---|---|---|---|---|
| Mã SKU | `sku` | String(128) | **Có** | Phải tồn tại trong danh mục `inv_items` |
| Mã Kho / Vị trí | `location_code` | String(64) | **Có** | Tra cứu từ `inv_locations.code` (VD: `BAR-MAIN`, `KHO-TT`) |
| Tồn thực tế kiểm đếm | `target_quantity` | Numeric(20,3) | Tùy chọn* | Số lượng tồn sau điều chỉnh (không được âm) |
| Số lượng lệch (+/-) | `delta_quantity` | Numeric(20,3) | Tùy chọn* | (*Phải có 1 trong 2 cột `target_quantity` hoặc `delta_quantity`) |
| Lý do điều chỉnh | `reason` | String(512) | Không | Diễn giải lý do kiểm kê, hao hụt, hư hỏng... |
| Số lô sản xuất | `lot_no` | String(64) | Không | Quản lý theo lô nếu hàng có hạn sử dụng |
| Hạn sử dụng | `expiry_date` | Date | Không | Định dạng `YYYY-MM-DD` hoặc `DD/MM/YYYY` |
| *Ghi chú xử lý (Hệ thống ghi)* | `_action_preview` | String | Output | Hệ thống hiển thị: `Hiện tại: 10 -> Mới: 15 (Tăng +5)` |

#### Template 3: Nhập kho từ Nhà Cung Cấp (`inventory_receipt`)
Tab name: `NhapKho` hoặc `Inbound_Receipt`
| Tên cột tiếng Việt | Trường đích (DB) | Bắt buộc | Ghi chú nghiệp vụ |
|---|---|---|---|
| Mã SKU | `sku` | **Có** | Phải có trong danh mục |
| Kho nhận hàng | `location_code` | **Có** | Vd: `KHO-TT` |
| Số lượng nhập | `quantity` | **Có** | Số dương > 0 |
| Đơn giá nhập | `unit_price` | Không | Đơn giá mua vào thực tế |
| Nhà cung cấp | `supplier` | Không | Tên NCC / Đơn vị giao hàng |
| Số hóa đơn / Chứng từ | `invoice_no` | Không | Số hóa đơn VAT / Phiếu giao hàng |
| Số lô | `lot_no` | Không | Lưu vết theo dõi chất lượng |
| Hạn sử dụng | `expiry_date` | Không | Hạn dùng nguyên liệu |

#### Template 4: Thu Chi Quỹ Tiền Mặt (`cash_transactions`)
Tab name: `ThuChi_TienMat` hoặc `Cash_Transactions`
| Tên cột tiếng Việt | Trường đích (DB) | Bắt buộc | Ghi chú nghiệp vụ |
|---|---|---|---|
| Mã Quỹ tiền mặt | `cashbox_code` | **Có** | Phải tồn tại trong `cash_boxes.code` |
| Loại phiếu | `kind` | **Có** | `receipt` (Thu tiền) hoặc `payment` (Chi tiền) |
| Số tiền (VNĐ) | `amount` | **Có** | `Decimal > 0` |
| Lý do / Diễn giải | `reason` | **Có** | Mục đích chi / thu tiền |
| Mã đối soát ngoài | `idempotency_key` | Không | Mã giao dịch ngân hàng / hóa đơn để chống chi trùng |

---

### 5.4. Quy Trình Đồng Bộ Hai Chiều (Bi-directional Sync Flow)

```
========================================================================================
                          CHIỀU 1: IMPORT (GOOGLE SHEETS -> HỆ THỐNG)
========================================================================================

 [Google Sheet của người dùng]
          │
          │ 1. Kích hoạt đồng bộ (Manual qua Web UI hoặc Cron Worker)
          ▼
 [Google Sheets Service] ─── Trích xuất Sheet ID & Xác thực (SA / OAuth / API Key)
          │
          │ 2. Lấy toàn bộ hàng & tiêu đề (majorDimension: ROWS)
          ▼
 [ETL Engine: Fingerprint] ── Kiểm tra SHA-256 Fingerprint
          │                   ├─ Trùng với Run đã Staged/Posted? ──> Báo trùng, tránh duplicate
          │                   └─ Dữ liệu mới ──> Tiếp tục
          ▼
 [Schema Mapping & Validation] ── Ánh xạ cột, chuẩn hóa kiểu Decimal, kiểm tra FK (SKU, Kho)
          │
          │ 3. Tạo EtlRun & EtlRunRow (Trạng thái: "staged")
          ▼
 [Staging Store (PostgreSQL)] ── Tính toán action_preview (Số dư cũ, Số dư mới, Độ lệch)
          │
          │ 4. Phê duyệt kiểm soát (Maker-Checker Approval hoặc Single-Admin Override)
          ▼
 [ETL Posting Transaction]
          ├── Tạo InventoryRequest (Approved)
          ├── Tạo InventoryRequestLine
          ├── Ghi nhận sổ cái Movement / LotMovement (Append-only)
          ├── Cập nhật số dư inv_balances (Có khóa lạc quan version + kiểm tra non-negative)
          ├── Ghi AuditEvent (Append-only)
          └── Ghi OutboxEvent (Transactional)
          │
          │ 5. Phản hồi kết quả lên Google Sheet (Writeback status)
          ▼
 [Google Sheets API v4] ─── Cập nhật cột `Trạng thái xử lý` ("THÀNH CÔNG" / "LỖI")

========================================================================================
                          CHIỀU 2: EXPORT (HỆ THỐNG -> GOOGLE SHEETS)
========================================================================================

 [Yêu cầu Xuất dữ liệu] (Dataset: Catalog / Balances / Movements / Cash / Summary)
          │
          │ 1. Xác thực quyền (`_verify_export_permission`) & lọc theo Scope kho/chi nhánh
          ▼
 [Database Query] ────── Truy vấn dữ liệu có phân trang / lọc thời gian
          │
          │ 2. Khử Formula Injection (CWE-1236) & Định dạng dữ liệu
          ▼
 [Google Sheets Service]
          │
          ├── Cách A (Direct Update): Ghi đè tab được chỉ định qua API v4
          │   `PUT https://sheets.googleapis.com/v4/spreadsheets/{id}/values/{tab}!A1:Z`
          │   (majorDimension=ROWS, valueInputOption=USER_ENTERED)
          │
          └── Cách B (Create New Sheet): Gọi Drive API v3 tạo Spreadsheet mới
              và cấp quyền Viewer/Editor cho email người dùng.
          │
          │ 3. Lưu log kiểm toán
          ▼
 [AuditEvent] ────────── Ghi nhận `exports.sync_google_sheets.completed`
```

---

### 5.5. Phản Hồi Trạng Thái Đồng Bộ Trực Tiếp Lên Google Sheet (In-Sheet Status Feedback)

Điểm nâng cấp quan trọng của R3 là **phản hồi hai chiều**:
- Khi đọc dữ liệu từ Google Sheets vào Staging, nếu có dòng bị lỗi (VD: SKU không tồn tại, số lượng âm, thiếu cột bắt buộc), hệ thống không chỉ trả lỗi trên giao diện web mà còn sử dụng Sheets API v4 `spreadsheets.values.batchUpdate` để ghi trực tiếp trạng thái vào cột cuối cùng của Google Sheet:
  - Cột `[Trạng Thái Xử Lý]`:
    * Hàng hợp lệ: Ghi `✓ ĐÃ DUYỆT (Run: {run_id[:8]})`
    * Hàng lỗi: Ghi `✗ LỖI: SKU 'TRA-XYZ' không tồn tại trong danh mục`
- Giúp nhân viên kho hoặc quản lý khi nhìn vào Google Sheets biết ngay dòng nào đã được đẩy vào hệ thống, dòng nào bị từ chối mà không cần mở công cụ kỹ thuật.

---

### 5.6. Xử Lý Lỗi, Quản Lý Hạn Ngạch (Rate Limits), Idempotency & Giám Sát

#### 1. Quản lý hạn ngạch Google API (Rate Limits):
- Google Sheets API v4 giới hạn:
  * 300 requests / phút / project.
  * 60 requests / phút / user / project.
- **Giải pháp tối ưu:**
  * Luôn sử dụng `batchGet` và `batchUpdate` thay vì gọi từng ô hay từng dòng riêng lẻ. Một batch call có thể đọc/ghi tới 10,000 dòng.
  * Cài đặt cơ chế Exponential Backoff có jitter khi gặp mã lỗi HTTP 429 (`RATE_LIMITED`):
    $$T_{retry} = 2^{\min(\text{attempt}, 5)} + \text{uniform}(0, 1) \text{ (giây)}$$

#### 2. Tính lũy thừa (Idempotency) & Chống xung đột dữ liệu:
- Sử dụng header `Idempotency-Key` kết hợp bảng `idempotency_keys` của hệ thống.
- Băm nội dung sheet bằng SHA-256 (`compute_fingerprint`). Nếu người dùng ấn nút "Đồng bộ" liên tiếp 2 lần trên cùng một nội dung trang tính, hệ thống phát hiện fingerprint trùng lặp và trả về kết quả phiên chạy trước đó mà không tạo thêm giao dịch thừa.
- Khóa bi quan (Pessimistic locking) với `with_for_update()` trên các bản ghi `inv_balances` trong lúc post giao dịch, bảo đảm hai tiến trình đồng bộ đồng thời không làm sai lệch số dư thực tế.

#### 3. Báo cáo lỗi chi tiết:
- Toàn bộ lỗi của từng dòng được lưu trữ trong trường `errors_json` của bảng `etl_run_rows`.
- Cung cấp endpoint sẵn có `GET /etl/runs/{run_id}/error-report` cho phép tải về báo cáo lỗi dạng CSV hoặc JSON để người dùng đối chiếu.

#### 4. Khả năng quan sát (Observability):
- Tích hợp hàm `record_external_dependency("google_sheets", outcome)` để đo lường tỷ lệ thành công/thất bại và độ trễ trên Prometheus và OpenTelemetry.

---

## 6. Kế Hoạch & Kiến Trúc Module Đề Xuất Cho Đội Ngũ Thực Thi

Để đội ngũ lập trình viên triển khai R3 nhanh chóng và an toàn, kiến trúc code được khuyến nghị triển khai theo cấu trúc module sau:

### 6.1. Cấu hình mới trong `app/config.py`
```python
# Google Sheets & Drive API Settings
google_sheets_service_account_json: str = Field(
    default="",
    description="Chuỗi JSON Service Account hoặc đường dẫn file .json credentials"
)
google_sheets_sync_timeout: int = Field(default=30, ge=5, le=120)
google_sheets_max_rows: int = Field(default=10000)
```

### 6.2. Nâng cấp `app/services/google_sheets_service.py`
Bổ sung các hàm async chuẩn sử dụng `google-auth` + `httpx.AsyncClient`:
1. `get_google_credentials(connection_config: dict | None = None) -> google.auth.credentials.Credentials`:
   - Ưu tiên lấy Service Account từ `connection_config["service_account_json"]` hoặc biến môi trường `settings.google_sheets_service_account_json`.
   - Fallback sang OAuth credentials nếu có `refresh_token`.
2. `get_access_token(credentials) -> str`: Lấy hoặc làm mới access token tự động.
3. `async def fetch_sheet_matrix(sheet_id: str, tab: str = "Sheet1", range_def: str | None = None) -> list[list[Any]]`:
   - Đọc dữ liệu dạng mảng 2 chiều qua endpoint:
     `GET https://sheets.googleapis.com/v4/spreadsheets/{sheet_id}/values/{tab}!A1:Z`
4. `async def write_sheet_matrix(sheet_id: str, tab: str, range_target: str, matrix: list[list[Any]]) -> dict`:
   - Ghi dữ liệu trực tiếp qua endpoint:
     `PUT https://sheets.googleapis.com/v4/spreadsheets/{sheet_id}/values/{tab}!{range_target}?valueInputOption=USER_ENTERED`
5. `async def update_row_statuses(sheet_id: str, tab: str, status_col_letter: str, statuses: list[str]) -> None`:
   - Batch update phản hồi trạng thái xử lý cho từng dòng trên Google Sheet.

### 6.3. Tích hợp chặt chẽ vào `app/api/routes/etl.py`
- Tận dụng triệt để luồng 4 tầng hiện có: người dùng chỉ cần chọn Connection loại `google_sheets` và nhập Sheet URL.
- Hệ thống tự động kéo dữ liệu vào Staging -> Hiển thị xem trước biến động -> Người dùng xác nhận -> Hệ thống post vào sổ cái và tự động ghi ngược trạng thái thành công lên Google Sheet.

---

## 7. Kết Luận Khảo Sát

Hệ thống backend `QuanLyKho` sở hữu nền tảng kiến trúc rất tốt, các quy chuẩn về toàn vẹn dữ liệu, kiểm toán và phân quyền đã được thiết kế bài bản. Toàn bộ hạ tầng cốt lõi cho ETL, Staging, Phê duyệt và Xuất file Excel/CSV đều đã sẵn sàng.

Việc hoàn thiện **Requirement R3 (Bi-directional Google Sheets API)** hoàn toàn khả thi mà **không cần cài thêm thư viện nặng nề nào ngoài `google-auth` và `httpx` đã có sẵn**. Giải pháp trên bảo đảm an toàn dữ liệu 100%, tuân thủ trọn vẹn quy ước kiến trúc của dự án, và mang lại trải nghiệm tiện dụng tối đa cho người dùng cuối.
