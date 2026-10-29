# Evidence Registry — QuanLyKho (2026-10-29)

**Repo:** `QuanLyKho`  
**Packaging task:** P3.7 — Python Evaluation Harvest — Review & Packaging  
**HEAD commit at packaging:** `9f877c2ad25ee5639c7a96b3c69037b2f40ff63c` (`feat: merge backend/docs into docs, remove temp/backup files, mask real emails`)  
**Branch:** `main`  
**Packaged by:** Kilo (Python Evaluation Harvest, Phase 3)  
**Date:** 2026-10-29

## Purpose

Standardized evidence directory `docs/evidence/YYYY-MM-DD/**` for QuanLyKho. Every claim marked `"verified"` in the multi-repo evaluation (P3) is backed by at least one file here. Each evidence file carries a markdown header: `task / commit SHA / command / output / status`.

> **Caveat (Python 3.14):** The sandbox runs Python 3.14.7 and `pytest` is not installed, so the backend suite cannot be re-executed locally here. Test figures below are carried forward from the last green local run captured in the repo's own evidence (`QA_REPORT.md`, `phase-m-closure.md`, CI run artifacts), not re-derived. See `01-backend-test-results.md` for the explicit caveat.

## Evidence index

| # | Evidence file | Task | Commit SHA | Claim covered | Status |
|---|---------------|------|------------|---------------|--------|
| 01 | `01-backend-test-results.md` | P3.7 | `9f877c2` | Backend: 405 passed / 6 failed / 11 skipped | VERIFIED (carried forward) |
| 02 | `02-flutter-test-results.md` | P3.7 | `9f877c2` | Flutter: 57 test files; 28/28 + 80/80 pass, analyze 0 | VERIFIED |
| 03 | `03-qa-report-11-vong.md` | P3.7 | `9f877c2` | QA 11 vòng; round 9: 136 passed / 2 skipped / 0 error | VERIFIED |
| 04 | `04-maker-checker-flow-evidence.md` | P3.7 | `9f877c2` | RBAC maker-checker / four-eyes approval flows | VERIFIED |
| 05 | `05-outbox-worker-evidence.md` | P3.7 | `9f877c2` | Outbox worker / reconciliation / idempotency | VERIFIED |
| 06 | `06-ci-results.md` | P3.7 | `9f877c2` | CI results (8 workflows; s9-k8s 2/2 RollingUpdate verified) | VERIFIED |
| 07 | `07-eval-report-summary.md` | P3.6/P3.7 | `9f877c2` | Harness overall 100.0/100, 6 dimensions | VERIFIED |

## Source evidence (read-only symlinks)

Stored under `_src/` for traceability; do not edit.

- `_src/QA_REPORT.md` → `QuanLyKho/QA_REPORT.md` (QA 11 vòng, full round matrix)
- `_src/docs/evidence/phase-m-closure.md` → `docs/evidence/phase-m-closure.md` (PHASE_M gate closure: S10/G2/S9 verified, S11 partial)
- `_src/docs/evidence/cloudflare-assets-azure-edge-2026-10-25.md` → `docs/evidence/cloudflare-assets-azure-edge-2026-10-25.md` (Cloudflare → Azure edge URL contract)
- `_src/.github/workflows` → `.github/workflows/` (8 CI workflows)
- `_src/backend/tests` → `backend/tests/` (95 pytest files)
- `_src/frontend/test` → `frontend/test/` (57 Flutter test files)
- `_src/docs/EVIDENCE.md` → `docs/EVIDENCE.md` (project evidence baseline)

## DoD check (P3.7)

- [x] Thư mục `docs/evidence/2026-10-29/` tồn tại
- [x] Các file evidence chính đã copy/symlink (backend tests, Flutter tests, QA report 11 vòng, maker-checker, outbox worker, CI results)
- [x] Mỗi file evidence có markdown header: task / commit SHA / command / output / status
- [x] Evidence registry (`INDEX.md`) có sẵn
- [x] Mỗi claim "verified" có file bằng chứng đi kèm

---
*File này được sinh tự động bởi Phase 3 P3.7. Không commit, không push.*
