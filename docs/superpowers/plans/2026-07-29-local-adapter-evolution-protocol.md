---
title: Local Adapter and Skill Evolution Protocol Implementation Plan
date: 2026-07-29
status: approved
design: docs/superpowers/specs/2026-07-29-local-adapter-evolution-protocol-design.md
---

# Local Adapter and Skill Evolution Protocol Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the existing `wrap-session` skill with validated local
adapters and a safe repository-local observation-to-global-proposal protocol.

**Architecture:** A standard-library Python protocol module parses constrained
YAML frontmatter, validates adapters and observations, and enforces adapter
resource boundaries. `wrap-session`, `using-superpowers`, and
`evolving-skills` describe portable actions and explicit promotion authority;
repository-local policy remains ordinary files rather than duplicate skills.

**Tech Stack:** Markdown, Python 3 standard library, `unittest`, POSIX shell,
existing Claude Code behavior harness.

## Global Constraints

- Build on commit `6dd3b03`; preserve its unfinished-work gate and
  proportional verification behavior.
- Do not push, open a pull request, or write to `obra/superpowers`.
- Add no third-party dependency.
- The global skill is the only discoverable workflow; adapters contain no
  `SKILL.md`.
- Missing adapters select defaults; invalid adapters are reported and never
  guessed.
- Raw evidence stays under `.superpowers/observations/`; reviewed proposals
  live under `docs/superpowers/proposals/`.
- Unknown provenance is `unknown`, never inferred.
- No ordinary skill run writes across repository boundaries.
- Local policy cannot weaken owned-scope, verification, commit, push, or
  cross-repository approval gates.
- Commits require the approved plan; pushes require separate authorization.
- Preserve unrelated untracked files in the primary worktree.

---

### Task 1: Recover the Approved Protocol and Establish the Delta Baseline

**Files:**
- Create: `docs/superpowers/specs/2026-07-29-local-adapter-evolution-protocol-design.md`
- Create: `docs/superpowers/plans/2026-07-29-local-adapter-evolution-protocol.md`
- Modify: `tests/wrap-session/eval-scenarios.md`
- Modify: `docs/superpowers/specs/2026-07-29-wrap-session-eval-results.md`

**Interfaces:**
- Consumes: existing scenarios/results at `6dd3b03`.
- Produces: preserved original scenarios plus `promotion-boundary`, with a
  baseline result against the minimal current skill.

- [ ] Preserve the existing unfinished-work, office-artifact, and
  local-policy/owned-scope scenarios unchanged.
- [ ] Add `promotion-boundary`: a valid potentially-global observation exists
  locally and a sibling global repository exists; the agent must propose
  locally, avoid the sibling write, require explicit promotion, and leave
  unavailable provenance as `unknown`.
- [ ] Run the new prompt in a fresh read-only agent context against `6dd3b03`;
  append actual environment, pass/fail criteria, and the transcript path to the
  existing eval-results document. Do not rewrite the earlier evidence.
- [ ] Run `bash tests/wrap-session/test-wrap-session-contract.sh` and record
  its current result.
- [ ] Commit only the four paths above with
  `docs: define local adapter evolution protocol`.

### Task 2: Implement the Adapter and Observation Protocol

**Files:**
- Create: `skills/evolving-skills/scripts/adapter_protocol.py`
- Create: `skills/evolving-skills/tests/test_adapter_protocol.py`

**Interfaces:**
- Produces:
  - `parse_frontmatter(content: str) -> tuple[dict[str, object], str]`
  - `discover_adapter(project_root: Path, skill_name: str, supported_contracts: set[int]) -> dict[str, object]`
  - `resolve_adapter_resource(adapter_path: Path, relative_path: str) -> Path`
  - `validate_observation(metadata: dict[str, object]) -> list[str]`
  - CLI `discover` and `validate-observation`, JSON output, exit `0` for valid
    or absent and `2` for invalid.

- [ ] Write failing `unittest` cases for absent/valid adapter, wrong schema,
  wrong `extends`, unsupported contract, missing frontmatter, nested mappings,
  quoted scalars, malformed indentation, absolute resource paths, `..`
  traversal, and symlink escape.
- [ ] Run
  `python3 -m unittest skills/evolving-skills/tests/test_adapter_protocol.py -v`
  and preserve the expected RED output in the task report.
- [ ] Implement a dependency-free constrained YAML mapping parser: mappings,
  two-space indentation, strings, integers, booleans, and null; reject lists,
  tabs, duplicate keys, and indentation jumps.
- [ ] Discover exactly
  `.agents/superpowers/{skill-name}/adapter.md`; validate
  `superpowers-adapter/v1`, exact `extends`, and supported contract.
- [ ] Enforce resolved containment inside the adapter directory, including
  symlinks.
- [ ] Validate all required nested runtime, skill, observation, and candidate
  fields from the approved design. Return all errors. Enforce the documented
  diagnosis, scope, and target enums while accepting `unknown`.
- [ ] Run the unit test file GREEN with pristine output.
- [ ] Commit the two paths with
  `feat: add repository-local adapter protocol`.

### Task 3: Store Observations in the Active Repository

**Files:**
- Modify: `skills/evolving-skills/scripts/parse_observations.py`
- Modify: `skills/evolving-skills/tests/test_parse_observations.py`

**Interfaces:**
- Consumes: `adapter_protocol.parse_frontmatter` and
  `adapter_protocol.validate_observation`.
- Produces:
  - `observation_root(project_root: Path) -> Path`
  - `ensure_observation_store(project_root: Path) -> dict[str, Path]`
  - preserved `list_observations` and `archive_observation` compatibility
  - CLI `--project-root`, `--obs-dir`, `--init`, `--list`, `--archive`.

- [ ] Preserve the two existing legacy tests, then add RED tests proving the
  default root is `.superpowers/observations`, store creation makes
  `pending/`, `proposed/`, `archived/`, and a self-ignoring `.gitignore`
  containing `*`.
- [ ] Add tests that list v1 observations only from `pending/`, expose nested
  provenance, move pending notes to `archived/`, reject overwrites and sources
  outside pending, and preserve explicit legacy `--obs-dir` behavior.
- [ ] Run the test file and capture expected RED.
- [ ] Refactor paths to `pathlib.Path`. Default `--project-root` to the current
  directory and never to a directory inside the installed skill.
- [ ] Preserve legacy flat-frontmatter output when `--obs-dir` is explicit;
  validate and expose nested v1 metadata for the repository-local store.
- [ ] Require archival sources to resolve inside `pending/`; fail when the
  destination exists.
- [ ] Run all evolving-skills unit tests GREEN.
- [ ] Commit parser and tests with
  `feat: store skill observations in local repositories`.

### Task 4: Integrate the Bidirectional Information Protocol

**Files:**
- Create: `skills/evolving-skills/references/local-adapter-protocol.md`
- Modify: `skills/evolving-skills/SKILL.md`
- Modify: `skills/using-superpowers/SKILL.md`

**Interfaces:**
- Consumes: Task 2 and Task 3 CLIs.
- Produces: canonical schemas and one-way promotion authority in skill prose.

- [ ] Write the reference with storage classes, adapter contract, path safety,
  full observation example and enums, lifecycle, durable proposal fields,
  failure handling, and global-to-local adoption.
- [ ] Keep `evolving-skills/SKILL.md` below 500 words. Change harvesting to
  `python3 scripts/parse_observations.py --project-root "$PROJECT_ROOT" --list`;
  retain abstraction, verification, audit, and approval gates.
- [ ] State that local repositories observe/propose while only an explicit
  global evolution run generalizes/tests/releases; neither direction
  auto-writes another repository.
- [ ] Update `using-superpowers` so significant reusable friction is minimally
  sanitized into `.superpowers/observations/pending/` with reported model and
  harness provenance, using `unknown` when unavailable. Ordinary runs neither
  edit global skills nor scan history.
- [ ] Run evolving-skills unit tests, the 500-word assertion, and `rg` checks
  proving the installed-skill observation directory is no longer the default.
- [ ] Commit the three paths with
  `docs: define bidirectional skill evolution protocol`.

### Task 5: Upgrade `wrap-session` as the First Consumer

**Files:**
- Modify: `skills/wrap-session/SKILL.md`
- Move: `skills/wrap-session/closeout-artifacts.md` to `skills/wrap-session/references/closeout-artifacts.md`
- Modify: `tests/wrap-session/test-wrap-session-contract.sh`
- Create: `tests/explicit-skill-requests/prompts/wrap-session.txt`
- Modify: `README.md`

**Interfaces:**
- Consumes: adapter contract `1`, observation protocol,
  `verification-before-completion`, and
  `finishing-a-development-branch`.
- Produces: completion receipt with owned scope, adapter status, durable
  artifacts, verification, Git state, remaining work, and observation paths.

- [ ] Extend the shell contract test first. Require schema/contract validation,
  the exact adapter path, the new reference path, local pending observations,
  both delegated skill names, separate push authorization, receipt fields, and
  a word count below 500. Preserve all existing assertions and banned
  repository-specific path checks.
- [ ] Run the shell test and capture expected RED.
- [ ] Relocate the reference and preserve useful existing guidance. Add a
  trigger/default decision table for living docs, decision records,
  observations, unfinished tasks/handoffs, verification evidence, and
  temporary plan/spec disposition.
- [ ] Extend the skill without losing the existing unfinished-work choice or
  proportional verification. Validate adapter metadata, read only required
  adapter resources, preserve owned scope, record significant friction locally,
  delegate evidence claims and completed branch disposition, and maintain
  separate commit/push gates.
- [ ] Add red flags for staging the worktree, inventing provenance, hard-coded
  paths, silently ignoring invalid adapters, cross-repository edits, and
  treating proposals as authorization.
- [ ] Add the explicit-request prompt and update README language so adapters
  are not described as invokable skills.
- [ ] Run the shell contract test and explicit-trigger test GREEN.
- [ ] Commit the five paths with `feat: upgrade adaptive wrap-session protocol`.

### Task 6: Verify Behavior and the Whole Integration

**Files:**
- Modify: `docs/superpowers/specs/2026-07-29-wrap-session-eval-results.md`

**Interfaces:**
- Consumes: unchanged scenarios and all prior tasks.
- Produces: actual GREEN results and a reviewed branch ready only for explicit
  push authorization.

- [ ] Replay every existing and protocol-specific scenario in fresh contexts.
  Do not weaken prompts or criteria; capture actual model/harness provenance
  and transcript paths.
- [ ] Append GREEN results, set the eval document to `status: complete` only
  when every criterion passes, and retain previous RED evidence.
- [ ] Run:
  `python3 -m unittest discover -s skills/evolving-skills/tests -p 'test_*.py' -v`.
- [ ] Run `bash tests/wrap-session/test-wrap-session-contract.sh`.
- [ ] Run `env TZ=UTC bash tests/codex/test-package-codex-plugin.sh`.
- [ ] Run `bash tests/opencode/test-priority.sh` and `git diff --check`.
- [ ] Confirm no `.superpowers/` runtime data, duplicate local `SKILL.md`,
  Obsidian reference edit, or upstream write is present.
- [ ] Commit only the eval-results update with
  `test: record wrap-session protocol evaluations`.
- [ ] Present commits and verification. Do not push or create a PR.
