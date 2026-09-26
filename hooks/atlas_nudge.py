#!/usr/bin/env python3
"""SessionStart nudge: one line about new friction, so a lesson can reach the Atlas.

Deterministic, no model call. Reads `<project>/.superpowers/friction.jsonl`
(written by friction_recorder.py), counts the events added since the last
nudge, and prints one line only when an earlier session left some. The line
is shown once per batch: the offset of the last line read is kept in
`<project>/.superpowers/atlas-nudge.json`. Always exits 0.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

LOG_NAME = "friction.jsonl"
STATE_NAME = "atlas-nudge.json"


def _read_offset(state: Path) -> int:
    try:
        offset = json.loads(state.read_text(encoding="utf-8")).get("offset", 0)
    except (OSError, ValueError, AttributeError):
        return 0
    return offset if isinstance(offset, int) and offset >= 0 else 0


def _new_events(log: Path, offset: int) -> tuple[list[dict[str, Any]], int]:
    with open(log, "rb") as handle:
        handle.seek(0, 2)
        size = handle.tell()
        if offset > size:  # log was truncated or replaced: start over
            offset = 0
        handle.seek(offset)
        data = handle.read()
    complete = data[: data.rfind(b"\n") + 1]  # never consume a half-written line
    events = []
    for line in complete.splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if isinstance(event, dict):
            events.append(event)
    return events, offset + len(complete)


def nudge(payload: Mapping[str, Any]) -> str | None:
    """The line to show for this session start, or None. Advances the offset."""
    project = Path(payload.get("cwd") or ".").resolve()
    log = project / ".superpowers" / LOG_NAME
    if not log.is_file():
        return None
    state = log.parent / STATE_NAME
    events, offset = _new_events(log, _read_offset(state))
    current = payload.get("session_id")
    earlier = [e for e in events if e.get("session_id") != current]
    if not earlier:
        return None
    state.write_text(json.dumps({"offset": offset}) + "\n", encoding="utf-8")
    corrections = sum(1 for e in earlier if e.get("kind") == "correction")
    failures = sum(1 for e in earlier if e.get("kind") == "tool-failure")
    sessions = len({e.get("session_id") for e in earlier})
    return (
        f"Atlas nudge: earlier sessions in this project logged {corrections} user "
        f"corrections and {failures} tool failures across {sessions} sessions "
        f"(.superpowers/{LOG_NAME}). Do not act on this now. At a natural break, ask "
        "the user once whether a lesson from this work holds beyond this project. "
        "If yes, use the update-atlas skill. If nothing generalizes, drop it."
    )


def main() -> int:
    import sys

    try:
        raw = sys.stdin.read() if not sys.stdin.isatty() else ""
        payload = json.loads(raw) if raw.strip() else {}
        line = nudge(payload if isinstance(payload, dict) else {})
        if line:
            print(line)
    except BaseException as error:  # a hook bug must never surface in the session
        print(f"atlas-nudge: {error!r}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
