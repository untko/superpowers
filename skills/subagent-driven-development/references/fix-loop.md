# The Fix Loop — Round Mechanics

Read this when a task review comes back with findings that enter the loop. The SKILL.md carries the entry conditions, the five-round cap, and the breaker's three outcomes; this file carries the per-round dispatch mechanics.

A fix round is one fix dispatch plus one scoped re-review. **Five rounds maximum per task.**

## Rounds 1-3 — Resume the original implementer

Send it the open findings verbatim. Its context is intact: it knows the task, the code, and its own choices.

If your harness cannot send another message to a live subagent, dispatch a fresh implementer carrying the brief path, the report-file path, and the findings — the report file is the persistent memory either way.

## Rounds 4-5 — Fresh implementer, more capable model

Dispatch a fresh implementer on a more capable model (see [model-selection.md](model-selection.md)), with the brief path, the report-file path, the open findings, and this framing:

> "A prior implementer attempted this task [N] times; you own it now. Read the report file for what was tried."

A loop that survives three resumes usually means the implementer cannot see its own problem — fresh eyes and a capability bump in one move.

## Every round, either way

The implementer fixes, re-runs the tests covering the amended code, appends its fix report to the same report file, and returns the short contract.

Before re-dispatching the reviewer, confirm the fix report contains the covering tests, the command run, and the output; dispatch the re-review once all three are present. Name the covering test files in the fix message — a one-line fix does not need the whole suite.

## The re-review is scoped

Run `scripts/review-package PLAN_FILE FIX_BASE HEAD` where FIX_BASE is the head the previous review saw, and dispatch [re-review-prompt.md](../re-review-prompt.md) with the findings list, the brief, the report file, and the printed diff path.

The re-reviewer verdicts each finding ADDRESSED or NOT ADDRESSED and flags new breakage in the fix diff only. New Critical/Important breakage in the fix diff joins the open findings list. Out-of-scope observations go to the ledger as deferred minors — they never extend the loop.

## After each round

Append to the ledger:

```
Task <N>: fix round <R>/5 (<X> addressed, <Y> open — <finding one-liners>; commits <a7>..<b7>)
```

Never fix findings yourself in the controller session — your context stays clean for coordination, and controller fixes skip review.
