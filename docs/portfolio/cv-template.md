# CV Template — QuanLyKho (ba biến thể JD)

**Lưu ý:** Đây là mẫu, không chứa dữ liệu cá nhân. Sao chép và điền thông tin cá nhân trước khi dùng.

---

## Biến thể 1: Backend Engineer

**Tóm tắt:** Backend Engineer chuyên thiết kế API transactional, RBAC, idempotency và audit trail trên PostgreSQL. Dự án tiêu biểu: QuanLyKho — hệ thống quản lý kho & tài chính mô phỏng với maker-checker dual control.

### Dự án: QuanLyKho (commit `f65f962`)
- Thiết kế API FastAPI + SQLAlchemy 2.0 (AsyncSession) làm write authority duy nhất cho RBAC, posting và audit.
- Xây dựng maker-checker dual control: chặn self-approval (403), idempotency key (SHA-256 payload validation), atomic posting với rollback khi ledger thất bại.
- Quản lý schema bằng Alembic (33 migration 001→034, không downtime), chạy trên PostgreSQL 16.
- Viết test integration cho luồng receipt → approve → movement → balance → audit, 2 test demo pass.

**Tech stack:** Python 3.11, FastAPI, SQLAlchemy 2, PostgreSQL 16, Alembic, Docker, Poetry, Pytest.

---

## Biến thể 2: Fullstack / Product Engineer

**Tóm tắt:** Fullstack Engineer xây dựng sản phẩm nghiệp vụ end-to-end: backend FastAPI/PostgreSQL kết hợp frontend Flutter web. Dự án tiêu biểu: QuanLyKho.

### Dự án: QuanLyKho (commit `f65f962`)
- Backend: FastAPI API với RBAC theo nhánh, maker-checker workflow, idempotency, audit trail.
- Frontend: Flutter web (355 test pass, release build thành công), giao diện dashboard kho, phiếu nhập/xuất, quản lý user vai trò.
- Kết nối API backend + Flutter UI qua REST, dữ liệu mô phỏng trong RAM cho demo offline.

**Tech stack:** Python 3.11, FastAPI, PostgreSQL, Flutter 3.47.7, Dart, Docker, GitHub Actions.

---

## Biến thể 3: AI / Platform Engineer

**Tóm tắt:** AI/Platform Engineer chuyên hệ thống trợ lý AI theo dự đoán, không thay đổi quyết định nghiệp vụ. Dự án tiêu biểu: QuanLyKho (advisory AI fallback) và hai repo khác trong portfolio (IncidentIQ, Smart Document Chatbot).

### Dự án: QuanLyKho (commit `f65f962`)
- Xây dựng advisory AI path với `heuristic_fallback` và `simulation=true` — AI chỉ tư vấn, không đăng kho hay phê duyệt phiếu.
- Phân ranh giới rõ ràng giữa AI advisory (read-only) và authorization decision (human checker).
- Ghi audit stamp (SHA-256) cho mọi sự kiện AI → có thể truy vết.

**Tech stack:** Python 3.11, FastAPI, PostgreSQL, deterministic heuristic (không dùng mô hình ML bên ngoài), audit trail.

---

## Quy tắc dùng CV

- Tối đa 2 bullet mỗi repo trong mỗi biến thể.
- Thứ tự repo thay đổi theo JD (repo phù hợp JD nhất lên đầu).
- Không nhận là đáp ứng mọi vị trí — ba repo không chứng minh mobile native, QA chuyên biệt, hay data science.
- Mọi claim phải có link bằng chứng (code, test, demo, CI) tại đúng commit.
