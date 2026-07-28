#!/usr/bin/env python3
"""Discover, validate, and archive local skill-evolution observations."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import sys

from adapter_protocol import parse_frontmatter, validate_observation


_LIFECYCLE_NAMES = ("pending", "proposed", "archived")


def _resolve_project_root(project_root: Path) -> Path:
    """Resolve and validate the active repository root."""
    try:
        resolved = Path(project_root).resolve(strict=True)
    except OSError as error:
        raise ValueError(f"project root cannot be resolved: {error}") from error
    if not resolved.is_dir():
        raise ValueError("project root must be a directory")
    return resolved


def _require_local_directory(
    path: Path,
    *,
    label: str,
    project_root: Path,
    create: bool,
) -> Path:
    """Reject symlinks and require one directory beneath the project root."""
    if path.is_symlink():
        raise ValueError(f"repository observation store has symlinked {label}")
    if create:
        path.mkdir(exist_ok=True)
    try:
        resolved = path.resolve(strict=True)
    except OSError as error:
        raise ValueError(f"{label} directory cannot be resolved: {error}") from error
    if not resolved.is_dir():
        raise ValueError(f"{label} must be a directory")
    try:
        resolved.relative_to(project_root)
    except ValueError as error:
        raise ValueError(f"{label} must remain beneath the project root") from error
    return resolved


def _repository_project_root(observation_directory: Path) -> Path:
    """Infer the active root only from the canonical local-store shape."""
    root = (
        observation_directory.parent
        if observation_directory.name == "pending"
        else observation_directory
    )
    if root.name != "observations" or root.parent.name != ".superpowers":
        raise ValueError(
            "repository-local observations must use "
            "<project>/.superpowers/observations/"
        )
    return _resolve_project_root(root.parent.parent)


def _require_observation_store(
    project_root: Path, *, create: bool
) -> dict[str, Path]:
    """Validate every repository-local store component without following links."""
    resolved_project_root = _resolve_project_root(project_root)
    superpowers = resolved_project_root / ".superpowers"
    _require_local_directory(
        superpowers,
        label=".superpowers",
        project_root=resolved_project_root,
        create=create,
    )
    root = superpowers / "observations"
    _require_local_directory(
        root,
        label="observations",
        project_root=resolved_project_root,
        create=create,
    )
    store = {"root": root}
    for name in _LIFECYCLE_NAMES:
        directory = root / name
        _require_local_directory(
            directory,
            label=name,
            project_root=resolved_project_root,
            create=create,
        )
        store[name] = directory
    return store


def _observation_store_exists(project_root: Path) -> bool:
    """Return false for a missing store while rejecting unsafe components."""
    resolved_project_root = _resolve_project_root(project_root)
    components = (
        (".superpowers", resolved_project_root / ".superpowers"),
        (
            "observations",
            resolved_project_root / ".superpowers" / "observations",
        ),
        *(
            (
                name,
                resolved_project_root
                / ".superpowers"
                / "observations"
                / name,
            )
            for name in _LIFECYCLE_NAMES
        ),
    )
    for label, path in components:
        if path.is_symlink():
            raise ValueError(
                f"repository observation store has symlinked {label}"
            )
        if not path.exists():
            return False
        if not path.is_dir():
            raise ValueError(f"{label} must be a directory")
    return True


def observation_root(project_root: Path) -> Path:
    """Return the repository-local root for operational observations."""
    return _resolve_project_root(project_root) / ".superpowers" / "observations"


def ensure_observation_store(project_root: Path) -> dict[str, Path]:
    """Create the ignored lifecycle directories for one repository."""
    store = _require_observation_store(project_root, create=True)
    ignore_file = store["root"] / ".gitignore"
    if ignore_file.is_symlink():
        raise ValueError("repository observation store has symlinked .gitignore")
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


def _has_repository_local_shape(directory: Path) -> bool:
    """Recognize canonical local-store paths without inspecting their targets."""
    root = directory.parent if directory.name == "pending" else directory
    return root.name == "observations" and root.parent.name == ".superpowers"


def list_observations(
    obs_directory: Path | str, *, repository_local: bool | None = None
) -> list[dict[str, object]]:
    """List legacy notes or valid v1 notes in a repository-local pending queue."""
    directory = Path(obs_directory)
    if repository_local is None:
        repository_local = _has_repository_local_shape(directory) or (
            (directory / "pending").is_dir()
            or (
                directory.name == "pending"
                and (directory.parent / "proposed").is_dir()
                and (directory.parent / "archived").is_dir()
            )
        )
    if repository_local:
        source_directory = directory if directory.name == "pending" else directory / "pending"
        project_root = _repository_project_root(source_directory)
        if not _observation_store_exists(project_root):
            return []
        store = _require_observation_store(project_root, create=False)
        source_directory = store["pending"]
    else:
        source_directory = directory
    if not source_directory.is_dir():
        return []

    observations: list[dict[str, object]] = []
    for path in sorted(source_directory.iterdir()):
        if repository_local and path.is_symlink():
            sys.stderr.write(
                f"Warning: Ignoring symlinked observation note {path.name}\n"
            )
            continue
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


def _require_pending_source(source: Path, pending_directory: Path) -> Path:
    """Resolve a non-symlink v1 source inside the canonical pending queue."""
    if source.is_symlink():
        raise ValueError("observation source is a symlinked observation note")
    resolved_source = source.resolve(strict=True)
    try:
        resolved_source.relative_to(pending_directory)
    except ValueError as error:
        raise ValueError("observation source must resolve inside pending/") from error
    return resolved_source


def archive_observation(filepath: Path | str, archive_directory: Path | str) -> str:
    """Move an observation to an archive without replacing an existing note.

    The legacy ``archive/`` destination remains supported. A repository-local
    ``archived/`` destination accepts only sources resolved inside its sibling
    ``pending/`` directory.
    """
    archive_path = Path(archive_directory)
    source = Path(filepath)
    if archive_path.name == "archived":
        project_root = _repository_project_root(archive_path.parent)
        store = _require_observation_store(project_root, create=False)
        if archive_path.resolve(strict=False) != store["archived"]:
            raise ValueError("archive directory must be the canonical archived/")
        source = _require_pending_source(source, store["pending"])
        archive_path = store["archived"]
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
