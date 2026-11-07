#!/usr/bin/env bash
# Build the offline map for your region (MAP_BBOX and MAP_REGION_NAME in .env):
#  1. cut the region out of the latest Protomaps planet build (pmtiles extract, run in Docker)
#  2. download the MapLibre viewer, fonts and icons so the map works with no internet
# Output: $ARK_DATA/maps/www, served by the "maps" container on port 8082.
#
#   scripts/build-maps.sh              # max zoom 15 (street level, everything)
#   MAXZOOM=14 scripts/build-maps.sh   # smaller file, slightly less detail
set -euo pipefail
cd "$(dirname "$0")/.."
[ -f .env ] && set -a && . ./.env && set +a

WWW="${ARK_DATA:-/srv/ark}/maps/www"
# west,south,east,north in degrees. Find yours at https://bboxfinder.com (draw a box, copy "Box").
# Example: Texas, Oklahoma, Arkansas and Louisiana = -106.7,25.8,-88.8,37.1 (about 2 GB at zoom 15).
BBOX="${BBOX:-${MAP_BBOX:-}}"
REGION="${MAP_REGION_NAME:-Regional map}"
if [ -z "$BBOX" ]; then
  echo "Set MAP_BBOX (west,south,east,north) and MAP_REGION_NAME in .env first. See https://bboxfinder.com"; exit 1
fi
MAXZOOM="${MAXZOOM:-15}"
PMTILES_IMG="ghcr.io/protomaps/go-pmtiles:latest"
MAPLIBRE_VER="5.24.0"    # 6.x dropped the single-file browser build
PMTILES_JS_VER="4.5.0"
BASEMAPS_VER="5.7.2"

mkdir -p "$WWW/assets"

BUILD=$(curl -fsL https://build-metadata.protomaps.dev/builds.json \
  | python3 -I -c "import json,sys; print(json.load(sys.stdin)[-1]['key'])")
SRC="https://build.protomaps.com/$BUILD"
echo "Planet build: $BUILD   bbox: $BBOX   max zoom: $MAXZOOM"

echo "==> Estimating size (dry run)"
docker run --rm "$PMTILES_IMG" extract "$SRC" /tmp/x.pmtiles --bbox="$BBOX" --maxzoom="$MAXZOOM" --dry-run
df -h "$WWW" | tail -1
read -rp "Extract now? [y/N] " a; [[ "$a" =~ ^[Yy] ]] || exit 0

echo "==> Extracting (this can take a while)"
docker run --rm -u "$(id -u):$(id -g)" -v "$WWW:/out" "$PMTILES_IMG" \
  extract "$SRC" /out/region.pmtiles.part --bbox="$BBOX" --maxzoom="$MAXZOOM"
mv "$WWW/region.pmtiles.part" "$WWW/region.pmtiles"

echo "==> Viewer libraries"
curl -fsSL -o "$WWW/assets/maplibre-gl.js"  "https://unpkg.com/maplibre-gl@$MAPLIBRE_VER/dist/maplibre-gl.js"
curl -fsSL -o "$WWW/assets/maplibre-gl.css" "https://unpkg.com/maplibre-gl@$MAPLIBRE_VER/dist/maplibre-gl.css"
curl -fsSL -o "$WWW/assets/pmtiles.js"      "https://unpkg.com/pmtiles@$PMTILES_JS_VER/dist/pmtiles.js"
curl -fsSL -o "$WWW/assets/basemaps.js"     "https://unpkg.com/@protomaps/basemaps@$BASEMAPS_VER/dist/basemaps.js"

echo "==> Fonts and map icons"
tmp=$(mktemp -d)
curl -fsSL https://github.com/protomaps/basemaps-assets/archive/refs/heads/main.tar.gz | tar xz -C "$tmp"
rm -rf "$WWW/assets/fonts" "$WWW/assets/sprites"
mv "$tmp"/basemaps-assets-main/fonts "$WWW/assets/fonts"
mkdir -p "$WWW/assets/sprites" && mv "$tmp"/basemaps-assets-main/sprites/v4 "$WWW/assets/sprites/v4"
rm -rf "$tmp"

python3 -I - "$REGION" "$BBOX" config/maps/index.html "$WWW/index.html" <<'PY'
import html, sys
region, bbox, src, dst = sys.argv[1:]
s = open(src).read().replace("__REGION__", html.escape(region)).replace("__BBOX__", ",".join(str(float(x)) for x in bbox.split(",")))
open(dst, "w").write(s)
PY
cp config/homepage/icons/ark.svg "$WWW/ark.svg"
du -sh "$WWW"
echo "Done. Open http://${HOST_ADDR:-localhost}:8082"
