# ── Azure Key Vault (Single source of truth for secrets on Azure) ───────────────
data "azurerm_client_config" "current" {}

resource "azurerm_key_vault" "secrets" {
  name                = "kv-${var.resource_group_name}"
  location            = var.location
  resource_group_name = azurerm_resource_group.main.name
  sku_name            = "standard"
  tenant_id           = data.azurerm_client_config.current.tenant_id
  tags                = var.common_tags
}

# Access policy: AKS cluster system-assigned managed identity can read secrets
resource "azurerm_key_vault_access_policy" "aks_identity" {
  key_vault_id = azurerm_key_vault.secrets.id
  tenant_id    = data.azurerm_client_config.current.tenant_id
  object_id    = azurerm_kubernetes_cluster.main.identity.0.principal_id

  secret_permissions = [
    "Get",
    "List",
  ]
}

# ── Helm release: SealedSecrets controller (Bitnami) ────────────────────────────
resource "helm_release" "sealed_secrets" {
  name       = "sealed-secrets"
  repository = "https://bitnami-labs.github.io/sealed-secrets"
  chart      = "sealed-secrets"
  version    = "2.15.0"
  namespace  = "kube-system"
  create_namespace = true

  set {
    name  = "fullnameOverride"
    value = "sealed-secrets"
  }

  set {
    name  = "createCustomResource"
    value = "true"
  }

  depends_on = [
    azurerm_kubernetes_cluster.main,
  ]
}

# ── Helm release: External Secrets Operator ─────────────────────────────────────
resource "helm_release" "external_secrets" {
  name       = "external-secrets"
  repository = "https://external-secrets.github.io/kubernetes-external-secrets/"
  chart      = "external-secrets"
  version    = "0.10.0"
  namespace  = "external-secrets"
  create_namespace = true

  set {
    name  = "installCRDs"
    value = "true"
  }

  set {
    name  = "replicaCount"
    value = "1"
  }

  depends_on = [
    azurerm_kubernetes_cluster.main,
    helm_release.sealed_secrets,
  ]
}

# ── Kubernetes SecretStore: Azure Key Vault provider for ExternalSecrets ────────
resource "kubernetes_secret_v1" "eso_credentials" {
  metadata {
    name      = "eso-azure-credentials"
    namespace = "external-secrets"
  }

  data = {
    AZURE_TENANT_ID     = data.azurerm_client_config.current.tenant_id
    AZURE_CLIENT_ID     = azurerm_kubernetes_cluster.main.identity.0.principal_id
    AZURE_CLIENT_SECRET = ""  # system-assigned MI, no client secret needed
    AZURE_SUBSCRIPTION_ID = data.azurerm_client_config.current.subscription_id
  }
}

# ── ExternalSecret: QuanLyKho production secrets synced from Azure Key Vault ────
resource "kubernetes_secret_v1" "bankops_external_secret" {
  metadata {
    name      = "bankops-external-secrets"
    namespace = var.namespace
  }

  data = {
    "bankops-external-secret.yaml" = jsonencode({
      apiVersion = "external-secrets.io/v1beta1"
      kind       = "ExternalSecret"
      metadata = {
        name      = "bankops-external-secrets"
        namespace = var.namespace
      }
      spec = {
        secretStoreRef = {
          name = "bankops-secret-store"
          kind = "SecretStore"
        }
        target = {
          name = "bankops-secrets"
          creationPolicy = "Owner"
        }
        data = [
          {
            secretKey = "DATABASE_URL"
            remoteRef = {
              key = "bankops/DATABASE_URL"
            }
          },
          {
            secretKey = "DB_PASSWORD"
            remoteRef = {
              key = "bankops/DB_PASSWORD"
            }
          },
          {
            secretKey = "BANKOPS_SIGNING_KEY"
            remoteRef = {
              key = "bankops/BANKOPS_SIGNING_KEY"
            }
          },
          {
            secretKey = "BANKOPS_SESSION_SECRET"
            remoteRef = {
              key = "bankops/BANKOPS_SESSION_SECRET"
            }
          },
        ]
      }
    })
  }
}

# ── SecretStore (Azure Key Vault) for bankops namespace ─────────────────────────
resource "kubernetes_secret_v1" "bankops_secret_store" {
  metadata {
    name      = "bankops-secret-store"
    namespace = var.namespace
  }

  data = {
    "bankops-secret-store.yaml" = jsonencode({
      apiVersion = "external-secrets.io/v1beta1"
      kind       = "SecretStore"
      metadata = {
        name      = "bankops-secret-store"
        namespace = var.namespace
      }
      spec = {
        provider = {
          azurekeyvault = {
            vaultName = azurerm_key_vault.secrets.name
            auth = {
              workloadIdentity = {
                clientID = azurerm_kubernetes_cluster.main.identity.0.principal_id
                tenantID = data.azurerm_client_config.current.tenant_id
              }
            }
          }
        }
      }
    })
  }
}

# ── Outputs ─────────────────────────────────────────────────────────────────────
output "key_vault_name" {
  value     = azurerm_key_vault.secrets.name
  sensitive = false
}

output "key_vault_uri" {
  value     = azurerm_key_vault.secrets.vault_uri
  sensitive = false
}