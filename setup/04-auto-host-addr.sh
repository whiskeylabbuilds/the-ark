#!/usr/bin/env bash
# Make the dashboard follow this machine's IP automatically (DHCP stays on).
# Installs:
#   ark-host-addr.service                       runs scripts/update-host-addr.sh at boot
#   /etc/NetworkManager/dispatcher.d/90-ark-host-addr   re-runs it when the network comes up
#                                                        or DHCP hands out a new address
# Run with: sudo setup/04-auto-host-addr.sh
# Re-run it if the project folder moves (the service stores the folder's path).
set -euo pipefail
[ "$(id -u)" -eq 0 ] || { echo "Run with sudo."; exit 1; }
PROJECT="$(cd "$(dirname "$0")/.." && pwd)"
OWNER="$(stat -c %U "$PROJECT/.env")"
SCRIPT="$PROJECT/scripts/update-host-addr.sh"
[ -x "$SCRIPT" ] || chmod +x "$SCRIPT"

cat > /etc/systemd/system/ark-host-addr.service <<EOF
[Unit]
Description=The Ark: point dashboard links at the current IP
Wants=network-online.target
After=network-online.target docker.service

[Service]
Type=oneshot
User=$OWNER
WorkingDirectory=$PROJECT
ExecStart=$SCRIPT

[Install]
WantedBy=multi-user.target
EOF

cat > /etc/NetworkManager/dispatcher.d/90-ark-host-addr <<'EOF'
#!/bin/sh
# The Ark: when a network comes up or DHCP renews with a new address, re-check HOST_ADDR.
case "$2" in
  up|dhcp4-change) systemctl start --no-block ark-host-addr.service ;;
esac
EOF
chmod 755 /etc/NetworkManager/dispatcher.d/90-ark-host-addr

systemctl daemon-reload
systemctl enable ark-host-addr.service
systemctl start ark-host-addr.service
echo
systemctl --no-pager --lines=5 status ark-host-addr.service || true
echo
echo "Installed. Project folder: $PROJECT (re-run this script if it moves)."
