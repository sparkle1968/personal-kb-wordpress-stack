#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

if [[ ! -f .env ]]; then
  echo "Missing .env. Run ./scripts/make-env.sh first."
  exit 1
fi

set -a
source .env
set +a

mkdir -p secrets
chmod 700 secrets

wp() {
  local site="$1"
  shift
  docker compose run --rm "wpcli-${site}" wp "$@"
}

fix_permissions() {
  local site="$1"
  docker compose exec -T -u root "wordpress-${site}" sh -lc '
    mkdir -p /var/www/html/wp-content/uploads /var/www/html/wp-content/upgrade /var/www/html/wp-content/plugins
    chown -R www-data:www-data /var/www/html/wp-content/uploads /var/www/html/wp-content/upgrade /var/www/html/wp-content/plugins
  '
}

ensure_site() {
  local site="$1"
  local url="$2"
  local title="$3"

  if wp "$site" core is-installed >/dev/null 2>&1; then
    echo "$site is already installed."
  else
    wp "$site" core install \
      --url="https://${url}" \
      --title="$title" \
      --admin_user="${WP_ADMIN_USER}" \
      --admin_password="${WP_ADMIN_PASSWORD}" \
      --admin_email="${WP_ADMIN_EMAIL}" \
      --skip-email
  fi

  wp "$site" option update timezone_string "America/Los_Angeles"
  wp "$site" option update permalink_structure "/%postname%/"
  wp "$site" option update blog_public 0
  wp "$site" option update users_can_register 0
  wp "$site" rewrite flush --hard
  wp "$site" theme activate kanso-minimal
}

clean_default_content() {
  local site="$1"
  local slug ids
  for slug in hello-world sample-page; do
    ids="$(wp "$site" post list --post_type=post,page --name="$slug" --field=ID 2>/dev/null || true)"
    if [[ -n "$ids" ]]; then
      wp "$site" post delete $ids --force >/dev/null
    fi
  done
}

ensure_user() {
  local site="$1"
  if wp "$site" user get "${WP_PUBLISHER_USER}" >/dev/null 2>&1; then
    wp "$site" user update "${WP_PUBLISHER_USER}" \
      --user_email="${WP_PUBLISHER_EMAIL}" \
      --role=editor \
      --user_pass="${WP_PUBLISHER_PASSWORD}"
  else
    wp "$site" user create "${WP_PUBLISHER_USER}" "${WP_PUBLISHER_EMAIL}" \
      --role=editor \
      --user_pass="${WP_PUBLISHER_PASSWORD}" \
      --display_name="Codex Publisher"
  fi
}

ensure_categories() {
  local site="$1"
  shift
  for category in "$@"; do
    wp "$site" term list category --field=name | grep -Fx "$category" >/dev/null 2>&1 || \
      wp "$site" term create category "$category" >/dev/null 2>&1 || true
  done
}

ensure_plugins() {
  local site="$1"
  wp "$site" plugin is-installed members >/dev/null 2>&1 || wp "$site" plugin install members
  wp "$site" plugin activate members
}

ensure_roles() {
  local site="$1"
  wp "$site" role exists family_member >/dev/null 2>&1 || \
    wp "$site" role create family_member "Family Member" --clone=subscriber >/dev/null
  wp "$site" role exists kb-viewer >/dev/null 2>&1 || \
    wp "$site" role create kb-viewer "KB Viewer" --clone=subscriber >/dev/null
  wp "$site" cap add kb-viewer kb_viewer >/dev/null 2>&1 || true
  wp "$site" role exists kb-author >/dev/null 2>&1 || \
    wp "$site" role create kb-author "KB Author" --clone=author >/dev/null
  wp "$site" cap add kb-author assign_categories >/dev/null 2>&1 || true
  if wp "$site" user get kb-viewer >/dev/null 2>&1; then
    wp "$site" user set-role kb-viewer kb-viewer >/dev/null
  fi
}

app_password() {
  local site="$1"
  local output="secrets/${site}-application-password.txt"
  local generated
  if [[ -f "$output" ]]; then
    echo "Application password for $site already exists in $output"
    return
  fi
  generated="$(wp "$site" user application-password create "${WP_PUBLISHER_USER}" "Codex API $(date +%Y-%m-%d)" --porcelain)"
  printf '%s\n' "${generated//[[:space:]]/}" > "$output"
  chmod 600 "$output"
  echo "Saved application password for $site to $output"
}

echo "Starting WordPress stack..."
docker compose up -d

echo "Waiting for WordPress containers..."
sleep 20

fix_permissions kb
fix_permissions family

ensure_site kb "${DOMAIN_KB}" "个人知识库"
ensure_site family "${DOMAIN_FAMILY}" "布丁一家人"
clean_default_content kb
clean_default_content family

ensure_user kb
ensure_user family

ensure_plugins kb
ensure_plugins family
ensure_roles kb
ensure_roles family

ensure_categories kb "技术" "健康" "生活" "资料" "待读"
ensure_categories family "节日" "旅行" "日常" "成长" "聚会"

app_password kb
app_password family

echo
echo "Done. Add these values to .env:"
echo "WP_KB_APP_PASSWORD=$(cat secrets/kb-application-password.txt)"
echo "WP_FAMILY_APP_PASSWORD=$(cat secrets/family-application-password.txt)"
