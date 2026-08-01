#!/usr/bin/env python3
"""Generate one valid repository-local observation from minimal prose input."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys

from adapter_protocol import (
    OBSERVATION_SCHEMA,
    discover_adapter,
    validate_observation,
)
from parse_observations import archive_observation, ensure_observation_store

_SLUG = re.compile(r"[^a-z0-9]+")
_UNKNOWN = "unknown"
_RUNTIME_KEYS = (
    "provider",
    "model",
    "reasoning-effort",
    "harness",
    "harness-version",
    "interface",
)

_OPTIONAL_RUNTIME_KEYS = ("os", "workspace", "session-id")


def _scalar(value: object) -> str:
    """Render one value inside the frontmatter parser's accepted subset."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    text = " ".join(str(value).split())
    return repr(text)


def render_frontmatter(metadata: dict[str, object]) -> str:
    """Serialize nested metadata as indented single-line scalars."""
    lines = ["---"]

    def emit(mapping: dict[str, object], indent: int) -> None:
        for key, value in mapping.items():
            pad = "  " * indent
            if isinstance(value, dict):
                lines.append(f"{pad}{key}:")
                emit(value, indent + 1)
            else:
                lines.append(f"{pad}{key}: {_scalar(value)}")

    emit(metadata, 0)
    lines.append("---")
    return "\n".join(lines) + "\n"


def build_metadata(
    *,
    skill: str,
    phase: str,
    expected: str,
    actual: str,
    evidence: str,
    diagnosis: str,
    scope: str,
    target: str,
    runtime: dict[str, str],
    provenance: dict[str, object],
    adapter: dict[str, object] | None,
    observed: str | None = None,
) -> dict[str, object]:
    """Assemble current-schema metadata, defaulting every unknown to 'unknown'."""
    global_block: dict[str, object] = {
        "name": skill,
        "contract": 1,
        "plugin-version": str(provenance.get("plugin-version") or _UNKNOWN),
        "git-commit": str(provenance.get("git-commit") or _UNKNOWN),
    }
    if "dirty" in provenance:
        global_block["dirty"] = bool(provenance["dirty"])
    runtime_block = {key: runtime.get(key) or _UNKNOWN for key in _RUNTIME_KEYS}
    for key in _OPTIONAL_RUNTIME_KEYS:
        if runtime.get(key):
            runtime_block[key] = runtime[key]
    observation_block: dict[str, object] = {
        "phase": phase,
        "expected": expected,
        "actual": actual,
        "evidence": evidence,
        "diagnosis": diagnosis,
    }
    if observed:
        observation_block["observed"] = observed
    return {
        "schema": OBSERVATION_SCHEMA,
        "runtime": runtime_block,
        "skills": {
            "global": global_block,
            "adapter": {
                "path": str((adapter or {}).get("path") or _UNKNOWN),
                "version": str((adapter or {}).get("version") or _UNKNOWN),
                "git-commit": str((adapter or {}).get("git-commit") or _UNKNOWN),
            },
        },
        "observation": observation_block,
        "candidate": {"scope": scope, "target": target, "status": "observed"},
    }


def _filename(metadata: dict[str, object], now: str) -> str:
    """Build a sortable, slugged filename from the observation summary."""
    summary = str(metadata["observation"]["actual"])[:60].lower()
    slug = _SLUG.sub("-", summary).strip("-") or "observation"
    return f"{now}-{slug}.md"


def write_observation(
    project_root: Path,
    metadata: dict[str, object],
    body: str,
    *,
    archive_now: bool = False,
    now: str | None = None,
) -> Path:
    """Validate, write into pending/, and optionally archive in one guarded move."""
    errors = validate_observation(metadata)
    if errors:
        raise ValueError("; ".join(errors))
    from datetime import datetime

    stamp = now or datetime.now().strftime("%Y-%m-%d-%H%M%S")
    store = ensure_observation_store(project_root)
    path = store["pending"] / _filename(metadata, stamp)
    if path.exists() or path.is_symlink():
        raise ValueError(f"observation already exists: {path}")
    path.write_text(
        render_frontmatter(metadata) + body.strip() + "\n", encoding="utf-8"
    )
    if archive_now:
        return Path(archive_observation(path, store["archived"]))
    return path


def _git(skill_root: Path, *args: str) -> str | None:
    """Return trimmed git output, or None when git or the repository is absent."""
    try:
        result = subprocess.run(
            ["git", "-C", str(skill_root), *args],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def _plugin_provenance(skill_root: Path) -> dict[str, object]:
    """Derive plugin version, commit, and dirty state from the installed skill."""
    provenance: dict[str, object] = {}
    for name in ("plugin.json", "package.json"):
        candidate = skill_root / name
        if candidate.is_file():
            try:
                provenance["plugin-version"] = json.loads(
                    candidate.read_text(encoding="utf-8")
                ).get("version")
            except (OSError, ValueError):
                provenance["plugin-version"] = None
            if provenance.get("plugin-version"):
                break
    commit = _git(skill_root, "rev-parse", "--short", "HEAD")
    if commit:
        provenance["git-commit"] = commit
        status = _git(skill_root, "status", "--porcelain")
        # `dirty` is optional by design; an unverified state call must leave
        # it absent rather than recording a false "false".
        if status is not None:
            provenance["dirty"] = bool(status)
    return provenance


def _adapter_provenance(project_root: Path, skill: str) -> dict[str, object] | None:
    """Return adapter provenance when a valid adapter is discoverable."""
    try:
        result = discover_adapter(project_root, skill, {1})
    except (OSError, ValueError):
        return None
    if not isinstance(result, dict) or result.get("status") != "valid":
        return None
    metadata = result.get("metadata") or {}
    return {
        "path": result.get("path"),
        "version": metadata.get("adapter-version"),
        "git-commit": _UNKNOWN,
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Write one valid repository-local observation."
    )
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--skill", required=True)
    parser.add_argument("--phase", required=True)
    parser.add_argument("--expected", required=True)
    parser.add_argument("--actual", required=True)
    parser.add_argument("--evidence", required=True)
    parser.add_argument("--diagnosis", default="uncertain")
    parser.add_argument("--scope", default="uncertain")
    parser.add_argument("--target", default="unknown")
    parser.add_argument("--body", default="")
    parser.add_argument("--archive-now", action="store_true")
    for key in _RUNTIME_KEYS:
        parser.add_argument(f"--{key}", default=None)
    for key in _OPTIONAL_RUNTIME_KEYS:
        parser.add_argument(f"--{key}", default=None)
    parser.add_argument("--observed", default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Generate one observation and print its path."""
    args = _build_parser().parse_args(argv)
    skill_root = Path(__file__).resolve().parents[3]
    runtime = {key: getattr(args, key.replace("-", "_")) for key in _RUNTIME_KEYS}
    runtime["harness"] = runtime["harness"] or os.environ.get("SUPERPOWERS_HARNESS")
    runtime["model"] = runtime["model"] or os.environ.get("SUPERPOWERS_MODEL")
    for key in _OPTIONAL_RUNTIME_KEYS:
        value = getattr(args, key.replace("-", "_"))
        if value:
            runtime[key] = value
    if "os" not in runtime:
        runtime["os"] = sys.platform
    metadata = build_metadata(
        skill=args.skill,
        phase=args.phase,
        expected=args.expected,
        actual=args.actual,
        evidence=args.evidence,
        diagnosis=args.diagnosis,
        scope=args.scope,
        target=args.target,
        runtime=runtime,
        provenance=_plugin_provenance(skill_root),
        adapter=_adapter_provenance(args.project_root, args.skill),
        observed=args.observed,
    )
    try:
        path = write_observation(
            args.project_root,
            metadata,
            args.body or args.evidence,
            archive_now=args.archive_now,
        )
    except (OSError, ValueError) as error:
        sys.stderr.write(f"Error: {error}\n")
        return 2
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
