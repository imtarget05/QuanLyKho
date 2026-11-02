# Current Tasks — QuanLyKho (Kho Trà Sữa / BankOps)

> **Execution checkpoint, 2026-11-01 (local only):** Backend Ruff passes and
> the complete backend suite passes (**735 passed, 8 skipped, 1 xfailed**) on
> a fresh isolated PostgreSQL test database migrated to Alembic head
> `030_admin_inventory_create`, with demo mode explicitly enabled for the
> integration fixtures. Flutter analysis is clean, all **261** Flutter tests
> pass, and the Flutter Web release build succeeds. The local API readiness
> endpoint and frontend at `http://127.0.0.1:8000` and `http://127.0.0.1:8080`
> respond successfully. The canonical Docker-backed `make test-backend` gate
> passes with an ephemeral PostgreSQL container; full application Compose and
> kind integration were not run. A read-only AKS check found no QuanLyKho
> deployment; the relevant registry artifact is
> the 2026-10-25 `bankops-api:sha-fde9570`
> (`sha256:bd8098b0603478335352676d19872fb66dd9d3505a569be149d5c70c86495d61`,
> source commit `fde9570a390babbffd9149f5e408771cb9300bb0`). No production
> redeployment was performed. The phase table below is the last audited plan
> status, not proof that all project phases are done. Production recovery and
> deployment remain blocked on separate, explicit cloud-operation approval.

> **Historical portfolio audit checkpoint, 2026-10-21 (test status superseded
> by the checkpoint above):** work started at HEAD `c9b6935`
> and concurrent local commits advanced HEAD through `d53c092` to
> `5d79314364739e48cd589604d56764583d963286` during the audit.
> At start there were pre-existing edits in `backend/app/api/routes/reconciliations.py`,
> `backend/docs/17-b2-authorization-scope-audit.md` and
> `backend/tests/test_b2_authorization_scope.py`. The historical clean-tree
> baseline below is **not** the current working-tree state. See
> `docs/PORTFOLIO_AUDIT_2026-10-21.md` for the current claim matrix, gaps and
> reproducible AI → checker demo. The former 21 MLflow failures on the host's
> read-only `/data` path are superseded by the full passing backend run above.
> Historical revision details remain in the audit.

> **Updated 2026-10-20** after a full local re-verification. Earlier revisions of
> this board recorded a dirty worktree, a "missing AGENTS.md", and an
> unresolved Alembic gap. All three are now resolved; the claims below were
> reproduced locally, not copied forward.

## Historical verified baseline (2026-10-20, HEAD `197a08e`, branch `main`)

| Item | Verified state |
|---|---|
| Branch / HEAD | `main` @ `197a08e` — **no upstream configured** (`git branch -vv` shows no `[origin/main]`) |
| Worktree | **clean** before and after verification |
| Local branches | `main`, `codex/bankops-b1`, `qa-validation-20261014`, `backup/pre-token-scrub-20261013-213005` |
| `AGENTS.md` | **present** (6.9 KB) — the previous "MISSING" note was wrong |
| Secret guard | `python3 scripts/check_no_secrets.py` → PASS |
| Lint | `ruff check backend/` with **0.17.0** (CI pin) → All checks passed |
| Migrations | `alembic upgrade head` on an **isolated** Postgres 16 → `024_add_branch_id_to_cashbox (head)`, 42 tables |
| Backend tests | **387 passed, 7 skipped, 1 xfailed** in 129 s |
| Flutter | `flutter analyze` → No issues; `flutter test` → **180 passing** |
| Scale | backend 16,247 LOC / 56 `.py`; frontend 46,277 LOC / 86 `.dart`; 141 routes; 43 test files |

## Resolved findings

1. **Alembic `022 → 024` is not a break.** `024_add_branch_id_to_cashbox.down_revision`
   is `022_movement_cost_and_sub_kind`; no revision declares `023` as parent.
   `alembic upgrade head` succeeds and there is exactly one head. The missing
   number is a cosmetic gap in filenames, not a broken chain.
2. **`cost_price` is provided by migration 021**, not 022
   (`021_receipt_invoice_and_lots.py:41-42`). The historical CI failure
   (`i.cost_price` absent) is not reproducible from a clean database.
3. **`AGENTS.md` exists** and carries its own gotchas table. The board no longer
   duplicates it.
4. **B1 work is committed** — the worktree is clean at `197a08e`.

## Phase status (last audited 2026-10-20; not a current completion claim)

| Phase | Status | Notes |
|---|---|---|
| B0 Baseline audit | PASS | 2026-10-19 inventory; superseded by the 2026-10-20 re-verification above |
| B1 Recover CI/schema/lint | PASS | Migration, lint, backend and Flutter suites all green locally |
| B2 Identity/Auth | NOT_STARTED | |
| B3 Atomic posting | NOT_STARTED | |
| B4 Contract/Events | NOT_STARTED | |
| B5 Workflows | NOT_STARTED | |
| B6 Offline (P2) | DEFER | |
| B7 Ops/Release | NOT_STARTED | |

## Open items (do not overstate)

- **Full application Compose/kind integration remains unverified.** The
  canonical Docker-backed PostgreSQL test target passed, but that does not
  exercise the complete app stack or a kind cluster.
- **Backend tests require an isolated database.** `backend/tests/conftest.py`
  refuses database names without `_test`. Supply an explicit disposable
  PostgreSQL `DATABASE_URL`; the full suite above used one and did not target
  the developer's application database. Demo fixtures require both
  `APP_ENV=demo` and `DEMO_MODE=true`.
- **Production release is not complete.** The inspected AKS cluster has no
  QuanLyKho workloads, and the older ACR image is not evidence of a current
  deployment. Obtain separate approval for an exact release target and
  deployment operation before any cloud mutation.
- **Branch has no upstream.** `main` is not tracking `origin/main`, so
  `git push` has no default and CI is not driven by a push from this checkout.

## Next step (B2 — Identity/Auth)

Scope when B2 opens: enumerate authentication and authorization surfaces, prove
object-level authorization for each route group, and add negative tests for
cross-branch access. The audit must start from `app/api/routes/` + IAM models,
not from the docs.

## AGENTS.md

Present at the repository root. Repo-specific conventions there take precedence
over the portfolio-wide conventions in `Productionized-LegacyApp` /
`AKS-SRE-Platform`.
