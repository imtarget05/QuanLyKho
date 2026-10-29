# Acceptance Criteria — P0/P1 Security & Atomicity (QuanLyKho)

> Mục tiêu: Mỗi mục dưới đây phải có ít nhất 1 test case chạy được và pass trước khi coi là ĐÓNG.
> Môi trường verify: Postgres 16 isolated (testcontainers/docker-compose.test.yml), backend `pytest`, frontend `flutter test`.

## 1. OTP — Đơn lần dùng bảo mật (P0)

| AC ID | Yêu cầu | Input | Expected Output | Lệnh verify |
|-------|---------|-------|-----------------|-------------|
| OTP-01 | Tạo OTP lưu durable vào DB (không mất khi restart) | `POST /auth/otp/send {username, purpose: "password_reset"}` | Trả `message`, `expires_in_seconds: 900`, không trả mã OTP ngoài demo mode | `pytest backend/tests/test_otp.py::test_otp_durable_survives_restart` |
| OTP-02 | Verify OTP thành công, đánh dấu consumed (không verify lại được) | `POST /auth/otp/verify {username, otp, purpose}` | Trả `otp_verified_token` (JWT, 5p); gọi lại cùng OTP → 400 | `pytest backend/tests/test_otp.py::test_otp_consume_once` |
| OTP-03 | Verify OTP sai 3 lần → khóa tạm 15p | Gửi OTP sai 3 lần | Lần thứ 4 trở đi → 423/429 `OTP_LOCKED` | `pytest backend/tests/test_otp.py::test_otp_lock_after_3_failures` |
| OTP-04 | OTP hết hạn (TTL 900s) → verify fail | Tạo OTP, mock thời gian > 900s, verify | 400 `OTP_EXPIRED` | `pytest backend/tests/test_otp.py::test_otp_expired` |
| OTP-05 | Rate-limit gửi OTP: tối đa 5 lần/15p theo username+IP | Gửi OTP 6 lần cùng username+IP | Lần thứ 6 → 429 `OTP_RATE_LIMITED` | `pytest backend/tests/test_otp.py::test_otp_rate_limit` |
| OTP-06 | Không trả OTP plaintext trong response ngoài demo mode | `POST /auth/otp/send` ở `APP_ENV=production` | Response không chứa trường `otp` | `pytest backend/tests/test_otp.py::test_otp_not_returned_in_prod` |
| OTP-07 | Frontend OTP dialog hiển thị countdown + nút gửi lại | Mở `OtpVerifyDialog` | Countdown 900s, nút "Gửi lại mã" bị disable trong 60s sau khi gửi | `flutter test frontend/test/otp_dialog_test.dart` |

**Files liên quan:** `backend/alembic/versions/031_otp_codes.py`, `backend/app/models/otp.py`, `backend/app/services/otp.py`, `backend/app/api/routes/auth.py`, `backend/tests/test_otp.py`, `frontend/lib/src/features/auth/widgets/otp_verify_dialog.dart`, `frontend/lib/src/features/auth/widgets/forgot_password_dialog.dart`, `frontend/lib/src/features/auth/auth_service.dart`.

## 2. Mock Google Login — chỉ ở demo/debug (P0)

| AC ID | Yêu cầu | Input | Expected Output | Lệnh verify |
|-------|---------|-------|-----------------|-------------|
| GOOG-01 | Token `mock-google-token:...` chỉ nhận ở `is_demo_mode` | `POST /auth/google {id_token: "mock-..."}` ở production | 401 `GOOGLE_TOKEN_INVALID` | `pytest backend/tests/test_google_auth.py::test_google_mock_rejected_in_production_mode` |
| GOOG-02 | Mock token tạo user role `staff` (không tự cấp approve) | `POST /auth/google {id_token: "mock-...:user@example.com"}` ở demo | User mới có role `staff`, không có `inventory_manager`/`approver` | `pytest backend/tests/test_google_auth.py::test_google_mock_staff_only` |
| GOOG-03 | Admin email được cấu hình có thể nhận role admin qua mock | `POST /auth/google {id_token: "mock-...:admin@example.com"}` | User có role `admin` nếu email trong `settings.admin_emails` | `pytest backend/tests/test_google_auth.py::test_google_mock_admin_email` |
| GOOG-04 | Frontend: nút Google mock chỉ hiển thị ở `kDebugMode` | Mở `LoginScreen` ở release/build release | Không có nút "Đăng nhập Google (mock)" | `flutter analyze` + kiểm tra source không có nút mock ở release |
| GOOG-05 | Frontend: thông báo rõ ràng ở chế độ mock | Mở `LoginScreen` ở debug | Hiển thị banner "Chế độ demo/mock — không dùng ở production" | Widget test |

**Files liên quan:** `backend/app/api/routes/auth_google.py`, `backend/app/config.py`, `backend/tests/test_google_auth.py`, `frontend/lib/src/features/auth/auth_service.dart`, `frontend/lib/src/features/auth/login_screen.dart`.

## 3. SSE Auth — Xác thực stream thời gian thực (P0)

| AC ID | Yêu cầu | Input | Expected Output | Lệnh verify |
|-------|---------|-------|-----------------|-------------|
| SSE-01 | Mọi endpoint SSE yêu Bearer token + capability | `GET /api/v1/events/stream` không token | 401 | `pytest backend/tests/test_sse_auth.py::test_sse_requires_auth` |
| SSE-02 | Token từ header `Authorization`, không từ query param | `GET /api/v1/events/stream?token=xxx` | 401 (token từ query bị bỏ qua) | `pytest backend/tests/test_sse_auth.py::test_sse_token_from_header_only` |
| SSE-03 | Token hết hạn trong stream → `reauth_required` + đóng | Kết nối SSE, hết hạn token | Gửi frame `event: reauth_required`, đóng stream | `pytest backend/tests/test_sse_auth.py::test_sse_reauth_required` |
| SSE-04 | Hỗ trợ `Last-Event-ID` header + query `cursor` | Kết nối với `Last-Event-ID: <uuid>` | Phát sự kiện sau cursor đó | `pytest backend/tests/test_sse_auth.py::test_sse_last_event_id` |
| SSE-05 | Cursor quá cũ → `resync_required` | `GET /events/stream?cursor=<cũ_qua_7_ngày>` | Gửi frame `event: resync_required` | `pytest backend/tests/test_sse_auth.py::test_sse_cursor_expired` |
| SSE-06 | Heartbeat định kỳ giữ kết nối | Kết nối SSE 30s không có sự kiện | Nhận frame `event: heartbeat` | `pytest backend/tests/test_sse_auth.py::test_sse_heartbeat` |

## 4. Reversal — Đảo giao dịch nguyên tử (P0)

| AC ID | Yêu cầu | Input | Expected Output | Lệnh verify |
|-------|---------|-------|-----------------|-------------|
| REV-01 | Reversal tạo journal mới, không sửa entry cũ | `POST /cash-sim/requests/{id}/reverse` | Tạo `CashJournal` mới có `reversal_of = original_journal.id` | `pytest backend/tests/test_cash_reversal.py::test_reversal_creates_new_journal` |
| REV-02 | Reversal cần đủ số dư (đảo phiếu thu) | Đảo phiếu `receipt` khi số dư không đủ | 409 `INSUFFICIENT_SIM_CASH` | `pytest backend/tests/test_cash_reversal.py::test_reversal_insufficient_cash` |
| REV-03 | Reversal idempotent theo `Idempotency-Key` | Gọi reverse 2 lần cùng key | Trả kết quả cũ, không tạo journal thứ 2 | `pytest backend/tests/test_cash_reversal.py::test_reversal_idempotent` |
| REV-04 | Reversal cao niveau cần duyệt (maker ≠ checker + PIN) | Reversal amount > ngưỡng | Yêu cầu `cash:post_adjustment` + supervisor pin | `pytest backend/tests/test_cash_reversal.py::test_reversal_requires_approval` |
| REV-05 | Reversal kho: tạo movement mới đảo signed quantity | `POST /inventory/movements/{id}/reverse` | Tạo `Movement` mới với `quantity_signed` ngược, cập nhật `inv_balances` | `pytest backend/tests/test_inventory_reversal.py::test_inventory_reversal_updates_balance` |
| REV-06 | Reversal kho: lock balance theo thứ tự cố định (không deadlock) | 2 reversal cùng lúc trên 2 kho khác nhau | Không deadlock, balance chính xác | `pytest backend/tests/test_inventory_reversal.py::test_no_deadlock` |

**Files liên quan:** `backend/app/api/routes/activity.py`, `backend/app/api/routes/approvals.py`, `backend/tests/test_sse_auth.py` (mới), `backend/app/api/routes/cash_sim.py` (phần reverse), `backend/app/api/routes/inventory.py` (mới), `backend/app/services/inventory.py` (mới), `backend/tests/test_cash_reversal.py`, `backend/tests/test_inventory_reversal.py`.

## 5. Idempotency Store — Bền vững qua restart (P0)

| AC ID | Yêu cầu | Input | Expected Output | Lệnh verify |
|-------|---------|-------|-----------------|-------------|
| IDEM-01 | Mọi endpoint ghi bắt buộc `Idempotency-Key` | `POST /cash-sim/requests` không key | 422 `MISSING_IDEMPOTENCY_KEY` | `pytest backend/tests/test_idempotency_coverage.py` |
| IDEM-02 | Replay cùng key + cùng payload → trả response cũ | Gọi tạo cash request 2 lần cùng key | Trả response lần 1, không tạo bản ghi thứ 2 | `pytest backend/tests/test_idempotency_durable.py::test_replay_same_payload` |
| IDEM-03 | Cùng key + khác payload → 409 conflict | Gọi cùng key, payload khác | 409 `IDEMPOTENCY_KEY_REUSED` | `pytest backend/tests/test_idempotency_durable.py::test_conflict_different_payload` |
| IDEM-04 | Key tồn tại sau restart process | Lưu response, xóa `_store` in-memory | Vẫn replay được từ DB | `pytest backend/tests/test_idempotency_durable.py::test_survives_restart` |
| IDEM-05 | Job purge xóa bản ghi hết hạn (TTL 24h) | Chạy worker job `idempotency_purge` | Bản ghi `expires_at < now` bị xóa, còn lại được giữ | `pytest backend/tests/test_idempotency_purge.py` |

## 6. Balance Locking — Khóa số dư phòng tràn (P0)

| AC ID | Yêu cầu | Input | Expected Output | Lệnh verify |
|-------|---------|-------|-----------------|-------------|
| BAL-01 | `inv_balances` lock `FOR UPDATE` khi posting movement | POST movement kho | `SELECT ... FOR UPDATE` trên `inv_balances` | `pytest backend/tests/test_balance_locking.py::test_lock_inv_balance` |
| BAL-02 | Thứ tự lock cố định `(location_id, item_id)` tránh deadlock | Transfer giữa 2 kho cùng lúc | Không deadlock | `pytest backend/tests/test_balance_locking.py::test_no_deadlock_transfer` |
| BAL-03 | Concurrency: 50 coroutine post cùng 1 balance | Launch 50 job cùng balance | Balance cuối = tổng chính xác, không lost update | `pytest backend/tests/test_balance_locking.py::test_concurrent_posting` |
| BAL-04 | `cash_balances` đã lock `FOR UPDATE` (kiểm tra lại) | Approve cash request | `_balance_for_box(..., for_update=True)` được gọi | `pytest backend/tests/test_balance_locking.py::test_cash_balance_locked` |

**Files liên quan:** `backend/app/services/idempotency.py`, `backend/app/api/routes/cash_sim.py`, `backend/app/api/routes/inventory.py`, `backend/app/api/routes/approvals.py`, `backend/app/api/routes/reconciliations.py`, `backend/app/worker.py`, `backend/tests/test_idempotency_durable.py`, `backend/tests/test_idempotency_purge.py` (mới), `backend/app/api/routes/inventory.py`, `backend/app/domain/inventory.py`, `backend/app/api/routes/cash_sim.py`, `backend/tests/test_balance_locking.py` (mới).

## 7. Parity Legacy Worker — Đơn giáng công việc legacy (P1)

| AC ID | Yêu cầu | Input | Expected Output | Lệnh verify |
|-------|---------|-------|-----------------|-------------|
| WKR-01 | Job fail quá MAX_RETRY (5 lần) → `dead_letter` | Job luôn ném exception | Trạng thái job = `dead_letter`, không lặp vô hạn | `pytest backend/tests/test_worker_parity.py::test_dead_letter` |
| WKR-02 | Poison pill không treo worker loop | Job liên tục lỗi | Worker vẫn poll job khác bình thường | `pytest backend/tests/test_worker_parity.py::test_poison_pill` |
| WKR-03 | 2 worker claim cùng job → chỉ 1 nhận (SKIP LOCKED) | 2 process claim cùng lúc | Chỉ 1 process có `status = running` | `pytest backend/tests/test_worker_parity.py::test_skip_locked` |
| WKR-04 | Lease hết hạn → job khác có thể reclaim | Job `running`, `lease_until` quá hạn | Job khác có thể claim sau `LEASE_SECONDS` | `pytest backend/tests/test_worker_parity.py::test_lease_expiry_reclaim` |

## 8. Multi-replica SSE — Nhiều bản sao (P1)

| AC ID | Yêu cầu | Input | Expected Output | Lệnh verify |
|-------|---------|-------|-----------------|-------------|
| MR-01 | Redis backplane hoạt động cho `ApprovalEventBus` | Cấu hình `REDIS_URL`, publish từ replica A | Subscriber ở replica B nhận sự kiện | `pytest backend/tests/test_sse_multi_replica.py::test_redis_backplane` |
| MR-02 | Fallback in-memory nếu Redis lỗi | Redis không kết nối | `ApprovalEventBus` vẫn hoạt động in-memory | `pytest backend/tests/test_sse_multi_replica.py::test_redis_fallback` |
| MR-03 | Stream chính `/events/stream` nhận sự kiện từ replica khác | Tạo sự kiện trên replica A, client kết nối replica B | Client B nhận sự kiện qua SSE | `pytest backend/tests/test_sse_multi_replica.py::test_cross_replica_stream` |
| MR-04 | Frontend SSE reconnect với `Last-Event-ID` | Ngắt kết nối, kết nối lại | Gửi `Last-Event-ID`, không bỏ sự kiện | `flutter test frontend/test/sse_reconnect_test.dart` |
| MR-05 | Frontend xử lý `resync_required` → sync REST | Nhận frame `resync_required` | Gọi REST sync lại trạng thái | `flutter test frontend/test/sse_resync_test.dart` |

**Files liên quan:** `backend/app/worker.py`, `backend/tests/test_worker_parity.py` (mới), `docs/backend/ADR_WORKER_PARITY.md` (mới), `backend/app/services/approval_events.py`, `backend/app/main.py`, `backend/app/api/routes/activity.py`, `backend/tests/test_sse_multi_replica.py` (mới), `frontend/lib/src/data/repositories/http_bankops_repository.dart`, `frontend/test/sse_reconnect_test.dart` (mới), `frontend/test/sse_resync_test.dart` (mới).

---

## Cổng verify tổng thể (Definition of Done)

- [ ] `pytest backend/tests` → 0 failed (bao gồm tất cả test P0/P1 mới)
- [ ] `ruff check backend/` 0.17.0 → 0 lỗi
- [ ] `alembic upgrade head` trên DB trống → thành công, có bảng `otp_codes`
- [ ] `flutter analyze` → 0 issue
- [ ] `flutter test` → 100% xanh
- [ ] `scripts/check_no_secrets.py` → PASS
- [ ] E2E smoke: login → tạo phiếu → duyệt → reversal → SSE nhận event → PASS

---