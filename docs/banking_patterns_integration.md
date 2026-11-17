# Tài liệu kiến trúc tích hợp pattern ngân hàng vào QuanLyKho

**Dự án:** QuanLyKho (Kho Quản Lý & Ngân Hàng AI)  
**Stack:** FastAPI + SQLAlchemy 2.x + Alembic + PostgreSQL 16 + Poetry + Pytest  
**Nguồn tham chiếu:** `interview-prep/` (02-banking-domain-architecture, 03-system-design-banking), GAP_ANALYSIS_MATRIX.md  
**Môi trường độc lập:** `make test-backend` (PostgreSQL 16 cục bộ qua docker-compose.test.yml, không cần dịch vụ đám mây)

---

## 1. Tổng quan luồng tích hợp

Tất cả các write nghiệp vụ tài chính (chuyển tiền / kho, phong tỏa, xác nhận, hủy) diễn ra trong **một transaction ACID duy nhất** chứa cùng lúc:

1. Bút toán sổ cái kép (Double-entry ledger, ∑Debit = ∑Credit).
2. Bản ghi outbox sự kiện (Transactional Outbox, cùng transaction).
3. Bản ghi audit trail append-only (hash-chain SHA-256).
4. Trạng thái saga / bước saga (nếu là giao dịch đa bước).

Cơ chế này khắc phục triệt để **Dual-Write Problem** (interview-prep 02/05 §2): không bao giờ có trạng thái "ghi DB xong nhưng gửi event thất bại" hay "gửi event rồi DB rollback".

```
Client --(X-Idempotency-Key)--> FastAPI --(IdempotencyMiddleware claim_key)-->
   Banking API (app/api/routes/banking.py)
         │
         ├─> ConcurrencyService (SELECT FOR UPDATE / version check) ──> inv_balances
         ├─> SagaOrchestrator (TCC: Try reserve -> Confirm deduct source/add dest -> Release)
         │        │                                                │
         │        ├─ step thành công ──> GeneralLedger post (double-entry, ∑dr=∑cr)
         │        └─ step thất bại ───> chạy bù trừ ngược thứ tự (compensating)
         │
         ├─> OutboxEvent (cùng transaction DB) ──> worker.dispatch_outbox ──> Kafka/Redis
         └─> AuditEvent (append-only) + hash-chain SHA-256 (previous_hash -> chain_hash)
```

---

## 2. Các thành phần kiến trúc

### 2.1 Sổ cái kế toán kép (Double-entry Ledger)

- Mỗi giao dịch là một `InventoryJournal` chứa các `InventoryEntry` (account_code, debit, credit).
- Ràng buộc DB: mỗi dòng có đúng một vế dương (`(debit > 0 AND credit = 0) OR (credit > 0 AND debit = 0)`), số tiền không âm.
- `app/services/general_ledger.py::post_subledger_journal` kiểm tra ∑Debit = ∑Credit trước khi ghi, ném `ValueError` nếu lệch.
- Vị trí: `app/models/ledger.py`, `app/services/general_ledger.py`, `alembic/versions/033_inventory_ledger.py`.

### 2.2 Idempotency Key (3 lớp phòng thủ)

1. **Lớp 1:** `IdempotencyMiddleware` (Starlette) — khóa phân tán trên key `idempotency-key` header, fast path in-memory.
2. **Lớp 2:** Bảng `idempotency_keys` (`idempotency_key UNIQUE`), `INSERT ... ON CONFLICT DO NOTHING` cùng transaction với nghiệp vụ.
3. **Lớp 3:** Máy trạng thái PENDING → PROCESSING → COMPLETED/FAILED, lưu response body; replay cùng key + cùng payload trả kết quả cũ; cùng key khác payload → 409 `IDEMPOTENCY_KEY_REUSED`.

Vị trí: `app/models/idempotency.py`, `app/services/idempotency.py`, `app/api/middleware/idempotency.py`.

### 2.3 Transactional Outbox

- Bảng `outbox_events` (id, event_type, aggregate_id, payload_json, created_at, published_at, attempts).
- Ghi outbox cùng transaction DB với nghiệp vụ → at-least-once delivery đảm bảo.
- `app/worker.py::dispatch_outbox` pubblic các dòng chưa publish, đánh dấu `published_at`.
- `app/services/kafka_publisher.py::KafkaOutboxPublisher` gửi Kafka (development without Kafka = best-effort, không làm hỏng request).

Vị trí: `app/models/activity.py`, `app/services/kafka_publisher.py`, `app/worker.py`.

### 2.4 Saga Orchestration + bù trừ (Compensating Transaction)

- **Orchestrator tập trung** (theo 02/05 §4.1, bắt buộc trong banking): `SagaOrchestrator` lưu trạng thái saga trong DB, gửi lệnh rõ ràng tới từng bước.
- Mỗi bước có `action_fn` và `compensate_fn`. Nếu bước k thất bại, orchestrator chạy bù trừ cho các bước k-1 … 1 theo thứ tự ngược lại.
- `saga_id` là idempotency key: chạy lại saga đã hoàn thành không xử lý lại.
- Mẫu TCC (Try–Confirm–Cancel): Try (phong tỏa số dư), Confirm (trừ nguồn + cộng đích + giải tỏa), Cancel (hủy phong tỏa).
- Vị trí mới: `app/models/saga.py`, `app/services/saga.py`, migration `035_banking_patterns.py`.

### 2.5 Khóa đồng thời tài chính (Concurrency Control)

Hai lớp bảo vệ số dư / tồn kho trước xung đột truy cập cùng thời điểm:

- **Pessimistic:** `SELECT ... FOR UPDATE` trên dòng `inv_balances` trong transaction, chặn các luồng khác đọc/ghi cùng dòng cho đến khi commit.
- **Optimistic:** cột `version` trên `inv_balances`; `UPDATE ... SET quantity = ..., version = version + 1 WHERE version = :expected_version`; nếu rowcount = 0 ném `ConcurrencyConflict`.
- `reserve_balance` / `commit_reservation` / `release_reservation` dùng cột `reserved_quantity` hiện có (Reservation/Escrow pattern).

Vị trí mới: `app/services/concurrency.py`.

### 2.6 Audit trail hash-chain bất biến

- Bảng `audit_events` hiện có guard append-only (chặn UPDATE/DELETE qua SQLAlchemy event listener).
- Bổ sung cột `previous_hash`, `chain_hash`, `hash_seq`: mỗi sự kiện mới ghi `previous_hash = chain_hash của sự kiện trước cùng subject`, tính `chain_hash = SHA256(previous_hash || action || subject || payload_hash || occurred_at || hash_seq)`.
- `verify_chain(subject)` tính lại toàn chuỗi từ sự kiện đầu, so sánh `chain_hash` lưu trữ; trả False/ném lỗi nếu phát hiện biến đổi bất kỳ nút nào.
- Vị trí mới: `app/services/audit_chain.py`, cột hash-chain trong migration `035_banking_patterns.py`.

---

## 3. Trạng thái máy Saga

```
PENDING  --(bắt đầu)-->  RUNNING  --(bước i thành công)-->  RUNNING (bước i+1)
                              │
                              └─(bước k thất bại)-->  COMPENSATING --(bù trừ xong)--> COMPENSATED
RUNNING --(tất cả bước thành công)--> COMPLETED
```

Mỗi bước saga lưu trạng thái trong `saga_steps` (PENDING / DONE / FAILED / COMPENSATED). Bù trừ chỉ chạy cho bước có trạng thái `DONE` (idempotent, không bù trừ 2 lần).

---

## 4. Cách chạy local độc lập

```bash
# 1. Khởi động PostgreSQL test cục bộ + alembic + seed + chạy toàn bộ test (bao gồm test banking mới)
make test-backend

# 2. Chạy riêng các test banking mới (pure-unit, không cần DB nếu được tách)
cd backend && pytest tests/test_banking_*.py -q

# 3. Lint (ruff 0.17.0, pin theo CI)
backend/.venv/bin/python -m ruff check backend/
```

Toàn bộ chạy trên máy local, không gọi dịch vụ đám mây bên ngoài (thỏa R3).
