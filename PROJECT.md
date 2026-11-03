# Project: QuanLyKho Enterprise Upgrade & Real-World Productionization

## Architecture
- **Frontend**: Flutter Web SPA (Flutter 3.27.7, Dart 3.6.1) deployed on Cloudflare Workers Assets (`tea-inventory-web`).
  - Architecture: `CommerceWorkspace` (`frontend/lib/src/features/commerce/commerce_workspace.dart`) drives 8 business subsystems (Overview, Sales POS, Purchases, Inventory, Debt, Reports, Approvals, Settings) with in-memory store `CommerceMemoryStore` and `CommerceApi`.
- **Backend**: FastAPI (Python 3.11+), SQLAlchemy 2.0 (async/sync), Alembic migrations, PostgreSQL 16 on tmpfs for tests.
  - Endpoints registered in `backend/app/main.py` via `_mount_routes()` under `/` and `/api/v1/`.
  - Strict domain invariants: Non-negative balance constraint (`qty_non_negative`), immutable ledger movements (`inv_movements`), append-only audit events (`audit_events`), idempotent request key tracking (`idempotency_keys`).
- **Data Integration & ETL**:
  - 4-layer staging architecture: `EtlConnection` -> `EtlPipeline` -> `EtlMappingVersion` -> `EtlRun` -> `EtlRunRow`.
  - Bi-directional Google Sheets API v4 using `google-auth` for Service Account / OAuth token signing and `httpx.AsyncClient`.
- **Export Engine**:
  - Multi-format file export: Excel (.xlsx) via `openpyxl`, CSV via built-in `csv` (single UTF-8 BOM, sanitized against CWE-1236), PDF via `reportlab` with Unicode `Roboto` font.

## Feature Inventory
| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| F1 | Modern Homepage Revamp | Redesign overview tab with visual KPI cards, quick actions, and direct navigation to all 8 subsystems | M1 | ORIGINAL_REQUEST § R1 |
| F2 | Real-Time Subsystem Data Freshness | Add background state synchronization (periodic / event-driven reload) to keep subsystem data fresh across devices | M1 | ORIGINAL_REQUEST § R1, survey_frontend |
| F3 | Admin Role Change Notification & Session Refresh | Backend email notification on role updates and frontend 401 session refresh dialog on `auth_version` invalidation | M1 | ORIGINAL_REQUEST § R1, survey_frontend |
| F4 | Topbar Mobile Responsive Fix | Eliminate title squashing on 375px/390px/414px viewports by removing redundant `Spacer()` and optimizing compact layout | M2 | ORIGINAL_REQUEST § R2, survey_frontend BUG-01, BUG-02 |
| F5 | Metric Card Fitted Values | Wrap mini summary values in `FittedBox` to prevent large number clipping on mobile screens | M2 | ORIGINAL_REQUEST § R2, survey_frontend BUG-03 |
| F6 | Responsive Mobile Modals & Bottom Sheets | Replace hardcoded width dialogs (440px/420px/580px) with responsive bottom sheets or full-screen dialogs with vertical form layouts on <600px viewports | M2 | ORIGINAL_REQUEST § R2, survey_frontend BUG-04 to BUG-08 |
| F7 | Mobile Scroll & Component Polish | Resolve nested scroll friction in Debt tab, responsive 1-column cards in Reports, order tile text truncation, and bottom navigation indicator | M2 | ORIGINAL_REQUEST § R2, survey_frontend BUG-09 to BUG-12 |
| F8 | Pure Async Google Sheets API v4 Client | Service Account and OAuth 2.0 credential signing via `google-auth` + `httpx.AsyncClient` without heavy/blocking external libraries | M3 | ORIGINAL_REQUEST § R3, survey_backend_gsheets |
| F9 | Google Sheets Inbound Staging & ETL | Inbound sheet data ingestion through 4-layer ETL pipeline with schema validation, action previews, SHA-256 deduplication, and maker-checker ledger posting | M3 | ORIGINAL_REQUEST § R3, survey_backend_gsheets |
| F10 | Google Sheets Outbound Sync & Writeback | Outbound export to Google Sheets with `_sync_status` writeback, CWE-1236 formula sanitization, and quota backoff | M3 | ORIGINAL_REQUEST § R3, survey_backend_gsheets |
| F11 | CSV Double-BOM Defect Fix | Correct duplicated UTF-8 BOM bytes (`\xef\xbb\xbf\xef\xbb\xbf`) across `export_engine.py` and `exports.py` | M4 | ORIGINAL_REQUEST § R4, survey_export_tests |
| F12 | Server-Side PDF Export Engine | Implement lightweight, pure-Python PDF generation for reports and vouchers using `reportlab` and bundled `Roboto-Regular.ttf` | M4 | ORIGINAL_REQUEST § R4, survey_export_tests |
| F13 | Multi-Format Export Endpoints | Update `/exports/*` routes query pattern to `^(xlsx|csv|pdf)$` supporting Catalog, Balances, Movements, Cash Journal, Inventory Summary, and Reconciliations | M4 | ORIGINAL_REQUEST § R4, survey_export_tests |
| F14 | Comprehensive E2E Test Suite | 4-tier opaque-box requirement-driven test suite validating UI parity, Google Sheets sync, and multi-format exports | M5 (Final) / E2E Track | ORIGINAL_REQUEST Acceptance Criteria |
| F15 | Adversarial Coverage Hardening | Tier 5 white-box challenger analysis and test hardening | M5 (Final) | Project Pattern Dual Track |

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| M1 | Homepage Revamp & Subsystem Sync | F1, F2, F3: Modern homepage overview, subsystem sync, role change email hook & 401 session refresh | none | DONE |
| M2 | Mobile Viewport Parity & Component Fixes | F4, F5, F6, F7: Fix BUG-01 to BUG-12 on viewports 375px, 390px, 414px (topbar, dialogs, cards, scrolling) | M1 | DONE |
| M3 | Bi-Directional Google Sheets API Service | F8, F9, F10: Google Sheets API v4 async client, ETL staging & maker-checker inbound, outbound sync with status writeback | none | DONE |
| M4 | Multi-Format Data Export Service | F11, F12, F13: Fix CSV Double-BOM, implement PDF export engine via reportlab, expand `/exports/*` endpoints | none | DONE |
| M5 | E2E Test Pass & Adversarial Hardening | F14, F15: Pass 100% of E2E test suite (Tiers 1-4) and complete Tier 5 adversarial hardening | M1, M2, M3, M4 | DONE |

## Interface Contracts

### M1 ↔ M2 (Frontend Workspace Contract)
- `_WorkspaceTopbar`: Exposes `compact: bool = MediaQuery.of(context).size.width < 600`. When `compact == true`, title width must receive >= 140px, location chip displays icon + abbreviated warehouse name, and actions are grouped into a compact popup menu.
- `CommerceMemoryStore` ↔ `CommerceApi`: State reload contract via `Future<void> reload(CommerceMemoryStore store)`. Background refresh triggers this contract without resetting user navigation tab.
- HTTP 401 Session Interceptor: When backend returns 401 with `"auth_version"` or `"Phiên đăng nhập đã bị thu hồi"`, triggers `onSessionExpired(String reason)` callback displaying refresh dialog without losing draft inputs.

### M1 ↔ M3 / M4 (Backend Admin & Outbox Contract)
- `admin_users.py`: When `update_user_roles` increments `user.auth_version`, it dispatches email via `email_service.send_email(to=user.email, subject="Cập nhật quyền tài khoản", ...)` with non-blocking error handling.

### M3 ↔ M4 (Export & Sync Contract)
- Google Sheets Service and Export Engine share `export_engine.sanitize_cell_value(val)` to ensure zero CWE-1236 formula injection on all tabular outputs.
- Inbound Google Sheets pipelines yield standardized rows: `dict[str, Any]` matching `EtlMappingVersion` rules before generating `EtlRunRow` staging records.

## Code Layout
- `frontend/lib/src/features/commerce/`:
  - `commerce_workspace.dart`: Shell, Topbar (`_WorkspaceTopbar`), Bottom Navigation, Modals.
  - `commerce_memory_store.dart`: In-memory business state and reactive calculation.
  - `commerce_api.dart`: REST communication with backend.
  - `commerce_reports_page.dart`: Responsive reports cards.
- `backend/app/services/`:
  - `google_sheets_service.py`: Google Sheets API v4 async client and bi-directional sync logic.
  - `export_engine.py`: Multi-format serializer (openpyxl for xlsx, csv with single UTF-8 BOM, reportlab for pdf).
  - `etl_engine.py`: 4-layer ETL pipeline execution, action previews, staging, ledger posting.
  - `email_service.py`: SMTP notification delivery with HTML templates.
- `backend/app/api/routes/`:
  - `exports.py`: Multi-format export endpoints (`/exports/*`).
  - `etl.py`: Pipeline and connection configuration endpoints (`/etl/*`).
  - `admin_users.py`: User management and role assignment (`/admin/users/*`).
- `backend/tests/`:
  - Integration & unit test suites for all backend modules.
- `frontend/test/`:
  - Flutter widget tests for mobile viewports and UI synchronization.
