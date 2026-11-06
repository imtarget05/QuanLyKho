# QuanLyKho: 5–10 minute backend interview demo

This is a local simulation of ingredient inventory with separate maker and checker roles. It uses a disposable PostgreSQL database and the real FastAPI routes. No customer data, bank connection, production service, or external AI provider is involved.

## Run the demo

Prerequisites: PostgreSQL CLI tools (`initdb`, `pg_ctl`, `createdb`), Python 3.11 and the project environment created with `cd backend && poetry install --with dev`.

From the repository root:

```bash
bash scripts/demo_ai_checker.sh
```

The script creates a temporary `bankops_test` database under `/tmp`, applies every Alembic migration, explicitly seeds demo identities and inventory, runs `tests/test_portfolio_ai_checker_demo.py`, and removes that database when it exits. The test guard refuses to run mutating tests against a database whose name lacks `_test`. The script does not touch the developer's normal database.

On 2026-11-06, the isolated demo reached migration `034_general_ledger_coa` and both focused tests passed. Re-run on the commit you present in an interview; this result does not certify later changes.

## What to show and explain

1. Maker creates and submits an ingredient receipt. No stock movement is posted yet.
2. The checker requests an advisory assessment. The response identifies `heuristic_fallback` and `simulation=true`; it does not approve stock.
3. Maker self-approval returns 403. A separate checker approves; exactly one stock movement appears.
4. Repeating approval with the same idempotency key returns the stored result. A different key after final state returns 409.
5. Checker rejects another receipt; no stock movement appears. Auditor can see the approval and rejection events with request IDs.
6. A separate receipt and issue change the stock balance by their signed movements. An injected ledger-posting failure leaves the request submitted and rolls back movement, balance, and approval audit changes.

The assertions are in [the demo test](backend/tests/test_portfolio_ai_checker_demo.py). FEFO issue and concurrent no-negative-stock cases are separately covered by [the outbound tests](backend/tests/test_phase2b_fefo_outbound.py). The API base path is `/api/v1`; use the test as the source for exact request shapes.

## Portfolio claims supported by this demo

- Python/FastAPI API design, PostgreSQL schema migrations, inventory transactions, maker/checker RBAC, idempotency and audit trail.
- A deterministic advisory AI fallback, clearly separated from the authorization decision.

The demo does not prove Java experience, a live banking integration, production cloud deployment, mobile offline behavior, or a measured query optimization. For those claims, point to separate current evidence or leave them off the CV.
