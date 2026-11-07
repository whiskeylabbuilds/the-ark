#!/usr/bin/env bash
# Pull the AI models into Ollama. Run with the stack up. Picks a set that suits this machine:
#   full   (GPU with 6 GB+, or 16 GB+ RAM)  ~17 GB: Quick Answers, Deep Thinker, Second Opinion, Photo Helper
#   small  (anything less)                   ~7 GB: Quick Answers and Photo Helper
#   MODEL_SET=small scripts/pull-models.sh   # choose yourself
# Only one chat model is loaded at a time. On the CPU the 8B models work but answer slowly.
set -euo pipefail
cd "$(dirname "$0")/.."

vram_gb() {
  if command -v nvidia-smi >/dev/null && nvidia-smi >/dev/null 2>&1; then
    nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits | head -1 | awk '{print int($1/1024+0.5)}'; return
  fi
  local f; for f in /sys/class/drm/card*/device/mem_info_vram_total; do
    [ -r "$f" ] && { awk '{print int($1/1024/1024/1024+0.5)}' "$f"; return; }
  done
  echo 0
}
RAM=$(awk '/MemTotal/ {print int($2/1024/1024+0.5)}' /proc/meminfo)
VRAM=$(vram_gb)
if [ -z "${MODEL_SET:-}" ]; then
  if [ "$VRAM" -ge 6 ] || [ "$RAM" -ge 16 ]; then MODEL_SET=full; else MODEL_SET=small; fi
fi
echo "RAM ${RAM} GB, graphics memory ${VRAM} GB -> model set: $MODEL_SET"

MODELS=(
  qwen3:4b-instruct   # ~2.5 GB  Quick Answers: fast everyday model, good with tools (also Ark Mechanic's base)
  gemma3:4b           # ~3.3 GB  Photo Helper: reads images
  nomic-embed-text    # ~0.3 GB  required: search index for the Bookshelf and your documents
)
if [ "$MODEL_SET" = full ]; then
  MODELS+=(
    qwen3:8b          # ~5.2 GB  Deep Thinker: best reasoning, slower
    llama3.1:8b       # ~4.9 GB  Second Opinion: a different model family
  )
fi

dc() { docker compose "$@" 2>/dev/null || sg docker -c "docker compose $*"; }
for m in "${MODELS[@]}"; do
  echo "==> $m"
  dc exec -T ollama ollama pull "$m" < /dev/null
done
dc exec -T ollama ollama list
