#!/usr/bin/env bash
# render-redeploy.sh — Redeploy Render service qua API token
#
# Yêu cầu:
#   - RENDER_API_TOKEN: token có quyền deploy service (tạo ở Render Dashboard -> Account Settings -> API Keys)
#   - RENDER_SERVICE_ID: ID của Web Service `kho-tra-sua-fastapi` (trong URL dashboard: /web/srv-<id>)
#
# Usage:
#   export RENDER_API_TOKEN="rnd_..."
#   export RENDER_SERVICE_ID="srv-db8esj689jmc73d8b420"
#   ./scripts/render-redeploy.sh
set -euo pipefail

RENDER_API_TOKEN="${RENDER_API_TOKEN:?Thiếu RENDER_API_TOKEN (export trước khi chạy)}"
RENDER_SERVICE_ID="${RENDER_SERVICE_ID:?Thiếu RENDER_SERVICE_ID (export trước khi chạy)}"

DEPLOY_URL="https://api.render.com/v1/services/${RENDER_SERVICE_ID}/deploys"

echo "==> Kích hoạt redeploy cho service: ${RENDER_SERVICE_ID}"
response=$(curl -s -w "\n%{http_code}" -X POST "${DEPLOY_URL}" \
  -H "Accept: application/json" \
  -H "Authorization: Bearer ${RENDER_API_TOKEN}" \
  -H "Content-Type: application/json") || {
  echo "ERROR: curl request đến Render API thất bại (mạng/token/DNS)"
  exit 1
}

http_code=$(echo "$response" | tail -n1)
body=$(echo "$response" | sed '$d')

echo "---- Render API response (HTTP $http_code) ----"
echo "$body"
echo "-----------------------------------------------"

if [[ "$http_code" == "201" || "$http_code" == "202" ]]; then
  echo "OK: Redeploy đã được kích hoạt. Chờ vài phút rồi kiểm tra:"
  echo "    curl -i https://kho-tra-sua-fastapi.onrender.com/api/v1/health/ready"
  exit 0
else
  echo "FAIL: Render API trả HTTP $http_code"
  echo "      Kiểm tra lại RENDER_API_TOKEN, RENDER_SERVICE_ID và quyền của token."
  exit 1
fi
