---
title: Adaptive Wrap Session Design
date: 2026-07-29
status: approved
---

# Adaptive Wrap Session Design

## Objective

Add a small, model- and harness-agnostic `wrap-session` skill that closes a
working session without treating every session like a software release.

The workflow must adapt to the work that actually occurred. A short
documentation session should be cheap to close; unfinished implementation work
should either be completed or preserved in a useful handoff.

## Core Workflow

Every invocation performs five decisions:

1. **Check unfinished work.** Determine whether the requested task is complete
   from the current conversation, active plan or task state, and repository
   status when applicable. If meaningful work remains, ask whether to finish it
   now or create a handoff.
2. **Preserve relevant context.** Update only durable artifacts affected by the
   session: living documentation, logs, ADRs, specs, plans, task records, or
   observations. Ask when it is unclear whether an update is wanted.
3. **Verify proportionally.** Match evidence to the changed artifact and risk.
   Do not run an extensive software test suite for simple knowledge or office
   work.
4. **Apply repository Git policy.** Stage only session-owned changes. Commit,
   merge, and push only when repository instructions or explicit user
   authorization allow the action. Ask when disposition is unclear.
5. **Return a concise receipt.** Report completed work, durable updates,
   verification performed or intentionally skipped, Git state, and any
   remaining work or handoff.

## Adaptive Depth

The skill chooses depth from observable session state rather than requiring a
mode flag.

| Situation | Closeout depth |
|---|---|
| No meaningful changes or a short completed task | Check status, update nothing unnecessary, and return a brief receipt |
| Documentation, knowledge, or office artifact changed | Validate the artifact at the lightest useful level and update directly related records |
| Code or configuration changed | Run focused checks for the changed surface; use broader gates only when risk or repository policy requires them |
| Meaningful work remains or a blocker exists | Ask to finish or create a cold-start handoff; do not claim completion |

Verification is evidence for claims, not a mandatory list of commands. When no
useful verification exists, the receipt states that it was skipped and why.

## Optional Repository Adapter

The global skill is the only discoverable skill. A repository may optionally
provide local policy at:

```text
.agents/
└── superpowers/
    └── wrap-session/
        ├── adapter.md
        ├── references/
        └── scripts/
```

Only `adapter.md` is conventional. `references/` and `scripts/` are optional.
The directory contains no `SKILL.md`, preventing duplicate-name discovery and
skill drift.

When the adapter exists, the global skill reads it after repository
instructions and uses only sections relevant to the current closeout. The
adapter may identify:

- documentation, decision, task, and handoff locations;
- artifact-specific verification;
- generated or protected files;
- Git disposition rules; and
- local observation conventions.

The adapter cannot override user instructions, repository safety rules, or
ownership boundaries. No metadata schema or parser is required in v1.

## Observations and Evolution

An observation is optional. Record one only when the session reveals
significant reusable friction, a recurring error, or a plausible improvement
to a skill, reference, or script. Routine success and one-off project facts do
not become observations.

The default local location is:

```text
.superpowers/observations/
```

When available, an observation records:

```yaml
model: gpt-5.6-sol
reasoning-effort: high
harness: codex
harness-version: unknown
```

Unknown values remain `unknown`; they are not guessed. The body records the
skill, phase, expected behavior, actual behavior, concise evidence, and whether
the pattern appears local, potentially global, or uncertain.

Normal wrap-up does not read the observation archive or promote changes. During
an explicit `evolving-skills` run, significant observations may be generalized
and proposed for the global skill library. Cross-repository edits always
require explicit user approval.

## Git Safety

- Inspect repository instructions before choosing Git actions.
- Never stage unrelated or pre-existing files.
- Treat commit, merge, and push as separate actions.
- Follow an explicit local auto-disposition rule when one exists.
- Otherwise ask before consequential or ambiguous Git actions.
- Never open a pull request or write to `obra/superpowers` as part of this
  fork-specific workflow.

## Acceptance Criteria

1. `wrap-session` notices meaningful unfinished work and offers finish or
   handoff.
2. It does not manufacture logs, ADRs, specs, observations, or handoffs for a
   trivial completed session.
3. It uses lightweight artifact validation for knowledge and office work.
4. It uses focused verification for changed code and follows stricter local
   gates when required.
5. It loads an optional local adapter without requiring a duplicate local
   skill.
6. It stages only owned changes and follows repository-specific Git policy.
7. It emits a short, useful receipt.
8. The design introduces no runtime dependency, parser, synchronization
   service, or automatic cross-repository mutation.

## Non-Goals

- A universal adapter framework or schema validator.
- Automatic observation harvesting or promotion.
- Reading every local reference or observation during normal closeout.
- Replacing repository-native tasks, logs, ADRs, or handoff formats.
- Making every session run extensive verification.
- Contributing these fork-specific changes to `obra/superpowers`.
