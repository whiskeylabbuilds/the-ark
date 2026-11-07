#!/usr/bin/env bash
# Rename this machine (default "ark") so phones and laptops can reach it as http://ark.local (mDNS),
# and on many home routers as http://ark too. Keeps mDNS off Docker's internal networks.
#   sudo setup/03-rename-host.sh          # -> ark
#   sudo setup/03-rename-host.sh myark    # -> myark
# Reboot afterwards so the router learns the new name.
set -euo pipefail
[ "$(id -u)" -eq 0 ] || { echo "Run with sudo."; exit 1; }
NEW="${1:-${ARK_HOSTNAME:-ark}}"
[[ "$NEW" =~ ^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$ ]] || { echo "Invalid hostname: $NEW (lowercase letters, digits, dashes)"; exit 1; }
OLD=$(hostname)

if [ "$OLD" != "$NEW" ]; then
  echo "Renaming $OLD -> $NEW"
  hostnamectl set-hostname "$NEW"
fi
# /etc/hosts: point 127.0.1.1 at the new name
if grep -q '^127\.0\.1\.1' /etc/hosts; then
  sed -i "s/^127\.0\.1\.1.*/127.0.1.1\t$NEW/" /etc/hosts
else
  printf '127.0.1.1\t%s\n' "$NEW" >> /etc/hosts
fi

# mDNS (.local): make sure avahi is installed, and announce only on real network ports
command -v avahi-daemon >/dev/null || DEBIAN_FRONTEND=noninteractive apt-get install -y avahi-daemon
IFACES=$(for d in /sys/class/net/*; do
  n=$(basename "$d")
  [ -e "$d/device" ] && [ "$n" != lo ] && echo "$n"      # physical ports only (no docker0, br-*, veth*)
done | paste -sd, -)
conf=/etc/avahi/avahi-daemon.conf
if [ -n "$IFACES" ] && [ -f "$conf" ]; then
  if grep -qE '^#?allow-interfaces=' "$conf"; then
    sed -i -E "s/^#?allow-interfaces=.*/allow-interfaces=$IFACES/" "$conf"
  else
    sed -i "/^\[server\]/a allow-interfaces=$IFACES" "$conf"
  fi
  echo "mDNS announces on: $IFACES"
  systemctl restart avahi-daemon || true
fi

echo
echo "Done: hostname is $NEW. Add it to ARK_NAMES in .env ($NEW.local,$NEW), then reboot (sudo reboot)."
