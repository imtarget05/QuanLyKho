# Forensic Audit Report (Milestones M1–M5 Victory Audit)

**Work Product**: QuanLyKho Enterprise Upgrade & Real-World Productionization (Milestones M1–M5)  
**Profile**: General Project  
**Integrity Mode**: Development (Ground truth from `ORIGINAL_REQUEST.md`)  
**Auditor**: `auditor_m5_1` (Forensic Integrity Auditor)  
**Verdict**: **CLEAN**

---

## 1. Observation

### 1.1 Source Code Verification of Key Deliverables

1. **`backend/app/services/google_sheets_service.py` (M3 — F8, F9, F10)**:
   - Line 25: `import httpx`
   - Lines 181–224: `_request_with_retry` implements genuine exponential backoff with jitter on HTTP 429 and 503 (`initial_delay * (backoff_factor ** (attempt - 1))) + random.uniform(0.01, 0.05)`).
   - Lines 231–285: `fetch_sheet_values` executes genuine async GET to `https://sheets.googleapis.com/v4/spreadsheets/{clean_id}/values/{quoted_range}` using `httpx.AsyncClient`.
   - Lines 287–350: `write_sheet_values` sanitizes cell values against formula injection via `sanitize_cell_value` before issuing HTTP PUT.
   - Lines 419–501: `fetch_sheet_rows` implements dual-mode ingestion: Sheets API v4 with Service Account / OAuth / API Key, falling back to public Google Visualization CSV export endpoint (`tqx=out:csv`).
   - Lines 535–630: `sync_out_to_google_sheet` handles outbound export with automatic `_sync_status` tracking, CWE-1236 sanitization, and optional Apps Script Webhook forwarding.
   - Zero hardcoded responses or facade classes found.

2. **`backend/app/services/export_engine.py` (M4 — F11, F12)**:
   - Lines 38–48: `sanitize_cell_value(val)` neutralizes formula injection by prefixing `'` on values starting with `=`, `+`, `-`, `@`, `\t`, `\r` unless strictly numeric.
   - Lines 50–138: `generate_xlsx` uses `openpyxl` with custom brand palette (`#0F4C81`), auto-calculated column widths, explicit borders, and header fills.
   - Lines 140–165: `generate_csv` writes UTF-8 BOM `\ufeff` and sanitizes all exported cells.
   - Lines 171–208: `_get_or_register_pdf_font` checks candidate paths for TrueType Unicode fonts (`Roboto-Regular.ttf`, `DejaVuSans.ttf`, `LiberationSans-Regular.ttf`) and registers `RobotoUnicode` with `pdfmetrics`.
   - Lines 210–242: `NumberedCanvas(canvas.Canvas)` implements two-pass page numbering drawing `"Trang X / Y"` in the footer.
   - Lines 243–350: `generate_pdf` compiles dynamic-width ReportLab tables using `SimpleDocTemplate`, `TableStyle`, and HTML-escaped paragraphs.

3. **`backend/app/api/routes/exports.py` (M4 — F11, F13)**:
   - Lines 78–92: Correctly encodes CSV output using `utf-8` on string containing `\ufeff`, guaranteeing exactly one 3-byte BOM sequence (`\xef\xbb\xbf`) and eliminating double-BOM byte duplication (`\xef\xbb\xbf\xef\xbb\xbf`).
   - Lines 118, 138, 173, 215, 276: Enforces regex `pattern="^(xlsx|csv|pdf)$"` across all export endpoints.

4. **`backend/app/api/routes/etl.py` (M3 — F9, F10)**:
   - Lines 721–764: Inbound ETL pipeline automatically reads from Google Sheets connections with allowlist enforcement (`conn.allowlist_sheets`), secret resolution, and staging into `EtlRun`.
   - Lines 965, 1114, 1204: Outbound ETL and manual writeback endpoints call `google_sheets_service.writeback_sheet_status` and `sync_out_to_google_sheet`.

5. **`backend/app/services/email_service.py` & `backend/app/api/routes/admin_users.py` (M1 — F3)**:
   - Lines 135–160 in `email_service.py`: `_send_smtp_sync` runs synchronous SMTP safely wrapped in `asyncio.to_thread` with SSL/STARTTLS support and CRLF injection defenses.
   - Lines 651–664 in `admin_users.py`: Role updates atomically insert `OutboxEvent(event_type="user.roles_updated")`, bump `auth_version`, commit to PostgreSQL, and trigger non-blocking email dispatch.

6. **`frontend/lib/src/core/widgets/admin_promotion_banner.dart` (M1/M2/M5)**:
   - Lines 38–41, 62–63: `Timer? _countdownTimer; bool _hasTriggered = false;` ensures countdown fires only once.
   - Lines 98–114: `_handleRefresh` and `_handleDismiss` check and set `_hasTriggered = true`, immediately cancelling the timer and preventing multi-tap races.
   - Lines 220–231: Compact view wraps action buttons inside a responsive `Wrap(alignment: WrapAlignment.end, spacing: 8, runSpacing: 8, ...)` preventing RenderFlex overflow on 320px screens.

7. **`frontend/lib/src/features/commerce/commerce_workspace.dart` (M1/M2)**:
   - Lines 101–133: `_startBackgroundReloadTimer` sets up periodic 60-second silent state reloads and resumes refresh on lifecycle change (`resumed`) without disturbing active tabs.
   - Lines 145–180: Intercepts 401 session revocation to prompt user refresh dialog non-disruptively.
   - Lines 412–431: Displays `AdminPromotionBanner` when admin promotion is pending, refreshing state upon dismissal or countdown trigger.

8. **Database Invariants**:
   - PostgreSQL engine connected at `postgresql://bankops:bankops@localhost:5432/bankops_test`.
   - `conftest.py` strictly refuses SQLite or unisolated non-`_test` databases in `pytest_sessionstart`.

---

### 1.2 Test Suite Execution Results

1. **Frontend Flutter Tests**:
   - Command: `flutter test test/admin_promotion_banner_test.dart test/admin_promotion_banner_adversarial_test.dart test/admin_promotion_banner_challenger_m3_2_test.dart test/homepage_subsystem_sync_test.dart test/mobile_viewport_audit_test.dart`
   - Output: `00:07 +52: All tests passed!` (52 tests passed, 0 failed).

2. **Backend Pytest Suites (PostgreSQL `bankops_test`)**:
   - `test_exports_multiformat.py`: 27 passed (100%) in 7.16s
   - `test_e2e_exports_multiformat.py`: 16 passed (100%) in 5.78s
   - `test_google_sheets_sync.py`: 13 passed (100%) in 3.51s
   - `test_e2e_gsheets_sync.py`: 12 passed (100%) in 3.16s
   - `test_admin_user_role_notification.py` & `test_admin_role_email_notification.py`: 13 passed (100%) in 24.63s
   - `test_e2e_admin_notification_sync.py`: 12 passed (100%) in 35.54s
   - `test_adversarial_m1_challenger.py` & challenger adversarial suites: 84 passed (100%) in 135.03s
   - **Total Backend Tests Passed**: 177 passed, 0 failed.

---

## 2. Logic Chain

1. **Absence of Facades and Hardcoding**:
   - Direct inspection of all 11 critical files across backend and frontend confirmed 0 dummy returns, 0 mock returns in production files, and 0 `NotImplementedError` stubs.
   - Database operations execute against real PostgreSQL tables with genuine transactional guarantees.
2. **Formula Injection Sanitization (CWE-1236)**:
   - `sanitize_cell_value` in `export_engine.py` and `_csv_safe` in `etl.py` neutralize spreadsheet formula injection across Excel, CSV, and Google Sheets outputs.
3. **CSV Single-BOM Verification**:
   - `export_engine.generate_csv` injects `\ufeff`. `exports.py` encodes this with `utf-8` (rather than `utf-8-sig`). Empirical tests (`test_csv_endpoint_single_bom_byte_sequence`) confirm the output payload starts with exactly `b'\xef\xbb\xbf'` (3 bytes).
4. **ReportLab PDF Generation**:
   - `generate_pdf` loads true Unicode TrueType fonts, creates flowable tables, and uses `NumberedCanvas` for two-pass page numbering.
5. **Mobile Viewport Parity & Banner Guard**:
   - `admin_promotion_banner.dart` contains both challenger requirements: `_hasTriggered` latch guard against multi-tap, and `Wrap` on 320px/compact viewports.
   - All 52 Flutter tests verifying 320px/375px/390px/414px viewports pass with zero RenderFlex overflow.
6. **Pure Async IO**:
   - Network IO in `google_sheets_service.py` is executed via `httpx.AsyncClient` with exponential backoff on 429/503.
   - Synchronous SMTP operations in `email_service.py` and Google Auth token refreshes are offloaded using `asyncio.to_thread`.
7. **Empirical Validation**:
   - All 52 Flutter widget/adversarial tests and all 177 backend pytest tests executed and passed cleanly on the live environment.

---

## 3. Caveats

- No live external Google Sheets or SMTP credentials were used during test runs; instead, network tests properly exercised httpx mocking, backoff simulation, and local SMTP server traps in accordance with isolated testing requirements.
- No caveats found regarding code integrity or compliance.

---

## 4. Conclusion

All deliverables across Milestones M1, M2, M3, M4, and M5 represent authentic, genuine implementations with robust defenses against edge cases, concurrency races, formula injections, and mobile layout constraints.

**Verdict**: **CLEAN**

---

## 5. Verification Method

To independently verify this verdict:

1. **Run Backend Test Suite**:
   ```bash
   cd /Users/mainguyenbinhtan/Downloads/QuanLyKho/backend
   DATABASE_URL="postgresql+psycopg2://bankops:bankops@localhost:5432/bankops_test" poetry run pytest tests/test_exports_multiformat.py tests/test_e2e_exports_multiformat.py tests/test_google_sheets_sync.py tests/test_e2e_gsheets_sync.py tests/test_admin_user_role_notification.py tests/test_admin_role_email_notification.py tests/test_e2e_admin_notification_sync.py tests/test_adversarial_m1_challenger.py tests/test_challenger_m1_2_empirical.py tests/test_challenger_m3_empirical.py tests/test_challenger_m3_2_empirical.py -q
   ```
   *Expected outcome*: 177 passed.

2. **Run Frontend Flutter Test Suite**:
   ```bash
   cd /Users/mainguyenbinhtan/Downloads/QuanLyKho/frontend
   flutter test test/admin_promotion_banner_test.dart test/admin_promotion_banner_adversarial_test.dart test/admin_promotion_banner_challenger_m3_2_test.dart test/homepage_subsystem_sync_test.dart test/mobile_viewport_audit_test.dart
   ```
   *Expected outcome*: 52 passed.

3. **Inspect Critical Files for Verification**:
   - `frontend/lib/src/core/widgets/admin_promotion_banner.dart` (lines 40-41, 62-63, 98-114 for `_hasTriggered`, line 222 for `Wrap`)
   - `backend/app/services/export_engine.py` (lines 38-48 for `sanitize_cell_value`, lines 171-242 for ReportLab font & NumberedCanvas)
   - `backend/app/api/routes/exports.py` (lines 78-92 for single-BOM CSV)
   - `backend/app/services/google_sheets_service.py` (lines 181-224 for retry with backoff, lines 231-350 for pure async httpx)
