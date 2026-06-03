#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

failures=0
warnings=0

ok() {
  printf 'OK   %s\n' "$1"
}

warn() {
  warnings=$((warnings + 1))
  printf 'WARN %s\n' "$1"
}

fail() {
  failures=$((failures + 1))
  printf 'FAIL %s\n' "$1"
}

file_mode() {
  stat -c '%a' "$1" 2>/dev/null || stat -f '%Lp' "$1" 2>/dev/null || echo unknown
}

http_code() {
  local url="$1"
  curl -ksS -o /dev/null -w '%{http_code}' "$url" 2>/dev/null || true
}

if [[ ! -f .env ]]; then
  fail "Missing .env in $(pwd)"
else
  mode="$(file_mode .env)"
  case "$mode" in
    600|640) ok ".env permissions are ${mode}" ;;
    unknown) warn "Could not determine .env permissions" ;;
    *) warn ".env permissions are ${mode}; recommended 600" ;;
  esac
fi

set -a
if [[ -f .env ]]; then
  source .env
fi
set +a

KB_COMPOSE_FILE="${KB_COMPOSE_FILE:-compose.kb-cloudflare.yml}"
kb_url="${KB_PUBLIC_URL:-}"
if [[ -z "$kb_url" ]]; then
  kb_url="https://${DOMAIN_KB:-kb.example.com}"
fi

compose() {
  docker compose --env-file .env -f "$KB_COMPOSE_FILE" "$@"
}

if [[ -f "$KB_COMPOSE_FILE" ]]; then
  ok "Compose file present: ${KB_COMPOSE_FILE}"
else
  fail "Missing compose file: ${KB_COMPOSE_FILE}"
fi

if command -v docker >/dev/null 2>&1 && [[ -f .env && -f "$KB_COMPOSE_FILE" ]]; then
  if compose ps >/tmp/home-wordpress-kb-ps.txt 2>/tmp/home-wordpress-kb-ps.err; then
    ok "Docker Compose responds"
    if grep -q 'wordpress-kb' /tmp/home-wordpress-kb-ps.txt; then
      ok "wordpress-kb service is listed"
    else
      fail "wordpress-kb service is not listed by compose ps"
    fi
    if grep -q 'db-kb' /tmp/home-wordpress-kb-ps.txt; then
      ok "db-kb service is listed"
    else
      fail "db-kb service is not listed by compose ps"
    fi
  else
    fail "Docker Compose check failed: $(cat /tmp/home-wordpress-kb-ps.err)"
  fi
else
  warn "Skipping Docker checks; docker, .env, or compose file is unavailable"
fi

if command -v curl >/dev/null 2>&1; then
  login_status="$(http_code "${kb_url}/wp-login.php")"
  case "$login_status" in
    200|301|302) ok "Login page responds with HTTP ${login_status}" ;;
    "") warn "Could not reach ${kb_url}/wp-login.php" ;;
    *) fail "Login page returned HTTP ${login_status}" ;;
  esac

  rest_status="$(http_code "${kb_url}/wp-json/wp/v2/posts")"
  case "$rest_status" in
    401|403) ok "Anonymous REST posts endpoint is blocked with HTTP ${rest_status}" ;;
    "") warn "Could not reach REST endpoint" ;;
    *) warn "Anonymous REST posts endpoint returned HTTP ${rest_status}; expected 401 or 403" ;;
  esac

  xmlrpc_status="$(http_code "${kb_url}/xmlrpc.php")"
  case "$xmlrpc_status" in
    403|404|405) ok "XML-RPC endpoint is blocked with HTTP ${xmlrpc_status}" ;;
    "") warn "Could not reach XML-RPC endpoint" ;;
    *) warn "XML-RPC endpoint returned HTTP ${xmlrpc_status}; expected blocked response" ;;
  esac
else
  warn "Skipping HTTP checks; curl is unavailable"
fi

backup_root="${BACKUP_DIR:-./backups}"
if [[ -d "$backup_root" ]]; then
  latest_backup="$(find "$backup_root" -mindepth 1 -maxdepth 1 -type d -name '*-kb' -print | sort | tail -n 1)"
  if [[ -n "$latest_backup" ]]; then
    ok "Latest backup: ${latest_backup}"
    if [[ -f "${latest_backup}/SHA256SUMS" ]]; then
      if (
        cd "$latest_backup"
        if command -v sha256sum >/dev/null 2>&1; then
          sha256sum -c SHA256SUMS
        else
          shasum -a 256 -c SHA256SUMS
        fi
      ) >/tmp/home-wordpress-kb-sha.txt 2>&1; then
        ok "Latest backup checksum verifies"
      else
        fail "Latest backup checksum failed: $(cat /tmp/home-wordpress-kb-sha.txt)"
      fi
    else
      warn "Latest backup has no SHA256SUMS file"
    fi
  else
    warn "No personal KB backups found in ${backup_root}"
  fi
else
  warn "Backup directory does not exist yet: ${backup_root}"
fi

if command -v systemctl >/dev/null 2>&1; then
  if systemctl is-enabled home-wordpress-kb-cloudflare-backup.timer >/dev/null 2>&1; then
    ok "Backup timer is enabled"
  else
    warn "Backup timer is not enabled"
  fi
fi

if [[ "$failures" -gt 0 ]]; then
  printf '\nHealthcheck finished with %s failure(s) and %s warning(s).\n' "$failures" "$warnings"
  exit 1
fi

printf '\nHealthcheck finished with %s warning(s).\n' "$warnings"
