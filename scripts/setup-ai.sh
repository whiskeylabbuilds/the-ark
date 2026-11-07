#!/usr/bin/env bash
# Finish setting up Ask the Ark after its first admin account exists. Safe to re-run.
#
#   1. Open http://<ark>:3000 and create the first account (it becomes the admin).
#   2. Settings → Account → API Keys → Create, and paste the key into .env:  OPENWEBUI_API_KEY=...
#      (If API Keys is missing: Admin Panel → Settings → General → enable API Keys.)
#   3. scripts/setup-ai.sh
set -euo pipefail
cd "$(dirname "$0")/.."
grep -qE '^OPENWEBUI_API_KEY=.+' .env || { sed -n '3,6p' "$0"; exit 1; }

echo "==> Ask the Ark settings (search, voice, library tool)"
python3 -I scripts/setup-ask-the-ark.py
echo "==> Model names and menu order"
python3 -I scripts/setup-model-names.py
echo "==> Bookshelf → AI knowledge collections"
python3 -I scripts/sync-knowledge.py || echo "   (some files failed; see above. Re-run scripts/sync-knowledge.py later.)"
echo "==> Ark Mechanic"
python3 -I scripts/setup-ark-mechanic.py
echo "Done. Reload Ask the Ark in the browser."
