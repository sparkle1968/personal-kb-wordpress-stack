#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

if [[ $# -ne 1 ]]; then
  echo "Usage: $0 backups/YYYYmmdd-HHMMSS-kb"
  exit 1
fi

backup_dir="$1"
for file in db-kb.sql.gz uploads-kb.tar.gz; do
  if [[ ! -f "${backup_dir}/${file}" ]]; then
    echo "Missing ${backup_dir}/${file}"
    exit 1
  fi
done

if [[ -f "${backup_dir}/SHA256SUMS" ]]; then
  echo "Verifying backup checksums..."
  (
    cd "$backup_dir"
    if command -v sha256sum >/dev/null 2>&1; then
      sha256sum -c SHA256SUMS
    else
      shasum -a 256 -c SHA256SUMS
    fi
  )
fi

if [[ "${RESTORE_CONFIRM:-}" != "I_UNDERSTAND_THIS_WILL_OVERWRITE_DATA" ]]; then
  echo "Refusing to restore without confirmation."
  echo "Run: RESTORE_CONFIRM=I_UNDERSTAND_THIS_WILL_OVERWRITE_DATA $0 ${backup_dir}"
  exit 2
fi

set -a
source .env
set +a

compose() {
  docker compose --env-file .env -f "${KB_COMPOSE_FILE:-compose.kb.yml}" "$@"
}

compose up -d

echo "Restoring personal knowledge base database..."
gunzip -c "${backup_dir}/db-kb.sql.gz" | compose exec -T db-kb mariadb -uroot -p"${MYSQL_ROOT_PASSWORD}" "${KB_DB_NAME}"

echo "Restoring personal knowledge base uploads..."
gunzip -c "${backup_dir}/uploads-kb.tar.gz" | compose exec -T wordpress-kb tar -C /var/www/html/wp-content -xf -

if [[ -f "${backup_dir}/plugins-kb.tar.gz" ]]; then
  echo "Restoring personal knowledge base plugins..."
  gunzip -c "${backup_dir}/plugins-kb.tar.gz" | compose exec -T wordpress-kb tar -C /var/www/html/wp-content -xf -
fi

echo "Restore complete."
