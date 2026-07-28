#!/usr/bin/env python3
"""Discover, validate, and archive local skill-evolution observations."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import sys

from adapter_protocol import parse_frontmatter, validate_observation


def observation_root(project_root: Path) -> Path:
    """Return the repository-local root for operational observations."""
    return Path(project_root) / ".superpowers" / "observations"


def ensure_observation_store(project_root: Path) -> dict[str, Path]:
    """Create the ignored lifecycle directories for one repository."""
    root = observation_root(project_root)
    store = {
        "root": root,
        "pending": root / "pending",
        "proposed": root / "proposed",
        "archived": root / "archived",
    }
    for directory in store.values():
        directory.mkdir(parents=True, exist_ok=True)

    ignore_file = root / ".gitignore"
    if not ignore_file.exists():
        ignore_file.write_text("*\n", encoding="utf-8")
    return store


def _legacy_observation(path: Path) -> dict[str, object]:
    frontmatter, body = parse_frontmatter(path.read_text(encoding="utf-8"))
    return {
        "filepath": str(path),
        "filename": path.name,
        "timestamp": frontmatter.get("timestamp", ""),
        "skill": frontmatter.get("skill", "unknown"),
        "phase": frontmatter.get("phase", "unknown"),
        "status": frontmatter.get("status", "pending_distillation"),
        "content": body.strip(),
        "frontmatter": frontmatter,
    }


def _repository_observation(path: Path) -> dict[str, object] | None:
    frontmatter, body = parse_frontmatter(path.read_text(encoding="utf-8"))
    errors = validate_observation(frontmatter)
    if errors:
        sys.stderr.write(
            f"Warning: Ignoring invalid observation {path.name}: {'; '.join(errors)}\n"
        )
        return None

    runtime = frontmatter["runtime"]
    skills = frontmatter["skills"]
    observation = frontmatter["observation"]
    candidate = frontmatter["candidate"]
    return {
        "filepath": str(path),
        "filename": path.name,
        "timestamp": "",
        "skill": skills["global"]["name"],
        "phase": observation["phase"],
        "status": candidate["status"],
        "content": body.strip(),
        "frontmatter": frontmatter,
        "runtime": runtime,
        "skills": skills,
        "observation": observation,
        "candidate": candidate,
    }


def list_observations(
    obs_directory: Path | str, *, repository_local: bool | None = None
) -> list[dict[str, object]]:
    """List legacy notes or valid v1 notes in a repository-local pending queue."""
    directory = Path(obs_directory)
    if repository_local is None:
        repository_local = (directory / "pending").is_dir() or (
            directory.name == "pending"
            and (directory.parent / "proposed").is_dir()
            and (directory.parent / "archived").is_dir()
        )
    if repository_local:
        source_directory = directory if directory.name == "pending" else directory / "pending"
    else:
        source_directory = directory
    if not source_directory.is_dir():
        return []

    observations: list[dict[str, object]] = []
    for path in sorted(source_directory.iterdir()):
        if path.suffix != ".md" or path.name == "README.md" or not path.is_file():
            continue
        try:
            observation = (
                _repository_observation(path)
                if repository_local
                else _legacy_observation(path)
            )
            if observation is not None:
                observations.append(observation)
        except (OSError, UnicodeError, ValueError) as error:
            sys.stderr.write(f"Warning: Failed to read {path.name}: {error}\n")
    return observations


def _require_pending_source(source: Path, archive_directory: Path) -> Path:
    """Resolve a v1 source and reject paths outside its sibling pending queue."""
    pending_directory = (archive_directory.parent / "pending").resolve(strict=True)
    resolved_source = source.resolve(strict=True)
    try:
        resolved_source.relative_to(pending_directory)
    except ValueError as error:
        raise ValueError("observation source must resolve inside pending/") from error
    return resolved_source


def _require_contained_archive_directory(archive_directory: Path) -> None:
    """Resolve the archive directory without allowing a symlink escape."""
    archive_directory.mkdir(parents=True, exist_ok=True)
    observation_root = archive_directory.parent.resolve(strict=True)
    resolved_archive = archive_directory.resolve(strict=True)
    try:
        resolved_archive.relative_to(observation_root)
    except ValueError as error:
        raise ValueError("archive directory must resolve inside observation store") from error


def archive_observation(filepath: Path | str, archive_directory: Path | str) -> str:
    """Move an observation to an archive without replacing an existing note.

    The legacy ``archive/`` destination remains supported. A repository-local
    ``archived/`` destination accepts only sources resolved inside its sibling
    ``pending/`` directory.
    """
    archive_path = Path(archive_directory)
    source = Path(filepath)
    if archive_path.name == "archived":
        source = _require_pending_source(source, archive_path)
        _require_contained_archive_directory(archive_path)
    else:
        archive_path.mkdir(parents=True, exist_ok=True)
    target = archive_path / source.name
    if target.exists() or target.is_symlink():
        raise FileExistsError(f"archive destination already exists: {target}")
    shutil.move(str(source), str(target))
    return str(target)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Parse and manage superpowers observation notes."
    )
    parser.add_argument(
        "--project-root",
        type=Path,
        default=Path.cwd(),
        help="Repository root for the local observation store (default: current directory)",
    )
    parser.add_argument(
        "--obs-dir",
        type=Path,
        help="Legacy flat observations directory; overrides --project-root",
    )
    parser.add_argument("--init", action="store_true", help="Create the local store")
    parser.add_argument("--list", action="store_true", help="List pending observations as JSON")
    parser.add_argument("--archive", type=Path, help="Observation file to archive")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the observation utility and return a process status."""
    parser = _build_parser()
    args = parser.parse_args(argv)
    legacy_mode = args.obs_dir is not None

    if legacy_mode:
        observation_directory = args.obs_dir
        archive_directory = observation_directory / "archive"
        if args.init:
            observation_directory.mkdir(parents=True, exist_ok=True)
    else:
        store = ensure_observation_store(args.project_root) if (args.init or args.archive) else None
        observation_directory = observation_root(args.project_root)
        archive_directory = store["archived"] if store else observation_directory / "archived"

    if args.init and not legacy_mode:
        print(json.dumps({name: str(path) for name, path in store.items()}, indent=2))

    if args.list:
        observations = list_observations(
            observation_directory, repository_local=not legacy_mode
        )
        print(json.dumps(observations, indent=2))

    if args.archive:
        try:
            archived = archive_observation(args.archive, archive_directory)
        except (FileNotFoundError, FileExistsError, OSError, ValueError) as error:
            sys.stderr.write(f"Error: {error}\n")
            return 2
        print(f"Archived {args.archive} -> {archived}")

    if not (args.init or args.list or args.archive):
        parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
