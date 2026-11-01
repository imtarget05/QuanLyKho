# Incident Response Runbook — Quy trình 6 bước (Google SRE)

Áp dụng cho: **QuanLyKho** (FastAPI + PostgreSQL + Flutter)

## 0. Quy tắc vàng

> Khi hệ thống đang gián đoạn nghiêm trọng, ưu tiên **khôi phục dịch vụ** trước. Phân tích nguyên nhân gốc (root cause) có thể thực hiện sau khi dịch vụ đã ổn định.

---

## 1. Detect — Phát hiện bất thường

| Nguồn | Cách phát hiện | Công cụ |
|-------|---------------|---------|
| Alerting | SLO burn-rate, error rate > ngưỡng, CPU > 80% | Prometheus + Alertmanager, Grafana |
| Golden Signals | Latency p95 tăng, Traffic突增, Errors 5xx, Saturation CPU/RAM | Grafana dashboard |
| User report | Người dùng báo "ứng dụng không hoạt động" | Support ticket, Slack, email |
| Synthetic probe | Health check `/api/v1/health/live` thất bại | k6, curl, uptime robot |

**Lệnh kiểm tra nhanh:**

```bash
# Local development
curl -f http://localhost:8000/api/v1/health/live

# PostgreSQL
psql -h 127.0.0.1 -U bankops -d bankops_test -c "SELECT 1"

# Docker
docker compose ps
docker compose logs --tail=50
```

---

## 2. Assess — Xác định phạm vi ảnh hưởng

| Câu hỏi | Cách trả lời |
|---------|-------------|
| Có bao nhiêu user bị ảnh hưởng? | Xem Grafana traffic dashboard, Access logs |
| Dịch vụ nào bị ảnh hưởng? | Xem API status, database status |
| Thời điểm bắt đầu? | Xem alert timestamp, application logs |
| Có liên quan đến deploy mới không? | Xem git log, CI/CD pipeline, image tag |

---

## 3. Investigate — Thu thập bằng chứng, khoanh vùng lỗ

### 3.1 API trả HTTP 500 (FastAPI)

| Bước | Lệnh | Dấu hiệu |
|------|------|----------|
| 1 | Application logs + `X-Request-ID` | Exception stack trace |
| 2 | Kiểm tra envelope error | `error.code`, `error.message`, `error.request_id` |
| 3 | Kiểm tra dependency | PostgreSQL, Redis, Cloudflare Edge |
| 4 | Kiểm tra DB connection | `pg_stat_activity` |

### 3.2 API phản hồi chậm (PostgreSQL)

```sql
SELECT
    pid,
    state,
    wait_event_type,
    wait_event,
    now() - xact_start AS transaction_age,
    now() - query_start AS query_age
FROM pg_stat_activity
WHERE datname = current_database()
ORDER BY xact_start NULLS LAST;
```

| Quan sát | Hướng suy luận |
|----------|---------------|
| `wait_event_type = Lock` | Chờ transaction khác nhả khóa |
| `idle in transaction` kéo dài | Giao dịch chưa kết thúc, giữ tài nguyên/khóa |
| Nhiều phiên xử lý kéo dài | Truy vấn chậm, quá tải, dependency |
| Nhiều kết nối gần giới hạn | Connection pool rò rỉ |

### 3.3 Hai người duyệt phiếu kho đồng thời (409 Conflict)

| Kiểm tra | Cách xác minh |
|----------|--------------|
| Transaction isolation | `SELECT ... FOR UPDATE` khóa hàng |
| Idempotency key | Cùng key chỉ xử lý 1 lần |
| 409 Conflict | Kết quả đúng của cơ chế bảo vệ nghiệp vụ |
| Movement trùng | Không được có duplicate movement trong DB |

---

## 4. Mitigate — Giảm ảnh hưởng, khôi phục dịch vụ

| Tình huống | Hành động giảm ảnh hưởng |
|-----------|------------------------|
| Lỗi code sau deploy mới | Rollback về bản ổn định (git revert + redeploy) |
| DB bị chậm | Kill transaction dài hạn |
| TransactionIdle | Kill session: `SELECT pg_terminate_backend(pid)` |
| 409 Conflict hợp lệ | Không xử lý lại, trả 409 cho client |

---

## 5. Verify — Kiểm chứng hệ thống đã phục hồi

| Kiểm tra | Lệnh | Kết quả mong đợi |
|----------|------|------------------|
| Health check | `curl -f /api/v1/health/live` | HTTP 200 |
| Test suite | `poetry run pytest tests -q` | 0 failed, 0 errors |
| DB connection | `SELECT 1` | Thành công |
| Error rate | Grafana/logs | 5xx < 0.1% |

---

## 6. Postmortem — Phân tích nguyên nhân và phòng ngừa

Sử dụng template `INCIDENT_REPORT_TEMPLATE.md`.

| Phần | Nội dung |
|------|----------|
| Timeline | Thời điểm phát hiện, bắt đầu xử lý, khôi phục |
| Tác động | Số user affected, thời gian downtime, loss estimation |
| Nguyên nhân gốc | Root cause (5 Whys) |
| Bằng chứng | Logs, metrics, traces, screenshots |
| Xử lý đã thực hiện | Mitigate actions, rollback |
| Phòng ngừa | Action items, owner, deadline |

---

## Runbook liên quan

- `RUNBOOK_API_500_FASTAPI.md` — Debug API trả 500
- `RUNBOOK_API_SLOW_POSTGRESQL.md` — Debug API chậm do PostgreSQL
- `RUNBOOK_QH_409_CONFLICT.md` — Hai người duyệt phiếu kho đồng thời
- `INCIDENT_REPORT_TEMPLATE.md` — Template báo cáo sự cố