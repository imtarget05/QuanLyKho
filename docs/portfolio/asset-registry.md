# Portfolio Asset Registry

Tổng quan tài sản kỹ thuật của 3 repo trong portfolio `/Users/mainguyenbinhtan/Downloads/Phương Trang`.

## 1. QuanLyKho — Dev Backend + DevOps

| Asset | Loại | Đường dẫn | Mô tả | Evidence |
|-------|------|-----------|-------|----------|
| API FastAPI | Backend | `backend/app/main.py` | FastAPI app, OTel + Prometheus wiring, health endpoints | CI test 387 passed |
| Alembic migrations | DB migration | `backend/alembic/versions/` | 24 migration, idempotent | `alembic upgrade head` |
| Docker multi-stage | Container | `Dockerfile` | Python 3.11-slim, non-root user 10001 | CI build |
| Helm chart | K8s | `infra/helm/bankops/` | Chart + values dev/staging/prod, Rollouts canary | `helm lint` pass |
| ArgoCD Application | GitOps | `infra/argocd/` | AppProject + 3 Application (dev/staging/prod) | — |
| Terraform AKS | IaC | `infra/terraform/` | AKS + PG Flexible + Redis + Storage | `terraform validate` success |
| CI pipeline | CI/CD | `.github/workflows/ci.yml` | Trivy, gitleaks, pip-audit, SBOM, Cosign, k6, kubeconform | — |
| Observability | Observability | `infra/observability/` | OTel collector, Prometheus, Loki, Grafana, alert SLI/SLO | — |
| OPA/Kyverno | Policy as Code | `infra/policy/` | deny latest, non-root, resource limits | — |
| DR runbook + scripts | DR | `docs/20-backup-disaster-recovery-runbook.md`, `scripts/dr/` | RPO ≤5p, RTO ≤30p, drill tháng | — |
| k6 load test | Load test | `loadtest/k6-flashsale.js` | Flash-sale / inventory spike, error rate + p95 thresholds | CI job |
| Runbooks SLI/SLO | Runbook | `docs/runbooks/*.md` | latency, error rate, saturation, approval-stuck, crash-loop | — |

## 2. SmartDoc — Dev (Java + Fullstack) + AI + Cloud

| Asset | Loại | Đường dẫn | Mô tả | Evidence |
|-------|------|-----------|-------|----------|
| Spring Boot 4.1.2 | Backend | `backend/pom.xml` | Java 17, Flyway, Actuator, R2, Qdrant | Maven build |
| React 18 + TS | Frontend | `frontend/` | TypeScript, Playwright E2E | — |
| FastAPI agent/router | Agent | `agent/` | LangGraph, Corrective RAG, HITL | — |
| Airflow DAGs | MLOps | `airflow/dags/` | document_ingestion, model_retrain, drift_monitor | — |
| Model registry | MLOps | `agent/model_registry.py` | register/promote/get_latest/production_ready | — |
| Eval framework | AI eval | `eval/` | llm_judge, golden_dataset, run_live_benchmark, eval.yml | CI eval |
| K8s manifests | K8s | `k8s/` | qdrant, llm-router, redis, backend, agent, frontend | — |
| Azure IaC | IaC | `infra/terraform/`, `infra/bicep/` | Container Apps, storage, service bus | — |

## 3. IncidentIQ — DevOps/Platform + Serverless

| Asset | Loại | Đường dẫn | Mô tả | Evidence |
|-------|------|-----------|-------|----------|
| Cloudflare Workers | Serverless | `api/`, `wrangler.toml` | Python Workers, D1, Vectorize, Queues | wrangler dry-run |
| Terraform CF | IaC | `infrastructure/terraform/` | D1, Queues, KV | `terraform validate` |
| CI/CD | CI/CD | `.github/workflows/ci.yml` | Trivy, pip-audit, npm audit, SonarQube | — |
| MCP TypeScript | MCP | `mcp/` | TypeScript MCP server | `npm run typecheck` |

## 4. Chưa có / cần bổ sung (gap)

- Helm chart cho SmartDoc & IncidentIQ (chỉ QuanLyKho có)
- Multi-cloud deploy evidence (chỉ Azure TF có)
- Policy as Code cho SmartDoc/IncidentIQ (chỉ QuanLyKho OPA/Kyverno)
- DR drill thực tế đã chạy + video/screenshot (chỉ có runbook)
