# SLO & burn-rate — QuanLyKho

Người dùng: SRE / platform team. Mục tiêu: định nghĩa SLO, tính error budget và cảnh báo theo burn-rate để hành động trước khi vi phạm SLO.

## 1. SLO mục tiêu (khởi tạo)

| SLO | Medida | Mục tiêu | Cửa sổ | Ngữ cảnh |
|-----|--------|----------|--------|----------|
| API availability | yêu cầu thành công / tổng yêu cầu | ≥ 99.9% | 30 ngày | `http_server_requests_total{status!~"5.."}` |
| API latency p95 | phần yêu cầu dưới ngưỡng | p95 ≤ 500 ms | 30 ngày | `http_server_requests_seconds_bucket` |
| Worker outbox lag | sự kiện không xử lý quá ngưỡng | lag ≤ 5 phút | 30 ngày | `bankops_worker_outbox_lag` |
| Migration thành công | migration chạy không lỗi | 100% | mỗi bản release | Alembic upgrade head |

> Các con số trên là mốc khởi tạo, chưa được đo trên traffic thật. Gắn `MEASURED` sau khi có baseline từ Prometheus; trước đó đánh giá `DESIGN_ONLY`.

## 2. Error budget

```
Error budget = 1 - Mục tiêu SLO
```

Ví dụ API availability 99.9% → error budget 0.1% trong cửa sổ 30 ngày. Khi error budget cạn kiệt → ngừng deploy tính năng mới, ưu tiên sửa độ ổn định.

## 3. Burn-rate (cảnh báo)

Cảnh báo khi tốc độ tiêu thụ error budget vượt ngưỡng:

| Cửa sổ | Burn-rate ngưỡng | Hành động |
|--------|------------------|-----------|
| 1 giờ | ≥ 14.4× | Trang trọng: khẩn cấp, xem xét rollback |
| 6 giờ | ≥ 7.2× | Cao: 조사 nguyên nhân, freeze tính năng |
| 24 giờ | ≥ 1.44× | Trung bình: ưu tiên sửa lỗi trong sprint |

Công thức burn-rate: `(tỷ lệ thất bại hiện tại / tỷ lệ thất bại cho phép SLO)`. Tỷ lệ thất bại cho phép = (1 - mục tiêu SLO) chia đều theo cửa sổ.

Ví dụ: SLO availability 99.9% (sai lệch 0.1%/30 ngày ≈ 0.0033%/ngày). Nếu sai lệch thực 0.05% trong 1 giờ → burn-rate cao → kích hoạt cảnh báo 1 giờ.

## 4. Cách triển khai

- Cài đặt PrometheusRule trong `infra/k8s/base/observability/` (hoặc nền tảng observability chung do AKS-SRE-Platform sở hữu).
- Dashboard Grafana: `infra/k8s/base/grafana-dashboards/bankops-overview.json`.
- Multi-doc SLO/SLI: lưu tại `deploy/sli/`; mỗi thay đổi SLO đi qua PR và review SRE.

## 5. Ràng buộc

- Không pager trên metric design-only; chỉ cảnh báo khi có bằng chứng từ Prometheus.
- Không dùng SLO để buộc deploy khi error budget còn dư.
