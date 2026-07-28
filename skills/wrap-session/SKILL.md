---
name: wrap-session
description: Use when ending or wrapping up a working session, preparing a handoff, or deciding how completed work should be documented or integrated
---

# Wrap Session

## Overview

Close the actual session, not an imagined release process. Preserve what future
work needs, verify only the claims being made, and spend effort in proportion
to the artifact and risk.

First read repository instructions. If
`.agents/superpowers/wrap-session/adapter.md` exists, read it as local policy;
load only references or scripts relevant to this closeout. It supplements this
workflow and is not another skill.

## Workflow

### 1. Establish state

Use the conversation, active tasks or plan, and repository status/diff when
applicable. Separate session-owned changes from pre-existing or unrelated
files.

### 2. Gate unfinished work

If meaningful requested work remains, a relevant check fails, or a blocker is
unresolved, do not silently close or present the task as complete. Ask:

> Meaningful work remains. Should I finish it now or create a handoff?

A request to commit or push unfinished work is not itself a handoff choice.
Unless the user already explicitly chose a WIP handoff, pause for this decision
even when the user asks not to be questioned.

If handoff is chosen, preserve the goal, completed work, remaining work,
blockers or failing evidence, and the next concrete action. Follow explicit
user direction for any WIP Git action.

### 3. Preserve durable context

Use [closeout-artifacts.md](closeout-artifacts.md) to update only artifacts the
session materially affected. Do not manufacture logs, ADRs, specs, or
observations for routine work. Ask when the correct durable update is
ambiguous.

### 4. Verify proportionally

Match evidence to the claim:

| Change | Useful evidence |
|---|---|
| Code or configuration | Focused changed-surface checks; broader gates when risk or repository policy requires |
| Documentation or knowledge | Relevant links, structure, examples, or repository doc checks |
| Office or exported artifact | Opens/renders and preserves critical content |
| No material change | Status inspection; state that further verification was skipped |

A focused check supports a focused claim, not “the full suite passes.”

### 5. Apply Git policy

Inspect repository instructions and the adapter before acting. Stage only
session-owned changes. Treat add, commit, merge, and push as separate actions.
Perform actions authorized by explicit user direction or clear local policy;
ask when disposition is consequential or unclear. Never include unrelated
files merely because staging everything is faster.

### 6. Return the receipt

Keep the result concise:

```markdown
Summary: <completed work or handoff>
Durable updates: <paths or none>
Verification: <evidence, failure, or intentional skip>
Git: <staged/commit/merge/push state>
Remaining: <next action or none>
```

## Red Flags

- A known failure exists, but the session is described as complete.
- A handoff is created when nothing meaningful remains.
- An unrelated test suite is run for a simple document or office artifact.
- Unrelated files are staged.
- Commit, merge, or push policy is guessed.
