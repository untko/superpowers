---
title: Implement Phase 2/3 skill-evolution capture loop and routing
description: Turn the design at docs/superpowers/specs/2026-08-03-skill-evolution-capture-and-routing-design.md into an implementation plan and code — a Stop-hook capture loop plus draft-only routing on top of the existing observation pipeline.
status: open
created: 2026-08-03T23:37:00+07:00
updated: 2026-08-03T23:37:00+07:00
author: claude-sonnet-5
harness: claude-code
---

# Objective

Automate the one manual step in an otherwise-complete pipeline: writing to
`.superpowers/observations/pending/`. Everything downstream of that write
(`evolving-skills`, the vault's `vault-skill-upgrade`) already exists and is
already human-approval-gated. Nothing here changes that gate.

**Scope: this repository (`superpowers`) only.** No cross-repository edits —
the Obsidian vault at `/Users/gugg/Documents/Obsidian/ObsidianVault-main` has
its own copy of this pipeline and its own handoffs; do not touch it from
here.

# Why now

This came out of a long design conversation (this session, `claude-code`,
2026-08-03) adapting the OSS `hermes-agent` project's proactive
skill-maintenance loop into this fork. Three constraints came directly from
the user and must not be relaxed by an implementer optimizing for
convenience:

1. **Do not hardcode a review model.** This plugin runs across multiple
   harnesses (Claude Code, Codex CLI, Cursor, Copilot CLI — see
   `hooks/session-start`'s existing branch-per-harness pattern) with
   different available/default models. Model choice must resolve from a
   small config table, not a literal string in the hook script.
2. **Small, mechanical changes may be autonomous** (updating a reference file,
   a helper script); **major changes need the user in the loop**. This maps
   onto the existing `scope`/`target` fields in the observation schema —
   Phase 3 drafts candidates, never commits them.
3. **A user-initiated correction ("that skill did X wrong, fix it") is a
   stronger signal than a threshold** and must bypass it, writing an
   observation immediately rather than waiting for the tool-iteration count
   to cross the default-10 threshold.

Full design, with the Hermes source citations and cost analysis behind these
choices, is in the spec below — read it before writing any code.

# Current state

**Nothing has been implemented.** This handoff and its spec are the entire
deliverable of the design conversation. No hook has been added, no script
written, no test exists yet for any of this. `git status` on this repo is
clean of any related changes (only pre-existing untracked `__pycache__`
directories and unrelated plugin-installed content — see Environment below).

What already exists and this work builds on top of, unmodified:

- `superpowers-observation/v1` schema and its enums
  (`skills/evolving-skills/references/local-adapter-protocol.md`)
- `skills/evolving-skills/scripts/new_observation.py` — already accepts every
  field this design needs (`--diagnosis`, `--scope`, `--target`,
  `--provider`, `--model`, `--harness`, etc. — run `--help` to see the full
  flag list, already verified during this session)
- `skills/evolving-skills/scripts/parse_observations.py` — harvest/list/tidy/
  archive, unchanged
- `evolving-skills/SKILL.md` — the human-approval-gated promotion workflow,
  unchanged
- `hooks/hooks.json`, `hooks/hooks-cursor.json`, `hooks/run-hook.cmd`,
  `hooks/session-start` — the existing cross-platform hook dispatcher
  pattern and its per-harness branching (`CURSOR_PLUGIN_ROOT` /
  `CLAUDE_PLUGIN_ROOT` / `COPILOT_CLI`), which the new `Stop` hook should
  copy rather than reinvent

# Next action

1. Read the design spec in full:
   `docs/superpowers/specs/2026-08-03-skill-evolution-capture-and-routing-design.md`
2. Use `superpowers:writing-plans` to turn it into a task-by-task
   implementation plan under `docs/superpowers/plans/`. Phase 2 (capture) and
   Phase 3 (routing) are independent enough to be separate plans/PRs — the
   spec's own sectioning follows that split.
3. Execute Phase 2 first (capture has no dependents; Phase 3's routers have
   nothing to route on until observations accumulate). Use
   `superpowers:test-driven-development` for the watermark/threshold logic —
   it's pure Python/bash and fully unit-testable without a live hook.
4. Before opening any PR against this repo (even though it's this user's own
   fork), re-read the root `CLAUDE.md` — it still applies to this fork's own
   contribution hygiene even though the upstream-specific rejection-rate
   framing doesn't.

# Remaining work

Everything in the spec's "Phase 2" and "Phase 3" sections. Concretely, not
yet built:

- `hooks/skill-review` (new extensionless script, `Stop` hook)
- `Stop` entries in `hooks/hooks.json` and `hooks/hooks-cursor.json`
- `.superpowers/review-state.json` (watermark) and
  `.superpowers/review-log.md` (visibility/tuning log) — both need
  `.gitignore` coverage, verify the existing pattern for `observations/`
  extends to these or add it
- `hooks/review-model-map.json` (per-harness model resolution table; ships
  with one real entry, `claude-code`; Codex CLI's row needs an actual
  capability check, not a guess — see Open Questions in the spec)
- The explicit-correction fast path — likely a short addition to
  `evolving-skills/SKILL.md` or `using-superpowers/SKILL.md` describing when
  to call `new_observation.py` inline rather than waiting on the hook. Any
  edit to `using-superpowers/SKILL.md` specifically **must be measured**, per
  `[[skill-edit-eval-policy]]` — that file already caused one measured
  regression this fork reverted (see `bd4ad9e`). This is the highest-risk
  single file in the whole plan; treat it accordingly.
- Phase 3 drafters (scope/target routers) writing to `.superpowers/drafts/`
  only, never to `.agents/superpowers/` or the skill tree directly
- Dry-run mode for first rollout of the hook

# Decisions and constraints

- **Model resolution table, not hardcoded model.** This was an explicit user
  correction during design — do not reintroduce a literal `"haiku"` string
  anywhere in the hook path.
- **Watermark on disk, not in-process.** Claude Code's `Stop` hook is a fresh
  process per firing; there is no live counter to increment like Hermes'
  `agent._iters_since_skill`. The cumulative-across-turns behavior (verified
  from Hermes source: the counter is never reset except when a review fires)
  is reproduced via a persisted watermark file, not an in-memory variable.
- **The threshold is not per chat message.** A single turn with 12 tool
  calls fires the review once; several quiet turns with two tool calls each
  don't fire until the cumulative count crosses the threshold. This directly
  answers a question the user asked mid-design; don't redesign it as
  per-turn.
- **Approval gate is untouched.** Every write Phase 2/3 produces is either an
  observation (`pending/`) or a draft (`.superpowers/drafts/`) — never a
  committed skill/adapter/reference change. `vault-skill-upgrade`'s own
  wording — "present the candidate diff to the user and obtain explicit
  approval before any skill write" — is the bar; do not weaken it for
  convenience.
- **Domains are name-prefixes, not directories.** `~/.agents/skills/` was
  confirmed flat (one level deep) during design; do not introduce nested
  `<domain>/<skill>/SKILL.md` paths — harnesses glob one level deep and would
  silently drop nested entries.
- **Consolidation stays off by default**, mirroring Hermes'
  `DEFAULT_CONSOLIDATE = False` — even with a large corpus of captured
  observations, the umbrella-clustering pass is explicitly invoked, never
  automatic.
- **This is a fork.** `origin` is `untko/superpowers`
  (`https://github.com/untko/superpowers.git`); `upstream` is
  `obra/superpowers` with push disabled. Push to `origin`; no upstream PRs
  unless the user says otherwise.
- **`SKILL.md` word budgets are frozen anchors** —
  `evolving-skills/SKILL.md` is at 495/500 words; `using-superpowers` is
  frozen at 598. Any new prose goes in `references/`, not the top-level file.

# Environment

- Project root: `/Users/gugg/Projects/superpowers`
- Branch `main` at `cb09220`, in sync with `origin/main`
- Untracked at handoff time (pre-existing, unrelated to this work — do not
  clean up as part of this task without checking with the user first):
  `domain/content-creation/mermaid-graph` and `skills/mermaid-graph/`
  (installed-plugin scaffolding, not agent-created), plus stray
  `__pycache__` directories under `skills/evolving-skills/`
- Platform: darwin. `python3` and `pytest` available.
- `origin` push-enabled; `upstream` push-disabled (read-only mirror)

# References

- `docs/superpowers/specs/2026-08-03-skill-evolution-capture-and-routing-design.md`
  — the full design this handoff executes
- `docs/superpowers/specs/2026-07-29-local-adapter-evolution-protocol-design.md`
  — the design this one extends; read it first if the schema/lifecycle isn't
  already familiar
- `skills/evolving-skills/references/local-adapter-protocol.md` — the
  contract (schema fields, enums, storage classes)
- `skills/evolving-skills/scripts/new_observation.py`,
  `parse_observations.py`, `adapter_protocol.py` — existing, unmodified
  building blocks
- `hooks/session-start`, `hooks/run-hook.cmd`, `hooks/hooks.json`,
  `hooks/hooks-cursor.json`, `docs/windows/polyglot-hooks.md` — the hook
  dispatcher pattern the new `Stop` hook must follow
- `.agents/handoffs/archive/2026-08-01-1619-observation-schema-optional-fields.md`
  — the most recent prior handoff in this repo; good example of the format
  and of how much verification evidence to include when this one is closed out

# Suggested skills

- `superpowers:brainstorming` — the design above already went through this;
  do not re-run it unless requirements have changed since 2026-08-03
- `superpowers:writing-plans` — turn the spec into a task-by-task plan before
  writing code
- `superpowers:test-driven-development` — watermark/threshold logic and the
  model-resolution table are both small and fully unit-testable; write the
  tests first
- `superpowers:evolving-skills` — owns the pipeline this plugs into; read it
  before changing anything under `skills/evolving-skills/`
- `superpowers:verification-before-completion` — before closing this
  handoff, actually fire the hook (or simulate a Stop event) and read the
  resulting observation file, don't just claim the code compiles
