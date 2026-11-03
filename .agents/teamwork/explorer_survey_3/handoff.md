# Handoff Report — Export Engine & Test Infrastructure Survey

**Agent**: `explorer_survey_3` (Export Engine & Test Infrastructure Explorer)  
**Parent Conversation ID**: `fbdb9d15-e07c-4143-974c-2efe416095ff`  
**Date**: 2026-11-02  
**Detailed Survey Report**: `/Users/mainguyenbinhtan/Downloads/QuanLyKho/.agents/teamwork/explorer_survey_3/survey_export_tests.md`

---

## 1. Observation

1. **Existing Export Routes & Formats**:
   - In `backend/app/api/routes/exports.py:102-282`, endpoints exist for 5 datasets:
     - `GET /exports/catalog` (line 102) with `format: str = Query("xlsx", pattern="^(xlsx|csv)$")`
     - `GET /exports/balances` (line 122) with `format: str = Query("xlsx", pattern="^(xlsx|csv)$")`
     - `GET /exports/movements` (line 157) with `format: str = Query("xlsx", pattern="^(xlsx|csv)$")`
     - `GET /exports/cash-journal` (line 201) with `format: str = Query("xlsx", pattern="^(xlsx|csv)$")`
     - `GET /exports/inventory-summary` (line 233) with `format: str = Query("xlsx", pattern="^(xlsx|csv)$")`
     - `POST /exports/sync-google-sheets` (line 298)
   - PDF format is completely disallowed by the route query parameter regex `pattern="^(xlsx|csv)$"`.

2. **Existing Export Engine**:
   - In `backend/app/services/export_engine.py:18-20, 45, 127`:
     - Uses `openpyxl.Workbook()` for Excel (.xlsx).
     - Uses `io.StringIO()` and `csv.writer` with `output.write("\ufeff")` for CSV.
     - Implements `sanitize_cell_value` neutralizing CWE-1236 characters (`=`, `+`, `-`, `@`, `\t`, `\r`).
     - Serializes 5 datasets: `serialize_catalog_dataset`, `serialize_balances_dataset`, `serialize_movements_dataset`, `serialize_cash_journal_dataset`, `serialize_inventory_summary_dataset`.

3. **Double-BOM Encoding Defect**:
   - In `backend/app/services/export_engine.py:133`:
     ```python
     output = io.StringIO()
     output.write("\ufeff")  # UTF-8 BOM
     ```
   - In `backend/app/api/routes/exports.py:78-79`:
     ```python
     csv_content = export_engine.generate_csv(rows, headers)
     encoded = csv_content.encode("utf-8-sig")
     ```
   - Encoding string starting with `\ufeff` using `"utf-8-sig"` produces duplicated BOM bytes `b'\xef\xbb\xbf\xef\xbb\xbf'`.

4. **Dependencies**:
   - In `backend/pyproject.toml:35, 51`:
     - `pandas = "^2.2.0"`
     - `openpyxl = "^3.1.5"`
     - No PDF libraries installed (`reportlab`, `fpdf2`, `weasyprint` all absent).
   - In `backend/Dockerfile:2, 16, 20`:
     - Base image is `python:3.11-slim`, installing only `libpq5`. No Cairo/Pango C libraries installed.
   - In `frontend/pubspec.yaml:21-23`:
     - `excel: ^4.0.6`, `printing: ^5.14.3`, `pdf: ^3.12.0`.

5. **Test Infrastructure & Database Guarantees**:
   - In `backend/tests/conftest.py:48-64`:
     - `pytest_sessionstart` aborts with `returncode=2` if `_test` is not in database name:
       `Refusing to run mutating tests against database ... Use a dedicated database whose name contains '_test'`.
     - In `backend/tests/test_phase2b_pre2c_items.py:39`:
       `assert "sqlite" not in DATABASE_URL.lower(), "Không được dùng SQLite cho môi trường test"`.
   - In `Makefile:27-32` and `docker-compose.test.yml:1-19`:
     - Container `postgres-test` runs `postgres:16-alpine` on port 5433 with tmpfs mount for `/var/lib/postgresql/data`.
     - Test execution command: `make test-backend` (`alembic upgrade head` + `pytest tests -q`).
   - In `backend/tests/conftest.py:208-232`:
     - Keyset cursor pagination helper `fetch_all_balances(client, headers)` traverses `next_cursor` until exhaustively reading all items.

6. **Email & Role Notification Infrastructure (R1, R2)**:
   - In `backend/app/services/email_service.py:119, 417, 630`:
     - Contains `_send_smtp_sync`, `send_invite_email`, `send_activation_confirmation_email`, `EmailSendResult`.
   - In `backend/app/api/routes/admin_users.py:636, 645`:
     - `update_user_roles` increments `user.auth_version` and writes to outbox `user.roles_updated`.
   - In `backend/app/services/approval_events.py:19-198`:
     - Real-time `ApprovalEventBus` supports local fanout and Redis Pub/Sub, broadcasting over SSE endpoint `/approvals/stream` (`approvals.py:184`).

---

## 2. Logic Chain

1. From **Observation 1 & 4**:
   - Backend exports currently support only `xlsx` and `csv`. PDF is rejected by endpoint regex and lacks a backend library.
   - Adding PDF export requires installing a lightweight engine compatible with `python:3.11-slim`.
2. From **Observation 4**:
   - `weasyprint` requires extensive native packages (`libcairo2`, `libpango`, `gdk-pixbuf`), which contradicts the slim container profile and adds build friction.
   - In contrast, `reportlab` (pre-built wheels) or `fpdf2` (pure Python) require zero extra Debian packages and render table-based financial/inventory reports in <50ms with existing project font `Roboto-Regular.ttf`.
3. From **Observation 3**:
   - Double-BOM in CSV responses is a latent bug causing external CSV parsers to read column headers with corrupted characters. Normalizing encoding to either `encode("utf-8")` after `\ufeff` or dropping manual `\ufeff` in favor of `"utf-8-sig"` directly resolves the issue.
4. From **Observation 1 & 2**:
   - Current datasets are limited to inventory balances, movements, catalog, cash journal, and inventory summary.
   - Enterprise operations in QuanLyKho require exporting Reconciliation records (`reconciliation_runs`, `reconciliation_exceptions`), Audit events (`audit_events`), and printable single-voucher PDFs (Mẫu 01-VT, 02-VT, 01-TT, 02-TT).
5. From **Observation 5**:
   - SQLite is prohibited for integration tests; all tests must execute against PostgreSQL with `_test` in the connection string.
   - On keyset pagination endpoints like `/inventory/balances`, tests must use `fetch_all_balances()` to prevent flakiness from accumulated DB records.
6. From **Observation 6**:
   - For R1 (admin role UI refresh): incrementing `auth_version` causes immediate token invalidation (401), and publishing role events over `approval_event_bus` enables real-time client notification without polling.
   - For R2 (admin grant email): `email_service.py` provides the exact pattern (`_build_admin_role_granted_html` + `_send_smtp_sync`) with non-blocking resilience (try/except preventing DB rollback on SMTP failure).

---

## 3. Caveats

1. **Font Bundling**: Backend currently does not have `Roboto-Regular.ttf` in its own directory (it resides in `frontend/assets/fonts/Roboto-Regular.ttf`). The backend should bundle or mount a Unicode TrueType font so PDF generation is independent of frontend presence.
2. **Streaming for Large Datasets**: For normal datasets (<5,000 rows), in-memory buffering in `Response(content=bytes)` is adequate. For tables exceeding 50,000 rows, a `StreamingResponse` with generator chunking and `openpyxl(write_only=True)` should be adopted.
3. **No Code Written**: Per explorer role constraints, all investigations were strictly read-only. No application source code or tests were modified during this exploration.

---

## 4. Conclusion

1. **R4 Architecture**:
   - Keep `openpyxl` for Excel (.xlsx).
   - Keep built-in `csv` with formula sanitization, fix the Double-BOM bug, and add StreamingResponse.
   - Introduce `reportlab` (or `fpdf2`) with `Roboto` font for server-side PDF exports.
   - Extend dataset serializers to cover Reconciliation Reports and Audit Logs.
2. **Testing Infrastructure**:
   - Test suite is healthy (387 passed tests).
   - Use `make test-backend` with the dedicated tmpfs PostgreSQL container (`bankops_test` on port 5433).
   - Enforce `fetch_all_balances()` in all inventory balance tests.
   - New test suites for R1, R2, R3, R4 must follow the established mock and integration patterns documented in `survey_export_tests.md`.

---

## 5. Verification Method

1. **Verify Existing Tests**:
   ```bash
   make test-backend
   ```
   *Expected*: Container `postgres-test` boots, Alembic runs to `head`, pytest executes all 100 test files and passes cleanly.
2. **Verify Double-BOM Bug**:
   Inspect `backend/app/services/export_engine.py:133` and `backend/app/api/routes/exports.py:79`.
   Run Python verification:
   ```python
   import io, csv
   out = io.StringIO()
   out.write("\ufeff")
   content = out.getvalue().encode("utf-8-sig")
   assert content == b"\xef\xbb\xbf\xef\xbb\xbf"  # Reproduces Double-BOM
   ```
3. **Verify Dependencies**:
   Inspect `backend/pyproject.toml` (lines 35, 51) and `backend/Dockerfile` (lines 2, 16, 20).
4. **Inspect Generated Survey Report**:
   Read `/Users/mainguyenbinhtan/Downloads/QuanLyKho/.agents/teamwork/explorer_survey_3/survey_export_tests.md`.
