# CI Audit — QuanLyKho

Generated: 2026-11-12
Source: `.github/workflows/*.yml`

## Workflows

### `.github/workflows/ci.yml` — CI
**Triggers:** `push` to `main`, `pull_request` to `main`  
**Runs on PR:** Yes.

| Job | Purpose | Gating |
|-----|---------|--------|
| secret-guard | `python3 scripts/check_no_secrets.py` (fail-severity blocks); asserts no tracked `.env` files (allowlist `*.env.example|sample|template`) | Blocking |
| lint | `ruff==0.17.0` `ruff check backend/`; release workflow gate unit tests (`scripts.test_release_workflow_gates`, `scripts.test_tested_image_artifact`) | Blocking |
| test | `APP_ENV=demo`, `DEMO_MODE=true`, PostgreSQL 16 service (`bankops_test`), Poetry 2.5.1 export + install, `alembic upgrade head`, `python -m app.seed`, `pytest tests/ -v --cov=app --cov-report=xml` | Blocking |
| frontend-web | Flutter 3.47.7 stable, `flutter pub get`, `flutter analyze --no-fatal-infos --no-fatal-warnings`, `flutter test`, `flutter build web --release` | Blocking |
| worker-typecheck | Legacy Cloudflare Worker (`infra/cloudflare-worker`) Node 20 `npm ci` + `npm run typecheck` | Blocking |
| build | `docker build -f backend/Dockerfile -t bankops-api:latest backend/`, `docker compose config` | Blocking (needs all above) |
| sonar-scan | SonarCloud scan (SonarScanner 5.0.1, Java 21), `SONAR_TOKEN` secret required, coverage `backend/coverage.xml`, project `imtarget05_BankOps` | Blocking (token required) |

### `.github/workflows/deploy-pages.yml` — Build & Deploy Quản Lý Kho Trà Sữa
**Triggers:** `workflow_dispatch` with required input `confirm == DEPLOY_CLOUDFLARE_ASSETS`, `refs/heads/main`  
**Environment:** `cloudflare-assets-manual`  
**Timeout:** 20 min  
**Secrets verified:** `GOOGLE_CLIENT_ID`, `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID`  
**Build:** Flutter Web release with `--dart-define=API_BASE_URL`, `GOOGLE_CLIENT_ID`, `APP_ENV=production`; writes `version.json`.  
**Deploy:** `npx wrangler@4 deploy --config infra/cloudflare-worker/wrangler.tea-inventory.toml` to Cloudflare Workers Assets.  
**Smoke test:** `curl {API_BASE_URL}/health/live` expects `"status":"alive"`.  
**URL:** `https://quan-ly-kho-tra-sua.tanmainguyenbinh.workers.dev`  
**API_BASE_URL (env):** `https://imtarget05--quan-ly-kho-tra-sua-api.us-east.modal.run/api/v1` — **Modal, not Render.**

### `.github/workflows/deploy-worker.yml` — Validate legacy Cloudflare Worker
**Triggers:** `workflow_dispatch`  
**Purpose:** type-check legacy Worker source only; explicitly never deploys. FastAPI is canonical production API.

## Findings
- `secret-guard` job enforces no committed secrets and no tracked `.env` — good security baseline.
- CI runs lint, test, frontend, worker-typecheck, build, sonar before Docker build — solid gating.
- **Inconsistency:** `render.yaml` declares a Render free service `kho-tra-sua-fastapi` with `AI_PROVIDER=disabled`, but `deploy-pages.yml` deploys Flutter to Cloudflare Workers Assets calling a **Modal** FastAPI endpoint. Render is not in the active deploy path; reconcile render.yaml vs Modal before production cutover (P3.2).
- `AI_PROVIDER=disabled` in render.yaml confirms G9 (AI luồng chưa bật) — must be changed for P3.3.
- Production deploy requires manual `workflow_dispatch` with confirm input — acceptable for manual gating, but consider adding automatic deploy-on-merge to `main` after branch protection is enabled.

## To do (P0)
- [x] Enable GitHub branch protection on `main`: require PR, require review, require CI status checks. **Done 2026-11-13:** 1 required review + 7 required CI checks (secret-guard, lint, test, frontend-web, worker-typecheck, build, sonar-scan), enforce_admins; CI green on both landed commits (fe6350d, 265a27c).
- [ ] Reconcile `render.yaml` (Render free, `AI_PROVIDER=disabled`) vs actual Modal production backend (P3.2).
- [ ] Change `AI_PROVIDER` from `disabled` to `cloudflare`/`ollama` and configure `CLOUDFLARE_ACCOUNT_ID`, `CLOUDFLARE_API_TOKEN` secrets (P3.3).
- [ ] Review hardcoded `SMTP_USER=binhtan5734@gmail.com` in `render.yaml` — move to `sync: false` secret for production.
