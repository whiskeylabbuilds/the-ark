#!/usr/bin/env bash
# The Ark installer: offline library + local AI server on Ubuntu 24.04 / Linux Mint 22 / Debian 12.
#
#   git clone https://github.com/whiskeylabbuilds/the-ark.git ~/ark && cd ~/ark && ./install.sh
#
# Run it as your normal user (it asks for sudo when needed). Safe to run again at any time: every
# step checks what's already done. With an NVIDIA card it stops once for a reboot after the driver
# install; run it again afterwards and it carries on.
#   ARK_YES=1 ./install.sh       # accept the defaults, skip the big optional downloads
#   ARK_NO_PULL=1 ./install.sh   # don't update the programs (e.g. re-running with no internet)
set -euo pipefail
cd "$(dirname "$0")"
PROJECT="$(pwd)"

c_o=$'\e[38;2;235;106;20m'; c_b=$'\e[1m'; c_0=$'\e[0m'
step() { printf '\n%s==>%s %s%s%s\n' "$c_o" "$c_0" "$c_b" "$*" "$c_0"; }
ask() {  # ask "question" default(y/n)
  local q="$1" d="${2:-y}" a
  if [ "${ARK_YES:-0}" = 1 ]; then [ "$d" = y ]; return; fi
  read -rp "$q [$( [ "$d" = y ] && echo Y/n || echo y/N )] " a || true
  a="${a:-$d}"; [[ "$a" =~ ^[Yy] ]]
}
setenv() {  # setenv KEY VALUE  (edits .env in place, keeps its 600 permissions)
  python3 -I - "$1" "$2" <<'PY'
import re, sys
k, v = sys.argv[1], sys.argv[2]
if re.search(r'[\s&#"]', v): v = '"' + v.replace('"', '') + '"'
s = open('.env').read()
s = re.sub(rf'(?m)^{k}=.*$', f'{k}={v}', s) if re.search(rf'(?m)^{k}=', s) else s.rstrip('\n') + f'\n{k}={v}\n'
with open('.env', 'r+') as f: f.seek(0); f.write(s); f.truncate()
PY
}
getenv() { grep -oP "^$1=\K.*" .env 2>/dev/null | tr -d '"' || true; }

[ "$(id -u)" -ne 0 ] || { echo "Run as your normal user, not root (it uses sudo when needed)."; exit 1; }
[ "$(uname -m)" = x86_64 ] || echo "Note: tested on x86-64 only; $(uname -m) may not work for every service."
. /etc/os-release
echo "${c_o}${c_b}THE ARK${c_0}  installer · ${PRETTY_NAME} · $(nproc) CPU threads · $(awk '/MemTotal/ {printf "%.0f", $2/1048576}' /proc/meminfo) GB RAM"

# ---------- 1. graphics card ----------
GPU=none
LSPCI=$(command -v lspci >/dev/null && lspci -nn | grep -E 'VGA|3D|Display' || true)
if grep -q '\[10de:' <<<"$LSPCI"; then GPU=nvidia
elif grep -q '\[1002:' <<<"$LSPCI" && [ -e /dev/kfd ]; then GPU=amd
fi
step "Graphics card: $GPU"
[ -n "$LSPCI" ] && sed 's/^/    /' <<<"$LSPCI"
if [ "$GPU" = nvidia ] && ! nvidia-smi >/dev/null 2>&1; then
  if ask "Install the NVIDIA driver now? (needs a reboot afterwards)" y; then
    sudo setup/01-nvidia-driver.sh
    echo; echo "${c_b}Reboot now (sudo reboot), then run ./install.sh again.${c_0}"; exit 0
  else
    echo "    Continuing without the GPU: the AI will run on the CPU."; GPU=none
  fi
fi
if [ "$GPU" = amd ]; then
  echo "    AMD: using Ollama's ROCm build (compose.amd.yml). If the AI ends up on the CPU, see the README."
fi

# ---------- 2. Docker ----------
step "Docker"
if ! command -v docker >/dev/null || { [ "$GPU" = nvidia ] && ! command -v nvidia-ctk >/dev/null; } \
   || ! command -v pdftotext >/dev/null || ! command -v bc >/dev/null; then
  sudo setup/02-docker.sh
else
  echo "    already installed: $(docker --version)"
fi
# The docker group only applies to new logins; until then run docker through 'sg'.
if docker info >/dev/null 2>&1; then DC() { docker compose "$@"; }
else DC() { sg docker -c "docker compose $(printf '%q ' "$@")"; }; fi

# ---------- 3. settings (.env) ----------
step "Settings (.env)"
if [ ! -f .env ]; then
  install -m 600 .env.example .env
  setenv WEBUI_SECRET_KEY "$(openssl rand -hex 32 2>/dev/null || python3 -c 'import secrets;print(secrets.token_hex(32))')"
  tz=$(timedatectl show -p Timezone --value 2>/dev/null || cat /etc/timezone 2>/dev/null || echo UTC)
  setenv TZ "${tz:-UTC}"
  setenv ARK_UID "$(id -u)"; setenv ARK_GID "$(id -g)"
  echo "    created .env (secret key generated, time zone ${tz:-UTC})"
else
  echo "    keeping your existing .env"
fi
chmod 600 .env
DATA="$(getenv ARK_DATA)"; DATA="${DATA:-/srv/ark}"
if [ ! -w "$DATA" ]; then sudo mkdir -p "$DATA" && sudo chown "$(id -u):$(id -g)" "$DATA"; fi
mkdir -p "$DATA"/{zim,ollama,open-webui,kolibri,kavita,books,maps/www,notes,music,navidrome,meshcore,caddy,ca}
# compose files: base + graphics card + private overlay
cf=docker-compose.yml
[ "$GPU" = nvidia ] && cf="$cf:compose.nvidia.yml"
[ "$GPU" = amd ] && cf="$cf:compose.amd.yml"
[ -f local/compose.yml ] && cf="$cf:local/compose.yml"
if [ "$(getenv COMPOSE_FILE)" != "$cf" ]; then setenv COMPOSE_FILE "$cf"; echo "    COMPOSE_FILE=$cf"; fi
# LAN address
ip=$(scripts/update-host-addr.sh --print || true)   # the real LAN port, never a VPN or Docker address
[ -n "$ip" ] && [ "$(getenv HOST_ADDR)" != "$ip" ] && { setenv HOST_ADDR "$ip"; echo "    HOST_ADDR=$ip"; }
[ -n "$(getenv HOST_ADDR)" ] || { echo "No network address found. Connect to your router, then run ./install.sh again."; exit 1; }

# ---------- 4. name on the network ----------
step "Network name"
host=$(hostname)
if [ "$host" != ark ] && ask "Rename this computer from '$host' to 'ark', so people can open http://ark.local?" y; then
  sudo setup/03-rename-host.sh ark; host=ark; NEED_REBOOT=1
fi
names=$(getenv ARK_NAMES)
for n in "$host.local" "$host"; do
  [[ ",$names," == *",$n,"* ]] || names="${names:+$names,}$n"
done
[ "$names" != "$(getenv ARK_NAMES)" ] && setenv ARK_NAMES "$names"
echo "    reachable as: http://$(getenv HOST_ADDR)  and  ${names//,/ , }"
if ! systemctl is-enabled ark-host-addr.service >/dev/null 2>&1 \
   || ! grep -q "WorkingDirectory=$PROJECT$" /etc/systemd/system/ark-host-addr.service 2>/dev/null; then
  echo "    installing the service that keeps links right when the router hands out a new address"
  sudo setup/04-auto-host-addr.sh >/dev/null
fi

# ---------- 5. start everything ----------
step "Starting the Ark (first time: downloads ~12 GB of programs)"
if [ "${ARK_NO_PULL:-0}" != 1 ]; then   # ARK_NO_PULL=1: use the programs already downloaded (offline re-run)
  for i in 1 2 3; do DC pull --quiet && break || { echo "    download hiccup, retrying ($i/3)..."; sleep 10; }; done
fi
DC up -d
scripts/export-ca.sh || true

# ---------- 6. AI models ----------
step "AI models"
if ask "Download the AI models now? (about 7-17 GB, picked for this machine)" y; then
  scripts/pull-models.sh
else
  echo "    later: scripts/pull-models.sh"
fi

# ---------- 7. content ----------
step "Content (each shows its size and asks first)"
if ask "Download the free Bookshelf books (Bible, philosophy, field manuals; under 1 GB)?" y; then scripts/download-books.sh; fi
if [ "${ARK_YES:-0}" != 1 ]; then
  if ask "Plan the Reference Library download (Wikipedia, medicine, repair guides; ~100 GB)?" y; then
    scripts/download-zims.sh || true
  fi
  if [ -z "$(getenv MAP_BBOX)" ]; then
    echo "    Offline map: set MAP_BBOX and MAP_REGION_NAME in .env (see https://bboxfinder.com), then run scripts/build-maps.sh"
  elif ask "Build the offline map for $(getenv MAP_REGION_NAME)?" y; then
    scripts/build-maps.sh || true
  fi
else
  echo "    skipped in ARK_YES mode: scripts/download-zims.sh, scripts/build-maps.sh"
fi

# ---------- done ----------
A="$(getenv HOST_ADDR)"
cat <<EOF

${c_o}${c_b}The Ark is running.${c_0}  Dashboard: ${c_b}http://$A${c_0}   (or http://$host.local)

Next steps (in a browser):
  1. Ask the Ark   http://$A:3000  -> create the first account (it becomes the admin).
     Then Settings -> Account -> API Keys -> Create, put it in .env as OPENWEBUI_API_KEY=...,
     and run:  scripts/setup-ai.sh     (search tuning, voice, library tool, model names, Ark Mechanic)
  2. Bookshelf     http://$A:5000  -> create the admin account, add each folder under /books as a library.
  3. Courses       http://$A:8300  -> set up, then Device -> Channels -> Import (Khan Academy is a good start).
  4. Music         http://$A:4533  -> create the admin account; copy music into $DATA/music.
  5. Your own pages and vehicle list: see local.example/README.md
EOF
[ "${NEED_REBOOT:-0}" = 1 ] && echo "${c_b}Reboot once (sudo reboot) so the new name takes effect on your network.${c_0}"
exit 0
