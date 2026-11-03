## 2026-11-02T15:08:35Z
You are a Worker agent for Milestone M4 (Multi-Format Data Export Service: F11, F12, F13) in project QuanLyKho.

Identity & Working Directory:
- Working directory: /Users/mainguyenbinhtan/Downloads/QuanLyKho/.agents/teamwork/worker_m4_1
- Role: Export Engine & Multi-Format Service Worker
- Project root: /Users/mainguyenbinhtan/Downloads/QuanLyKho

Mandatory Input:
Read ORIGINAL_REQUEST.md at:
/Users/mainguyenbinhtan/Downloads/QuanLyKho/.agents/teamwork/ORIGINAL_REQUEST.md
Read PROJECT.md at:
/Users/mainguyenbinhtan/Downloads/QuanLyKho/PROJECT.md
Read Explorer 3's survey report at:
/Users/mainguyenbinhtan/Downloads/QuanLyKho/.agents/teamwork/explorer_survey_3/survey_export_tests.md
and handoff report at:
/Users/mainguyenbinhtan/Downloads/QuanLyKho/.agents/teamwork/explorer_survey_3/handoff.md
Also read project conventions in:
/Users/mainguyenbinhtan/Downloads/QuanLyKho/AGENTS.md

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

Write Ownership (Exclusive to this Worker):
- backend/app/services/export_engine.py
- backend/app/api/routes/exports.py
- backend/tests/test_exports_multiformat.py
- backend/pyproject.toml (if updating dependencies for PDF export)

Objective:
Implement Milestone M4 according to the specifications in PROJECT.md:
1. Feature F11 - Fix Double-BOM Defect in CSV Export:
   - In `backend/app/services/export_engine.py:133` and `backend/app/api/routes/exports.py:78-79`, eliminate the duplicated BOM bytes (`b'\xef\xbb\xbf\xef\xbb\xbf'`). Ensure CSV responses have exactly ONE clean UTF-8 BOM (`b'\xef\xbb\xbf'`) so external spreadsheet software (Excel) opens Vietnamese characters cleanly without corrupted first column headers.
   - Maintain formula injection neutralization (CWE-1236) via `sanitize_cell_value()`.
2. Feature F12 - Server-Side PDF Export Engine:
   - Implement `generate_pdf(rows, headers, title, metadata)` in `backend/app/services/export_engine.py` using `reportlab` (or pure-Python `fpdf2`). Ensure it runs in `python:3.11-slim` without requiring system C libraries (like Cairo/Pango).
   - Bundle/register a Unicode TrueType font (e.g. `Roboto-Regular.ttf` from `frontend/assets/fonts/Roboto-Regular.ttf` or system Unicode font) so Vietnamese accents (e.g., "Trà Sữa Sài Gòn", "Số lượng", "Đơn giá") render cleanly without mojibake.
   - Structure professional PDF tables with column headers, zebra striping, currency/quantity alignments, and page numbers.
3. Feature F13 - Multi-Format Export Endpoints:
   - Update `backend/app/api/routes/exports.py` route definitions: change query validation from `pattern="^(xlsx|csv)$"` to `pattern="^(xlsx|csv|pdf)$"`.
   - Implement PDF handling in the response dispatcher:
     * Media type: `application/pdf`
     * Headers: `{"Content-Disposition": f'attachment; filename="{dataset}_{timestamp}.pdf"'}`
     * Datasets supported: `catalog`, `balances`, `movements`, `cash-journal`, `inventory-summary`.
4. Verification & Testing:
   - Write comprehensive unit and integration tests in `backend/tests/test_exports_multiformat.py` covering:
     * CSV output format, single BOM verification, CWE-1236 neutralization.
     * Excel (.xlsx) output validity, headers, row count, openpyxl parseability.
     * PDF (.pdf) output validity, PDF magic header `%PDF`, non-empty byte stream, table layout.
   - Run the test suite:
     `cd /Users/mainguyenbinhtan/Downloads/QuanLyKho/backend && pytest tests/test_exports_multiformat.py tests/test_export_sync.py -v`
   - Document all test execution commands and results in your handoff report.

Output Requirements:
- Write your handoff report to:
  /Users/mainguyenbinhtan/Downloads/QuanLyKho/.agents/teamwork/worker_m4_1/handoff.md
- Include: Observation, Logic Chain, Changes Made, Test Commands & Results, Verification.
- Notify parent upon completion via send_message.
