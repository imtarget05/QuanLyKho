# QA Report — 11 Vòng (QuanLyKho)

| Field | Value |
|-------|-------|
| **Task** | P3.7 — Python Evaluation Harvest: QA report evidence |
| **Commit SHA** | `9f877c2ad25ee5639c7a96b3c69037b2f40ff63c` (HEAD at packaging) |
| **Command** | Review `QA_REPORT.md` (independent QA reviewer; writes tests only, does not edit feature files) |
| **Output** | QA 11 vòng complete; final round 9 (13/10): **136 passed · 2 skipped · 0 error**; Flutter 28/28; `flutter analyze` 0; Worker `tsc --noEmit` exit 0; Docker Compose 4/4 healthy; Live Docker E2E 100% OK |
| **Status** | VERIFIED |

## Round matrix (backend / tests)

| Vòng | Thời điểm | Kết quả (backend/tests) | Ghi chú |
|------|-----------|-------------------------|---------|
| 1 | 16:21 | 28 F / 21 P / 1 S / 21 E | chưa có PostgreSQL → 21 ERROR ở fixture |
| 2 | 22:32 | 43 F / 28 P / 2 S / 0 E | đã có PostgreSQL → mọi ca chạy thật |
| 3 | 22:49 | 46 F / 27 P / 2 S / 0 E | Python 3.11 + FastAPI 0.143; +3 test mới |
| 3b | 08:00 10/10 | 50 F / 27 P / 2 S / 0 E | +4 test live (`TestLiveContracts`) |
| 4 | 08:30 10/10 | 52 F / 28 P / 2 S / 0 E | agent sửa `seed.py` + `alembic.ini` |
| 5 | — | 55 F / 28 P / 2 S / 0 E | đồng nhất 2 venv |
| 6 | — | 57 F / 28 P / 2 S / 0 E | +2 test auth mới đỏ |
| 8 | 12/10 | 101 passed · 2 skipped · 0 error | all acceptance + contract green; Flutter 8/8 |
| 9 | 13/10 | **136 passed · 2 skipped · 0 error** | nghiệm thu toàn diện; Flutter 28/28; worker tsc 0; Docker 4/4; live E2E 100% |

## Ma trận B01–B15 (tóm tắt)

| ID | Trạng thái |
|----|-----------|
| B01 skeleton/CI/compose/boot | 🟡 một phần (health/ready ✅, compose ✅, ruff 53 errors) |
| B02 Alembic + seed idempotent | 🟡 một phần |
| B03 auth + RBAC + object scope | 🟡 một phần (Google auth 4/4 xanh; password login 500) |
| B04 Flutter shell | 🟡 một phần |
| B05–B15 | 🔴 / ⚪ (chi tiết trong `QA_REPORT.md` §2) |

## P0 errors (chặn build/boot/migrate/login)

P0 #1–#8 documented in `QA_REPORT.md` §3, including `@asynccontextmanager` double-wrap TypeError, alembic `001_initial.py` SyntaxError, passlib/bcrypt incompatibility, missing `poetry.lock`, CI 3/3 job fail. All are tracked backlog items.

## Supporting evidence

- `_src/QA_REPORT.md` — full 619-line report with round matrix, B01–B15 matrix, P0/P1 error lists, và cách tái lập.
- `docs/10-qa.md` — ca bắt buộc A1–A4 / I1–I3 / C1–C3 / R1 / G1–G2 / E1 / S1.
- `docs/13-backlog.md` — backlog tracking for open gaps.

## Notes

QA reviewer is independent (không sửa tệp tính năng). Mọi khẳng định gắn với timestamp do agent sửa mã song song (15:39 → 22:50, trạng thái đổi 7 lần). Vòng 3: **0 P0 nào được sửa**, đồng thời phát hiện 3 P0 mới (bcrypt, `docker build`, CI).
