#!/usr/bin/env bash
set -euo pipefail
REQUIRED=(APP_ENV DATABASE_URL REDIS_URL)
MISSING=()
for k in "${REQUIRED[@]}"; do
  v="${!k:-}"
  if [[ -z "$v" ]]; then MISSING+=("$k"); fi
done
if [[ ${#MISSING[@]} -gt 0 ]]; then
  echo "Missing required Render env vars:" >&2
  for k in "${MISSING[@]}"; do echo "  - $k" >&2; done
  exit 1
fi
echo "All required Render env vars present (values not shown)."
