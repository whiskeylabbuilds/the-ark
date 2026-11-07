#!/usr/bin/env bash
# Publish the Ark's root certificate (Caddy's local CA) so devices can trust https://<ark>:3443,
# which browsers require before they allow the microphone (voice in Ask the Ark).
# Copies it to $ARK_DATA/ca/ark-root-ca.crt, served by the dashboard at /ca/ark-root-ca.crt.
# Only the public certificate is copied; the private key never leaves Caddy's data folder.
set -euo pipefail
cd "$(dirname "$0")/.."
[ -f .env ] && set -a && . ./.env && set +a
DEST="${ARK_DATA:-/srv/ark}/ca"
mkdir -p "$DEST"
dc() { docker compose "$@" 2>/dev/null || sg docker -c "docker compose $*"; }

for _ in $(seq 30); do   # Caddy creates its CA a moment after it first starts
  if dc exec -T https cat /data/caddy/pki/authorities/local/root.crt < /dev/null > "$DEST/ark-root-ca.crt.new" \
     && grep -q 'BEGIN CERTIFICATE' "$DEST/ark-root-ca.crt.new"; then
    if cmp -s "$DEST/ark-root-ca.crt.new" "$DEST/ark-root-ca.crt"; then
      rm -f "$DEST/ark-root-ca.crt.new"; echo "Certificate already published."; exit 0
    fi
    mv "$DEST/ark-root-ca.crt.new" "$DEST/ark-root-ca.crt"
    chmod 644 "$DEST/ark-root-ca.crt"
    dc restart homepage >/dev/null   # the dashboard only serves files that existed when it started
    echo "Published $DEST/ark-root-ca.crt  (http://${HOST_ADDR:-<ark>}/ca/ark-root-ca.crt)"
    exit 0
  fi
  sleep 2
done
rm -f "$DEST/ark-root-ca.crt.new"
echo "Caddy's certificate isn't ready yet. Is the https service running? (docker compose ps https)" >&2
exit 1
