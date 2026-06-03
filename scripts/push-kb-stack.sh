#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

REMOTE_HOST="${REMOTE_HOST:-}"
REMOTE_USER="${REMOTE_USER:-}"
REMOTE_DIR="${REMOTE_DIR:-/opt/home-wordpress}"
KB_COMPOSE_FILE="${KB_COMPOSE_FILE:-compose.kb-cloudflare.yml}"
RUN_REMOTE_HEALTHCHECK="${RUN_REMOTE_HEALTHCHECK:-1}"
RESTART_KB="${RESTART_KB:-0}"
RSYNC_DELETE="${RSYNC_DELETE:-0}"

if [[ -z "$REMOTE_HOST" ]]; then
  echo "Set REMOTE_HOST to the target server before syncing." >&2
  echo "Example: REMOTE_HOST=your-server.example.com REMOTE_USER=debian ./scripts/push-kb-stack.sh" >&2
  exit 2
fi

ssh_target="${REMOTE_HOST}"
if [[ -n "$REMOTE_USER" ]]; then
  ssh_target="${REMOTE_USER}@${REMOTE_HOST}"
fi

remote_dir_q="$(printf '%q' "$REMOTE_DIR")"

echo "Syncing project files to ${ssh_target}:${REMOTE_DIR}"
ssh "$ssh_target" "mkdir -p ${remote_dir_q}"
if [[ "$RSYNC_DELETE" == "1" ]]; then
  rsync -az --delete \
    --exclude='.DS_Store' \
    --exclude='._*' \
    --exclude='__MACOSX/' \
    --exclude='.git/' \
    --exclude='.env' \
    --exclude='.env.*' \
    --exclude='backups/' \
    --exclude='incoming/' \
    --exclude='prepared-media/' \
    --exclude='private/' \
    --exclude='secrets/' \
    --exclude='*.log' \
    ./ "${ssh_target}:${REMOTE_DIR}/"
else
  rsync -az \
    --exclude='.DS_Store' \
    --exclude='._*' \
    --exclude='__MACOSX/' \
    --exclude='.git/' \
    --exclude='.env' \
    --exclude='.env.*' \
    --exclude='backups/' \
    --exclude='incoming/' \
    --exclude='prepared-media/' \
    --exclude='private/' \
    --exclude='secrets/' \
    --exclude='*.log' \
    ./ "${ssh_target}:${REMOTE_DIR}/"
fi

if [[ "$RESTART_KB" == "1" ]]; then
  echo "Restarting personal knowledge base services..."
  ssh "$ssh_target" "cd ${remote_dir_q} && KB_COMPOSE_FILE=${KB_COMPOSE_FILE} ./scripts/kb-compose.sh up -d"
fi

if [[ "$RUN_REMOTE_HEALTHCHECK" == "1" ]]; then
  echo "Running remote healthcheck..."
  ssh "$ssh_target" "cd ${remote_dir_q} && KB_COMPOSE_FILE=${KB_COMPOSE_FILE} ./scripts/kb-healthcheck.sh"
fi

echo "Sync complete."
