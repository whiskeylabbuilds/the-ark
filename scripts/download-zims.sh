#!/usr/bin/env bash
# Download the newest version of every ZIM in content/zims.list into $ARK_DATA/zim.
# Shows sizes and free space first and refuses to fill the disk.
# Safe to re-run: finished files are skipped, partial ones resume, and older
# versions of an updated ZIM are deleted after the new one verifies.
#
#   scripts/download-zims.sh            # plan, ask, download
#   scripts/download-zims.sh --dry-run  # plan only
set -euo pipefail
cd "$(dirname "$0")/.."
[ -f .env ] && set -a && . ./.env && set +a

DATA="${ARK_DATA:-/srv/ark}"
DEST="$DATA/zim"
LIST="content/zims.list"
BASE="https://download.kiwix.org/zim"
RESERVE_GB="${RESERVE_GB:-60}"   # keep this much free for the OS, Docker images, models and maps
DRY=0; [ "${1:-}" = "--dry-run" ] && DRY=1

mkdir -p "$DEST"
declare -A listing
plan=()   # "folder|file|bytes"
need=0

echo "Resolving newest files..."
while read -r folder prefix _; do
  [[ -z "$folder" || "$folder" == \#* ]] && continue
  if [ -z "${listing[$folder]+x}" ]; then
    listing[$folder]="$(curl -fsL "$BASE/$folder/")"
  fi
  file=$(grep -oE "${prefix//./\\.}[0-9][0-9-]*[a-z]?\.zim" <<<"${listing[$folder]}" | sort -u | tail -1 || true)
  if [ -z "$file" ]; then echo "  !! nothing found for $folder/$prefix"; continue; fi
  bytes=$(curl -fsIL "$BASE/$folder/$file" | grep -i '^content-length' | tail -1 | tr -dc 0-9)
  have=0; [ -f "$DEST/$file" ] && have=1
  [ -f "$DEST/$file.part" ] && bytes_left=$(( bytes - $(stat -c%s "$DEST/$file.part") )) || bytes_left=$bytes
  if [ $have -eq 1 ]; then status="have"; else status="get"; need=$(( need + bytes_left )); fi
  printf "  %-5s %7.2f GB  %s\n" "$status" "$(bc -l <<<"$bytes/1000000000")" "$file"
  plan+=("$folder|$file|$bytes|$prefix")
done < "$LIST"

free=$(( $(df --output=avail -B1 "$DEST" | tail -1) ))
reserve=$(( RESERVE_GB * 1000000000 ))
printf "\nTo download: %.1f GB   Free: %.1f GB   Keeping free: %d GB\n" \
  "$(bc -l <<<"$need/1000000000")" "$(bc -l <<<"$free/1000000000")" "$RESERVE_GB"
if (( need > free - reserve )); then
  echo "Not enough room. Comment out some lines in $LIST (or lower RESERVE_GB)."; exit 1
fi
[ $DRY -eq 1 ] && exit 0
read -rp "Download now? [y/N] " a; [[ "$a" =~ ^[Yy] ]] || exit 0

for item in "${plan[@]}"; do
  IFS='|' read -r folder file bytes prefix <<<"$item"
  [ -f "$DEST/$file" ] && continue
  echo "==> $file"
  # Resume after dropped connections: curl's own --retry gives up on mid-transfer errors,
  # so loop, picking up where the .part file left off. A stall (<10 KB/s for 2 min) counts as a drop.
  tries=0
  until curl -fL --retry 5 --retry-delay 10 --retry-all-errors --speed-limit 10000 --speed-time 120 \
          -C - -o "$DEST/$file.part" "$BASE/$folder/$file"; do
    tries=$(( tries + 1 ))
    if (( tries >= 50 )); then echo "    !! giving up on $file after $tries attempts (re-run to resume)"; continue 2; fi
    echo "    connection dropped, resuming in 30 s (attempt $tries)..."
    sleep 30
  done
  if sum=$(curl -fsL "$BASE/$folder/$file.sha256" 2>/dev/null | awk '{print $1}') && [ -n "$sum" ]; then
    echo "    verifying checksum..."
    echo "$sum  $DEST/$file.part" | sha256sum -c --quiet - || { echo "    checksum FAILED, deleting"; rm -f "$DEST/$file.part"; continue; }
  fi
  mv "$DEST/$file.part" "$DEST/$file"
  # remove older versions of the same ZIM
  for old in "$DEST/$prefix"*.zim; do
    [ "$old" != "$DEST/$file" ] && [ -f "$old" ] && { echo "    removing old $(basename "$old")"; rm -f "$old"; }
  done
done

echo "Restarting Kiwix to pick up new files..."
{ docker compose restart kiwix || sg docker -c "docker compose restart kiwix"; } >/dev/null 2>&1 || echo "(start the stack with: docker compose up -d)"
echo "Done."
