# Disaster Recovery Runbook — QuanLyKho (Phase 4)

## 1. Mục tiêu
Chứng minh khả năng khôi phục hệ thống QuanLyKho sau sự cố lớn (region outage, DB corruption, cluster mất toàn bộ node) dưới RTO < 4 giờ, RPO < 1 giờ.

## 2. Kiến trúc DR
- **Primary**: Azure AKS (Southeast Asia) + Azure PostgreSQL Flexible Server + Azure Cache for Redis + Azure Storage (backups container)
- **DR Target**: Azure PostgreSQL Flexible Server trong cùng region (hoặc region khác) + Azure Storage cho backup artifacts
- **Backup**: CronJob `bankops-backup-db` chạy hàng ngày 02:00 UTC, pg_dump định dạng custom (compressed), SHA-256 checksum, upload lên Azure Blob Storage (`backups` container)

## 3. Các bước drill (tự động qua `scripts/dr/dr-drill.sh`)
| Bước | Mô tả | Công cụ |
|------|-------|---------|
| 1 | `pg_dump` DB nguồn (custom format, compressed) | `pg_dump` |
| 2 | Tính SHA-256 checksum của file dump | `sha256sum` |
| 3 | Upload file dump + checksum lên Azure Blob Storage | `az storage blob upload` |
| 4 | Drop + recreate DB mục tiêu, `pg_restore` từ dump | `pg_restore` |
| 5 | So sánh `count(*)` của các bảng chính giữa source và target | `psql` |
| 6 | Sinh báo cáo evidence JSON | Shell + `cat` |

## 4. Bảng chính được kiểm tra
`inv_items`, `inv_balances`, `cashbox_journals`, `outbox_events`, `users`

## 5. Chuẩn chấp nhận (Pass/Fail)
- **PASS**: Tất cả bảng kiểm tra có `count(*)` khớp giữa source và target, checksum khớp, báo cáo JSON được sinh.
- **FAIL**: Bất kỳ bảng nào `count(*)` khác, hoặc restore thất bại.

## 6. Cách chạy drill (production)
```bash
export DR_SOURCE_PG_HOST=<primary-pg-fqdn>
export DR_SOURCE_PG_USER=<admin-user>
export DR_SOURCE_PG_DB=bankops
export DR_SOURCE_PG_PASSWORD=<from-key-vault>

export DR_TARGET_PG_HOST=<dr-pg-fqdn>
export DR_TARGET_PG_USER=<admin-user>
export DR_TARGET_PG_DB=bankops_dr
export DR_TARGET_PG_PASSWORD=<from-key-vault>

export AZURE_STORAGE_CONNECTION_STRING=<from-key-vault>
export BACKUP_CONTAINER=backups

./scripts/dr/dr-drill.sh
```

## 7. Tần suất drill
- **Full DR drill**: 1 lần/quý (Q1, Q2, Q3, Q4)
- **Backup verification**: hàng tuần (tự động qua CronJob + kiểm tra checksum)
- **Restore test**: 1 lần/tháng (khôi phục vào staging cluster, verify smoke test)

## 8. Evidence artifacts
- `dr-drill_evidence_<timestamp>.json` — báo cáo chi tiết drill
- Backup file trong Azure Storage (`backups/dr-drill/<timestamp>/bankops_db.dump`)
- Screenshot của Azure Portal: storage container, PostgreSQL servers, AKS cluster

## 9. Rollback nếu drill thất bại
- Dùng bản backup gần nhất trước khi sự cố xảy ra (Retention 7 ngày trên PostgreSQL Flexible Server)
- Nếu cả primary và DR đều lỗi, khôi phục từ backup artifact trong Azure Storage vào cluster mới