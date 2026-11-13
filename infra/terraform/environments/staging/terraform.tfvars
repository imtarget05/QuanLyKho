environment = "staging"
namespace   = "quanlykho-staging"

image_repository = "ghcr.io/imtarget05/bankops-api"
image_tag        = "sha-${CI_COMMIT_SHORT_SHA:-latest}"
image_pull_policy = "IfNotPresent"

api_replicas    = 2
worker_replicas = 1
frontend_replicas = 1

postgres_persistence_enabled = true
postgres_storage_size        = "5Gi"

ingress_enabled       = true
ingress_host          = "staging.quanlykho.internal"
network_policy_enabled = false

# Staging: inject real secrets via CI/CD or secret manager
# db_password = "<staging-db-password>"
# bankops_signing_key = "<staging-signing-key>"
# bankops_session_secret = "<staging-session-secret>"