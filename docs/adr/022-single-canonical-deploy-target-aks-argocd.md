# ADR 022: Single Canonical Deploy Target — AKS + ArgoCD (Render/Modal deprecated)

## Status
Accepted

## Date
2026-10-29

## Related
docs/11-devops.md, infra/k8s/, infra/argocd/, render.yaml, infra/modal/

---

## Context

QuanLyKho backend hiện có nhiều kênh triển khai sản xuất song song, dẫn đến
sự chênh lệch cấu hình, secret và kiểm soát phiên bản:

1. **Render** (`render.yaml`): dịch vụ Docker `kho-tra-sua-fastapi`, plan free,
   secret được quản lý trên bảng điều khiển Render (không trong Git), không có
   GitOps pipeline rõ ràng.
2. **Modal** (`infra/modal/`): triển khai LLM/API server riêng biệt, ngoài toàn
   bộ quan sát và CI/CD chung của hệ thống.
3. **ArgoCD + AKS** (`infra/argocd/`, `infra/k8s/`): Application `quanlykho-application.yaml`,
   AppProject `appproject.yaml`, manifests Kustomize (`infra/k8s/base`, `overlays/production`),
   migration Job làm PreSync hook. Đây là kênh duy nhất đã được kiểm soát qua GitOps.

Việc giữ 3 target đồng thời làm murky nguồn sự thật (source of truth): secret,
phiên bản image, cài đặt tính năng (AI_PROVIDER, v.v.) bị tách rải giữa Render
dashboard, Modal cli và Git. Khi Rollback cần phải thao tác trên 3 nền tảng,
tăng sai sót và thời gian khôi phục (MTTR).

## Decision

1. **AKS + ArgoCD là target sản xuất duy nhất (single canonical deploy target)**
   của QuanLyKho backend. Mọi thay đổi sản xuất phải đi qua Git:
   `infra/argocd/` (Application/AppProject), `infra/k8s/` (Kustomize base +
   overlays/production), `backend/Dockerfile`, `backend/poetry.lock`.
   ArgoCD sync → AKS. Alembic migration chạy qua `migration-job.yaml` làm
   ArgoCD `PreSync` hook (ADR 0007).
2. **Render bị ngừng sử dụng (deprecate)**: `render.yaml` đánh dấu deprecated,
   không được triển khai sản xuất mới. Secret trên Render dashboard sẽ bị xóa
   sau khi xác nhận ArgoCD sync ổn định.
3. **Modal bị ngừng sử dụng (deprecate)**: `infra/modal/` chỉ giữ lại cho mục
   đích thí nghiệm LLM nội bộ, không được dùng làm target phục vụ traffic
   sản xuất của API Quản Lý Kho.

## Consequences

- **Positive**:
  - Một nguồn sự thật duy nhất (Git + ArgoCD) cho image, secret, cấu hình.
  - Rollback/rollback-forward nhất quán qua ArgoCD rollback + Helm/Kustomize.
  - Triển khai độc lập, có thể kiểm thử, khôi phục nhanh (độc lập CSDL theo ADR 0007).
  - Giảm bề mặt tấn công: không còn secret sống bên ngoài Git (Render dashboard).
- **Negative / Trade-offs**:
  - Cần di chuyển secret từ Render dashboard vào Kubernetes Secret / SealedSecret
    trước khi tắt Render.
  - Modal LLM server cần được đóng gói thành workload AKS (hoặc gọi qua API
    bên ngoài) nếu tính năng AI cần chạy sản xuất; hiện AI_PROVIDER=disabled
    trên production (xem render.yaml).

## Approval

| Role | Name | Signature | Date |
|---|---|---|---|
| Architect | | | |
| Platform Lead | | | |
| Security Lead | | | |
| Backend Lead | | | |

