---
title: Adaptive Wrap Session Implementation Plan
date: 2026-07-29
status: complete
design: docs/superpowers/specs/2026-07-29-wrap-session-design.md
---

# Adaptive Wrap Session Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a concise, adaptive `wrap-session` skill with an optional
repository-local adapter and lightweight observation handoff.

**Architecture:** `skills/wrap-session/SKILL.md` owns the portable closeout
decisions. A short reference helps choose durable artifacts without hard-coded
repository paths. The existing `evolving-skills` skill gains only the boundary
needed to consume significant repository-local observations during an explicit
evolution run.

**Tech Stack:** Markdown skills, POSIX shell contract tests, existing
Superpowers skill conventions.

## Global Constraints

- Do not push, open a pull request, or otherwise write to `obra/superpowers`.
- Add no runtime dependency, adapter parser, synchronization service, or
  automatic cross-repository mutation.
- The global skill is the only discoverable workflow; the optional local
  adapter contains no `SKILL.md`.
- Verification depth follows the changed artifact, session risk, and
  repository instructions.
- Stage only session-owned files.
- Unknown model or harness provenance values remain `unknown`.
- Skill behavior changes use RED/GREEN evaluation before deployment.

## File Map

- `tests/wrap-session/eval-scenarios.md` — stable behavioral scenarios and pass
  criteria.
- `tests/wrap-session/test-wrap-session-contract.sh` — fast structural contract
  checks.
- `docs/superpowers/specs/2026-07-29-wrap-session-eval-results.md` — observed
  RED/GREEN evidence.
- `skills/wrap-session/SKILL.md` — adaptive closeout workflow.
- `skills/wrap-session/closeout-artifacts.md` — lightweight durable-artifact
  decision guide.
- `skills/evolving-skills/SKILL.md` — explicit local-observation intake
  boundary.
- `README.md` — skill-library entry.

---

### Task 1: Establish the Behavioral Baseline

**Files:**
- Create: `tests/wrap-session/eval-scenarios.md`
- Create: `tests/wrap-session/test-wrap-session-contract.sh`
- Create: `docs/superpowers/specs/2026-07-29-wrap-session-eval-results.md`

**Interfaces:**
- Consumes: a fresh agent context without `skills/wrap-session/SKILL.md`.
- Produces: three stable scenarios covering unfinished work, proportional
  verification, and owned Git disposition.

- [x] **Step 1: Define three compact scenarios**

Create scenarios for:

1. unfinished code work under pressure to commit immediately;
2. a completed office document where a full code test suite would be wasteful;
3. a repository with an adapter, one owned change, and one unrelated untracked
   file.

Each scenario records fixture, prompt, pass criteria, model, reasoning effort,
harness, and harness version.

- [x] **Step 2: Add the failing contract test**

The shell test checks that `skills/wrap-session/SKILL.md` exists, contains
valid `name` and `description` frontmatter, names the optional adapter path,
contains the finish-or-handoff decision, treats verification proportionally,
protects unrelated files, and returns a receipt.

Run:

```bash
bash tests/wrap-session/test-wrap-session-contract.sh
```

Expected RED: failure because `skills/wrap-session/SKILL.md` does not exist.

- [x] **Step 3: Run the behavioral scenarios without the skill**

Run each prompt in a fresh context without injecting the proposed skill. Record
only observed behavior and rationalizations. Keep outputs bounded to the
closeout decision.

- [x] **Step 4: Record the RED results**

Write the environment and per-scenario pass/fail evidence to
`docs/superpowers/specs/2026-07-29-wrap-session-eval-results.md`. Use `unknown`
for unavailable runtime values.

### Task 2: Implement and Verify the Minimal Skill

**Files:**
- Create: `skills/wrap-session/SKILL.md`
- Create: `skills/wrap-session/closeout-artifacts.md`
- Modify: `skills/evolving-skills/SKILL.md`
- Modify: `README.md`
- Modify: `docs/superpowers/specs/2026-07-29-wrap-session-eval-results.md`

**Interfaces:**
- Consumes: conversation state, repository instructions and status, optional
  `.agents/superpowers/wrap-session/adapter.md`, and significant local
  observations only during explicit evolution.
- Produces: an adaptive closeout decision and concise completion or handoff
  receipt.

- [x] **Step 1: Write the smallest skill that addresses RED failures**

Keep `SKILL.md` under 500 words. Its description contains only triggering
conditions. The workflow covers:

- meaningful unfinished work: finish now or create handoff;
- durable updates only when the session materially requires them;
- proportional verification for code, documentation, knowledge, and office
  artifacts;
- optional, selective local-adapter reading;
- owned-file staging and repository-directed commit, merge, and push; and
- a concise receipt.

- [x] **Step 2: Add the artifact decision reference**

Keep repository-specific paths out of the reference. For each artifact type,
state the observable condition that justifies updating it and when to skip it.

- [x] **Step 3: Add the evolution boundary**

Update `evolving-skills` so an explicit evolution run may read significant
observations from the active repository's `.superpowers/observations/`.
Routine wrap-up does not harvest the archive, and global edits still require
user approval.

- [x] **Step 4: Run fast GREEN checks**

Run:

```bash
bash tests/wrap-session/test-wrap-session-contract.sh
wc -w skills/wrap-session/SKILL.md
python3 -m unittest skills/evolving-skills/tests/test_parse_observations.py -v
```

Expected: contract test passes, `SKILL.md` is below 500 words, and existing
observation parser tests pass.

- [x] **Step 5: Replay the behavioral scenarios**

Run the unchanged scenarios with `wrap-session` available. Record actual GREEN
results and any new rationalizations. Tighten only wording tied to an observed
failure, then rerun the affected scenario.

- [x] **Step 6: Review the exact owned diff**

Confirm the change set contains only the design, plan, evaluation files,
`wrap-session` skill, its reference, the small `evolving-skills` edit, README,
and contract tests. Do not stage the pre-existing `hooks.json`, `plugin.json`,
legacy observation, or `__pycache__`.

- [x] **Step 7: Leave Git disposition explicit**

Report the verified diff and current branch. Commit, merge, or push only if
the repository instructions or the user explicitly authorize those actions.
