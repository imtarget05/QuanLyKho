# QuanLyKho interview release

## One-sentence pitch

QuanLyKho is a warehouse and financial-operations simulation with FastAPI,
PostgreSQL, Alembic, Flutter, role-scoped maker-checker workflows, idempotency,
and audit-friendly ledger behavior.

## Five-minute demo

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

The current run passes **975 tests**, with **8 skipped** and **1 expected
failure**. Ruff passes for `backend/` and `ai/`. The latest migration is
`034_general_ledger_coa`.

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
