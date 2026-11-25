#!/usr/bin/env bash
# selftest.sh: exercises check_review.sh on fixtures and on mutated copies,
# and watch_review.sh on a generated synthetic clip. Needs jq, and ffmpeg for
# the clip step. Exit 0 when every assertion holds.
set -euo pipefail

here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
check="$here/check_review.sh"
watch="$here/watch_review.sh"
fixtures="$here/fixtures"

work=$(mktemp -d)
trap 'rm -rf -- "$work"' EXIT

pass_count=0
fail_count=0

ok() { pass_count=$((pass_count + 1)); echo "ok   - $1"; }
bad() { fail_count=$((fail_count + 1)); echo "FAIL - $1"; }

# expect_rc <name> <expected rc> <review file> [grep pattern for stderr]
expect_rc() {
  local name=$1 want=$2 file=$3 pattern=${4:-}
  local err rc=0
  err=$("$check" "$file" 2>&1 >/dev/null) || rc=$?
  if [[ $rc -ne $want ]]; then
    bad "$name (rc=$rc, want $want)"
    return
  fi
  if [[ -n $pattern ]] && ! grep -q -- "$pattern" <<< "$err"; then
    bad "$name (stderr lacks '$pattern')"
    return
  fi
  ok "$name"
}

# mutate <name> <jq filter> <expected rc> [stderr pattern]
mutate() {
  local name=$1 filter=$2 want=$3 pattern=${4:-}
  local slug file
  slug=$(echo "$name" | tr ' ' '_')
  file="$work/$slug.json"
  jq "$filter" "$fixtures/review_pass.json" > "$file"
  expect_rc "$name" "$want" "$file" "$pattern"
}

expect_rc "passing fixture passes" 0 "$fixtures/review_pass.json"
expect_rc "failing fixture fails" 1 "$fixtures/review_fail.json" "pacing is below 4"
expect_rc "failing fixture reports missing criterion" 1 "$fixtures/review_fail.json" "glitch_intro_exit is missing"
expect_rc "failing fixture reports non-integer score" 1 "$fixtures/review_fail.json" "not an integer"
expect_rc "template (blank) fails" 1 "$here/review_template.json"

mutate "same family rejected" '.family_b.family = .family_a.family' 1 "same family"
mutate "reviewer model equals author rejected" '.family_a.model = .author_model' 1 "equals author_model"
mutate "same reviewer model id rejected" '.family_b.model = .family_a.model' 1 "same model id"
mutate "score 5 accepted" '.family_a.scores.pacing = 5' 0
mutate "score 0 rejected" '.family_a.scores.pacing = 0' 1 "outside 1-5"
mutate "score 6 rejected" '.family_a.scores.pacing = 6' 1 "outside 1-5"
mutate "string score rejected" '.family_a.scores.pacing = "4"' 1 "not an integer"
mutate "unknown criterion rejected" '.family_a.scores.loudness = 5' 1 "not a template criterion"
mutate "missing author model rejected" '.author_model = ""' 1 "author_model is empty"
mutate "missing family_b rejected" 'del(.family_b)' 1 "family_b is missing"

if ! command -v ffmpeg >/dev/null; then
  echo "skip - watch_review synthetic clip (ffmpeg not on PATH)"
else
  clip="$work/synthetic.mp4"
  ffmpeg -v error -y -f lavfi -i testsrc=duration=50:size=640x360:rate=25 \
    -f lavfi -i sine=frequency=440:duration=50 \
    -c:v libx264 -pix_fmt yuv420p -c:a aac -shortest "$clip"
  sheet=$("$watch" "$clip" "$work/out")
  if [[ $(ffprobe -v error -show_entries stream=codec_name -of csv=p=0 "$sheet") == png ]]; then
    ok "watch_review writes a PNG contact sheet"
  else
    bad "watch_review contact sheet is not a PNG"
  fi
  if [[ $(jq -r '.frame_count' "$work/out/manifest.json") == 7 ]] \
     && [[ $(jq -r '.frames[-1].t_s' "$work/out/manifest.json") == 48 ]]; then
    ok "watch_review manifest: 7 frames at 0..48 s for a 50 s clip"
  else
    bad "watch_review manifest timestamps wrong"
  fi
fi

echo "selftest: $pass_count passed, $fail_count failed"
[[ $fail_count -eq 0 ]]
