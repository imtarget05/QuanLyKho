# Argo Rollouts — canary strategy for the QuanLyKho backend

Owner: imtarget05/QuanLyKho · Added 2026-11-13 (P0.6) · Branch: `feat/canary-rollouts`

## Why canary (maker-checker for traffic)

QuanLyKho's core business rule is **maker-checker**: nothing dangerous is committed
without an independent verification step. Releasing a new API build to all pods at
once (RollingUpdate) is the deployment equivalent of a maker committing straight to
production — one bad image, bad migration or latency regression hits 100% of traffic
instantly.

A canary rollout applies the same discipline to traffic:

| Release step | Maker-checker equivalent |
|---|---|
| 20% traffic, 2m pause | maker submits the change |
| 40% traffic + Prometheus analysis (error rate, p95) | checker reviews the diff against SLOs |
| 60% → 80% → 100% with pauses | staged commit after each checkpoint |

If the analysis fails (`failureLimit: 1`), the Rollout **aborts automatically** and
traffic snaps back to the previous ReplicaSet — no human pager required. Manual
abort with `kubectl argo rollouts abort` is also available (below).

## Files

| File | Purpose |
|---|---|
| `argo/rollouts-backend.yaml` | `Rollout` CRD replicating `infra/k8s/base/deployment-api.yaml` exactly (selector, probes, envFrom, resources) + canary steps: 20% → 2m → 40% → analysis → 60% → 2m → 80% → 5m → 100%. `minReadySeconds: 30`, `progressDeadlineSeconds: 600`. |
| `argo/analysis-template.yaml` | `AnalysisTemplate quanlykho-analysis`: successRate (`1 - 5xx/total`, ≥ 0.99) and p95Latency (≤ 1.0 s), both Prometheus-based with `failureLimit: 1`. Metric names match the app's own exporters (`quanlykho_http_requests_total`, `quanlykho_http_request_duration_seconds`) — see comments in the manifest. |
| `argo/kustomization.yaml` | Kustomize entry so ArgoCD (or `kubectl apply -k argo/`) can apply the folder. |

## Install the Argo Rollouts controller

```bash
kubectl create namespace argo-rollouts
kubectl apply -n argo-rollouts \
  -f https://github.com/argoproj/argo-rollouts/releases/latest/download/install.yaml
```

Or with Helm:

```bash
helm repo add argo https://argoproj.github.io/argo-helm
helm repo update
helm install argo-rollouts argo/argo-rollouts \
  --namespace argo-rollouts --create-namespace
```

Install the kubectl plugin (watch/promote/abort):

```bash
# macOS
brew install argo-rollouts
# Linux
curl -LO https://github.com/argoproj/argo-rollouts/releases/latest/download/kubectl-argo-rollouts-linux-amd64
chmod +x kubectl-argo-rollouts-linux-amd64 && sudo mv kubectl-argo-rollouts-linux-amd64 /usr/local/bin/kubectl-argo-rollouts
```

## Use it

```bash
# Apply the manifests (namespace defaults to wherever you apply, e.g. quanlykho)
kubectl apply -k argo/

# Watch the canary progress live (TUI)
kubectl argo rollouts get rollout bankops-api --watch

# Manually promote a paused step
kubectl argo rollouts promote bankops-api

# Manually abort — traffic returns to the previous ReplicaSet
kubectl argo rollouts abort bankops-api

# Undo/rollback to a previous revision
kubectl argo rollouts undo bankops-api
```

## Important caveat: setWeight needs a traffic router

`setWeight` only shifts real traffic when `trafficRouting` is configured
(nginx, ALB, Istio…). Without a router, each `setWeight` step is a traffic no-op
and the Rollout progresses by pod scaling; the **pause and analysis gates still
enforce safety** (that is the current safe default shipped here).

The repo's ingress is nginx (`infra/k8s/base/ingress.yaml`), so the natural
follow-up is: split the Service into `bankops-api-stable` / `bankops-api-canary`,
point the ingress at the stable Service, then uncomment the `trafficRouting.nginx`
block in `argo/rollouts-backend.yaml`.

## Integration with the existing GitOps stack

- The `Rollout` intentionally uses the **same name (`bankops-api`) and selector** as
  `infra/k8s/base/deployment-api.yaml` so it is a drop-in replacement. When you cut
  over: apply the Rollout, then remove `deployment-api.yaml` from
  `infra/k8s/base/kustomization.yaml` and let ArgoCD prune the old Deployment
  (running both simultaneously would split Service traffic across old and new pods).
- `infra/argocd/quanlykho-application.yaml` currently points at
  `infra/k8s/overlays/production`. To adopt the Rollout, either add `../../argo`
  (relative) to the overlay's `resources:` or point a second ArgoCD Application at
  the `argo/` path.
- **Helm chart follow-up:** this repo has no `helm/` directory on `origin/main`
  (only uncommitted local work), so no Helm wiring is included here. When
  `helm/quanlykho` lands, add a values flag `rollout.enabled` that switches the
  template between `Deployment` and `Rollout`:

  ```yaml
  # values.yaml (follow-up)
  rollout:
    enabled: true        # render a argoproj.io/v1alpha1 Rollout instead of apps/v1 Deployment
  ```
