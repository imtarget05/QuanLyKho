# TEST_VERIFICATION.md

## 1. Thông tin chung

| Mục | Chi tiết |
|-----|----------|
| Thời gian chạy | 30/10/2026 |
| Python version | 3.11.9 (qua pyenv) |
| Poetry version | 2.5.1 |
| Repo | QuanLyKho (feat/p0-p1-security-atomicity, commit 40d975f) |
| DB test | kilo_test trên port 5433 (PostgreSQL 16 qua Docker) |

---

## 2. Alembic migration

**Lệnh:** `poetry run alembic upgrade head`

**Kết quả:** Thành công, không lỗi, DB ở head (revision `031_otp_codes`).

---

## 3. Tests đã sửa 15 fail (tất cả pass)

| Test file | Số test | Test case đại diện |
|-----------|---------|--------------------|
| test_airflow_ingest_tasks.py | 2 | PROMOTION_THRESHOLD_R2 |
| test_api_v1_web_e2e.py | 1 | maker_checker_web_flow |
| test_multimodal_intake.py | 2 | parse_invoice_bytes |
| test_reversal.py | 1 | reversal_creates_new_draft_request |
| test_sse_redis.py | 1 | sse_endpoint_exists |
| test_stocktake_agent_unit.py | 7 | risk assessment evidence |
| test_worker_extended.py | 1 | retry_count |
| **Tổng** | **15 test logic (27 passed do parametrization)** | **0 failed, 0 errors** |

---

## 4. Các test file khác trước đó fail đã pass trên kilo_test mới

Danh sách test file: security_wave2_identity, shift_stocktake, sse_approvals, tea_inventory_catalog, trusted_proxy_client_ip, seed_role_capabilities, tea_shift_regression, worker_jobs

**Kết quả:** 65 passed, 7 warnings, 0 failed, 0 errors

---

## 5. Lệnh chạy test

```bash
cd /Users/mainguyenbinhtan/Downloads/QuanLyKho/backend
DATABASE_URL="postgresql+psycopg2://bankops:bankops@127.0.0.1:5433/kilo_test" APP_ENV=demo DEMO_MODE=true TESTING=1 poetry run pytest tests -q
```

---

## 6. Kết luận

**PASS** — 0 failed, 0 errors trên DB kilo_test đã migrate + seed.

File này có thể copy-paste làm tiếp.
