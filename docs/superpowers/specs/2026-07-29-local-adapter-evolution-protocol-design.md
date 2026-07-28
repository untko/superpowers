---
title: Local Adapter and Skill Evolution Protocol
date: 2026-07-29
status: approved
---

# Local Adapter and Skill Evolution Protocol

## Objective

Keep one globally discoverable Superpowers skill while allowing optional
repository-specific policy and evidence. Local repositories may propose global
improvements, but only an explicit global `evolving-skills` run may generalize,
test, approve, and release them.

`wrap-session` is the first consumer. Commit `6dd3b03` is the verified minimal
baseline; this design extends rather than replaces its unfinished-work and
proportional-verification behavior.

## Invariants

1. The global skill is the only discoverable workflow.
2. Optional local adapters contain no `SKILL.md` and cannot shadow the global
   skill.
3. Missing adapters select global defaults without warning.
4. Invalid adapters are reported; their policy is never guessed.
5. Raw observations stay in the repository where they occurred.
6. Proposals are evidence, not authorization.
7. Ordinary skill runs never write to another repository.
8. Global releases never rewrite local adapters.
9. Local policy cannot weaken owned-scope, verification, commit, push, or
   cross-repository approval gates.
10. No change from this fork is proposed to `obra/superpowers`.

## Storage

Tracked local policy:

```text
.agents/superpowers/{global-skill-name}/
├── adapter.md
├── references/
└── scripts/
```

Ignored operational evidence:

```text
.superpowers/observations/
├── pending/
├── proposed/
└── archived/
```

Reviewed durable proposals:

```text
docs/superpowers/proposals/
```

`.superpowers/` is runtime state, not the home of specs and plans.

## Adapter Contract

An adaptable global skill checks
`.agents/superpowers/{skill-name}/adapter.md` at the active project root. The
adapter frontmatter must contain:

```yaml
schema: superpowers-adapter/v1
extends: wrap-session
contract: 1
adapter-version: 1
```

The skill reads only references or scripts required for the current phase.
Absolute paths, `..` traversal, and symlink escapes outside the adapter
directory are invalid.

## Observation Contract

Raw observations use `superpowers-observation/v1` and record:

```yaml
runtime:
  provider: openai
  model: gpt-5.6-sol
  reasoning-effort: high
  harness: codex-app
  harness-version: unknown
  interface: desktop
skills:
  global:
    name: wrap-session
    contract: 1
    plugin-version: unknown
    git-commit: unknown
  adapter:
    path: unknown
    version: unknown
    git-commit: unknown
observation:
  phase: durable-context
  expected: Update the existing task record.
  actual: Created a duplicate handoff document.
  evidence: Two handoff files were present.
  diagnosis: global-skill
candidate:
  scope: potentially-global
  target: skill
  status: observed
```

Unavailable provenance is `unknown`, never inferred. Allowed diagnoses are
`global-skill`, `adapter`, `model`, `harness`, `tool`, `project`, and
`uncertain`. Candidate scopes are `local`, `potentially-global`, and
`uncertain`; targets are `skill`, `reference`, `script`, `test`, and `none`.
Evidence is minimal and sanitized; secrets and raw transcripts are excluded.

## Lifecycle and Authority

1. Observe significant reusable friction under `pending/`.
2. Classify it during closeout or an explicit evolution pass.
3. Resolve local-only findings in the adapter with approval and local tests.
4. Sanitize potentially universal findings into `proposed/`.
5. With approval, preserve a reviewed proposal under
   `docs/superpowers/proposals/`.
6. Explicitly import/read it in the global repository and run
   `evolving-skills`.
7. Record accepted, rejected, deferred, or local-only outcomes under
   `archived/`.

Normal skill invocation does not scan historical observations. No step
automatically edits an installed plugin or sibling repository.

## `wrap-session`

The global skill establishes owned scope, validates the optional adapter,
preserves only necessary durable context, delegates evidence claims to
`verification-before-completion`, delegates completed branch disposition to
`finishing-a-development-branch` only when needed, records significant
friction locally, and emits a portable completion receipt. Commit approval and
push authorization remain separate.

## Failure Handling

- Missing adapter: continue with global defaults.
- Invalid schema, `extends`, or contract: report the exact incompatibility.
- Missing or escaping resource: stop that extension point.
- Failing adapter script: preserve output and do not claim completion.
- Unwritable observation directory: put the proposed note in the receipt.
- Implicit cross-repository write: refuse and present an explicit import/update
  action for approval.

## Verification

Use unit tests for frontmatter parsing, adapter discovery, compatibility,
resource boundaries, observation validation, repository-local storage, and
legacy parser compatibility. Use deterministic skill contract tests and
unchanged before/after behavioral scenarios for adapter policy, unrelated
files, proportional verification, unfinished work, and promotion boundaries.
