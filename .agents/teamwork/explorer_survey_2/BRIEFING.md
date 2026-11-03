# BRIEFING — 2026-11-02T14:55:00Z

## Mission
Survey QuanLyKho backend architecture, data models, and design bi-directional Google Sheets API integration (R3).

## 🔒 My Identity
- Archetype: explorer
- Roles: Backend & Google Sheets Integration Explorer
- Working directory: /Users/mainguyenbinhtan/Downloads/QuanLyKho/.agents/teamwork/explorer_survey_2
- Original parent: fbdb9d15-e07c-4143-974c-2efe416095ff
- Milestone: exploration_survey_phase

## 🔒 Key Constraints
- Read-only investigation — do NOT implement or modify application source code
- Write outputs only inside working directory (/Users/mainguyenbinhtan/Downloads/QuanLyKho/.agents/teamwork/explorer_survey_2/)
- Deliver survey_backend_gsheets.md and handoff.md
- Adhere to project conventions in QuanLyKho/AGENTS.md

## Current Parent
- Conversation ID: fbdb9d15-e07c-4143-974c-2efe416095ff
- Updated: 2026-11-02T14:55:00Z

## Investigation State
- **Explored paths**:
  * `backend/app/main.py`, `backend/app/config.py`, `backend/app/database.py`, `backend/app/worker.py`
  * `backend/app/models/` (`inventory.py`, `cash_sim.py`, `etl.py`, `integration.py`, `activity.py`, `idempotency.py`, `reconciliation.py`)
  * `backend/app/api/routes/` (`etl.py`, `exports.py`, `integrations.py`, `auth_google.py`, `inventory.py`, `cash_sim.py`)
  * `backend/app/services/` (`google_sheets_service.py`, `export_engine.py`, `etl_engine.py`, `idempotency.py`)
  * `backend/pyproject.toml`, `backend/poetry.lock`, `backend/sample-data/inventory.json`
  * `backend/tests/` (`test_etl_pipeline.py`, `test_export_sync.py`, `test_integrations.py`)
- **Key findings**:
  * Robust 4-layer ETL pipeline architecture already exists in `app/api/routes/etl.py` & `app/services/etl_engine.py`.
  * `google-auth = "^2.30.0"` and `httpx = "^0.27.0"` are already in `pyproject.toml`. No new external dependency is needed!
  * Service Account JSON and OAuth 2.0 credentials can be authenticated via `google-auth` to call Google Sheets API v4 directly using `httpx.AsyncClient`.
  * Core ledger invariants (non-negative balance, zero direct updates to balances without movements/requests, append-only audit, maker-checker rule) must be strictly preserved during Sheet import.
  * Formula Injection (CWE-1236) sanitization is already standardized in `export_engine.py`.
- **Unexplored areas**:
  * None within the assigned backend & Google Sheets survey scope.

## Key Decisions Made
- Decision 1: Recommend using existing `google-auth` + `httpx.AsyncClient` for native asynchronous REST API v4 communication rather than adding heavy/blocking libraries like `gspread` or `google-api-python-client`.
- Decision 2: Route all Google Sheets inbound sync operations through the existing 4-layer ETL pipeline (`/etl/*`) to ensure non-destructive staging, action diff previews, and maker-checker validation.
- Decision 3: Add bi-directional in-sheet status feedback by using API v4 `batchUpdate` to write execution outcomes directly onto the sheet.

## Artifact Index
- DISPATCH.md — Initial dispatch message
- BRIEFING.md — Persistent context & state tracking
- progress.md — Task checklist & liveness heartbeat
- survey_backend_gsheets.md — Detailed survey report & architectural blueprint for R3
- handoff.md — 5-component self-contained handoff report
