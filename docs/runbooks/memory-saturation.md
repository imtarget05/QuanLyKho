# Runbook — Memory Saturation (>85%)

## Trigger
Alert `BankOpsApiMemorySaturation` fire: memory usage > 85% của request trong 10 phút.

## Severity
Warning

## Impact
Pod gần hết memory, có thể OOMKill và restart liên tục.

## Owner
Platform team

## Quy trình xử lý

1. **Xác nhận**: `kubectl top pods -n bankops`.
2. **Khắc phục khẩn cấp**: `kubectl rollout restart deployment bankops-api -n bankops` để giải phóng memory.
3. **Scale**: Tăng replica và/hoặc memory limit trong `values-prod.yaml`.
4. **Verify**: memory quay lại < 75% và ổn định 15 phút.
