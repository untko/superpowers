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
| `luna6-max-worker` | `gpt-6-luna`, max effort, via Codex | same, when the account supports the model | OpenAI, user's account |

2026-09-29: `gpt-6-luna` was rejected on the user's ChatGPT account ("not
supported when using Codex with a ChatGPT account"). Use `luna-max-worker`
unless a direct run shows it accepted.

Never fall back to a paid model, even when free quota runs out. A worker is not
a native subagent of the harness: name it as what it is.

Visual work: workers cannot see images. The brief lists layout checks that run
as code, and the parent reviews screenshots itself.

## 3. Write the brief

The worker sees only the brief. It carries the outcome wanted, the files or
directories the worker owns, constraints, and the exact commands whose results
it must report. Optional first lines steer the relay: `DIR: /abs/path`,
`ISOLATED` (scouts), `MODE: read-only` (Luna). Builders get a git worktree,
never the main checkout, and never two builders in one checkout.

## 4. Invoke

- **Claude Code:** the Agent tool with `subagent_type` set to the worker name.
  Each is a thin Haiku relay with only Bash; it runs the launcher or Codex once
  and returns the output. Installed by the opencode-subagents package
  (`install.sh`) and `~/.claude/agents`.
- **Codex:** the OpenCode launcher through the shell ([opencode](references/opencode.md));
  Luna through its own agents (`luna_max_worker`, `luna6_max_worker`), spawned
  with the harness's multi-agent tools.
- **Any other CLI:** run the launcher or `codex exec` directly from the shell;
  both forms are in the references.

A relay's report counts only if it opens with the real `exit=N` line. A report
without one, or one that only repeats the brief, is a delegation failure: the
relay answered from the prompt instead of running the worker.

## 5. Validate

Treat every nonzero exit as delegation failure and read the diagnostics before
choosing. On success, check the result deterministically: tests, lint, type
checks, the diff, observable behavior. Confirm the worker stayed inside its
ownership and left unrelated work alone. The task is complete when those checks
pass or a concrete failure is escalated to the user. Do not spend frontier-model
effort restyling valid output that merely differs in preference.

Worker mechanics: [OpenCode launcher](references/opencode.md) ·
[Codex Luna](references/codex-luna.md)
