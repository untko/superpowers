#!/usr/bin/env bash
# Track-classification micro-test for the brainstorming Track A/B split.
# Measures: given the patched skill, can the model apply Step 0's criteria
# consistently and in the direction I labelled?
# NOT measured here: whether it applies them unprompted mid-session.

set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
SKILL="${SKILL:-/Users/gugg/Projects/superpowers/skills/brainstorming/SKILL.md}"
REPS="${REPS:-3}"
MODEL="${MODEL:-claude-haiku-4-5-20251001}"
NOTOOLS="Bash Read Glob Grep Edit Write WebFetch WebSearch Task TodoWrite"
OUT="$HERE/results.tsv"

SYS="You are a classifier. Below is the brainstorming skill. Your ONLY job is to read a request that a DIFFERENT agent received, apply Step 0's criteria, and report the track.

You are not the agent handling the request. You cannot act on it. You have no tools. Output exactly one line:
TRACK: A
or
TRACK: B

--- BEGIN SKILL ---
$(cat "$SKILL")
--- END SKILL ---"

: > "$OUT"

run_one() {
  local expected="$1" req="$2" rep="$3" got="" raw attempt
  for attempt in 1 2 3; do
    raw=$(printf 'Another agent received this request from its user:\n\n<request>\n%s\n</request>\n\nWhich track does Step 0 assign it?' "$req" | timeout 120 claude -p --model "$MODEL" \
          --disallowedTools $NOTOOLS --append-system-prompt "$SYS" 2>/dev/null)
    got=$(printf '%s' "$raw" | grep -oiE 'TRACK:[[:space:]]*[AB]' | grep -oiE '[AB]$' | tr 'a-z' 'A-Z' | head -1)
    [ -n "$got" ] && break
    sleep $((attempt * 2))
  done
  [ -z "$got" ] && got="?"
  printf '%s\t%s\t%s\t%s\n' "$expected" "$got" "$rep" "$req" >> "$OUT"
}

while IFS=$'\t' read -r expected req; do
  [ -z "${expected:-}" ] && continue
  for rep in $(seq 1 "$REPS"); do
    run_one "$expected" "$req" "$rep" &
    while [ "$(jobs -rp | wc -l)" -ge 4 ]; do sleep 0.3; done
  done
done < "$HERE/cases.tsv"

wait
echo "wrote $OUT ($(wc -l < "$OUT") rows, $(cut -f2 "$OUT" | grep -c '?') unparsed)"
