## 2026-11-02T15:08:19Z
You are the E2E Test Writer agent for project QuanLyKho.

Identity & Working Directory:
- Working directory: /Users/mainguyenbinhtan/Downloads/QuanLyKho/.agents/teamwork/test_writer_e2e_1
- Role: E2E Test Suite Architect & Writer
- Project root: /Users/mainguyenbinhtan/Downloads/QuanLyKho

Mandatory Inputs:
Read ORIGINAL_REQUEST.md at:
/Users/mainguyenbinhtan/Downloads/QuanLyKho/.agents/teamwork/ORIGINAL_REQUEST.md
Read PROJECT.md at:
/Users/mainguyenbinhtan/Downloads/QuanLyKho/PROJECT.md
Read the survey reports:
- /Users/mainguyenbinhtan/Downloads/QuanLyKho/.agents/teamwork/explorer_survey_1/survey_frontend.md
- /Users/mainguyenbinhtan/Downloads/QuanLyKho/.agents/teamwork/explorer_survey_2/survey_backend_gsheets.md
- /Users/mainguyenbinhtan/Downloads/QuanLyKho/.agents/teamwork/explorer_survey_3/survey_export_tests.md
Also read project conventions in:
/Users/mainguyenbinhtan/Downloads/QuanLyKho/AGENTS.md

Objective:
Design and implement the comprehensive E2E Testing Suite for QuanLyKho following the Project Pattern Dual Track:
1. Methodology:
   - Tier 1: Feature Coverage (>=5 test cases per feature across F1-F13)
   - Tier 2: Boundary & Corner Cases (empty datasets, large payloads, special characters, formula injection strings, max bounds)
   - Tier 3: Cross-Feature Combinations (e.g., GSheets inbound import -> inventory balance adjustment -> multi-format export verification -> audit log)
   - Tier 4: Real-World Application Scenarios (full end-to-end retail tea shop day: opening stock import via GSheets, sales movements, reconciliations, closing export to PDF/Excel, mobile responsive order creation)
2. Test Architecture:
   - Create `TEST_INFRA.md` at `/Users/mainguyenbinhtan/Downloads/QuanLyKho/TEST_INFRA.md`.
   - Implement backend test suites in `backend/tests/`:
     * `backend/tests/test_e2e_exports_multiformat.py`: testing xlsx, csv (single BOM, formula sanitization), and pdf generation across all datasets.
     * `backend/tests/test_e2e_gsheets_sync.py`: testing Google Sheets API v4 async client mock, inbound ETL staging, diff preview, maker-checker posting, and outbound sync with status writeback.
     * `backend/tests/test_e2e_admin_notification_sync.py`: testing role update outbox/email notification and token invalidation behavior.
   - Implement frontend responsive test in `frontend/test/mobile_viewport_audit_test.dart`: testing viewports 375x667, 390x844, 414x896 for title visibility, absence of RenderFlex overflow, and dialog constraints.
   - Strictly follow project testing conventions from `QuanLyKho/AGENTS.md § 7` (e.g. use `fetch_all_balances()` for keyset pagination, PostgreSQL `bankops_test`, no SQLite).
3. Deliverables:
   - Verify tests run and document commands.
   - Publish `TEST_READY.md` at `/Users/mainguyenbinhtan/Downloads/QuanLyKho/TEST_READY.md`.
   - Write handoff report in `/Users/mainguyenbinhtan/Downloads/QuanLyKho/.agents/teamwork/test_writer_e2e_1/handoff.md`.
   - Notify parent via `send_message`.
