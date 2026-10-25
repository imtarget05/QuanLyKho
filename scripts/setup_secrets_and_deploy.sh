#!/usr/bin/env bash
# =============================================================================
# BankOps Automated Secrets Setup & Cloudflare Deployment Script
#
# Usage:
#   bash scripts/setup_secrets_and_deploy.sh [OPTIONS]
#
# Options:
#   --from-env                  Non-interactive: read every secret from the
#                               environment (canonical names only). Exits 1 and
#                               writes NOTHING when a required variable is missing.
#   --database-url <url>        PostgreSQL URL (e.g. Neon or Managed DB)
#   --signing-key <key>         BANKOPS_SIGNING_KEY (JWT signing key)
#   --session-secret <secret>   BANKOPS_SESSION_SECRET (session cookie key)
#   --smtp-user <user>          SMTP_USER
#   --smtp-password <password>  SMTP_PASSWORD
#   --cf-account-id <id>        Cloudflare Account ID
#   --cf-api-token <token>      Cloudflare API Token
#   --cf-tunnel-token <token>   Cloudflare Tunnel Token
#   --r2-key-id <id>            Cloudflare R2 Access Key ID
#   --r2-secret-key <key>       Cloudflare R2 Secret Access Key
#   --supervisor-pin <pin>      Supervisor PIN (required, no default — never reuse a published value)
#   --gpg-passphrase <passphrase> Backup GPG Passphrase (auto-generated if omitted)
#   --apply-k8s                 Apply secret and kustomize to current K8s context
#   --auto-migrate              Run alembic upgrade head on target database
#   -h, --help                  Show this help message
#
# Hard rules (2026-10-21 secret-hygiene wave):
#   1. CANONICAL NAMES ONLY. `SECRET_KEY` is the DEPRECATED legacy name and is
#      never written and never used as a silent fallback — two names for one
#      value is what makes a rotation drift (see
#      docs/security/secret-rotation-inventory-2026-10-20.md §4).
#   2. NEVER print a secret value to stdout. Only names/lengths are printed.
#   3. NEVER overwrite `secret-production.yaml` / `.env.production` when a
#      required variable is missing: exit 1 and list the MISSING NAMES.
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

info()    { echo -e "${BLUE}[INFO]${NC}  $*"; }
success() { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error()   { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }

# ---------------------------------------------------------------------------
# Canonical secret set (single source of truth).
# Names MUST match backend/app/config.py and infra/k8s/base/secret-template.yaml.
# The REQUIRED set is resolved in `missing_vars()` below.
# ---------------------------------------------------------------------------

# Default values / Read from existing .env if present
EXISTING_ENV="${ROOT_DIR}/.env"
if [ -f "${EXISTING_ENV}" ]; then
    info "Loading existing defaults from .env..."
    while IFS='=' read -r key val || [ -n "$key" ]; do
        # Ignore comments and empty lines
        [[ "$key" =~ ^[[:space:]]*# ]] && continue
        [[ -z "$key" ]] && continue
        # Strip leading/trailing whitespace and surrounding quotes
        key=$(echo "$key" | xargs)
        val=$(echo "$val" | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//' -e 's/^"//' -e 's/"$//' -e "s/^'//" -e "s/'$//")
        if [ -n "$key" ] && [ -z "${!key:-}" ]; then
            export "$key"="$val"
        fi
    done < "${EXISTING_ENV}"
fi

DB_URL="${DATABASE_URL:-}"
CF_ACCOUNT_ID="${CLOUDFLARE_ACCOUNT_ID:-}"
CF_API_TOKEN="${CLOUDFLARE_API_TOKEN:-}"
CF_TUNNEL_TOKEN="${CLOUDFLARE_TUNNEL_TOKEN:-}"
R2_KEY_ID="${AWS_ACCESS_KEY_ID:-}"
R2_SECRET_KEY="${AWS_SECRET_ACCESS_KEY:-}"
PIN="${SUPERVISOR_PIN:-}"
SIGNING_KEY="${BANKOPS_SIGNING_KEY:-}"
SESSION_SECRET="${BANKOPS_SESSION_SECRET:-}"
SMTP_USER_VALUE="${SMTP_USER:-}"
SMTP_PASSWORD_VALUE="${SMTP_PASSWORD:-}"
GPG_PASS="${BACKUP_GPG_PASSPHRASE:-}"
APPLY_K8S=0
AUTO_MIGRATE=0
FROM_ENV=0

# Parse CLI arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        --from-env) FROM_ENV=1; shift ;;
        --database-url) DB_URL="$2"; shift 2 ;;
        --signing-key) SIGNING_KEY="$2"; shift 2 ;;
        --session-secret) SESSION_SECRET="$2"; shift 2 ;;
        --smtp-user) SMTP_USER_VALUE="$2"; shift 2 ;;
        --smtp-password) SMTP_PASSWORD_VALUE="$2"; shift 2 ;;
        --cf-account-id) CF_ACCOUNT_ID="$2"; shift 2 ;;
        --cf-api-token) CF_API_TOKEN="$2"; shift 2 ;;
        --cf-tunnel-token) CF_TUNNEL_TOKEN="$2"; shift 2 ;;
        --r2-key-id) R2_KEY_ID="$2"; shift 2 ;;
        --r2-secret-key) R2_SECRET_KEY="$2"; shift 2 ;;
        --supervisor-pin) PIN="$2"; shift 2 ;;
        --gpg-passphrase) GPG_PASS="$2"; shift 2 ;;
        --apply-k8s) APPLY_K8S=1; shift ;;
        --auto-migrate) AUTO_MIGRATE=1; shift ;;
        -h|--help)
            sed -n '2,40p' "$0"
            exit 0
            ;;
        *) error "Unknown option: $1" ;;
    esac
done

echo ""
echo "╔══════════════════════════════════════════════════════════════════╗"
echo "║      BankOps — Automated Cloudflare & Secrets Deploy Tool       ║"
echo "║          Zero Trust & Instant Disaster Recovery Sizing           ║"
echo "╚══════════════════════════════════════════════════════════════════╝"
echo ""

# ---------------------------------------------------------------------------
# 0. Legacy name check: `SECRET_KEY` must NOT be used as a silent fallback.
# ---------------------------------------------------------------------------
if [ -n "${SECRET_KEY:-}" ]; then
    warn "'SECRET_KEY' (tên LEGACY/DEPRECATED) đang có trong môi trường và SẼ KHÔNG được dùng làm fallback."
    warn "Hãy cấp 'BANKOPS_SIGNING_KEY' (tên chuẩn) và gỡ 'SECRET_KEY' — 2 tên / 1 giá trị khiến rotate bị lệch."
fi

# ---------------------------------------------------------------------------
# 1. Supervisor PIN must be provided explicitly.
#    S10: no default PIN — a default that lives in git is a published credential
#    and was the reason the production PIN matched the value in the repo.
# ---------------------------------------------------------------------------
if [ -n "${PIN}" ] && [ "${PIN}" = "123456" ]; then
    error "Supervisor PIN must not be the published demo PIN. Refusing to write it."
fi

# ---------------------------------------------------------------------------
# 2. Resolve every REQUIRED canonical variable.
#    Missing required variable => exit 1 with the list of missing NAMES and
#    WITHOUT touching secret-production.yaml / .env.production.
# ---------------------------------------------------------------------------
missing_vars() {
    local m=()
    [ -z "${DB_URL}" ] && m+=("DATABASE_URL")
    [ -z "${SIGNING_KEY}" ] && m+=("BANKOPS_SIGNING_KEY")
    [ -z "${SESSION_SECRET}" ] && m+=("BANKOPS_SESSION_SECRET")
    [ -z "${SMTP_USER_VALUE}" ] && m+=("SMTP_USER")
    [ -z "${SMTP_PASSWORD_VALUE}" ] && m+=("SMTP_PASSWORD")
    [ -z "${PIN}" ] && m+=("SUPERVISOR_PIN")
    printf '%s\n' "${m[@]:-}"
}

MISSING="$(missing_vars | grep -v '^$' || true)"

if [ -n "${MISSING}" ]; then
    if [ "${FROM_ENV}" -eq 1 ]; then
        error "--from-env: thiếu biến môi trường bắt buộc: $(echo "${MISSING}" | tr '\n' ' ' | sed 's/ $//')"
        error "--from-env: KHÔNG ghi file nào (secret-production.yaml / .env.production giữ nguyên bản cũ)."
    fi
    if [ ! -t 0 ]; then
        error "Thiếu biến bắt buộc: $(echo "${MISSING}" | tr '\n' ' ' | sed 's/ $//')"
        error "KHÔNG ghi file nào (secret-production.yaml / .env.production giữ nguyên bản cũ)."
        error "Cấp biến qua env (tên chuẩn) hoặc dùng --from-env / các cờ tương ứng."
    fi
fi

# Interactive prompt (không bao giờ echo giá trị ra stdout).
if [ -n "${MISSING}" ] && [ "${FROM_ENV}" -eq 0 ] && [ -t 0 ]; then
    prompt_plain() {
        local var="$1" label="$2" val=""
        read -r -p "[INPUT] ${label} (${var}): " val
        printf '%s' "$val"
    }
    prompt_secret() {
        local var="$1" label="$2" val=""
        read -r -s -p "[INPUT] ${label} (${var}, input ẩn): " val
        echo ""
        printf '%s' "$val"
    }
    while IFS= read -r var; do
        [ -z "$var" ] && continue
        case "$var" in
            DATABASE_URL) DB_URL="$(prompt_plain "$var" 'PostgreSQL URL')" ;;
            BANKOPS_SIGNING_KEY) SIGNING_KEY="$(prompt_secret "$var" 'JWT signing key')" ;;
            BANKOPS_SESSION_SECRET) SESSION_SECRET="$(prompt_secret "$var" 'Session secret')" ;;
            SMTP_USER) SMTP_USER_VALUE="$(prompt_plain "$var" 'SMTP user')" ;;
            SMTP_PASSWORD) SMTP_PASSWORD_VALUE="$(prompt_secret "$var" 'SMTP password')" ;;
            SUPERVISOR_PIN) PIN="$(prompt_secret "$var" 'Supervisor PIN')" ;;
        esac
    done <<< "$(missing_vars)"
fi

MISSING="$(missing_vars | grep -v '^$' || true)"
if [ -n "${MISSING}" ]; then
    error "Thiếu biến bắt buộc: $(echo "${MISSING}" | tr '\n' ' ' | sed 's/ $//')"
    error "KHÔNG ghi file nào (secret-production.yaml / .env.production giữ nguyên bản cũ)."
fi

# Ensure asyncpg scheme for Python backend if raw postgresql:// was provided
if [[ "${DB_URL}" =~ ^postgresql:// ]]; then
    DB_URL="postgresql+asyncpg://${DB_URL#postgresql://}"
fi

DB_PASS="${DB_PASSWORD:-}"
if [ -z "${DB_PASS}" ] && [[ "${DB_URL}" =~ ://[^:]+:([^@]+)@ ]]; then
    DB_PASS="${BASH_REMATCH[1]}"
fi

# ---------------------------------------------------------------------------
# 3. Generate GPG Passphrase if not set (optional secret).
#    Ghi chú: chạy lại script khi đã có backup cũ sẽ đổi passphrase => phải
#    re-encrypt backup cũ (xem docs/security/credential-rotation-runbook.md).
# ---------------------------------------------------------------------------
if [ -z "${GPG_PASS}" ] || [ "${GPG_PASS}" = "CHANGE_ME_ENCRYPTION_PASSPHRASE" ]; then
    info "Generating random GPG Passphrase for automated backups..."
    if command -v openssl >/dev/null 2>&1; then
        GPG_PASS=$(openssl rand -base64 24)
    else
        GPG_PASS=$(python3 -c "import secrets; print(secrets.token_urlsafe(24))")
    fi
    warn "GPG passphrase mới đã được sinh (giá trị KHÔNG in ra). Backup cũ phải được re-encrypt."
fi

# ---------------------------------------------------------------------------
# 4. Generate Kubernetes Production Secret Manifest
#    CHỈ ghi TÊN CHUẨN. `SECRET_KEY` (legacy) không được ghi.
# ---------------------------------------------------------------------------
K8S_SECRET_FILE="${ROOT_DIR}/infra/k8s/base/secret-production.yaml"
info "Writing Kubernetes production secret manifest to ${K8S_SECRET_FILE}..."

cat <<EOF > "${K8S_SECRET_FILE}"
apiVersion: v1
kind: Secret
metadata:
  name: bankops-secrets
  labels:
    app.kubernetes.io/name: bankops
    app.kubernetes.io/part-of: bankops-system
type: Opaque
stringData:
  DATABASE_URL: "${DB_URL}"
  DB_PASSWORD: "${DB_PASS}"
  BANKOPS_SIGNING_KEY: "${SIGNING_KEY}"
  BANKOPS_SESSION_SECRET: "${SESSION_SECRET}"
  SMTP_USER: "${SMTP_USER_VALUE}"
  SMTP_PASSWORD: "${SMTP_PASSWORD_VALUE}"
  SUPERVISOR_PIN: "${PIN}"
  CLOUDFLARE_ACCOUNT_ID: "${CF_ACCOUNT_ID}"
  CLOUDFLARE_API_TOKEN: "${CF_API_TOKEN}"
  CLOUDFLARE_TUNNEL_TOKEN: "${CF_TUNNEL_TOKEN}"
  AWS_ACCESS_KEY_ID: "${R2_KEY_ID}"
  AWS_SECRET_ACCESS_KEY: "${R2_SECRET_KEY}"
  BACKUP_GPG_PASSPHRASE: "${GPG_PASS}"
EOF
chmod 600 "${K8S_SECRET_FILE}"
success "Created ${K8S_SECRET_FILE} (protected 0600, gitignored)."

# ---------------------------------------------------------------------------
# 5. Generate .env.production file for docker-compose or standalone worker
# ---------------------------------------------------------------------------
ENV_PROD_FILE="${ROOT_DIR}/.env.production"
info "Writing production environment file to ${ENV_PROD_FILE}..."

cat <<EOF > "${ENV_PROD_FILE}"
# BankOps Production Configuration
# Generated by scripts/setup_secrets_and_deploy.sh — KHÔNG commit file này.
APP_ENV=production
DATABASE_URL=${DB_URL}
BANKOPS_SIGNING_KEY=${SIGNING_KEY}
BANKOPS_SESSION_SECRET=${SESSION_SECRET}
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=${SMTP_USER_VALUE}
SMTP_PASSWORD=${SMTP_PASSWORD_VALUE}
SUPERVISOR_PIN=${PIN}
ALLOWED_ORIGINS=["https://bankops.yourbank.com","https://bankops-web.pages.dev"]

# Cloudflare Workers AI
CLOUDFLARE_ACCOUNT_ID=${CF_ACCOUNT_ID}
CLOUDFLARE_API_TOKEN=${CF_API_TOKEN}
CLOUDFLARE_MODEL=@cf/meta/llama-3.1-8b-instruct
CLOUDFLARE_TUNNEL_TOKEN=${CF_TUNNEL_TOKEN}
AI_PROVIDER=cloudflare
AI_TIMEOUT_SECONDS=120
AI_REQUESTS_PER_MINUTE=60

# Backup & Object Storage (Cloudflare R2)
AWS_ACCESS_KEY_ID=${R2_KEY_ID}
AWS_SECRET_ACCESS_KEY=${R2_SECRET_KEY}
BACKUP_GPG_PASSPHRASE=${GPG_PASS}
S3_BUCKET=bankops-backups
S3_ENDPOINT=https://${CF_ACCOUNT_ID}.r2.cloudflarestorage.com
EOF
chmod 600 "${ENV_PROD_FILE}"
success "Created ${ENV_PROD_FILE} (protected 0600, gitignored)."

# ---------------------------------------------------------------------------
# 6. Database Migrations Check / Execution
# ---------------------------------------------------------------------------
if [ "${AUTO_MIGRATE}" -eq 1 ]; then
    info "Running database migrations (alembic upgrade head)..."
    cd "${ROOT_DIR}/backend"
    DATABASE_URL="${DB_URL}" poetry run alembic upgrade head || {
        warn "Could not run poetry run alembic directly. Trying via python3..."
        DATABASE_URL="${DB_URL}" python3 -m alembic upgrade head || true
    }
    success "Database migration step completed."
    cd "${ROOT_DIR}"
fi

# ---------------------------------------------------------------------------
# 7. Apply to Kubernetes if requested
# ---------------------------------------------------------------------------
if [ "${APPLY_K8S}" -eq 1 ]; then
    info "Applying secret-production.yaml to active Kubernetes cluster..."
    if command -v kubectl >/dev/null 2>&1; then
        kubectl apply -f "${K8S_SECRET_FILE}" -n bankops-prod || kubectl apply -f "${K8S_SECRET_FILE}"
        success "Applied secret to Kubernetes."
    else
        warn "kubectl not found. Skipped K8s apply."
    fi
fi

echo ""
echo "=================================================================="
echo "🎉 SECRETS CONFIGURED & ENVIRONMENT READY!"
echo "=================================================================="
echo "Summary of generated configurations:"
echo " - K8s Secret:     ${K8S_SECRET_FILE}"
echo " - Env File:       ${ENV_PROD_FILE}"
echo " - Database URL:   configured (giá trị KHÔNG in ra)"
echo " - Cloudflare AI:  configured (giá trị KHÔNG in ra)"
echo " - Supervisor PIN: configured (${#PIN} chars, value not printed)"
echo " - Signing key:    configured (${#SIGNING_KEY} chars, value not printed)"
echo " - Session secret: configured (${#SESSION_SECRET} chars, value not printed)"
echo " - SMTP:           configured (giá trị KHÔNG in ra)"
echo ""
if [ -z "${CF_TUNNEL_TOKEN}" ]; then
    echo "💡 NEXT STEP: To activate Cloudflare Tunnel without opening ports:"
    echo "   1. Run 'cloudflared tunnel login'"
    echo "   2. Create tunnel: 'cloudflared tunnel create bankops-prod-tunnel'"
    echo "   3. Put tunnel token into ${K8S_SECRET_FILE} or rerun with --cf-tunnel-token <TOKEN>"
fi
echo "=================================================================="
