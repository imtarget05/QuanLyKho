# Runbook — BankOps API High Error Rate (>1%)

## Trigger
Alert `BankOpsApiHighErrorRate` fire: tỷ lệ 5xx > 1% trong 5 phút.

## Severity
Critical

## Impact
Người dùng không thể thực hiện giao dịch (mua/bán kho, phê duyệt).

## Owner
Backend team

## Quy trình xử lý

1. **Xác nhận**: Grafana panel "HTTP Error Rate (5m)". Xác nhận status class (500 vs 502/503/504).
2. **Xác định scope**: Tất cả routes hay chỉ một route (ví dụ `/api/v1/approvals`)?
3. **Kiểm tra dependency**:
   - DB: `kubectl exec -n bankops <postgres-pod> -- pg_isready`
   - Redis: `kubectl exec -n bankops <redis-pod> -- redis-cli ping`
   - External (Cloudflare AI, Google Sheets): xem log lỗi timeout.
4. **Rollback nếu deploy mới**: Nếu error bắt đầu sau release mới, revert image trong ArgoCD (`git revert HEAD` trên infra repo).
5. **Scale / restart**: `kubectl rollout restart deployment bankops-api -n bankops`.
6. **Verify**: error rate quay lại < 1% và ổn định 15 phút. Ghi incident vào error budget.

## Runbook liên kết
- `api-high-latency.md` nếu latency cũng cao.
- `approval-stuck.md` nếu route `/approvals` lỗi.
