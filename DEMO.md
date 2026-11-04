# QuanLyKho — Interview Demo Script (5–10 phút, chạy hoàn toàn local)

Mục đích: minh họa hệ thống tồn kho & quỹ mô phỏng với maker-checker 4 mắt, dual-entry ledger, audit trail, không cần production deploy.

## Yêu cầu trước khi demo

- Docker & docker compose (để chạy PostgreSQL + API)
- Python 3.11+, poetry đã cài (`poetry install --with dev`)
- Flutter SDK (tuỳ chọn, để chạy frontend test)

## Bước 1: Khởi động stack local

```bash
cd /Users/mainguyenbinhtan/Downloads/QuanLyKho

docker compose up -d  # API :8000, PostgreSQL :5432
```

Hoặc chạy test với database tách biệt (khuyên dùng):

```bash
make test-backend
```

## Bước 2: Tạo dữ liệu demo qua API

```bash
# Health check
curl http://localhost:8000/health

# Tạo item kho (inventory)
curl -s -X POST http://localhost:8000/api/inventory/items \
  -H "Content-Type: application/json" \
  -d '{"sku": "TEA-001", "name": "Trà xanhMatcha", "unit": "kg", "cost_price": 120000, "selling_price": 200000, "min_stock": 10}'

# Xem catalog
curl http://localhost:8000/api/inventory/catalog
```

## Bước 3: Workflow maker-checker (4 mắt)

```bash
# Maker tạo phiếu kho (submit -> PENDING_REVIEW)
curl -s -X POST http://localhost:8000/api/inventory/requests \
  -H "Content-Type: application/json" \
  -d '{"item_sku": "TEA-001", "quantity": 50, "type": "INBOUND"}'

# Checker duyệt (phải là người khác với maker)
curl -s -X POST http://localhost:8000/api/inventory/requests/{request_id}/approve \
  -H "Content-Type: application/json" \
  -d '{"action": "approve", "reason": "Demo approval"}'

# Xem sổ cái kép (dual-entry ledger)
curl http://localhost:8000/api/reports/ledger
```

## Bước 4: Health check

```bash
curl http://localhost:8000/health
```

## Bước 5: Chạy toàn bộ test suite

```bash
cd backend

# Ruff (0 errors mong đợi)
poetry run ruff check backend/ ai/

# Pytest (975 passed, 8 skipped, 1 xfailed mong đợi)
poetry run python -m pytest tests/ -q
```

## Bước 6: Flutter frontend test (tuỳ chọn)

```bash
cd frontend
flutter test --no-pub
# Kết quả mong đợi: 350/350 passed
```

## Các điểm nhấn để trình bày phỏng vấn

| Điểm | Nơi chứng minh |
|---|---|
| Maker-checker 4 mắt (phải là người khác) | `backend/app/api/routes/inventory.py`, `backend/app/services/approval_controls.py` |
| Dual-entry ledger (sổ cái kép) | `backend/app/services/general_ledger.py`, `backend/app/models/ledger.py` |
| Audit trail với SHA-256 stamp | `backend/app/api/routes/inventory.py` (audit stamp hash) |
| Idempotency (chống double-submit) | `backend/app/api/middleware/idempotency.py` |
| Alembic migrations (34 versions) | `backend/alembic/versions/` |
| Flutter mobile/web frontend | `frontend/lib/src/`, `frontend/test/` |
| Keyset pagination (inventory balances) | `backend/app/api/pagination.py` |

## Giới hạn trung thực (không claim)

- Quỹ, journal, đối soát là **financial-operations simulation**, không phải core-banking.
- Không kết nối ngân hàng, không sử dụng dữ liệu khách hàng thật, không xử lý tiền thật.
- Local test xanh (975 passed) nhưng chưa có bằng chứng production deploy.
- Cloudflare Worker giữ tạm để tương thích, không phải đích deploy production.
- Một số historical TestClient flow có vấn đề event-loop, giữ nguyên thay vì che giấu.
