# Observability Lab Evidence & Output Documentation

This directory contains real, live captured evidence from the local BankOps monitoring stack (`docker-compose.monitoring.yml`) executed during Milestone 4.

## Captured Artifacts Index

| File | Source / Scrape Endpoint | Job Name / Component | Description |
|------|--------------------------|----------------------|-------------|
| `prometheus-targets.json` | `http://localhost:9090/api/v1/targets` | `prometheus`, `otel-collector`, `bankops-api`, `bankops-worker` | Live Prometheus target discovery and scrape health states |
| `prometheus-up-metric.json` | `http://localhost:9090/api/v1/query?query=up` | All active Prometheus jobs | Live evaluation of `up` metric confirming Prometheus and OTel Collector are active (`1`) |
| `otel-collector-metrics.txt` | `http://localhost:8888/metrics` | `otelcol-contrib` v0.106.0 | Raw Prometheus-formatted internal telemetry metrics exported directly by OTel Collector |
| `loki-ready.txt` | `http://localhost:3100/ready` | `grafana/loki:2.9.7` | Readiness probe confirming ingester, querier, and storage rings initialized |
| `loki-query-response.json` | `http://localhost:3100/loki/api/v1/query?query={job="bankops-lab-audit"}` | `bankops-lab-audit` stream | Push (`POST /loki/api/v1/push`) and retrieve structured JSON log entry |
| `promtail-targets.json` | `http://localhost:9080/targets` | `docker-container-logs` | Active Promtail targets discovering local Docker container stdout/stderr streams |
| `grafana-datasources.json` | `http://localhost:3000/api/datasources` | Grafana Provisioning | Provisioned Prometheus (`http://prometheus:9090`) and Loki (`http://loki:3100`) datasources |
| `cloudflare-analytics.json` | Cloudflare GraphQL Analytics API | `workersInvocationsAdaptive` | Telemetry schema and invocation counters for `sop-worker-lab` |

## Metrics & Alerts Source Attribution

### 1. Prometheus Scrape Configuration
- **Configuration File**: `QuanLyKho/docker/prometheus.yml`
- **Global Evaluation Interval**: 15s (scrape interval: 15s)
- **Scrape Jobs**:
  - `prometheus`: `localhost:9090` (Self-scrape)
  - `otel-collector`: `otel-collector:8888` (OTel collector internal telemetry)
  - `bankops-api`: `api:8000/metrics` (FastAPI backend endpoints)
  - `bankops-worker`: `worker:8000/metrics` (Async worker instrumentation)

### 2. OpenTelemetry Collector Pipeline
- **Configuration File**: `QuanLyKho/docker/otel-collector-config.yaml`
- **Receivers**: OTLP gRPC (`0.0.0.0:4317`), OTLP HTTP (`0.0.0.0:4318`)
- **Exporters**: Prometheus (`0.0.0.0:8889`), Loki HTTP (`http://loki:3100/loki/api/v1/push`), Debug
- **Telemetry Server**: `0.0.0.0:8888/metrics`

### 3. Loki & Promtail Log Aggregation
- **Loki Config**: `QuanLyKho/docker/loki-config.yaml` (port 3100)
- **Promtail Config**: `QuanLyKho/docker/promtail-config.yaml` (port 9080)
- **Scrape Job**: `docker-container-logs` via `unix:///var/run/docker.sock`
- **Label Mappings**: container name, image, k8s component

### 4. Grafana Dashboards
- **Datasources File**: `QuanLyKho/docker/grafana/datasources.yml`
- **Dashboard File**: `QuanLyKho/docker/grafana/dashboards/bankops-dashboard.json`
- **Dashboard Title**: BankOps Observability Dashboard (ID: `bankops-overview`)
