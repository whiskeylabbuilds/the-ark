#!/usr/bin/env bash
# Step 1 (NVIDIA cards only): install the NVIDIA driver, keeping the desktop on the built-in GPU
# when there is one, so the AI gets all of the card's memory.
#
# Uses Ubuntu's prebuilt, signed kernel modules (works with Secure Boot, no key-enrollment screen).
# Updates the system first, since signed modules usually target the newest kernel. Reboot afterwards.
#   DRIVER=nvidia:595-open setup/01-nvidia-driver.sh   # pick a specific driver (default: recommended)
set -euo pipefail
[ "$EUID" -eq 0 ] || exec sudo -E bash "$0" "$@"

if ! lspci -nn | grep -E 'VGA|3D|Display' | grep -q '\[10de:'; then
  echo "No NVIDIA graphics card found; nothing to do (the Ark will use the CPU or another GPU)."; exit 0
fi
if nvidia-smi >/dev/null 2>&1; then
  echo "NVIDIA driver already working:"; nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv,noheader; exit 0
fi

echo "==> Updating the system (includes the newest kernel)"
apt-get update
DEBIAN_FRONTEND=noninteractive apt-get -y full-upgrade
DEBIAN_FRONTEND=noninteractive apt-get install -y ubuntu-drivers-common pciutils

echo "==> Installing the NVIDIA driver with signed kernel modules"
if [ -n "${DRIVER:-}" ]; then ubuntu-drivers install "$DRIVER"; else ubuntu-drivers install; fi

# A second (built-in Intel/AMD) GPU: run the desktop on it so the NVIDIA card stays free for the AI.
HYBRID=0
if [ "$(lspci -nn | grep -E 'VGA|3D|Display' | grep -cvE '\[10de:')" -gt 0 ]; then
  HYBRID=1
  DEBIAN_FRONTEND=noninteractive apt-get install -y nvidia-prime
  prime-select on-demand
  echo "==> Desktop on the built-in GPU, NVIDIA card free for the AI (PRIME on-demand)"
fi

echo
echo "Done. Reboot now:  sudo reboot"
if [ "$HYBRID" -eq 1 ]; then
  echo "Before rebooting, plug the monitor into the MOTHERBOARD's video port (not the NVIDIA card's),"
  echo "so the desktop runs on the built-in GPU."
fi
echo "After the reboot, check: nvidia-smi   (idle memory use should be near 0 MiB), then run ./install.sh again."
