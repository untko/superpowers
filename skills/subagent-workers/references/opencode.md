# OpenCode launcher

Applies to `opencode-scout` and `opencode-builder`, and to any harness calling
the launcher directly. Source: `~/Projects/codex/a2a/subagents/opencode-subagents`.

Choose `scout` for read-only exploration or `builder` for a bounded edit. Use
the installed launcher path directly; do not probe the CLI first:

```bash
LAUNCHER="${HOME:?HOME is required}/.local/bin/opencode-subagent"
```

Choose exactly one context mode before requesting network access:

- **Repository mode:** `--dir` only when the whole directory is authorized for
  hosted processing.
- **Text-only mode:** for an authorized excerpt from a private source, put all
  necessary text in the task and use `scout --isolated`. It runs in an empty
  temporary workspace removed on exit, and is unavailable to builders.

Hosted models need outbound network, and OpenCode may write logs under the home
directory. Use the host's permission path on the **first** live invocation:

- Codex: set `sandbox_permissions` to `require_escalated` on the execution tool
  (a tool parameter, not shell text) and explain that the sanitized worker needs
  network and its user-level runtime files.
- Claude Code: allow the normal permission prompt.

Do not make a sandboxed probe first, and never retry a private `--dir` with
broader permissions.

Task text goes on standard input, never in arguments. `--timeout SECONDS`
defaults to 1200; the Claude relays pass 540 to fit the Bash tool cap.

```bash
"$LAUNCHER" scout --dir /path/to/project <<'BRIEF'
Find the parser entry points and report file paths and line numbers.
BRIEF

"$LAUNCHER" scout --isolated <<'BRIEF'
Summarize this authorized excerpt: ...
BRIEF

"$LAUNCHER" builder --dir /path/to/worktree <<'BRIEF'
Implement the assigned change; run the named checks and report outcomes.
BRIEF
```

Shell command substitution normalizes trailing newlines; the launcher does not
promise byte-for-byte preservation of them.

## Models

The launcher takes only current OpenCode Zen IDs ending in `-free`, in the order
of `config/free-model-priority.txt` (the user's pinned model first), or the file
named by `OPENCODE_SUBAGENT_PRIORITY_FILE`. A failing model falls through to the
next; the `--timeout` is shared across them, so a hanging first model burns it.
The roster cache lasts 15 minutes. Check `opencode models opencode` when a model
errors.

## Exit codes

| Code | Meaning |
| --- | --- |
| 0 | worker handoff extracted |
| 2 | caller, path, timeout, dependency, or local OpenCode runtime failure |
| 3 | no eligible free model, roster discovery failed without a valid cache, or every model failed |
| 4 | another builder holds the checkout lock; do not remove it |
| 124 | worker timed out |

Standard output is the worker handoff; model notices and diagnostics go to
standard error.
