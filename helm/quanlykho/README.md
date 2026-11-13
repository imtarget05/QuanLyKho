# QuanLyKho Helm chart

Production-grade Helm chart for the QuanLyKho (Kho Trà Sữa) FastAPI backend.

Values are sourced from the repo's existing raw manifests (`infra/k8s/base/*`,
`backend/k8s/model-serving.yaml`, `.github/workflows/deploy.yml`, root
`Dockerfile`) — image `ghcr.io/imtarget05/quanlykho/quanlykho-api`, port 8000,
UID 10001, probes `/api/v1/health/live` and `/api/v1/health/ready`.

## What the chart deploys

| Object | Notes |
| --- | --- |
| `Deployment` (backend) | 2 replicas default, non-root (10001), resources, live/readiness probes, `env` from values + `envFrom` secretRef |
| `Service` | ClusterIP, port 8000 |
| `HorizontalPodAutoscaler` | Conditional (`autoscaling.enabled`), CPU utilization target |
| `Ingress` | Conditional (`ingress.enabled`), nginx class, cert-manager + timeout annotations reused from `infra/k8s/base/ingress.yaml` |
| `Job` (migration) | Helm hook `pre-install,pre-upgrade` weight 1, `alembic upgrade head`, `restartPolicy: Never` |
| `ServiceAccount` | Token not automounted |

**No Secrets are created by the chart.** The backend reads its secret env
(`DATABASE_URL`, `REDIS_URL`, `BANKOPS_SIGNING_KEY`, `BANKOPS_SESSION_SECRET`,
`SMTP_USER`, `SMTP_PASSWORD`, `CLOUDFLARE_ACCOUNT_ID`, `CLOUDFLARE_API_TOKEN`)
from an externally provisioned Secret referenced via
`secrets.existingSecret`. Provision it per cluster with SealedSecrets /
External Secrets / `kubectl create secret` — never commit values.

PostgreSQL 16 and Redis are external dependencies (see
`externalDatabase` / `externalRedis` in values.yaml — placeholders only; the
URLs live in the Secret).

## Install

```bash
# DEV — 1 replica, no ingress, no HPA
helm install quanlykho-dev ./helm/quanlykho \
  -n quanlykho --create-namespace \
  -f ./helm/quanlykho/values-dev.yaml

# STAGING — HPA (2–4), ingress, staging secret
helm install quanlykho-staging ./helm/quanlykho \
  -n quanlykho --create-namespace \
  -f ./helm/quanlykho/values-staging.yaml \
  --set ingress.host=quanlykho-staging.<real-cluster-host>

# PROD — HPA (2–6), ingress, prod secret
helm install quanlykho-prod ./helm/quanlykho \
  -n quanlykho --create-namespace \
  -f ./helm/quanlykho/values-prod.yaml \
  --set ingress.host=<real-prod-host>
```

Upgrades run `alembic upgrade head` first via the pre-upgrade hook:

```bash
helm upgrade quanlykho-prod ./helm/quanlykho -f ./helm/quanlykho/values-prod.yaml \
  --set image.tag=<sha-tag>
```

> **Ingress host note.** The default hosts (`quanlykho-*.example.com`) and the
> host in `values-prod.yaml` are placeholders. The real production domain
> `quan-ly-kho-tra-sua.tanmainguyenbinh.workers.dev` is served by **Cloudflare
> Workers**, which is outside this chart's scope; the actual cluster ingress
> host must be set per environment with `--set ingress.host=...` (or a cluster
> values overlay).

## Render / verify locally

```bash
helm lint ./helm/quanlykho
helm template quanlykho ./helm/quanlykho -f ./helm/quanlykho/values-prod.yaml
helm template quanlykho ./helm/quanlykho -f ./helm/quanlykho/values-dev.yaml
```

## ArgoCD (future GitOps wave)

The repo already has ArgoCD applications (`infra/argocd/*.yaml`) consuming
kustomize from `infra/k8s/overlays/`. To switch this app to the chart later,
add an Application like:

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: quanlykho-helm
  namespace: argocd
spec:
  project: portfolio
  source:
    repoURL: "https://github.com/imtarget05/QuanLyKho.git"
    targetRevision: main
    path: helm/quanlykho
    helm:
      valueFiles:
        - values-prod.yaml
      parameters:
        - name: ingress.host
          value: <real-prod-host>
        - name: image.tag
          value: <sha-tag>
  destination:
    server: "https://kubernetes.default.svc"
    namespace: quanlykho
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
    syncOptions:
      - CreateNamespace=true
```

ArgoCD ignores `helm.sh/hook` annotations for Helm hooks — the migration Job
becomes an Argo `PostSync`/`PreSync` concern once synced via ArgoCD; the repo's
existing ArgoCD PreSync migration pattern (see `backend/entrypoint.sh`
comments) remains the reference there.
