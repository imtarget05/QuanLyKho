# Baseline — QuanLyKho portfolio evidence

**Commit:** `f65f96249033fd7e83ad910242c6acec86e8544a` (short: `f65f962`)
**Branch:** `codex/portfolio-three-repo-plan`
**Date:** 2026-11-12
**Environment:** macOS, Docker Desktop, Python 3.11.15 (Poetry 2.5.1), Flutter 3.47.7 (Dart 3.13.5)

## P0-T1 — Baseline commit và artifact

### 1. Trạng thái worktree

```
git status → clean (không có thay đổi theo dõi, ngoại trừ tasks/plan.md và tasks/todo.md chưa commit)
git rev-parse HEAD → f65f96249033fd7e83ad910242c6acec86e8544a
```

### 2. Backend test (Docker Compose PostgreSQL 16)

**Lệnh:** `make test-backend` (chạy các bước riêng lẻ do timeout):

| Bước | Lệnh | Kết quả |
|------|------|---------|
| Start PostgreSQL container | `docker compose -p quanlykho-test -f docker-compose.test.yml up -d --wait` | ✅ Container healthy |
| Alembic migration | `alembic upgrade head` | ✅ 34 migrations (001→034) applied |
| Seed demo data | `python -m app.seed` | ✅ 8 roles, 16 caps, 39 mappings, 10 users, 4 locations, 30 items, 33 balances, 120 safety stock, 3 cashboxes |
| Alembic upgrade head (lần 2) | `alembic upgrade head` | ✅ Idempotent |
| Demo test | `pytest tests/test_portfolio_ai_checker_demo.py -v` | ✅ **2 passed** |

**Demo test chi tiết:**
- `test_advice_then_checker_approve_or_reject_without_duplicate_post` — PASSED
- `test_receipt_issue_audit_and_failed_post_are_atomic` — PASSED

**Hành vi được chứng minh:**
- Maker tạo phiếu nhập → chưa có stock movement
- Checker khác người duyệt → 1 stock movement, balance tăng 12
- Maker tự duyệt → 403 `SELF_APPROVAL_FORBIDDEN`
- Lặp cùng idempotency key → kết quả cũ (không post doppi)
- Key khác sau trạng thái cuối → 409
- Checker từ chối phiếu khác → không có stock movement
- Auditor thấy sự kiện approve/reject với request ID
- Injected ledger failure → request stays `submitted`, rollback balance/movement/audit

**Ghi chú:** Toàn bộ test suite qua `make test-backend` bị timeout sau 300s (tiến độ ~57% khi dừng). Demo test (2 test cốt lõi) chạy thành công trong 5.18s.

### 3. Ruff lint

**Lệnh:** `python -m ruff check backend/ ai/`

**Kết quả:** `All checks passed!` (0 cảnh báo)

### 4. Flutter analyze

**Lệnh:** `flutter analyze --no-fatal-infos --no-fatal-warnings`

**Kết quả:** ❌ Analysis server crash (`FormatException: Unexpected end of input` trong Dart LSP channel) — đây là lỗi môi trường Dart SDK (Flutter 3.47.7 / Dart 3.13.5), không phải lỗi code. Thử lại nhiều lần và `flutter clean` vẫn gặp cùng lỗi.

**Hướng xử lý:** Bỏ qua `flutter analyze` do lỗi môi trường; dùng `flutter test` và `flutter build web` làm bằng chứng thay thế.

### 5. Flutter test

**Lệnh:** `flutter test --no-pub`

**Kết quả:** ✅ **355 passed, 0 failed**

### 6. Flutter build web

**Lệnh:** `flutter build web --release --no-tree-shake-icons --dart-define=OFFLINE_DEMO=true`

**Kết quả:** ✅ `✓ Built build/web` (warnings về wasm dry run chỉ là thông báo, không chặn build)

## P0-T2 — Chứng minh luồng nghiệp vụ maker/checker

✅ Hoàn tất thông qua 2 demo test ở trên. Mọi claim trong demo đã được verify bằng code test tại commit `f65f962`.

## Tiêu chí P0

- [x] Có bảng lệnh/kết quả/commit/ngày tại file này
- [x] Mọi số test là số tái lập tại commit hiện tại (không dùng số lịch sử 988/355)
- [x] Demo nghiệp vụ chạy lại được bằng lệnh `pytest tests/test_portfolio_ai_checker_demo.py`
- [x] Ruff lint sạch (0 cảnh báo)
- [x] Flutter test: 355 passed
- [x] Flutter build web: thành công

## Giới hạn (đối với CV)

- Không claim production deployment (chỉ local Docker test container)
- Không claim ngân hàng thật / tiền thật (cash là simulation)
- Không claim AI tự quyết định (AI chỉ tư vấn heuristic fallback, human checker quyết định)
- Không claim Flutter offline (chưa chứng minh offline behavior)
- `flutter analyze` không chạy được do lỗi môi trường Dart SDK

---

## Bước tiếp theo (P1)

1. Tạo `docs/portfolio/quanlykho-overview.md` — trang giới thiệu 1 trang
2. Viết CV ba repo theo 3 nhóm JD (Backend, Fullstack/Product, AI/Platform)
3. Tạo `docs/portfolio/claim-matrix.md` — bảng claim → bằng chứng → câu trả lời phỏng vấn