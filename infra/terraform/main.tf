terraform {
  required_version = ">= 1.5.0"
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 3.102.0"
    }
    # AWS & GCP providers sẵn sàng kích hoạt khi cần chứng minh multi-cloud
    # (Option C). Hiện chỉ cấu hình Azure vì AKS cluster của portfolio đang chạy
    # trên Azure; giữ lại source để dễ bật thêm sau.
    # aws = { source = "hashicorp/aws", version = "~> 5.0" }
    # google = { source = "hashicorp/google", version = "~> 5.0" }

    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "~> 2.23"
    }
    helm = {
      source  = "hashicorp/helm"
      version = "~> 2.12"
    }
  }
}

provider "azurerm" {
  features {}
}

# ── Resource Group ────────────────────────────────────────────────────────────
resource "azurerm_resource_group" "main" {
  name     = var.resource_group_name
  location = var.location
  tags     = var.common_tags
}

# ── Log Analytics (cho Container Insights / AKS diagnostics) ──────────────────
resource "azurerm_log_analytics_workspace" "main" {
  name                = "law-${var.resource_group_name}"
  location            = var.location
  resource_group_name = azurerm_resource_group.main.name
  sku                 = "PerGB2018"
  retention_in_days   = 30
  tags                = var.common_tags
}

# ── AKS Cluster (3 node, hệ thống tối thiểu để fit node capacity) ─────────────
resource "azurerm_kubernetes_cluster" "main" {
  name                = "aks-${var.resource_group_name}"
  location            = var.location
  resource_group_name = azurerm_resource_group.main.name
  dns_prefix          = var.dns_prefix

  default_node_pool {
    name               = "agentpool"
    vm_size            = var.vm_size
    node_count         = 3
    vnet_subnet_id     = azurerm_subnet.aks.id
    enable_auto_scaling = false
    max_pods           = 30
    type               = "VirtualMachineScaleSets"
  }

  network_profile {
    network_plugin    = "azure"
    load_balancer_sku = "standard"
  }

  identity {
    type = "SystemAssigned"
  }

  tags = var.common_tags
}

# ── VNet + Subnet cho AKS ─────────────────────────────────────────────────────
resource "azurerm_virtual_network" "main" {
  name                = "vnet-${var.resource_group_name}"
  location            = var.location
  resource_group_name = azurerm_resource_group.main.name
  address_space       = ["10.0.0.0/16"]
  tags                = var.common_tags
}

resource "azurerm_subnet" "aks" {
  name                 = "aks-subnet"
  virtual_network_name = azurerm_virtual_network.main.name
  resource_group_name  = azurerm_resource_group.main.name
  address_prefixes     = ["10.0.1.0/24"]
  service_endpoints    = ["Microsoft.Storage"]
}

# ── Azure Database for PostgreSQL Flexible Server ─────────────────────────────
resource "azurerm_postgresql_flexible_server" "main" {
  name                = "pg-${var.resource_group_name}"
  location            = var.location
  resource_group_name = azurerm_resource_group.main.name
  administrator_login = var.pg_admin_user
  sku_name             = var.pg_sku
  storage_mb           = var.pg_storage_mb
  backup_retention_days = var.pg_backup_retention_days

  # Mặc định PostgreSQL Flexible Server tự tạo database `postgres`;
  # database ứng dụng (`bankops`) được tạo qua migration job sau khi cluster sẵn sàng.
  tags = var.common_tags
}

# ── Azure Cache for Redis ─────────────────────────────────────────────────────
resource "azurerm_redis_cache" "main" {
  name                = "redis-${var.resource_group_name}"
  location            = var.location
  resource_group_name = azurerm_resource_group.main.name
  capacity            = 1
  family              = "C"
  sku_name            = "Basic"
  enable_non_ssl_port = false
  minimum_tls_version = "1.2"
  tags                = var.common_tags
}

# ── Azure Storage Account (object storage, backup artifacts) ──────────────────
resource "azurerm_storage_account" "main" {
  name                     = var.storage_account_name
  resource_group_name      = azurerm_resource_group.main.name
  location                 = var.location
  account_tier             = "Standard"
  account_replication_type = "LRS"
  tags                     = var.common_tags
}

resource "azurerm_storage_container" "backups" {
  name                  = "backups"
  storage_account_name  = azurerm_storage_account.main.name
  container_access_type = "private"
}

# ── Outputs ───────────────────────────────────────────────────────────────────
output "kubernetes_cluster_id" {
  value     = azurerm_kubernetes_cluster.main.id
  sensitive = false
}

output "kubernetes_cluster_name" {
  value = azurerm_kubernetes_cluster.main.name
}

output "postgres_fqdn" {
  value     = azurerm_postgresql_flexible_server.main.fqdn
  sensitive = true
}

output "redis_hostname" {
  value     = azurerm_redis_cache.main.hostname
  sensitive = true
}

output "storage_account_name" {
  value = azurerm_storage_account.main.name
}

output "resource_group_name" {
  value = azurerm_resource_group.main.name
}

# ── Kubernetes provider (lấy kubeconfig từ AKS vừa tạo) ─────────────────────────
provider "kubernetes" {
  host                   = azurerm_kubernetes_cluster.main.kube_config.0.host
  client_certificate     = base64decode(azurerm_kubernetes_cluster.main.kube_config.0.client_certificate)
  client_key             = base64decode(azurerm_kubernetes_cluster.main.kube_config.0.client_key)
  cluster_ca_certificate = base64decode(azurerm_kubernetes_cluster.main.kube_config.0.cluster_ca_certificate)
}

provider "helm" {
  kubernetes {
    host                   = azurerm_kubernetes_cluster.main.kube_config.0.host
    client_certificate     = base64decode(azurerm_kubernetes_cluster.main.kube_config.0.client_certificate)
    client_key             = base64decode(azurerm_kubernetes_cluster.main.kube_config.0.client_key)
    cluster_ca_certificate = base64decode(azurerm_kubernetes_cluster.main.kube_config.0.cluster_ca_certificate)
  }
}
