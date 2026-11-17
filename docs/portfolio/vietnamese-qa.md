# Vietnamese Q&A — Portfolio Defense (QuanLyKho / DevOps + AI)

Câu trả lời bằng tiếng Việt, dùng cho phỏng vấn Dev Backend / DevOps / AI-MLOps.

## 1. Dev / Backend

**Q: Hệ thống xử lý idempotency như thế nào?**
A: Dùng IdempotencyMiddleware (`backend/app/api/middleware/idempotency.py`). Client gửi header `Idempotency-Key`; API kiểm tra trong bảng `idempotency_keys`, nếu key đã xử lý thì trả lại kết quả cũ, không thực hiện lại nghiệp vụ. Đảm bảo an toàn khi client retry do timeout/mất mạng.

**Q: Outbox pattern được triển khai ở đâu?**
A: Bảng `outbox_events` lưu sự kiện sau mỗi commit transaction. Worker (`app/worker.py`) đọc outbox và publish lên Redis pub/sub (hoặc SSE) để các dịch vụ khác phản ứng. Giúp đảm bảo sự nhất quán eventual giữa DB và các hệ thống downstream.

**Q: Migration DB được quản lý như thế nào?**
A: Alembic (24 phiên bản trong `backend/alembic/versions/`). Mỗi migration có kiểm tra idempotent qua `op.get_bind()` + `insp.get_columns()` trước khi cột/thay đổi schema. Trong K8s, migration chạy qua Job (`alembic upgrade head`) trước khi API khởi động.

**Q: Làm sao đảm bảo type safety trong Python?**
A: Pydantic v2 cho request/response schema, SQLAlchemy 2.0 `Mapped`/`mapped_column` cho ORM model, ruff (0.17.0) để kiểm tra kiểu và import order. CI chạy ruff + pytest coverage.

## 2. DevOps / Platform

**Q: Helm chart có gì cho QuanLyKho?**
A: `infra/helm/bankops/` chứa Chart.yaml, values.yaml (base), values-dev/staging/prod.yaml (env-based), templates: Deployment api/worker, Service, ConfigMap, Secret, HPA, Ingress, HTTPRoute, ServiceMonitor, PDB, NetworkPolicy, Argo Rollouts (canary), Migration Job, Backup CronJob. `helm lint` pass.

**Q: GitOps được triển khai như thế nào?**
A: ArgoCD AppProject `bankops-portfolio` + 3 Application (dev/staging/prod), syncPolicy automated với prune + selfHeal, CreateNamespace=true. ArgoCD tự kéo Helm chart từ Git repo và prune resource khi xoá trong values.

**Q: Canary release được làm như thế nào?**
A: Argo Rollouts trong Helm chart (`rollouts.enabled: true` ở prod), chiến lược canary: 20% → 50% → 100%, mỗi bước pause 30s, có analysis template success-rate. Nếu lỗi thì ArgoRollout tự rollback về bản ổn định.

**Q: Observability end-to-end có những thành phần?**
A: OpenTelemetry tracer/metric exporter (OTLP HTTP) nối API → OTel Collector → Prometheus (metrics) + Tempo (traces) + Loki (logs). Grafana dashboard `bankops-sli-slo` hiển thị SLI/SLO (latency p95, error rate, saturation). Alert rules trong `infra/observability/alert-rules.yaml`.

**Q: CI security gates có gì?**
A: Trivy (fs + image), gitleaks (secret), pip-audit (Python dependency), npm-audit (Node), SBOM qua Syft, ký ảnh qua Cosign, helm-lint + kubeconform validate manifest.

**Q: IaC cung cấp infra như thế nào?**
A: Terraform Azure (`infra/terraform/`): Resource Group, AKS (3 node), PostgreSQL Flexible Server, Redis Cache, Storage Account. Có tfvars cho dev/staging/prod. `terraform validate` success.

**Q: Policy as Code có những rule?**
A: OPA (`policies.rego`) và Kyverno (`pod-security.yaml`): từ chối image tag `:latest`, bắt buộc `runAsNonRoot=true`, bắt buộc resource limits trên mọi container.

**Q: Disaster Recovery cam kết gì?**
A: RPO ≤ 5 phút (WAL archiving), RTO ≤ 15 phút (lỗi dữ liệu) / ≤ 30 phút (sập cluster). Backup CronJob hàng ngày 02:00 UTC (pg_dump + SHA-256 + GPG AES-256 + upload R2/S3 WORM). Có script restore + drill test tháng.

## 3. AI / MLOps

**Q: Drift detection tính toán như thế nào?**
A: `ai/drift_detection.py` tính PSI (Population Stability Index) cho biến phân loại và KS (Kolmogorov-Smirnov) cho biến liên tục, so sánh phân phối reference vs current. Ngưỡng mặc định PSI ≥ 0.2 hoặc KS ≥ 0.2 coi là drift. Kết quả ghi JSON report.

**Q: Model registry làm gì?**
A: `ai/model_registry.py` lưu từng phiên bản model (version, artifact_uri, sha256, metrics, alias staging/production/archived). Có `register`, `promote`, `get_latest`, `production_ready` (kiểm tra quality gate trước khi đưa production).

**Q: Retraining được kích hoạt tự động như thế nào?**
A: Airflow DAG `drift_monitor_dag` (chạy mỗi 30 phút) gọi drift detection, nếu phát hiện drift thì trigger DAG `model_retrain_pipeline` qua Airflow REST API. Retrain pipeline build dataset → submit training → poll → verify adapter URI/SHA-256/quality gate.

**Q: AI eval chạy trong CI như thế nào?**
A: SmartDoc có `eval.yml`: fixture smoke (mock stack), live benchmark (real Qdrant + LLM), LLM-as-judge (llm_judge.py), golden_dataset.json (30+ câu hỏi), Hit@K / MRR, hallucination rate. QuanLyKho có `scripts/run_ai_eval.py` (Recall@K + citation accuracy).

**Q: Guardrails / HITL có trong chỗ nào?**
A: SmartDoc agent có HITL (human-in-the-loop) và guardrails qua `agent/hitl.py`, `agent/security/`. QuanLyKho Langfuse tracing được mask dữ liệu nhạy cảm (`mask_sensitive_data`).

## 4. Cloud / Infra

**Q: Portfolio chạy trên cloud nào?**
A: QuanLyKho → Azure AKS (Terraform). SmartDoc → Azure Container Apps + Neon Postgres + Cloudflare R2. IncidentIQ → Cloudflare Workers + D1 + Vectorize (Terraform Cloudflare). Multi-cloud có thể mở rộng qua provider aws/gcp đã khai báo trong `required_providers`.

**Q: Secret management như thế nào?**
A: Không hardcode secret. K8s Secret (template CHANGE_ME) được override bằng ExternalSecrets / SOPS / env thực tế. CI không commit `.env` (job secret-guard chặn). Cloudflare Wrangler secrets cho IncidentIQ.
