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

compose() {
  docker compose --env-file .env -f "${KB_COMPOSE_FILE:-compose.kb.yml}" "$@"
}

hash_files() {
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$@"
  else
    shasum -a 256 "$@"
  fi
}

check_hashes() {
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum -c "$1"
  else
    shasum -a 256 -c "$1"
  fi
}

redact_env() {
  awk -F= '
    /^[[:space:]]*#/ || /^[[:space:]]*$/ || $0 !~ /=/ { print; next }
    {
      key=$1
      if (key ~ /(PASSWORD|SECRET|TOKEN|KEY|COOKIE|NONCE)/) {
        print key "=<redacted>"
      } else {
        print $0
      }
    }
  ' .env > "$1"
  chmod 600 "$1"
}

backup_root="${BACKUP_DIR:-./backups}"
if [[ -z "$backup_root" || "$backup_root" == "/" ]]; then
  echo "Refusing unsafe BACKUP_DIR: ${backup_root:-<empty>}"
  exit 2
fi
backup_read_user="${BACKUP_READ_USER:-${SUDO_USER:-${USER:-}}}"
backup_read_group="${BACKUP_READ_GROUP:-${backup_read_user}}"

stamp="$(date +%Y%m%d-%H%M%S)"
target="${backup_root}/${stamp}-kb.incomplete"
final_target="${backup_root}/${stamp}-kb"
if [[ -e "$target" || -e "$final_target" ]]; then
  echo "Backup target already exists for stamp ${stamp}"
  exit 2
fi

mkdir -p "$backup_root"
chmod 700 "$backup_root"
mkdir -p "$target"
chmod 700 "$target"
trap 'echo "Backup failed; incomplete directory kept at: ${target}" >&2' ERR

echo "Dumping personal knowledge base database..."
compose exec -T db-kb mariadb-dump -uroot -p"${MYSQL_ROOT_PASSWORD}" --single-transaction "${KB_DB_NAME}" | gzip > "${target}/db-kb.sql.gz"

echo "Archiving personal knowledge base uploads..."
compose exec -T wordpress-kb tar -C /var/www/html/wp-content -cf - uploads | gzip > "${target}/uploads-kb.tar.gz"

echo "Archiving WordPress plugins..."
compose exec -T wordpress-kb tar -C /var/www/html/wp-content -cf - plugins | gzip > "${target}/plugins-kb.tar.gz"

echo "Saving site metadata..."
compose ps > "${target}/compose-ps.txt" || true
compose run --rm wpcli-kb wp core version > "${target}/wp-core-version.txt" 2>/dev/null || echo "unknown" > "${target}/wp-core-version.txt"
compose run --rm wpcli-kb wp plugin list --format=json > "${target}/wp-plugins.json" 2>/dev/null || echo "[]" > "${target}/wp-plugins.json"

echo "Archiving deploy configuration without secrets..."
tar \
  --exclude='.DS_Store' \
  --exclude='.env' \
  --exclude='.env.*' \
  --exclude='backups' \
  --exclude='incoming' \
  --exclude='prepared-media' \
  --exclude='secrets' \
  -czf "${target}/site-config.tar.gz" \
  README.md .env.example caddy compose*.yml config docs examples mu-plugins scripts systemd themes

cp .env.example "${target}/env-template.txt"
redact_env "${target}/env-redacted.txt"

cat > "${target}/RESTORE.md" <<'EOF'
# Personal KB Restore Notes

This backup contains the database, uploads, installed WordPress plugins, a
redacted environment snapshot, and the deploy configuration without secrets.

Restore database and uploads from the project directory:

```bash
cd /opt/home-wordpress
RESTORE_CONFIRM=I_UNDERSTAND_THIS_WILL_OVERWRITE_DATA ./scripts/restore-kb.sh backups/YYYYmmdd-HHMMSS-kb
```

The real `.env` and `secrets/` directory are intentionally not stored here.
Keep a separate encrypted copy of those secrets.
EOF

(
  cd "$target"
  hash_files * > SHA256SUMS
  check_hashes SHA256SUMS >/dev/null
)

mv "$target" "$final_target"
trap - ERR
ln -sfn "$(basename "$final_target")" "${backup_root}/latest-kb"

if [[ -n "$backup_read_user" ]] && id "$backup_read_user" >/dev/null 2>&1; then
  if getent group "$backup_read_group" >/dev/null 2>&1; then
    chown -R "${backup_read_user}:${backup_read_group}" "$backup_root" "$final_target" 2>/dev/null || true
  else
    chown -R "$backup_read_user" "$backup_root" "$final_target" 2>/dev/null || true
  fi
  chmod 700 "$backup_root" "$final_target" 2>/dev/null || true
  find "$final_target" -type d -exec chmod 700 {} + 2>/dev/null || true
  find "$final_target" -type f -exec chmod 600 {} + 2>/dev/null || true
fi

if [[ "${BACKUP_RETENTION_DAYS:-0}" -gt 0 ]]; then
  find "$backup_root" -mindepth 1 -maxdepth 1 -type d -name '*-kb' -mtime +"${BACKUP_RETENTION_DAYS}" -print -exec rm -rf {} +
fi

if [[ -n "${OFFSITE_BACKUP_TARGET:-}" ]]; then
  echo "Syncing to ${OFFSITE_BACKUP_TARGET}..."
  rsync_args=(-a)
  if [[ "${OFFSITE_BACKUP_DELETE:-0}" == "1" ]]; then
    rsync_args+=(--delete)
  fi
  rsync "${rsync_args[@]}" "${backup_root}/" "${OFFSITE_BACKUP_TARGET}/"
fi

echo "Backup complete: ${final_target}"
