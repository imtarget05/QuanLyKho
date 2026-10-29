# QUANLYKHO — P0/P1 SECURITY & ATOMICITY COMPLETION PLAN

> **Mục tiêu:** Đóng tất cả khoảng trắng bảo mật (P0) và tính nhất quán nguyên tử (P1) còn thiếu trong dự án QuanLyKho (Kho Trà Sữa / BankOps).
> **Nhóm mục tiêu:** OTP, Mock Google Login, SSE Auth, Reversal, Idempotency Store, Balance Locking, Parity Legacy Worker, Multi-replica SSE.
> **Ngôn ngữ:** Tiếng Việt. Tất cả task là một PR reviewable; test + migration + contract là phần của task, không dồn cuối kỳ.

---

## 1. TÌNH HÌNH HIỆN TẠI (BASELINE)

| Mục | State hiện tại (2026-10-28) | Gap cần đóng |
|-----|---------------------------|--------------|
| **Backend** | FastAPI + SQLAlchemy 2.x + Alembic (024 head) + Postgres 16. 387 backend tests xanh. | — |
| **Frontend** | Flutter 3.4+, 180 tests xanh, `flutter analyze` 0 issue. | — |
| **OTP** | Có `generate_password_reset_otp()` / `verify_password_reset_otp()` (in-memory `_password_reset_otps`), endpoint `/auth/forgot-password`, `/auth/reset-password`. OTP trả trong response chỉ ở demo mode. | Chưa bền vững (mất khi restart), chưa có OTP cho login (2FA), chưa có rate-limit OTP, chưa có bảng OTP durable, chưa có resend tracking. |
| **Mock Google Login** | Có `auth_google.py`, hỗ trợ token `mock-google-token:...` gated bởi `demo_mode`. Test `test_google_auth.py` xanh. Frontend `auth_service.dart` + `login_screen.dart` có nút Google mock (chỉ `kDebugMode`). | Mock cần hardening, tách biệt rõ luồng mock vs production, config client ID qua env, không chấp nhận mock ở release. |
| **SSE Auth** | Có `/events/stream`, `/activity/stream`, `/approvals/stream` đều yêu Bearer token + capability (`activity:view`/`audit:view`). Đọc từ bảng `outbox_events` (DB-shared → chạy được qua replica). | `ApprovalEventBus` là in-memory per-process. Stream chính `/events/stream` chưa dùng event bus fan-out. Cần Redis backplane cho multi-replica. |
| **Reversal** | Có endpoint `POST /cash-sim/requests/{id}/reverse`, tạo journal mới đảo debit/credit, lock balance `FOR UPDATE`, audit + outbox. | Chưa có workflow duyệt reversal, chưa kiểm tra idempotency reversal, chưa có reversal cho kho (inventory). |
| **Idempotency Store** | Có `app/services/idempotency.py` + model `IdempotencyKey` + migration `027_idempotency_keys`. Durable store + in-memory fast path. Test `test_idempotency_durable.py` xanh. | Chưa áp dụng đầy đủ cho mọi endpoint ghi, chưa có job dọn TTL, chưa có scope granular. |
| **Balance Locking** | Có `_balance_for_box(db, cashbox_id, for_update=True)` trong cash_sim (`SELECT ... FOR UPDATE`). | Chưa có lock cho `inv_balances` (kho), chưa có thứ tự lock khóa cố định tránh deadlock, chưa test tranh chấp đồng thời. |
| **Parity Legacy Worker** | Có `app/worker.py`: job lease `FOR UPDATE SKIP LOCKED`, outbox dispatch, retry state. Test `test_worker_jobs.py` xanh. | Chưa có spec hành vi legacy để so sánh parity, chưa cover các edge case (dead-letter, poison pill, overlapping lease). |
| **Multi-replica SSE** | `ApprovalEventBus` đã có skeleton Redis Pub/Sub (`approval_events.py`) nhưng chưa được kích hoạt đầy đủ. SSE chính đọc DB (shared → OK qua replica). | Chưa có cross-replica event visibility cho stream chính, chưa xử lý connection affinity, Last-Event-ID reconnection giữa các replica. |

---

## 2. MÔ HÌNH ƯU TIÊN

- **P0:** Bảo mật trực tiếp (OTP, auth, SSE auth, idempotency, balance locking, reversal atomicity) — phải xanh trước demo/release.
- **P1:** Khả năng vận hành cao (multi-replica SSE, worker parity, mock google production-gating) — hoàn thiện MVP.
- **P2:** Tối ưu, observability, cleanup (bỏ trong plan này, giao sang backlog riêng).

Mỗi task có: **ID**, **tên**, **files liên quan**, **interfaces**, **các bước**, **verification** (test/lệnh chạy được), **Definition of Done (DoD)**.

## 3. PHASE 0 — CHUẨN BỊ & ĐIỀU KIỆN TIÊN QUYẾT

**Mục tiêu:** Xác định acceptance criteria, chuẩn bị môi trường test, tạo branch feature, đồng bộ docs trước khi viết code.

### Task P0-0: Tạo branch feature + cơ sở hạ tầng test
- **Files:** `git branch feat/p0-p1-security-atomicity`
- **Steps:**
  1. Tạo branch `feat/p0-p1-security-atomicity` từ `main`.
  2. Khởi động Postgres test isolated (docker-compose test) cho backend.
  3. Confirm `ruff check backend/` 0.17.0 → 0 lỗi, `pytest backend/tests` baseline xanh.
- **DoD:** Branch sẵn sàng, CI-local pass, không có secret hardcode (`scripts/check_no_secrets.py` pass).

### Task P0-1: Viết Acceptance Criteria (AC) cho từng mục 8
- **Files:** `docs/P0_P1_SECURITY_ATOMICITY_AC.md` (mới)
- **Steps:** Ghi AC testable cho OTP, Google mock, SSE auth, reversal, idempotency, balance lock, worker parity, multi-replica SSE.
- **DoD:** Mỗi AC có input/expected output/lệnh verify, được review.

---
## 4. PHASE 1 — OTP: ĐƠN LẦN DÙNG BẢO MẬT

**Mục tiêu:** OTP phải bền vững, không lộ mã, có thời gian sống, có rate-limit, hỗ trợ login (2FA) và password reset.

### Task P1-1: Tạo bảng `otp_codes` durable + migration
- **Files:** `backend/alembic/versions/031_otp_codes.py` (mới), `backend/app/models/otp.py` (mới)
- **Interfaces:** Bảng `otp_codes(id, username, code_hash, purpose, expires_at, consumed_at, attempts, channel)`; unique username+purpose chưa consumed.
- **Steps:**
  1. Tạo migration Alembic `031_otp_codes` với bảng `otp_codes`.
  2. Tạo ORM model `OtpCode` trong `app/models/otp.py`.
  3. `alembic upgrade head` trên DB test isolated → bảng tồn tại.
- **DoD:** Migration upgrade/downgrade OK, model import không lỗi.

### Task P1-2: Dịch vụ OTP durable (tạo, verify, consume, resend, rate-limit)
- **Files:** `backend/app/services/otp.py` (mới)
- **Interfaces:** `create_otp(username, purpose, channel, ttl)`, `verify_otp(username, code, purpose)` → consume once, `can_resend(username)`, `rate_limit_otp(username)`.
- **Steps:**
  1. Triển khai lưu OTP vào DB (hash bcrypt), không lưu plaintext.
  2. TTL mặc định 900s (15p), attempts tối đa 3, khóa tạm 15p nếu quá attempts.
  3. Rate-limit gửi OTP: tối đa 5 lần/15p theo username+IP (dùng Redis nếu có, fallback RAM).
  4. `verify_otp` đánh dấu `consumed_at`, không cho verify lại.
- **DoD:** Unit test cover: tạo+verify thành công, verify sai 3 lần → khóa, resend quá hạn → 429, OTP hết hạn → verify fail, OTP đã dùng → không verify lại.

### Task P1-3: Endpoint OTP gửi mã (forgot-password / login-2FA)
- **Files:** `backend/app/api/routes/auth.py` (sửa)
- **Interfaces:** `POST /auth/otp/send`, `POST /auth/otp/verify`, đầu vào `{username, purpose, channel?}`.
- **Steps:**
  1. Endpoint gửi OTP (email trong demo, in-memory/SMTP stub).
  2. Endpoint verify OTP, trả về `otp_verified_token` (JWT ngắn hạn, 5p) cho bước tiếp theo (reset mật khẩu / xác nhận login).
  3. Không trả OTP trong response ngoài demo mode (`settings.is_demo_mode`).
- **DoD:** Integration test qua TestClient: gửi OTP → verify đúng → nhận token; verify sai → 400; gửi quá nhiều → 429.

### Task P1-4: Frontend OTP UI (forgot password + login 2FA)
- **Files:** `frontend/lib/src/features/auth/widgets/forgot_password_dialog.dart` (sửa), `frontend/lib/src/features/auth/widgets/otp_verify_dialog.dart` (mới), `frontend/lib/src/features/auth/auth_service.dart` (sửa)
- **Steps:**
  1. Thêm hàm `sendOtp`, `verifyOtp` vào `AuthService`.
  2. UI nhập OTP 6 chữ số, hiển thị countdown, nút "Gửi lại mã".
  3. Kết nối với endpoint `/auth/otp/send`, `/auth/otp/verify`.
- **DoD:** `flutter analyze` 0 issue; widget test OTP dialog pass.

## 5. PHASE 2 — MOCK GOOGLE LOGIN: ĐĂNG NHẬP SSO GIẢ LẬP

**Mục tiêu:** Mock Google login chỉ hoạt động trong chế độ phát triển/demo, không bao giờ chấp nhận ở production, tách biệt rõ luồng mock vs thực.

### Task P2-1: Hardening mock Google token validation
- **Files:** `backend/app/api/routes/auth_google.py` (sửa), `backend/app/config.py` (sửa)
- **Interfaces:** Thêm cờ `google_mock_enabled` (chỉ bật khi `is_demo_mode`), danh sách audience mock được cấu hình.
- **Steps:**
  1. Token `mock-google-token:...` chỉ được nhận khi `settings.is_demo_mode` = True, khác đó → 401 `GOOGLE_TOKEN_INVALID`.
  2. Mock token không được tạo user có role ngoài `staff` (trừ admin_email được cấu hình).
  3. Thêm log bảo mật khi nhận mock token ngoài demo mode.
- **DoD:** `test_google_auth.py` xanh; thêm test `test_google_mock_rejected_in_production_mode`.

### Task P2-2: Frontend Google Sign-In production-gating
- **Files:** `frontend/lib/src/features/auth/auth_service.dart` (sửa), `frontend/lib/src/features/auth/login_screen.dart` (sửa)
- **Steps:**
  1. Nút Google mock chỉ hiển thị khi `kDebugMode` (hoặc `--dart-define=ALLOW_GOOGLE_MOCK=true`).
  2. Prod/release không bao giờ gọi endpoint `/auth/google` với token `mock-`.
  3. Hiển thị thông báo rõ ràng khi ở chế độ mock.
- **DoD:** `flutter analyze` 0 issue; không có mock token pathways ở release build.

## 6. PHASE 3 — SSE AUTH: XÁC THỰC STREAM THỜI GIAN THỰC

**Mục tiêu:** Mọi kết nối SSE phải có token hợp lệ, capability phù hợp, và không lộ token qua URL/query string.

### Task P3-1: Đảm bảo auth trên tất cả endpoint SSE
- **Files:** `backend/app/api/routes/activity.py` (sửa), `backend/app/api/routes/approvals.py` (sửa)
- **Interfaces:** `/events/stream`, `/activity/stream`, `/approvals/stream` đều yêu `Authorization: Bearer` + capability.
- **Steps:**
  1. Review lại tất cả 3 endpoint SSE, đảm bảo không có endpoint nào bỏ qua auth.
  2. Token lấy từ header `Authorization`, KHÔNG từ query param `token` (tránh lộ token trong log proxy).
  3. Nếu token hết hạn trong khi stream đang mở → gửi frame `reauth_required` và đóng stream.
- **DoD:** Test `GET /api/v1/events/stream` không token → 401; có token sai capability → 403.

### Task P3-2: SSE reconnection với Last-Event-ID + cursor
- **Files:** `backend/app/api/routes/activity.py` (sửa)
- **Steps:**
  1. Hỗ trợ header `Last-Event-ID` đồng thời với query `cursor`.
  2. Nếu cursor quá cũ/không xác định → gửi `resync_required`, client tải lại REST.
  3. Heartbeat định kỳ giữ kết nối không bị idle-timeout.
- **DoD:** Test reconnect với Last-Event-ID nhận được sự kiện sau cursor; cursor cũ → `resync_required`.

## 7. PHASE 4 — REVERSAL: ĐẢO GIAO DỊCH NGUYÊN TỰ

**Mục tiêu:** Reversal phải tạo journal mới (không sửa entry cũ), có phê duyệt riêng, đủ số dư, idempotent, áp dụng cả tiền và kho.

### Task P4-1: Reversal cash đã có — thêm workflow duyệt + idempotency
- **Files:** `backend/app/api/routes/cash_sim.py` (sửa, phần reverse)
- **Steps:**
  1. Reversal phiếu `payment` (giảm quỹ) → đảo tạo `receipt` cần quyền `cash:post_adjustment` + đủ số dư.
  2. Reversal phiếu `receipt` (tăng quỹ) → đảo tạo `payment` cần kiểm tra số dư sau khi đảo không âm.
  3. Thêm `Idempotency-Key` cho reversal endpoint (replay cùng key → trả kết quả cũ).
  4. Reversal cần duyệt (maker ≠ checker) nếu amount vượt ngưỡng (dùng `verify_supervisor_pin`).
- **DoD:** Test reversal thành công, reversal thiếu số dư → 409, reversal idempotent, reversal cần duyệt cao niveau.

### Task P4-2: Reversal cho kho (inventory movement reversal)
- **Files:** `backend/app/api/routes/inventory.py` (mới endpoint), `backend/app/services/inventory.py` (mới)
- **Steps:**
  1. Endpoint `POST /inventory/movements/{id}/reverse` tạo movement mới đảo chiều (signed quantity ngược).
  2. Cập nhật `inv_balances` transactionally trong cùng transaction.
  3. Lock balance theo thứ tự item/location cố định tránh deadlock.
  4. Yêu cầu `inventory:approve_request` + idempotency key.
- **DoD:** Test reversal movement kho, balance đúng sau đảo, concurrent reversal không tạo movement trùng.

## 8. PHASE 5 — IDEMPOTENCY STORE: KHO KHÓA IDEMPOTENCY BỀN VŨNG

**Mục tiêu:** Idempotency-Key phải bền vững qua restart, dùng chung nhiều replica, áp dụng cho mọi endpoint ghi.

### Task P5-1: Mở rộng idempotency cho tất cả endpoint ghi quan trọng
- **Files:** `backend/app/api/routes/cash_sim.py`, `backend/app/api/routes/inventory.py`, `backend/app/api/routes/approvals.py`, `backend/app/api/routes/reconciliations.py` (sửa)
- **Steps:**
  1. Mọi endpoint POST/PUT tạo/sửa trạng thái phải bắt buộc header `Idempotency-Key`.
  2. Sử dụng `claim_key` trong cùng transaction với business write.
  3. `store_response` sau commit thành công.
  4. Replay cùng key + cùng payload → trả response cũ (không tạo nghiệp vụ lần 2).
- **DoD:** Test các endpoint ghi nhận `Idempotency-Key`, replay không tạo bản ghi mới.

### Task P5-2: Job dọn bản ghi idempotency hết hạn (TTL cleanup)
- **Files:** `backend/app/worker.py` (sửa), `backend/app/services/idempotency.py` (sửa)
- **Steps:**
  1. Thêm job loại `idempotency_purge` xóa bản ghi `expires_at < now`.
  2. Chạy định kỳ (ví dụ mỗi 1 giờ), batch 1000 bản ghi.
  3. Giữ lại bản ghi trong cửa sổ retention (`idempotency_key_retention_hours`, mặc định 24h).
- **DoD:** Test job purge xóa bản ghi hết hạn, giữ bản ghi còn hiệu lực.

## 9. PHASE 6 — BALANCE LOCKING: KHÓA SỐ DƯ PHÒNG TRÀN

**Mục tiêu:** Mọi thay đổi số dú (tiền và kho) phải lock row trong transaction, tránh race condition và deadlock.

### Task P6-1: Balance locking cho kho (`inv_balances`)
- **Files:** `backend/app/api/routes/inventory.py` (sửa), `backend/app/domain/inventory.py` (sửa)
- **Steps:**
  1. Hàm `_lock_balance(db, location_id, item_id, for_update=True)` dùng `SELECT ... FOR UPDATE`.
  2. Khi posting movement, lock balance trước khi thay đổi quantity.
  3. Thứ tự lock khóa cố định: sắp xếp theo `(location_id, item_id)` trước khi lock nhiều balance (transfer 2 kho).
- **DoD:** Test concurrent posting 2 movements cùng item không bị lost update; transfer 2 kho không deadlock.

### Task P6-2: Test tranh chấp đồng thời (concurrency test)
- **Files:** `backend/tests/test_balance_locking.py` (mới)
- **Steps:**
  1. Viết test launch N coroutine cùng post movement vào cùng balance.
  2. Assert balance cuối = tổng chính xác, không có bản ghi bị bỏ lỡ.
  3. Test reversal + approve cùng lúc không tạo journal trùng.
- **DoD:** Concurrency test pass với 50+ job đồng thời.

## 10. PHASE 7 — PARITY LEGACY WORKER: ĐƠN GIÁ CÔNG VIỆC LEGACY

**Mục tiêu:** Worker hiện tại phải hành vi nhất quán với spec legacy (job lease, outbox, retry, dead-letter).

### Task P7-1: Ghi spec hành vi legacy worker
- **Files:** `docs/09-integrations-jobs.md` (bổ sung), `backend/docs/ADR_WORKER_PARITY.md` (mới)
- **Steps:**
  1. Ghi lại spec: lease `FOR UPDATE SKIP LOCKED`, retry tối đa 5 lần, outbox dispatch riêng, abandoned lease recovery.
  2. Xác định row "legacy" cần giữ tính nhất quán (ví dụ: job type `sla_reminder`, `reconciliation_run`).
- **DoD:** Spec tài liệu được review, không mâu thuẫn với code hiện tại.

### Task P7-2: Test parity worker (dead-letter, poison pill, overlapping lease)
- **Files:** `backend/tests/test_worker_parity.py` (mới)
- **Steps:**
  1. Test job fail quá MAX_RETRY → chuyển trạng thái `dead_letter` (không lặp vô hạn).
  2. Test poison pill (job luôn lỗi) không làm treo worker loop.
  3. Test 2 worker process claim cùng lúc → chỉ 1 process nhận job (SKIP LOCKED).
  4. Test lease hết hạn → job khác có thể reclaim sau LEASE_SECONDS.
- **DoD:** Tất cả test parity xanh, worker ổn định dưới áp lực.

## 11. PHASE 8 — MULTI-REPLICA SSE: SSE NHIỀU BẢN SAO

**Mục tiêu:** Sự kiện SSE phải được nhìn thấy bởi các client kết nối đến bất kỳ replica nào, không bị mất khi replica xử lý sự kiện khác replica client đang lắng nghe.

### Task P8-1: Kích hoạt Redis backplane cho ApprovalEventBus
- **Files:** `backend/app/services/approval_events.py` (sửa), `backend/app/main.py` (sửa)
- **Steps:**
  1. Khi `settings.redis_url` có cấu hình, `ApprovalEventBus` tự kết nối Redis, publish/subscribe kênh `approval:events`.
  2. Sự kiện publish từ replica A được forward đến listener của replica B qua Redis.
  3. Filter sự kiện gốc từ chính instance đó (`origin` check) tránh lặp lại local.
  4. Fallback về in-memory nếu Redis không có/lỗi (graceful degradation).
- **DoD:** Test với 2 instance mock (hoặc Redis testcontainer) → event publish từ instance A đến subscriber của instance B.

### Task P8-2: Fan-out SSE stream chính (`/events/stream`) qua Redis/Outbox-shared
- **Files:** `backend/app/api/routes/activity.py` (sửa), `backend/app/services/approval_events.py` (sửa)
- **Steps:**
  1. Stream chính `/events/stream` đăng ký vào `ApprovalEventBus` (hoặc bus riêng `sse:events`) để nhận sự kiện từ các replica khác.
  2. Kết hợp với đọc `outbox_events` (DB-shared) để không bỏ sót sự kiện cũ.
  3. Client reconnect với `Last-Event-ID` → replay từ outbox table (source of truth) + fan-out từ bus cho sự kiện mới.
- **DoD:** Test multi-replica (giả lập 2 FastAPI instance qua Redis) → client kết nối replica B vẫn nhận sự kiện được tạo trên replica A.

### Task P8-3: Frontend SSE client multi-replica resilient
- **Files:** `frontend/lib/src/data/repositories/http_bankops_repository.dart` (sửa)
- **Steps:**
  1. SSE client tự reconnect sau ngắt kết nối (backoff 3s → 5s → 10s).
  2. Gửi `Last-Event-ID` khi reconnect để không bỏ sự kiện.
  3. Xử lý frame `resync_required` → gọi REST sync lại trạng thái.
- **DoD:** Widget test SSE reconnect, Last-Event-ID được gửi.

## 12. PHASE 9 — FRONTEND: ĐỒNG BỘ FLUTTER (OTP UI, GOOGLE, SSE, REVERSAL)

**Mục tiêu:** Flutter frontend hỗ trợ đầy đủ luồng P0/P1 phía client.

### Task F9-1: AuthService thêm OTP + Google mock + SSE multi-replica
- **Files:** `frontend/lib/src/features/auth/auth_service.dart` (sửa), `frontend/lib/src/data/repositories/http_bankops_repository.dart` (sửa)
- **Steps:**
  1. Thêm `sendOtp`, `verifyOtp` methods.
  2. Google Sign-In: thực production flow + mock debug-only.
  3. SSE: hỗ trợ `Last-Event-ID`, reconnect, `resync_required`.
- **DoD:** `flutter analyze` 0 issue, `flutter test` xanh.

### Task F9-2: UI Reversal (đảo giao dịch) + OTP dialog
- **Files:** `frontend/lib/src/features/cash/cash_screen.dart` (sửa), `frontend/lib/src/features/auth/widgets/otp_verify_dialog.dart` (mới), `frontend/lib/src/features/auth/widgets/forgot_password_dialog.dart` (sửa)
- **Steps:**
  1. Nút "Đảo giao dịch" trên chi tiết phiếu quỹ (cần quyền duyệt, nhập lý do, xác nhận OTP nếu cao niveau).
  2. Dialog nhập OTP khi quên mật khẩu / xác nhận nhạy cảm.
- **DoD:** UI hiển thị đúng, test widget pass.

## 13. PHASE 10 — TEST, QA, RELEASE GATE

**Mục tiêu:** Chạy toàn bộ suite, đảm bảo không regression, sẵn sàng deploy.

### Task Q10-1: Backend full test suite
- **Files:** `backend/tests/` (mới + sửa)
- **Steps:**
  1. Chạy `pytest backend/tests` trên Postgres isolated → 0 failed.
  2. Bổ sung test cho OTP, Google mock, SSE auth, reversal, idempotency, balance lock, worker parity, multi-replica SSE.
  3. `ruff check backend/` 0.17.0 → 0 lỗi.
- **DoD:** Tất cả test xanh, cobertura P0/P1 ≥ 90%.

### Task Q10-2: Flutter full test suite
- **Files:** `frontend/test/` (mới + sửa)
- **Steps:**
  1. `flutter analyze` → 0 issue.
  2. `flutter test` → 100% xanh (bao gồm test OTP dialog, Google mock, SSE reconnect, reversal UI).
- **DoD:** Flutter xanh 100%.

### Task Q10-3: E2E smoke test + secret guard
- **Files:** `scripts/smoke_test.py`, `scripts/check_no_secrets.py`
- **Steps:**
  1. Chạy smoke test E2E (login → tạo phiếu → duyệt → reversal → SSE nhận sự kiện).
  2. `check_no_secrets.py` → PASS (không có hardcoded secret/token).
  3. Alembic `upgrade head` trên DB trống → 42 bảng + bảng mới (`otp_codes`).
- **DoD:** E2E pass, secret guard pass, migration sạch.

## 14. DỰ KIẾN THỜI GIAN & NHÂN LỰC

| Phase | Thời gian dự kiến | Nhiệm vụ chính |
|-------|------------------|----------------|
| Phase 0 | 1 ngày | Branch, AC, môi trường test |
| Phase 1 (OTP) | 2-3 ngày | Bảng OTP, dịch vụ, endpoint, frontend UI |
| Phase 2 (Google mock) | 1 ngày | Hardening mock, production-gating |
| Phase 3 (SSE auth) | 1 ngày | Auth mọi stream, reconnection |
| Phase 4 (Reversal) | 2 ngày | Cash reversal duyệt, kho reversal, idempotency |
| Phase 5 (Idempotency) | 1-2 ngày | Mở rộng coverage, TTL purge job |
| Phase 6 (Balance lock) | 1-2 ngày | Lock inv_balances, concurrency test |
| Phase 7 (Worker parity) | 1-2 ngày | Spec, parity test, dead-letter |
| Phase 8 (Multi-replica SSE) | 2-3 ngày | Redis backplane, fan-out, frontend resilient |
| Phase 9 (Frontend) | 2 ngày | AuthService, UI reversal/OTP |
| Phase 10 (QA/Release) | 2 ngày | Full test, E2E, secret guard |
| **Tổng cộng** | **~15-18 ngày** | 1-2 dev backend + 1 dev frontend |

## 15. DEFINITION OF DONE (DỰ ÁN HOÀN TOÀN)

- [ ] Mọi endpoint ghi bắt buộc `Idempotency-Key`, replay không tạo nghiệp vụ trùng.
- [ ] OTP bền vững (DB), có TTL, rate-limit, không trả mã trong response ngoài demo.
- [ ] Mock Google chỉ hoạt động ở `is_demo_mode` / `kDebugMode`, bị chặn ở production.
- [ ] Tất cả endpoint SSE yêu Bearer token + capability, hỗ trợ `Last-Event-ID` reconnect.
- [ ] Reversal tạo journal mới (không sửa cũ), cần duyệt, đủ số dư, idempotent.
- [ ] `inv_balances` và `cash_balances` đều lock `FOR UPDATE`, thứ tự lock cố định, không deadlock.
- [ ] Worker pass test parity: dead-letter, poison pill, SKIP LOCKED, lease expiry.
- [ ] Multi-replica SSE: sự kiện từ replica A đến được client kết nối replica B (qua Redis backplane).
- [ ] Backend `pytest` 100% xanh, `ruff` 0 lỗi, Alembic upgrade head OK.
- [ ] Flutter `flutter analyze` 0 issue, `flutter test` 100% xanh.
- [ ] `scripts/check_no_secrets.py` PASS, không có hardcoded token/secret.
- [ ] E2E smoke test pass: login → tạo phiếu → duyệt → reversal → SSE nhận event.

## 16. RỦI RO & GIẢI PHÁP

| Rủi ro | Mức | Giải pháp |
|--------|-----|-----------|
| OTP in-memory mất khi restart | P0 | Lưu vào bảng `otp_codes` durable (Phase 1). |
| Mock Google rò rỉ vào production | P0 | Gate cứng bởi `settings.is_demo_mode`, test đổi mode. |
| SSE event bị mất giữa các replica | P1 | Redis backplane + DB outbox làm source of truth (Phase 8). |
| Deadlock khi lock nhiều balance | P1 | Thứ tự lock khóa cố định `(location_id, item_id)` (Phase 6). |
| Worker treo do poison pill | P1 | Giới hạn retry, chuyển dead_letter, isolate lỗi job (Phase 7). |
| Không có Flutter SDK trên một số máy | P2 | Ghi `BLOCKED: no SDK`, không claim pass (theo quy ước repo). |

## 17. CÁCH SỬ DỤNG PLAN NÀY

1. Mỗi task được giao **một lần duy nhất** cho một agent/dev.
2. Trước khi bắt đầu task: đọc lại file liên quan, nêu files thay đổi, migration, API diff, test target.
3. Sau khi hoàn thành task: chạy verify (test/lệnh), commit PR, cập nhật status trong plan này.
4. Nếu cần thay đổi invariant/hợp đồng API: cập nhật docs trước hoặc cùng PR, yêu cầu review.

---