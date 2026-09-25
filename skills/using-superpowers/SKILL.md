---
name: using-superpowers
description: Select among Superpowers workflow skills when the task needs a method and the applicable skill is unclear.
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

| Task condition | Relevant method |
| --- | --- |
| Product behavior or a material design choice remains unresolved | `brainstorming` |
| An observed bug needs diagnosis | `systematic-debugging` |
| Execution dependencies need a written plan | `writing-plans` |
| An existing plan needs execution | `executing-plans` |
| A coding task benefits from a test-first workflow | `tdd` |

Choose the method that resolves the current need. Do not require a fixed chain
of brainstorming, planning, implementation, and review for every task.

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
