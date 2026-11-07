# QuanLyKho — Inventory & Treasury Operations (Demo)

Portfolio demo: FastAPI + PostgreSQL backend, Flutter web frontend, maker-checker workflow with audit trail. **Demo only** — not production, no real banking data.

## Evidence (verified 2026-11-07)

- Release SHA: `4418ad71b376d7f28d93daa39012fafdbadfd320`
- CI: https://github.com/imtarget05/QuanLyKho/actions/runs/42270199810 (success)
- S10 cloud CI acceptance: https://github.com/imtarget05/QuanLyKho/actions/runs/42270199866 (success)
- Render deploy `dep-dbn9muou01pc73c4ijig` live on this SHA; `/health/ready` → 200, DB ready, login rate limit ready
- Cloudflare Pages: https://quan-ly-kho-tra-sua.pages.dev/ (version.json exposes same SHA)
- DB: Alembic empty→head (`034_general_ledger_coa`), 10 demo users, 30 items, 33 balances, 120 safety stock, 3 cashboxes
- Maker-checker journey PASS: inventory +15, cash +300,000 VND; self-approval → 403
- Full evidence: see `INTERVIEW_CLOUD_EVIDENCE_2026-11-07.md`, `docs/INTERVIEW_RELEASE.md`

## Open (not claimed)

Full 21-ID UAT, mobile/offline device test, backup/restore drill, real owner sign-off. Render Free + shared KV are demo-grade.

## Stack

FastAPI, PostgreSQL 16, Redis (optional, fail-open in demo), Flutter 3.24+, Cloudflare Pages, Render.

## Run locally

See `backend/README` and `frontend/`. Tests: `pytest` (backend), `flutter test` (frontend).

