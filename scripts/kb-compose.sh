#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

docker compose --env-file .env -f "${KB_COMPOSE_FILE:-compose.kb.yml}" "$@"
