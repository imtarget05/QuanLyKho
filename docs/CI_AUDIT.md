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
- `render.yaml` now sets `AI_PROVIDER=cloudflare` (Workers AI; fe6350d), but `deploy-pages.yml` deploys Flutter to Cloudflare Workers Assets calling a **Modal** FastAPI endpoint. Render is a secondary/preview environment (documented in `render.yaml` header); Modal remains the canonical production API (P3.2 reconciled 2026-11-13).
- Production deploy requires manual `workflow_dispatch` with confirm input — acceptable for manual gating, but consider adding automatic deploy-on-merge to `main` after branch protection is enabled.

## To do (P0)
- [ ] Enable GitHub branch protection on `main`: require PR, require review, require CI status checks.
- [x] Reconcile `render.yaml` vs actual Modal production backend (P3.2). **Done 2026-11-13:** `render.yaml` header now documents Modal as the canonical production API path; this blueprint is a secondary/preview environment, not the cutover path.
- [x] Change `AI_PROVIDER` from `disabled` to `cloudflare` and rely on existing `CLOUDFLARE_ACCOUNT_ID` + `CLOUDFLARE_API_TOKEN` GitHub secrets (P3.3). **Done in fe6350d:** render.yaml now sets `AI_PROVIDER=cloudflare`. Note: runtime AI creds must also be configured on the Modal backend's own environment; Modal deploy requires `MODAL_TOKEN`, not present in GitHub secrets.
- [x] Review hardcoded `SMTP_USER=binhtan5734@gmail.com` in `render.yaml` — moved to `sync: false` (2026-11-13); value lives in the Render dashboard / deploy environment.

## Canary rollout (P0.6) — 2026-11-13

Added a canary release path for the FastAPI backend under `argo/` (worktree branch `feat/canary-rollouts`, PR to `main`):

- `argo/rollouts-backend.yaml` — `argoproj.io/v1alpha1 Rollout` for `bankops-api`, a 1:1 replica of `infra/k8s/base/deployment-api.yaml` (same selector, probes `/health/live` + `/health/ready`, envFrom, resources, securityContext), with canary steps 20% → 2m pause → 40% → Prometheus analysis → 60% → 2m → 80% → 5m → 100%, `minReadySeconds: 30`, `progressDeadlineSeconds: 600`. A commented `trafficRouting.nginx` block documents the cutover to real weighted traffic (base ingress is nginx).
- `argo/analysis-template.yaml` — `AnalysisTemplate quanlykho-analysis` with two Prometheus metrics (`successRate` ≥ 0.99 and `p95Latency` ≤ 1.0 s, `failureLimit: 1`), querying the app's own exporters (`quanlykho_http_requests_total{status_class="5xx"}`, `quanlykho_http_request_duration_seconds_bucket`) documented as assumptions; Prometheus address is a placeholder (`http://prometheus.observability:9090`) until the observability stack lands.
- `argo/kustomization.yaml` — kustomize entry for ArgoCD / `kubectl apply -k argo/`.
- `argo/README.md` — rationale (canary = maker-checker for traffic), controller + kubectl-plugin install, watch/promote/abort commands, cutover notes (Rollout replaces the base Deployment; same name/selector), and the planned `rollout.enabled` values flag for a future `helm/quanlykho` chart.

Not yet wired into `infra/k8s/base/kustomization.yaml` or `infra/argocd/quanlykho-application.yaml` — adoption is a deliberate follow-up (see `argo/README.md` § Integration).
