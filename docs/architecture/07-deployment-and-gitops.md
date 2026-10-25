# 07 — Deployment & GitOps Independent Delivery Contract

## 1. Nguyên Tắc Độc Lập Triển Khai (Independent Delivery)
QuanLyKho là sản phẩm hoàn chỉnh độc lập (Standalone Product), không phụ thuộc vào `FlashSale-Backend` hay nền tảng `AKS-SRE-Platform` để build, test hoặc chạy nghiệp vụ:
- **Local Dev**: Chạy đầy đủ qua `docker-compose up` với database PostgreSQL 16 và container app/worker/frontend.
- **CI / Testing**: Chạy qua `poetry run pytest tests -q` với database test riêng biệt.
- **Kubernetes / AKS Target**: Triển khai trong namespace `quanlykho`, sở hữu StatefulSet database riêng (`bankops-postgres`), migrations (`bankops-migration`), secrets (`bankops-secrets`) và backup cronjob (`bankops-backup-db`).

## 2. Ranh Giới Dữ Liệu & Hạ Tầng
- **Tách biệt hoàn toàn**: Tuyệt đối không kết nối chéo sang PostgreSQL của `flashsale`. Mọi bảng nghiệp vụ (`inv_*`, `cash_*`, `iam_*`, `etl_*`) nằm trong database `bankops` thuộc namespace `quanlykho`.
- **Hợp đồng tích hợp**: Tích hợp với OpsBridge / FlashSale thông qua Webhook HMAC ký số (`GoodsReceiptConfirmed`), tuân thủ Two-Man Rule (Maker-Checker) và FEFO lot expiration.

## 3. GitOps Manifests
- **Base Manifests**: `infra/k8s/base/`
  - `postgres.yaml`: PostgreSQL 16 StatefulSet + Service (non-root, readOnlyRootFilesystem, 1Gi PVC).
  - `migration-job.yaml`: PreSync hook chạy `alembic upgrade head`.
  - `deployment-api.yaml`: Uvicorn / FastAPI server.
  - `deployment-worker.yaml`: Async job processor.
  - `cronjob-backup.yaml`: Automated encrypted S3/R2 backup.
- **Overlays**:
  - `infra/k8s/overlays/production`: Pin image tags, cấu hình HTTPRoute và Cloudflare Tunnel.
- **Argo CD Application**: `infra/argocd/quanlykho-application.yaml`
  - Repository nguồn: `https://github.com/imtarget05/QuanLyKho.git`
  - Destination namespace: `quanlykho`
