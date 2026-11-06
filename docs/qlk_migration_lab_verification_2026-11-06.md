# QuanLyKho migration-lab verification — 2026-11-06

**Source SHA:** `83b9d7e9af76fc3fe0f80074460ced6632326473`  
**Environment:** disposable PostgreSQL 16 Compose projects on host port 5547; isolated from the shared `quanlykho-test` database. Python 3.11.15.  
**Scope:** local migration and negative-case evidence only; this does not demonstrate cloud acceptance or a clean full backend suite.

## Results

- Fresh database `alembic upgrade head`: PASS, revision `034_general_ledger_coa`.
- Demo seed followed by a repeated `alembic upgrade head`: PASS; revision remained `034_general_ledger_coa`.
- `backend/tests/test_migration_lab_negatives.py`: **3 passed** (R02 expired receipt, F03 insufficient stock, S05 maker self-approval).
- Snapshot rollback drill on a disposable database: PASS.
  - Downgraded from 034 to `033_inventory_ledger`.
  - Created a `pg_dump --no-owner` snapshot (**94,638 bytes**).
  - Upgraded to `034_general_ledger_coa`.
  - Dropped/recreated only the disposable test database and restored the snapshot.
  - Restore returned the version to `033_inventory_ledger`; re-upgrade returned it to `034_general_ledger_coa`.
  - Drill ran from `2026-11-06T06:48:03Z` through `2026-11-06T06:48:23Z`.

The temporary Compose services and dump file were removed after verification. The full backend suite is not certified by these targeted runs; prior shared-database runs were contaminated by concurrent tests, and an independent suite was still active during this verification. Keep the full-suite gate `PARTIAL` until a clean sequential run completes.
