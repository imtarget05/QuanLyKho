# Runbook — Maker-Checker Approval Stuck (>1 giờ)

## Trigger
Alert `BankOpsApprovalPendingTooLong` fire: có đơn maker-checker pending > 3600 giây.

## Severity
Warning

## Impact
Giao dịch cần phê duyệt bị treo, ảnh hưởng quy trình nhập/xuất kho.

## Owner
Ops team

## Quy trình xử lý

1. **Xác nhận**: Truy vấn `SELECT * FROM approval_requests WHERE status = 'pending' AND created_at < NOW() - INTERVAL '1 hour';`.
2. **Xác định lý do**: Checker không online? Confict dữ liệu? Hết hạn idempotency key?
3. **Can thiệp**:
   - Nếu checker bỏ quên: nhắc nhở qua email/SMS (xem `admin_alert_email` trong config).
   - Nếu conflict: admin can thiệp thủ công qua endpoint `/api/v1/approvals/{id}/override` (cần quyền admin).
4. **Verify**: Số đơn pending > 1 giờ giảm về 0 trong 30 phút.

## Runbook liên kết
- `api-high-error-rate.md` nếu API lỗi khiến không thể phê duyệt.
