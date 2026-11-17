# DR Drill Checklist (P1 — chạy thật cần credentials cloud)

Mục tiêu: chứng minh backup/restore hoạt động và ghi lại evidence.  
**Lưu ý**: Đây là checklist chạy thủ công. Các script đã có sẵn tại `scripts/dr/`:
- `backup_postgres.sh`
- `restore_postgres.sh`
- `dr_drill_test.sh`

## 1. Chuẩn bị

- [ ] PostgreSQL đang chạy (local/docker/Azure PG Flexible)
- [ ] `pg_restore` hoặc Docker container `bankops-db` có sẵn
- [ ] GPG passphrase được cấu hình (`BACKUP_GPG_PASSPHRASE`)
- [ ] Thông tin cloud storage (R2/S3) nếu upload backup

## 2. Thực hiện drill (theo scripts/dr/dr_drill_test.sh)

```bash
# 1. Dump DB hiện tại
bash scripts/dr/backup_postgres.sh

# 2. Tính SHA-256
sha256sum /tmp/backups/bankops_db_*.dump > /tmp/backups/checksum.sha256

# 3. Mã hóa GPG AES-256 (nếu có passphrase)
gpg --batch --yes --passphrase "$BACKUP_GPG_PASSPHRASE" \
    --symmetric --cipher-algo AES256 -o dump.gpg dump_file

# 4. Khởi tạo DB test tạm thời
# (dùng Docker postgres:16 hoặc Azure PG Flexible test)

# 5. Giải mã và restore vào DB test
bash scripts/dr/restore_postgres.sh /tmp/backups/dump.gpg bankops_test

# 6. Đối soát
psql -U bankops -d bankops_test -c "SELECT count(*) FROM information_schema.tables WHERE table_schema='public';"
psql -U bankops -d bankops_test -c "SELECT version_num FROM alembic_version;"

# 7. Dọn dẹp environment test
```

## 3. Eviden cần thu thập

| File | Mục đích |
|------|----------|
| `scripts/dr/dr_drill_test.sh` output | Log chạy drill thành công |
| `checksum.sha256` | Chứng minh toàn vẹn backup |
| `restore_postgres.sh` output | Chứng minh restore hoạt động |
| `alembic_version` query result | Chứng minh schema khớp sau restore |
| Screenshot DB test có dữ liệu | Evidence visual cho CV |

## 4. Tiêu chí thành công (pass/fail)

| Tiêu chí | Đạt / Không |
|----------|-------------|
| Backup file được tạo và không rỗng | ☐ |
| SHA-256 checksum khớp sau khi giải mã | ☐ |
| Restore vào DB test thành công | ☐ |
| Số bảng trong DB test khớp với production | ☐ |
| `alembic_version` khớp head migration | ☐ |
| Thời gian restore ≤ 15 phút (RTO) | ☐ |

## 5. Ghi video / chụp màn hình

- Chụp màn hình terminal khi chạy `bash scripts/dr/dr_drill_test.sh` (toàn bộ luồng).
- Chụp màn hình kết quả `psql` verify table count + alembic_version.
- Ghi video nếu yêu cầu chứng minh end-to-end (tùy đơn vị tuyển dụng).

## 6. Lưu ý khi chạy thật

- Không để GPG passphrase / DB password vào script output.
- Chạy drill trên environment test/staging, không ảnh hưởng production.
- Sau khi drill xong, xóa DB test và backup tạm để không rò rỉ dữ liệu.
