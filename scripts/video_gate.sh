#!/usr/bin/env bash
# video_gate.sh - measurable part of the VIDEO-QUALITY-GATE for course mp4s.
#
# Usage:
#   video_gate.sh [--json] <file.mp4> ...   measure each file, exit 0 all PASS, 1 any FAIL, 2 any NOT_MEASURED
#   video_gate.sh --selftest                synthetic-clip self-test (exit 0 = all assertions hold)
#
# Gates:
#   silence   no silence over MAX_SILENCE s (default 1.0), silencedetect at SILENCE_DB (default -45 dB)
#   cadence   a visual change at least every MAX_GAP s (default 8), scene score > SCENE_T (default 0.01);
#             gaps counted from t=0 and to the end of the file
#   glitch    cards only (basename intro.mp4 = 3.50 s, conclusion.mp4 = 6.50 s, +/- 0.05 s);
#             any other file is NOT_MEASURED (its pinned card sha is checked by build.sh, not here)
set -euo pipefail

MAX_SILENCE=${MAX_SILENCE:-1.0}
MAX_GAP=${MAX_GAP:-8}
SCENE_T=${SCENE_T:-0.01}
SILENCE_DB=${SILENCE_DB:--45dB}
JSON=0

die() { echo "video_gate: $*" >&2; exit 3; }
command -v ffmpeg >/dev/null && command -v ffprobe >/dev/null || die "ffmpeg/ffprobe not on PATH"

duration_of() { ffprobe -v error -show_entries format=duration -of csv=p=0 "$1"; }

has_audio() { [ -n "$(ffprobe -v error -select_streams a -show_entries stream=index -of csv=p=0 "$1")" ]; }

# Longest silence (seconds) and count of silences over MAX_SILENCE.
measure_silence() {
  local f=$1 total
  total=$(duration_of "$f")
  if ! has_audio "$f"; then echo "NOAUDIO 0 0"; return; fi
  ffmpeg -nostdin -hide_banner -i "$f" -af "silencedetect=noise=$SILENCE_DB:d=0.5" -vn -f null - 2>&1 |
    awk -v total="$total" -v max="$MAX_SILENCE" '
      /silence_start/ { s = $0; sub(/.*silence_start: /, "", s); start = s + 0; open = 1 }
      /silence_duration/ { d = $0; sub(/.*silence_duration: /, "", d); d += 0;
                           if (d > longest) longest = d; if (d > max) over++; open = 0 }
      END {
        if (open) { d = total - start; if (d > longest) longest = d; if (d > max) over++ }
        printf "OK %.3f %d\n", longest + 0, over + 0 }'
}

# Largest gap (seconds) between consecutive visual changes, including t=0 and end of file.
measure_cadence() {
  local f=$1 total
  total=$(duration_of "$f")
  ffmpeg -nostdin -hide_banner -i "$f" -vf "select='gt(scene,$SCENE_T)',metadata=print:file=-" -an -f null - 2>/dev/null |
    { grep -o 'pts_time:[0-9.]*' || true; } | cut -d: -f2 |
    awk -v total="$total" '
      { gap = $1 - prev; if (gap > longest) longest = gap; prev = $1; n++ }
      END { gap = total - prev; if (gap > longest) longest = gap
            printf "%.3f %d\n", longest + 0, n + 0 }'
}

# Card length check for the two glitch cards. Prints PASS/FAIL/NOT_MEASURED.
glitch_gate() {
  local f=$1 want d
  case "$(basename "$f")" in
    intro.mp4) want=3.50 ;;
    conclusion.mp4) want=6.50 ;;
    *) echo "NOT_MEASURED"; return ;;
  esac
  d=$(duration_of "$f")
  awk -v d="$d" -v w="$want" 'BEGIN { exit !((d - w) < 0.05 && (w - d) < 0.05) }' && echo "PASS" || echo "FAIL"
}

measure_file() {
  local f=$1 dur sil_line sil_max sil_over cad_line cad_max cad_n sil_gate cad_gate gl_gate sil_ok sil_res
  [ -r "$f" ] || die "cannot read $f"
  dur=$(duration_of "$f")
  sil_line=$(measure_silence "$f")
  read -r sil_ok sil_max sil_over <<<"$sil_line"
  cad_line=$(measure_cadence "$f")
  read -r cad_max cad_n <<<"$cad_line"
  gl_gate=$(glitch_gate "$f")

  if [ "$sil_ok" = "NOAUDIO" ]; then sil_gate=FAIL; sil_max=$dur
  elif awk -v m="$sil_max" -v x="$MAX_SILENCE" 'BEGIN { exit !(m > x) }'; then sil_gate=FAIL
  else sil_gate=PASS; fi
  awk -v m="$cad_max" -v x="$MAX_GAP" 'BEGIN { exit !(m > x) }' && cad_gate=FAIL || cad_gate=PASS

  if [ "$JSON" = 1 ]; then
    jq -cn --arg file "$f" --arg dur "$dur" --arg smax "$sil_max" --argjson sover "$sil_over" \
      --arg sg "$sil_gate" --arg cmax "$cad_max" --argjson cn "$cad_n" --arg cg "$cad_gate" --arg gg "$gl_gate" \
      '{file: $file, duration_s: ($dur|tonumber), max_silence_s: ($smax|tonumber), silences_over_limit: $sover,
        silence_gate: $sg, max_visual_gap_s: ($cmax|tonumber), visual_changes: $cn, cadence_gate: $cg, glitch_gate: $gg}'
  else
    printf '%s duration=%.3f max_silence=%s silence=%s max_gap=%s changes=%s cadence=%s glitch=%s\n' \
      "$f" "$dur" "$sil_max" "$sil_gate" "$cad_max" "$cad_n" "$cad_gate" "$gl_gate"
  fi

  RESULT_FAIL=0; RESULT_NM=0
  for g in "$sil_gate" "$cad_gate" "$gl_gate"; do
    [ "$g" = FAIL ] && RESULT_FAIL=1
    [ "$g" = NOT_MEASURED ] && RESULT_NM=1
  done
  return 0
}

selftest() {
  local t fails=0 out
  t=$(mktemp -d "${TMPDIR:-/tmp}/video_gate_selftest.XXXXXX")
  # Tone for 2 s, silence for SIL seconds, tone again. Video: testsrc (changes every frame).
  mk_sil() { ffmpeg -nostdin -hide_banner -loglevel error -y -f lavfi -i "testsrc=size=320x240:rate=25:duration=5" \
      -f lavfi -i "aevalsrc='if(lt(t,2)+gte(t,2+$2),sin(2*PI*440*t),0)':d=5:s=44100" \
      -shortest -c:v libx264 -pix_fmt yuv420p -c:a aac "$1"; }
  mk_static() { ffmpeg -nostdin -hide_banner -loglevel error -y -f lavfi -i "color=c=gray:s=320x240:r=25:d=9" \
      -f lavfi -i "sine=f=440:d=9" -shortest -c:v libx264 -pix_fmt yuv420p -c:a aac "$1"; }
  mk_moving() { ffmpeg -nostdin -hide_banner -loglevel error -y -f lavfi -i "testsrc=size=320x240:rate=25:duration=9" \
      -f lavfi -i "sine=f=440:d=9" -shortest -c:v libx264 -pix_fmt yuv420p -c:a aac "$1"; }
  mk_sil "$t/sil10.mp4" 1.0
  mk_sil "$t/sil15.mp4" 1.5
  mk_static "$t/static9.mp4"
  mk_moving "$t/moving9.mp4"

  check() { # name expected actual
    if [ "$3" = "$2" ]; then echo "selftest ok   $1 -> $3"; else echo "selftest FAIL $1 expected $2 got $3"; fails=$((fails + 1)); fi
  }
  gate_of() { "$0" "$1" | sed -E "s/.* $2=([A-Z_]+).*/\1/"; }
  check "1.0 s silence passes silence gate" PASS "$(gate_of "$t/sil10.mp4" silence)"
  check "1.5 s silence fails silence gate" FAIL "$(gate_of "$t/sil15.mp4" silence)"
  check "9 s static clip fails cadence" FAIL "$(gate_of "$t/static9.mp4" cadence)"
  check "9 s moving clip passes cadence" PASS "$(gate_of "$t/moving9.mp4" cadence)"
  rm -rf "${t:?}"
  [ "$fails" -eq 0 ] && echo "selftest: all assertions hold" || echo "selftest: $fails FAILED"
  [ "$fails" -eq 0 ]
}

case "${1:-}" in
  --selftest) selftest; exit $? ;;
  "") die "usage: video_gate.sh [--json] <file.mp4> ... | --selftest" ;;
esac
if [ "$1" = "--json" ]; then JSON=1; shift; fi

ANY_FAIL=0; ANY_NM=0
for f in "$@"; do
  measure_file "$f"
  [ "$RESULT_FAIL" = 1 ] && ANY_FAIL=1
  [ "$RESULT_NM" = 1 ] && ANY_NM=1
done
[ "$ANY_FAIL" = 1 ] && exit 1
[ "$ANY_NM" = 1 ] && exit 2
exit 0
