#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

if [[ ! -f .env.kb-local ]]; then
  echo "Missing .env.kb-local. Run ./scripts/make-kb-local-env.sh first."
  exit 1
fi

set -a
source .env.kb-local
set +a

mkdir -p secrets
chmod 700 secrets

compose() {
  docker compose --env-file .env.kb-local -f compose.kb-local.yml "$@"
}

wp() {
  compose run --rm kb-wpcli-local wp "$@"
}

wait_for_wordpress() {
  local attempts=60
  until compose exec -T kb-wordpress-local test -f /var/www/html/wp-config.php >/dev/null 2>&1; do
    attempts=$((attempts - 1))
    if [[ "$attempts" -le 0 ]]; then
      echo "WordPress did not become ready in time."
      exit 1
    fi
    sleep 2
  done
}

fix_permissions() {
  compose exec -T -u root kb-wordpress-local sh -lc '
    mkdir -p /var/www/html/wp-content/uploads /var/www/html/wp-content/upgrade /var/www/html/wp-content/plugins
    chown -R www-data:www-data /var/www/html/wp-content/uploads /var/www/html/wp-content/upgrade /var/www/html/wp-content/plugins
  '
}

ensure_site() {
  if wp core is-installed >/dev/null 2>&1; then
    echo "Personal knowledge base is already installed."
  else
    wp core install \
      --url="${KB_LOCAL_URL}" \
      --title="个人知识库" \
      --admin_user="${WP_ADMIN_USER}" \
      --admin_password="${WP_ADMIN_PASSWORD}" \
      --admin_email="${WP_ADMIN_EMAIL}" \
      --skip-email
  fi

  wp option update timezone_string "America/Los_Angeles"
  wp option update permalink_structure "/%postname%/"
  wp option update blog_public 0
  wp option update users_can_register 0
  wp rewrite flush --hard
  wp theme activate kanso-minimal
}

clean_default_content() {
  local slug ids
  for slug in hello-world sample-page; do
    ids="$(wp post list --post_type=post,page --name="$slug" --field=ID 2>/dev/null || true)"
    if [[ -n "$ids" ]]; then
      wp post delete $ids --force >/dev/null
    fi
  done
}

ensure_user() {
  if wp user get "${WP_PUBLISHER_USER}" >/dev/null 2>&1; then
    wp user update "${WP_PUBLISHER_USER}" \
      --user_email="${WP_PUBLISHER_EMAIL}" \
      --role=editor \
      --user_pass="${WP_PUBLISHER_PASSWORD}"
  else
    wp user create "${WP_PUBLISHER_USER}" "${WP_PUBLISHER_EMAIL}" \
      --role=editor \
      --user_pass="${WP_PUBLISHER_PASSWORD}" \
      --display_name="Codex Publisher"
  fi
}

ensure_categories() {
  for category in "技术" "健康" "生活" "资料" "待读"; do
    wp term list category --field=name | grep -Fx "$category" >/dev/null 2>&1 || \
      wp term create category "$category" >/dev/null 2>&1 || true
  done
}

ensure_plugins() {
  wp plugin is-installed members >/dev/null 2>&1 || wp plugin install members
  wp plugin activate members
}

ensure_roles() {
  wp role exists family_member >/dev/null 2>&1 || \
    wp role create family_member "Family Member" --clone=subscriber >/dev/null
  wp role exists kb-viewer >/dev/null 2>&1 || \
    wp role create kb-viewer "KB Viewer" --clone=subscriber >/dev/null
  wp cap add kb-viewer kb_viewer >/dev/null 2>&1 || true
  wp role exists kb-author >/dev/null 2>&1 || \
    wp role create kb-author "KB Author" --clone=author >/dev/null
  wp cap add kb-author assign_categories >/dev/null 2>&1 || true
  if wp user get kb-viewer >/dev/null 2>&1; then
    wp user set-role kb-viewer kb-viewer >/dev/null
  fi
}

app_password() {
  local output="secrets/kb-local-application-password.txt"
  local generated
  if [[ -f "$output" ]]; then
    echo "Application password already exists in $output"
  else
    generated="$(wp user application-password create "${WP_PUBLISHER_USER}" "Codex Local API $(date +%Y-%m-%d)" --porcelain)"
    printf '%s\n' "${generated//[[:space:]]/}" > "$output"
    chmod 600 "$output"
    echo "Saved application password to $output"
  fi

  python3 - <<'PY'
from pathlib import Path

env_path = Path(".env.kb-local")
password = Path("secrets/kb-local-application-password.txt").read_text().strip()
lines = env_path.read_text().splitlines()
updated = False
for index, line in enumerate(lines):
    if line.startswith("WP_KB_APP_PASSWORD="):
        lines[index] = f"WP_KB_APP_PASSWORD={password}"
        updated = True
        break
if not updated:
    lines.append(f"WP_KB_APP_PASSWORD={password}")
env_path.write_text("\n".join(lines) + "\n")
PY
}

echo "Starting local personal knowledge base..."
compose up -d kb-db-local kb-wordpress-local
wait_for_wordpress
fix_permissions

ensure_site
clean_default_content
ensure_user
ensure_plugins
ensure_roles
ensure_categories
app_password

echo
echo "Local personal knowledge base is ready:"
echo "  ${KB_LOCAL_URL}/wp-login.php"
echo
echo "Admin:"
echo "  user: ${WP_ADMIN_USER}"
echo "  password: stored in .env.kb-local as WP_ADMIN_PASSWORD"
echo
echo "Add this to .env.kb-local for API publishing:"
echo "WP_KB_APP_PASSWORD=$(cat secrets/kb-local-application-password.txt)"
