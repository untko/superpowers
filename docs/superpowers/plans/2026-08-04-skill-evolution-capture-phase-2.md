# Skill Evolution Phase 2 Capture Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a cross-harness `Stop` hook that cumulatively counts transcript tool-use blocks from a disk-persisted watermark, immediately routes explicit skill corrections to the reviewer, and records every decision without directly changing skills.

**Architecture:** Keep the extensionless `hooks/skill-review` script as a thin Bash entrypoint because `run-hook.cmd` dispatches hook scripts through Bash on every platform. Put parsing, state, threshold, substance-gate, model-table, logging, and reviewer-command logic in dependency-free `hooks/skill_review.py`, which is directly unit-testable. The hook reads the Stop payload from stdin, uses `cwd` as the repository root, persists only operational state under `.superpowers/`, and delegates any observation writing to a background `claude -p` reviewer instructed to use the existing `new_observation.py` contract.

**Tech Stack:** Bash, Python 3 standard library, JSONL transcript fixtures, `unittest`, existing `run-hook.cmd` dispatcher, and existing `new_observation.py` observation writer.

## Global Constraints

- The count is cumulative across turns and persists in `.superpowers/review-state.json`; it is not per-message and not an in-process counter.
- The review fires at `tool_calls_since_watermark >= threshold`; the shipped default is `10`, configured in `hooks/review-config.json`.
- The substance gate requires a skill-adjacent path (`skills/`, `references/`, or `scripts/`) or a retry/correction signal before threshold capture can run.
- Explicit user corrections about skill behavior trigger the reviewer immediately and do not reset the ordinary tool-call watermark unless the same event also satisfies the substantive threshold path.
- No model name is present in executable code; model selection comes from `hooks/review-model-map.json`, where `null` means inherit the running harness model.
- The first rollout is dry-run by default; dry-run logs the decision and skips `claude -p` while still advancing a threshold-fired watermark so the log does not repeat forever.
- The reviewer may write only observations through `skills/evolving-skills/scripts/new_observation.py`; it must not edit `.agents/superpowers/`, `skills/`, or `docs/superpowers/proposals/`.
- Preserve the existing human approval gate, the observation schema, the 500-word skill budgets, and all unrelated untracked files.
- Do not add third-party dependencies.

---

### Task 1: Build the pure transcript/state decision engine

**Files:**
- Create: `hooks/skill_review.py`
- Create: `tests/hooks/test_skill_review.py`

**Interfaces:**
- `load_review_config(path: Path) -> ReviewConfig`
- `load_model_map(path: Path) -> dict[str, str | None]`
- `resolve_harness(env: Mapping[str, str]) -> str`
- `resolve_model(model_map: Mapping[str, str | None], harness: str) -> str | None`
- `read_transcript_window(path: Path, tool_offset: int, correction_offset: int) -> TranscriptWindow`
- `decide_review(*, tool_calls: int, threshold: int, substantive: bool, explicit_correction: bool) -> ReviewDecision`
- `process_event(payload: Mapping[str, object], *, plugin_root: Path, env: Mapping[str, str], run_reviewer: Callable[..., int] | None = None, now: Callable[[], str] | None = None) -> ReviewResult`

**Produces:** A deterministic decision object and a safe state/log update that later hook integration tests can call without a live harness or model.

- [ ] **Step 1: Write failing tests for configuration and model resolution.**

```python
def test_model_map_resolves_known_harness_and_inherits_unknown(tmp_path):
    model_map = tmp_path / "review-model-map.json"
    model_map.write_text('{"claude-code": "review-model", "_default": null}\n')

    loaded = load_model_map(model_map)

    assert resolve_model(loaded, "claude-code") == "review-model"
    assert resolve_model(loaded, "codex-cli") is None

def test_model_map_rejects_empty_model_strings(tmp_path):
    path = tmp_path / "review-model-map.json"
    path.write_text('{"claude-code": "", "_default": null}\n')

    with pytest.raises(ValueError, match="non-empty string or null"):
        load_model_map(path)

def test_harness_detection_matches_session_start_branch_order():
    assert resolve_harness({"CURSOR_PLUGIN_ROOT": "/plugin", "CLAUDE_PLUGIN_ROOT": "/plugin"}) == "cursor"
    assert resolve_harness({"CLAUDE_PLUGIN_ROOT": "/plugin"}) == "claude-code"
    assert resolve_harness({"COPILOT_CLI": "1", "CLAUDE_PLUGIN_ROOT": "/plugin"}) == "copilot-cli"
    assert resolve_harness({}) == "_default"
```

- [ ] **Step 2: Run the focused tests to verify the expected RED failure.**

Run: `python3 -m pytest tests/hooks/test_skill_review.py -q`

Expected: collection fails because `hooks/skill_review.py` and its public functions do not exist yet.

- [ ] **Step 3: Add failing tests for JSONL parsing, cumulative counting, substance, and corrections.**

```python
def test_transcript_window_counts_tool_use_blocks_after_byte_watermarks(tmp_path):
    transcript = tmp_path / "transcript.jsonl"
    transcript.write_text(
        '{"type":"assistant","message":{"content":[{"type":"tool_use","name":"Read","input":{"file_path":"skills/demo/SKILL.md"}}]}}\n'
        '{"type":"assistant","message":{"content":[{"type":"tool_use","name":"Bash","input":{"command":"pytest"}},{"type":"tool_use","name":"Edit","input":{"file_path":"references/guide.md"}}]}}\n'
    )

    window = read_transcript_window(transcript, tool_offset=0, correction_offset=0)

    assert window.tool_calls == 3
    assert window.substantive is True
    assert window.end_offset == transcript.stat().st_size

def test_transcript_window_detects_user_skill_correction_without_tool_threshold(tmp_path):
    transcript = tmp_path / "transcript.jsonl"
    transcript.write_text(
        '{"type":"user","message":{"content":"That skill got this wrong. Fix it."}}\n'
    )

    window = read_transcript_window(transcript, tool_offset=0, correction_offset=0)

    assert window.tool_calls == 0
    assert window.explicit_corrections == ("That skill got this wrong. Fix it.",)

def test_threshold_fires_at_exact_boundary_only_when_substantive():
    assert decide_review(tool_calls=10, threshold=10, substantive=True, explicit_correction=False).outcome == "review"
    assert decide_review(tool_calls=10, threshold=10, substantive=False, explicit_correction=False).outcome == "skip-no-substance"
    assert decide_review(tool_calls=2, threshold=10, substantive=False, explicit_correction=False).outcome == "skip-below-threshold"

def test_explicit_correction_bypasses_threshold_without_resetting_tool_watermark():
    decision = decide_review(tool_calls=2, threshold=10, substantive=False, explicit_correction=True)

    assert decision.outcome == "review-explicit-correction"
    assert decision.reset_tool_watermark is False
```

- [ ] **Step 4: Run the new tests and confirm they fail for missing behavior, not fixture errors.**

Run: `python3 -m pytest tests/hooks/test_skill_review.py -q`

Expected: the new tests fail with missing module/function errors, while the fixture JSONL remains valid input.

- [ ] **Step 5: Implement the minimal dependency-free engine.**

Implement `ReviewConfig` and `ReviewDecision` dataclasses; strict JSON config validation; harness detection using the same `CURSOR_PLUGIN_ROOT` / `CLAUDE_PLUGIN_ROOT` / `COPILOT_CLI` precedence as `hooks/session-start`; recursive `type: tool_use` discovery; complete-line byte offsets; path/retry/correction substance classification; and explicit-correction extraction from user-role text. Treat a missing state file as zero offsets, reject malformed state/config rather than following unsafe paths, and keep the ordinary tool watermark unchanged for explicit-only or no-substance decisions.

- [ ] **Step 6: Run the focused tests GREEN.**

Run: `python3 -m pytest tests/hooks/test_skill_review.py -q`

Expected: all configuration, parsing, boundary, and decision tests pass.

- [ ] **Step 7: Refactor only after GREEN and rerun the focused tests.**

Keep file I/O, classification, and decision logic in separate small functions; do not add behavior beyond the tests. Rerun `python3 -m pytest tests/hooks/test_skill_review.py -q` and require zero failures.

### Task 2: Add persisted state, review logging, and reviewer execution

**Files:**
- Modify: `hooks/skill_review.py`
- Modify: `tests/hooks/test_skill_review.py`

**Interfaces:**
- State file: `<project>/.superpowers/review-state.json` with `transcript_path`, `tool_watermark`, and `correction_watermark`.
- Log file: `<project>/.superpowers/review-log.md`, one Markdown line per invocation with timestamp, tool count, model, and outcome.
- Reviewer runner: receives the sanitized excerpt, project root, harness, model, and existing `new_observation.py` path; adds `--model` only when the resolved map value is non-null.

- [ ] **Step 1: Write failing tests for cumulative state and log outcomes.**

```python
def test_below_threshold_keeps_tool_watermark_so_counts_accumulate(tmp_path):
    payload = make_stop_payload(tmp_path, tool_use_records=2)
    first = process_event(payload, plugin_root=PLUGIN_ROOT, env={"SUPERPOWERS_REVIEW_THRESHOLD": "10"}, now=fixed_time)
    append_tool_use_records(payload["transcript_path"], 2)
    second = process_event(payload, plugin_root=PLUGIN_ROOT, env={"SUPERPOWERS_REVIEW_THRESHOLD": "10"}, now=fixed_time)

    assert first.outcome == "skip-below-threshold"
    assert second.tool_calls == 4
    assert not (tmp_path / ".superpowers" / "review-state.json").exists()

def test_threshold_review_resets_watermark_to_current_transcript_position(tmp_path):
    payload = make_stop_payload(tmp_path, tool_use_records=10, substantive=True)
    result = process_event(payload, plugin_root=PLUGIN_ROOT, env={"SUPERPOWERS_REVIEW_DRY_RUN": "true"}, now=fixed_time)

    state = json.loads((tmp_path / ".superpowers" / "review-state.json").read_text())
    assert result.outcome == "dry-run-review"
    assert state["tool_watermark"] == Path(payload["transcript_path"]).stat().st_size

def test_no_substance_keeps_tool_watermark_but_advances_correction_watermark(tmp_path):
    payload = make_stop_payload(tmp_path, tool_use_records=10, substantive=False)
    result = process_event(payload, plugin_root=PLUGIN_ROOT, env={}, now=fixed_time)

    state = json.loads((tmp_path / ".superpowers" / "review-state.json").read_text())
    assert result.outcome == "skip-no-substance"
    assert state["tool_watermark"] == 0
    assert state["correction_watermark"] == Path(payload["transcript_path"]).stat().st_size

def test_every_invocation_appends_timestamp_count_model_and_outcome(tmp_path):
    payload = make_stop_payload(tmp_path, tool_use_records=1)
    process_event(payload, plugin_root=PLUGIN_ROOT, env={}, now=lambda: "2026-08-04T00:00:00Z")

    line = (tmp_path / ".superpowers" / "review-log.md").read_text().strip()
    assert "2026-08-04T00:00:00Z" in line
    assert "tool_calls=1" in line
    assert "model=inherit" in line
    assert "outcome=skip-below-threshold" in line
```

- [ ] **Step 2: Run the tests to verify RED.**

Run: `python3 -m pytest tests/hooks/test_skill_review.py -q`

Expected: state/log assertions fail because event processing and persistence are not implemented.

- [ ] **Step 3: Implement safe state and log persistence.**

Create `.superpowers/` only beneath the resolved `cwd`, reject a symlinked `.superpowers`, write JSON state atomically via a sibling temporary file and `replace`, and append one bounded single-line log entry. If a transcript path changes or the file shrinks below a stored offset, restart both offsets at zero for the new transcript.

- [ ] **Step 4: Implement review prompt construction and dry-run/live command execution.**

The prompt must identify the repository, the existing writer path, the reason (`threshold` or `explicit correction`), and the sanitized current-window excerpt. It must instruct the reviewer to write at most one valid `superpowers-observation/v1` note via `new_observation.py`, preserve `scope`/`target`, omit secrets/raw transcripts, and make no other file changes. In dry-run mode, log `dry-run-review` or `dry-run-explicit-correction` and skip the subprocess. In live mode, run `claude -p <prompt>` in the project root, pass `--model <configured-model>` only when the model table resolves a string, and log failure without blocking the host harness.

- [ ] **Step 5: Add tests for explicit-correction state and command argv.**

```python
def test_explicit_correction_runs_reviewer_and_preserves_tool_counter(tmp_path):
    payload = make_stop_payload(tmp_path, tool_use_records=2, user_text="Stop doing that; this skill is wrong.")
    calls = []

    def fake_reviewer(**kwargs):
        calls.append(kwargs)
        return 0

    result = process_event(payload, plugin_root=PLUGIN_ROOT, env={"SUPERPOWERS_REVIEW_DRY_RUN": "false"}, run_reviewer=fake_reviewer, now=fixed_time)

    state = json.loads((tmp_path / ".superpowers" / "review-state.json").read_text())
    assert result.outcome == "review-explicit-correction"
    assert state["tool_watermark"] == 0
    assert calls[0]["reason"] == "explicit-correction"
    assert "new_observation.py" in calls[0]["prompt"]

def test_live_review_passes_model_only_for_non_null_table_entry(tmp_path):
    payload = make_stop_payload(tmp_path, tool_use_records=10, substantive=True)
    calls = []

    def fake_reviewer(**kwargs):
        calls.append(kwargs)
        return 0

    test_plugin_root = make_plugin_fixture(tmp_path, model_map={"claude-code": "review-model-from-config", "_default": None})
    process_event(payload, plugin_root=test_plugin_root, env={"CLAUDE_PLUGIN_ROOT": str(test_plugin_root), "SUPERPOWERS_REVIEW_DRY_RUN": "false"}, run_reviewer=fake_reviewer, now=fixed_time)

    assert calls[0]["model"] == "review-model-from-config"
```

- [ ] **Step 6: Run the full hook unit test file GREEN.**

Run: `python3 -m pytest tests/hooks/test_skill_review.py -q`

Expected: all state, log, prompt, and model-argument tests pass with no live model invocation.

### Task 3: Wire the extensionless Stop hook and shipped configuration

**Files:**
- Create: `hooks/skill-review`
- Create: `hooks/review-config.json`
- Create: `hooks/review-model-map.json`
- Modify: `hooks/hooks.json`
- Modify: `hooks/hooks-cursor.json`
- Create: `tests/hooks/test-skill-review.sh`

**Interfaces:**
- `hooks/skill-review` reads the Stop JSON payload from stdin and executes `python3 hooks/skill_review.py --plugin-root <plugin-root>`.
- `SUPERPOWERS_REVIEW_THRESHOLD` and `SUPERPOWERS_REVIEW_DRY_RUN` are test/rollout overrides; absent overrides defer to `hooks/review-config.json`.
- Claude Code registration uses an asynchronous Bash command through `run-hook.cmd`; Cursor registration uses its existing lowercase `stop` hook shape.
- Shipped config is `{ "threshold": 10, "dry_run": true }`.
- Shipped model map contains the configured `claude-code` entry and `_default: null`; no guessed Codex CLI model is added.

- [ ] **Step 1: Write the failing shell contract test.**

```bash
node -e '
const hooks = JSON.parse(require("fs").readFileSync(process.argv[1], "utf8"));
const stop = hooks.hooks.Stop[0].hooks[0];
if (stop.async !== true || stop.shell !== "bash" || !stop.command.endsWith(" skill-review")) process.exit(1);
' hooks/hooks.json

node -e '
const hooks = JSON.parse(require("fs").readFileSync(process.argv[1], "utf8"));
if (!hooks.hooks.stop || hooks.hooks.stop[0].command !== "./hooks/run-hook.cmd skill-review") process.exit(1);
' hooks/hooks-cursor.json

test -x hooks/skill-review
python3 -m json.tool hooks/review-config.json >/dev/null
python3 -m json.tool hooks/review-model-map.json >/dev/null
```

- [ ] **Step 2: Run the shell test to verify RED.**

Run: `bash tests/hooks/test-skill-review.sh`

Expected: it fails because the Stop registrations, configs, and wrapper do not exist.

- [ ] **Step 3: Add the executable wrapper and JSON configs.**

The wrapper must resolve its own directory, derive the plugin root, and `exec python3` the Python engine while forwarding stdin unchanged. Keep model strings exclusively in `review-model-map.json`.

- [ ] **Step 4: Add Stop registrations without changing SessionStart behavior.**

Append a `Stop` entry to `hooks/hooks.json` with `shell: "bash"`, `async: true`, and command `"${CLAUDE_PLUGIN_ROOT}/hooks/run-hook.cmd" skill-review`; append lowercase `stop` to the Cursor variant with `./hooks/run-hook.cmd skill-review`.

- [ ] **Step 5: Extend the shell test to simulate a Stop event through `run-hook.cmd`.**

Use a temporary project and JSONL transcript containing ten skill-adjacent tool-use blocks. Set `SUPERPOWERS_REVIEW_DRY_RUN=true` and assert that the wrapper exits zero, creates `.superpowers/review-state.json`, appends `tool_calls=10` and `dry-run-review` to `review-log.md`, and does not create an observation. Add a second invocation with a user correction and assert the log records the explicit path while the ordinary tool watermark remains unchanged.

- [ ] **Step 6: Run the shell contract and wrapper simulation tests GREEN.**

Run: `bash tests/hooks/test-skill-review.sh`

Expected: all registration, config, executable, state, logging, and dry-run simulation assertions pass.

### Task 4: Verify Phase 2 end-to-end and document the operational contract

**Files:**
- Modify: `tests/hooks/test-skill-review.sh`
- Modify: `docs/superpowers/plans/2026-08-04-skill-evolution-capture-phase-2.md`

**Interfaces:**
- The simulated reviewer executable writes one valid observation via the existing `new_observation.py`, proving the live command seam without contacting a model service.
- Existing hook and evolving-skills tests remain the regression suite.

- [ ] **Step 1: Add an isolated fake reviewer to the shell test.**

Place a temporary `claude` executable first on `PATH`; have it invoke the repository’s existing `new_observation.py` with `SUPERPOWERS_PROJECT_ROOT`, a sanitized fixed skill observation, and the runtime environment passed by the hook. Run the hook with `SUPERPOWERS_REVIEW_DRY_RUN=false`, then assert the observation appears under `<project>/.superpowers/observations/pending/` and validates with `adapter_protocol.py validate-observation`.

- [ ] **Step 2: Run the focused red-green and integration checks.**

Run:

```bash
python3 -m pytest tests/hooks/test_skill_review.py -q
bash tests/hooks/test-skill-review.sh
bash tests/hooks/test-session-start.sh
python3 -m pytest skills/evolving-skills/tests -q
git diff --check
```

Expected: every command exits `0`; the fake-reviewer integration reports one valid pending observation and the existing SessionStart/evolving-skills suites remain green.

- [ ] **Step 3: Run shell syntax/lint checks on the new and modified hook scripts.**

Run: `bash scripts/lint-shell.sh hooks/skill-review hooks/run-hook.cmd tests/hooks/test-skill-review.sh`

Expected: Bash syntax and ShellCheck pass, or if ShellCheck is unavailable, record that exact environment limitation rather than claiming lint success.

- [ ] **Step 4: Re-read the spec and verify the Phase 2 checklist.**

Confirm: disk watermark is cross-turn cumulative; no-substance skips do not reset it; explicit corrections bypass threshold; model selection is table-driven with `null` inheritance; every invocation logs timestamp/count/model/outcome; dry-run is shipped; existing approval gates and skill budgets are untouched; no Phase 3 routing is included.

- [ ] **Step 5: Present the complete diff and verification evidence to the human partner.**

Do not push, open a PR, or modify the unrelated untracked files. A later commit/branch disposition requires explicit human review of the complete diff, per this repository’s contributor guidelines.
