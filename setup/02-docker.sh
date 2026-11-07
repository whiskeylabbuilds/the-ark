#!/usr/bin/env bash
# Step 2: Docker Engine + Compose (+ NVIDIA Container Toolkit when an NVIDIA driver is present),
# and the data folder. Works on Ubuntu, Linux Mint and Debian.
set -euo pipefail
[ "$EUID" -eq 0 ] || exec sudo -E bash "$0" "$@"

TARGET_USER="${SUDO_USER:-$(logname)}"
DATA="${ARK_DATA:-/srv/ark}"

. /etc/os-release
if [ -n "${UBUNTU_CODENAME:-}" ]; then     # Ubuntu and its derivatives (Mint's own codename isn't in Docker's repo)
  DISTRO=ubuntu; CODENAME="$UBUNTU_CODENAME"
elif [ "${ID:-}" = debian ] || [ "${ID_LIKE:-}" = debian ]; then
  DISTRO=debian; CODENAME="${VERSION_CODENAME:?VERSION_CODENAME missing}"
else
  echo "Unsupported system ($PRETTY_NAME). The Ark is tested on Ubuntu 24.04 / Linux Mint 22 / Debian 12."; exit 1
fi
echo "==> Docker repo for $DISTRO $CODENAME"

apt-get update
apt-get install -y ca-certificates curl gnupg pciutils poppler-utils bc python3
install -m 0755 -d /etc/apt/keyrings
curl -fsSL "https://download.docker.com/linux/$DISTRO/gpg" -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/$DISTRO $CODENAME stable" \
  > /etc/apt/sources.list.d/docker.list

NVIDIA=0
if nvidia-smi >/dev/null 2>&1; then
  NVIDIA=1
  echo "==> NVIDIA Container Toolkit repo"
  curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey \
    | gpg --batch --yes --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
  curl -fsSL https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list \
    | sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' \
    > /etc/apt/sources.list.d/nvidia-container-toolkit.list
fi

apt-get update
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
if [ "$NVIDIA" -eq 1 ]; then
  apt-get install -y nvidia-container-toolkit
  echo "==> Letting Docker use the GPU"
  nvidia-ctk runtime configure --runtime=docker
fi
systemctl enable docker containerd
systemctl restart docker

echo "==> Adding $TARGET_USER to the docker group"
usermod -aG docker "$TARGET_USER"
# AMD GPUs: Ollama's ROCm build needs the video and render groups' devices
getent group render >/dev/null && usermod -aG render "$TARGET_USER" || true
usermod -aG video "$TARGET_USER" || true

echo "==> Creating data folders in $DATA"
mkdir -p "$DATA"/{zim,ollama,open-webui,kolibri,kavita,books,maps/www,notes,music,navidrome,meshcore,caddy,ca}
chown -R "$TARGET_USER:$TARGET_USER" "$DATA"

if [ "$NVIDIA" -eq 1 ]; then
  echo "==> GPU test inside a container"
  docker run --rm --gpus all ubuntu:24.04 nvidia-smi || echo "!! GPU test failed; the AI will fall back to the CPU until this works."
fi
echo "Docker ready. Log out and back in (or reboot) so '$TARGET_USER' can run docker without sudo."
