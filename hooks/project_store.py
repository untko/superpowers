"""Where a project's `.superpowers` store lives: the main checkout, even from a worktree.

A linked worktree is removed when its branch merges, and anything written into
it goes with it. So the store always resolves to the main checkout's root,
read from git's own files with no subprocess. Outside git, the store is in the
working directory.
"""

from __future__ import annotations

from pathlib import Path

STORE_NAME = ".superpowers"


def _main_checkout(git_file: Path) -> Path | None:
    """The main checkout of the linked worktree whose `.git` file this is, or None."""
    try:
        text = git_file.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if not text.startswith("gitdir:"):
        return None
    gitdir = Path(text.removeprefix("gitdir:").strip())
    if not gitdir.is_absolute():
        gitdir = git_file.parent / gitdir
    try:
        common = (gitdir / (gitdir / "commondir").read_text(encoding="utf-8").strip()).resolve()
    except OSError:
        return None  # a submodule: its own checkout is the project
    return common.parent if common.name == ".git" else None


def project_root(cwd: str | Path | None) -> Path:
    """The main checkout's root for `cwd`, else `cwd` itself."""
    start = Path(cwd or ".").resolve()
    for directory in (start, *start.parents):
        marker = directory / ".git"
        if marker.is_dir():
            return directory
        if marker.is_file():
            return _main_checkout(marker) or directory
    return start


def store_dir(cwd: str | Path | None) -> Path:
    """The `.superpowers` directory the hooks read and write for `cwd`."""
    return project_root(cwd) / STORE_NAME
