# General ledger

Alembic revision `034_general_ledger_coa` adds the consolidated chart of
accounts and general-ledger journals. It backfills the existing inventory and
cash sub-ledgers. Each new inventory or cash-simulation posting is copied into
the general ledger in the same database transaction and is unique by source
type and source-journal ID.

The base chart contains accounts 111, 112, 152, 156, 331, 511, and 632.
Inventory count adjustments use account 632 as the balancing expense/offset.
Legacy adjustment journals that had only one inventory-side entry are
normalized with a balancing account 632 entry in the general ledger; their
original sub-ledger rows are not changed.

Cash journals remain simulations. `SIM_CASH:<cashbox UUID>` and
`SIM_OFFSET:DEMO` accounts and their general-ledger journals are marked
`simulation_only`. The `GET /reports/general-ledger` report excludes simulation
postings by default; callers must opt in and still pass the inventory or cash
scope checks. Amounts are returned as decimal strings in VND.

This ledger does not initiate real money movement and does not bypass existing
maker-checker approval. Before production rollout, apply the migration and
verify the backfill, account totals, backup/restore, and failover against an
isolated PostgreSQL test database.
