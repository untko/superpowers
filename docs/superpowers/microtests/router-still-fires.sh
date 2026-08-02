#!/usr/bin/env bash
# Guard for using-superpowers: does the router still name a skill after the
# anti-ceremony Red Flags row was added? Every case below MUST name a skill.
# The failure this catches: "it's small, I'll just answer" — the exact
# rationalization the new row could be misread as licensing.

set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
SKILL="${SKILL:-$HERE/../../../skills/using-superpowers/SKILL.md}"
REPS="${REPS:-3}"
MODEL="${MODEL:-claude-haiku-4-5-20251001}"
NOTOOLS="Bash Read Glob Grep Edit Write WebFetch WebSearch Task TodoWrite"
OUT="$HERE/router-results.tsv"

SYS="$(cat "$SKILL")

---

Before responding to the user's message, state your FIRST action. Reply with
exactly one line and nothing else:
SKILL: <skill-name>
or
SKILL: none"

CASES=(
  "Let's make a react todo list"
  "Fix this bug: the login button does nothing on Safari"
  "Can you just quickly rename getUserData to fetchUserProfile?"
  "What's the fastest way to add a config option here?"
  "Add a --json flag to the status command"
)

: > "$OUT"
for req in "${CASES[@]}"; do
  for rep in $(seq 1 "$REPS"); do
    (
      got=""
      for attempt in 1 2 3; do
        got=$(printf '%s' "$req" | timeout 120 claude -p --model "$MODEL" \
              --disallowedTools $NOTOOLS --append-system-prompt "$SYS" 2>/dev/null \
              | grep -oiE 'SKILL:[[:space:]]*[a-z-]+' | sed 's/.*[[:space:]]//' | head -1)
        [ -n "$got" ] && break
        sleep $((attempt * 2))
      done
      [ -z "$got" ] && got="?"
      printf '%s\t%s\t%s\n' "$got" "$rep" "$req" >> "$OUT"
    ) &
    while [ "$(jobs -rp | wc -l)" -ge 4 ]; do sleep 0.3; done
  done
done
wait

echo "--- results ---"
awk -F'\t' '{print "  "$1"\t"$3}' "$OUT" | sort -u
none=$(cut -f1 "$OUT" | grep -ciE '^(none|\?)$')
echo "---"
echo "answered without a skill: $none / $(wc -l < "$OUT")   (bar: 0)"
