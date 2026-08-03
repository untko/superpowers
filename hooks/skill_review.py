#!/usr/bin/env python3
"""Stateless transcript analysis and persisted Stop-hook review decisions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Any, Mapping


_SKILL_PATH = re.compile(r"(?:^|[^A-Za-z0-9_])(skills|references|scripts)[/\\]")
_RETRY_SIGNAL = re.compile(
    r"\b(?:retry|retried|again|correct(?:ed|ion)?|wrong|incorrect|failed|failure|regression)\b",
    re.IGNORECASE,
)
_EXPLICIT_CORRECTION = re.compile(
    r"(?:\bstop\s+(?:doing|using)\b|\bdo\s+not\b|\bdon't\b|\bwrong\b|\bincorrect\b|\bfix\s+(?:it|this|that)\b|\bgot\s+.+?\s+wrong\b)",
    re.IGNORECASE | re.DOTALL,
)


@dataclass(frozen=True)
class TranscriptWindow:
    tool_calls: int
    substantive: bool
    explicit_corrections: tuple[str, ...]
    excerpt: str
    end_offset: int


@dataclass(frozen=True)
class ReviewDecision:
    outcome: str
    reset_tool_watermark: bool


@dataclass(frozen=True)
class ReviewConfig:
    threshold: int
    dry_run: bool


@dataclass(frozen=True)
class ReviewResult:
    outcome: str
    tool_calls: int
    model: str | None


def load_model_map(path: Path) -> dict[str, str | None]:
    """Load a harness-to-model map, accepting only strings or JSON null."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError(f"invalid review model map: {error}") from error
    if not isinstance(data, dict) or "_default" not in data:
        raise ValueError("review model map must be an object with _default")
    for harness, model in data.items():
        if not isinstance(harness, str) or not harness:
            raise ValueError("review model map keys must be non-empty strings")
        if model is not None and (not isinstance(model, str) or not model.strip()):
            raise ValueError(
                f"model for {harness!r} must be a non-empty string or null"
            )
    return data


def resolve_harness(env: Mapping[str, str]) -> str:
    """Resolve the active harness with session-start's branch precedence."""
    if env.get("CURSOR_PLUGIN_ROOT"):
        return "cursor"
    if env.get("CLAUDE_PLUGIN_ROOT") and not env.get("COPILOT_CLI"):
        return "claude-code"
    if env.get("COPILOT_CLI"):
        return "copilot-cli"
    return "_default"


def resolve_model(
    model_map: Mapping[str, str | None], harness: str
) -> str | None:
    """Return a configured model, or None to inherit the running model."""
    return model_map.get(harness, model_map.get("_default"))


def load_review_config(path: Path) -> ReviewConfig:
    """Load the positive threshold and rollout dry-run setting."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError(f"invalid review config: {error}") from error
    threshold = data.get("threshold") if isinstance(data, dict) else None
    dry_run = data.get("dry_run") if isinstance(data, dict) else None
    if isinstance(threshold, bool) or not isinstance(threshold, int) or threshold <= 0:
        raise ValueError("review threshold must be a positive integer")
    if not isinstance(dry_run, bool):
        raise ValueError("review dry_run must be boolean")
    return ReviewConfig(threshold=threshold, dry_run=dry_run)


def _env_config(config: ReviewConfig, env: Mapping[str, str]) -> ReviewConfig:
    threshold = config.threshold
    if env.get("SUPERPOWERS_REVIEW_THRESHOLD"):
        try:
            threshold = int(env["SUPERPOWERS_REVIEW_THRESHOLD"])
        except ValueError as error:
            raise ValueError("SUPERPOWERS_REVIEW_THRESHOLD must be an integer") from error
        if threshold <= 0:
            raise ValueError("SUPERPOWERS_REVIEW_THRESHOLD must be positive")
    dry_run = config.dry_run
    if env.get("SUPERPOWERS_REVIEW_DRY_RUN"):
        value = env["SUPERPOWERS_REVIEW_DRY_RUN"].strip().lower()
        if value not in {"true", "false"}:
            raise ValueError("SUPERPOWERS_REVIEW_DRY_RUN must be true or false")
        dry_run = value == "true"
    return ReviewConfig(threshold=threshold, dry_run=dry_run)


def _iter_tool_blocks(value: Any):
    if isinstance(value, dict):
        if value.get("type") == "tool_use":
            yield value
        for child in value.values():
            yield from _iter_tool_blocks(child)
    elif isinstance(value, list):
        for child in value:
            yield from _iter_tool_blocks(child)


def _text_values(value: Any):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        if value.get("type") in {"text", "input_text"} and isinstance(
            value.get("text"), str
        ):
            yield value["text"]
        else:
            for child in value.values():
                yield from _text_values(child)
    elif isinstance(value, list):
        for child in value:
            yield from _text_values(child)


def _record_role(record: Mapping[str, Any]) -> str:
    message = record.get("message")
    if isinstance(message, dict) and isinstance(message.get("role"), str):
        return message["role"].lower()
    if isinstance(record.get("role"), str):
        return str(record["role"]).lower()
    if isinstance(record.get("type"), str):
        return str(record["type"]).lower()
    return ""


def _message_text(record: Mapping[str, Any]) -> str:
    message = record.get("message")
    if isinstance(message, dict):
        return " ".join(_text_values(message.get("content"))).strip()
    return " ".join(_text_values(record.get("content"))).strip()


def _complete_json_lines(path: Path, start_offset: int) -> tuple[list[dict[str, Any]], int]:
    raw = path.read_bytes()
    if start_offset < 0 or start_offset > len(raw):
        start_offset = 0
    window = raw[start_offset:]
    complete_length = window.rfind(b"\n") + 1
    if complete_length <= 0:
        return [], start_offset
    records: list[dict[str, Any]] = []
    for line in window[:complete_length].splitlines():
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(record, dict):
            records.append(record)
    return records, start_offset + complete_length


def read_transcript_window(
    path: Path, tool_offset: int, correction_offset: int
) -> TranscriptWindow:
    """Read complete JSONL records and classify the unwatermarked window."""
    tool_records, end_offset = _complete_json_lines(path, tool_offset)
    correction_records, _ = _complete_json_lines(path, correction_offset)
    tool_blocks = [block for record in tool_records for block in _iter_tool_blocks(record)]
    serialized_blocks = [json.dumps(block, sort_keys=True) for block in tool_blocks]
    substantive = any(_SKILL_PATH.search(block) for block in serialized_blocks)
    record_text = "\n".join(
        text for record in tool_records for text in _text_values(record)
    )
    substantive = substantive or bool(_RETRY_SIGNAL.search(record_text))

    corrections: list[str] = []
    for record in correction_records:
        if _record_role(record) not in {"user", "human"}:
            continue
        text = _message_text(record)
        if text and _EXPLICIT_CORRECTION.search(text):
            corrections.append(text)

    excerpt_parts = []
    for record in tool_records:
        role = _record_role(record)
        if role in {"user", "human", "assistant"}:
            text = " ".join(_text_values(record)).strip()
            if text:
                excerpt_parts.append(f"{role}: {text}")
        for block in _iter_tool_blocks(record):
            excerpt_parts.append(
                "tool: "
                + json.dumps(
                    {
                        "name": block.get("name"),
                        "input": block.get("input"),
                    },
                    sort_keys=True,
                )
            )
    excerpt = "\n".join(excerpt_parts)[-12000:]
    return TranscriptWindow(
        tool_calls=len(tool_blocks),
        substantive=substantive,
        explicit_corrections=tuple(corrections),
        excerpt=excerpt,
        end_offset=end_offset,
    )


def decide_review(
    *, tool_calls: int, threshold: int, substantive: bool, explicit_correction: bool
) -> ReviewDecision:
    """Return the observable action for one Stop-hook transcript window."""
    if tool_calls >= threshold and substantive:
        return ReviewDecision("review", True)
    if explicit_correction:
        return ReviewDecision("review-explicit-correction", False)
    if tool_calls >= threshold:
        return ReviewDecision("skip-no-substance", False)
    return ReviewDecision("skip-below-threshold", False)


def _project_root(payload: Mapping[str, object]) -> Path:
    value = payload.get("cwd") or os.getcwd()
    root = Path(str(value)).expanduser().resolve(strict=True)
    if not root.is_dir():
        raise ValueError("Stop hook cwd must be a directory")
    return root


def _runtime_directory(project_root: Path) -> Path:
    runtime = project_root / ".superpowers"
    if runtime.is_symlink():
        raise ValueError(".superpowers must not be a symlink")
    runtime.mkdir(exist_ok=True)
    if not runtime.is_dir():
        raise ValueError(".superpowers must be a directory")
    return runtime


def _empty_state(transcript_path: Path) -> dict[str, object]:
    return {
        "transcript_path": str(transcript_path),
        "tool_watermark": 0,
        "correction_watermark": 0,
    }


def _load_state(path: Path, transcript_path: Path) -> dict[str, object]:
    if not path.exists():
        return _empty_state(transcript_path)
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError(f"invalid review state: {error}") from error
    if not isinstance(state, dict):
        raise ValueError("review state must be an object")
    if state.get("transcript_path") != str(transcript_path):
        return _empty_state(transcript_path)
    tool_watermark = state.get("tool_watermark", 0)
    correction_watermark = state.get("correction_watermark", 0)
    if (
        isinstance(tool_watermark, bool)
        or not isinstance(tool_watermark, int)
        or tool_watermark < 0
        or isinstance(correction_watermark, bool)
        or not isinstance(correction_watermark, int)
        or correction_watermark < 0
    ):
        raise ValueError("review watermarks must be non-negative integers")
    size = transcript_path.stat().st_size
    if tool_watermark > size or correction_watermark > size:
        return _empty_state(transcript_path)
    return {
        "transcript_path": str(transcript_path),
        "tool_watermark": tool_watermark,
        "correction_watermark": correction_watermark,
    }


def _save_state(path: Path, state: Mapping[str, object]) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def _append_log(
    path: Path, *, timestamp: str, tool_calls: int, model: str | None, outcome: str
) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(
            f"- {timestamp} | tool_calls={tool_calls} | model={model or 'inherit'} | outcome={outcome}\n"
        )


def _build_prompt(
    *,
    plugin_root: Path,
    project_root: Path,
    reason: str,
    window: TranscriptWindow,
) -> str:
    corrections = "\n".join(f"- {text}" for text in window.explicit_corrections)
    correction_block = corrections or "(none detected by the hook)"
    writer = plugin_root / "skills/evolving-skills/scripts/new_observation.py"
    return f"""You are the background skill-evolution reviewer for one repository.

Repository: {project_root}
Trigger: {reason}
Existing observation writer: {writer}

Review the sanitized current transcript window below. If and only if it contains
a concrete, reusable observation about a skill's behavior, write at most one
valid superpowers-observation/v1 note under this repository's pending queue by
invoking new_observation.py. Preserve the existing diagnosis, candidate.scope,
and candidate.target vocabulary. Use unknown when evidence is insufficient.
Keep the observation sanitized: do not copy secrets, raw transcripts, customer
data, or unnecessary project paths into the note. If there is no such
observation, do not write anything. Do not edit skills, adapters, proposals,
or any file other than the observation produced by new_observation.py.

Explicit user-correction candidates:
{correction_block}

Current window:
{window.excerpt or '(no textual/tool excerpt)'}
"""


def _run_reviewer(
    *,
    prompt: str,
    project_root: Path,
    harness: str,
    model: str | None,
    env: Mapping[str, str],
    reason: str,
) -> int:
    command = ["claude", "-p"]
    if model:
        command.extend(["--model", model])
    command.append(prompt)
    child_env = dict(env)
    child_env["SUPERPOWERS_PROJECT_ROOT"] = str(project_root)
    child_env["SUPERPOWERS_HARNESS"] = harness
    if model:
        child_env["SUPERPOWERS_MODEL"] = model
    try:
        completed = subprocess.run(
            command,
            cwd=project_root,
            env=child_env,
            check=False,
            timeout=300,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except (OSError, subprocess.SubprocessError):
        return 1
    return completed.returncode


def process_event(
    payload: Mapping[str, object],
    *,
    plugin_root: Path,
    env: Mapping[str, str],
    run_reviewer=None,
    now=None,
) -> ReviewResult:
    """Process one Stop payload without ever blocking the host harness."""
    project_root = _project_root(payload)
    runtime = _runtime_directory(project_root)
    timestamp = (
        now or (lambda: datetime.now(timezone.utc).replace(microsecond=0).isoformat())
    )()
    config = _env_config(
        load_review_config(plugin_root / "hooks/review-config.json"), env
    )
    model_map = load_model_map(plugin_root / "hooks/review-model-map.json")
    harness = resolve_harness(env)
    model = resolve_model(model_map, harness)
    transcript_value = payload.get("transcript_path")
    if not transcript_value:
        outcome = "skip-missing-transcript"
        _append_log(
            runtime / "review-log.md",
            timestamp=timestamp,
            tool_calls=0,
            model=model,
            outcome=outcome,
        )
        return ReviewResult(outcome=outcome, tool_calls=0, model=model)

    transcript_path = Path(str(transcript_value)).expanduser()
    if not transcript_path.is_absolute():
        transcript_path = project_root / transcript_path
    transcript_path = transcript_path.resolve(strict=True)
    state_path = runtime / "review-state.json"
    state = _load_state(state_path, transcript_path)
    window = read_transcript_window(
        transcript_path,
        int(state["tool_watermark"]),
        int(state["correction_watermark"]),
    )
    decision = decide_review(
        tool_calls=window.tool_calls,
        threshold=config.threshold,
        substantive=window.substantive,
        explicit_correction=bool(window.explicit_corrections),
    )

    should_save_state = decision.outcome != "skip-below-threshold" or state_path.exists()
    outcome = decision.outcome
    if decision.outcome in {"review", "review-explicit-correction"}:
        reason = "threshold" if decision.reset_tool_watermark else "explicit-correction"
        prompt = _build_prompt(
            plugin_root=plugin_root,
            project_root=project_root,
            reason=reason,
            window=window,
        )
        if config.dry_run:
            outcome = (
                "dry-run-review"
                if decision.reset_tool_watermark
                else "dry-run-explicit-correction"
            )
        else:
            runner = run_reviewer or _run_reviewer
            return_code = runner(
                prompt=prompt,
                project_root=project_root,
                harness=harness,
                model=model,
                env=env,
                reason=reason,
            )
            if return_code != 0:
                outcome = "review-failed"
        state["tool_watermark"] = (
            window.end_offset
            if decision.reset_tool_watermark
            else state["tool_watermark"]
        )
        state["correction_watermark"] = window.end_offset
        should_save_state = True
    elif decision.outcome == "skip-no-substance":
        state["correction_watermark"] = window.end_offset
        should_save_state = True

    if should_save_state:
        _save_state(state_path, state)
    _append_log(
        runtime / "review-log.md",
        timestamp=timestamp,
        tool_calls=window.tool_calls,
        model=model,
        outcome=outcome,
    )
    return ReviewResult(outcome=outcome, tool_calls=window.tool_calls, model=model)


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Run one skill review Stop hook")
    parser.add_argument("--plugin-root", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("Stop payload must be a JSON object")
        process_event(payload, plugin_root=args.plugin_root.resolve(), env=os.environ)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        sys.stderr.write(f"skill-review: {error}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
