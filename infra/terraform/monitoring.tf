# ── Namespace: monitoring ───────────────────────────────────────────────────────
resource "kubernetes_namespace" "monitoring" {
  metadata {
    name = "monitoring"
    labels = {
      "monitoring" = "enabled"
    }
  }
}

# ── Helm release: Prometheus Community (kube-prometheus-stack) ─────────────────
resource "helm_release" "kube_prometheus_stack" {
  name       = "kube-prometheus-stack"
  repository = "https://prometheus-community.github.io/helm-charts"
  chart      = "kube-prometheus-stack"
  version    = "59.0.0"
  namespace  = kubernetes_namespace.monitoring.metadata.0.name
  create_namespace = false

  set {
    name  = "prometheus.prometheusSpec.podMonitorNamespaceSelector.matchLabels.monitoring"
    value = "enabled"
  }

  set {
    name  = "prometheus.prometheusSpec.serviceMonitorNamespaceSelector.matchLabels.monitoring"
    value = "enabled"
  }

  set {
    name  = "grafana.enabled"
    value = "true"
  }

  set {
    name  = "prometheus-node-exporter.enabled"
    value = "true"
  }

  set {
    name  = "kube-state-metrics.enabled"
    value = "true"
  }

  set {
    name  = "alertmanager.enabled"
    value = "true"
  }

  set {
    name  = "prometheus.prometheusSpec.retention"
    value = "15d"
  }

  set {
    name  = "prometheus.prometheusSpec.storageSpec.volumeClaimTemplate.spec.accessModes[0]"
    value = "ReadWriteOnce"
  }

  set {
    name  = "prometheus.prometheusSpec.storageSpec.volumeClaimTemplate.spec.resources.requests.storage"
    value = "8Gi"
  }

  depends_on = [
    kubernetes_namespace.monitoring,
  ]
}

# ── Helm release: Grafana Loki ──────────────────────────────────────────────────
resource "helm_release" "loki" {
  name       = "loki"
  repository = "https://grafana.github.io/loki/charts"
  chart      = "loki-stack"
  version    = "2.9.0"
  namespace  = kubernetes_namespace.monitoring.metadata.0.name
  create_namespace = false

  set {
    name  = "loki.enabled"
    value = "true"
  }

  set {
    name  = "promtail.enabled"
    value = "true"
  }

  set {
    name  = "grafana.enabled"
    value = "false"
  }

  set {
    name  = "loki.persistence.enabled"
    value = "true"
  }

  set {
    name  = "loki.persistence.size"
    value = "10Gi"
  }

  depends_on = [
    kubernetes_namespace.monitoring,
    helm_release.kube_prometheus_stack,
  ]
}

# ── Outputs ─────────────────────────────────────────────────────────────────────
output "monitoring_namespace" {
  value = kubernetes_namespace.monitoring.metadata.0.name
}

output "prometheus_release" {
  value = helm_release.kube_prometheus_stack.name
}

output "loki_release" {
  value = helm_release.loki.name
}