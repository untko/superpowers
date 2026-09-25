---
title: Full design guidance
type: reference
---

# Full design guidance

Use this procedure when several unresolved decisions affect the same result.
The checklist provides execution support without adding approval stages.

## Establish the boundary

Read the relevant files, contracts, and prior accepted decisions. Inspect recent
changes when they could affect the proposal. Avoid unrelated repository tours.

State the objective, constraints, assumptions, and acceptance criteria. Separate
facts established by inspection from choices that need the user's judgment.
Resolve discoverable facts before asking questions.

If the request spans independent subsystems, identify their responsibilities and
dependencies. Propose a bounded first deliverable when the requested scope needs
decomposition. Keep the user's original objective visible.

## Compare meaningful approaches

Present viable alternatives where they lead to different outcomes or costs.
Explain the recommended approach and its principal tradeoff. Do not invent extra
options to satisfy a fixed count.

For each important component, identify its responsibility, interface, and
dependencies. Keep business rules independent of external implementation details
where that separation has a concrete benefit. Prefer existing conventions and
avoid unrelated refactoring.

Include data flow, failure handling, validation, and migration or rollback
requirements when those concerns affect the design. A user interface proposal
should also explain observable behavior and important interaction states.

## Make the decision reviewable

Present enough detail for the user to assess unresolved choices. Use concise
prose for a small proposal and a document when the design needs a durable record.
Follow repository location rules. Otherwise use
`docs/superpowers/specs/YYYY-MM-DD-<topic>-design.md` when a saved specification
is warranted.

Before requesting a decision, check for missing requirements, contradictory
assumptions, unclear interfaces, scope expansion, and untestable acceptance
criteria. Fix discoverable gaps directly. Label decisions that remain open.

Seek one decision on the coherent proposal when user input is required. Existing
approval remains valid when the written artifact faithfully records that design.
If new evidence changes a material choice, explain that change before dependent
implementation.

## Continue to the requested outcome

A design-only request ends with the requested design artifact and its open
decisions. An authorized build continues through implementation and appropriate
checks after the design is settled.

Use a separate implementation plan when order, dependencies, or handoff needs
justify it. Do not require a plan merely because this reference was loaded.
Git commits, publication, deployment, and delegation follow the user's scope and
applicable repository rules.
