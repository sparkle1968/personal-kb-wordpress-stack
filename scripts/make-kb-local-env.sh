#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

if [[ -f .env.kb-local ]]; then
  echo ".env.kb-local already exists; refusing to overwrite it."
  exit 1
fi

cp .env.kb-local.example .env.kb-local
python3 - <<'PY'
from pathlib import Path
import secrets

path = Path(".env.kb-local")
text = path.read_text()
replacements = {
    "CHANGE_ME_KB_LOCAL_DB_PASSWORD": secrets.token_urlsafe(36),
    "CHANGE_ME_KB_LOCAL_ROOT_PASSWORD": secrets.token_urlsafe(36),
    "CHANGE_ME_ADMIN_PASSWORD": secrets.token_urlsafe(30),
    "CHANGE_ME_PUBLISHER_PASSWORD": secrets.token_urlsafe(30),
}
for old, new in replacements.items():
    text = text.replace(old, new)
path.write_text(text)
PY

chmod 600 .env.kb-local
echo "Created .env.kb-local"

