---
title: Codex Luna workers across hosts
---

# Codex Luna workers

Luna runs through the user's authenticated Codex account. The parent keeps
ownership, verification, and the final decision. A CLI relay is a subprocess;
only Codex's native `luna6_max_worker` / `luna_max_worker` roles use its own
multi-agent tools. Claude and Antigravity need a shell route to Codex.

## Shared launcher

Use `scripts/luna_worker.py` relative to this skill's directory. It needs Python
3, Git, an authenticated Codex installation, and an authorized git repository.
Send the self-contained brief on stdin: outcome, owned files or questions,
constraints, and exact checks. For edits, use an isolated worktree.

On an installation sharing skills through `~/.agents/skills`:

```bash
python3 "$HOME/.agents/skills/subagent-workers/scripts/luna_worker.py" \
  --model gpt-6-luna --dir /absolute/path/to/repo --mode read-only <<'BRIEF'
Find the parser entry points. Own only this read-only question. Report paths
and line numbers; run no edits, commits, pushes, external messages, or agents.
BRIEF
```

Replace the launcher path with the loaded skill's actual path if that alias is
absent. Use `--mode workspace-write` for an approved bounded edit in its own
worktree. `--model gpt-5.6-luna` is an explicit choice, never an automatic
fallback. Both models use `model_reasoning_effort=max`.

The launcher prepends bounded-worker rules, runs Codex once, captures its
actual exit code and final handoff, and cleans up temporary output files. The
timeout defaults to 540 seconds; split larger tasks, or set `--timeout` within
the host tool's time limit. It retains Codex's git check and sandbox; it does
not bypass approvals or alter authentication or user configuration.

## Choose a working Codex binary

Selection order is `--codex-bin`, then `LUNA_CODEX_BIN`, then the macOS
ChatGPT app-bundled CLI when installed, then `codex` on PATH. Explicit choices
fail if unavailable; a failed model call never triggers a different binary or
model. The selected binary path is reported on stderr.

For another installation or platform, select the executable explicitly:

```bash
python3 /absolute/path/to/subagent-workers/scripts/luna_worker.py \
  --codex-bin /absolute/path/to/codex --model gpt-6-luna \
  --dir /absolute/path/to/repo --mode read-only < /absolute/path/to/brief.txt
```

On Windows, use the same script and flags with the host's Python command and
native stdin redirection; select the installed Codex executable. That platform
has not been tested here. Availability depends on the binary and account
accepting the model.

Verified 2026-09-29 on this installation: PATH Codex **0.144.5** rejected
`gpt-6-luna` with the ChatGPT-account unsupported-model error. The app-bundled
Codex **0.158.0-alpha.2.1** accepted the same Luna 6 max read-only probe
(`exit=0`). The earlier rejection was not an account-wide capability verdict.
Other machines and host integrations need their own live verification.

## Host routing

- **Codex native tools:** spawn `agent_type: "luna6_max_worker"` with
  `fork_turns: "none"` and a self-contained brief. Observe completion through
  the harness; do not invent a subprocess exit code for a native response.
- **Claude Code:** its installed `luna6-max-worker` Agent relay uses the shared
  launcher through Bash. If the relay is absent, run the launcher with Bash
  directly. Set the tool timeout above the launcher's limit.
- **Antigravity, Gemini, and other hosts:** call the launcher through the
  available shell execution tool and wait for the process to finish. A host's
  own subagent model selector does not select the Codex worker model.

Hosted Codex needs network access and its normal user-level runtime files. If
the parent is sandboxed, use its execution-permission mechanism for the
authorized call; keep the worker's `--mode` sandbox. Runtime initialization
failure before the request is not evidence of model unavailability.

## Validate the handoff

For a launched process, stdout begins with `exit=N`, the actual Codex exit
code. A nonzero exit or missing final message is failure. Local preflight
errors go to stderr and return 2 without claiming the model ran; timeout
returns 124 and reports the terminated process's actual exit code.

Preserve diagnostics and stop on an unsupported-model error. Do not change
model, effort, provider, or credentials to mask it. On success, inspect the
diff, ownership boundaries, and requested checks before accepting the work.
