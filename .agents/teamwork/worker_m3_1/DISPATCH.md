## 2026-11-02T15:08:58Z

You are a Worker agent for Milestone M3 (Bi-Directional Google Sheets API Service: F8, F9, F10) in project QuanLyKho.

Identity & Working Directory:
- Working directory: /Users/mainguyenbinhtan/Downloads/QuanLyKho/.agents/teamwork/worker_m3_1
- Role: Google Sheets Integration Worker
- Project root: /Users/mainguyenbinhtan/Downloads/QuanLyKho

Mandatory Input:
Read ORIGINAL_REQUEST.md at:
/Users/mainguyenbinhtan/Downloads/QuanLyKho/.agents/teamwork/ORIGINAL_REQUEST.md
Read PROJECT.md at:
/Users/mainguyenbinhtan/Downloads/QuanLyKho/PROJECT.md
Read Explorer 2's survey report at:
/Users/mainguyenbinhtan/Downloads/QuanLyKho/.agents/teamwork/explorer_survey_2/survey_backend_gsheets.md
and handoff report at:
/Users/mainguyenbinhtan/Downloads/QuanLyKho/.agents/teamwork/explorer_survey_2/handoff.md
Also read project conventions in:
/Users/mainguyenbinhtan/Downloads/QuanLyKho/AGENTS.md

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

Write Ownership (Exclusive to this Worker):
- backend/app/services/google_sheets_service.py
- backend/app/api/routes/etl.py
- backend/tests/test_google_sheets_sync.py

Objective:
Implement Milestone M3 according to the specifications in PROJECT.md and Explorer 2's blueprint:
1. Feature F8 - Pure Async Google Sheets API v4 Client:
   - In `backend/app/services/google_sheets_service.py`, build an async Google Sheets v4 client using existing `google-auth` (`google.oauth2.service_account.Credentials` and `google.oauth2.credentials.Credentials`) + `httpx.AsyncClient`. Zero heavy/blocking dependencies (`gspread` / `google-api-python-client` are NOT needed).
   - Support both Service Account JSON (parsed from dict or JSON string) and OAuth 2.0 Bearer tokens.
   - Implement methods:
     * `async def fetch_sheet_values(sheet_id: str, range_name: str, credentials_info: dict | None, api_key: str | None) -> list[list[Any]]`
     * `async def write_sheet_values(sheet_id: str, range_name: str, values: list[list[Any]], credentials_info: dict, value_input_option: str = "USER_ENTERED") -> dict`
     * `async def batch_update_sheet_values(...)`
   - Handle rate limiting (HTTP 429 / 503) with exponential backoff and jitter.
2. Feature F9 - Inbound Google Sheets Staging & 4-Layer ETL Integration:
   - In `backend/app/api/routes/etl.py` (around line 690) and `google_sheets_service.py`:
     * When `conn.type == "google_sheets"`, retrieve sheet credentials from `conn.config` (e.g. service account JSON or OAuth token).
     * Fetch sheet rows asynchronously and pass into `etl_engine.generate_staging_run()`.
     * Compute SHA-256 row fingerprints for deduplication.
     * Enforce maker-checker: staging rows remain in pending review state, presenting `action_preview` (insert / update / delta) before post.
     * Ensure inventory ledger invariant: all inventory adjustments post strictly via `InventoryRequest` and `Movement`, NEVER direct `inv_balances` updates.
3. Feature F10 - Outbound Google Sheets Sync & Status Writeback:
   - Implement exporting application datasets (Catalog, Balances, Movements, Cash Journal) to a designated Google Sheet spreadsheet and tab.
   - Implement writeback of `_sync_status` (e.g., `"SYNCED_2026-11-02 15:00:00"`) into an extra column on the sheet so users see real-time confirmation on their spreadsheet.
   - Enforce formula sanitization (CWE-1236) neutralizing leading characters (`=`, `+`, `-`, `@`, `\t`, `\r`).
4. Verification & Testing:
   - Write comprehensive tests in `backend/tests/test_google_sheets_sync.py`:
     * Mock Google Sheets API v4 endpoints (values.get, values.update) using `httpx.MockTransport` or `respx`/mocking.
     * Test Service Account credentials authorization header generation.
     * Test inbound sheet parsing, staging into `EtlRunRow`, and diff generation.
     * Test outbound dataset export and `_sync_status` column writeback.
     * Test exponential backoff on HTTP 429.
   - Run tests:
     `cd /Users/mainguyenbinhtan/Downloads/QuanLyKho/backend && pytest tests/test_google_sheets_sync.py tests/test_etl_pipeline.py -v`
   - Ensure all tests pass.

Output Requirements:
- Write handoff report in:
  /Users/mainguyenbinhtan/Downloads/QuanLyKho/.agents/teamwork/worker_m3_1/handoff.md
- Include: Observation, Logic Chain, Changes Made, Test Commands & Results, Verification.
- Notify parent upon completion via send_message.
