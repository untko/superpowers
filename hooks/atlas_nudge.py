#!/usr/bin/env python3
"""SessionStart nudge: one line about new friction, so a lesson can reach the Atlas.

Deterministic, no model call. Reads the project's `.superpowers/friction.jsonl`
(written by friction_recorder.py; in the main checkout, even from a worktree)
and counts the events added since the last nudge. It stays quiet: it prints one
line only when earlier sessions left at least MIN_CORRECTIONS user corrections,
and at most once per COOLDOWN. Below that, the events wait for a later start.
Tool failures are counted in the line but never trigger it. The offset of the
last line read and the time of the last nudge are kept in
`.superpowers/atlas-nudge.json`. Always exits 0.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

if __package__:  # imported as hooks.atlas_nudge
    from . import project_store
else:  # hook entry point: python3 hooks/atlas_nudge.py
    import project_store

LOG_NAME = "friction.jsonl"
STATE_NAME = "atlas-nudge.json"
MIN_CORRECTIONS = 2
COOLDOWN = timedelta(days=7)


def _read_state(state: Path) -> tuple[int, datetime | None]:
    """The offset of the last line read, and when the last nudge was shown."""
    try:
        data = json.loads(state.read_text(encoding="utf-8"))
        offset = data.get("offset", 0)
        last = data.get("nudged_at")
    except (OSError, ValueError, AttributeError):
        return 0, None
    offset = offset if isinstance(offset, int) and offset >= 0 else 0
    try:
        nudged = datetime.fromisoformat(last) if isinstance(last, str) else None
    except ValueError:
        nudged = None
    return offset, nudged


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


def nudge(payload: Mapping[str, Any], now: datetime | None = None) -> str | None:
    """The line to show for this session start, or None. Advances the offset only when shown."""
    log = project_store.store_dir(payload.get("cwd")) / LOG_NAME
    if not log.is_file():
        return None
    now = now or datetime.now(timezone.utc)
    state = log.parent / STATE_NAME
    start, nudged = _read_state(state)
    if nudged is not None and now - nudged < COOLDOWN:
        return None
    events, offset = _new_events(log, start)
    current = payload.get("session_id")
    earlier = [e for e in events if e.get("session_id") != current]
    corrections = sum(1 for e in earlier if e.get("kind") == "correction")
    if corrections < MIN_CORRECTIONS:
        return None
    state.write_text(json.dumps({"offset": offset, "nudged_at": now.isoformat()}) + "\n",
                     encoding="utf-8")
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
