#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

if [[ $# -ne 1 ]]; then
  echo "Usage: $0 backups/YYYYmmdd-HHMMSS"
  exit 1
fi

backup_dir="$1"
for file in db-kb.sql.gz db-family.sql.gz uploads-kb.tar.gz uploads-family.tar.gz; do
  if [[ ! -f "${backup_dir}/${file}" ]]; then
    echo "Missing ${backup_dir}/${file}"
    exit 1
  fi
done

if [[ "${RESTORE_CONFIRM:-}" != "I_UNDERSTAND_THIS_WILL_OVERWRITE_DATA" ]]; then
  echo "Refusing to restore without confirmation."
  echo "Run: RESTORE_CONFIRM=I_UNDERSTAND_THIS_WILL_OVERWRITE_DATA $0 ${backup_dir}"
  exit 2
fi

set -a
source .env
set +a

docker compose up -d

echo "Restoring databases..."
gunzip -c "${backup_dir}/db-kb.sql.gz" | docker compose exec -T db-kb mariadb -uroot -p"${MYSQL_ROOT_PASSWORD}" "${KB_DB_NAME}"
gunzip -c "${backup_dir}/db-family.sql.gz" | docker compose exec -T db-family mariadb -uroot -p"${MYSQL_ROOT_PASSWORD}" "${FAMILY_DB_NAME}"

echo "Restoring uploads..."
gunzip -c "${backup_dir}/uploads-kb.tar.gz" | docker compose exec -T wordpress-kb tar -C /var/www/html/wp-content -xf -
gunzip -c "${backup_dir}/uploads-family.tar.gz" | docker compose exec -T wordpress-family tar -C /var/www/html/wp-content -xf -

echo "Restore complete."

