#!/usr/bin/env bash
# check_review.sh: validate a filled watch-review file before any upload.
# Passes only when: two distinct reviewer families, each reviewer model differs
# from author_model and from the other reviewer, every criterion in
# review_template.json is present, and every score is an integer 1-5 with score >= 4.
#
# Usage: scripts/check_review.sh <review.json>
# Exit: 0 pass, 1 fail (reasons on stderr), 2 usage or unreadable file.
set -euo pipefail

usage() {
  echo "usage: $0 <review.json>" >&2
  exit 2
}

[[ $# -eq 1 ]] || usage
review=$1
[[ -f $review ]] || { echo "error: no such file: $review" >&2; exit 2; }

template="$(dirname -- "${BASH_SOURCE[0]}")/review_template.json"
[[ -f $template ]] || { echo "error: missing template: $template" >&2; exit 2; }

command -v jq >/dev/null || { echo "error: jq not found on PATH" >&2; exit 2; }

if ! jq -e . -- "$review" >/dev/null 2>&1; then
  echo "FAIL: $review is not valid JSON" >&2
  exit 1
fi

criteria=$(jq -c '.family_a.scores | keys' -- "$template")

problems=$(jq -r --argjson req "$criteria" '
  def nonempty: type == "string" and length > 0;
  ( if (.author_model | nonempty) | not then "author_model is empty" else empty end ),
  ( ["family_a", "family_b"][] as $s
    | (.[$s]) as $slot
    | if ($slot | type) != "object" then "\($s) is missing"
      else
        ( if ($slot.family | nonempty) | not then "\($s).family is empty" else empty end ),
        ( if ($slot.model | nonempty) | not then "\($s).model is empty"
          elif $slot.model == .author_model then "\($s).model equals author_model (same model id as the author)"
          else empty end ),
        ( ($slot.scores) as $sc
          | if ($sc | type) != "object" then "\($s).scores is missing"
            else
              ( $req[] as $c
                | if ($sc | has($c)) | not then "\($s).scores.\($c) is missing"
                  else ($sc[$c]) as $v
                    | if ($v | type) != "number" or $v != ($v | floor) then "\($s).scores.\($c) is not an integer (\($v | tojson))"
                      elif $v < 1 or $v > 5 then "\($s).scores.\($c) is outside 1-5 (\($v))"
                      elif $v < 4 then "\($s).scores.\($c) is below 4 (\($v))"
                      else empty end
                  end ),
              ( $sc | keys[] as $k
                | select(($req | contains([$k])) | not)
                | "\($s).scores.\($k) is not a template criterion" )
            end )
      end ),
  ( if (.family_a.family | nonempty) and .family_a.family == .family_b.family
    then "family_a and family_b are the same family" else empty end ),
  ( if (.family_a.model | nonempty) and .family_a.model == .family_b.model
    then "family_a and family_b use the same model id" else empty end )
' -- "$review")

if [[ -n $problems ]]; then
  while IFS= read -r line; do
    echo "FAIL: $line" >&2
  done <<< "$problems"
  exit 1
fi

echo "PASS: $review"
