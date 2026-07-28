---
name: wrap-session
description: Use when ending or wrapping up a working session, preparing a handoff, or deciding how completed work should be documented or integrated
---

# Wrap Session

## Overview

Preserve needs, verify claims proportionally, and keep writes
inside the active repository and session-owned scope.

## Workflow

### 1. Establish scope and policy

Read repository instructions, conversation/plan, and status/diff. Separate
session-owned changes from pre-existing or unrelated files.

Check exactly `.agents/superpowers/wrap-session/adapter.md`. Absence selects
global defaults. If present, validate frontmatter before applying it:

```yaml
schema: superpowers-adapter/v1
extends: wrap-session
contract: 1
adapter-version: <positive integer>
```

Report invalid metadata; never guess policy. Read only resources required for
the current phase. Reject directories, absolute paths, `..`, missing files, and
symlink escapes. Adapters are not invokable skills and cannot weaken scope,
verification, Git, or cross-repository gates.

### 2. Gate unfinished work

If meaningful work remains, a check fails, or a blocker is unresolved, do not
claim completion. Ask:

> Meaningful work remains. Should I finish it now or create a handoff?

Unless the user explicitly chose a WIP handoff, pause even when asked not to
question. A commit/push request is not a handoff choice. For a handoff,
preserve the goal, completed/remaining work, blockers or failing evidence, and
next action; follow explicit WIP Git direction.

### 3. Preserve durable context

Use [artifact decisions](references/closeout-artifacts.md) to update only
artifacts materially affected. Record significant reusable friction, minimally
sanitized, in `.superpowers/observations/pending/`; never scan history, invent
provenance, promote a proposal, or edit another repository. Put an unwritable
proposed note in the receipt. Ask when the durable destination is ambiguous.

### 4. Verify proportionally

Match evidence to the claim:

| Change | Useful evidence |
|---|---|
| Code or configuration | Focused changed-surface checks; broader gates when risk/policy requires |
| Documentation or knowledge | Relevant links, structure, examples, or doc checks |
| Office or exported artifact | Opens/renders; critical content preserved |
| No material change | Status inspection; state that further verification was skipped |

Focused evidence supports focused claims.

**REQUIRED SUB-SKILL:** Use superpowers:verification-before-completion for
evidence claims.

### 5. Apply Git gates

Stage only session-owned files, never the worktree. Treat add, commit, merge,
and push separately. Commit only with explicit direction or clear local policy.
Push requires separate explicit authorization.

When completed branch disposition is needed, **REQUIRED SUB-SKILL:** Use
superpowers:finishing-a-development-branch. Do not use it for unfinished work.

### 6. Return the receipt

```markdown
Summary: <completed work or handoff>
Owned scope: <session-owned paths>
Adapter status: <absent, valid version, or exact error>
Durable artifacts: <updated paths or none>
Verification: <evidence, failure, or intentional skip>
Git: <staged, commit, branch, and push state>
Remaining work: <next action or none>
Observations: <local paths, receipt-only note, or none>
```

## Red Flags

- A known failure exists, but the session is described as complete.
- Staging the worktree or unrelated files.
- Inventing provenance or hard-coding repository-specific paths.
- Silently ignoring an invalid adapter.
- Editing another repository during ordinary wrap-up.
- Treating an observation or proposal as authorization.
