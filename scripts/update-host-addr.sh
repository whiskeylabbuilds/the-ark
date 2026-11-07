#!/usr/bin/env bash
# Keep the dashboard links pointing at this machine's current IP.
# Finds the LAN IPv4 address, and if it differs from HOST_ADDR in .env, updates .env
# and recreates the dashboard so its tile links follow.
# Run automatically by the ark-host-addr service (setup/04-auto-host-addr.sh) at boot and
# whenever the network comes up or DHCP hands out a new address. Safe to run by hand.
#
#   scripts/update-host-addr.sh            # update if needed
#   scripts/update-host-addr.sh --check    # only print what it would do
set -euo pipefail
cd "$(dirname "$0")/.."
CHECK=0; [ "${1:-}" = "--check" ] && CHECK=1

detect_ip() {
  local ip
  # The address the default route leaves from (works without internet, as long as there's a router).
  ip=$(ip -4 route get 1.1.1.1 2>/dev/null | grep -oP 'src \K[0-9.]+' || true)
  # No default route: take the first global address on a real network port (not Docker).
  if [ -z "$ip" ]; then
    ip=$(ip -4 -o addr show scope global 2>/dev/null \
         | grep -vE ' (docker[0-9]*|br-[0-9a-f]+|veth[^ ]*) ' | awk '{print $4}' | cut -d/ -f1 | head -1)
  fi
  echo "$ip"
}

new=$(detect_ip)
old=$(grep -oP '^HOST_ADDR=\K.*' .env || true)
if [ -z "$new" ]; then echo "No LAN address yet; leaving HOST_ADDR=$old"; exit 0; fi
if [ "$new" = "$old" ]; then echo "HOST_ADDR already $new"; exit 0; fi
echo "IP changed: $old -> $new"
[ $CHECK -eq 1 ] && exit 0

# Edit in place so .env keeps its owner and 600 permissions.
python3 -I - "$new" <<'EOF'
import sys, re
new = sys.argv[1]
p = '.env'
s = open(p).read()
s = re.sub(r'(?m)^HOST_ADDR=.*$', 'HOST_ADDR=' + new, s) if re.search(r'(?m)^HOST_ADDR=', s) else s + '\nHOST_ADDR=' + new + '\n'
with open(p, 'r+') as f:
    f.seek(0); f.write(s); f.truncate()
EOF

# Wait for Docker (at boot the network can come up first), then recreate the dashboard.
for _ in $(seq 60); do docker info >/dev/null 2>&1 && break; sleep 2; done
docker compose up -d homepage https   # https: its certificate includes the IP
echo "Dashboard links now use $new"
