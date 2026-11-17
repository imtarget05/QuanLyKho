# Runbook — BankOps Pod Crash-Looping

## Trigger
Alert `BankOpsPodCrashLooping` fire: restart > 0 trong 15 phút.

## Severity
Critical

## Impact
Khả năng xử lý giảm, có thể gây downtime nếu toàn bộ Pod crash.

## Owner
Platform team

## Quy trình xử lý

1. **Xác nhận**: `kubectl get pods -n bankops` — tìm Pod trạng thái `CrashLoopBackOff`.
2. **Xem logs**: `kubectl logs -n bankops <pod> -c api --previous` — tìm lý do crash (OOM, exception, migration lỗi).
3. **Kiểm tra event**: `kubectl describe pod -n bankops <pod>`.
4. **Khắc phục**:
   - Nếu OOM: tăng memory limit trong `values-prod.yaml` và redeploy qua ArgoCD.
   - Nếu migration lỗi: revert migration job hoặc downgrade image.
   - Nếu exception code: rollback release (`git revert` + push).
5. **Verify**: Pod trạng thái `Running`, restart = 0, readiness/liveness probe pass.
