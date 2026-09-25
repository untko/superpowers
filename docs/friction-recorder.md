# Friction recorder

`hooks/friction_recorder.py` is a deterministic hook: it reads the session's
transcript, finds friction (a correction the user typed, a tool that failed),
and appends one JSON line per event to `<project>/.superpowers/friction.jsonl`.
No model call. The `Stop` sweep covers the whole session, and event ids dedupe
across runs, so registering `Stop` alone is enough everywhere.

One script serves every CLI. `hooks/transcripts.py` normalizes each harness's
transcript into the Claude Code records the recorder reads; the recorder core
(attribution, dedupe, log) is the same for all of them. Point the hook at this
repo, not the plugin path, so it works with symlinked skills.

## Claude Code

Add the three events to `~/.claude/settings.json` (or a project's
`.claude/settings.json`), pointing at the script in this repo:

```json
{
  "hooks": {
    "PostToolUseFailure": [
      {"hooks": [{"type": "command", "command": "python3 /path/to/superpowers/hooks/friction_recorder.py --harness claude-code"}]}
    ],
    "UserPromptSubmit": [
      {"hooks": [{"type": "command", "command": "python3 /path/to/superpowers/hooks/friction_recorder.py --harness claude-code"}]}
    ],
    "Stop": [
      {"hooks": [{"type": "command", "command": "python3 /path/to/superpowers/hooks/friction_recorder.py --harness claude-code"}]}
    ]
  }
}
```

`PostToolUseFailure` and `UserPromptSubmit` catch friction as it happens;
`Stop` sweeps the transcript, so skill attribution is right even if you
register only it.

## Codex CLI

Codex runs Claude-compatible command hooks and passes the payload as JSON on
stdin. Its `Stop` payload carries `session_id`, `cwd`, `hook_event_name: "Stop"`
and `transcript_path` (a rollout JSONL), which the codex adapter normalizes.

Add one `Stop` entry to `~/.codex/hooks.json` (`$CODEX_HOME/hooks.json`, or
`.codex/hooks.json` per project). Event names are PascalCase:

```json
{
  "description": "Record skill friction",
  "hooks": {
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 /path/to/superpowers/hooks/friction_recorder.py --harness codex",
            "timeout": 10
          }
        ]
      }
    ]
  }
}
```

Codex asks you to trust newly discovered hooks at startup: choose *Trust all and
continue* or the hook stays disabled. A project's `.codex/hooks.json` and the
`[hooks]` section of `config.toml` both load, and Codex warns if both are
non-empty for the same layer.

## OpenCode

OpenCode has JS plugins rather than command hooks. `hooks/opencode/friction-recorder.js`
is one: on `session.idle` it writes the session's messages to a temp file and
spawns the recorder with a `Stop` payload, so the sweep sees the whole session.
It resolves this repo from its own file location, so symlink it:

```bash
ln -s /path/to/superpowers/hooks/opencode/friction-recorder.js \
  ~/.config/opencode/plugins/friction-recorder.js
```

Project-level `.opencode/plugins/` works too. The plugin swallows every error —
capture must never break a session.

## Harness names

`--harness` names the normalizer and is recorded on every event:
`claude` (or `claude-code`) reads a Claude Code transcript, `codex` a rollout
JSONL, `opencode` a JSON message array. An unknown name records nothing.
