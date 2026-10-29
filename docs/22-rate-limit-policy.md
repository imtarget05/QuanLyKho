# 22 — Rate-limit policy

Thong nhat mot bo policy rate-limit duyet cho tat ca cong cong API cua QuanLyKho
(FastAPI backend) de chong DDOS, brute force, va lufy du lieu qua API.

## 1. Muc tieu

- Gioi han so yeu cau cua mot nguoi dung / IP / API key trong mot khoang thoi gian.
- Tra `429 Too Many Requests` kèm `Retry-After` khi vuot ngưỡng.
- Khong ghi token / secret vao log rate-limit.

## 2. Ngưỡng (màu khởi tạo, chua do tren traffic thuc)

| Buoc | Scope | Ngưỡng | Cửa so | Hanh dong |
|------|-------|--------|--------|-----------|
| Auth (login / refresh) | IP + user-agent | 5 req | 1 phut | 429 + khoi dong captcha |
| API chung (xac thuc) | JWT subject / API key | 100 req | 1 phut | 429 |
| API chung (chua xac thuc) | IP | 20 req | 1 phut | 429 |
| Webhook nhap kho | webhook secret + IP | 30 req | 1 phut | 429 + lam toi uu du lieu |
| AI assess (tu van) | JWT subject | 10 req | 1 phut | 429 + huong dan |

## 3. Trien khai

- Middleware FastAPI (hoa extension `slowapi` / `redis`) luu counter trong Redis de chinh xac trong cac instance.
- Key boi: `JWT subject` neu da xac thuc, nguoc lai `X-Forwarded-For` / client IP.
- Header tra ve: `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset`.
- 429 kèm `Retry-After` (giay).

## 4. Liet ke voi secret rotation

Rate-limit khong kiem tra secret. Khi rotate token (xem `docs/security/credential-rotation-runbook.md`), ratelimit counter duoc lap lai theo nguoi dung moi (JWT subject thay doi) de khong bi lien quan giua cu va moi.

## 5. Rang buoc

- Khong su dung `*` voi ALLOWED_ORIGINS tren staging/prod (xem docs/14:71).
- Khong ghi raw body / token / raw rows vao log rate-limit.
- Muc ngưỡng chua duoc do tren traffic thuc: danh dau `MEASURED` sau khi co baseline Prometheus.
