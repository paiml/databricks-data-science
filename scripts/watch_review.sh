#!/usr/bin/env bash
# watch_review.sh: one frame every 8 s of a course video, tiled into a contact
# sheet, plus a JSON manifest of the frame timestamps. Runs ffmpeg locally.
#
# Usage: scripts/watch_review.sh <video.mp4> [out_dir]
# Output: <out_dir>/contact_sheet.png and <out_dir>/manifest.json
#         (out_dir defaults to <video dir>/watch-review). Prints the sheet path.
set -euo pipefail

INTERVAL=8   # seconds between sampled frames
COLS=5       # contact sheet columns
THUMB_W=320  # thumbnail width in pixels

usage() {
  echo "usage: $0 <video.mp4> [out_dir]" >&2
  exit 2
}

[[ $# -ge 1 && $# -le 2 ]] || usage
video=$1
[[ -f $video ]] || { echo "error: no such file: $video" >&2; exit 2; }
out_dir=${2:-"$(dirname -- "$video")/watch-review"}

for tool in ffmpeg ffprobe jq sha256sum; do
  command -v "$tool" >/dev/null || { echo "error: $tool not found on PATH" >&2; exit 2; }
done

mkdir -p -- "$out_dir"
sheet="$out_dir/contact_sheet.png"
manifest="$out_dir/manifest.json"

# Sampled frames sit at t = 0, 8, 16, ... <= duration: floor(duration/8)+1 of them.
duration=$(ffprobe -v error -show_entries format=duration -of csv=p=0 -- "$video")
[[ $duration =~ ^[0-9]+(\.[0-9]+)?$ ]] || { echo "error: cannot read duration of $video" >&2; exit 1; }
whole_seconds=${duration%%.*}
frame_count=$(( whole_seconds / INTERVAL + 1 ))
rows=$(( (frame_count + COLS - 1) / COLS ))

# ffmpeg flushes a partly filled final tile row at end of stream, so the
# grid only needs to be sized, not padded with extra frames.
ffmpeg -v error -y -i "$video" \
  -vf "fps=1/${INTERVAL},scale=${THUMB_W}:-2,tile=${COLS}x${rows}" \
  -frames:v 1 -- "$sheet"

video_sha=$(sha256sum -- "$video" | cut -d' ' -f1)
jq -n \
  --arg video "$(basename -- "$video")" \
  --arg sha "$video_sha" \
  --arg sheet "$(basename -- "$sheet")" \
  --argjson interval "$INTERVAL" \
  --argjson duration "$duration" \
  --argjson n "$frame_count" \
  '{video: $video, video_sha256: $sha, duration_s: $duration,
    interval_s: $interval, contact_sheet: $sheet, frame_count: $n,
    frames: [range(0; $n) | {index: ., t_s: (. * $interval)}]}' > "$manifest"

echo "$sheet"
