#!/usr/bin/env bash
# Restore a base backup + archived WAL to an arbitrary point in time, into a
# NEW standalone Postgres instance on a different port - never overwrites
# the live database. This is the same procedure used for the timestamped
# drill recorded in docs/disaster-recovery.md, as a reusable script instead
# of the one-off commands that drill was first run with.
#
# Usage:
#   ./scripts/restore_pitr.sh <backup-directory> "<recovery target time>" [port]
#
# Example:
#   ./scripts/restore_pitr.sh ./backups/basebackup-20260917T043957Z \
#       "2026-09-17 04:39:56.374951+00" 5555
#
# Requires the postgres container from docker-compose.yml to be running
# (its WAL archive volume is what --restore_command reads from).
set -euo pipefail

CONTAINER="${POSTGRES_CONTAINER:-kone-elevate-postgres}"
BACKUP_DIR="${1:?Usage: restore_pitr.sh <backup-directory> \"<recovery target time>\" [port]}"
TARGET_TIME="${2:?Usage: restore_pitr.sh <backup-directory> \"<recovery target time>\" [port]}"
PORT="${3:-5555}"
RESTORE_PATH="/var/lib/postgresql/pitr_restore_$(date -u +%s)"

if ! docker ps --format '{{.Names}}' | grep -qx "${CONTAINER}"; then
    echo "Postgres container '${CONTAINER}' is not running." >&2
    exit 1
fi

echo "Copying backup into the container ..."
docker exec "${CONTAINER}" mkdir -p "${RESTORE_PATH}"
docker cp "${BACKUP_DIR}/." "${CONTAINER}:${RESTORE_PATH}"
docker exec "${CONTAINER}" chown -R postgres:postgres "${RESTORE_PATH}"
docker exec "${CONTAINER}" chmod 700 "${RESTORE_PATH}"
docker exec "${CONTAINER}" rm -f "${RESTORE_PATH}/postmaster.pid"

echo "Writing recovery configuration (target: ${TARGET_TIME}) ..."
docker exec "${CONTAINER}" bash -c "cat > '${RESTORE_PATH}/postgresql.auto.conf' <<EOF
restore_command = 'cp /var/lib/postgresql/wal_archive/%f %p'
recovery_target_time = '${TARGET_TIME}'
recovery_target_action = 'promote'
port = ${PORT}
EOF"
docker exec "${CONTAINER}" touch "${RESTORE_PATH}/recovery.signal"
docker exec "${CONTAINER}" chown postgres:postgres "${RESTORE_PATH}/postgresql.auto.conf" "${RESTORE_PATH}/recovery.signal"

echo "Starting the restored instance on port ${PORT} ..."
docker exec -u postgres "${CONTAINER}" bash -c \
    "/usr/local/bin/pg_ctl -D '${RESTORE_PATH}' -l /tmp/pitr_restore.log start"

echo
echo "Restored instance is running on port ${PORT} inside ${CONTAINER}."
echo "Connect with:  docker exec -u postgres ${CONTAINER} psql -p ${PORT} -U \${POSTGRES_USER:-kone_admin} -d \${POSTGRES_DB:-kone_elevate}"
echo "Recovery log:  docker exec ${CONTAINER} cat /tmp/pitr_restore.log"
echo
echo "When done verifying, stop and remove the restored instance:"
echo "  docker exec -u postgres ${CONTAINER} pg_ctl -D '${RESTORE_PATH}' stop -m fast"
echo "  docker exec ${CONTAINER} rm -rf '${RESTORE_PATH}'"
