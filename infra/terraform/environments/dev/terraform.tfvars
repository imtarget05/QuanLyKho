environment = "dev"
namespace   = "quanlykho-dev"

image_repository = "ghcr.io/imtarget05/bankops-api"
image_tag        = "local"
image_pull_policy = "Never"

api_replicas    = 1
worker_replicas = 1
frontend_replicas = 1

postgres_persistence_enabled = false
postgres_storage_size        = "1Gi"

ingress_enabled       = false
ingress_host          = "bankops.local"
network_policy_enabled = false

# Dev: Terraform will generate random secrets if not provided
# db_password = "dev-db-password-change-me"
# bankops_signing_key = "dev-signing-key-change-me"
# bankops_session_secret = "dev-session-secret-change-me"