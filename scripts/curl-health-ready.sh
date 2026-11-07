#!/usr/bin/env bash
# curl-health-ready.sh — Kiểm tra health/ready của kho-tra-sua-fastapi trên Render
set -euo pipefail

URL="${1:-https://kho-tra-sua-fastapi.onrender.com/api/v1/health/ready}"

echo "==> GET $URL"
http_code=$(curl -s -o /tmp/render_health_body.json -w "%{http_code}" --max-time 30 "$URL") || {
  echo "ERROR: curl request failed (network/DNS/timeout)"
  exit 1
}

echo "HTTP status: $http_code"
echo "---- body ----"
cat /tmp/render_health_body.json 2>/dev/null || true
echo
echo "--------------"

if [[ "$http_code" == "200" ]]; then
  echo "OK: /api/v1/health/ready trả HTTP 200 (service sẵn sàng)"
  exit 0
else
  echo "FAIL: /api/v1/health/ready trả HTTP $http_code (không phải 200)"
  echo "      Kiểm tra lại env vars REDIS_URL/DATABASE_URL trên Render dashboard rồi redeploy."
  exit 1
fi
