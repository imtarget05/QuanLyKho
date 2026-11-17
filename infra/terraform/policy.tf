# ── OPA Gatekeeper (Policy as Code - Kubernetes admission control) ───────────────
# Installs OPA Gatekeeper via Helm to enforce cluster-wide policies:
#   - No 'latest' image tag
#   - runAsNonRoot required
#   - Resource limits required
#   - No privileged containers

resource "helm_release" "opa_gatekeeper" {
  name       = "gatekeeper"
  repository = "https://open-policy-agent.github.io/gatekeeper/charts"
  chart      = "gatekeeper"
  version    = "3.13.0"
  namespace  = "gatekeeper-system"
  create_namespace = true

  set {
    name  = "replicas"
    value = "1"
  }

  set {
    name  = "audit.interval"
    value = "60s"
  }

  set {
    name  = "audit.fromDeploymentAnnotations"
    value = "true"
  }

  depends_on = [
    azurerm_kubernetes_cluster.main,
    kubernetes_namespace.monitoring,
  ]
}

# ── Kyverno (alternative policy engine - more Kubernetes-native) ─────────────────
# Kyverno is installed as an alternative to OPA Gatekeeper. Both are available;
# use Kyverno for Kubernetes-native policy (validate/mutate/generate rules).

resource "helm_release" "kyverno" {
  name       = "kyverno"
  repository = "https://kyverno.github.io/kyverno/"
  chart      = "kyverno"
  version    = "3.2.0"
  namespace  = "kyverno"
  create_namespace = true

  set {
    name  = "replicaCount"
    value = "1"
  }

  set {
    name  = "webhookConfiguration.timeoutSeconds"
    value = "10"
  }

  set {
    name  = "backgroundController.replicas"
    value = "1"
  }

  depends_on = [
    azurerm_kubernetes_cluster.main,
    helm_release.opa_gatekeeper,
  ]
}

# ── Kyverno ClusterPolicy: Disallow latest tag + non-root + resource limits ──────
resource "kubernetes_manifest" "kyverno_pod_security_policy" {
  manifest = {
    apiVersion = "kyverno.io/v1"
    kind       = "ClusterPolicy"
    metadata   = {
      name = "bankops-pod-security"
      labels = tomap({
        "app.kubernetes.io/name"      = "kyverno"
        "app.kubernetes.io/component" = "policy"
      })
    }
    spec = {
      background         = true
      validationFailureAction = "enforce"
      rules = [
        {
          name = "no-latest-tag"
          match = {
            resources = {
              kinds = ["Deployment", "StatefulSet", "DaemonSet", "CronJob", "Job", "Rollout"]
            }
          }
          validate = {
            message = "Container images must not use 'latest' tag"
            pattern = {
              spec = {
                template = {
                  spec = {
                    containers = [
                      {
                        image = "!*:latest"
                      }
                    ]
                  }
                }
              }
            }
          }
        },
        {
          name = "require-non-root"
          match = {
            resources = {
              kinds = ["Deployment", "StatefulSet", "DaemonSet"]
            }
          }
          validate = {
            message = "Pod security context must set runAsNonRoot=true"
            pattern = {
              spec = {
                template = {
                  spec = {
                    securityContext = {
                      runAsNonRoot = true
                    }
                  }
                }
              }
            }
          }
        },
        {
          name = "require-resource-limits"
          match = {
            resources = {
              kinds = ["Deployment", "StatefulSet", "DaemonSet"]
            }
          }
          validate = {
            message = "All containers must define resource limits"
            pattern = {
              spec = {
                template = {
                  spec = {
                    containers = [
                      {
                        resources = {
                          limits = "*"
                        }
                      }
                    ]
                  }
                }
              }
            }
          }
        },
        {
          name = "no-privileged-containers"
          match = {
            resources = {
              kinds = ["Deployment", "StatefulSet", "DaemonSet", "Job", "CronJob"]
            }
          }
          validate = {
            message = "Containers must not run in privileged mode"
            pattern = {
              spec = {
                template = {
                  spec = {
                    containers = [
                      {
                        securityContext = {
                          privileged = false
                        }
                      }
                    ]
                  }
                }
              }
            }
          }
        }
      ]
    }
  }

  depends_on = [
    helm_release.kyverno,
  ]
}

# ── Outputs ─────────────────────────────────────────────────────────────────────
output "opa_gatekeeper_release" {
  value = helm_release.opa_gatekeeper.name
}

output "kyverno_release" {
  value = helm_release.kyverno.name
}