#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SKILL_FILE="$ROOT_DIR/skills/wrap-session/SKILL.md"
REFERENCE_FILE="$ROOT_DIR/skills/wrap-session/closeout-artifacts.md"

fail() {
  printf 'FAIL: %s\n' "$1" >&2
  exit 1
}

[[ -f "$SKILL_FILE" ]] || fail "missing skills/wrap-session/SKILL.md"
[[ -f "$REFERENCE_FILE" ]] || fail "missing wrap-session artifact reference"

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

printf 'PASS: wrap-session contract\n'
