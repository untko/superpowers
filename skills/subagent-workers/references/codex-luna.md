# Codex Luna workers

Applies to `luna-max-worker` (`gpt-5.6-luna`) and `luna6-max-worker`
(`gpt-6-luna`), and to any harness running Codex directly. Agent files live in
`~/.claude/agents`; the Codex `.toml` twins are in the same directory.

Run once, brief on standard input, the worker's final message written to a file:

```bash
OUT=$(mktemp) && codex exec -m gpt-5.6-luna -c model_reasoning_effort=max \
  -s workspace-write -C /abs/path/to/repo --ephemeral --color never \
  -o "$OUT" - >/dev/null 2>"$OUT.err" <<'BRIEF'
<bounded-worker rules and the task>
BRIEF
echo "exit=$?"; cat "$OUT"; tail -5 "$OUT.err"; rm -f "$OUT" "$OUT.err"
```

- `-s read-only` for investigation; `workspace-write` for edits.
- The directory must be a git repository (no `--skip-git-repo-check`).
- The Bash tool caps a call at about 10 minutes; split larger tasks.
- Prefix the task with the bounded-worker rules: restate the outcome and owned
  files, do not broaden scope, do not commit, push, message externally or spawn
  agents, no destructive reset or checkout, report checks and blockers.
- Codex prints "model is not supported when using Codex with a ChatGPT account"
  for models the account lacks. Report it and stop; never retry with another
  model or effort.
- The worker does not commit or push: the parent reviews `git diff`.
