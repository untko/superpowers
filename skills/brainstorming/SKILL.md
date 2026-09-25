---
name: brainstorming
description: Resolve open product or design decisions before implementation, or develop a design when explicitly requested.
metadata:
  version: "0.1.0"
---

# Develop a design

Turn unresolved ideas into a design with clear scope, constraints, and acceptance
criteria. Use the same decision rules across models. Additional procedure
depends on the task, not on a model's estimate of its own capability.

## Choose the depth

First read relevant project context and identify what is already specified or
approved. Do not repeat discovery for decisions the user has already made.

| Condition | Action |
| --- | --- |
| Behavior is specified and implementation choices are routine and reversible | State material assumptions briefly and proceed within existing authorization. |
| One missing choice would materially change the result | Ask a focused question or present the concrete choice and your recommendation. |
| Several coupled decisions affect behavior, interfaces, data, or architecture | Read [full design guidance](references/full-design.md) and develop a coherent proposal. |
| The user explicitly requests a design or specification | Produce that artifact at the requested depth. |

A new feature does not automatically need a separate design phase. Conversely,
a small code change can require a decision about stored data or public behavior.
Assess the unresolved decision and its consequences, not the file count alone.

## Decision checklist

Keep these questions explicit when the design is unsettled:

1. What result does the user want, and what is outside scope?
2. Which constraints and existing decisions must the design preserve?
3. What remains unknown, and can available context resolve it?
4. Which meaningful alternatives exist, and what are their tradeoffs?
5. What observable result will establish completion?

Ask only for missing information that matters. Continue independent preparation
while waiting. For consequential unresolved choices, present a concrete proposal
before requesting a decision. Do not execute dependent changes until resolved.

Existing approval covers the agreed boundary. Do not add separate approvals for
each design section, its written copy, and an unchanged implementation plan.
Additional external actions or scope changes still require applicable authorization.
Repository-specific evidence and mutation gates remain binding for every model.

## Examples

- A specified label correction can proceed after locating the relevant file.
- A requested export with unspecified fields needs its output contract resolved.
- An approved migration design can proceed through authorized implementation and
  checks. Reopen design only if new evidence changes a material decision.

## Completion

For a design-only request, deliver the design with acceptance criteria and any
unresolved decisions. Do not infer implementation authorization from discussion.

When implementation is authorized, continue through implementation and relevant
verification after design decisions are resolved. Use `writing-plans` only when
execution dependencies warrant a separate plan. Report the completed result and
any remaining blocker.

When a visual comparison would clarify a decision, use an appropriate available
visual tool. If using the optional browser companion, obtain agreement and read
[visual companion instructions](visual-companion.md) before starting it.
