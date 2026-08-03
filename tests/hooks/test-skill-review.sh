#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
FAILURES=0

pass() {
  echo "  [PASS] $1"
}

fail() {
  echo "  [FAIL] $1"
  FAILURES=$((FAILURES + 1))
}

echo "Skill-review hook contract tests"

if node -e '
const fs = require("fs");
const hooks = JSON.parse(fs.readFileSync(process.argv[1], "utf8"));
const entry = hooks.hooks.Stop[0].hooks[0];
if (entry.type !== "command" || entry.shell !== "bash" || entry.async !== true) process.exit(1);
if (entry.command !== "\"${CLAUDE_PLUGIN_ROOT}/hooks/run-hook.cmd\" skill-review") process.exit(1);
' "$REPO_ROOT/hooks/hooks.json"; then
  pass "hooks.json registers an async Bash Stop hook through run-hook.cmd"
else
  fail "hooks.json registers an async Bash Stop hook through run-hook.cmd"
fi

if node -e '
const fs = require("fs");
const hooks = JSON.parse(fs.readFileSync(process.argv[1], "utf8"));
if (!hooks.hooks.stop || hooks.hooks.stop[0].command !== "./hooks/run-hook.cmd skill-review") process.exit(1);
' "$REPO_ROOT/hooks/hooks-cursor.json"; then
  pass "Cursor registers the lowercase stop hook through run-hook.cmd"
else
  fail "Cursor registers the lowercase stop hook through run-hook.cmd"
fi

if test -x "$REPO_ROOT/hooks/skill-review"; then
  pass "extensionless skill-review wrapper is executable"
else
  fail "extensionless skill-review wrapper is executable"
fi

if node -e '
const config = require(process.argv[1]);
if (config.threshold !== 10 || config.dry_run !== true) process.exit(1);
' "$REPO_ROOT/hooks/review-config.json"; then
  pass "review config ships with threshold 10 and dry-run enabled"
else
  fail "review config ships with threshold 10 and dry-run enabled"
fi

if node -e '
const map = require(process.argv[1]);
for (const [harness, model] of Object.entries(map)) {
  if (typeof model !== "string" && model !== null) process.exit(1);
  if (typeof model === "string" && model.trim() === "") process.exit(1);
}
if (!("_default" in map) || !("claude-code" in map)) process.exit(1);
' "$REPO_ROOT/hooks/review-model-map.json"; then
  pass "model map has a non-empty/null value for every harness and a default"
else
  fail "model map has a non-empty/null value for every harness and a default"
fi

if rg -n 'claude-haiku|claude-sonnet|gpt-[0-9]' \
  "$REPO_ROOT/hooks/skill_review.py" "$REPO_ROOT/hooks/skill-review" >/dev/null 2>&1; then
  fail "executable hook path does not hardcode a model name"
else
  pass "executable hook path does not hardcode a model name"
fi

if grep -Fxq ".superpowers/" "$REPO_ROOT/.gitignore"; then
  pass ".superpowers runtime state is already covered by gitignore"
else
  fail ".superpowers runtime state is already covered by gitignore"
fi

TEST_ROOT="$(mktemp -d)"
cleanup() {
  rm -rf "$TEST_ROOT"
}
trap cleanup EXIT

project="$TEST_ROOT/project"
transcript="$project/transcript.jsonl"
mkdir -p "$project"
python3 - "$transcript" <<'PY'
import json
import sys
from pathlib import Path

transcript = Path(sys.argv[1])
records = []
for _ in range(10):
    records.append(
        {
            "type": "assistant",
            "message": {
                "content": [
                    {
                        "type": "tool_use",
                        "name": "Read",
                        "input": {"file_path": "skills/demo/SKILL.md"},
                    }
                ]
            },
        }
    )
transcript.write_text("".join(json.dumps(record) + "\n" for record in records))
PY

payload="$(python3 - "$project" "$transcript" <<'PY'
import json
import sys

print(json.dumps({"cwd": sys.argv[1], "transcript_path": sys.argv[2]}))
PY
)"

if printf '%s' "$payload" | \
  CLAUDE_PLUGIN_ROOT="$REPO_ROOT" \
  SUPERPOWERS_REVIEW_DRY_RUN=true \
  bash "$REPO_ROOT/hooks/run-hook.cmd" skill-review; then
  pass "run-hook.cmd dispatches a threshold Stop event successfully"
else
  fail "run-hook.cmd dispatches a threshold Stop event successfully"
fi

log_file="$project/.superpowers/review-log.md"
state_file="$project/.superpowers/review-state.json"
if grep -Fq "tool_calls=10" "$log_file" && \
  grep -Fq "model=claude-haiku-4-5-20251001" "$log_file" && \
  grep -Fq "dry-run-review" "$log_file"; then
  pass "threshold Stop event logs its count and dry-run review outcome"
else
  fail "threshold Stop event logs its count and dry-run review outcome"
fi

if test -s "$state_file" && test ! -d "$project/.superpowers/observations/pending"; then
  pass "dry-run threshold event persists state without creating observations"
else
  fail "dry-run threshold event persists state without creating observations"
fi

first_watermark="$(python3 - "$state_file" <<'PY'
import json
import sys

print(json.load(open(sys.argv[1], encoding="utf-8"))["tool_watermark"])
PY
)"
printf '%s\n' '{"type":"user","message":{"content":"Stop doing that; this skill is wrong."}}' >> "$transcript"

if printf '%s' "$payload" | \
  CLAUDE_PLUGIN_ROOT="$REPO_ROOT" \
  SUPERPOWERS_REVIEW_DRY_RUN=true \
  bash "$REPO_ROOT/hooks/run-hook.cmd" skill-review; then
  pass "run-hook.cmd dispatches an explicit-correction Stop event successfully"
else
  fail "run-hook.cmd dispatches an explicit-correction Stop event successfully"
fi

second_watermark="$(python3 - "$state_file" <<'PY'
import json
import sys

print(json.load(open(sys.argv[1], encoding="utf-8"))["tool_watermark"])
PY
)"
if grep -Fq "dry-run-explicit-correction" "$log_file" && [[ "$first_watermark" == "$second_watermark" ]]; then
  pass "explicit correction logs its fast path without resetting tool watermark"
else
  fail "explicit correction logs its fast path without resetting tool watermark"
fi

live_project="$TEST_ROOT/live-project"
live_transcript="$live_project/transcript.jsonl"
fake_bin="$TEST_ROOT/fake-bin"
mkdir -p "$live_project" "$fake_bin"
python3 - "$live_transcript" <<'PY'
import json
import sys
from pathlib import Path

transcript = Path(sys.argv[1])
records = []
for _ in range(10):
    records.append(
        {
            "type": "assistant",
            "message": {
                "content": [
                    {
                        "type": "tool_use",
                        "name": "Edit",
                        "input": {"file_path": "references/guide.md"},
                    }
                ]
            },
        }
    )
transcript.write_text("".join(json.dumps(record) + "\n" for record in records))
PY

cat > "$fake_bin/claude" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
exec python3 "$SUPERPOWERS_TEST_REPO_ROOT/skills/evolving-skills/scripts/new_observation.py" \
  --project-root "$SUPERPOWERS_PROJECT_ROOT" \
  --skill evolving-skills \
  --phase verification \
  --expected "Reusable evidence is recorded without changing global skills." \
  --actual "A background reviewer recorded a sanitized skill observation." \
  --evidence "A simulated Stop event crossed the configured threshold." \
  --diagnosis adapter \
  --scope local \
  --target reference \
  --provider openai \
  --model "${SUPERPOWERS_MODEL:-unknown}" \
  --harness "${SUPERPOWERS_HARNESS:-unknown}" \
  --interface desktop \
  --body "Sanitized evidence from the simulated reviewer."
EOF
chmod +x "$fake_bin/claude"

live_payload="$(python3 - "$live_project" "$live_transcript" <<'PY'
import json
import sys

print(json.dumps({"cwd": sys.argv[1], "transcript_path": sys.argv[2]}))
PY
)"

if printf '%s' "$live_payload" | \
  PATH="$fake_bin:$PATH" \
  SUPERPOWERS_TEST_REPO_ROOT="$REPO_ROOT" \
  CLAUDE_PLUGIN_ROOT="$REPO_ROOT" \
  SUPERPOWERS_REVIEW_DRY_RUN=false \
  bash "$REPO_ROOT/hooks/run-hook.cmd" skill-review; then
  pass "live reviewer seam invokes the existing observation writer"
else
  fail "live reviewer seam invokes the existing observation writer"
fi

observation="$(find "$live_project/.superpowers/observations/pending" -type f -name '*.md' -print -quit 2>/dev/null || true)"
if test -n "$observation" && \
  python3 "$REPO_ROOT/skills/evolving-skills/scripts/adapter_protocol.py" \
    validate-observation "$observation" >/dev/null; then
  pass "live reviewer seam leaves one valid pending observation"
else
  fail "live reviewer seam leaves one valid pending observation"
fi

if [[ "$FAILURES" -eq 0 ]]; then
  echo "All skill-review hook contract tests passed"
else
  echo "$FAILURES skill-review hook contract test(s) failed"
  exit 1
fi
