"""Harness transcript normalizers: any CLI's transcript in, Claude Code records out.

The recorder reads one shape whatever the harness, so an adapter only translates.
The interchange format is the subset of Claude Code transcript records the recorder
already understands:

    human prompt   {"type": "user", "origin": {"kind": "human"}, "promptId": <id or None>,
                    "message": {"content": "<text>"}}
    skill load     {"type": "assistant", "message": {"content": [{"type": "tool_use",
                    "name": "Read", "input": {"file_path": "<abs path>/SKILL.md"}}]}}
                   the same, with "name": "Skill" and "input": {"skill": <name>}
    tool failure   {"type": "user", "message": {"content": [{"type": "tool_result",
                    "tool_use_id": <id>, "is_error": true, "content": "<error text>"}]}}

Per harness:

    claude / claude-code  Claude Code's own transcript JSONL, passed through as records.
    codex                 a rollout JSONL, lines of {"timestamp", "type", "payload"}.
    opencode              a JSON array of {"info": {...}, "parts": [...]}.

`normalize` never raises: an unknown harness, a missing file, or a file it cannot
parse all give [].
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Callable, Iterator

# An absolute path ending in a skill file, as it appears in a codex tool call.
_ABS_SKILL_PATH = re.compile(r"/[^\s\"'`<>|()\[\],;]*SKILL\.md")


def normalize(harness: str, path: str | None) -> list[dict]:
    """The transcript at `path` as interchange records, in transcript order."""
    reader = _READERS.get(_key(harness))
    if reader is None or not path:
        return []
    try:
        return reader(Path(path))
    except (OSError, ValueError, TypeError):
        return []


def _key(harness: Any) -> str:
    return harness.strip().lower() if isinstance(harness, str) else ""


# --- Claude Code ---------------------------------------------------------------


def _claude(path: Path) -> list[dict]:
    return _dicts(_jsonl(path))


def _jsonl(path: Path) -> Iterator[Any]:
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


# --- Codex ----------------------------------------------------------------------


def _codex(path: Path) -> list[dict]:
    records = []
    for line in _dicts(_jsonl(path)):
        payload = line.get("payload")
        if line.get("type") == "event_msg":
            records.extend(_codex_event(payload if isinstance(payload, dict) else {}))
        elif line.get("type") == "response_item":
            records.extend(_codex_call(payload if isinstance(payload, dict) else {}))
    return records


def _codex_event(payload: dict) -> list[dict]:
    kind = payload.get("type")
    if kind == "user_message":
        return _prompt(payload.get("message"), payload.get("id"))
    if kind == "item_completed":
        return _codex_failure(payload.get("item"))
    return []


def _codex_call(payload: dict) -> list[dict]:
    # Codex replays its instructions as response_item user messages, and a user
    # message there may name every available skill: only a tool call loads one.
    if payload.get("type") not in ("custom_tool_call", "function_call"):
        return []
    records = []
    for field in ("input", "arguments"):
        text = payload.get(field)
        if isinstance(text, str):
            records.extend(_read_load(m.group(0)) for m in _ABS_SKILL_PATH.finditer(text))
    return records


def _codex_failure(item: Any) -> list[dict]:
    if not isinstance(item, dict) or item.get("type") != "CommandExecution":
        return []
    if item.get("status") != "failed":
        return []
    body = next(
        (
            item[field]
            for field in ("stderr", "aggregated_output")
            if isinstance(item.get(field), str) and item[field].strip()
        ),
        "",
    )
    return [_failure(item.get("id"), f"exit {item.get('exit_code')}: {body}")]


# --- OpenCode -------------------------------------------------------------------


def _opencode(path: Path) -> list[dict]:
    messages = json.loads(path.read_text(encoding="utf-8"))
    records = []
    for message in messages if isinstance(messages, list) else []:
        if not isinstance(message, dict):
            continue
        info, parts = message.get("info"), message.get("parts")
        if not isinstance(info, dict) or not isinstance(parts, list):
            continue
        if info.get("role") == "user":
            records.extend(_prompt(_opencode_text(parts), info.get("id")))
        for part in parts:
            if isinstance(part, dict) and part.get("type") == "tool":
                records.extend(_opencode_tool(part))
    return records


def _opencode_text(parts: list[Any]) -> str:
    """What the user typed: their text parts, without the harness's own."""
    return "\n".join(
        part["text"]
        for part in parts
        if isinstance(part, dict)
        and part.get("type") == "text"
        and not part.get("synthetic")
        and isinstance(part.get("text"), str)
    )


def _opencode_tool(part: dict) -> list[dict]:
    state = part.get("state")
    state = state if isinstance(state, dict) else {}
    tool_input = state.get("input")
    tool_input = tool_input if isinstance(tool_input, dict) else {}
    records = []
    if part.get("tool") == "skill" and isinstance(tool_input.get("name"), str):
        records.append(_skill_load(tool_input["name"]))
    elif part.get("tool") == "read":
        file_path = tool_input.get("filePath")
        if isinstance(file_path, str) and file_path.endswith("SKILL.md"):
            records.append(_read_load(file_path))
    metadata = state.get("metadata")
    exit_code = metadata.get("exit") if isinstance(metadata, dict) else None
    if state.get("status") == "error":
        records.append(_failure(part.get("callID"), _text(state.get("error"))))
    elif isinstance(exit_code, int) and exit_code != 0:
        # opencode reports a failed bash command as completed with a non-zero exit.
        output = _text(metadata.get("output")) or _text(state.get("output"))
        records.append(_failure(part.get("callID"), f"exit {exit_code}: {output}"))
    return records


# --- Interchange records ---------------------------------------------------------


def _prompt(text: Any, prompt_id: Any) -> list[dict]:
    if not isinstance(text, str) or not text.strip():
        return []
    return [
        {
            "type": "user",
            "origin": {"kind": "human"},
            "promptId": _id(prompt_id),
            "message": {"content": text},
        }
    ]


def _read_load(file_path: str) -> dict:
    return _tool_use("Read", {"file_path": file_path})


def _skill_load(name: str) -> dict:
    return _tool_use("Skill", {"skill": name})


def _tool_use(name: str, tool_input: dict) -> dict:
    return {
        "type": "assistant",
        "message": {"content": [{"type": "tool_use", "name": name, "input": tool_input}]},
    }


def _failure(tool_use_id: Any, content: str) -> dict:
    return {
        "type": "user",
        "message": {
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": _id(tool_use_id),
                    "is_error": True,
                    "content": content,
                }
            ]
        },
    }


def _dicts(records: Iterator[Any]) -> list[dict]:
    return [record for record in records if isinstance(record, dict)]


def _id(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _text(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value) if value is not None else ""


_READERS: dict[str, Callable[[Path], list[dict]]] = {
    "claude": _claude,
    "claude-code": _claude,
    "claude_code": _claude,
    "codex": _codex,
    "opencode": _opencode,
}
