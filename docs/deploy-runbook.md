# Deployment Runbook — QuanLyKho (Enterprise Inventory & Treasury)

Generated: 2026-11-13
Scope: Production domain, AI provider enable, backend SLA, E2E tests,
ArgoCD GitOps, monitoring.

Prerequisites:
- `CLOUDFLARE_API_TOKEN` + `CLOUDFLARE_ACCOUNT_ID` (GitHub Secrets / Render dashboard)
- Render dashboard access (for backend secrets)
- Cloudflare dashboard + DNS access (for production domain)
- Modal access (canonical production API)
- AKS cluster kubeconfig (for ArgoCD production)

---

## Step 0 — Reconcile render.yaml vs Modal (P3.2)

Goal: Understand that Modal is canonical production API, Render is preview.

1. Confirm `deploy-pages.yml` deploys Flutter to Cloudflare Workers Assets
   pointing at Modal endpoint:
   `https://imtarget05--quan-ly-kho-tra-sua-api.us-east.modal.run/api/v1`
2. Confirm `render.yaml` header documents Modal as canonical, Render as
   secondary/preview (already done in commit 265a27c).
3. Do NOT treat render.yaml as production cutover path.

---

## Step 1 — Production Domain (Frontend) (G8 / P3.1)

Goal: Frontend on production domain, not Pages preview.

1. In Cloudflare dashboard, add custom domain to Pages project
   `quan-ly-kho-tra-sua`.
2. Or deploy to Cloudflare Workers Assets via `deploy-pages.yml`.
3. Update `ALLOWED_ORIGINS` in `render.yaml` and `.env.example` with
   production domain.
4. Verify: `curl https://<production-domain>/` returns 200.
5. Verify: frontend can call backend API (CORS configured).

Evidence to collect: Production domain URL, CORS test, frontend screenshot.

---

## Step 2 — AI Provider Enable (G9 / P3.3) — CRITICAL

Goal: `AI_PROVIDER=cloudflare` with actual credentials, AI endpoint working.

1. In Render dashboard (kho-tra-sua-fastapi service), set environment variables:
   - `CLOUDFLARE_ACCOUNT_ID`
   - `CLOUDFLARE_API_TOKEN`
2. These are already declared as `sync: false` in `render.yaml`
   (commit 5a88758 / ecda258).
3. Confirm `AI_PROVIDER=cloudflare` in render.yaml (already done).
4. Verify: `POST /ai/chat` returns grounded answer in Vietnamese.
5. Verify: `POST /ai/assess-request` returns heuristic assessment.

Evidence to collect: AI chat response screenshot, assess-request response.

---

## Step 3 — Backend Production SLA (P3.2)

Goal: Backend on environment with SLA, not Render free tier.

Option A — Render paid tier:
1. Upgrade Render service from free to paid.
2. Verify health endpoint `/api/v1/health/ready` returns 200.
3. Configure uptime monitoring.

Option B — Migrate to Modal (canonical):
1. Confirm Modal deployment is stable.
2. Update `deploy-pages.yml` to point to Modal production URL.
3. Verify API health.

Option C — Azure AKS:
1. Deploy FastAPI to AKS via ArgoCD.
2. Configure ingress, TLS, health probes.

Evidence to collect: Backend health endpoint 200, uptime monitor config.

---

## Step 4 — SMTP_USER Secret (MEDIUM)

Goal: Remove hardcoded email from render.yaml.

1. In Render dashboard, set `SMTP_USER` as `sync: false` secret.
2. Remove hardcoded `binhtan5734@gmail.com` from render.yaml envVars.
3. Verify: email notifications still work after restart.

Evidence to collect: Render dashboard secret config, email test.

---

## Step 5 — E2E Tests Full Suite (P3.5)

Goal: 100% test pass on production-like environment.

1. Backend: `cd backend && poetry run pytest tests/ -v --cov=app`
   - Target: full suite (was 988+ tests before, currently 2 demo tests)
2. Frontend: `cd frontend && flutter test`
   - Target: 355 tests pass
3. Run on production-like environment (not local dev).

Evidence to collect: Test coverage report, Flutter test output.

---

## Step 6 — ArgoCD GitOps Production (P3.6)

Goal: Migration job runs on production cluster.

1. Get AKS cluster kubeconfig.
2. Configure ArgoCD sync for `infra/k8s/base/migration-job.yaml`.
3. Verify: migration job runs successfully, Alembic `upgrade head`.
4. Verify: ArgoCD sync status = Healthy.

Evidence to collect: ArgoCD sync status, migration job logs.

---

## Step 7 — Monitoring & SLA Dashboard (P3.7)

Goal: API latency, error rate, AI latency visible.

1. Configure Prometheus/Grafana or uptime monitor.
2. Track: `/api/v1/health/ready` uptime, AI `/ai/chat` latency.
3. Configure alert on error rate threshold.

Evidence to collect: Dashboard screenshot, alert rule.

---

## Rollback

- Frontend domain issue: revert DNS to preview domain.
- AI provider issue: set `AI_PROVIDER=disabled` temporarily (fallback to
  heuristic/grounded responses).
- Backend SLA issue: fail back to Render preview or Modal.

---

## Sign-off checklist

- [ ] Production domain configured, frontend 200
- [ ] `CLOUDFLARE_ACCOUNT_ID` + `CLOUDFLARE_API_TOKEN` set in Render
- [ ] `POST /ai/chat` returns Vietnamese response
- [ ] Backend health endpoint 200 with SLA
- [ ] `SMTP_USER` moved to secret (not hardcoded)
- [ ] Full E2E test suite passes
- [ ] ArgoCD sync Healthy on production cluster
- [ ] Monitoring dashboard configured