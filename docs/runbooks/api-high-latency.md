# Runbook — BankOps API High Latency (p95 > 500ms)

## Trigger
Alert `BankOpsApiHighLatencyP95` fire: p95 request duration > 500 ms trong 5 phút.

## Severity
Warning

## Impact
Trải nghiệm người dùng chậm, có thể gây timeout ở frontend/mobile.

## Owner
Backend team

## Quy trình xử lý

1. **Xác nhận**: Mở Grafana dashboard `bankops-sli-slo`, panel "HTTP p95 Latency (5m)". Xác nhận哪 routes chậm.
2. **Kiểm tra Pod**: `kubectl top pods -n bankops` — xem Pod nào sử dụng CPU/Memory cao.
3. **Kiểm tra logs**: `kubectl logs -n bankops -l app.kubernetes.io/name=bankops-api -c api --tail=100` — tìm slow query / external call treo.
4. **Kiểm tra DB**: `pg_stat_activity` xem có query chậm hay lock không.
5. **Khắc phục khẩn cấp**:
   - Nếu Pod OOM/crash: `kubectl rollout restart deployment bankops-api -n bankops`.
   - Nếu DB query chậm: thêm index / tối ưu query (xem `docs/04-database.md`).
6. **Scale tạm thời**: Tăng replica API qua ArgoCD values-staging/prod.yaml nếu traffic tăng đột biến.
7. **Verify**: p95 quay lại < 500 ms và ổn định trong 15 phút.

## Runbook liên kết
- `api-high-error-rate.md` nếu đồng thời error rate cao.
- `cpu-saturation.md` / `memory-saturation.md` nếu resource saturate.
