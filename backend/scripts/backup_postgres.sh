#!/usr/bin/env bash
# Take a physical base backup of the docker-compose Postgres instance for
# point-in-time recovery. Run this on a schedule (cron/Task Scheduler) - a
# base backup on its own only restores to the moment it was taken; combined
# with the WAL archive (see docker-compose.yml's postgres.command and
# docs/disaster-recovery.md), it is the starting point for restoring to any
# moment after it, not just the backup time itself.
#
# Usage:
#   ./scripts/backup_postgres.sh [output-directory]
#
# Requires the postgres container from docker-compose.yml to be running.
set -euo pipefail

CONTAINER="${POSTGRES_CONTAINER:-kone-elevate-postgres}"
PG_USER="${POSTGRES_USER:-kone_admin}"
OUT_DIR="${1:-./backups}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
DEST="${OUT_DIR}/basebackup-${STAMP}"

if ! docker ps --format '{{.Names}}' | grep -qx "${CONTAINER}"; then
    echo "Postgres container '${CONTAINER}' is not running. Start it with:" >&2
    echo "  docker compose up -d postgres" >&2
    exit 1
fi

mkdir -p "${OUT_DIR}"

# A freshly created postgres_wal_archive volume is root-owned by default,
# which makes archive_command fail silently (Postgres logs a warning and
# retries forever rather than crashing) - found the hard way while testing
# this script. Idempotent and harmless once already correct.
docker exec --user root "${CONTAINER}" chown postgres:postgres /var/lib/postgresql/wal_archive

echo "Taking a base backup of ${CONTAINER} -> ${DEST}"

docker exec "${CONTAINER}" bash -c "rm -rf /tmp/backup_staging && mkdir -p /tmp/backup_staging"
docker exec "${CONTAINER}" pg_basebackup -U "${PG_USER}" -D /tmp/backup_staging -Fp -Xs -P
docker cp "${CONTAINER}:/tmp/backup_staging" "${DEST}"
docker exec "${CONTAINER}" rm -rf /tmp/backup_staging

echo "Base backup complete: ${DEST}"
echo "Retention: keep daily backups 35 days, weekly backups 1 year (see docs/disaster-recovery.md)."
echo "The WAL archive volume (postgres_wal_archive) must be retained at least as long as the oldest base backup you intend to restore from."
