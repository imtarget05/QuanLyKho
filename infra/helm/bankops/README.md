# BankOps Helm Chart

Enterprise Inventory & Treasury Operations Platform — Helm chart for backend API,
background worker, frontend SPA, PostgreSQL, Alembic migration Job, and encrypted
backup CronJob.

## Chart structure

```
infra/helm/bankops/
├── Chart.yaml
├── values.yaml            # default (dev-friendly) values
├── values-dev.yaml        # dev / local overrides (imagePullPolicy: Never, no PVC)
├── values-staging.yaml    # staging overrides
├── values-production.yaml # production overrides
├── values-prod.yaml       # (removed — superseded by values-production.yaml)
├── .helmignore
├── README.md
└── templates/
    ├── _helpers.tpl
    ├── configmap.yaml
    ├── secret.yaml
    ├── service-api.yaml
    ├── service-frontend.yaml
    ├── postgres-service.yaml
    ├── postgres-statefulset.yaml
    ├── deployment-api.yaml
    ├── deployment-worker.yaml
    ├── deployment-frontend.yaml
    ├── migration-job.yaml
    ├── cronjob-backup.yaml
    ├── ingress.yaml
    ├── httproute.yaml
    ├── cloudflare-tunnel.yaml
    └── networkpolicy.yaml
```

## Quick start

### Dev / local (Kind, minikube, Docker Desktop)

```bash
helm upgrade --install bankops ./infra/helm/bankops \
  -f infra/helm/bankops/values-dev.yaml \
  -n quanlykho-dev --create-namespace
```

### Staging

```bash
helm upgrade --install bankops-staging ./infra/helm/bankops \
  -f infra/helm/bankops/values-staging.yaml \
  -n quanlykho-staging --create-namespace \
  --set image.tag=sha-$(git rev-parse --short HEAD) \
  --set-string secrets.DB_PASSWORD=<staging-db-password> \
  --set-string secrets.BANKOPS_SIGNING_KEY=<staging-signing-key>
```

### Production

```bash
helm upgrade --install bankops ./infra/helm/bankops \
  -f infra/helm/bankops/values-production.yaml \
  -n quanlykho --create-namespace \
  --set image.tag=sha-$(git rev-parse --short HEAD) \
  --set-string secrets.DB_PASSWORD=<prod-db-password> \
  --set-string secrets.BANKOPS_SIGNING_KEY=<prod-signing-key> \
  --set-string secrets.BANKOPS_SESSION_SECRET=<prod-session-secret>
```

> **Never commit real secrets.** Use `--set-string` at deploy time, or integrate
> an external secret manager (SealedSecrets, ExternalSecrets, Vault, AWS Secrets
> Manager, GCP Secret Manager).

## Terraform (IaC)

Provision the namespace and Helm release via Terraform:

```bash
cd infra/terraform/environments/dev
terraform init
terraform plan -var-file=terraform.tfvars
terraform apply -var-file=terraform.tfvars
```

## ArgoCD (GitOps)

Three ArgoCD `Application` manifests are provided in `infra/argocd/`:
- `bankops-helm-dev.yaml` → `quanlykho-dev`
- `bankops-helm-staging.yaml` → `quanlykho-staging`
- `bankops-helm-production.yaml` → `quanlykho`

They sync the Helm chart from `infra/helm/bankops` on every push to `main`.

## Security posture

- All Deployments run as non-root with `allowPrivilegeEscalation: false` and
  `capabilities.drop: [ALL]`.
- PostgreSQL runs as UID 70 with `readOnlyRootFilesystem: true`.
- Secrets are `Opaque` with placeholder values; real values must come from
  external secret management in production.
- NetworkPolicy (opt-in via `networkPolicy.enabled`) restricts API ingress to
  the ingress component only.
- Liveness/readiness probes are configured on all workloads.

## Values reference

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `namespace` | string | `quanlykho` | Target namespace |
| `image.repository` | string | `ghcr.io/imtarget05/bankops-api` | Backend image |
| `image.tag` | string | `latest` | Image tag |
| `image.pullPolicy` | string | `IfNotPresent` | Pull policy |
| `api.replicas` | int | `2` | API replica count |
| `api.resources` | object | see `values.yaml` | API resource requests/limits |
| `worker.replicas` | int | `1` | Worker replica count |
| `frontend.replicas` | int | `2` | Frontend replica count |
| `postgres.persistence.enabled` | bool | `false` | Enable PVC for Postgres |
| `postgres.persistence.size` | string | `1Gi` | PVC size |
| `ingress.enabled` | bool | `false` | Enable Ingress |
| `ingress.host` | string | `bankops.local` | Ingress host |
| `networkPolicy.enabled` | bool | `false` | Enable NetworkPolicy |
| `migration.enabled` | bool | `true` | Run Alembic migration Job |
| `backup.enabled` | bool | `true` | Enable encrypted backup CronJob |