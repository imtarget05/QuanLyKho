terraform {
  required_version = ">= 1.5"
  required_providers {
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "~> 2.20"
    }
    helm = {
      source  = "hashicorp/helm"
      version = "~> 2.12"
    }
  }
}

provider "kubernetes" {
  # Kết nối vào cluster AKS do AKS-SRE-Platform cấp tài nguyên (kubeconfig /
  # OIDC / Azure AD). Không hardcode credential; lấy từ environment hoặc
  # Azure provider data source.
  load_config_file = var.kubeconfig_path != "" ? var.kubeconfig_path : false
  host             = var.kubernetes_cluster_endpoint
  client_certificate     = var.client_certificate
  client_key             = var.client_key
  cluster_ca_certificate = var.cluster_ca_certificate
  token                  = var.kubernetes_token
}

# Interop với AKS foundation (AKS-SRE-Platform): quanlykho chỉ sở hữu
# namespace + workload (Kustomize/ArgoCD); VNet, subnet, node pool,
# ingress controller và observability chung do platform sở hữu.
resource "kubernetes_namespace" "quanlykho" {
  metadata {
    name = var.platform_namespace
    labels = {
      "app.kubernetes.io/part-of" = "bankops-system"
      "platform"                  = "aks-foundation"
    }
  }
}

# ResourceQuota để định biên sử dụng tài nguyên của workload trong platform
# namespace (interop với foundation quota/policy).
resource "kubernetes_resource_quota" "quanlykho" {
  metadata {
    name      = "quanlykho-quota"
    namespace = kubernetes_namespace.quanlykho.metadata[0].name
  }
  spec = {
    hard = {
      "requests.cpu"     = var.cluster_request_cpu
      "requests.memory"  = var.cluster_request_memory
      "limits.cpu"       = var.cluster_limit_cpu
      "limits.memory"    = var.cluster_limit_memory
      "pods"             = var.cluster_max_pods
    }
  }
}

# ArgoCD Application trỏ về overlay production của repo này. Hiệu lực khi
# ArgoCD controller chạy trong cùng cluster (do AKS-SRE-Platform cài đặt).
resource "kubernetes_manifest" "quanlykho_argocd_app" {
  manifest = {
    apiVersion = "argoproj.io/v1alpha1"
    kind       = "Application"
    metadata   = {
      name      = "quanlykho-production"
      namespace = var.argocd_namespace
    }
    spec = {
      project = var.argocd_project
      source = {
        repoURL = var.gitops_repo_url
        targetRevision = var.gitops_revision
        path        = "infra/k8s/overlays/production"
        kustomize = {}
      }
      destination = {
        server    = "https://kubernetes.default.svc"
        namespace = kubernetes_namespace.quanlykho.metadata[0].name
      }
      syncPolicy = {
        automated = {
          prune    = true
          selfHeal = true
        }
        syncOptions = ["CreateNamespace=true"]
      }
    }
  }
}
