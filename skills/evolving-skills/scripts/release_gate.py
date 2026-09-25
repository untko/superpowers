#!/usr/bin/env python3
"""Deterministic release gate: validate a skill-edit proposal before any eval runs."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Mapping

from adapter_protocol import parse_frontmatter

PROJECT_SKILL_DIRS = (".claude/skills", ".agents/skills")
FRICTION_LOG = Path(".superpowers") / "friction.jsonl"
MIN_FRICTION_SESSIONS = 2
DEFAULT_WORD_BUDGET = 500
SCRIPT_TEST_TIMEOUT = 300
# Each operation names one line; the fields it must carry, all single-line text.
OPERATION_FIELDS = {"add": ("file", "to"), "change": ("file", "line", "to"), "remove": ("file", "line")}
# Edits confined to these directories cannot change what the skill tells an agent to do.
STATIC_DIRS = ("references", "scripts")
_LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")


@dataclass
class Report:
    passed: bool
    kind: str | None = None  # "static" or "rule-change", once the operations apply
    reason: str | None = None
    detail: str = ""
    checks: list[str] = field(default_factory=list)  # checks passed, in order
    review: list[str] = field(default_factory=list)  # claims a human must confirm


class Rejected(Exception):
    def __init__(self, reason: str, detail: str) -> None:
        super().__init__(f"{reason}: {detail}")
        self.reason, self.detail = reason, detail


def _skill_dir(name: Any, scope: Any, library_root: Path, project: Path) -> Path | None:
    """The skill's directory in the repo its scope names, or None if it lives elsewhere."""
    if not isinstance(name, str) or not name or "/" in name or name.startswith("."):
        return None
    if scope == "global":
        candidates = [library_root / name]
    elif scope == "local":
        candidates = [project / d / name for d in PROJECT_SKILL_DIRS]
    else:
        return None
    library = library_root.resolve()
    for candidate in candidates:
        # A project link into the library is still a library skill.
        in_library = candidate.resolve().is_relative_to(library)
        if (candidate / "SKILL.md").is_file() and in_library == (scope == "global"):
            return candidate
    return None


def _single_line(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip()) and "\n" not in value and "\r" not in value


def _itemized(operations: Any) -> bool:
    """A non-empty list of add/change/remove operations, each touching one line."""
    if not isinstance(operations, list) or not operations:
        return False
    for operation in operations:
        if not isinstance(operation, dict):
            return False
        fields = OPERATION_FIELDS.get(operation.get("op"))
        if fields is None or not all(_single_line(operation.get(f)) for f in fields):
            return False
        if "after" in operation and not _single_line(operation["after"]):
            return False
    return True


def _friction_about(skill: str, project: Path) -> dict[str, dict[str, Any]]:
    """Events in the project's friction log attributed to this skill, by id."""
    events = {}
    try:
        with open(project / FRICTION_LOG, encoding="utf-8") as handle:
            for line in handle:
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                skills = event.get("skills") if isinstance(event, dict) else None
                if isinstance(skills, list) and any(
                    isinstance(s, dict) and s.get("name") == skill for s in skills
                ):
                    events[event.get("id")] = event
    except OSError:
        pass
    return events


def _has_case(skill: str, case_id: Any, evals_root: Path) -> bool:
    if not isinstance(case_id, str) or not case_id or "/" in case_id or case_id.startswith("."):
        return False
    cases = evals_root / skill
    return cases.is_dir() and any(path.stem == case_id for path in cases.iterdir())


def _sufficient_evidence(skill: str, evidence: Any, project: Path, evals_root: Path) -> bool:
    """A correction, a failing case, or friction from at least two sessions, all verifiable."""
    if not isinstance(evidence, list):
        return False
    friction = _friction_about(skill, project)
    sessions = set()
    for item in evidence:
        if not isinstance(item, dict):
            continue
        kind, item_id = item.get("type"), item.get("id")
        if kind == "case" and _has_case(skill, item_id, evals_root):
            return True
        event = friction.get(item_id) if isinstance(item_id, str) else None
        if event is None:
            continue
        if kind == "correction" and event.get("kind") == "correction":
            return True
        if kind == "friction":
            sessions.add(event.get("session_id"))
    return len(sessions) >= MIN_FRICTION_SESSIONS


def _only_line(lines: list[str], text: str, file: str) -> int:
    matches = [i for i, line in enumerate(lines) if line.strip() == text.strip()]
    if len(matches) != 1:
        found = "no" if not matches else f"{len(matches)}"
        raise Rejected("not-itemized", f"{file}: {found} lines read {text!r}")
    return matches[0]


def _apply(operation: Mapping[str, Any], skill_copy: Path) -> None:
    """Apply one line operation to the working copy, keeping the edited line's indentation."""
    target = (skill_copy / operation["file"]).resolve()
    if not target.is_relative_to(skill_copy.resolve()):
        raise Rejected("scope", f"{operation['file']} is outside the skill")
    exists = target.is_file()
    if not exists and not (operation["op"] == "add" and "after" not in operation):
        raise Rejected("not-itemized", f"{operation['file']} does not exist")
    lines = target.read_text(encoding="utf-8").splitlines() if exists else []
    if operation["op"] == "add":
        after = operation.get("after")
        index = len(lines) if after is None else _only_line(lines, after, operation["file"]) + 1
        lines.insert(index, operation["to"])
    else:
        index = _only_line(lines, operation["line"], operation["file"])
        if operation["op"] == "remove":
            del lines[index]
        else:
            indent = lines[index][: len(lines[index]) - len(lines[index].lstrip())]
            lines[index] = indent + operation["to"].strip()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _limits(skill_md: Path) -> tuple[dict[str, str], int, str]:
    """A SKILL.md's frozen anchors (name to line), word budget, and full text."""
    text = skill_md.read_text(encoding="utf-8")
    try:
        metadata, _ = parse_frontmatter(text)
    except ValueError as error:
        raise Rejected("anchor", f"frontmatter unreadable, anchors unknown: {error}") from error
    extra = metadata.get("metadata") if isinstance(metadata.get("metadata"), dict) else {}
    frozen = extra.get("frozen") if isinstance(extra.get("frozen"), dict) else {}
    budget = extra.get("word-budget", DEFAULT_WORD_BUDGET)
    if not isinstance(budget, int) or isinstance(budget, bool):
        raise Rejected("budget", f"word-budget must be an integer, got {budget!r}")
    return {k: str(v) for k, v in frozen.items()}, budget, text


def _check_anchors(original: Path, edited: Path) -> None:
    anchors = _limits(original)[0]
    edited_anchors, _, after = _limits(edited)
    if edited_anchors != anchors:
        changed = sorted({k for k, _ in set(anchors.items()) ^ set(edited_anchors.items())})
        raise Rejected("anchor", f"anchor declarations changed: {', '.join(changed)}")
    body = {line.strip() for line in parse_frontmatter(after)[1].splitlines()}
    lost = [name for name, line in anchors.items() if line.strip() not in body]
    if lost:
        raise Rejected("anchor", f"frozen anchor edited or removed: {', '.join(lost)}")


def _check_budget(original: Path, edited: Path) -> None:
    """Hold SKILL.md to its budget; a skill already over it may shrink but not grow."""
    _, budget, before = _limits(original)
    _, edited_budget, after = _limits(edited)
    if edited_budget != budget:
        raise Rejected("budget", f"word budget changed from {budget} to {edited_budget}")
    words_before, words_after = len(before.split()), len(after.split())
    if words_after > budget and words_after > words_before:
        raise Rejected("budget", f"SKILL.md grows to {words_after} words, budget {budget}")


def _check_links(operations: list[Mapping[str, Any]], skill_dir: Path, skill_copy: Path) -> None:
    """Every relative link an operation writes must resolve, in the edited skill or beside it."""
    for operation in operations:
        for target in _LINK.findall(operation.get("to", "") if operation["op"] != "remove" else ""):
            if "://" in target or target.startswith(("#", "mailto:")):
                continue
            relative = Path(operation["file"]).parent / target.split("#", 1)[0]
            if not ((skill_copy / relative).exists() or (skill_dir / relative).exists()):
                raise Rejected("links", f"{operation['file']}: {target} does not resolve")


def _check_script_tests(skill_copy: Path) -> None:
    """Run the edited skill's own unittest suite; the harness and model play no part."""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "unittest", "discover", "-s", "tests"],
            cwd=skill_copy,
            capture_output=True,
            text=True,
            timeout=SCRIPT_TEST_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        raise Rejected("script-tests", f"tests exceeded {SCRIPT_TEST_TIMEOUT}s") from None
    if result.returncode != 0:
        raise Rejected("script-tests", result.stderr.strip().splitlines()[-1] if result.stderr else "")


def _classify(operations: list[Mapping[str, Any]]) -> tuple[str, list[str]]:
    """Static when no operation can change a rule; claimed rewordings go to human review."""
    review = []
    for operation in operations:
        if Path(operation["file"]).parts[0] in STATIC_DIRS:
            continue
        if operation["file"] == "SKILL.md" and operation["op"] == "change" and operation.get("wording") is True:
            review.append(f"wording-only claim: {operation['line']!r} -> {operation['to']!r}")
            continue
        return "rule-change", []
    return "static", review


def _run_checks(proposal: Mapping[str, Any], report: Report, *, library_root: Path, project: Path,
                evals_root: Path) -> None:
    skill_dir = _skill_dir(proposal.get("skill"), proposal.get("scope"), library_root, project)
    if skill_dir is None:
        raise Rejected("scope", "skill not found in the repo its scope names")
    report.checks.append("scope")
    operations = proposal.get("operations")
    if not _itemized(operations):
        raise Rejected("not-itemized", "operations must each add, change, or remove one line")
    report.checks.append("itemized")
    if not _sufficient_evidence(skill_dir.name, proposal.get("evidence"), project, evals_root):
        raise Rejected(
            "insufficient-evidence",
            "cite a correction, a failing case, or the same friction in two sessions",
        )
    report.checks.append("evidence")
    with tempfile.TemporaryDirectory() as work:
        skill_copy = Path(work) / skill_dir.name
        shutil.copytree(skill_dir, skill_copy)
        for operation in operations:
            _apply(operation, skill_copy)
        report.kind, report.review = _classify(operations)
        _check_anchors(skill_dir / "SKILL.md", skill_copy / "SKILL.md")
        report.checks.append("anchor")
        _check_budget(skill_dir / "SKILL.md", skill_copy / "SKILL.md")
        report.checks.append("budget")
        _check_links(operations, skill_dir, skill_copy)
        report.checks.append("links")
        if any(Path(op["file"]).parts[0] == "scripts" for op in operations):
            if (skill_copy / "tests").is_dir():
                _check_script_tests(skill_copy)
                report.checks.append("script-tests")
            else:
                report.review.append("scripts changed and the skill has no tests")
    if report.kind == "rule-change":
        raise Rejected("eval-skipped", "no runner chosen")


def check(
    proposal: Mapping[str, Any], *, library_root: Path, project: Path, evals_root: Path
) -> Report:
    """Run the gate's own checks on one proposal; the report names the first rejection."""
    report = Report(passed=False)
    try:
        _run_checks(proposal, report, library_root=library_root, project=project,
                    evals_root=evals_root)
    except Rejected as rejection:
        report.reason, report.detail = rejection.reason, rejection.detail
        return report
    report.passed = True
    return report


def main(argv: list[str] | None = None) -> int:
    library = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("proposal", type=Path)
    parser.add_argument("--project", type=Path, default=Path.cwd())
    parser.add_argument("--library-root", type=Path, default=library)
    parser.add_argument("--evals-root", type=Path, default=library.parent / "evals")
    args = parser.parse_args(argv)
    proposal = json.loads(args.proposal.read_text(encoding="utf-8"))
    report = check(
        proposal,
        library_root=args.library_root,
        project=args.project.resolve(),
        evals_root=args.evals_root,
    )
    print(json.dumps(asdict(report), indent=2))
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
