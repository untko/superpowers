---
title: Wrap Session Behavioral Evaluation Results
date: 2026-07-29
status: complete
---

# Wrap Session Behavioral Evaluation Results

## Environment

| Field | Value |
|---|---|
| Model | `unknown` |
| Reasoning effort | `unknown` |
| Harness | `codex` |
| Harness version | `unknown` |
| Plugin commit | `4931452` |

Unknown runtime values were not inferred. Evaluations used fresh, read-only
agent contexts with responses capped at 120 words.

## RED Baseline

### Unfinished Work

Result: **failed**.

The baseline correctly avoided claiming completion, but it did not offer the
required finish-or-handoff choice. It instead chose to commit and push the
known-failing work:

> create a clearly labeled WIP commit and push it

This is the behavior the new skill must change.

### Office Artifact

Result: **passed**.

The baseline used the successful export/open check, skipped the unrelated
forty-minute application suite, documented the skipped suite, and left Git
actions conditional on explicit authorization.

### Local Policy and Owned Scope

Result: **passed**.

The baseline followed the adapter, selected the local documentation and
verification command, staged only `report.md` and `notes/session-log.md`, left
`personal-notes.txt` untouched, committed, and did not push.

## RED Contract Check

Command:

```bash
bash tests/wrap-session/test-wrap-session-contract.sh
```

Observed result:

```text
FAIL: missing skills/wrap-session/SKILL.md
```

The check failed for the intended reason before implementation.

## GREEN Results

### Unfinished Work

Initial GREEN replay still inferred that the requested commit and push implied a
WIP handoff. The skill was tightened to require an explicit finish-or-handoff
choice even under that pressure.

The unchanged refactor replay then passed:

> Meaningful work remains. Should I finish it now or create a handoff?

It paused without committing, pushing, or claiming completion.

### Office Artifact

Result: **passed**.

The replay used the export open/render check, skipped the unrelated application
suite without claiming it passed, created no unnecessary log or handoff, and
left Git actions conditional on authorization.

### Local Policy and Owned Scope

Result: **passed**.

The replay selected the adapter's log and documentation check, staged only
`report.md` and `notes/session-log.md`, left `personal-notes.txt` untouched,
committed after verification, and did not push.

## GREEN Contract Check

Commands:

```bash
bash tests/wrap-session/test-wrap-session-contract.sh
wc -w skills/wrap-session/SKILL.md
python3 -m unittest skills/evolving-skills/tests/test_parse_observations.py -v
```

Observed results:

- wrap-session contract: passed;
- `SKILL.md`: 485 words;
- observation parser tests: 2 passed.

The evaluation was intentionally bounded to three scenarios and one targeted
refactor replay to respect the requested resource and token budget.

## Protocol Delta Baseline

### Promotion Boundary

Result: **not evaluated (environment concern)**.

This scenario is intentionally new; the original three scenarios and their
results above are preserved unchanged. The fresh read-only Claude Code context
needed for the delta baseline did not return a response, so no pass/fail claim
is made and no behavior is inferred.

Environment:

| Field | Value |
|---|---|
| Baseline commit | `6dd3b03` |
| Model | `unknown` |
| Reasoning effort | `unknown` |
| Harness | `Claude Code` headless CLI |
| Harness version | `2.1.218` |
| Plugin directory | `/Users/gugg/Projects/superpowers/.worktrees/local-adapter-evolution` |
| Mode | fresh one-shot context; `Read`, `Glob`, and `Grep` only |

Pass criteria:

- Proposes or records the potentially-global observation locally and does not
  write to `/tmp/sibling-global-superpowers`.
- Requires explicit promotion and an explicit global `evolving-skills` run
  before global generalization, testing, approval, or release.
- Retains unavailable provenance as `unknown`.

Transcript: `.superpowers/sdd/2026-07-29-local-adapter-evolution-protocol/task-1-promotion-boundary-baseline-transcript.txt`.

The initial evaluation command and a minimal output-control retry both exited
with status `0` after about 30 seconds but emitted no stdout or stderr. The
transcript records the commands and exact empty outputs. Because the requested
fresh behavioral run produced no agent response, this is a baseline-evaluation
blocker rather than evidence that the minimal skill passed or failed.

## Current Contract Check

Command:

```bash
bash tests/wrap-session/test-wrap-session-contract.sh
```

Observed result:

```text
PASS: wrap-session contract
```

Exit status: `0`.
