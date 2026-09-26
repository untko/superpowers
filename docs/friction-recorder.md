# Friction recorder

`hooks/friction_recorder.py` is a deterministic hook: it reads the session's
transcript, finds friction (a correction the user typed, a tool that failed),
and appends one JSON line per event to `<project>/.superpowers/friction.jsonl`.
No model call. `<project>` is the main checkout, even when the session runs in
a linked worktree: a worktree is removed when its branch merges, and its log
would go with it (`hooks/project_store.py` reads git's files, no subprocess).

A correction is a prompt that says the agent got something wrong: "no, …",
"wrong", "not what I asked", "you forgot …", "why did you …", "revert that".
A bare "don't" or "fix it" is an instruction or a preference, not a correction,
and text the user pasted or quoted is someone else's words; neither counts. The `Stop` sweep covers the whole session, and event ids dedupe
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

## Atlas nudge

`hooks/atlas_nudge.py` is the optional read side, and it stays quiet. At
session start it reads the friction log and prints one line only when earlier
sessions left at least two user corrections since the last nudge, and at most
once a week. Below that, the events wait. Tool failures are counted in the line
but never trigger it. The line gives the counts and asks the agent to ask the
user once, at a natural break, whether a lesson belongs in the Atlas
(`update-atlas`). The read offset and the last nudge time live in
`.superpowers/atlas-nudge.json`. It never fails a session and nothing depends
on it: `wrap-session` offers the same step.

Plain stdout from a `SessionStart` command becomes session context in both
Claude Code and Codex. Claude Code (`~/.claude/settings.json`):

```json
"SessionStart": [
  {"matcher": "startup",
   "hooks": [{"type": "command", "command": "python3 /path/to/superpowers/hooks/atlas_nudge.py", "timeout": 10}]}
]
```

Codex takes the same entry in `~/.codex/hooks.json`, beside the `Stop` recorder.
