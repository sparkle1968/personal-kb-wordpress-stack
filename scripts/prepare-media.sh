#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 FILE_OR_DIRECTORY [...]"
  exit 1
fi

cd "$(dirname "$0")/.."
mkdir -p prepared-media

image_tool() {
  if command -v magick >/dev/null 2>&1; then
    echo "magick"
  elif command -v convert >/dev/null 2>&1; then
    echo "convert"
  else
    echo "ImageMagick is required. Install imagemagick first." >&2
    exit 1
  fi
}

process_image() {
  local input="$1"
  local base
  base="$(basename "${input%.*}")"
  local output="prepared-media/${base}.jpg"
  "$(image_tool)" "$input" -auto-orient -strip -quality 88 "$output"
  echo "$output"
}

process_video() {
  local input="$1"
  local base
  base="$(basename "${input%.*}")"
  local output="prepared-media/${base}.mp4"
  local cover="prepared-media/${base}-cover.jpg"
  ffmpeg -y -i "$input" -map_metadata -1 \
    -vf "scale='min(1920,iw)':-2" \
    -c:v libx264 -preset medium -crf 23 \
    -c:a aac -b:a 160k \
    "$output"
  ffmpeg -y -ss 00:00:01 -i "$output" -frames:v 1 -q:v 2 "$cover"
  echo "$output"
  echo "$cover"
}

walk_input() {
  local input="$1"
  if [[ -d "$input" ]]; then
    find "$input" -type f
  else
    printf '%s\n' "$input"
  fi
}

for item in "$@"; do
  while IFS= read -r file; do
    case "${file,,}" in
      *.jpg|*.jpeg|*.png|*.heic|*.webp) process_image "$file" ;;
      *.mov|*.mp4|*.m4v|*.avi|*.mkv) process_video "$file" ;;
      *) echo "Skipping unsupported file: $file" ;;
    esac
  done < <(walk_input "$item")
done
