# ADR 023: Thay `python-jose` bằng `joserfc` (Xử lý JWT)

## Status
Accepted

## Date
2026-10-29

## Related
ADR 022 (single canonical deploy target), backend/pyproject.toml,
backend/app/api/routes/auth_utils.py, backend/app/api/routes/auth.py

---

## Context

`python-jose` (JOSE) là thư viện xử lý JWT hiện tại của backend
(`pyproject.toml:38`). Vấn đề:

1. `python-jose` đã hết năng lực bảo trì, phát hành chậm, ít nhận bản vá bảo mật
   kịp thời so với các thay thế hiện đại.
2. API của `python-jose` (`jose.jwt.encode/decode`, `JWTError`) cũ kỹ, dễ
   nhầm lẫn giữa các kiểu payload và không khai báo kiểu rõ ràng cho Python 3.11+.
3. Backend cần một thư viện JWT hiện đại, type-safe, được bảo trì tích cực để
   phục vụ refresh-token rotation, logout-revoke và auth hardening (P1.14).

## Decision

1. **Xoá `python-jose` khỏi dependencies** (`backend/pyproject.toml`).
2. **Thêm `joserfc`** (thay thế trực tiếp cho encode/decode JWT, RS256/HS256)
   và **`authlib`** (dùng cho các trường hợp OAuth/OIDC phức tạp hơn sau này,
   ví dụ Google auth) vào `backend/pyproject.toml`.
3. **Tái cấu hình mã JWT** trong `app/api/routes/auth_utils.py` và
   `app/api/routes/auth.py` để dùng `joserfc` thay vì `jose`, thông qua một
   lớp wrapper nhỏ (`app/core/jwt.py`) giữ API ổn định cho toàn bộ ứng dụng.
4. **Migration fail-start-up**: nếu `joserfc` không có sẵn hoặc cấu hình JWT
   sai (thiếu `BANKOPS_SIGNING_KEY`), ứng dụng KHÔNG khởi động (fail-start-up),
   được bảo vệ bởi unit-test.

## Consequences

- **Positive**:
  - Thư viện JWT hiện đại, actively maintained, type-hint rõ ràng.
  - Giữ nguyên thuật ngữ rotation / revoke / deny-list đã có (P1.14 không bị
    thay đổi hành vi).
  - Dễ dàng erweit sang `authlib` khi cần OIDC/Google auth tiefer.
- **Negative / Trade-offs**:
  - Cần viết lại đoạn mã encode/decode JWT (auth_utils.py, auth.py) và các test
    liên quan.
  - `joserfc` chưa có trong lockfile hiện tại — phải chạy `poetry lock` +
    `poetry install` trước khi triển khai (xem P1.15 unit-test).

## Approval

| Role | Name | Signature | Date |
|---|---|---|---|
| Architect | | | |
| Security Lead | | | |
| Backend Lead | | | |

