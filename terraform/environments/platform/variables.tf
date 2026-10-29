variable "platform_namespace" {
  description = "Namespace AKS mà workload QuanLyKho được đặt trong nền tảng platform"
  type        = string
  default     = "quanlykho"
}

variable "argocd_namespace" {
  description = "Namespace ArgoCD cài sẵn do AKS-SRE-Platform sở hữu"
  type        = string
  default     = "argocd"
}

variable "argocd_project" {
  description = "AppProject ArgoCD dùng cho QuanLyKho (do platform tạo)"
  type        = string
  default     = "default"
}

variable "gitops_repo_url" {
  description = "URL repo GitOps chứa infra/k8s (QuanLyKho repo)"
  type        = string
}

variable "gitops_revision" {
  description = "SHA/revision của GitOps repo được pin (đầu ra gitops-pin-overlay)"
  type        = string
  default     = "main"
}

variable "kubeconfig_path" {
  description = "Đường dẫn kubeconfig cluster AKS foundation"
  type        = string
  default     = ""
}

variable "kubernetes_cluster_endpoint" {
  description = "Endpoint API server cluster AKS"
  type        = string
  default     = ""
}

variable "client_certificate" {
  description = "Client certificate (PEM) khi dùng cert-based auth"
  type        = string
  default     = ""
}

variable "client_key" {
  description = "Client private key (PEM) khi dùng cert-based auth"
  type        = string
  default     = ""
}

variable "cluster_ca_certificate" {
  description = "Cluster CA certificate (PEM)"
  type        = string
  default     = ""
}

variable "kubernetes_token" {
  description = "Bearer token khi dùng OIDC/Azure AD (không hardcode secret)"
  type        = string
  default     = ""
  sensitive   = true
}

variable "cluster_request_cpu" {
  description = "Quota CPU request của namespace"
  type        = string
  default     = "4"
}

variable "cluster_request_memory" {
  description = "Quota memory request của namespace"
  type        = string
  default     = "8Gi"
}

variable "cluster_limit_cpu" {
  description = "Quota CPU limit của namespace"
  type        = string
  default     = "8"
}

variable "cluster_limit_memory" {
  description = "Quota memory limit của namespace"
  type        = string
  default     = "16Gi"
}

variable "cluster_max_pods" {
  description = "Số pod tối đa trong namespace"
  type        = string
  default     = "50"
}
