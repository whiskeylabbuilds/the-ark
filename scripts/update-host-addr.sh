#!/usr/bin/env bash
# Keep the dashboard links pointing at this machine's current IP.
# Finds the LAN IPv4 address, and if it differs from HOST_ADDR in .env, updates .env
# and recreates the dashboard so its tile links follow.
# Run automatically by the ark-host-addr service (setup/04-auto-host-addr.sh) at boot and
# whenever the network comes up or DHCP hands out a new address. Safe to run by hand.
#
#   scripts/update-host-addr.sh            # update if needed
#   scripts/update-host-addr.sh --check    # only print what it would do
#   scripts/update-host-addr.sh --print    # only print the detected LAN address
set -euo pipefail
cd "$(dirname "$0")/.."
CHECK=0; [ "${1:-}" = "--check" ] && CHECK=1

detect_ip() {
  # The LAN address on a real network port. VPNs (wg0, tun0, ...) and Docker networks have no
  # /sys/class/net/<name>/device, so they're skipped even when a VPN carries the default route.
  # Ports with a default route come first; works without internet, as long as there's a router.
  local dev ip
  for dev in $(ip -4 route show default 2>/dev/null | grep -oP 'dev \K\S+') $(ls /sys/class/net); do
    [ -e "/sys/class/net/$dev/device" ] || continue
    ip=$(ip -4 -o addr show dev "$dev" scope global 2>/dev/null | awk '{print $4}' | cut -d/ -f1 | head -1)
    [ -n "$ip" ] && { echo "$ip"; return; }
  done
}
[ "${1:-}" = "--print" ] && { detect_ip; exit 0; }

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
