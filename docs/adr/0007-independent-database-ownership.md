# ADR 0007: Independent Database & Deployment Ownership

## Status
Accepted

## Context
Previously in cluster deployments (e.g. on AKS or shared dev clusters), QuanLyKho was referencing a PostgreSQL database running inside the `flashsale` namespace (`postgres.flashsale.svc.cluster.local`). This created an operational coupling where:
1. Re-deploying, tearing down, or migrating FlashSale had the blast radius of disrupting QuanLyKho's database connectivity.
2. Database credentials, lifecycle, backup cronjobs, and schema migrations were shared across business boundary domains.
3. The platform violated Clean Architecture and Independent Deployability standards: QuanLyKho could not be independently tested, deployed, or rolled back without dependency on FlashSale infrastructure.

## Decision
1. **Dedicated Database StatefulSet**: QuanLyKho declares and owns its dedicated PostgreSQL 16 database within its own Kubernetes namespace (`quanlykho`).
   - Manifest: `infra/k8s/base/postgres.yaml` (StatefulSet `bankops-postgres` with Service `bankops-postgres:5432`).
   - Security: Runs as non-root (`uid: 70`, `gid: 70`), `readOnlyRootFilesystem: true` with `emptyDir` mounts for `/var/run/postgresql` and `/tmp`, and isolated PersistentVolumeClaim (1Gi).
2. **Dedicated Schema Migration Job**: QuanLyKho owns its Alembic database migration lifecycle via `infra/k8s/base/migration-job.yaml` as an ArgoCD `PreSync` hook.
3. **Dedicated Secrets & Backups**: QuanLyKho manages its own credentials (`DB_PASSWORD`, `DATABASE_URL`) via `bankops-secrets` and its automated backup cronjob (`bankops-backup-db`) targets its own database instance.
4. **Stable API Contracts**: Cross-service interaction between FlashSale/OpsBridge and QuanLyKho occurs strictly via authenticated, signed HTTP webhooks (`GoodsReceiptConfirmed`), not through shared database tables or shared instances.

## Consequences
- **Positive**:
  - Full operational independence: QuanLyKho can be deployed, scaled, backed up, and restored without touching FlashSale.
  - Zero blast-radius cross-contamination during maintenance.
  - Portable across any standard Kubernetes cluster (AKS, Kind, K3s, GKE).
- **Negative / Trade-offs**:
  - Requires dedicated persistent storage and compute allocations (~256Mi memory request) for QuanLyKho's PostgreSQL instance.
