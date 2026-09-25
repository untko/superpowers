---
name: using-superpowers
description: Select among workflow skills when the task needs a method and the applicable skill is unclear.
metadata:
  version: "0.1.0"
---

# Select a workflow skill

Use this router when skill selection is unclear. If the task already names an
applicable skill, read that skill directly. A bounded subagent assignment does
not need this router unless its assigned workflow is unclear.

## Selection

1. Identify the requested outcome and any applicable repository instructions.
2. Match the task to a skill's actual capability and trigger. A shared keyword
   alone does not establish relevance.
3. Read the selected skill before using its workflow. Announce its purpose
   briefly, without loading other skills merely to explain the selection.
4. Read supporting references only when their stated condition applies.

If no skill adds useful task guidance, handle the request directly. Explicit
user requests for a skill and applicable repository routing still apply.

This table is the single routing authority for this library. Each job has one
owner. Skills marked *(user-typed)* set `disable-model-invocation`: do not load
them yourself; name the command and let the user type it.

| Task condition | Skill |
| --- | --- |
| An idea or design choice needs interrogating before building | `grilling`; in a repo with docs, `/grill-with-docs` *(user-typed)* |
| A settled conversation should become a spec | `/to-spec` *(user-typed)* |
| A spec should be broken into tickets | `/to-tickets` *(user-typed)* |
| A plan or ticket needs executing | `/implement` *(user-typed)* |
| An observed bug or performance regression needs diagnosis | `diagnosing-bugs` |
| A coding task benefits from a test-first workflow | `tdd` |
| A module interface or seam needs designing | `codebase-design` |
| Domain terminology needs pinning down, or an ADR recorded | `domain-modeling` |
| A design question is best answered by a throwaway build | `prototype` |
| A non-library topic needs researching into a repo file | `research` |
| Changes since a fixed point need review against standards and spec | `review-since` |
| Review feedback needs acting on | `receiving-code-review` |
| A merge or rebase conflict is in progress | `resolving-merge-conflicts` |
| Two or more independent tasks can run in parallel | `dispatching-parallel-agents` |
| Work needs an isolated workspace | `using-git-worktrees` |
| About to claim work is done | `verification-before-completion` |
| A finished branch needs integrating | `finishing-a-development-branch` |
| A session is ending or needs a handoff | `wrap-session` |
| Steps only a human can perform | `wizard` |
| Diagrams or visual artifacts | `creative`; Draw.io specifically, `drawio` |
| A skill needs writing or editing | `writing-for-agents` |

Choose the skill that resolves the current need. Do not require a fixed chain
of grilling, spec, implementation, and review for every task.

Several imported skills read tracker and label config written by
`/setup-matt-pocock-skills`; if it is missing, tell the user to run it.

## Boundaries and completion

Skills support the user's scope and existing authorization. They do not grant
permission for additional actions. Repository evidence rules, ownership limits,
and approval gates remain binding.

Selection is complete when the applicable workflow is known. Continue the
requested task through its completion criteria, without asking the user to
approve skill selection or repeating an approval already provided.

For harness-specific mechanics, read only the relevant reference when needed:

- Codex delegation or Git environment handling: [Codex tools](references/codex-tools.md).
- Pi tool adaptation: [Pi tools](references/pi-tools.md).
- Antigravity tool adaptation: [Antigravity tools](references/antigravity-tools.md).
- Gemini tool adaptation: [Gemini tools](references/gemini-tools.md).

For authorized skill maintenance, use the available `evolving-skills` workflow
to record demonstrated, reusable friction. Ordinary task execution does not
require an archive scan, observation write, or global skill edit.
