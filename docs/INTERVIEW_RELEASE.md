# QuanLyKho interview release

## One-sentence pitch

QuanLyKho is a warehouse and financial-operations simulation with FastAPI,
PostgreSQL, Alembic, Flutter, role-scoped maker-checker workflows, idempotency,
and audit-friendly ledger behavior.

## Five-minute offline UI demo

Offline UI demo:

```bash
make up
# open http://localhost:8080
make down
```

Backend verification with an isolated PostgreSQL container:

```bash
make test-backend
```

## Ten-minute backend demo

From the repository root, run:

```bash
bash scripts/demo_ai_checker.sh
```

The script requires `backend/.venv` and local PostgreSQL executables
(`initdb`, `pg_ctl`, `createdb`). It creates a disposable PostgreSQL cluster on
a dynamically selected loopback port, migrates to Alembic head, seeds fake
demo users/data, runs the API integration journey, and removes only its
validated temporary directory on exit. It does not use a developer database.

The journey proves receipt → maker submit → separate checker approval → stock
movement and balance increase → issue → separate checker approval → stock
movement and balance decrease → audit events. A fault injected
after movement work but before ledger commit verifies the transaction leaves
the request submitted and does not persist balance, movement, or approval-audit
changes. Demo credentials and inventory data are synthetic; the AI advice path
is a deterministic fallback, not a live model.

Suggested interview pacing:

| Minutes | Walkthrough |
|---|---|
| 0–2 | Explain disposable PostgreSQL, Alembic migration, and synthetic seed data. |
| 2–4 | Show maker submission and separate checker approval; point out RBAC and audit assertions. |
| 4–7 | Trace receipt and issue from request through signed movements and balance changes. |
| 7–9 | Show same-transaction rollback when ledger posting fails before commit. |
| 9–10 | State limits: simulated data, deterministic AI fallback, no bank or production integration. |

The focused command currently reports **2 passed** on a fresh isolated local
PostgreSQL database. The full hosted CI workflow records the exact tested
commit in the test job summary; use the run for the commit being presented,
not a historical test count. See [CI workflow](../.github/workflows/ci.yml).
The latest migration is `034_general_ledger_coa`.

## Interview talking points

- FastAPI + PostgreSQL is the canonical business backend; the Cloudflare
  Worker is not the production source of truth.
- Maker-checker rules, branch scoping, idempotency keys, optimistic versions,
  and dual-entry ledger posting protect write workflows.
- Alembic is the schema authority and the test target is an isolated PostgreSQL
  database, not a developer database.
- The offline demo intentionally keeps browser data in memory and does not
  claim to be a live production deployment.

## Honest production boundary

- The product is a simulation and does not connect to a bank or handle real
  money.
- Live cloud deployment, external identity, notification delivery, and
  production operations still require environment-specific acceptance.
- Historical QA notes may describe older counts; use the commands above for the
  current working tree.

## Evidence

- [Root README](../README.md)
- [QA report](../QA_REPORT.md)
- [Docker Compose stack](../docker-compose.yml)
- [Operations Makefile](../Makefile)
