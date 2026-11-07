# Render Dashboard Checklist — kho-tra-sua-fastapi

Service: `https://kho-tra-sua-fastapi.onrender.com`
Health check: `GET https://kho-tra-sua-fastapi.onrender.com/api/v1/health/ready`

## Root cause (đã xác nhận)

`render.yaml` set `APP_ENV=production` và `REDIS_URL` có `sync: false` (chỉ nhập ở Dashboard, không sync từ file). Code tại `backend/app/api/routes/auth_utils.py:226-256` bắt buộc trong production:

- `REDIS_URL` phải bắt đầu bằng `rediss://` (TLS), ngược lại trả 503 `LOGIN_RATE_LIMIT_REQUIRES_TLS`
- Redis phải reachable, ngược lại trả 503 `LOGIN_RATE_LIMIT_UNAVAILABLE`

`GET /api/v1/health/ready` gọi `assert_redis_ready()` (`backend/app/api/routes/health.py:67`) -> 503 khi Redis chưa sẵn sàng.

## Bước 1 — Truy cập Render Dashboard

1. Mở https://dashboard.render.com
2. Chọn Web Service `kho-tra-sua-fastapi`
3. Vào tab **Environment**

## Bước 2 — Thiết lập Environment Variables

Copy-paste từng dòng vào Render Dashboard (Environment Variables), sau đó nhấn **Save Changes**:

| Key | Value | Lưu ý |
|-----|-------|-------|
| `APP_ENV` | `production` | Bắt buộc, fail-closed production |
| `DATABASE_URL` | `postgresql+asyncpg://<user>:<password>@<host>:5432/<db>?sslmode=require` | Thay `<user>`, `<password>`, `<host>`, `<db>` bằng giá trị thực của Render Postgres |
| `REDIS_URL` | `rediss://:<password>@<host>:6379/0` | **Phải bắt đầu bằng `rediss://`** (TLS). Thay `<password>`, `<host>` bằng giá trị thực của Render Redis |
| `BANKOPS_SIGNING_KEY` | `<random long secret>` | Tạo: `openssl rand -base64 48` |
| `BANKOPS_SESSION_SECRET` | `<random long secret>` | Tạo: `openssl rand -base64 48` |
| `SMTP_PASSWORD` | `<gmail-app-password>` | App Password Gmail (không phải mật khẩu chính) |
| `FRONTEND_BASE_URL` | `https://quan-ly-kho-tra-sua.tanmainguyenbinh.workers.dev` | Domain frontend thực tế |
| `ALLOWED_ORIGINS` | `["https://quan-ly-kho-tra-sua.tanmainguyenbinh.workers.dev"]` | JSON array, không trailing slash |

**Lưu ý:** Các biến `DATABASE_URL`, `REDIS_URL`, `SMTP_PASSWORD` có `sync: false` trong `render.yaml` -> chỉ tồn tại ở Dashboard, không bị ghi đè từ file.

## Bước 3 — Save Changes & Redeploy

1. Nhấn **Save Changes** sau khi nhập xong tất cả biến.
2. Vào tab **Deploys** -> nhấn **Manual Deploy** -> **Deploy latest commit** (hoặc latest successful build).
3. Chờ build và health check xanh.

## Bước 4 — Xác nhận sau redeploy

Chạy lệnh kiểm tra (xem file `scripts/curl-health-ready.sh`):

```bash
curl -i https://kho-tra-sua-fastapi.onrender.com/api/v1/health/ready
```

Kết quả mong đợi:
- HTTP `200`
- Body JSON: `{"status": "ready", ..., "services": {"database": "ready", "login_rate_limit": "ready"}}`

Logs không nên còn xuất hiện:
- `Required Redis readiness check failed (ConnectionError)`
- `LOGIN_RATE_LIMIT_UNAVAILABLE`
- `LOGIN_RATE_LIMIT_REQUIRES_TLS`

## Bước 5 — Nếu vẫn 503

1. Kiểm tra lại `REDIS_URL` bắt đầu đúng bằng `rediss://` (không phải `redis://`).
2. Kiểm tra Render Redis instance đang chạy và cho phép kết nối từ service `kho-tra-sua-fastapi` (Internal Connection / Public endpoint).
3. Kiểm tra `DATABASE_URL` có `sslmode=require` và DB reachable.
4. Redeploy lại sau khi chỉnh env.
