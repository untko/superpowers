---
title: Wrap Session Artifact Decisions
---

# Wrap Session Artifact Decisions

Choose artifacts from observable session impact. Repository instructions and
the local adapter determine exact paths and formats.

| Artifact | Trigger | Default |
|---|---|---|
| Living documentation | User-visible behavior, interfaces, operating steps, or current facts changed | Update the existing authoritative document; skip for internal-only implementation changes |
| Decision record | A consequential, durable choice was made among meaningful alternatives | Update an existing record or create the repository's normal form; skip routine, reversible, or already-recorded choices |
| Observation | Significant reusable friction, a recurring error, or a plausible skill improvement appeared | Write minimal sanitized evidence to `.superpowers/observations/pending/`; skip routine success and one-off project facts |
| Unfinished task or handoff | Meaningful work remains, a blocker exists, or the user chooses to pause | Update the existing task/handoff when present; otherwise create one only after the finish-or-handoff choice |
| Verification evidence | A completion or correctness claim needs support | Record focused command/result evidence in the existing task record or receipt; do not manufacture a separate log |
| Temporary plan or spec | Scope, acceptance criteria, status, or continuing authority changed | Update it while authoritative; after completion follow local disposition policy, otherwise leave it and report its state rather than deleting it |

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

Use the `superpowers-observation/v1` contract. Capture reported runtime, global
skill contract `1`, adapter status, phase, expected and actual behavior,
minimal evidence, diagnosis, and candidate scope/target/status. Use `unknown`
for unavailable provenance; never infer it.

Raw evidence stays in the active repository. Promotion into the global library
happens only during an explicitly authorized global `evolving-skills` run.
Ordinary wrap-up neither scans the observation archive nor writes an installed
skill, sibling checkout, or source repository.
