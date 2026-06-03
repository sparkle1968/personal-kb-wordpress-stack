#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

if [[ ! -f .env ]]; then
  echo "Missing .env"
  exit 1
fi

set -a
source .env
set +a

stamp="$(date +%Y%m%d-%H%M%S)"
target="${BACKUP_DIR:-./backups}/${stamp}"
mkdir -p "$target"
chmod 700 "$target"

echo "Dumping databases..."
docker compose exec -T db-kb mariadb-dump -uroot -p"${MYSQL_ROOT_PASSWORD}" --single-transaction "${KB_DB_NAME}" | gzip > "${target}/db-kb.sql.gz"
docker compose exec -T db-family mariadb-dump -uroot -p"${MYSQL_ROOT_PASSWORD}" --single-transaction "${FAMILY_DB_NAME}" | gzip > "${target}/db-family.sql.gz"

echo "Archiving uploads..."
docker compose exec -T wordpress-kb tar -C /var/www/html/wp-content -cf - uploads | gzip > "${target}/uploads-kb.tar.gz"
docker compose exec -T wordpress-family tar -C /var/www/html/wp-content -cf - uploads | gzip > "${target}/uploads-family.tar.gz"

cp .env.example "${target}/env-template.txt"
sha256sum "${target}"/* > "${target}/SHA256SUMS"

if [[ -n "${OFFSITE_BACKUP_TARGET:-}" ]]; then
  echo "Syncing to ${OFFSITE_BACKUP_TARGET}..."
  rsync -a --delete "${BACKUP_DIR:-./backups}/" "${OFFSITE_BACKUP_TARGET}/"
fi

if [[ "${BACKUP_RETENTION_DAYS:-0}" -gt 0 ]]; then
  find "${BACKUP_DIR:-./backups}" -mindepth 1 -maxdepth 1 -type d -mtime +"${BACKUP_RETENTION_DAYS}" -print -exec rm -rf {} +
fi

echo "Backup complete: ${target}"

