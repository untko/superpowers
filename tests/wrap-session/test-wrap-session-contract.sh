#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SKILL_FILE="$ROOT_DIR/skills/wrap-session/SKILL.md"
REFERENCE_FILE="$ROOT_DIR/skills/wrap-session/references/closeout-artifacts.md"
OLD_REFERENCE_FILE="$ROOT_DIR/skills/wrap-session/closeout-artifacts.md"

fail() {
  printf 'FAIL: %s\n' "$1" >&2
  exit 1
}

[[ -f "$SKILL_FILE" ]] || fail "missing skills/wrap-session/SKILL.md"
[[ -f "$REFERENCE_FILE" ]] || fail "missing wrap-session artifact reference"
[[ ! -e "$OLD_REFERENCE_FILE" ]] ||
  fail "old wrap-session artifact reference must be moved, not duplicated"

grep -q '^name: wrap-session$' "$SKILL_FILE" ||
  fail "skill name is missing or invalid"
grep -q '^description: Use when ' "$SKILL_FILE" ||
  fail "description must contain triggering conditions"
grep -q '\.agents/superpowers/wrap-session/adapter\.md' "$SKILL_FILE" ||
  fail "optional adapter path is missing"
grep -Eqi 'finish.*handoff|handoff.*finish' "$SKILL_FILE" ||
  fail "finish-or-handoff decision is missing"
grep -Eqi 'proportion|changed artifact|risk' "$SKILL_FILE" ||
  fail "proportional verification guidance is missing"
grep -Eqi 'unrelated|session-owned|owned changes' "$SKILL_FILE" ||
  fail "owned-file staging boundary is missing"
grep -Eqi 'receipt' "$SKILL_FILE" ||
  fail "completion receipt is missing"
grep -q 'schema: superpowers-adapter/v1' "$SKILL_FILE" &&
  grep -q 'extends: wrap-session' "$SKILL_FILE" &&
  grep -q 'contract: 1' "$SKILL_FILE" &&
  grep -q 'adapter-version' "$SKILL_FILE" ||
  fail "adapter schema and contract validation is incomplete"
grep -Fqi 'current phase' "$SKILL_FILE" ||
  fail "adapter resources must be limited to the current phase"
grep -Eqi 'reject (adapter resource )?directories' "$SKILL_FILE" ||
  fail "adapter resource directories must be rejected"
grep -q 'references/closeout-artifacts\.md' "$SKILL_FILE" ||
  fail "new artifact reference path is missing"
grep -q '\.superpowers/observations/pending/' "$SKILL_FILE" ||
  fail "repository-local pending observation path is missing"
grep -q 'superpowers:verification-before-completion' "$SKILL_FILE" ||
  fail "verification delegation is missing"
grep -q 'superpowers:finishing-a-development-branch' "$SKILL_FILE" ||
  fail "completed branch disposition delegation is missing"
grep -Eqi 'push.*separate.*(authoriz|approval)|separate.*push.*(authoriz|approval)' "$SKILL_FILE" ||
  fail "separate push authorization is missing"

for field in \
  "Owned scope" \
  "Adapter status" \
  "Durable artifacts" \
  "Verification" \
  "Git" \
  "Remaining work" \
  "Observations"
do
  grep -Fq "$field:" "$SKILL_FILE" ||
    fail "completion receipt field is missing: $field"
done

WORD_COUNT="$(wc -w < "$SKILL_FILE")"
(( WORD_COUNT < 500 )) ||
  fail "SKILL.md must stay below 500 words (found $WORD_COUNT)"

if grep -Eqi '/Users/|Obsidian|vault' "$SKILL_FILE" "$REFERENCE_FILE"; then
  fail "wrap-session guidance contains a repository-specific path or artifact"
fi

printf 'PASS: wrap-session contract\n'
