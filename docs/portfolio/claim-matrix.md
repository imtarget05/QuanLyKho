# Claim Matrix — QuanLyKho (commit `f65f962`)

Mỗi claim CV phải đi kèm bằng chứng (code/test/demo/CI) tại đúng commit. Ghi rõ giới hạn để không phóng đại.

| # | Claim | Bằng chứng (file + SHA) | Câu trả lời phỏng vấn | Giới hạn |
|---|-------|------------------------|----------------------|----------|
| 1 | Maker-checker dual control: người lập phiếu không tự phê duyệt | `backend/tests/test_portfolio_ai_checker_demo.py` @ `f65f962` (test `test_advice_then_checker_approve_or_reject_without_duplicate_post`) | "Maker submit phiếu, checker khác người duyệt. Nếu maker tự approve → trả 403 `SELF_APPROVAL_FORBIDDEN`. Invariant `maker_id != approver_id` được enforce ở route layer." | Chỉ verified trên dữ liệu mô phỏng (demo_maker/demo_checker), chưa chạy trên UAT thực. |
| 2 | Idempotency: cùng key không post doppi | `backend/tests/test_portfolio_ai_checker_demo.py` @ `f65f962` | "Lưu idempotency_key + SHA-256 payload vào bảng PostgreSQL. Replay cùng key → trả kết quả cũ, không ghi movement mới. Key khác sau trạng thái cuối → 409." | PostgreSQL-backed, chưa test trên multi-node crash recovery thực tế. |
| 3 | Atomic posting / rollback khi ledger thất bại | `backend/tests/test_portfolio_ai_checker_demo.py` @ `f65f962` (test `test_receipt_issue_audit_and_failed_post_are_atomic`) | "Injected `AppError(503, POSTING_UNAVAILABLE)` trước ledger commit → request vẫn ở `submitted`, balance/movement/audit không thay đổi. Toàn bộ trong 1 transaction PostgreSQL." | Failure được inject bằng `monkeypatch` trong test, không phải failure thực tế từ hệ thống bên ngoài. |
| 4 | Audit trail: append-only, auditor chỉ đọc | `backend/app/api/routes/audit.py` + `test_portfolio_ai_checker_demo.py` @ `f65f962` | "`audit_events` được bảo vệ bởi SQLAlchemy DBAPI event listener — chặn UPDATE/DELETE vật lý. Auditor chỉ có quyền đọc, xem sự kiện approve/reject với request ID." | Không claim tamper-proof ở cấp độ production (cần DB-level permission, WAL archiving...). |
| 5 | Alembic migration 33 file (001→034) | `backend/alembic/versions/` @ `f65f962` + `make test-backend` output | "33 migration tuần tự, không downtime, chạy qua ArgoCD migration job trên K8s. `alembic upgrade head` thành công trên PostgreSQL 16 isolated container." | Migration 023 bị bỏ (cosmetic gap trong tên file, không phải broken chain). |
| 6 | Flutter UI: 355 test pass, build web thành công | `frontend/test/` @ `f65f962` + `flutter build web --release` | "Flutter web release build thành công, artifact ở `frontend/dist/`. 355 test pass bao gồm widget test, RBAC test, AI copilot risk assessment modal." | `flutter analyze` không chạy được do lỗi môi trường Dart SDK (analysis server crash), không phải lỗi code. |
| 7 | FastAPI là write authority duy nhất | `backend/app/main.py` + `docs/adr/0001-canonical-api-fastapi-worker-proxy-deprecation.md` @ `f65f962` | "Cloudflare Worker không phải write authority. Tất cả write (RBAC, posting, audit) đi qua FastAPI + PostgreSQL transaction. Worker chỉ xử lý background job qua outbox pattern." | Worker parity được deprecate theo ADR 0001, không claim production worker. |

---

## Cách dùng trong phỏng vấn

1. Chọn claim phù hợp với JD (ví dụ: JD Backend nhấn đơn hàng 1, 2, 3; JD Fullstack nhấn 5, 6).
2. Trả lời theo cấu trúc: **Claim → Bằng chứng (commit + file) → Cách triển khai → Giới hạn**.
3. Không mở rộng claim ngoài bằng chứng có sẵn.
