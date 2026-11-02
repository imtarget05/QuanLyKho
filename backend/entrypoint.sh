#!/bin/sh
set -e

# --- Secret JWT (fail-closed) --------------------------------------------
# `app/config.py` mặc định `APP_ENV=production`: server thiếu
# `BANKOPS_SIGNING_KEY` thì KHÔNG được khởi động (token ký bằng secret
# ephemeral sẽ hết hạn sau mỗi lần restart).
#
# `SECRET_KEY` là tên CŨ (legacy) của secret deploy. KHÔNG được dùng nó làm
# fallback ÂM THẦM: 2 tên / 1 giá trị ⇒ rotate `BANKOPS_SIGNING_KEY` ở một
# nơi thì nơi kia vẫn giữ giá trị cũ (xem
# `docs/security/secret-rotation-inventory-2026-10-20.md` §4).
#
# - `APP_ENV` = production|staging (hoặc KHÔNG set -> coi như production):
#   FAIL-FAST, không start server.
# - `APP_ENV` = demo|dev|test: fallback legacy **kèm CẢNH BÁO LỚN** (chỉ để
#   môi trường dev/demo khởi động được; tuyệt đối không dùng ở production).
if [ -z "${BANKOPS_SIGNING_KEY:-}" ]; then
    APP_ENV_VALUE="${APP_ENV:-production}"
    case "$APP_ENV_VALUE" in
        demo|dev|test|local)
            if [ -n "${SECRET_KEY:-}" ]; then
                echo "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!"
                echo "[Entrypoint] WARNING (DEPRECATED): 'SECRET_KEY' là tên CŨ (legacy) của secret deploy."
                echo "[Entrypoint]          'BANKOPS_SIGNING_KEY' chưa set nên đang fallback sang 'SECRET_KEY'"
                echo "[Entrypoint]          (APP_ENV=${APP_ENV_VALUE}). 2 tên / 1 giá trị = rủi ro rotate lệch."
                echo "[Entrypoint]          Hãy cấp 'BANKOPS_SIGNING_KEY' (k8s Secret / GitHub Secret) rồi bỏ 'SECRET_KEY'."
                echo "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!"
                BANKOPS_SIGNING_KEY="$SECRET_KEY"
                export BANKOPS_SIGNING_KEY
            else
                echo "[Entrypoint] WARNING: 'BANKOPS_SIGNING_KEY' chưa set (APP_ENV=${APP_ENV_VALUE})"
                echo "[Entrypoint]          -> app sẽ dùng secret EPHEMERAL (token hết hạn sau mỗi lần restart)."
            fi
            ;;
        *)
            echo "[Entrypoint] FATAL: thiếu 'BANKOPS_SIGNING_KEY' (APP_ENV=${APP_ENV_VALUE}) -> DỪNG khởi động server." >&2
            echo "[Entrypoint]        KHÔNG dùng fallback legacy 'SECRET_KEY' ở môi trường này (2 tên / 1 giá trị khiến rotate bị lệch)." >&2
            echo "[Entrypoint]        Hãy cấp 'BANKOPS_SIGNING_KEY' trong k8s Secret / GitHub Secret rồi deploy lại." >&2
            exit 1
            ;;
    esac
fi

# --- Migrations: SKIP (handled by ArgoCD PreSync Job) --------------------
# Migration chạy riêng qua ArgoCD PreSync Hook Job
# (infra/k8s/base/migration-job.yaml, argocd.argoproj.io/hook: PreSync)
# trước khi Deployment rollout. Mỗi pod khởi động KHÔNG tự chạy alembic
# để tránh race condition database lock khi HPA scale lên nhiều pod cùng lúc.
echo "[Entrypoint] Skipping alembic upgrade head — migration được xử lý bởi ArgoCD PreSync Job (migration-job.yaml)."

# --- Reverse proxy --------------------------------------------------------
# Sau nginx/Cloudflare/Traefik, mọi request đến từ IP của proxy. uvicorn chỉ
# tin `X-Forwarded-For` khi IP peer nằm trong `--forwarded-allow-ips`; mặc định
# chỉ tin loopback. Deploy sau proxy thật thì set `FORWARDED_ALLOW_IPS` (IP/CIDR
# của proxy) để rate-limit theo IP client THẬT thay vì gộp tất cả vào 1 IP.
FORWARDED_ALLOW_IPS="${FORWARDED_ALLOW_IPS:-127.0.0.1}"

echo "[Entrypoint] Starting Uvicorn on 0.0.0.0:${PORT:-8000} (forwarded-allow-ips=${FORWARDED_ALLOW_IPS})..."
exec uvicorn app.main:app \
    --host 0.0.0.0 \
    --port "${PORT:-8000}" \
    --forwarded-allow-ips "$FORWARDED_ALLOW_IPS"
