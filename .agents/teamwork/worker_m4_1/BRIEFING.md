# BRIEFING — 2026-11-02T15:24:00Z

## Mission
Implement Milestone M4 (Multi-Format Data Export Service: F11, F12, F13) in QuanLyKho: Single-BOM CSV, Server-Side PDF Export with Unicode support, and Multi-Format Endpoints.

## 🔒 My Identity
- Archetype: worker
- Roles: implementer, qa
- Working directory: /Users/mainguyenbinhtan/Downloads/QuanLyKho/.agents/teamwork/worker_m4_1
- Original parent: fbdb9d15-e07c-4143-974c-2efe416095ff
- Milestone: M4 (Multi-Format Data Export Service: F11, F12, F13)

## 🔒 Key Constraints
- Fix double-BOM in CSV export (backend/app/services/export_engine.py and backend/app/api/routes/exports.py) so CSV has exactly one UTF-8 BOM.
- Preserve CWE-1236 formula injection neutralization via sanitize_cell_value().
- Implement generate_pdf in export_engine.py using reportlab (or pure-Python fpdf2) with Unicode TrueType font (Vietnamese support).
- Ensure no requirement for heavy C libraries (runs cleanly in python:3.11-slim).
- Update export routes to support format=pdf across catalog, balances, movements, cash-journal, inventory-summary.
- Genuine implementation only, no hardcoded test values, no facades.
- All tests passing in pytest tests/test_exports_multiformat.py and tests/test_export_sync.py.

## Current Parent
- Conversation ID: fbdb9d15-e07c-4143-974c-2efe416095ff
- Updated: not yet

## Task Summary
- **What to build**: Multi-format data export service (single-BOM CSV, Excel, server-side PDF with Unicode Vietnamese support) and endpoints
- **Success criteria**: All exports working cleanly, single BOM for CSV, valid PDF generation with Vietnamese characters, comprehensive unit/integration tests passing
- **Interface contracts**: PROJECT.md Milestone M4, backend/app/api/routes/exports.py, backend/app/services/export_engine.py
- **Code layout**: QuanLyKho/backend/

## Key Decisions Made
- Added `reportlab = "^5.1.0"` to `backend/pyproject.toml` (pure wheels, 0 extra C packages required on python:3.11-slim).
- Solved Double-BOM defect by having `export_engine.generate_csv` prepend `\ufeff` and having `exports._format_response` encode with standard `"utf-8"` (instead of `"utf-8-sig"`), producing exactly ONE clean BOM `b'\xef\xbb\xbf'`.
- Built server-side PDF engine with ReportLab Platypus (`SimpleDocTemplate`, `Table`, `Paragraph`), landscape A4 format, auto column width weighting, `repeatRows=1` for repeating headers across pages, zebra striping, currency/quantity alignments, and `NumberedCanvas` two-pass page numbering ("Trang X / Y").
- Registered Unicode TrueType font `Roboto-Regular.ttf` dynamically from candidate paths (`frontend/assets/fonts/Roboto-Regular.ttf`, backend assets, and system Unicode fonts) to render all Vietnamese diacritics without mojibake.
- Handled timezone-naive conversion in `export_engine.generate_xlsx` to ensure openpyxl does not throw TypeError on TIMESTAMPTZ database fields.
- Fixed `get_accessible_location_ids(db, user)` argument mismatch in `exports.py`.
- Updated route query parameters across all 5 endpoints to `pattern="^(xlsx|csv|pdf)$"`.

## Artifact Index
- /Users/mainguyenbinhtan/Downloads/QuanLyKho/.agents/teamwork/worker_m4_1/DISPATCH.md — assignment record
- /Users/mainguyenbinhtan/Downloads/QuanLyKho/.agents/teamwork/worker_m4_1/BRIEFING.md — working memory
- /Users/mainguyenbinhtan/Downloads/QuanLyKho/.agents/teamwork/worker_m4_1/progress.md — liveness heartbeat
- /Users/mainguyenbinhtan/Downloads/QuanLyKho/.agents/teamwork/worker_m4_1/handoff.md — 5-component handoff report

## Change Tracker
- **Files modified**:
  * `backend/pyproject.toml`: Added `reportlab = "^5.1.0"`
  * `backend/app/services/export_engine.py`: Added `generate_pdf`, font registration, `NumberedCanvas`, timezone handling in Excel, and `include_bom` option in `generate_csv`
  * `backend/app/api/routes/exports.py`: Fixed CSV double-BOM encoding, added PDF response dispatching, updated query validation regex to `^(xlsx|csv|pdf)$`, and fixed `get_accessible_location_ids` signature calls
  * `backend/tests/test_exports_multiformat.py`: Comprehensive test suite (31 tests covering CSV single BOM, CWE-1236, PDF generation, table styling, pagination, Unicode accents, and endpoints)
- **Build status**: PASS (Ruff: All checks passed, Pytest: 31 passed, 0 failed)
- **Pending issues**: None

## Quality Status
- **Build/test result**: PASS (31 passed, 0 failed in 12.21s)
- **Lint status**: PASS (0 violations)
- **Tests added/modified**: 27 new tests in `test_exports_multiformat.py` + 4 existing in `test_export_sync.py`

## Loaded Skills
None
