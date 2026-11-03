# BRIEFING — 2026-11-02T15:30:00Z

## Mission
Implement Milestone M3 (Bi-Directional Google Sheets API Service: F8, F9, F10) in project QuanLyKho, covering async Google Sheets API v4 client, inbound staging & 4-layer ETL integration with maker-checker & inventory ledger invariant, and outbound dataset export with status writeback and formula sanitization.

## 🔒 My Identity
- Archetype: worker
- Roles: implementer, qa
- Working directory: /Users/mainguyenbinhtan/Downloads/QuanLyKho/.agents/teamwork/worker_m3_1
- Original parent: fbdb9d15-e07c-4143-974c-2efe416095ff
- Milestone: M3 (Bi-Directional Google Sheets API Service)

## 🔒 Key Constraints
- Write Ownership strictly limited to:
  * backend/app/services/google_sheets_service.py
  * backend/app/api/routes/etl.py
  * backend/tests/test_google_sheets_sync.py
- Zero heavy/blocking dependencies (`gspread` / `google-api-python-client` are NOT needed; use existing `google-auth` + `httpx.AsyncClient`).
- Support Service Account JSON (dict or JSON string) and OAuth 2.0 Bearer tokens.
- Handle rate limiting (HTTP 429 / 503) with exponential backoff and jitter.
- Inbound staging must compute SHA-256 row fingerprints for deduplication, enforce maker-checker (pending review state, action_preview before post), and respect inventory ledger invariant (post strictly via InventoryRequest & Movement, never direct inv_balances update).
- Outbound sync must export datasets (Catalog, Balances, Movements, Cash Journal), write back `_sync_status`, and enforce formula sanitization (CWE-1236).
- All tests must pass genuine execution (`pytest tests/test_google_sheets_sync.py tests/test_etl_pipeline.py -v`). No shortcuts or hardcoded facades.

## Current Parent
- Conversation ID: fbdb9d15-e07c-4143-974c-2efe416095ff
- Updated: 2026-11-02T15:08:58Z

## Task Summary
- **What to build**: Pure async Google Sheets v4 client, inbound ETL staging integration, and outbound sync with status writeback and formula injection defense.
- **Success criteria**: Genuine async client with backoff; inbound sync wired to ETL staging; outbound export with CWE-1236 sanitization; full test suite in `tests/test_google_sheets_sync.py` passing together with `tests/test_etl_pipeline.py`.
- **Interface contracts**: `/Users/mainguyenbinhtan/Downloads/QuanLyKho/PROJECT.md`, `/Users/mainguyenbinhtan/Downloads/QuanLyKho/.agents/teamwork/explorer_survey_2/survey_backend_gsheets.md`
- **Code layout**: `/Users/mainguyenbinhtan/Downloads/QuanLyKho/AGENTS.md`

## Key Decisions Made
- Used native `google.oauth2.service_account.Credentials` and `google.oauth2.credentials.Credentials` with `asyncio.to_thread` for non-blocking token refresh, paired with `httpx.AsyncClient` for REST API calls to Google Sheets v4.
- Implemented `fetch_sheet_values`, `write_sheet_values`, and `batch_update_sheet_values` with exponential backoff and jitter on 429/503.
- Integrated formula sanitization (CWE-1236) on all outbound cell writing.
- Added `/runs/{run_id}/writeback` and `/export-google-sheets` routes to `etl.py` while preserving existing contract and behavior.
- Strictly maintained inventory ledger invariant (no direct update to `inv_balances`, all changes via `InventoryRequest` and `Movement`).

## Artifact Index
- `backend/app/services/google_sheets_service.py` — Pure async Google Sheets API v4 service
- `backend/app/api/routes/etl.py` — 4-layer ETL integration with Google Sheets inbound and outbound writeback
- `backend/tests/test_google_sheets_sync.py` — Comprehensive unit & integration pytest suite (13 tests)

## Change Tracker
- **Files modified**:
  * `backend/app/services/google_sheets_service.py`: Implemented pure async v4 client, SA/OAuth token generation, exponential backoff, formula sanitization, and writeback.
  * `backend/app/api/routes/etl.py`: Added support for Google Sheets credentials, allowlists, writeback endpoint, and export endpoint.
  * `backend/tests/test_google_sheets_sync.py`: Added 13 comprehensive tests for F8, F9, and F10.
- **Build status**: PASS (18 passed, 0 failed in `pytest tests/test_google_sheets_sync.py tests/test_etl_pipeline.py`)
- **Pending issues**: None

## Quality Status
- **Build/test result**: 18 passed in 12.5s
- **Lint status**: 0 violations (ruff check clean)
- **Tests added/modified**: 13 new tests in `test_google_sheets_sync.py`

## Loaded Skills
- None
