environment = "production"
namespace   = "quanlykho"

image_repository = "ghcr.io/imtarget05/bankops-api"
image_tag        = "sha-${CI_COMMIT_SHORT_SHA:-latest}"
image_pull_policy = "IfNotPresent"

api_replicas    = 3
worker_replicas = 2
frontend_replicas = 2

postgres_persistence_enabled = true
postgres_storage_size        = "20Gi"

ingress_enabled       = true
ingress_host          = "bankops.yourbank.com"
network_policy_enabled = true

# PRODUCTION: secrets MUST be provided via CI/CD secrets or external secret
# manager. NEVER commit real values here.
# db_password = "<prod-db-password>"
# bankops_signing_key = "<prod-signing-key>"
# bankops_session_secret = "<prod-session-secret>"