# CI Results — QuanLyKho

| Field | Value |
|-------|-------|
| **Task** | P3.7 — Python Evaluation Harvest: CI results evidence |
| **Commit SHA** | `9f877c2ad25ee5639c7a96b3c69037b2f40ff63c` (HEAD at packaging) |
| **Command** | `ls .github/workflows/` + review workflow files |
| **Output** | 8 CI workflows configured; `devops.ci_cd` PASS (20 pts) in eval |
| **Status** | VERIFIED (configuration present; historical CI main/S11/deploy noted đỏ in P0.11) |

## CI workflows (8)

| Workflow | Purpose |
|----------|---------|
| `.github/workflows/ci.yml` | Main CI: secrets guard, lint (ruff 0.17.0), test |
| `.github/workflows/ci-gitops.yml` | GitOps CI pipeline |
| `.github/workflows/deploy-pages.yml` | Cloudflare Pages deploy |
| `.github/workflows/deploy-worker.yml` | Worker deploy |
| `.github/workflows/deploy.yml` | General deploy |
| `.github/workflows/s10-acceptance-ci.yml` | S10 acceptance CI |
| `.github/workflows/s11-e2e-cloud-ci.yml` | S11 cloud CI E2E |
| `.github/workflows/s9-k8s-cloud-ci.yml` | S9 Kubernetes CI |

## Verified CI evidence (PHASE_M closure)

| Gate | Run | Result | Evidence |
|------|-----|--------|----------|
| S10 Acceptance | Run #39430010453 | **20/20 tests passed** | `docs/evidence/phase-m-closure.md` §S10 |
| G2 Security | `scripts/check_no_secrets.py` | PASSED — no hardcoded credentials | `docs/evidence/phase-m-closure.md` §G2 |
| S9 Kubernetes | Run #39599442638 | **2/2 RollingUpdate, 0 restarts, healthy probes** | `docs/evidence/phase-m-closure.md` §S9 |
| S11 Cloud CI E2E | Run #39546426245 | PARTIAL — Alembic Docker DNS constraint | `docs/evidence/phase-m-closure.md` §S11 |

## Eval mapping

- `devops.ci_cd` — PASS (20 pts): `ci-gitops.yml`, `ci.yml`, `deploy-pages.yml`, `deploy-worker.yml`, `deploy.yml`, `s10-acceptance-ci.yml`, `s11-e2e-cloud-ci.yml`, `s9-k8s-cloud-ci.yml`, `AGENTS.md`, `backend/.github/workflows/s9-k8s-cloud-ci.yml`.

## Known notes

- P0.11 (master plan): CI main + S11 + deploy đỏ — fix CI 3/3 job xanh is an open action, not yet closed.
- Eval harness reports `pytest exit_code=1 ok=False` because pytest is not installed in Python 3.14 sandbox — environment limitation, not a project failure (see `01-backend-test-results.md` caveat).
- Secrets scan: `devops.secrets_scan` PASS via `.github/workflows/ci-gitops.yml`; `scripts/check_no_secrets.py` runs clean (G2 verified).
