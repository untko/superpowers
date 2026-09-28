---
name: subagent-workers
description: Use when a bounded task (read-only exploration, a scoped edit, a deep investigation) should go to a cheaper or stronger worker than the current agent, such as an OpenCode free model or a Codex Luna model
---

# Subagent workers

The parent agent keeps scope, safety, verification, and the final decision. A
worker executes one bounded brief and hands back a report.

## 1. Classify before sending

Classify the brief text and the whole directory the worker can read. A worker
may read any file under its directory whatever the brief says, and a harmless
excerpt from a private repository does not make the repository safe.

Never send credentials, tokens, secrets, private personal or financial data, or
consequential external actions to a hosted free model. Confidential code goes
only to a Codex worker (the user's own ChatGPT account), never to an OpenCode
free model.

## 2. Pick the worker

| Worker | Model | Use for | Sees |
| --- | --- | --- | --- |
| `opencode-scout` | OpenCode free roster, pinned model first | read-only exploration; `ISOLATED` for an excerpt only | hosted free model |
| `opencode-builder` | OpenCode free roster | one bounded edit with named files and checks | hosted free model |
| `luna-max-worker` | `gpt-5.6-luna`, max effort, via Codex | hard but bounded work: cross-cutting change, high-risk verification | OpenAI, user's account |
| `luna6-max-worker` | `gpt-6-luna`, max effort, via Codex | same, when the Codex binary accepts the model | OpenAI, user's account |

Use the requested Luna generation. Older PATH Codex can reject Luna 6 while
app-bundled Codex accepts it; use the [shared launcher](references/codex-luna.md).
Report rejection without changing model or effort.

Never fall back to a paid model when free quota runs out. CLI workers are
subprocesses; Codex's Luna roles are native subagents. Name the route accurately.

Visual work: workers cannot see images. The brief lists layout checks that run
as code, and the parent reviews screenshots itself.

## 3. Write the brief

Give a self-contained brief: outcome, owned files or questions, constraints,
and exact checks. Editing workers get separate git worktrees, never the main
checkout or another worker's checkout.

The Claude Code relays read optional first lines from the brief, strip them, and
pass the rest verbatim: `DIR: /abs/path` (directory or worktree the worker may
use; default the current directory), `ISOLATED` (scouts only: empty temporary
workspace, so the brief carries all the text), `MODE: read-only` (Luna; default
`workspace-write`, which needs its own worktree).

## 4. Invoke

- **Codex:** native `luna6_max_worker` / `luna_max_worker`, with
  `fork_turns: "none"`; OpenCode uses its shell launcher.
- **Claude Code:** the Agent tool with `subagent_type` `opencode-scout`,
  `opencode-builder`, `luna-max-worker` or `luna6-max-worker`. Each is a thin
  Haiku relay with only Bash that runs the launcher once. Or run the launcher
  through Bash.
- **Antigravity, Gemini, other hosts:** shared launcher through their shell
  tool. Agent names are host-specific; the shell route is portable.

Subprocess handoffs need the real `exit=N`; local launcher errors are failures.
Native responses use harness completion, not invented process exits.

## 5. Validate

Read failure diagnostics. On success, verify the requested checks, observable
behavior, diff, and ownership boundaries. Preserve unrelated work. Finish when
checks pass or report a concrete blocker. Accept valid output without restyling
it merely for preference.

Worker mechanics: [OpenCode launcher](references/opencode.md) ·
[Codex Luna](references/codex-luna.md)
