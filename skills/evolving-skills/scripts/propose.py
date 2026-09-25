#!/usr/bin/env python3
"""Proposer batch run: rank a project's friction, stage skill copies, and turn edits into proposals."""

from __future__ import annotations

import argparse
import difflib
import json
import shutil
import sys
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path

import release_gate
from parse_observations import list_observations
from release_gate import (
    FRICTION_LOG,
    MIN_FRICTION_SESSIONS,
    SCHEMA,
    Usage,
    _safe_name,
    _single_line,
    _skill_dir,
)

MARKER = ".proposer"
WORK_DIR = "proposer"
WORKSPACE = "workspace"
PROPOSALS = "proposals"
BRIEF = "brief.md"
RUNTIME = FRICTION_LOG.parent  # the project's .superpowers directory
OBSERVATIONS = RUNTIME / "observations"
HANDLED_NAME = "friction-handled.txt"
DEFAULT_LIMIT = 3
EXCERPT_LIMIT = 300
SCOPES = ("global", "local")


@dataclass
class Candidate:
    """One skill's friction in this batch, and the directory that owns it."""
    name: str
    scope: str
    events: list[dict] = field(default_factory=list)
    corrections: int = 0
    sessions: set[str] = field(default_factory=set)
    recent: int = 0  # events in which this skill was the last one loaded
    skill_dir: Path | None = None


def _library_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _handled(project: Path) -> set[str]:
    """Ids a previous run dismissed: their friction is not proposed again."""
    try:
        text = (project / RUNTIME / HANDLED_NAME).read_text(encoding="utf-8")
    except OSError:
        return set()
    return {line.strip() for line in text.splitlines() if line.strip()}


def _events(project: Path) -> list[dict]:
    """This project's friction, with malformed lines and handled ids dropped."""
    handled = _handled(project)
    events = []
    try:
        with open(project / FRICTION_LOG, encoding="utf-8") as handle:
            for line in handle:
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(event, dict) or event.get("id") in handled:
                    continue
                if isinstance(event.get("skills"), list) and isinstance(event.get("id"), str):
                    events.append(event)
    except OSError:
        pass
    return events


def _groups(events: list[dict]) -> dict[tuple[str, str], Candidate]:
    """Friction grouped by each skill an event names, in load order."""
    groups: dict[tuple[str, str], Candidate] = {}
    for event in events:
        loaded = [skill for skill in event["skills"] if isinstance(skill, dict)]
        for index, skill in enumerate(loaded):
            name, scope = skill.get("name"), skill.get("source")
            if not isinstance(name, str) or scope not in SCOPES:
                continue
            group = groups.setdefault((name, scope), Candidate(name=name, scope=scope))
            group.events.append(event)
            if event.get("kind") == "correction":
                group.corrections += 1
            if _single_line(event.get("session_id")):
                group.sessions.add(event["session_id"])
            if index == len(loaded) - 1:
                group.recent += 1
    return groups


def _sufficient(group: Candidate) -> bool:
    """A correction, or friction in enough sessions: the gate's own evidence rule."""
    return bool(group.corrections) or len(group.sessions) >= MIN_FRICTION_SESSIONS


def _rank(group: Candidate) -> tuple[int, int, int, str]:
    """Corrections, then sessions, then recency, then name, best first."""
    return (-group.corrections, -len(group.sessions), -group.recent, group.name)


def _candidates(groups: dict[tuple[str, str], Candidate], library_root: Path,
                project: Path) -> list[Candidate]:
    """The skills whose friction the gate would accept, in the order the brief should read."""
    kept = []
    for group in groups.values():
        if not _sufficient(group):
            continue
        group.skill_dir = _skill_dir(group.name, group.scope, library_root, project)
        if group.skill_dir is not None:
            kept.append(group)
    return sorted(kept, key=_rank)


def _evidence(group: Candidate) -> list[dict]:
    """Every id behind the candidate, corrections first, in the order the log recorded them."""
    cited = []
    for correction in (True, False):
        for event in group.events:
            if (event.get("kind") == "correction") is correction:
                cited.append({"type": "correction" if correction else "friction",
                              "id": event["id"]})
    return cited


def _excerpt(value: object) -> str:
    """One line of at most EXCERPT_LIMIT characters."""
    text = value if isinstance(value, str) else json.dumps(value)
    return " ".join(text.split())[:EXCERPT_LIMIT]


def _title(note: dict) -> str:
    """One observation's filename stem and its first line of body."""
    body = note.get("content") if isinstance(note.get("content"), str) else ""
    first = next((line.strip() for line in body.splitlines() if line.strip()), "")
    return f"- {Path(str(note.get('filename') or '')).stem}: {first}".rstrip()


def _notes(project: Path) -> dict[str, list[str]]:
    """Pending observation titles per skill: context for the agent, never evidence."""
    try:
        notes = list_observations(project / OBSERVATIONS)
    except (OSError, ValueError):
        return {}
    by_skill: dict[str, list[str]] = {}
    for note in notes:
        skill = note.get("skill")
        if isinstance(skill, str):
            by_skill.setdefault(skill, []).append(_title(note))
    return by_skill


def _brief(project: Path, work: Path, groups: list[Candidate]) -> str:
    """What the agent reads before deciding: skill, scope, counts, friction, notes."""
    notes = _notes(project)
    lines = ["# Proposer batch run", "", f"- work: {work}", f"- project: {project}", ""]
    for group in groups:
        lines += [f"## {group.name} ({group.scope})", "",
                  f"- corrections: {group.corrections}",
                  f"- sessions: {len(group.sessions)}",
                  f"- events: {len(group.events)}",
                  "", "Friction:", ""]
        lines += [f"- {event.get('kind')}: {_excerpt(event.get('excerpt'))}"
                  for event in group.events]
        if notes.get(group.name):
            lines += ["", "Pending observations (context, not evidence):", ""] + notes[group.name]
        lines.append("")
    return "\n".join(lines) + "\n"


def _work_dir(out: Path) -> Path:
    """An empty work directory, replacing an earlier run's only when it is marked as ours."""
    if out.exists():
        if not (out.is_dir() and (out / MARKER).is_file()):
            raise Usage(f"{out} is not empty and holds no {MARKER} marker; move it or pass --out")
        shutil.rmtree(out)
    out.mkdir(parents=True)
    (out / MARKER).write_text(f"proposer work directory for {out}\n", encoding="utf-8")
    for name in (WORKSPACE, PROPOSALS):
        (out / name).mkdir()
    return out


def _tree(root: Path) -> set[str]:
    """Every file under a skill copy, as paths relative to it."""
    return {path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()}


def _read(root: Path, name: str) -> bytes | None:
    path = root / name
    return path.read_bytes() if path.is_file() else None


def _lines(data: bytes, name: str) -> list[str]:
    """One text file as its lines; the gate edits lines, so a binary file cannot be proposed."""
    try:
        return data.decode("utf-8").splitlines()
    except UnicodeDecodeError:
        raise Usage(f"{name} is not text, and the gate edits lines") from None


def _insert(name: str, lines: list[str], prev: str | None, next_line: str | None) -> list[dict]:
    """Add operations placing lines between two neighbours, anchored on one that has text."""
    if next_line is None:
        return [{"op": "add", "file": name, "to": line} for line in lines]
    if next_line.strip():
        return [{"op": "add", "file": name, "before": next_line, "to": line} for line in lines]
    if prev is not None and prev.strip():
        return [{"op": "add", "file": name, "after": prev, "to": line} for line in reversed(lines)]
    raise Usage(f"{name}: {lines[0]!r} sits between blank lines; put a line with text next to it")


def _change(name: str, line: str, to: str, wording: bool) -> dict:
    """One changed line, claimed as a rewording only in SKILL.md and only when asked."""
    operation = {"op": "change", "file": name, "line": line, "to": to}
    if wording and name == "SKILL.md":
        operation["wording"] = True
    return operation


def _line_ops(name: str, before: list[str], after: list[str], wording: bool) -> list[dict]:
    """The operations turning one file into the next, in the order the gate applies them."""
    matcher = difflib.SequenceMatcher(a=before, b=after, autojunk=False)
    operations: list[dict] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        old, new = before[i1:i2], after[j1:j2]
        pairs = min(len(old), len(new))
        operations += [_change(name, old[index], new[index], wording) for index in range(pairs)]
        operations += [{"op": "remove", "file": name, "line": line} for line in old[pairs:]]
        if new[pairs:]:
            # Earlier hunks are already applied, so the line above is the edited file's line.
            prev = after[j1 + pairs - 1] if j1 + pairs else None
            next_line = before[i2] if i2 < len(before) else None
            operations += _insert(name, new[pairs:], prev, next_line)
    return operations


def _operations(skill_dir: Path, workspace: Path, *, wording: bool) -> list[dict]:
    """Every line operation separating the agent's copy from the skill it was copied from."""
    original, edited = _tree(skill_dir), _tree(workspace)
    operations: list[dict] = []
    for name in sorted(original | edited):
        before, after = _read(skill_dir, name), _read(workspace, name)
        if before == after:
            continue
        if name not in original:
            operations += _insert(name, _lines(after, name), None, None)
        elif name not in edited:
            raise Usage(f"{name} is deleted; a proposal can only add, change, or remove lines")
        else:
            operations += _line_ops(name, _lines(before, name), _lines(after, name), wording)
    for operation in operations:
        if "line" in operation and not _single_line(operation["line"]):
            raise Usage(f"{operation['file']}: the gate cannot name a blank line to change or remove; "
                        "keep it")
    return operations


def _verify(operations: list[dict], skill_dir: Path, workspace: Path) -> None:
    """Apply the operations to a fresh copy and insist the result is the agent's own copy."""
    with tempfile.TemporaryDirectory() as work:
        replay = Path(work) / skill_dir.name
        shutil.copytree(skill_dir, replay, symlinks=True)
        for operation in operations:
            try:
                release_gate._apply(operation, replay)
            except release_gate.Rejected as rejection:
                raise Usage(f"{rejection.detail}; make the edited lines unique, "
                            "or edit fewer lines") from None
        for name in sorted(_tree(replay) | _tree(workspace)):
            if _read(replay, name) != _read(workspace, name):
                raise Usage(f"{name}: the operations do not reproduce this edit; "
                            "make the edited lines unique, or edit fewer lines")


def _write_skeleton(path: Path, group: Candidate) -> None:
    """The proposal an agent fills in, carrying its evidence and no operations yet."""
    proposal = {"schema": SCHEMA, "skill": group.name, "scope": group.scope,
                "operations": [], "evidence": _evidence(group)}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(proposal, indent=2) + "\n", encoding="utf-8")


def _prepare(args: argparse.Namespace) -> int:
    if args.limit < 1:
        raise Usage("--limit must be at least 1")
    project = args.project.resolve()
    out = (args.out or project / RUNTIME / WORK_DIR).resolve()
    groups = _candidates(_groups(_events(project)), args.library_root.resolve(), project)
    groups = groups[: args.limit]
    _work_dir(out)
    for group in groups:
        shutil.copytree(group.skill_dir, out / WORKSPACE / group.name, symlinks=False)
        _write_skeleton(out / PROPOSALS / f"{group.name}.json", group)
    (out / BRIEF).write_text(_brief(project, out, groups), encoding="utf-8")
    print(out)
    for group in groups:
        print(f"{group.name} ({group.scope})")
    if not groups:
        print("no candidates")
    return 0


def _proposal_path(work: Path, skill: str) -> Path:
    """The proposal file for one skill, refused before anything else when the name is unsafe."""
    if not _safe_name(skill):
        raise Usage(f"{skill!r} is not a skill name")
    return work / PROPOSALS / f"{skill}.json"


def _load(path: Path) -> dict:
    try:
        proposal = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise Usage(f"{path}: {error}") from None
    if not isinstance(proposal, dict):
        raise Usage(f"{path}: a proposal is a JSON object")
    return proposal


def _collect(args: argparse.Namespace) -> int:
    work = args.work.resolve()
    path = _proposal_path(work, args.skill)
    skeleton = _load(path)
    project = args.project.resolve()
    skill_dir = _skill_dir(skeleton.get("skill"), skeleton.get("scope"),
                           args.library_root.resolve(), project)
    if skill_dir is None:
        raise Usage(f"{skeleton.get('skill')!r} does not resolve in the repo its scope names")
    runner = release_gate.build_runner(args.cli, args.model)
    workspace = work / WORKSPACE / args.skill
    if not (workspace / "SKILL.md").is_file():
        raise Usage(f"no staged copy of {args.skill} under {work / WORKSPACE}")
    operations = _operations(skill_dir, workspace, wording=args.wording)
    if not operations:
        raise Usage(f"no edit in workspace at {workspace}")
    _verify(operations, skill_dir, workspace)
    proposal = {**skeleton, "operations": operations}
    path.write_text(json.dumps(proposal, indent=2) + "\n", encoding="utf-8")
    report = release_gate.check(
        proposal,
        library_root=args.library_root.resolve(),
        project=project,
        evals_root=args.evals_root,
        runner=runner,
    )
    print(json.dumps(asdict(report), indent=2))
    return 0 if report.passed else 1


def _dismiss(args: argparse.Namespace) -> int:
    """Record the evidence as handled and drop the staged copy, so it is not proposed again."""
    work = args.work.resolve()
    proposal = _load(_proposal_path(work, args.skill))
    evidence = proposal.get("evidence") if isinstance(proposal.get("evidence"), list) else []
    handled = args.project.resolve() / RUNTIME / HANDLED_NAME
    handled.parent.mkdir(parents=True, exist_ok=True)
    with open(handled, "a", encoding="utf-8") as handle:
        for item in evidence:
            if isinstance(item, dict) and isinstance(item.get("id"), str):
                handle.write(item["id"] + "\n")
    (work / PROPOSALS / f"{args.skill}.json").unlink()
    shutil.rmtree(work / WORKSPACE / args.skill)
    print(f"dismissed {args.skill}")
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    prepare = commands.add_parser("prepare", help="rank the friction and stage the candidates")
    prepare.add_argument("--project", type=Path, default=Path.cwd())
    prepare.add_argument("--library-root", type=Path, default=_library_root())
    prepare.add_argument("--out", type=Path, help=f"work directory (default: <project>/.superpowers/{WORK_DIR})")
    prepare.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    collect = commands.add_parser("collect", help="turn a workspace edit into a proposal and gate it")
    collect.add_argument("work", type=Path)
    collect.add_argument("skill")
    collect.add_argument("--wording", action="store_true", help="claim SKILL.md changes reword a rule")
    collect.add_argument("--project", type=Path, default=Path.cwd())
    collect.add_argument("--library-root", type=Path, default=_library_root())
    collect.add_argument("--evals-root", type=Path, default=_library_root().parent / "evals")
    collect.add_argument("--cli", help="model CLI to run evals with, with --model")
    collect.add_argument("--model", help="model to run evals with, with --cli")
    dismiss = commands.add_parser("dismiss", help="record a candidate's evidence as handled")
    dismiss.add_argument("work", type=Path)
    dismiss.add_argument("skill")
    dismiss.add_argument("--project", type=Path, default=Path.cwd())
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "prepare":
            return _prepare(args)
        if args.command == "collect":
            return _collect(args)
        return _dismiss(args)
    except Usage as usage:
        print(f"propose: {usage}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
