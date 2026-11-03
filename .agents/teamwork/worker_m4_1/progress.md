# Progress — Milestone M4 (worker_m4_1)

Last visited: 2026-11-02T15:24:25Z

## Completed Work
1. **F11 - Fix Double-BOM Defect in CSV Export**:
   - Replaced `encoded = csv_content.encode("utf-8-sig")` with `encoded = csv_content.encode("utf-8")` in `backend/app/api/routes/exports.py:82`.
   - Verified that `generate_csv` writes `\ufeff` and encoding as `utf-8` outputs exactly ONE UTF-8 BOM (`b'\xef\xbb\xbf'`), eliminating the duplicated BOM bytes (`b'\xef\xbb\xbf\xef\xbb\xbf'`).
   - Verified that CWE-1236 formula injection neutralization (`sanitize_cell_value()`) remains 100% active.

2. **F12 - Server-Side PDF Export Engine**:
   - Added `reportlab = "^5.1.0"` to `backend/pyproject.toml`.
   - Implemented `generate_pdf(rows, headers, title, metadata)` in `backend/app/services/export_engine.py` using ReportLab Platypus.
   - Registered Unicode TrueType font `Roboto-Regular.ttf` dynamically from candidate paths (`frontend/assets/fonts/Roboto-Regular.ttf`, backend assets, and system Unicode fonts).
   - Structured landscape A4 PDF table with:
     * Header row with brand color `#0F4C81` and white text.
     * Zebra striping alternating `#FFFFFF` and `#F9FAFB`.
     * Grid borders (`0.5pt`, `#E5E7EB`).
     * Cell alignment: numbers/currency right-aligned with commas, status/dates center-aligned, text left-aligned.
     * Automatic column width weighting by max header/value lengths.
     * Repeating table headers across page breaks (`repeatRows=1`).
     * `NumberedCanvas` two-pass page numbering ("Trang X / Y") and branding footer.
     * Empty dataset handling ("Không có dữ liệu trong kỳ báo cáo").
     * HTML escaping for XML characters in cells.

3. **F13 - Multi-Format Export Endpoints**:
   - Updated `backend/app/api/routes/exports.py` query parameter validation to `pattern="^(xlsx|csv|pdf)$"` across all 5 endpoints:
     * `GET /exports/catalog`
     * `GET /exports/balances`
     * `GET /exports/movements`
     * `GET /exports/cash-journal`
     * `GET /exports/inventory-summary`
   - Added PDF dispatch branch in `_format_response`:
     * Media type: `application/pdf`
     * Headers: `Content-Disposition: attachment; filename="{base_name}.pdf"; filename*=UTF-8''...`
   - Fixed `get_accessible_location_ids(db, user)` call signatures in `export_balances` and `export_movements`.
   - Fixed openpyxl timezone-aware datetime issue by removing `tzinfo` before assigning to cells in `generate_xlsx`.

4. **Verification & Testing**:
   - Wrote comprehensive unit and integration tests in `backend/tests/test_exports_multiformat.py` (27 tests).
   - Ran full test suite:
     `pytest tests/test_exports_multiformat.py tests/test_export_sync.py -v` -> **31 passed, 0 failed in 12.21s**.
   - Ran `ruff check`: **All checks passed!**
