#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

exec docker compose --env-file .env.kb-local -f compose.kb-local.yml "$@"

