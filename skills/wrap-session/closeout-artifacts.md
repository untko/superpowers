---
title: Wrap Session Artifact Decisions
---

# Wrap Session Artifact Decisions

Choose artifacts from observable session impact. Repository instructions and
the local adapter determine exact paths and formats.

| Artifact | Update when | Skip when |
|---|---|---|
| Living documentation | User-visible behavior, interfaces, operating steps, or current facts changed | The implementation changed internally without affecting documented use |
| Log or session record | Local policy requires it or the entry materially helps continuity | It would only repeat the commit or receipt |
| ADR or decision record | A consequential, durable choice was made among meaningful alternatives | The choice was routine, reversible, or already documented |
| Spec or plan | Scope, acceptance criteria, status, or planned work changed | The session merely executed it without changing its meaning |
| Task record | Ownership, status, blocker, or next action changed | Nothing about the task state changed |
| Handoff | Meaningful work remains, a blocker exists, or the user chooses to pause | The task is complete and the receipt is sufficient |
| Observation | Reusable friction, a recurring error, or a plausible skill improvement appeared | Routine success or a one-off project fact |

When the need for a durable update is unclear, ask instead of creating another
source of truth.

## Handoff Minimum

A cold-start handoff contains:

- objective and current status;
- completed and remaining work;
- blockers and exact failing evidence;
- session-owned files and important decisions; and
- the next concrete action or command.

## Significant Observations

Use the repository's convention, defaulting to
`.superpowers/observations/`. Do not scan or harvest the archive during normal
wrap-up.

Record known provenance without guessing:

```yaml
model: gpt-5.6-sol
reasoning-effort: high
harness: codex
harness-version: unknown
skill: wrap-session
scope: potentially-global
```

Also capture the phase, expected behavior, actual behavior, and minimum useful
evidence. Promotion into the global library happens only during an explicit
`evolving-skills` run with user approval.
