# QuanLyKho — Portfolio Overview (2027)

**Repo:** `imtarget05/QuanLyKho` (nhánh `codex/portfolio-three-repo-plan`, commit `f65f962`)  
**Stack:** Python 3.11, FastAPI, SQLAlchemy 2.0 (AsyncSession), PostgreSQL 16, Alembic, Flutter 3.47.7, Docker, Poetry  
**Vai trò trong portfolio:** Sản phẩm nghiệp vụ kho & tài chính mô phỏng — chứng minh năng lực xây hệ thống giao dịch đúng, kiểm soát kép, tính đúng đắn dữ liệu.

---

## Vấn đề (30 giây)

Một quán trà sữa đa chi nhánh cần kiểm soát tồn nguyên liệu theo kho/lô/hạn dùng. Phiếu nhập/xuất không được sai lệch số lượng khi nhiều người thao tác cùng lúc. Cần phân quyền rõ ràng: người lập phiếu (maker) khác người phê duyệt (checker), không tự phê duyệt eigenes phiếu.

---

## Luồng chính (maker → checker → posted)

```
Maker tạo draft phiếu nhập (Idempotency-Key)
   → Submit (trạng thái: submitted, chưa có movement)
   → Checker (khác người) duyệt
   → Trong 1 transaction PostgreSQL:
       - Lock balance, post movement + journal
       - Ghi audit event
       - Ghi outbox event
   → Commit nguyên vẹn hoặc rollback toàn bộ nếu ledger posting thất bại
```

**Ràng buộc quan trọng:**
- `maker_id != approver_id` (chặn self-approval ngay cả với root admin)
- Idempotency key → cùng key trả kết quả cũ, key khác sau trạng thái cuối → 409
- Ledger posting thất bại → request vẫn ở `submitted`, rollback balance/movement/audit

---

## Đóng góp kỹ thuật (của tác giả repo)

1. **FastAPI là write authority duy nhất** — một model transactional cho RBAC, posting và audit (xem [ADR 0001](../adr/0001-canonical-api-fastapi-worker-proxy-deprecation.md)).
2. **PostgreSQL là source of truth** — row lock (`SELECT ... FOR UPDATE`), constraint kiểm soát stock/cash race condition, SQLite không được chấp nhận làm thay thế.
3. **Maker-checker dual control** — invariant A1 được enforce ở domain và route layer.
4. **Idempotency bền vững** — bảng `idempotency_keys` trong PostgreSQL với SHA-256 payload validation, phục vụ sau node crash.
5. **Transactional Outbox** — atomic dual-write domain state + `outbox_events`, drain qua background worker (`SELECT ... FOR UPDATE SKIP LOCKED`).
6. **Audit append-only** — `audit_events` bị chặn UPDATE/DELETE ở mức SQLAlchemy DBAPI event listener.
7. **Alembic migration** — 33 migration tuần tự (001→034, bỏ 023), không downtime, chạy qua ArgoCD migration job trên K8s.

---

## Bằng chứng (tại commit `f65f962`)

| Claim | Bằng chứng | Link |
|-------|-----------|------|
| Alembic migration 001→034 | `docker compose -p quanlykho-test` + `alembic upgrade head` | [`docs/portfolio/baseline-f65f962.md`](./baseline-f65f962.md) |
| Demo test maker/checker 2 passed | `pytest tests/test_portfolio_ai_checker_demo.py` | [`backend/tests/test_portfolio_ai_checker_demo.py`](../backend/tests/test_portfolio_ai_checker_demo.py) |
| Ruff lint sạch | `ruff check backend/ ai/` → `All checks passed!` | [`backend/pyproject.toml`](../backend/pyproject.toml) |
| Flutter test 355 passed | `flutter test --no-pub` | [`frontend/test/`](../frontend/test/) |
| Flutter build web | `flutter build web --release` | [`frontend/dist/`](../frontend/dist/) |

---

## Giới hạn (không claim)

- **Không phải production deployment** — chỉ chạy trên local Docker test container, chưa có UAT sign-off hay DR proof.
- **Không phải ngân hàng thật / tiền thật** — cash là simulation, không kết nối payment processor hay core-banking.
- **AI chỉ tư vấn, không quyết định** — heuristic fallback với `simulation=true`, human checker có quyền laatste.
- **Không claim Flutter offline** — chưa chứng minh offline behavior.
- **`flutter analyze` không chạy được** do lỗi môi trường Dart SDK (analysis server crash), không phải lỗi code.

---

## Cách chạy demo (1 lệnh)

```bash
# Backend: migration + seed + demo test
make test-backend

# Hoặc chỉ demo tập trung:
bash scripts/demo_ai_checker.sh

# Frontend: build web demo
make build-frontend
```

---

## So sánh với hai repo khác trong portfolio

| | IncidentIQ | Smart Document Chatbot | QuanLyKho |
|---|-----------|----------------------|-----------|
| **Chủ đạo** | Xử lý sự cố, RAG, MCP | Nền tảng tài liệu, RAG, Spring Boot | **Sản phẩm nghiệp vụ kho, giao dịch đúng** |
| **Ngôn ngữ chính** | Python (FastAPI) | Java (Spring Boot) | **Python (FastAPI)** |
| **Frontend** | Cloudflare Worker + HTML/JS | React | **Flutter** |
| **DB** | — | — | **PostgreSQL + Alembic** |
| **Kiểm soát** | — | — | **Maker-checker, idempotency, audit** |
| **AI** | RAG, eval, MCP | RAG, LLM router | **Advisory fallback chỉ (không quyết định)** |

QuanLyKho khác hai repo RAG bằng cách tập trung vào **tính đúng đắn của giao dịch nghiệp vụ** (maker-checker, dual-entry ledger, atomic posting, audit trail) thay vì AI retrieval.
