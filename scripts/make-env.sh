#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

if [[ -f .env ]]; then
  echo ".env already exists; refusing to overwrite it."
  exit 1
fi

cp .env.example .env
python3 - <<'PY'
from pathlib import Path
import secrets

path = Path(".env")
text = path.read_text()
replacements = {
    "CHANGE_ME_ROOT_PASSWORD": secrets.token_urlsafe(36),
    "CHANGE_ME_KB_DB_PASSWORD": secrets.token_urlsafe(36),
    "CHANGE_ME_FAMILY_DB_PASSWORD": secrets.token_urlsafe(36),
    "CHANGE_ME_ADMIN_PASSWORD": secrets.token_urlsafe(30),
    "CHANGE_ME_PUBLISHER_PASSWORD": secrets.token_urlsafe(30),
}
for old, new in replacements.items():
    text = text.replace(old, new)
path.write_text(text)
PY

chmod 600 .env
echo "Created .env. Edit domains, email, and optional Cloudflare/Aliyun settings before deployment."
