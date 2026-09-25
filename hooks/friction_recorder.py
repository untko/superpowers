#!/usr/bin/env python3
"""Deterministic friction recorder: hook payload in, JSON lines out, no model call."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Mapping

EXCERPT_LIMIT = 500
LOG_NAME = "friction.jsonl"

_CORRECTION = re.compile(
    r"(?:\bstop\s+(?:doing|using)\b|\bdo\s+not\b|\bdon't\b|\bwrong\b|\bincorrect\b"
    r"|\bfix\s+(?:it|this|that)\b|\bgot\s+.+?\s+wrong\b)",
    re.IGNORECASE | re.DOTALL,
)


def _iter_tool_blocks(value: Any) -> Iterator[dict[str, Any]]:
    if isinstance(value, dict):
        if value.get("type") == "tool_use":
            yield value
        for child in value.values():
            yield from _iter_tool_blocks(child)
    elif isinstance(value, list):
        for child in value:
            yield from _iter_tool_blocks(child)


def _read_transcript(path: str | None) -> list[Any]:
    if not path:
        return []
    records = []
    try:
        with open(path, encoding="utf-8") as handle:
            for line in handle:
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except OSError:
        return []
    return records


_PROJECT_SKILL_DIRS = (".claude/skills", ".agents/skills")
# Claude Code injects this line when a skill loads, by Skill tool or slash command.
_BASE_DIRECTORY = re.compile(r"^Base directory for this skill: (.+)$", re.MULTILINE)


def _source(skill_dir: Path, library_root: Path, project: Path) -> str | None:
    """Tag a skill directory global (canonical library) or local (this project)."""
    try:
        resolved = skill_dir.resolve()
    except OSError:
        return None
    if resolved.is_relative_to(library_root.resolve()):
        return "global"
    if resolved.is_relative_to(project):
        return "local"
    return None


def _named_skill_dir(name: str, library_root: Path, project: Path) -> Path | None:
    for candidate in (library_root / name, *(project / d / name for d in _PROJECT_SKILL_DIRS)):
        if (candidate / "SKILL.md").is_file():
            return candidate
    return None


def _skill_dirs(record: Any, library_root: Path, project: Path) -> Iterator[Path]:
    if isinstance(record, dict) and record.get("isMeta"):
        for text in _texts(record.get("message")):
            for match in _BASE_DIRECTORY.finditer(text):
                yield Path(match.group(1).strip())
    for block in _iter_tool_blocks(record):
        tool_input = block.get("input") or {}
        if not isinstance(tool_input, dict):
            continue
        if block.get("name") == "Skill" and isinstance(tool_input.get("skill"), str):
            skill_dir = _named_skill_dir(tool_input["skill"].split(":")[-1], library_root, project)
            if skill_dir is not None:
                yield skill_dir
        elif isinstance(tool_input.get("file_path"), str):
            path = Path(tool_input["file_path"])
            if path.name == "SKILL.md":
                yield path.parent


def _texts(message: Any) -> Iterator[str]:
    content = message.get("content") if isinstance(message, dict) else None
    if isinstance(content, str):
        yield content
    elif isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and isinstance(block.get("text"), str):
                yield block["text"]


def loaded_skills(records: list[Any], library_root: Path, project: Path) -> list[dict[str, str]]:
    """Skills loaded in the session (Skill tool, slash command, or SKILL.md read), first-load order."""
    skills: dict[str, dict[str, str]] = {}
    for record in records:
        for skill_dir in _skill_dirs(record, library_root, project):
            source = _source(skill_dir, library_root, project)
            name = skill_dir.resolve().name
            if source and name not in skills:
                skills[name] = {"name": name, "source": source}
    return list(skills.values())


def _excerpt(value: Any) -> str:
    text = value if isinstance(value, str) else json.dumps(value)
    return text[:EXCERPT_LIMIT]


def _event_id(session: Any, kind: str, key: Any, text: str) -> str:
    if not isinstance(key, str) or not key:
        key = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
    return f"{session}:{kind}:{key}"


def _is_correction(text: Any) -> bool:
    return isinstance(text, str) and bool(_CORRECTION.search(text))


def _human_prompt(record: Any) -> str | None:
    """Text of a prompt the user typed; None for tool results and injected context."""
    if not isinstance(record, dict) or record.get("type") != "user":
        return None
    if record.get("isMeta") or record.get("isCompactSummary"):
        return None
    origin = record.get("origin")
    if isinstance(origin, dict) and origin.get("kind") != "human":
        return None
    content = (record.get("message") or {}).get("content")
    if isinstance(content, list):
        if any(isinstance(b, dict) and b.get("type") != "text" for b in content):
            return None
        content = "\n".join(b.get("text", "") for b in content if isinstance(b, dict))
    if not isinstance(content, str) or content.lstrip().startswith("<"):
        return None
    return content


def _swept_friction(records: list[Any], session: Any) -> list[tuple[str, str, str]]:
    friction = []
    for record in records:
        prompt = _human_prompt(record)
        if prompt is not None:
            if _is_correction(prompt):
                key = record.get("promptId")
                friction.append((_event_id(session, "correction", key, prompt), "correction", _excerpt(prompt)))
            continue
        if not isinstance(record, dict) or record.get("type") != "user":
            continue
        content = (record.get("message") or {}).get("content")
        for block in content if isinstance(content, list) else []:
            if isinstance(block, dict) and block.get("type") == "tool_result" and block.get("is_error"):
                error = _excerpt(block.get("content") or "")
                key = block.get("tool_use_id")
                friction.append((_event_id(session, "tool-failure", key, error), "tool-failure", error))
    return friction


def _friction(payload: Mapping[str, Any], records: list[Any]) -> list[tuple[str, str, str]]:
    """Return (id, kind, excerpt) triples for the friction this payload reports."""
    event = payload.get("hook_event_name")
    session = payload.get("session_id")
    if event == "PostToolUseFailure":
        error = _excerpt(payload.get("error") or "")
        key = payload.get("tool_use_id")
        return [(_event_id(session, "tool-failure", key, error), "tool-failure", error)]
    if event == "UserPromptSubmit":
        prompt = payload.get("prompt")
        if _is_correction(prompt):
            key = payload.get("prompt_id")
            return [(_event_id(session, "correction", key, prompt), "correction", _excerpt(prompt))]
    if event == "Stop":
        return _swept_friction(records, session)
    return []


def _logged_ids(log: Path) -> set[str]:
    ids = set()
    try:
        with open(log, encoding="utf-8") as handle:
            for line in handle:
                try:
                    ids.add(json.loads(line).get("id"))
                except (json.JSONDecodeError, AttributeError):
                    continue
    except FileNotFoundError:
        pass
    return ids


def record(
    payload: Mapping[str, Any],
    *,
    library_root: Path,
    harness: str,
    now: str | None = None,
) -> list[dict[str, Any]]:
    """Append this payload's new friction events to the project log and return them."""
    records = _read_transcript(payload.get("transcript_path"))
    friction = _friction(payload, records)
    if not friction:
        return []
    project = Path(payload.get("cwd") or ".").resolve()
    log = project / ".superpowers" / LOG_NAME
    seen = _logged_ids(log)
    skills = loaded_skills(records, library_root, project)
    timestamp = now or datetime.now(timezone.utc).isoformat()
    events = []
    for event_id, kind, excerpt in friction:
        if event_id in seen:
            continue
        seen.add(event_id)
        events.append(
            {
                "id": event_id,
                "kind": kind,
                "timestamp": timestamp,
                "harness": harness,
                "session_id": payload.get("session_id"),
                "skills": skills,
                "excerpt": excerpt,
            }
        )
    if events:
        log.parent.mkdir(exist_ok=True)
        with open(log, "a", encoding="utf-8") as handle:
            handle.writelines(json.dumps(event) + "\n" for event in events)
    return events


def main(argv: list[str] | None = None) -> int:
    """Hook entry point: never blocks the session, never writes to stdout."""
    import argparse
    import sys

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--harness", required=True)
    parser.add_argument(
        "--library-root",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "skills",
    )
    try:
        args = parser.parse_args(argv)
        payload = json.loads(sys.stdin.read())
        if isinstance(payload, dict):
            record(payload, library_root=args.library_root, harness=args.harness)
    except BaseException as error:  # a hook bug must never surface in the session
        print(f"friction-recorder: {error!r}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
