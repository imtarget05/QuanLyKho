# TEST_COUNT_CORRECTION — Sửa sai số liệu kiểm thử (QA_REPORT.md)

## 1. Số liệu kiểm thử đúng (theo bằng chứng thực tế repo)

| Suite | Lệnh | Kết quả đúng (vòng 11, 15/10/2026) |
|---|---|---|
| Backend tests | `pytest -q` (DB QA `:5433`, `APP_ENV=test`) | **245 passed, 2 skipped, 0 failed** (+13 test mới) |
| Backend lint | `ruff check backend/` | **All checks passed!** (0 lỗi) |
| Flutter analyze | `flutter analyze` | **No issues found!** |
| Flutter tests | `flutter test` | **80/80 passed** (+11 test mới) |
| Secrets guard | `scripts/check_no_secrets.py` | **passed** |

Nguồn: `QA_REPORT.md` "## 11. Vòng 11" (cổng kiểm tra, dòng 603-612) + `docs/qa/06-deployment-validation.md` ("Bổ sung 2026-10-15 ~00:40Z", dòng 293-295).

Vòng 10 (14/10/2026): **232 passed, 1 skipped, 1 xfailed, 0 failed**; Flutter **69/69 passed**.
Nguồn: `QA_REPORT.md` "## 10. Vòng 10" (dòng 515-520).

## 2. Các con số KHÔNG khớp bằng chứng (đã bội chính)

| Con số bịClaim | Nguồn claim | Thực tế repo | Ghi chú |
|---|---|---|---|
| `932 PASS / 0 FAIL / 8 SKIP / 1 XFAIL` | Bảng tổng hợp cũ (không có tài liệu gốc hỗ trợ) | Tối đa quan sát được: **245 passed** (vòng 11) | Không có tài liệu nào trong repo ghi lại 932. Max observed = 245. |
| `350/350 Flutter PASS` | Bảng tổng hợp cũ | **80/80** (vòng 11), trước đó **69/69** (vòng 10) | Max observed = 80/80. Không có bằng chứng 350 ca Flutter. |
| `22 vị trí .with_for_update()` | Bảng tổng hợp cũ | **~36 call sites thực tế** | Đếm theo module sau (dưới đây). |

## 3. Đếm thực tế `.with_for_update()` (≈ 36 call sites)

| Module | Số call sites |
|---|---|
| `etl_engine` | 6 |
| `inventory` | 19 |
| `worker` | 4 |
| `commerce` | 5 |
| `cash_sim` | 2 |
| **Tổng** | **≈ 36** |

## 4. Vì con số claim sai

- Không có bản ghi kiểm thử nào trong repo (log CI, file kết quả pytest, báo cáo Flutter) ghi lại `932` hay `350/350`.
- Số lớn nhất có bằng chứng là `245 passed` (backend, vòng 11) và `80/80` (Flutter, vòng 11).
- `.with_for_update()` ~36 vị trí (không phải 22) — đếm thủ công trên 5 module nêu trên.

## 5. Các vấn đề P1/P2 còn lại (theo QA_REPORT)

Danh sách dưới được liệt kê theo QA_REPORT (các vấn đề P1/P2 chưa đóng). Lưu ý: một số mục đã được kiểm tra lại đối với mã nguồn hiện tại và có thể đã được xử lý phần lớn — đánh giá chi tiết xem phần 6.

### P1
1. **#8** CORS wildcard + credentials — `allow_credentials` kèm `allow_origins=["*"]` (rủi ro bảo mật).
2. **#9** Thiếu route refresh, logout revoke, rate-limit.
3. **#10** Thiếu Idempotency-Key, If-Match, maker-checker trên một số write endpoint.
4. **#11** Thiếu timestamptz, check-constraints, ledger double-entry (ràng buộc DB).
5. **#14e** Correlation ID middleware không bọc `send` cho header `X-Request-ID`.
6. **#14f** Error envelope `docs/06:44` (`{"error":{"code","message","request_id","details"}}`) chưa áp dụng toàn cục cho mọi loại lỗi.
7. **#14g** OpenAPI security scheme đánh dấu các đường dẫn public (cần `security: []` hoặc xóa security requirement trên public path).
8. **#6** Thiếu một số write endpoint (danh sách cụ thể tùy phiên bản QA_REPORT).

### P2
9. **#10** `alembic/env.py` không import `app.models` → autogenerate có thể bỏ qua model mới.
10. **#20** Thiếu file `alembic/script.py.mako` (template sinh migration).

## 6. Đánh giá lại nhanh đối với mã nguồn hiện tại (chỉ đọc)

| Vấn đề | File tham chiếu | Tình trạng hiện tại |
|---|---|---|
| CORS wildcard + credentials (P1 #8) | `backend/app/main.py:103-121` | `_allow_credentials = bool(_allowed_origins) and _allowed_origins != ["*"]` — credentials chỉ bật khi origins **không rỗng và khác `["*"]`**. Không bị kết hợp wildcard + credentials. |
| Error envelope toàn cục (P1 #14f) | `backend/app/main.py:144-280` | Đã có handler toàn cục: `request_id_mw` (145), `http_exception_envelope` (214), `validation_exception_envelope` (235), `unhandled_exception_envelope` (260), `register_error_handlers` (280). Tất cả render theo `{"error":{"code","message","request_id","details"}}` khớp `docs/06-api.md:49-51`. |
| Correlation ID bọc `send` (P1 #14e) | `backend/app/api/middleware/correlation.py:39-46` | **Đã bọc `send`** qua `send_with_request_id`, gán `x-request-id` + `x-correlation-id` vào mọi `http.response.start`. Beweis ngược lại claim QA_REPORT. |

## 7. Khuyến nghị

- Cập nhật mọi bảng tổng hợp/tài liệu tham chiếu: thay `932 PASS` → `245 passed` (vòng 11); `350/350 Flutter` → `80/80 Flutter`; `22 with_for_update` → `~36 with_for_update`.
- Tham khảo `QA_REPORT.md` vòng 10-11 (dòng 508-612) và `docs/qa/06-deployment-validation.md` làm nguồn sự thật duy nhất cho số liệu kiểm thử.
- Xem lại danh sách P1/P2 ở phần 5, đặc biệt các mục đã đánh giá lại ở phần 6, trước khi lên kế hoạch sprint sửa còn mở.
