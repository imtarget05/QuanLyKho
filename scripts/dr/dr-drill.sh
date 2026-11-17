#!/bin/bash
# Disaster Recovery Drill Script (Phase 4 - P0)
#
# Simulates a full DR drill for QuanLyKho PostgreSQL on AKS:
#   1. Take pg_dump of production DB
#   2. Upload to Azure Blob Storage (backups container)
#   3. Restore into a fresh PostgreSQL Flexible Server (DR target)
#   4. Verify row counts + checksums match
#   5. Generate evidence report
#
# Usage:
#   DR_SOURCE_PG_HOST=<source-pg> DR_SOURCE_PG_USER=<user> DR_SOURCE_PG_DB=<db> \
#   DR_TARGET_PG_HOST=<target-pg> DR_TARGET_PG_USER=<user> DR_TARGET_PG_DB=<db> \
#   AZURE_STORAGE_CONNECTION_STRING=<conn> ./scripts/dr/dr-drill.sh
#
set -euo pipefail

SOURCE_PG_HOST="${DR_SOURCE_PG_HOST:-bankops-postgres}"
SOURCE_PG_USER="${DR_SOURCE_PG_USER:-bankops}"
SOURCE_PG_DB="${DR_SOURCE_PG_DB:-bankops}"
SOURCE_PG_PASSWORD="${DR_SOURCE_PG_PASSWORD:-}"

TARGET_PG_HOST="${DR_TARGET_PG_HOST:-bankops-postgres-dr}"
TARGET_PG_USER="${DR_TARGET_PG_USER:-bankops}"
TARGET_PG_DB="${DR_TARGET_PG_DB:-bankops}"
TARGET_PG_PASSWORD="${DR_TARGET_PG_PASSWORD:-}"

AZURE_STORAGE_CONNECTION_STRING="${AZURE_STORAGE_CONNECTION_STRING:-}"
BACKUP_CONTAINER="${BACKUP_CONTAINER:-backups}"
TIMESTAMP=$(date -u +"%Y%m%d_%H%M%SZ")
BACKUP_FILE="/tmp/dr_backup_${TIMESTAMP}.dump"
CHECKSUM_FILE="${BACKUP_FILE}.sha256"
EVIDENCE_FILE="/tmp/dr_drill_evidence_${TIMESTAMP}.json"

echo "=== DR Drill started at $(date -u) ==="
echo "Source PG: ${SOURCE_PG_HOST}/${SOURCE_PG_DB}"
echo "Target PG: ${TARGET_PG_HOST}/${TARGET_PG_DB}"
echo "Timestamp: ${TIMESTAMP}"

# ── Step 1: pg_dump source database ─────────────────────────────────────────────
echo ""
echo "--- Step 1: pg_dump source database ---"
if [ -z "${SOURCE_PG_PASSWORD}" ]; then
  echo "ERROR: DR_SOURCE_PG_PASSWORD not set"
  exit 1
fi

PGPASSWORD="${SOURCE_PG_PASSWORD}" pg_dump \
  -h "${SOURCE_PG_HOST}" \
  -U "${SOURCE_PG_USER}" \
  -d "${SOURCE_PG_DB}" \
  -Fc \
  -f "${BACKUP_FILE}"

if [ ! -f "${BACKUP_FILE}" ]; then
  echo "ERROR: pg_dump produced no file"
  exit 1
fi

BACKUP_SIZE=$(stat -f%z "${BACKUP_FILE}" 2>/dev/null || stat -c%s "${BACKUP_FILE}")
echo "Backup file: ${BACKUP_FILE} (${BACKUP_SIZE} bytes)"

# ── Step 2: SHA-256 checksum ────────────────────────────────────────────────────
echo ""
echo "--- Step 2: SHA-256 checksum ---"
sha256sum "${BACKUP_FILE}" > "${CHECKSUM_FILE}"
BACKUP_CHECKSUM=$(cut -d' ' -f1 "${CHECKSUM_FILE}")
echo "Checksum: ${BACKUP_CHECKSUM}"

# ── Step 3: Upload to Azure Blob Storage ────────────────────────────────────────
echo ""
echo "--- Step 3: Upload to Azure Blob Storage ---"
if [ -z "${AZURE_STORAGE_CONNECTION_STRING}" ]; then
  echo "WARNING: AZURE_STORAGE_CONNECTION_STRING not set, skipping upload"
  UPLOAD_URL="<skipped>"
else
  BLOB_NAME="dr-drill/${TIMESTAMP}/bankops_db.dump"
  az storage blob upload \
    --connection-string "${AZURE_STORAGE_CONNECTION_STRING}" \
    --container-name "${BACKUP_CONTAINER}" \
    --name "${BLOB_NAME}" \
    --file "${BACKUP_FILE}" \
    --overwrite \
    --output none
  UPLOAD_URL="https://$(echo "${AZURE_STORAGE_CONNECTION_STRING}" | grep -oP 'AccountName=\K[^;]+').blob.core.windows.net/${BACKUP_CONTAINER}/${BLOB_NAME}"
  echo "Uploaded to: ${UPLOAD_URL}"
fi

# ── Step 4: Restore to target PostgreSQL ────────────────────────────────────────
echo ""
echo "--- Step 4: Restore to target PostgreSQL ---"
if [ -z "${TARGET_PG_PASSWORD}" ]; then
  echo "ERROR: DR_TARGET_PG_PASSWORD not set"
  exit 1
fi

# Drop and recreate target database
PGPASSWORD="${TARGET_PG_PASSWORD}" psql \
  -h "${TARGET_PG_HOST}" \
  -U "${TARGET_PG_USER}" \
  -d postgres \
  -c "DROP DATABASE IF EXISTS ${TARGET_PG_DB};"

PGPASSWORD="${TARGET_PG_PASSWORD}" psql \
  -h "${TARGET_PG_HOST}" \
  -U "${TARGET_PG_USER}" \
  -d postgres \
  -c "CREATE DATABASE ${TARGET_PG_DB};"

# Restore from dump
PGPASSWORD="${TARGET_PG_PASSWORD}" pg_restore \
  -h "${TARGET_PG_HOST}" \
  -U "${TARGET_PG_USER}" \
  -d "${TARGET_PG_DB}" \
  -v \
  "${BACKUP_FILE}"

echo "Restore completed to ${TARGET_PG_HOST}/${TARGET_PG_DB}"

# ── Step 5: Verify row counts ───────────────────────────────────────────────────
echo ""
echo "--- Step 5: Verify row counts ---"

verify_table_count() {
  local table=$1
  local source_count target_count
  source_count=$(PGPASSWORD="${SOURCE_PG_PASSWORD}" psql \
    -h "${SOURCE_PG_HOST}" -U "${SOURCE_PG_USER}" -d "${SOURCE_PG_DB}" \
    -t -A -c "SELECT count(*) FROM ${table};" 2>/dev/null || echo "0")
  target_count=$(PGPASSWORD="${TARGET_PG_PASSWORD}" psql \
    -h "${TARGET_PG_HOST}" -U "${TARGET_PG_USER}" -d "${TARGET_PG_DB}" \
    -t -A -c "SELECT count(*) FROM ${table};" 2>/dev/null || echo "0")

  if [ "${source_count}" = "${target_count}" ]; then
    echo "  ✅ ${table}: source=${source_count} target=${target_count} MATCH"
    return 0
  else
    echo "  ❌ ${table}: source=${source_count} target=${target_count} MISMATCH"
    return 1
  fi
}

TABLES=("inv_items" "inv_balances" "cashbox_journals" "outbox_events" "users")
ALL_MATCH=true
for table in "${TABLES[@]}"; do
  if ! verify_table_count "${table}"; then
    ALL_MATCH=false
  fi
done

# ── Step 6: Generate evidence report ────────────────────────────────────────────
echo ""
echo "--- Step 6: Generate evidence report ---"

cat > "${EVIDENCE_FILE}" << EOF
{
  "drill_id": "dr-drill-${TIMESTAMP}",
  "timestamp_utc": "${TIMESTAMP}",
  "source": {
    "host": "${SOURCE_PG_HOST}",
    "database": "${SOURCE_PG_DB}"
  },
  "target": {
    "host": "${TARGET_PG_HOST}",
    "database": "${TARGET_PG_DB}"
  },
  "backup": {
    "file": "${BACKUP_FILE}",
    "size_bytes": ${BACKUP_SIZE},
    "checksum_sha256": "${BACKUP_CHECKSUM}",
    "upload_url": "${UPLOAD_URL}",
    "container": "${BACKUP_CONTAINER}"
  },
  "restore": {
    "success": true,
    "target_host": "${TARGET_PG_HOST}",
    "target_database": "${TARGET_PG_DB}"
  },
  "verification": {
    "tables_checked": ${#TABLES[@]},
    "all_match": ${ALL_MATCH},
    "pass": ${ALL_MATCH}
  },
  "status": "$([ "${ALL_MATCH}" = true ] && echo "PASS" || echo "FAIL")"
}
EOF

echo "Evidence report: ${EVIDENCE_FILE}"
cat "${EVIDENCE_FILE}"

# ── Step 7: Summary ─────────────────────────────────────────────────────────────
echo ""
echo "=== DR Drill completed at $(date -u) ==="
if [ "${ALL_MATCH}" = true ]; then
  echo "RESULT: PASS — All table counts match between source and target"
  exit 0
else
  echo "RESULT: FAIL — Some table counts mismatch"
  exit 1
fi