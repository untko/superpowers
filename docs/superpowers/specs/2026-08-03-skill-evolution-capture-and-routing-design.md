---
title: Skill Evolution — Automated Capture and Two-Tier Routing
date: 2026-08-03
status: superseded
superseded_by: https://github.com/untko/superpowers/issues/1
---

# Skill Evolution — Automated Capture and Two-Tier Routing

## Objective

Today, `superpowers-observation/v1` notes, the `pending/`→`proposed/`→`archived/`
lifecycle, and the human-approval-gated promotion step
(`evolving-skills`, mirrored by the vault's `vault-skill-upgrade`) already
exist and work. The one missing piece: **nothing writes to `pending/` unless
an agent remembers to call `new_observation.py` on its own.** This spec
automates that write, and then automates routing an accumulated observation
toward the right tier — without touching the approval gate, which stays
exactly as strict as it is today.

Two phases, both in scope (Phase 3 is not deferred):

- **Phase 2 — Capture.** Fire a background review after enough tool-loop work
  has happened, on a model that is never hardcoded, and write observations
  automatically. Corrections the user states directly, in normal
  conversation, bypass the threshold entirely.
- **Phase 3 — Routing.** Use the `candidate.scope` / `candidate.target`
  fields the schema already defines to draft — never commit — the right kind
  of change: a local adapter update, or a reference/script addition, gated by
  the same explicit approval `evolving-skills` already requires for anything
  global.

## Relationship to existing work

Extends [2026-07-29-local-adapter-evolution-protocol-design.md](2026-07-29-local-adapter-evolution-protocol-design.md)
and the `evolving-skills` skill. Does not modify the `superpowers-observation/v1`
schema (`skills/evolving-skills/references/local-adapter-protocol.md`) — every
field this design routes on (`observation.diagnosis`, `candidate.scope`,
`candidate.target`) already exists and is already populated by
`new_observation.py`. This is a producer for that pipeline's input, and a
first consumer of fields that currently sit unread once written.

Builds on the cross-harness hook pattern already shipped in `hooks/`
(`hooks.json` / `hooks-cursor.json` / `run-hook.cmd` / `docs/windows/polyglot-hooks.md`)
rather than inventing a new one.

## Invariants preserved (must not weaken)

1. Only an explicit global `evolving-skills` run generalizes, tests, approves,
   and releases a global skill change. Automated capture writes proposals,
   never approved changes.
2. `vault-skill-upgrade`'s gate — "present the candidate diff to the user and
   obtain explicit approval before any skill write" — is unchanged. Phase 3
   drafts candidates; it does not commit them.
3. No skill's `SKILL.md` grows past its word budget as a side effect of this
   work (`evolving-skills/SKILL.md` is at 495 of 500; `using-superpowers` is
   frozen at 598). New instructions belong in `references/`.
4. The background reviewer never edits `.agents/superpowers/` or
   `docs/superpowers/proposals/` directly — Phase 3 writers draft to a scratch
   location and stop; a human or an explicit approved run moves the draft
   into place.

## Phase 2 — Automated capture

### Trigger: Stop hook, not an in-process counter

Hermes counts tool-loop iterations in a long-lived agent process
(`agent._iters_since_skill`, confirmed cross-turn cumulative — never reset
except when a review fires). Claude Code's `Stop` hook has no equivalent
living process: it's a fresh invocation every time the assistant finishes a
turn. The counter has to be reconstructed from disk, not carried in memory.

**Mechanism:**

1. Add a `Stop` entry to `hooks/hooks.json` (and the Cursor variant) pointing
   at a new extensionless script `hooks/skill-review`, dispatched through the
   existing `run-hook.cmd`, exactly like `session-start` today.
2. The Stop hook payload includes `transcript_path`. `skill-review` reads it,
   counts tool-use blocks since a stored watermark, and compares against a
   threshold (default 10, matching Hermes).
3. The watermark persists in `.superpowers/review-state.json` (same
   directory as `observations/`, gitignored, repo-local) — this is what makes
   the count cross-turn cumulative despite the hook being stateless: the
   state lives on disk, not in the process.
4. When the threshold is crossed, fire the review and reset the watermark to
   the current transcript position — regardless of how many user turns that
   span covered. This directly answers the open question from this session:
   the count is **not per chat message** — a single turn with 12 tool calls
   fires it once; four quiet turns with two tool calls each never fires it
   until a fifth pushes the cumulative count over 10.

### Substance gate

Don't fire on a stretch with no tool calls touching `skills/`, `references/`,
`scripts/`, or containing a retried/corrected action. Pure Q&A tool-free
stretches never trip the counter at all (no iterations to count); a stretch
that does use tools but never touches skill-adjacent files or shows no
retry/correction pattern skips the review and just resets nothing — the
watermark stays put so that work still accrues toward the next check.

### Model selection: resolved, never hardcoded

No script hardcodes a model name. `skill-review` resolves a model the same
way `session-start` already resolves a harness (branching on
`CURSOR_PLUGIN_ROOT` / `CLAUDE_PLUGIN_ROOT` / `COPILOT_CLI` and friends), via
a small, appendable table rather than an inline if/else chain:

```
hooks/review-model-map.json
{
  "claude-code": "claude-haiku-4-5-20251001",
  "codex-cli": null,
  "_default": null
}
```

`null` means "inherit whatever model is running the session" — the safe
default for any harness not yet in the table, and the only behavior for a
harness with no independent background-model capability. A new harness adds
one line to this file; nothing in `skill-review` itself names a model.

### The explicit-correction fast path

The scenario the user raised — asking mid-session "what went wrong with
skill X" and then telling the agent to fix it — is a stronger signal than
anything the threshold-triggered background pass can infer, and shouldn't
wait for it. Any direct user correction about a skill's behavior ("stop doing
X", "that skill got Y wrong") is written to `pending/` immediately via
`new_observation.py`, in the same turn, independent of the counter. This
mirrors Hermes' explicit `/learn` path and its stated principle that user
corrections are first-class signals, not just memory fodder. The tool calls
involved still count toward the ordinary threshold — this path adds an
observation, it doesn't subtract the iterations from the counter.

### Visibility and tuning

Every hook firing — reviewed, skipped (no substance), or skipped (below
threshold) — appends one line to `.superpowers/review-log.md`: timestamp,
tool-call count since last watermark, model used, and outcome. This is the
instrument for the user's stated need to judge "too fast or too slow" and
adjust the threshold in `review-model-map.json`'s sibling config without
reading source. Ships with a dry-run mode (log the decision, skip the actual
`claude -p` call) for the first rollout.

## Phase 3 — Two-tier routing

The vocabulary already exists in the schema; nothing currently reads
`candidate.scope` or `candidate.target` after they're written. Phase 3 adds
the two readers.

| Field value | Action | Approval required? |
|---|---|---|
| `scope: local` | Draft/update this repo's `.agents/superpowers/<skill>/adapter.md` | Yes — present diff, same as today |
| `scope: potentially-global` | Leave in `proposed/`, awaiting an explicit `evolving-skills` run | Yes — unchanged, global gate |
| `target: reference \| script` | Draft a candidate file under the skill's (or adapter's) `references/`/`scripts/` | Yes — same diff-then-approve step |
| `target: skill` (new umbrella) | Not automated — always a full `evolving-skills` pass | Yes |

A "draft" writes to a scratch path (e.g. `.superpowers/drafts/`), never
directly into `.agents/superpowers/` or the skill tree. Promotion from draft
to real location is the existing human-approval step — this design adds a
proposal-drafter, not a writer with commit rights.

### Domains stay emergent, not nested directories

`~/.agents/skills/` is confirmed flat — one level deep
(`~/.agents/skills/<name>/SKILL.md`, no `<domain>/<name>/SKILL.md` found
anywhere) — so harnesses that glob skills one level deep would silently drop
anything nested. Domains are therefore name-prefix clusters (`obsidian-*`,
`python-*`), detected at consolidation time, not a schema field and not a
directory layer. `evolving-skills`' existing step 5 gains an optional,
explicitly-invoked consolidation sweep that proposes umbrella groupings by
prefix — **off by default**, mirroring Hermes' own `DEFAULT_CONSOLIDATE =
False` even at scale. The deterministic staleness/archive clock (separately
proposed, not built here) is the only thing that runs unattended.

## What does not change

- The observation schema, its storage classes, and its one-way rule.
- `vault-skill-upgrade` / `evolving-skills`'s approval gate — every write this
  design produces is a draft awaiting the same human sign-off that already
  exists.
- `SKILL.md` word budgets on the skills this touches.

## Open questions for the implementer

- Default threshold (10, from Hermes) may need retuning once
  `review-log.md` has real data — leave it a config value, not a constant.
- `review-model-map.json` ships with one entry (`claude-code`); Codex CLI's
  own background-model capability (if any) needs to be checked against
  current Codex docs before filling in that row, rather than guessed.
- Whether `.superpowers/drafts/` needs its own `.gitignore` entry alongside
  `observations/` (it does; verify the existing ignore pattern covers it or
  extend it).

## Testing

- Watermark/threshold logic is pure Python/bash — unit-testable without a
  live hook (construct a fake transcript, assert fire/no-fire at the
  boundary).
- Substance-gate classification: a microtest in
  `docs/superpowers/microtests/` style (see
  `docs/superpowers/microtests/track-split-microtest.sh` for the harness
  pattern and `claude-p-microtest-gotchas` for the `claude -p` pitfalls
  already paid for).
- Model-resolution table: static test — every harness key resolves to either
  a real model string or `null`, never an empty string or throw.
- Phase 3 drafters: unit tests asserting a draft never lands outside
  `.superpowers/drafts/` without an explicit promotion call, plus the
  existing path-safety test style in `test_adapter_protocol.py` (symlink
  escape, absolute path, `..` traversal all rejected).
