# Runbook — CPU Saturation (>80%)

## Trigger
Alert `BankOpsApiCpuSaturation` fire: CPU usage > 80% của request trong 10 phút.

## Severity
Warning

## Impact
Pod gần hết CPU, latency tăng, có thể OOMKill.

## Owner
Platform team

## Quy trình xử lý

1. **Xác nhận**: `kubectl top pods -n bankops`.
2. **Scale**: Tăng replica API qua ArgoCD (`values-prod.yaml` `api.replicaCount`).
3. **Tối ưu**: Tăng CPU limit nếu cần.
4. **Verify**: CPU quay lại < 70% và ổn định.
