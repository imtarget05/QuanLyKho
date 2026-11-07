# T12 PostgreSQL migration rehearsal

- **Captured:** 2026-11-06, approximately 09:22 UTC
- **Repository:** `QuanLyKho`
- **Branch / source SHA:** `codex/qlk-migration-lab` / `e3420a5`
- **Database:** disposable PostgreSQL 16 container using `docker-compose.test.yml`
- **Scope:** local migration, backup, restore-based rollback, and forward re-application only

This rehearsal did not use an Azure database or production data. The test database ran on an isolated Compose project and a temporary port, with a tmpfs data directory. The pre-existing edit to the main `docker-compose.yml` was not used or modified.

## Procedure and results

| Step | Expected | Observed | Result |
|---|---|---|---|
| Empty database to snapshot | Alembic reaches `033_inventory_ledger` | All migrations through 033 completed | PASS |
| Seed snapshot data | Representative application rows exist | 30 `inv_items`, 33 `inv_balances` | PASS |
| Pre-migration backup | Custom-format dump is readable | `pg_restore --list` passed; 144,252 bytes; SHA-256 `beadd38ab970d74c86e5440851bb586b8cce7a5d84b95768cccbc356817209cd` | PASS |
| Forward migration | Upgrade from 033 to head | Reached `034_general_ledger_coa`; 8 `coa_accounts` created | PASS |
| Data preservation | Existing inventory rows remain unchanged | 30 items and 33 balances after upgrade | PASS |
| Rollback rehearsal | Restore snapshot to pre-migration version | Restored dump reported `033_inventory_ledger`; 30 items and 33 balances; `coa_accounts` absent | PASS |
| Forward recovery | Reapply migration after restore | Reached `034_general_ledger_coa`; 30 items, 33 balances, 8 COA accounts | PASS |
| Cleanup | No disposable database remains | Compose container, network, tmpfs, and local dump removed | PASS |

The database was seeded with the repository's demo seed command before the backup. The migration itself is transactional DDL; rollback evidence here is restore-based, not an Alembic downgrade of 034.

After the migration drill, the isolated backend suite was rerun on this checkout with `TEST_POSTGRES_PORT=55441 make test-backend`: **980 passed, 8 skipped, 1 xfailed, 25 warnings** in 844.94 seconds. The Makefile removed its disposable test database after the run. This result is for SHA `e3420a5`, not the separately reported SHA `5f0890b`.

## Limitations

- This is a local PostgreSQL rehearsal, not Azure Database for PostgreSQL, managed backup, PITR, or a cloud cutover.
- The observed row-count checks cover inventory items and balances, not every table or a production-sized dataset.
- RPO/RTO were not measured.
- The test run does not claim a green 977-test run on SHA `5f0890b`; this checkout reported 980 passing tests.
