# SLI/SLO — BankOps (QuanLyKho)

Mục tiêu: chuyển alert rules (`infra/observability/alert-rules.yaml`) thành SLO đo lường có trigger, severity, impact, owner và bước verify rõ ràng.

## 1. Chỉ số SLI đã định nghĩa

| SLI | Metric | Cửa sổ | Target (SLO) | Alert liên kết |
|-----|--------|--------|--------------|----------------|
| Latency p95 | `histogram_quantile(0.95, rate(quanlykho_http_request_duration_seconds_bucket[5m]))` | 5 phút | ≤ 500 ms | `BankOpsApiHighLatencyP95` |
| Error rate | `rate(quanlykho_http_requests_total{status_class=~"5.."}[5m]) / rate(quanlykho_http_requests_total[5m])` | 5 phút | ≤ 1% | `BankOpsApiHighErrorRate` |
| CPU saturation | `sum(rate(container_cpu_usage_seconds_total{container="api"}[5m])) / sum(kube_pod_container_resource_requests_cpu_cores)` | 10 phút | ≤ 80% | `BankOpsApiCpuSaturation` |
| Memory saturation | `sum(container_memory_working_set_bytes{container="api"}) / sum(kube_pod_container_resource_requests_memory_bytes)` | 10 phút | ≤ 85% | `BankOpsApiMemorySaturation` |
| Maker-checker pending | `quanlykho_approval_pending_seconds` | 10 phút | ≤ 3600 s | `BankOpsApprovalPendingTooLong` |
| Pod crash-loop | `rate(kube_pod_container_status_restarts_total[15m])` | 15 phút | = 0 | `BankOpsPodCrashLooping` |

## 2. Error budget

- SLO 99% error rate ⇒ error budget = 1% trong 30 ngày (~43.2 phút downtime/lỗi 5xx).
- Nếu error budget tiêu hết trong tháng → kỉ túc release mới, chỉ deploy hotfix.

## 3. Owner & trigger

| SLI | Owner | Trigger | Severity |
|-----|-------|---------|----------|
| Latency p95 | Backend team | p95 > 500 ms trong 5 phút | Warning |
| Error rate | Backend team | > 1% trong 5 phút | Critical |
| CPU/Memory saturation | Platform team | > 80/85% trong 10 phút | Warning |
| Maker-checker pending | Ops team | > 1 giờ | Warning |
| Pod crash-loop | Platform team | restart > 0 trong 15 phút | Critical |

## 4. Cách verify khi incident

1. Mở dashboard Grafana `BankOps — SLI/SLO Overview` (`uid: bankops-sli-slo`).
2. Xem panel "HTTP Error Rate (5m)" và "HTTP p95 Latency (5m)".
3. So sánh với SLO trong bảng trên.
4. Nếu vượt → vào runbook chi tiết tương ứng (xem các file bên dưới).
5. Sau khi khôi phục, ghi incident vào error budget tracker.
